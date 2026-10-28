"""Pure mapping from Engine state to API schemas. No I/O beyond what Engine already caches."""
from __future__ import annotations

import datetime as dt

from ..analysis import MoveResult, stat
from ..config import STAT_WINDOWS
from ..engine import Engine
from ..espn import PlayerInfo, TeamInfo
from . import schemas as s

POSITIONS = ("PG", "SG", "SF", "PF", "C")
HEALTHY = ("ACTIVE", "DAY_TO_DAY", "QUESTIONABLE")


def team_ref(t: TeamInfo) -> s.TeamRef:
    return s.TeamRef(id=t.id, name=t.name, abbrev=t.abbrev, record=t.record, standing=t.standing)


def league_meta(engine: Engine, loaded_at: dt.datetime, chat_enabled: bool) -> s.LeagueMeta:
    d = engine.data
    return s.LeagueMeta(
        name=d.name,
        scoring_type=d.scoring_type,
        is_points=d.is_points,
        categories=[s.CategoryInfo(stat=c.stat, reverse=c.reverse) for c in d.categories],
        lineup_slots=d.lineup_slots,
        roster_size=d.roster_size,
        my_team=team_ref(d.my_team),
        teams=[team_ref(t) for t in d.standings()],
        stat_window=engine.cfg.stat_window,
        stat_windows=list(STAT_WINDOWS),
        punt_categories=sorted(engine.cfg.punt_categories),
        loaded_at=loaded_at,
        chat_enabled=chat_enabled,
        model=engine.cfg.model,
    )


# ---------------------------------------------------------------- matchup

def matchup(engine: Engine) -> s.Matchup:
    d, proj = engine.data, engine.projection
    me = d.my_team
    span = [d.sp_date(sp) for sp in proj.elapsed + proj.remaining]
    theirs = {day.sp: day for day in proj.theirs.days} if proj.theirs else {}

    days = []
    for day in proj.mine.days:
        o = theirs.get(day.sp)
        days.append(s.StartsDay(
            date=day.date, mine_starts=len(day.started), mine_open_slots=day.open_slots, mine_benched=day.benched,
            opp_starts=len(o.started) if o else 0, opp_open_slots=o.open_slots if o else 0,
            opp_benched=o.benched if o else [],
        ))

    points_sd = None
    if d.is_points and proj.theirs:
        points_sd = (proj.mine.sd["FPTS"] ** 2 + proj.theirs.sd["FPTS"] ** 2) ** 0.5

    return s.Matchup(
        opponent=team_ref(proj.opponent) if proj.opponent else None,
        start_date=span[0] if span else None,
        end_date=span[-1] if span else None,
        days_left=len(proj.remaining),
        categories_total=len(proj.categories),
        expected_wins=proj.expected_wins,
        win_prob=proj.win_matchup_prob,
        my_starts_left=proj.mine.remaining_games,
        opp_starts_left=proj.theirs.remaining_games if proj.theirs else 0.0,
        points_margin_sd=points_sd,
        categories=[s.CategoryOutlookOut(stat=c.stat, win_prob=c.win_prob, mine_now=c.mine_now,
                                         theirs_now=c.theirs_now, mine_final=c.mine_final,
                                         theirs_final=c.theirs_final) for c in proj.categories],
        days=days,
        schedule=_schedule(engine, me.roster),
        lineup=_lineup(engine),
    )


def _schedule(engine: Engine, roster: list[PlayerInfo]) -> s.ScheduleGrid:
    plan = engine.projection.mine.days
    started = {day.sp: set(day.started) for day in plan}
    rows = []
    for p in sorted(roster, key=engine.value, reverse=True):
        cells: list[s.CellState | None] = []
        for day in plan:
            if day.sp not in p.game_days:
                cells.append(None)
            elif p.is_injured_reserve or p.availability(day.date) == 0:
                cells.append("out")
            else:
                cells.append("starts" if p.name in started[day.sp] else "bench")
        if any(cells):
            rows.append(s.ScheduleRow(player=p.name, status=p.injury_status, cells=cells))
    return s.ScheduleGrid(days=[day.date for day in plan], rows=rows)


def _lineup(engine: Engine) -> s.LineupAdvice:
    lc = engine.lineup_check()
    return s.LineupAdvice(date=dt.date.fromisoformat(lc["date"]), games_started=lc["games_started"],
                          start=lc["start"], bench=lc["bench"], ir_candidates=lc["ir_candidates"])


