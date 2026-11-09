"""Pure analysis: player valuation, lineup-aware matchup projection, move simulation.

Nothing here talks to ESPN; it only needs a `LeagueView` (LeagueData satisfies it),
which keeps the math testable offline.
"""
from __future__ import annotations

import datetime as dt
import math
import statistics
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from .espn import Category, PlayerInfo, TeamInfo

# Ratio categories and the (numerator, denominator) stats they are built from.
RATIO_CATS = {
    "FG%": ("FGM", "FGA"),
    "FT%": ("FTM", "FTA"),
    "3PT%": ("3PM", "3PA"),
    "AFG%": ("FGM", "FGA"),
    "A/TO": ("AST", "TO"),
}
# Single-game coefficient of variation per stat, used for matchup win probabilities.
GAME_CV = {
    "PTS": 0.35, "REB": 0.40, "OREB": 0.7, "DREB": 0.45, "AST": 0.45, "STL": 0.85, "BLK": 0.95,
    "3PM": 0.65, "TO": 0.55, "FGM": 0.35, "FTM": 0.55, "DD": 1.2, "TD": 3.0, "MIN": 0.2, "FPTS": 0.30,
}
DEFAULT_CV = 0.6
# Uncertainty in a player's true per-game average (role changes, small samples). Applied to
# each player's whole-matchup total, since it doesn't average out across their games.
MEAN_UNCERTAINTY = 0.15


class LeagueView(Protocol):
    categories: list[Category]
    lineup_slots: list[str]
    is_points: bool

    def sp_date(self, sp: int) -> dt.date | None: ...


def stat(p: PlayerInfo, name: str) -> float:
    return float(p.per_game.get(name, 0.0) or 0.0)


# ---------------------------------------------------------------- valuation

class Valuer:
    """Per-game z-scores against a reference pool (by default every rostered player).

    Ratio categories use impact z-scores: (player% - pool%) * attempts, so a
    high-volume shooter moves FG% more than a low-volume one.
    """

    def __init__(self, pool: Iterable[PlayerInfo], categories: list[Category], punts: frozenset[str] = frozenset()):
        self.categories = categories
        self.punts = punts
        pool = [p for p in pool if p.per_game]
        self._params: dict[str, tuple[float, float, float]] = {}
        for cat in categories:
            if cat.stat in RATIO_CATS:
                num, den = RATIO_CATS[cat.stat]
                total_den = sum(stat(p, den) for p in pool)
                rate = sum(stat(p, num) for p in pool) / total_den if total_den else 0.0
                values = [self._ratio_impact(p, num, den, rate) for p in pool]
            else:
                rate = 0.0
                values = [stat(p, cat.stat) for p in pool]
            mean = statistics.fmean(values) if values else 0.0
            sd = statistics.pstdev(values) if len(values) > 1 else 1.0
            self._params[cat.stat] = (mean, sd or 1.0, rate)

    @staticmethod
    def _ratio_impact(p: PlayerInfo, num: str, den: str, rate: float) -> float:
        if num == "AST":  # A/TO: assists above what the pool ratio implies for his turnovers
            return stat(p, "AST") - rate * stat(p, "TO")
        return stat(p, num) - rate * stat(p, den)

    def z(self, p: PlayerInfo) -> dict[str, float]:
        out = {}
        for cat in self.categories:
            mean, sd, rate = self._params[cat.stat]
            if cat.stat in RATIO_CATS:
                num, den = RATIO_CATS[cat.stat]
                raw = self._ratio_impact(p, num, den, rate)
            else:
                raw = stat(p, cat.stat)
            z = (raw - mean) / sd
            out[cat.stat] = round(-z if cat.reverse else z, 2)
        return out

    def total(self, p: PlayerInfo, weights: dict[str, float] | None = None) -> float:
        zs = self.z(p)
        return round(sum(
            v * (weights.get(k, 1.0) if weights else 1.0)
            for k, v in zs.items() if k not in self.punts
        ), 2)


# ---------------------------------------------------------------- lineups

