"""HTTP API tests against the synthetic league: no ESPN or Claude calls."""
import json

import pytest
from fakes import FakeData
from fastapi.testclient import TestClient

from fbb.api import create_app
from fbb.api.services import ChatSessions, ChatStore, LeagueService
from fbb.engine import Engine


class EchoAgent:
    """Stands in for FantasyAgent: reports one tool call, then echoes the question."""

    def __init__(self, engine):
        self.engine = engine
        self.messages = []

    def ask(self, question, on_tool=None, cancel=None):
        self.messages.append({"role": "user", "content": question})
        if on_tool:
            on_tool("my_roster", {})
        answer = f"echo: {question} (turn {len(self.messages) // 2 + 1})"
        self.messages.append({"role": "assistant", "content": answer})
        return answer

    def export_messages(self):
        return list(self.messages)

    def import_messages(self, messages):
        self.messages = list(messages)


def make_app(service, chats=None, chat_enabled=True, web_dist=None):
    return create_app(service, chats or ChatSessions(EchoAgent), chat_enabled=chat_enabled, web_dist=web_dist,
                      allowed_hosts=["testserver"])


@pytest.fixture
def builds():
    return []


@pytest.fixture
def client(builds):
    def factory(cfg):
        builds.append(cfg)
        data = FakeData()
        data.cfg = cfg
        return Engine(data)

    return TestClient(make_app(LeagueService(FakeData().cfg, factory=factory)))


def sse_events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_meta_and_settings_are_cached_per_window(client, builds):
    meta = client.get("/api/meta").json()
    assert meta["my_team"]["name"] == "Team 1"
    assert meta["chat_enabled"] is True
    assert len(meta["teams"]) == 4
    client.get("/api/roster")
    assert len(builds) == 1  # same settings reuse the snapshot

    meta = client.get("/api/meta", params={"window": "last_15", "punt": ["FT%", "TO"]}).json()
    assert meta["stat_window"] == "last_15"
    assert meta["punt_categories"] == ["FT%", "TO"]
    assert len(builds) == 2

    assert client.post("/api/refresh").status_code == 204
    client.get("/api/meta")
    assert len(builds) == 3


def test_invalid_window_rejected(client):
    assert client.get("/api/meta", params={"window": "forever"}).status_code == 422


def test_matchup_shape(client):
    m = client.get("/api/matchup").json()
    assert m["opponent"]["name"] == "Team 2"
    assert len(m["categories"]) == 9
    assert 0 <= m["win_prob"] <= 1
    assert len(m["days"]) == len(m["schedule"]["days"]) == 5
    assert all(len(r["cells"]) == 5 for r in m["schedule"]["rows"])


def test_roster_and_free_agents(client):
    roster = client.get("/api/roster").json()
    assert len(roster["players"]) == 13
    values = [p["value"] for p in roster["players"]]
    assert values == sorted(values, reverse=True)

    board = client.get("/api/free-agents").json()
    gains = [r["matchup_gain"] for r in board["rows"]]
    assert gains and gains == sorted(gains, reverse=True)
    assert client.get("/api/free-agents", params={"position": "XX"}).status_code == 422


def test_simulate(client):
    res = client.post("/api/simulate", json={"add": ["Player 60"], "drop": ["Player 5"]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["add"] == ["Player 60"] and body["drop"] == ["Player 5"]

    assert client.post("/api/simulate", json={}).status_code == 422
    bad = client.post("/api/simulate", json={"drop": ["Player 20"]})  # on Team 2, not mine
    assert bad.status_code == 422 and "Not on Team 1" in bad.json()["detail"]
    mine = client.post("/api/simulate", json={"add": ["Player 0"]})
    assert mine.status_code == 422 and "Already on your roster" in mine.json()["detail"]
    taken = client.post("/api/simulate", json={"add": ["Player 20"], "drop": ["Player 5"]}).json()
    assert any("trade target" in n for n in taken["notes"])


def test_trade(client):
    partner = client.get("/api/teams/2/roster").json()
    res = client.post("/api/trades/evaluate",
                      json={"partner_id": 2, "give": ["Player 0"], "get": [partner["players"][0]]})
    assert res.status_code == 200, res.text
    assert set(res.json()["per_game_change"]) >= {"PTS", "REB"}
    assert client.post("/api/trades/evaluate", json={"partner_id": 1, "give": ["Player 0"],
                                                     "get": ["Player 1"]}).status_code == 404


def test_league_and_report(client):
    standings = client.get("/api/standings").json()
    assert sum(t["is_me"] for t in standings) == 1
    assert client.get("/api/activity").json()[0]["action"] == "FA ADDED"
    assert "Do this now" in client.get("/api/report").json()["markdown"]


def test_chat_streams_tools_then_answer(client):
    sid = client.post("/api/assistant/sessions").json()["id"]
    res = client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "who do I drop?"})
    assert res.headers["content-type"].startswith("text/event-stream")
    events = sse_events(res.text)
    assert [e for e, _ in events] == ["tool", "answer"]
    assert events[0][1]["label"] == "my roster"
    assert events[1][1]["text"] == "echo: who do I drop? (turn 1)"

    assert client.post("/api/assistant/sessions/nope/messages", json={"text": "hi"}).status_code == 404
    assert client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": ""}).status_code == 422


