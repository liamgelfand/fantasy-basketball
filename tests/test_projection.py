"""Player projection (fbb/projection.py) and the short/long horizons built on it (Engine)."""
import dataclasses
import datetime as dt
import random
from types import SimpleNamespace

import pytest
from fakes import STRONG, FakeData, make_player, streaming_league

from fbb.analysis import ASSUMED_OUT_DAYS
from fbb.engine import DROP_POOL, Engine
from fbb.espn import LeagueData, PlayerInfo
from fbb.projection import LONG, SHORT, estimate, project

SEASON = {"MIN": 20.0, "PTS": 10.0, "REB": 4.0, "AST": 2.0, "STL": 0.8, "BLK": 0.4, "TO": 1.0,
          "FGA": 9.0, "FGM": 4.05, "FTA": 2.0, "FTM": 1.6, "3PA": 3.0, "3PM": 1.05,
          "FG%": 0.45, "FT%": 0.8, "3PT%": 0.35}
PRESEASON = {**SEASON, "MIN": 24.0, "PTS": 12.0, "FGA": 10.0, "FGM": 4.6, "FG%": 0.46}


def scaled(stats: dict, minutes: float) -> dict:
    """Same per-minute production and percentages at different minutes."""
    k = minutes / stats["MIN"]
    out = {s: v * k for s, v in stats.items() if "%" not in s}
    return {**out, **{s: v for s, v in stats.items() if "%" in s}, "MIN": minutes}


def model(gp: float, last_7: dict | None = None, l7_gp: float = 3, horizon=LONG):
    windows, gps = {"season": SEASON, "projected": PRESEASON}, {"season": gp}
    if last_7:
        windows["last_7"], gps["last_7"] = last_7, l7_gp
    return estimate(windows, gps, horizon)


# ---------------------------------------------------------------- per-game estimate

def test_preseason_prior_decays_fast_with_games_played():
    weights = [model(gp).prior_weight for gp in (0, 1, 5, 10, 15, 30)]
    assert weights[0] == 1.0  # no games: the projection is all there is
    assert weights == sorted(weights, reverse=True)
    assert weights[3] < 0.3  # 10 GP: the old blend still gave the projection 50%
    assert weights[4] <= 0.25 and weights[5] < 0.15
    # and the projection follows: at 30 GP it sits close to the season line
    assert abs(model(30).per_game["PTS"] - SEASON["PTS"]) < 0.35


def test_minutes_jump_raises_projection():
    base = model(20)
    promoted = model(20, scaled(SEASON, 32.0))
    assert promoted.role_change == pytest.approx(12.0)
    assert promoted.per_game["MIN"] > base.per_game["MIN"] + 4
    assert promoted.per_game["PTS"] > base.per_game["PTS"] * 1.2
    assert promoted.weights["last_7"] > 0.3
    assert "Minutes up" in promoted.note
    short = model(20, scaled(SEASON, 32.0), horizon=SHORT)
    assert short.per_game["MIN"] > promoted.per_game["MIN"]  # the short term leans harder on the new role
    benched = model(20, scaled(SEASON, 12.0))
    assert benched.role_change < 0 and benched.per_game["PTS"] < base.per_game["PTS"] * 0.85


def test_hot_shooting_at_same_minutes_barely_moves_it():
    base = model(20)
    hot = {**SEASON, "FGM": 6.3, "FG%": 0.7, "3PM": 2.1, "3PT%": 0.7, "PTS": 15.5}
    long, short = model(20, hot), model(20, hot, horizon=SHORT)
    assert long.role_change == 0
    assert long.per_game["PTS"] == pytest.approx(base.per_game["PTS"])  # a streak isn't a new talent level
    assert abs(short.per_game["PTS"] - base.per_game["PTS"]) < 0.05 * base.per_game["PTS"]
    assert short.per_game["FG%"] < 0.47  # percentages are regressed by attempts, never chased


def test_shooting_regressed_toward_prior_and_ratios_consistent():
    cold = {**SEASON, "FGM": 3.15, "FG%": 0.35, "PTS": 8.2}  # 35% over 5 games, projected at 46%
    est = estimate({"season": cold, "projected": PRESEASON}, {"season": 5})
    assert 0.38 < est.per_game["FG%"] < 0.46
    assert est.per_game["FG%"] == pytest.approx(est.per_game["FGM"] / est.per_game["FGA"])
    assert est.per_game["FT%"] == pytest.approx(est.per_game["FTM"] / est.per_game["FTA"])