def daily_starters(roster: list[PlayerInfo], sp: int, slots: list[str], rank: dict[int, float],
                   day: dt.date | None = None) -> list[PlayerInfo]:
    """Best legal lineup for one day: max-cardinality slot matching, filled in value order.

    Players are inserted highest-value first using augmenting paths, so a higher-value
    player is never displaced by a lower-value one and positional eligibility is respected.
    """
    return [p for p in _assign_slots(roster, sp, slots, rank, day) if p is not None]


def _assign_slots(roster: list[PlayerInfo], sp: int, slots: list[str], rank: dict[int, float],
                  day: dt.date | None) -> list[PlayerInfo | None]:
    """daily_starters' matching, one entry per slot (None = nobody can fill it that day)."""
    playing = [p for p in roster if sp in p.game_days and not p.is_injured_reserve and p.availability(day) > 0]
    playing.sort(key=lambda p: rank.get(p.id, 0.0), reverse=True)
    slot_owner: list[PlayerInfo | None] = [None] * len(slots)

    def place(p: PlayerInfo, seen: set[int]) -> bool:
        for i, slot in enumerate(slots):
            if i in seen or not p.can_fill(slot):
                continue
            seen.add(i)
            if slot_owner[i] is None or place(slot_owner[i], seen):
                slot_owner[i] = p
                return True
        return False

    for p in playing:
        place(p, set())
    return slot_owner


@dataclass
class DayPlan:
    sp: int
    date: dt.date | None
    playing: int  # roster players with a game
    started: list[str]  # names who fill a starting slot
    benched: list[str]  # have a game but no open slot
    open_slots: int
    open_slot_names: list[str] = field(default_factory=list)  # starting slots nobody can fill


def plan_days(roster: list[PlayerInfo], sps: list[int], view: LeagueView, rank: dict[int, float],
              day_rosters: dict[int, list[PlayerInfo]] | None = None) -> list[DayPlan]:
    plans = []
    for sp in sps:
        day = view.sp_date(sp)
        on_day = day_rosters.get(sp, roster) if day_rosters else roster
        owners = _assign_slots(on_day, sp, view.lineup_slots, rank, day)
        starters = [p for p in owners if p is not None]
        playing = [p for p in on_day if sp in p.game_days and not p.is_injured_reserve and p.availability(day) > 0]
        started_ids = {p.id for p in starters}
        plans.append(DayPlan(
            sp=sp,
            date=day,
            playing=len(playing),
            started=[p.name for p in starters],
            benched=[p.name for p in playing if p.id not in started_ids],
            open_slots=len(view.lineup_slots) - len(starters),
            open_slot_names=[slot for slot, p in zip(view.lineup_slots, owners, strict=True) if p is None],
        ))
    return plans


# ---------------------------------------------------------------- matchup projection

@dataclass
class SideProjection:
    final: dict[str, float]
    sd: dict[str, float]
    remaining_games: float
    games_by_player: dict[str, float]  # expected starts remaining, by player name
    days: list[DayPlan]


def _expected_contributions(roster, sps, view, rank, day_rosters=None):
    """Sum expected per-stat production over the given days, starters only, weighted by availability.

    `day_rosters` overrides the roster on specific days (moves made partway through the matchup).
    """
    sums: dict[str, float] = {}
    sq: dict[str, float] = {}
    games = 0.0
    by_player: dict[str, float] = {}
    player_games: dict[int, tuple[PlayerInfo, float]] = {}
    for sp in sps:
        day = view.sp_date(sp)
        on_day = day_rosters.get(sp, roster) if day_rosters else roster
        for p in daily_starters(on_day, sp, view.lineup_slots, rank, day):
            a = p.availability(day)
            if a <= 0:
                continue
            games += a
            by_player[p.name] = by_player.get(p.name, 0.0) + a
            player_games[p.id] = (p, player_games.get(p.id, (p, 0.0))[1] + a)
            for k, v in p.per_game.items():
                v = float(v or 0)
                sums[k] = sums.get(k, 0.0) + a * v
                cv = GAME_CV.get(k, DEFAULT_CV)
                # variance of a game that may not happen: a*sd^2 + a(1-a)*mean^2
                sq[k] = sq.get(k, 0.0) + a * (cv * v) ** 2 + a * (1 - a) * v * v
    for p, g in player_games.values():
        for k, v in p.per_game.items():
            sq[k] = sq.get(k, 0.0) + (MEAN_UNCERTAINTY * g * float(v or 0)) ** 2
    return sums, sq, games, by_player


