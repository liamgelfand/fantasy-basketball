"""Offline tests: a synthetic league exercises valuation, lineups, projection, report, and agent tools."""
import random

import pytest
from fakes import CATS, SLOTS, FakeData, make_player

from fbb.analysis import Valuer, daily_starters, win_prob
from fbb.engine import Engine
from fbb.espn import Category
from fbb.report import build_report


@pytest.fixture
def engine():
    return Engine(FakeData())


def test_valuer_orders_better_player_higher():
    rng = random.Random(1)
    pool = [make_player(i, rng) for i in range(50)]
    v = Valuer(pool, CATS)
    star = make_player(999, rng)
    star.per_game.update(PTS=35, REB=12, AST=9, STL=2, BLK=2, TO=1, **{"3PM": 4})
    assert v.total(star) > max(v.total(p) for p in pool[:10])
    assert v.z(star)["TO"] > 0  # few turnovers is good


def test_lineup_respects_slots_and_value():
    rng = random.Random(2)
    roster = [make_player(i, rng) for i in range(13)]
    for p in roster:
        p.game_days = {1}
    centers = [p for p in roster if p.eligible_slots[0] == "C"]
    rank = {p.id: -p.id for p in roster}
    starters = daily_starters(roster, 1, SLOTS, rank)
    assert len(starters) == len(SLOTS)
    assert any(p in starters for p in centers)  # C slot must be filled by a C-eligible player
    assert len({p.id for p in starters}) == len(starters)


def test_win_prob_direction():
    assert win_prob(Category("PTS"), 300, 250, 20, 20) > 0.9
    assert win_prob(Category("TO", True), 30, 40, 3, 3) > 0.9
    assert win_prob(Category("PTS"), 100, 100, 0, 0) == 0.5


def test_projection_and_moves(engine):
    proj = engine.projection
    assert 0 <= proj.expected_wins <= len(CATS)
    assert 0 <= proj.win_matchup_prob <= 1
    assert proj.mine.remaining_games > 0
    best = engine.top_streamers(3)
    assert best and best[0]["result"].gain >= best[-1]["result"].gain
    # dropping a healthy starter for nobody should not help
    worst_case = engine.simulate([], [engine.data.my_team.roster[0]])
    assert worst_case.expected_wins_after <= worst_case.expected_wins_before + 1e-9


def test_report_renders(engine):
    text = build_report(engine)
    for section in ("Do this now", "Matchup vs Team 2", "Your roster", "Best pickups", "Standings"):
        assert section in text
    assert "Player 12" in text  # the OUT player shows up as an IR candidate or in the roster


def test_agent_tools_run_offline(engine):
    from fbb.agent import FantasyAgent

    agent = FantasyAgent(engine, client=object())
    for name, args in [("league_overview", {}), ("my_roster", {}), ("matchup_projection", {}),
                       ("free_agents", {"sort": "season", "limit": 5}), ("standings", {}),
                       ("simulate_moves", {"add": ["Player 60"], "drop": ["Player 5"]}),
                       ("evaluate_trade", {"give": ["Player 0"], "receive": ["Player 13"]}),
                       ("team_roster", {"team": "Team 3"}), ("full_report", {})]:
        text, is_error = agent._run_tool(name, args)
        assert not is_error, (name, text)