def test_chat_disabled_without_key(builds):
    service = LeagueService(FakeData().cfg, factory=lambda cfg: Engine(FakeData()))
    client = TestClient(make_app(service, chat_enabled=False))
    res = client.post("/api/assistant/sessions")
    assert res.status_code == 503 and "ANTHROPIC_API_KEY" in res.json()["detail"]


def test_upstream_failure_is_503():
    def broken(cfg):
        raise SystemExit("ESPN_LEAGUE_ID is not set.")

    client = TestClient(make_app(LeagueService(FakeData().cfg, factory=broken), chat_enabled=False))
    res = client.get("/api/meta")
    assert res.status_code == 503 and "ESPN_LEAGUE_ID" in res.json()["detail"]


def test_serves_web_client_with_spa_fallback(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    service = LeagueService(FakeData().cfg, factory=lambda cfg: Engine(FakeData()))
    client = TestClient(make_app(service, chat_enabled=False, web_dist=tmp_path))
    assert "root" in client.get("/roster").text
    assert client.get("/favicon.svg").text == "<svg/>"
    assert client.get("/api/nope").status_code == 404


def test_chat_follows_refreshed_data_and_keeps_history(client, builds):
    sid = client.post("/api/assistant/sessions").json()["id"]
    client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "first"})
    client.post("/api/refresh")
    events = sse_events(client.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "second"}).text)
    assert events[-1][1]["text"] == "echo: second (turn 2)"  # history carried over
    state = client.app.state.chats.get(sid, None)
    assert state.engine is client.app.state.league.snapshot().engine  # rebound to the new snapshot


def test_chat_survives_restart(tmp_path, builds):
    service = LeagueService(FakeData().cfg, factory=lambda cfg: Engine(FakeData()))
    first = TestClient(make_app(service, ChatSessions(EchoAgent, ChatStore(tmp_path))))
    sid = first.post("/api/assistant/sessions").json()["id"]
    first.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "remember me"})

    restarted = TestClient(make_app(service, ChatSessions(EchoAgent, ChatStore(tmp_path))))
    events = sse_events(restarted.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "again"}).text)
    assert events[-1][1]["text"] == "echo: again (turn 2)"

    restarted.delete(f"/api/assistant/sessions/{sid}")
    assert restarted.post(f"/api/assistant/sessions/{sid}/messages", json={"text": "x"}).status_code == 404
    assert restarted.post("/api/assistant/sessions/../../etc/messages", json={"text": "x"}).status_code == 404


def test_untrusted_host_rejected(builds):
    service = LeagueService(FakeData().cfg, factory=lambda cfg: Engine(FakeData()))
    client = TestClient(create_app(service, ChatSessions(EchoAgent), web_dist=None, allowed_hosts=["localhost"]))
    assert client.get("/api/meta").status_code == 400
    assert client.get("/api/meta", headers={"host": "localhost"}).status_code == 200


def test_agent_stops_when_cancelled():
    import threading

    from fbb.agent import FantasyAgent

    class NoCalls:
        class beta:
            class messages:
                @staticmethod
                def create(**_):
                    raise AssertionError("should not call the API after cancel")

    agent = FantasyAgent(Engine(FakeData()), client=NoCalls())
    cancel = threading.Event()
    cancel.set()
    assert agent.ask("hi", cancel=cancel) == "Stopped."
    assert agent.export_messages() == [{"role": "user", "content": "hi"}]


def test_player_detail(client):
    roster = client.get("/api/roster").json()
    pid = roster["players"][0]["id"]
    detail = client.get(f"/api/players/{pid}").json()
    assert detail["is_mine"] and detail["owner"] == "Team 1"
    assert "season" in detail["windows"]
    assert detail["news"][0]["headline"].endswith("cleared to play")
    fa = client.get("/api/free-agents").json()["rows"][0]["id"]
    assert client.get(f"/api/players/{fa}").json()["owner"] is None
    assert client.get("/api/players/999999").status_code == 404


def test_closing_the_stream_cancels_the_agent():
    import threading
    import time

    stopped = threading.Event()

    class SlowAgent(EchoAgent):
        def ask(self, question, on_tool=None, cancel=None):
            on_tool("matchup_projection", {})
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if cancel is not None and cancel.is_set():
                    stopped.set()
                    return "Stopped."
                time.sleep(0.02)
            return "finished without being cancelled"

    service = LeagueService(FakeData().cfg, factory=lambda cfg: Engine(FakeData()))
    client = TestClient(make_app(service, ChatSessions(SlowAgent)))
    sid = client.post("/api/assistant/sessions").json()["id"]
    with client.stream("POST", f"/api/assistant/sessions/{sid}/messages", json={"text": "slow"}) as res:
        first = next(res.iter_lines())
        assert first == "event: tool"
    assert stopped.wait(3), "agent kept running after the client went away"