def project_side(roster: list[PlayerInfo], current: dict[str, float], elapsed: list[int],
                 remaining: list[int], view: LeagueView, rank: dict[int, float],
                 day_rosters: dict[int, list[PlayerInfo]] | None = None) -> SideProjection:
    add, var, games, by_player = _expected_contributions(roster, remaining, view, rank, day_rosters)
    final: dict[str, float] = {}
    sd: dict[str, float] = {}
    past = None

    for cat in view.categories:
        c = cat.stat
        if c in RATIO_CATS:
            num, den = RATIO_CATS[c]
            if num in current and den in current:  # ESPN gave us makes/attempts directly
                cur_num, cur_den = current[num], current[den]
            else:  # estimate the attempts already taken from the elapsed days
                if past is None:
                    past = _expected_contributions(roster, elapsed, view, rank)[0]
                cur_den = past.get(den, 0.0)
                cur_num = current.get(c, 0.0) * cur_den
            tot_num, tot_den = cur_num + add.get(num, 0.0), cur_den + add.get(den, 0.0)
            pct = tot_num / tot_den if tot_den else current.get(c, 0.0)
            final[c] = pct
            rem_den = add.get(den, 0.0)
            if c == "A/TO":
                sd[c] = 0.25 * pct * math.sqrt(rem_den / tot_den) if tot_den else 0.0
            else:
                # binomial noise on the remaining attempts, inflated for shot-quality variance
                sd[c] = math.sqrt(max(pct * (1 - pct), 0.0) * rem_den * 1.3) / tot_den if tot_den else 0.0
        else:
            final[c] = current.get(c, 0.0) + add.get(c, 0.0)
            sd[c] = math.sqrt(var.get(c, 0.0))

    days = plan_days(roster, remaining, view, rank, day_rosters)
    return SideProjection(final=final, sd=sd, remaining_games=games, games_by_player=by_player, days=days)


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


@dataclass
class CategoryOutlook:
    stat: str
    mine_now: float
    theirs_now: float
    mine_final: float
    theirs_final: float
    win_prob: float


@dataclass
class MatchupProjection:
    opponent: TeamInfo | None
    categories: list[CategoryOutlook]
    mine: SideProjection
    theirs: SideProjection | None
    elapsed: list[int]
    remaining: list[int]

    @property
    def expected_wins(self) -> float:
        return sum(c.win_prob for c in self.categories)

    @property
    def win_matchup_prob(self) -> float:
        """P(winning more categories than losing), via the Poisson-binomial distribution."""
        probs = [c.win_prob for c in self.categories]
        dist = [1.0]
        for p in probs:
            nxt = [0.0] * (len(dist) + 1)
            for k, q in enumerate(dist):
                nxt[k] += q * (1 - p)
                nxt[k + 1] += q * p
            dist = nxt
        n = len(probs)
        if n == 1:
            return probs[0]
        return sum(q for k, q in enumerate(dist) if k > n - k) + 0.5 * sum(q for k, q in enumerate(dist) if k == n - k)


def win_prob(cat: Category, mine: float, theirs: float, sd_m: float, sd_t: float) -> float:
    diff = (theirs - mine) if cat.reverse else (mine - theirs)
    sd = math.sqrt(sd_m ** 2 + sd_t ** 2)
    if sd < 1e-9:
        return 1.0 if diff > 0 else 0.0 if diff < 0 else 0.5
    return _phi(diff / sd)


def project_matchup(view: LeagueView, my_roster: list[PlayerInfo], opponent: TeamInfo | None,
                    mine_now: dict[str, float], theirs_now: dict[str, float],
                    elapsed: list[int], remaining: list[int], rank: dict[int, float],
                    day_rosters: dict[int, list[PlayerInfo]] | None = None) -> MatchupProjection:
    mine = project_side(my_roster, mine_now, elapsed, remaining, view, rank, day_rosters)
    theirs = project_side(opponent.roster, theirs_now, elapsed, remaining, view, rank) if opponent else None
    return _combine(view, opponent, mine, theirs, mine_now, theirs_now, elapsed, remaining)


