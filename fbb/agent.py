"""Claude agent over the league data. Claude calls these tools; we run them locally against the snapshot.

Runs through the Claude Agent SDK, which drives Claude Code with your claude.ai login, so usage
counts against your Claude plan (Pro/Max) instead of API credits.
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultError,
    ResultMessage,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

from .config import ROOT
from .engine import Engine
from .report import build_report

# With an API key in the environment, Claude Code bills the API instead of the plan login. The key
# is only ever read by this agent, so drop it once here (e.g. one left over in .env).
for _var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
    os.environ.pop(_var, None)


def _hide_child_consoles() -> None:
    """Under pythonw, every console child (the SDK's `claude` CLI, `claude auth status`) pops up its own
    console window. The SDK spawns via anyio with no creationflags, so add CREATE_NO_WINDOW to all Popens."""
    if getattr(subprocess.Popen.__init__, "_fbb_no_window", False):
        return
    original = subprocess.Popen.__init__

    def __init__(self, *args, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        original(self, *args, **kwargs)

    __init__._fbb_no_window = True
    subprocess.Popen.__init__ = __init__


if sys.platform == "win32":
    _hide_child_consoles()

SERVER = "league"
TOOL_PREFIX = f"mcp__{SERVER}__"
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
AGENT_DIR = ROOT / ".fbb" / "agent"  # Claude Code keeps session transcripts per working directory
RECAP_CHARS = 20_000


def subscription_ready() -> bool:
    """True when Claude Code is installed and logged in, so the assistant can run on the plan."""
    claude = shutil.which("claude")
    if claude:
        try:
            out = subprocess.run([claude, "auth", "status"], capture_output=True, text=True, timeout=20).stdout
            return json.loads(out).get("loggedIn") is True
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return (Path.home() / ".claude" / ".credentials.json").exists()


def _text(content) -> str:
    """Plain text of a stored message (a string, or API-style content blocks from older chats)."""
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")

SYSTEM_PROMPT = """You are a sharp fantasy basketball analyst advising the manager of one team in an ESPN league.

You have tools that read a live snapshot of the league: rosters, the current matchup with a
lineup-aware projection, free agents, player details and news, standings, and a move simulator
that re-projects the matchup after hypothetical adds and drops. Ground every claim in tool output
and say which numbers drove the call. Use web search for news ESPN's feed may lag on: injury
updates, minutes changes, rotation news, return timelines. Mention dates when you cite news.

Nothing you suggest is executed automatically: the manager makes the moves in the ESPN app. So be
concrete: exact player names, which day, which slot, who to drop. For streaming, start from
move_plan: an empty lineup slot today is production lost for good once games tip. Before
recommending an add/drop, run simulate_moves on it. Weigh this week's matchup against rest-of-season value and say which
one a recommendation is for. Respect acquisition limits and punted categories.

Today is {today}. League: {league} ({scoring}). The manager's team: {team}."""


def _json(obj) -> str:
    return json.dumps(obj, default=str, separators=(",", ":"))


class FantasyAgent:
    def __init__(self, engine: Engine, query_fn=query):
        self.engine = engine
        self.data = engine.data
        self.cfg = engine.cfg
        self._query = query_fn  # injectable for tests
        self.messages: list[dict] = []
        self.session_id: str | None = None  # Claude Code session to resume for follow-ups
        self.tools, self.handlers = self._build_tools()
        self.system = SYSTEM_PROMPT.format(
            today=dt.date.today().isoformat(),
            league=self.data.name,
            scoring=self.data.scoring_type,
            team=self.data.my_team.name,
        )

    # ---------- tools ----------

    def _resolve_players(self, names: list[str]) -> tuple[list, list[str]]:
        found, missing = [], []
        for n in names:
            p = self.data.find_player(n)
            (found if p else missing).append(p or n)
        return found, missing

    def _build_tools(self) -> tuple[list[dict], dict[str, Callable[..., object]]]:
        e, d = self.engine, self.data
        window_desc = "Stats window: blend (season blended with projection early in the year), season, last_30, last_15, last_7, projected."

        def league_overview():
            return {
                "league": d.name, "scoring_type": d.scoring_type,
                "categories": [asdict(c) for c in d.categories],
                "starting_slots": d.lineup_slots, "roster_spots": d.roster_size,
                "acquisition_rules": d.acquisition_rules,
                "my_team": {"name": d.my_team.name, "record": d.my_team.record, "standing": d.my_team.standing,
                            "acquisitions_this_season": d.my_team.acquisitions},
                "adds_left_this_week": e.adds_left,  # league limit - adds in ESPN's activity feed; None = no limit or unread
                "punted_categories": sorted(self.cfg.punt_categories),
                "stat_window_in_use": self.cfg.stat_window,
                "today_scoring_period": d.today_sp, "todays_games_started": d.today_started(),
            }

        def my_roster():
            return {
                "team": e.team_summary(d.my_team),
                "lineup_check_today": e.lineup_check(),
                "weakest_spots": [p.name for p in e.drop_candidates[:4]],
            }

        def matchup_projection():
            return e.projection_summary()

        def team_roster(team: str):
            t = d.find_team(team)
            return e.team_summary(t) if t else {"error": f"No team matching {team!r}",
                                                "teams": [x.name for x in d.teams.values()]}

        def free_agents(position: str | None = None, limit: int = 15, sort: str = "matchup"):
            rows = e.free_agents_at(position.upper(), size=max(limit * 2, 30)) if position else e.free_agent_board
            matchup = lambda r: e.matchup_gain(r["result"])
            key = {"matchup": matchup, "season": lambda r: r["value"],
                   "weighted": lambda r: r["weighted_value"]}.get(sort, matchup)
            return [e.fa_row(r) for r in sorted(rows, key=key, reverse=True)[:limit]]

        def player_details(name: str, include_news: bool = True):
            p = d.find_player(name)
            if not p:
                return {"error": f"No player matching {name!r}"}
            out = e.player_summary(p, detail=True)
            if include_news:
                try:
                    out["news"] = d.player_news(p)
                except Exception as ex:
                    out["news_error"] = str(ex)
            return out

        def simulate_moves(add: list[str] | None = None, drop: list[str] | None = None):
            adds, miss_a = self._resolve_players(add or [])
            drops, miss_d = self._resolve_players(drop or [])
            if miss_a or miss_d:
                return {"error": f"Could not find: {miss_a + miss_d}"}
            mine = {p.id for p in d.my_team.roster}
            bad = [p.name for p in drops if p.id not in mine]
            if bad:
                return {"error": f"Not on your roster: {bad}"}
            result = asdict(e.simulate(adds, drops))
            result["notes"] += e.ownership_notes(adds)
            return result

        def move_plan():
            return e.move_plan_summary()

        def evaluate_trade(give: list[str], receive: list[str]):
            gives, m1 = self._resolve_players(give)
            gets, m2 = self._resolve_players(receive)
            if m1 or m2:
                return {"error": f"Could not find: {m1 + m2}"}
            return e.evaluate_trade(gives, gets)

        def standings():
            return [{"standing": t.standing, "team": t.name, "record": t.record, "points_for": t.points_for}
                    for t in d.standings()]

        def recent_activity(limit: int = 20):
            return d.recent_activity(limit)

        def full_report():
            return build_report(e)

        handlers = {f.__name__: f for f in (league_overview, my_roster, matchup_projection, team_roster, free_agents,
                                            player_details, simulate_moves, move_plan, evaluate_trade, standings,
                                            recent_activity, full_report)}
        names = {"type": "array", "items": {"type": "string"}}
        schema = lambda props=None, req=None: {"type": "object", "properties": props or {}, "required": req or []}
        tools = [
            {"name": "league_overview", "description": "League settings: categories, roster slots, acquisition limits, my record.", "input_schema": schema()},
            {"name": "my_roster", "description": f"My roster with per-game stats, z-score values, injury status, games left this matchup and rest of season, plus a check of today's lineup. {window_desc}", "input_schema": schema()},
            {"name": "matchup_projection", "description": "Current matchup: live category totals, lineup-aware projected finals, per-category win probabilities, and a day-by-day plan of starts, open slots and benched games for both teams.", "input_schema": schema()},
            {"name": "team_roster", "description": "Another fantasy team's roster and record. Accepts team name, abbreviation, or id.", "input_schema": schema({"team": {"type": "string"}}, ["team"])},
            {"name": "free_agents", "description": "Free agents ranked by sort='matchup' (this matchup's gain after the best drop: projected fantasy points in points leagues, expected categories in category leagues), 'season' (rest-of-season z value), or 'weighted' (value weighted toward swing categories). Optional position filter: PG, SG, SF, PF, C, G, F.",
             "input_schema": schema({"position": {"type": "string"}, "limit": {"type": "integer"},
                                     "sort": {"type": "string", "enum": ["matchup", "season", "weighted"]}})},
            {"name": "player_details", "description": "One player in depth: every stats window (season, last 30/15/7, projected), upcoming game dates, owner, and recent ESPN news.",
             "input_schema": schema({"name": {"type": "string"}, "include_news": {"type": "boolean"}}, ["name"])},
            {"name": "simulate_moves", "description": "Re-project the current matchup after adding and/or dropping players. Returns expected categories won and win probability before and after, per-category changes, and rest-of-season value change.",
             "input_schema": schema({"add": names, "drop": names})},
            {"name": "move_plan", "description": "Dated add/drop sequence for the rest of the matchup, built day by day: today's moves first (e.g. a free agent who plays today filling an empty lineup slot, no drop needed if a roster spot is open), then each later day's best move on the roster left by the earlier ones. Respects the league's weekly add limit, counting this week's adds from ESPN's activity feed. Today is skipped once its games have tipped.",
             "input_schema": schema()},
            {"name": "evaluate_trade", "description": "Evaluate a trade from my side: per-category z-score and per-game changes, rest-of-season games, and the effect on this matchup.",
             "input_schema": schema({"give": names, "receive": names}, ["give", "receive"])},
            {"name": "standings", "description": "League standings.", "input_schema": schema()},
            {"name": "recent_activity", "description": "Recent league adds, drops and trades.", "input_schema": schema({"limit": {"type": "integer"}})},
            {"name": "full_report", "description": "The full deterministic markdown report (matchup, roster, pickups, standings). Good starting point for broad questions.", "input_schema": schema()},
        ]
        return tools, handlers

    def _run_tool(self, name: str, args: dict) -> tuple[str, bool]:
        try:
            result = self.handlers[name](**args)
            text = result if isinstance(result, str) else _json(result)
            return text, isinstance(result, dict) and "error" in result
        except Exception as ex:  # report tool failures to Claude instead of crashing the loop
            return f"Tool {name} failed: {type(ex).__name__}: {ex}", True

    def _server(self):
        """The league tools as an in-process MCP server that Claude Code calls into."""
        def wrap(name: str):
            async def run(args: dict) -> dict:
                text, is_error = await asyncio.to_thread(self._run_tool, name, dict(args or {}))
                return {"content": [{"type": "text", "text": text}], "is_error": is_error}
            return run

        sdk_tools = [tool(t["name"], t["description"], t["input_schema"])(wrap(t["name"])) for t in self.tools]
        return create_sdk_mcp_server(SERVER, tools=sdk_tools)

    def _options(self, max_turns: int) -> ClaudeAgentOptions:
        builtin = ["WebSearch"] if self.cfg.web_search else []
        AGENT_DIR.mkdir(parents=True, exist_ok=True)
        return ClaudeAgentOptions(
            system_prompt=self.system,
            model=self.cfg.model,
            effort=self.cfg.effort if self.cfg.effort in EFFORTS else None,
            tools=builtin,  # no file, shell, or other Claude Code tools: league tools and web search only
            allowed_tools=[TOOL_PREFIX + t["name"] for t in self.tools] + builtin,
            mcp_servers={SERVER: self._server()},
            setting_sources=[],  # ignore any CLAUDE.md or settings on this machine
            cwd=AGENT_DIR,
            max_turns=max_turns,
            resume=self.session_id,
        )

    # ---------- history ----------

    def export_messages(self) -> list[dict]:
        """History as plain JSON-able dicts: the questions and Claude's answers."""
        return [dict(m) for m in self.messages]

    def import_messages(self, messages: list[dict]) -> None:
        """Restore a saved chat. The next question carries a recap, since a restored chat has no live session."""
        self.messages = list(messages)
        self.session_id = None

    def _recap(self) -> str:
        lines = [f"{'Manager' if m['role'] == 'user' else 'You'}: {_text(m['content'])}"
                 for m in self.messages if _text(m["content"]).strip()]
        return "\n\n".join(lines)[-RECAP_CHARS:]

    # ---------- loop ----------

    def ask(self, question: str, on_tool: Callable[[str, dict], None] | None = None, max_turns: int = 25,
            cancel: threading.Event | None = None) -> str:
        """Send one user message, let Claude run tools until it answers, and keep the history for follow-ups.

        Setting `cancel` stops the run (and the Claude Code process) promptly. A stopped question stays
        in the history without an answer.
        """
        prompt = question
        if self.session_id is None and self.messages:
            prompt = f"Our conversation so far:\n\n{self._recap()}\n\n---\n\nNew question:\n{question}"
        self.messages.append({"role": "user", "content": question})
        if cancel is not None and cancel.is_set():
            return "Stopped."
        answer = asyncio.run(self._run(prompt, on_tool, max_turns, cancel))
        if answer is None:
            return "Stopped."
        self.messages.append({"role": "assistant", "content": answer})
        return answer

    async def _run(self, prompt: str, on_tool, max_turns: int, cancel: threading.Event | None) -> str | None:
        result: ResultMessage | None = None

        async def consume() -> None:
            nonlocal result
            try:
                async for message in self._query(prompt=prompt, options=self._options(max_turns)):
                    if isinstance(message, AssistantMessage) and on_tool:
                        for block in message.content:
                            if isinstance(block, ToolUseBlock):
                                name = block.name.removeprefix(TOOL_PREFIX)
                                on_tool("web_search" if name == "WebSearch" else name, dict(block.input or {}))
                    elif isinstance(message, ResultMessage):
                        result = message
            except ResultError:
                # Claude Code exits with an error after an error result (turn limit, usage limit, ...);
                # the result it already sent says what happened, so handle that below instead.
                if result is None or not result.is_error:
                    raise

        job = asyncio.create_task(consume())
        while not job.done():
            if cancel is not None and cancel.is_set():
                job.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await job
                return None
            await asyncio.wait({job}, timeout=0.2)
        job.result()  # re-raise a failure from the Claude Code process

        if result is None:
            raise RuntimeError("Claude Code ended without an answer")
        self.session_id = result.session_id
        if result.stop_reason == "refusal":
            return "Claude declined to answer this request."
        if result.subtype == "error_max_turns":
            return "Stopped: too many tool rounds without a final answer."
        if result.is_error:
            raise RuntimeError("; ".join(result.errors or []) or f"Claude Code error ({result.subtype})")
        return (result.result or "").strip()


AI_REPORT_PROMPT = """Write my game plan for this matchup and the week ahead.

Start from full_report, then dig in where it matters: check news (and the web) for any injured
or questionable players on my roster, my opponent's roster, and the top pickup candidates;
check move_plan and simulate the adds and drops you're considering; check if any trade target fits my category needs.

Output markdown with these sections:
1. **Bottom line**: 2-3 sentences on where the matchup stands and the single most important move.
2. **Moves to make**: a numbered list of exact actions (add/drop/lineup/IR) with the day and reason.
3. **Category strategy**: which categories to chase, protect, or concede this week, and why.
4. **Injury & news watch**: what to monitor and when to re-check.
5. **Longer-term**: roster construction, sell-high/buy-low, trade ideas.
"""