def test_missing_windows_fall_back_gracefully():
    assert estimate({}, {}).per_game == {}
    only_prior = estimate({"projected": PRESEASON}, {})
    assert only_prior.prior_weight == 1.0 and only_prior.per_game["PTS"] == pytest.approx(PRESEASON["PTS"])
    zero_gp = estimate({"season": SEASON, "projected": PRESEASON}, {"season": 0})
    assert zero_gp.prior_weight == 1.0 and "No games yet" in zero_gp.note
    no_prior = estimate({"season": SEASON}, {"season": 6})
    assert no_prior.per_game["PTS"] == pytest.approx(SEASON["PTS"]) and no_prior.prior_weight == 0
    recent_only = estimate({"last_15": SEASON}, {"last_15": 4})
    assert recent_only.per_game == SEASON
    no_minutes = {k: v for k, v in SEASON.items() if k != "MIN"}
    est = estimate({"season": no_minutes, "projected": PRESEASON, "last_7": scaled(SEASON, 34.0)},
                   {"season": 10, "last_7": 3})
    assert est.role_change == 0 and est.recent_window is None  # no season minutes: no role inference
    assert 10.0 < est.per_game["PTS"] < 12.0  # plain per-game blend of season and projection
    # a recent window with too few games isn't trusted for a role change
    assert model(20, scaled(SEASON, 32.0), l7_gp=1).role_change == 0


def test_to_player_uses_model_window_by_default():
    def split(avg, gp):
        return {"avg": avg, "total": {"GP": gp}, "applied_avg": 0}
    card = SimpleNamespace(
        playerId=7, name="Role Player", proTeam="BOS", position="SF", eligibleSlots=["SF", "F", "UT", "BE"],
        lineupSlot="BE", injuryStatus="ACTIVE", expected_return_date=None,
        stats={"2027_total": split(SEASON, 20), "2027_projected": split(PRESEASON, 70),
               "2027_last_7": split(scaled(SEASON, 32.0), 3)})
    data = LeagueData.__new__(LeagueData)
    data.year, data.pro_schedule = 2027, {}
    data.cfg = dataclasses.replace(FakeData().cfg, stat_window="model")
    p = data.to_player(card)
    long, short = project({"season": {**SEASON, "FPTS": 0}, "projected": {**PRESEASON, "FPTS": 0},
                           "last_7": {**scaled(SEASON, 32.0), "FPTS": 0}}, {"season": 20, "projected": 70, "last_7": 3})
    assert p.window == "model" and p.per_game["PTS"] == pytest.approx(long.per_game["PTS"])
    assert p.near_term["PTS"] == pytest.approx(short.per_game["PTS"]) and p.near_term["PTS"] > p.per_game["PTS"]
    assert p.minutes_trend > 0 and "Minutes up" in p.projection_note
    assert {"model", "model_short", "season", "blend"} <= set(p.windows)

    data.cfg = dataclasses.replace(data.cfg, stat_window="season")  # explicit windows still override
    p = data.to_player(card)
    assert p.per_game["PTS"] == SEASON["PTS"] and p.short_term == {} and p.near_term is p.per_game


# ---------------------------------------------------------------- horizons

def _best_player(engine: Engine) -> PlayerInfo:
    roster = [p for p in engine.data.my_team.roster if p.injury_status == "ACTIVE"]
    return max(roster, key=engine.value)


def test_long_injury_discounts_ros_value_not_this_matchup():
    data = FakeData()
    engine = Engine(data)
    star = _best_player(engine)
    healthy = engine.ros_value(star)
    r = engine.replacement_level
    today = data.sp_date(data.today_sp)

    def with_status(back):
        star.injury_status, star.expected_return = "OUT", back
        e = Engine(data)
        return e.ros_value(star), e.projection.expected_wins, e.simulate([], [star])

    end_of_matchup = data.sp_date(max(data.matchup_periods[1]))
    ros_long, wins_long, drop_long = with_status(today + dt.timedelta(weeks=6))
    ros_open, wins_open, drop_open = with_status(None)  # no date: assumed ~ASSUMED_OUT_DAYS
    ros_soon, _, _ = with_status(today + dt.timedelta(days=2))
    ros_next_week, wins_next_week, _ = with_status(end_of_matchup + dt.timedelta(days=1))
    assert r < ros_long < r + 0.4 * (healthy - r)  # most of the season gone: close to replacement level
    assert ros_long < ros_open < ros_next_week < ros_soon
    assert ros_soon > r + 0.85 * (healthy - r)  # back in two days: barely discounted
    assert ASSUMED_OUT_DAYS == 14

    # This matchup is unaffected by how long the absence lasts beyond it: OUT all week either way.
    assert wins_long == pytest.approx(wins_open) == pytest.approx(wins_next_week)
    assert drop_long.gain == pytest.approx(drop_open.gain)
    assert drop_long.gain == pytest.approx(0, abs=1e-9)  # out all week: dropping costs nothing now
    assert any("expected back" in n for n in drop_long.notes)