def _combine(view: LeagueView, opponent: TeamInfo | None, mine: SideProjection, theirs: SideProjection | None,
             mine_now: dict[str, float], theirs_now: dict[str, float],
             elapsed: list[int], remaining: list[int]) -> MatchupProjection:
    outlooks = []
    for cat in view.categories:
        c = cat.stat
        t_final = theirs.final[c] if theirs else 0.0
        t_sd = theirs.sd[c] if theirs else 0.0
        outlooks.append(CategoryOutlook(
            stat=c,
            mine_now=mine_now.get(c, 0.0),
            theirs_now=theirs_now.get(c, 0.0),
            mine_final=mine.final[c],
            theirs_final=t_final,
            win_prob=win_prob(cat, mine.final[c], t_final, mine.sd[c], t_sd) if theirs else 0.5,
        ))
    return MatchupProjection(opponent, outlooks, mine, theirs, elapsed, remaining)


# ---------------------------------------------------------------- moves

@dataclass
class MoveResult:
    add: list[str]
    drop: list[str]
    expected_wins_before: float
    expected_wins_after: float
    win_prob_before: float
    win_prob_after: float
    category_deltas: dict[str, float]  # change in category win probability
    games_delta: float
    season_value_delta: float
    projected_delta: dict[str, float]  # change in my projected final total per category
    notes: list[str] = field(default_factory=list)

    @property
    def gain(self) -> float:
        return self.expected_wins_after - self.expected_wins_before


def apply_moves(roster: list[PlayerInfo], add: list[PlayerInfo], drop: list[PlayerInfo]) -> list[PlayerInfo]:
    drop_ids = {p.id for p in drop}
    new = [p for p in roster if p.id not in drop_ids]
    for p in add:
        # newly added players land on the bench; daily_starters ignores lineup_slot except IR
        new.append(PlayerInfo(**{**p.__dict__, "lineup_slot": "BE"}))
    return new


@dataclass
class ScheduledMove:
    """An add/drop made on scoring period `sp`: the roster changes from that day on."""
    sp: int
    add: list[PlayerInfo]
    drop: list[PlayerInfo]


def rosters_by_day(roster: list[PlayerInfo], moves: list[ScheduledMove], sps: list[int]) -> dict[int, list[PlayerInfo]]:
    """The roster on each day once every move dated on or before it is made (moves in date order)."""
    out = {}
    for sp in sps:
        on_day = roster
        for m in moves:
            if m.sp <= sp:
                on_day = apply_moves(on_day, m.add, m.drop)
        out[sp] = on_day
    return out


def _reproject(view: LeagueView, base: MatchupProjection, roster: list[PlayerInfo], mine_now: dict[str, float],
               rank: dict[int, float], day_rosters: dict[int, list[PlayerInfo]] | None = None) -> MatchupProjection:
    """Re-project my side only; the opponent's projection doesn't change with my moves."""
    mine = project_side(roster, mine_now, base.elapsed, base.remaining, view, rank, day_rosters)
    return _combine(view, base.opponent, mine, base.theirs, mine_now,
                    {c.stat: c.theirs_now for c in base.categories}, base.elapsed, base.remaining)


def matchup_gain(view: LeagueView, before: MatchupProjection, after: MatchupProjection) -> float:
    """Points leagues: projected fantasy points added. Category leagues: expected categories added."""
    if view.is_points:
        return after.mine.final.get("FPTS", 0.0) - before.mine.final.get("FPTS", 0.0)
    return after.expected_wins - before.expected_wins


def simulate(view: LeagueView, base: MatchupProjection, roster: list[PlayerInfo], add: list[PlayerInfo],
             drop: list[PlayerInfo], mine_now: dict[str, float], valuer: Valuer,
             rank: dict[int, float], roster_size: int, on_sp: int | None = None) -> MoveResult:
    """Re-project the matchup after a move made now, or on scoring period `on_sp`.

    A move dated `on_sp` leaves the earlier days alone: dropped players keep the games before it
    and added players only count from that day on.
    """
    new_roster = apply_moves(roster, add, drop)
    notes = []
    active = [p for p in new_roster if not p.is_injured_reserve]
    if len(active) > roster_size:
        notes.append(f"Roster would have {len(active)} active players but only {roster_size} spots: drop someone.")
    days = {sp for sp in base.remaining if on_sp is None or sp >= on_sp}
    for p in add:
        if not p.game_days & days:
            notes.append(f"{p.name} has no games left in this matchup.")
    new_rank = {**rank, **{p.id: valuer.total(p) for p in add}}
    if on_sp is None:
        after = _reproject(view, base, new_roster, mine_now, new_rank)
    else:
        schedule = [ScheduledMove(on_sp, add, drop)]
        after = _reproject(view, base, roster, mine_now, new_rank, rosters_by_day(roster, schedule, base.remaining))
    return _move_result(base, after, add, drop, valuer, notes)


