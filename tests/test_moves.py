"""Day-by-day add/drop planning: today's open slot first, then later days on the updated roster."""
import datetime as dt
from types import SimpleNamespace

from fakes import activity, streaming_league

from fbb.analysis import plan_moves
from fbb.engine import Engine
from fbb.espn import ACTIVITY_PAGE, LeagueData
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
    assert plan.adds_left == 3 and not plan.capped  # limit 4, one add used this week


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


def test_counts_only_my_adds_this_matchup():
    engine = Engine(streaming_league())
    # The fake feed has my waiver claim this week, plus my drop, my trade, another team's add
    # and my add from last week, none of which count.
    assert engine.weekly_adds == (4, 1, [])
    assert engine.adds_left == 3
    summary = engine.move_plan_summary()
    assert summary["weekly_add_limit"] == 4 and summary["adds_used_this_week"] == 1
    assert summary["adds_left_this_week"] == 3


def test_weekly_cap_limits_the_sequence():
    data = streaming_league()
    data.acquisition_rules = {"matchup_acquisition_limit": 2}
    engine, plan = plan_of(data)
    assert engine.adds_left == 1
    assert len(plan.moves) == 1 and plan.capped
    assert plan.moves[0].add.name == "SF Later"  # the bigger of the two moves
    assert any("Weekly add limit" in n for n in plan.notes)

    data = streaming_league()
    data.activity += [activity(dt.datetime(2026, 10, 25, 9 + h), 1, "FA ADDED") for h in range(5)]
    engine, plan = plan_of(data)
    assert engine.weekly_adds[1] == 6 and engine.adds_left == 0  # never negative
    assert plan.moves == [] and plan.capped


def test_unbinding_cap_keeps_full_plan():
    data = streaming_league()
    data.acquisition_rules = {"matchup_acquisition_limit": 5}
    _, plan = plan_of(data)
    assert len(plan.moves) == 2 and not plan.capped and plan.adds_left == 4


def test_no_league_limit_is_uncapped():
    for limit in (None, 0, -1):
        data = streaming_league()
        data.acquisition_rules = {"matchup_acquisition_limit": limit}
        data.activity_error = AssertionError("no limit: the feed isn't needed")
        engine, plan = plan_of(data)
        assert engine.adds_left is None and engine.weekly_adds == (None, None, [])
        assert len(plan.moves) == 2 and not plan.capped


def test_activity_failure_leaves_plan_uncapped_with_a_note():
    data = streaming_league()
    data.acquisition_rules = {"matchup_acquisition_limit": 1}
    data.activity_error = RuntimeError("401")
    engine, plan = plan_of(data)
    assert engine.adds_left is None and plan.adds_left is None
    assert len(plan.moves) == 2 and not plan.capped
    assert any("couldn't be read from ESPN" in n for n in plan.notes)
    assert engine.move_plan_summary()["adds_used_this_week"] is None


def test_count_exceeding_season_total_is_flagged():
    data = streaming_league()
    data.teams[1].acquisitions = 0
    engine = Engine(data)
    assert engine.adds_left == 3 and "may be off" in engine.weekly_adds[2][0]


def test_no_same_day_add_then_drop_and_no_limit_stays_short():
    import random

    from fakes import FakeData, make_player

    data = FakeData()
    rng = random.Random(3)
    data._fas = [make_player(2000 + i, rng) for i in range(75)]
    data.acquisition_rules = {"matchup_acquisition_limit": None}
    engine, plan = plan_of(data)
    assert 0 < len(plan.moves) <= len(engine.move_days)

    # Uncapped with a low bar, the planner streams a lot: a pickup is never dropped the day it's added.
    long_plan = plan_moves(data, engine.projection, data.my_team.roster, data.free_agents(), engine.matchup_now[1],
                           engine.valuer, engine.rank, data.roster_size, engine.move_days, min_gain=0.02)
    assert len(long_plan.moves) > len(engine.move_days)
    added_on = {}
    for m in long_plan.moves:
        assert not (m.drop and added_on.get(m.drop.id) == m.sp), f"{m.drop.name} added and dropped on sp {m.sp}"
        added_on[m.add.id] = m.sp


def stub_league_data(pages: list[list], start: dt.date, sp_start: dict | None = None) -> tuple[LeagueData, list[int]]:
    """A LeagueData over a stub espn_api League whose recent_activity serves `pages`."""
    offsets = []

    def recent_activity(size=25, msg_type=None, offset=0, include_moved=False):
        offsets.append(offset)
        return pages[offset // size] if offset // size < len(pages) else []

    data = LeagueData.__new__(LeagueData)
    data.league = SimpleNamespace(recent_activity=recent_activity)
    data.my_team_id = 1
    data.today_sp = 10
    data.sp_start = sp_start or {10: dt.datetime.combine(start, dt.time(19))}
    data.__dict__["matchup_periods"] = ([10], [11, 12])
    return data, offsets


def test_espn_counting_pages_until_matchup_start():
    start = dt.date(2026, 11, 2)
    this_week = dt.datetime(2026, 11, 4, 12)
    def others(n):
        return [activity(this_week, 2, "FA ADDED")] * n

    pages = [
        [activity(this_week, 1, "FA ADDED"), activity(this_week, 1, "DROPPED")] + others(ACTIVITY_PAGE - 2),
        [activity(this_week, 1, "WAIVER ADDED"), activity(this_week, 1, "TRADED")] + others(ACTIVITY_PAGE - 4)
        + [activity(dt.datetime(2026, 11, 2, 0, 5), 1, "FA ADDED"),  # just after local midnight: counts
           activity(dt.datetime(2026, 11, 1, 23, 55), 1, "FA ADDED")],  # previous matchup
        [activity(this_week, 1, "FA ADDED")],  # never requested: page 2 already reached last week
    ]
    data, offsets = stub_league_data(pages, start)
    assert data.matchup_start == dt.datetime(2026, 11, 2)
    assert data.adds_used_this_matchup() == 3
    assert offsets == [0, ACTIVITY_PAGE]


def test_adds_after_previous_days_tip_count_toward_this_matchup():
    sunday_tip = dt.datetime(2026, 11, 1, 18)
    feed = [activity(dt.datetime(2026, 11, 3), 1, "FA ADDED"),
            activity(dt.datetime(2026, 11, 1, 21), 1, "FA ADDED"),  # Sunday night: effective Monday
            activity(dt.datetime(2026, 11, 1, 12), 1, "FA ADDED")]  # before Sunday's games: last week
    data, _ = stub_league_data([feed], dt.date(2026, 11, 2),
                               {9: sunday_tip, 10: dt.datetime(2026, 11, 2, 19)})
    assert data.matchup_start == sunday_tip
    assert data.adds_used_this_matchup() == 2


def test_espn_counting_stops_at_end_of_feed():
    data, offsets = stub_league_data([[activity(dt.datetime(2026, 11, 3), 1, "FA ADDED")]], dt.date(2026, 11, 2))
    assert data.adds_used_this_matchup() == 1 and offsets == [0]


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