def test_drop_candidates_weigh_injury_and_minutes():
    data = FakeData()
    engine = Engine(data)
    star = _best_player(engine)
    assert star not in engine.drop_pool

    today = data.sp_date(data.today_sp)
    star.injury_status, star.expected_return = "OUT", today + dt.timedelta(weeks=7)
    fringe = sorted(data.my_team.roster, key=engine.value)[-3]  # a solid player by per-game value
    fringe.short_term = {**fringe.per_game, "MIN": 11.0}
    fringe.minutes_trend, fringe.projection_note = -9.0, "Minutes down: 11.0 over the last 7 days vs 20.0."
    engine = Engine(data)
    order = [p.id for p in engine.drop_candidates]
    assert order.index(star.id) < order.index(sorted(data.my_team.roster, key=engine.value)[-2].id)
    assert star in engine.drop_pool and fringe in engine.drop_pool
    assert len(engine.drop_pool) > DROP_POOL
    assert any("expected back" in f for f in engine.drop_flags(star))
    assert any("Minutes down" in f for f in engine.drop_flags(fringe))
    # healthy, steady players aren't flagged
    steady = [p for p in data.my_team.roster if p.id not in (star.id, fringe.id) and p.injury_status == "ACTIVE"]
    assert all(not engine.drop_flags(p) for p in steady)


def test_short_term_projection_uses_near_term_stats():
    data = streaming_league()
    base = Engine(data).projection.mine.final["PTS"]
    for p in data.my_team.roster:
        p.short_term = {**p.per_game, "PTS": p.per_game["PTS"] + 5}
    assert Engine(data).projection.mine.final["PTS"] > base + 10


def test_moves_are_labeled_streamer_or_stash():
    data = streaming_league(full_roster=True)
    weak = make_player(700, random.Random(5))
    weak.name, weak.eligible_slots, weak.game_days = "SF Scrub", ["SF", "F", "UT", "BE", "IR"], {7, 8, 9, 10, 11}
    weak.per_game = {k: v * 0.35 for k, v in STRONG.items()}
    weak.per_game.update({"FG%": 0.42, "FT%": 0.7, "FGM": 0.42 * weak.per_game["FGA"], "FTM": 0.7 * weak.per_game["FTA"]})
    stash = make_player(701, random.Random(6))
    stash.name, stash.game_days = "Stash Star", set(range(12, 60))
    stash.per_game = {**STRONG, "FG%": STRONG["FGM"] / STRONG["FGA"], "FT%": STRONG["FTM"] / STRONG["FTA"]}
    data._fas += [weak, stash]
    engine = Engine(data)
    rows = {r["player"].name: r for r in engine.free_agent_board}

    assert rows["Stash Star"]["outlook"] == "stash"
    assert engine.fa_row(rows["Stash Star"])["why"][0].startswith("Stash")
    assert rows["SF Scrub"]["outlook"] == "streamer"
    assert any(n.startswith("Streamer") for n in rows["SF Scrub"]["result"].notes)
    assert rows["SF Later"]["outlook"] == "both"
    # the long-term list ranks by rest-of-season value, so the stash beats the scrub
    season = [r["player"].name for r in engine.top_season_adds(10)]
    assert season.index("Stash Star") < season.index("SF Scrub")


def test_injured_free_agents_do_not_set_replacement_level():
    data = FakeData()
    for i, fa in enumerate(data._fas[:6]):  # six free agents better than anyone, all out
        fa.per_game = {**STRONG, "FG%": STRONG["FGM"] / STRONG["FGA"], "FT%": STRONG["FTM"] / STRONG["FTA"]}
        fa.injury_status = "OUT" if i % 2 else "INJURY_RESERVE"
    healthy = data._fas[6:]
    engine = Engine(data)
    assert engine.replacement_level == pytest.approx(
        sorted((engine.value(p) for p in healthy), reverse=True)[4])
    assert engine.replacement_level < engine.value(data._fas[0])


def test_trade_ros_change_counts_roster_spots():
    engine = Engine(FakeData())
    mine, theirs = engine.data.teams[1].roster, engine.data.teams[2].roster
    r = engine.replacement_level
    give, get = mine[:2], theirs[:1]
    raw = engine.ros_value(get[0]) - engine.ros_value(give[0]) - engine.ros_value(give[1])
    two_for_one = engine.evaluate_trade(give, get)["rest_of_season_value_change"]
    assert two_for_one == pytest.approx(raw + r, abs=0.011)  # the freed spot is refilled at replacement level
    one_for_one = engine.evaluate_trade(give[:1], get)["rest_of_season_value_change"]
    assert one_for_one == pytest.approx(engine.ros_value(get[0]) - engine.ros_value(give[0]), abs=0.011)