def _move_result(base: MatchupProjection, after: MatchupProjection, add: list[PlayerInfo], drop: list[PlayerInfo],
                 valuer: Valuer, notes: list[str]) -> MoveResult:
    return MoveResult(
        add=[p.name for p in add],
        drop=[p.name for p in drop],
        expected_wins_before=round(base.expected_wins, 2),
        expected_wins_after=round(after.expected_wins, 2),
        win_prob_before=round(base.win_matchup_prob, 3),
        win_prob_after=round(after.win_matchup_prob, 3),
        category_deltas={a.stat: round(a.win_prob - b.win_prob, 3) for a, b in zip(after.categories, base.categories, strict=True)},
        games_delta=round(after.mine.remaining_games - base.mine.remaining_games, 2),
        season_value_delta=round(sum(valuer.total(p) for p in add) - sum(valuer.total(p) for p in drop), 2),
        projected_delta={c: round(after.mine.final[c] - base.mine.final[c], 3) for c in after.mine.final},
        notes=notes,
    )


# ---------------------------------------------------------------- day-by-day move plan

@dataclass
class PlannedMove:
    sp: int
    date: dt.date | None
    add: PlayerInfo
    drop: PlayerInfo | None  # None: goes into an open roster spot
    gain: float  # matchup gain of this move on top of the earlier moves in the plan
    result: MoveResult  # same, relative to the roster after the earlier moves
    fills: list[str]  # starting slots that would otherwise sit empty that day


@dataclass
class MovePlan:
    moves: list[PlannedMove]
    before: MatchupProjection
    after: MatchupProjection  # with every move in the plan made
    adds_left: int | None  # None: no weekly limit configured
    capped: bool = False  # the weekly limit cut moves that would have helped
    notes: list[str] = field(default_factory=list)

    @property
    def gain(self) -> float:
        return sum(m.gain for m in self.moves)


def _day_label(day: dt.date | None) -> str:
    return f"{day:%a %m/%d}" if day else "that day"


def plan_moves(view: LeagueView, base: MatchupProjection, roster: list[PlayerInfo], free_agents: list[PlayerInfo],
               mine_now: dict[str, float], valuer: Valuer, rank: dict[int, float], roster_size: int,
               move_days: list[int], adds_left: int | None = None, min_gain: float = 0.0,
               drop_pool: int = 3, season_weight: float = 0.05) -> MovePlan:
    """Dated add/drop plan for the rest of the matchup.

    Walks `move_days` in order. Each day it picks the best add among free agents who play that day
    (into an open roster spot, else for one of the `drop_pool` weakest players or a streamer added
    earlier in the plan), makes it, and searches again on the updated roster before moving on. A
    streamer dropped later still counts for the games in between. Moves are scored on matchup gain
    plus a small season-value term, as in Engine.best_drop_for.

    With `adds_left` set and binding, it keeps the plan of at most that many adds that captures at
    least 90% of the best capped gain with the fewest adds.
    """
    rank = {**rank, **{p.id: valuer.total(p) for p in free_agents if p.id not in rank}}

    def search(threshold: float, limit: int | None) -> tuple[list[PlannedMove], MatchupProjection]:
        return _greedy_plan(view, base, roster, free_agents, mine_now, valuer, rank, roster_size, move_days,
                            threshold, limit, drop_pool, season_weight)

    moves, after = search(min_gain, None)
    if adds_left is None or len(moves) <= adds_left:
        return MovePlan(moves, base, after, adds_left)

    full_gain = sum(m.gain for m in moves)
    options = [search(min_gain, adds_left)]  # first come, first served
    if adds_left > 0:  # or only take moves at least as big as the k-th biggest one
        for t in sorted({m.gain for m in moves}, reverse=True)[:adds_left + 2]:
            options.append(search(max(min_gain, t - 1e-9), adds_left))
    best = max(sum(m.gain for m in o[0]) for o in options)
    good = [o for o in options if sum(m.gain for m in o[0]) >= 0.9 * best - 1e-9]
    capped_moves, capped_after = min(good, key=lambda o: (len(o[0]), -sum(m.gain for m in o[0])))
    capped_gain = sum(m.gain for m in capped_moves)
    note = (f"Weekly add limit: {adds_left} add{'s' if adds_left != 1 else ''} left. The uncapped plan uses "
            f"{len(moves)} adds for {full_gain:+.2f}; this plan uses {len(capped_moves)} for {capped_gain:+.2f}.")
    return MovePlan(capped_moves, base, capped_after, adds_left, capped=True, notes=[note])


