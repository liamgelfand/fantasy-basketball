"""Day-by-day add/drop planning: today's open slot first, then later days on the updated roster."""
from dataclasses import replace

from fakes import streaming_league

from fbb.engine import Engine
from fbb.report import build_report


def plan_of(data):
    engine = Engine(data)
    return engine, engine.move_plan


def test_fills_todays_open_slot_then_plans_tomorrow():
    engine, plan = plan_of(streaming_league())
    assert 0.3 < engine.projection.win_matchup_prob < 0.7  # tight matchup
    assert [(m.sp, m.add.name) for m in plan.moves] == [(7, "SF Today"), (8, "SF Later")]

    today, tomorrow = plan.moves
    assert today.drop is None  # a roster spot is open, so no drop
    assert today.fills == ["SF"] and today.gain > 0
    assert tomorrow.drop is not None  # the roster is full after today's add
    assert tomorrow.fills == ["SF"]

    # Today's game still counts after the later move, and the plan beats doing nothing.
    day7 = next(d for d in plan.after.mine.days if d.sp == 7)
    assert "SF Today" in day7.started and day7.open_slots == 0
    assert plan.after.expected_wins > plan.before.expected_wins
    assert plan.notes and "MAX_WEEKLY_ADDS" in plan.notes[0]  # league has a limit, config doesn't


def test_full_roster_requires_a_drop():
    _, plan = plan_of(streaming_league(full_roster=True))
    first = plan.moves[0]
    assert (first.sp, first.add.name) == (7, "SF Today")
    assert first.drop is not None
    assert all(m.drop is not None for m in plan.moves)


def test_today_already_tipped_is_skipped():
    data = streaming_league()
    data.started = True
    engine, plan = plan_of(data)
    assert 7 not in engine.move_days
    assert all(m.sp > 7 for m in plan.moves)
    assert "SF Today" not in [m.add.name for m in plan.moves]  # plays only today: nothing left to gain
    assert plan.moves[0].add.name == "SF Later"
    assert any("tipped" in n for n in plan.notes)


def test_weekly_cap_limits_the_sequence():
    data = streaming_league()
    data.cfg = replace(data.cfg, max_weekly_adds=2, adds_used_this_week=1)
    engine, plan = plan_of(data)
    assert engine.adds_left == 1
    assert len(plan.moves) == 1 and plan.capped
    assert plan.moves[0].add.name == "SF Later"  # the bigger of the two moves
    assert any("Weekly add limit" in n for n in plan.notes)

    data = streaming_league()
    data.cfg = replace(data.cfg, max_weekly_adds=4, adds_used_this_week=4)
    _, plan = plan_of(data)
    assert plan.moves == [] and plan.capped


def test_unbinding_cap_keeps_full_plan():
    data = streaming_league()
    data.cfg = replace(data.cfg, max_weekly_adds=5)
    _, plan = plan_of(data)
    assert len(plan.moves) == 2 and not plan.capped and plan.adds_left == 5


def test_free_agent_board_times_the_add():
    engine = Engine(streaming_league())
    rows = {r["player"].name: r for r in engine.free_agent_board}
    assert rows["SF Today"]["add_sp"] == 7
    assert rows["SF Later"]["add_sp"] == 8
    assert engine.fa_row(rows["SF Later"])["add_on"] == "2026-10-27"


def test_report_and_agent_show_the_plan():
    from fbb.agent import FantasyAgent

    engine = Engine(streaming_league())
    text = build_report(engine)
    assert "Add/drop plan by day" in text
    assert "Today: add **SF Today**" in text and "Tomorrow: add **SF Later**" in text

    text, is_error = FantasyAgent(engine)._run_tool("move_plan", {})
    assert not is_error and '"day":"today"' in text and "SF Later" in text