# ---------------------------------------------------------------- players

def _player_fields(engine: Engine, p: PlayerInfo) -> dict:
    return dict(
        id=p.id,
        name=p.name,
        pro_team=p.pro_team,
        positions=[x for x in p.eligible_slots if x in POSITIONS],
        lineup_slot=p.lineup_slot or None,
        status=p.injury_status,
        value=engine.value(p),
        games_left=engine.games_left(p),
        ros_games=engine.ros_games(p),
        gp=p.gp,
        minutes=round(stat(p, "MIN"), 1),
        fpts=round(stat(p, "FPTS"), 1),
        stat_window=p.window,
        stats={k: round(stat(p, k), 3 if "%" in k else 1) for k in engine.display_stats()},
    )


def roster(engine: Engine) -> s.Roster:
    me = engine.data.my_team
    return s.Roster(
        team=team_ref(me),
        stats=engine.display_stats(),
        players=[s.PlayerRow(**_player_fields(engine, p)) for p in sorted(me.roster, key=engine.value, reverse=True)],
        weakest=[s.WeakSpot(name=p.name, value=engine.value(p)) for p in engine.drop_candidates[:3]],
    )


def free_agents(engine: Engine, position: str | None, include_injured: bool) -> s.FreeAgentBoard:
    board = engine.free_agents_at(position) if position else engine.free_agent_board
    rows = []
    for r in board:
        p = r["player"]
        if not include_injured and p.injury_status not in HEALTHY:
            continue
        rows.append(s.FreeAgentRow(
            **_player_fields(engine, p),
            matchup_gain=round(engine.matchup_gain(r["result"]), 2),
            win_prob_after=r["result"].win_prob_after,
            best_drop=r["drop"].name if r["drop"] else None,
            low_sample=p.gp < 5 and p.window == "blend",
        ))
    rows.sort(key=lambda r: r.matchup_gain, reverse=True)
    return s.FreeAgentBoard(gain_label="Proj FPTS gain" if engine.data.is_points else "Exp cats gain", rows=rows)


def team_roster(engine: Engine, team: TeamInfo) -> s.TeamRoster:
    return s.TeamRoster(team=team_ref(team), players=[p.name for p in sorted(team.roster, key=engine.value, reverse=True)])


# ---------------------------------------------------------------- moves

def move_result(engine: Engine, res: MoveResult) -> s.MoveResultOut:
    return s.MoveResultOut(
        add=res.add, drop=res.drop,
        expected_wins_before=res.expected_wins_before, expected_wins_after=res.expected_wins_after,
        win_prob_before=res.win_prob_before, win_prob_after=res.win_prob_after,
        matchup_gain=round(engine.matchup_gain(res), 3),
        games_delta=res.games_delta, season_value_delta=res.season_value_delta,
        category_deltas=res.category_deltas, projected_delta=res.projected_delta, notes=res.notes,
    )


def trade(engine: Engine, give: list[PlayerInfo], get: list[PlayerInfo]) -> s.TradeResult:
    result = engine.evaluate_trade(give, get)
    per_game = result["per_game_change"]
    if engine.data.is_points:  # one category (FPTS) says little; show the box-score stats instead
        per_game = {k: round(sum(stat(p, k) for p in get) - sum(stat(p, k) for p in give), 1)
                    for k in engine.display_stats()}

    change = None
    if m := result["this_matchup"]:
        change = (m["projected_delta"].get("FPTS", 0.0) if engine.data.is_points
                  else m["expected_wins_after"] - m["expected_wins_before"])
    return s.TradeResult(
        value_change=result["total_value_change"],
        ros_games_change=result["ros_games_change"],
        matchup_change=round(change, 2) if change is not None else None,
        per_game_change=per_game,
        z_change=result["z_change_by_category"],
        roster_overflow=max(0, result["roster_count_after"] - len(engine.data.my_team.roster)),
    )


# ---------------------------------------------------------------- league

def standings(engine: Engine) -> list[s.Standing]:
    me = engine.data.my_team_id
    return [s.Standing(**team_ref(t).model_dump(), points_for=round(t.points_for, 1), is_me=t.id == me)
            for t in engine.data.standings()]