def _greedy_plan(view, base, roster, free_agents, mine_now, valuer, rank, roster_size, move_days,
                 min_gain, limit, drop_pool, season_weight) -> tuple[list[PlannedMove], MatchupProjection]:
    schedule: list[ScheduledMove] = []
    planned: list[PlannedMove] = []
    current = base
    taken = {p.id for p in roster}
    streamers: set[int] = set()  # added earlier in this plan
    for sp in move_days:
        day = view.sp_date(sp)
        later = {d for d in base.remaining if d >= sp}
        while limit is None or len(planned) < limit:
            active = [p for p in rosters_by_day(roster, schedule, [sp])[sp] if not p.is_injured_reserve]
            if len(active) < roster_size:
                drops: list[PlayerInfo | None] = [None]
            else:
                drops = sorted(active, key=lambda p: rank.get(p.id, 0.0))[:drop_pool]
                drops += [p for p in active if p.id in streamers and all(p.id != d.id for d in drops)]
            best = None
            for fa in free_agents:
                if fa.id in taken or sp not in fa.game_days or fa.availability(day) <= 0:
                    continue
                for drop in drops:
                    trial = [*schedule, ScheduledMove(sp, [fa], [drop] if drop else [])]
                    after = _reproject(view, base, roster, mine_now, rank, rosters_by_day(roster, trial, base.remaining))
                    gain = matchup_gain(view, current, after)
                    score = gain + season_weight * (rank[fa.id] - (rank.get(drop.id, 0.0) if drop else 0.0))
                    if gain > min_gain and (best is None or score > best[0]):
                        best = (score, gain, fa, drop, after, trial)
            if best is None:
                break
            _, gain, fa, drop, after, schedule = best

            was = next(d for d in current.mine.days if d.sp == sp)
            now = next(d for d in after.mine.days if d.sp == sp)
            fills = list((Counter(was.open_slot_names) - Counter(now.open_slot_names)).elements())
            notes = []
            if drop is None:
                notes.append("Uses an open roster spot: no drop needed.")
            if fills:
                notes.append(f"Fills the empty {'/'.join(fills)} slot on {_day_label(day)}.")
            if drop is not None:
                left = len(drop.game_days & later)
                if drop.id in streamers:
                    notes.append(f"{drop.name} was streamed in earlier in this plan; those games still count.")
                if not left:
                    notes.append(f"{drop.name} has no games left this matchup.")
                else:
                    when = "plays that day" if sp in drop.game_days else "has no game that day"
                    notes.append(f"{drop.name} {when}. Losing {left} remaining game{'s' if left != 1 else ''} "
                                 "is already counted in the gain.")
            planned.append(PlannedMove(sp, day, fa, drop, gain,
                                       _move_result(current, after, [fa], [drop] if drop else [], valuer, notes),
                                       fills))
            current = after
            taken.add(fa.id)
            streamers.add(fa.id)
    return planned, current


def category_weights(proj: MatchupProjection, punts: frozenset[str]) -> dict[str, float]:
    """How much each category matters right now: swing categories (near 50%) weigh most."""
    return {
        c.stat: 0.0 if c.stat in punts else round(0.25 + 3.0 * c.win_prob * (1 - c.win_prob), 3)
        for c in proj.categories
    }
