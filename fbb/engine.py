"""Ties the ESPN snapshot to the analysis. Report and agent both call into this."""
from __future__ import annotations

from dataclasses import asdict
from functools import cached_property

from .analysis import (
    ASSUMED_OUT_DAYS,
    MatchupProjection,
    MovePlan,
    MoveResult,
    Valuer,
    category_weights,
    daily_starters,
    expected_games,
    plan_moves,
    project_matchup,
    simulate,
    stat,
)
from .espn import AVAILABILITY, LeagueData, PlayerInfo, TeamInfo
from .projection import ROLE_MIN_DELTA

SHOW_STATS_POINTS = ("FPTS", "PTS", "REB", "AST", "STL", "BLK", "3PM", "TO", "MIN")
HEALTHY = ("ACTIVE", "", None)

# ---- horizons
SHORT_DAYS = 14  # "short term": the next two weeks of games
# Replacement level: the long-term value of the REPLACEMENT_RANK-th best free agent. A player who
# can't play is worth what you could pick up instead, so missed games pull value toward it.
REPLACEMENT_RANK = 5
# Add/drop scoring = this matchup's simulated gain + the change in each player's value beyond it
# (Engine.hold_value), in matchup units. Value beyond the matchup counts as NEXT_WEIGHT weeks of
# next-two-weeks value plus ROS_WEIGHT weeks of rest-of-season value. ROS is discounted (the wire
# refills and projections drift) but still outweighs the next two weeks, which overlap this matchup
# and are already simulated game by game. Replaces the old flat 0.05 x season-value term.
NEXT_WEIGHT = 0.25
ROS_WEIGHT = 0.5
# One week of a +1 z-sum player in matchup units: ~0.15 expected categories in a 9-cat league;
# GAMES_PER_WEEK games of one FPTS standard deviation in points leagues.
CAT_WEEK_UNIT = 0.15
GAMES_PER_WEEK = 3.5
# Move labels: a move "helps now" above this matchup gain, and is a long-term upgrade at this much
# rest-of-season value (z).
HELPS_NOW_CATS, HELPS_NOW_POINTS = 0.05, 1.0
LONG_TERM_EDGE = 0.5
# Drop candidates: the DROP_POOL lowest hold values, plus anyone flagged (long injury, shrinking or
# small role) up to DROP_POOL_MAX in all.
DROP_POOL = 4
DROP_POOL_MAX = 7
LOW_MINUTES = 18.0


class Engine:
    def __init__(self, data: LeagueData):
        self.data = data
        self.cfg = data.cfg
        self._position_boards: dict[tuple[str, int], list[dict]] = {}
        self._horizon_cache: dict[tuple[str, int], float] = {}

    # ---------- core pieces ----------

    @cached_property
    def valuer(self) -> Valuer:
        return Valuer(self.data.rostered_players, self.data.categories, self.cfg.punt_categories)

    @cached_property
    def rank(self) -> dict[int, float]:
        """Long-term per-game value (z-sum) by player id."""
        players = self.data.rostered_players + self.data.free_agents()
        return {p.id: self.valuer.total(p) for p in players}

    @cached_property
    def start_rank(self) -> dict[int, float]:
        """Near-term per-game value by player id: who starts in the matchup projection."""
        players = self.data.rostered_players + self.data.free_agents()
        return {p.id: self.valuer.total(p, stats=p.near_term) for p in players}

    def value(self, p: PlayerInfo) -> float:
        """Stable long-term per-game value (z-sum vs rostered players)."""
        return self.rank.get(p.id) if p.id in self.rank else self.valuer.total(p)

    def near_value(self, p: PlayerInfo) -> float:
        return self.start_rank.get(p.id) if p.id in self.start_rank else self.valuer.total(p, stats=p.near_term)

    # ---------- horizons ----------

    @cached_property
    def ros_periods(self) -> list[int]:
        return self.data.rest_of_season_periods()

    @cached_property
    def short_periods(self) -> list[int]:
        return self.ros_periods[:SHORT_DAYS]  # scoring periods are consecutive days

    @cached_property
    def _today(self):
        return self.data.sp_date(self.data.today_sp)

    @cached_property
    def typical_games(self) -> tuple[float, float]:
        """Median scheduled games over (the next two weeks, the rest of the season) among rostered players."""
        def median(sps):
            counts = sorted(len(p.game_days & set(sps)) for p in self.data.rostered_players)
            return max(1.0, float(counts[len(counts) // 2])) if counts else 1.0
        return median(self.short_periods), median(self.ros_periods)

    @cached_property
    def replacement_level(self) -> float:
        """Long-term value of the REPLACEMENT_RANK-th best free agent who can play now: injured free agents
        (OUT, IR, suspended) aren't a usable replacement, so they don't set the level."""
        pool = self.data.free_agents()
        healthy = [p for p in pool if p.availability(None) > 0] or pool
        fas = sorted((self.value(p) for p in healthy), reverse=True)
        if fas:
            return fas[min(REPLACEMENT_RANK, len(fas)) - 1]
        return min(self.rank.values(), default=0.0)

    def expected_games(self, p: PlayerInfo, horizon: str = "ros") -> float:
        """Games `p` should play over the horizon ("short" = next two weeks, "ros"), given injuries."""
        sps = self.short_periods if horizon == "short" else self.ros_periods
        return expected_games(p, sps, self.data, self._today)

    def _horizon_value(self, p: PlayerInfo, horizon: str) -> float:
        key = (horizon, p.id)
        if key not in self._horizon_cache:
            short = horizon == "short"
            per_game = self.near_value(p) if short else self.value(p)
            typical = self.typical_games[0 if short else 1]
            r = self.replacement_level
            self._horizon_cache[key] = round(r + (per_game - r) * self.expected_games(p, horizon) / typical, 2)
        return self._horizon_cache[key]

    def ros_value(self, p: PlayerInfo) -> float:
        """Rest-of-season value: long-term per-game value above replacement, scaled by expected games
        (schedule x injury timeline) relative to a typical player. Out for the season = replacement level."""
        return self._horizon_value(p, "ros")

    def short_value(self, p: PlayerInfo) -> float:
        """Next-two-weeks value: near-term per-game value (current role and form) scaled the same way."""
        return self._horizon_value(p, "short")

    @cached_property
    def week_unit(self) -> float:
        return GAMES_PER_WEEK * self.valuer.sd("FPTS") if self.data.is_points else CAT_WEEK_UNIT

    def hold_value(self, p: PlayerInfo) -> float:
        """Value beyond this matchup, in matchup-gain units: what keeping (or adding) the player is worth."""
        return self.week_unit * (NEXT_WEIGHT * self.short_value(p) + ROS_WEIGHT * self.ros_value(p))

    def helps_now(self, gain: float) -> bool:
        return gain > (HELPS_NOW_POINTS if self.data.is_points else HELPS_NOW_CATS)

    def outlook(self, gain: float, ros_delta: float) -> str | None:
        """"streamer" (helps this matchup only), "stash" (long-term value, little now), "both", or None."""
        now, later = self.helps_now(gain), ros_delta >= LONG_TERM_EDGE
        return "both" if now and later else "streamer" if now else "stash" if later else None

    def availability_note(self, p: PlayerInfo) -> str | None:
        if p.injury_status in HEALTHY:
            return None
        sched = len(p.game_days & set(self.short_periods))
        exp = self.expected_games(p, "short")
        if p.expected_return:
            when = f"expected back {p.expected_return:%b %d}"
        elif AVAILABILITY.get((p.injury_status or "").upper(), 1.0) == 0:
            when = f"no return date, assuming about {ASSUMED_OUT_DAYS} days out"
        else:
            when = "no return date"
        return f"{p.name} is {p.injury_status} ({when}): about {exp:.0f} of {sched} games in the next 2 weeks."

    def drop_flags(self, p: PlayerInfo) -> list[str]:
        """Reasons to consider a roster player as a drop beyond raw value: long absence, small or shrinking role."""
        reasons = []
        sched = len(p.game_days & set(self.short_periods))
        if sched and self.expected_games(p, "short") < 0.5 * sched:
            reasons.append(self.availability_note(p) or f"{p.name} misses most of the next 2 weeks.")
        minutes = float(p.near_term.get("MIN", 0.0) or 0.0)
        if p.minutes_trend <= -ROLE_MIN_DELTA:
            reasons.append(f"{p.name}: {p.projection_note}")
        elif 0 < minutes < LOW_MINUTES:
            reasons.append(f"{p.name} is projected for only {minutes:.0f} minutes a game.")
        return reasons

    def ros_delta(self, add: list[PlayerInfo], drop: list[PlayerInfo]) -> float:
        """Rest-of-season value change of a move or trade. Roster spots count as replacement level: an extra
        player in uses a spot a replacement could fill, an extra player out frees one."""
        out = sum(self.ros_value(p) for p in add) - sum(self.ros_value(p) for p in drop)
        return out - self.replacement_level * (len(add) - len(drop))

    def move_notes(self, add: list[PlayerInfo], drop: list[PlayerInfo], gain: float) -> list[str]:
        """Why a move scores the way it does: horizon, role/minutes, injuries, schedule."""
        ros_delta = self.ros_delta(add, drop)
        notes = []
        tag = self.outlook(gain, ros_delta)
        if tag == "streamer":
            notes.append(f"Streamer: helps this matchup only ({ros_delta:+.1f} rest-of-season value).")
        elif tag == "stash":
            notes.append(f"Stash: long-term value ({ros_delta:+.1f} rest-of-season), low impact this matchup.")
        elif tag == "both":
            notes.append(f"Helps this matchup and long term ({ros_delta:+.1f} rest-of-season value).")
        for p in add + drop:
            if p.minutes_trend:
                notes.append(f"{p.name}: {p.projection_note}")
            if note := self.availability_note(p):
                notes.append(note)
        if len(add) == 1 and len(drop) == 1:
            ga, gd = (len(p.game_days & set(self.short_periods)) for p in (add[0], drop[0]))
            if abs(ga - gd) >= 2:
                notes.append(f"Next 2 weeks: {add[0].name} has {ga} games, {drop[0].name} {gd}.")
        return notes

    @cached_property
    def matchup_now(self):
        return self.data.current_matchup()

    @cached_property
    def projection(self) -> MatchupProjection:
        opponent, mine_now, theirs_now = self.matchup_now
        elapsed, remaining = self.data.matchup_periods
        return project_matchup(self.data, self.data.my_team.roster, opponent, mine_now, theirs_now,
                               elapsed, remaining, self.start_rank)

    @property
    def remaining(self) -> list[int]:
        return self.data.matchup_periods[1]

    @cached_property
    def weights(self) -> dict[str, float]:
        return category_weights(self.projection, self.cfg.punt_categories)

    def games_left(self, p: PlayerInfo) -> int:
        return len(p.game_days & set(self.remaining))

    def ros_games(self, p: PlayerInfo) -> int:
        return len(p.game_days & set(self.data.rest_of_season_periods()))

    @property
    def move_days(self) -> list[int]:
        """Matchup days a move can still use: today only until its first game tips."""
        first = self.data.today_sp + (1 if self.data.today_started() else 0)
        return [sp for sp in self.remaining if sp >= first]

    def first_game_day(self, p: PlayerInfo) -> int | None:
        return next((sp for sp in self.move_days if sp in p.game_days), None)

    def simulate(self, add: list[PlayerInfo], drop: list[PlayerInfo], on_sp: int | None = None,
                 explain: bool = True) -> MoveResult:
        result = simulate(self.data, self.projection, self.data.my_team.roster, add, drop,
                          self.matchup_now[1], self.valuer, self.start_rank, self.data.roster_size, on_sp)
        if explain:
            result.notes += self.move_notes(add, drop, self.matchup_gain(result))
        return result

    # ---------- roster decisions ----------

    @cached_property
    def drop_candidates(self) -> list[PlayerInfo]:
        """Non-IR players, worst first by hold value: long-term and next-two-weeks value with injuries
        and schedule priced in."""
        roster = [p for p in self.data.my_team.roster if not p.is_injured_reserve]
        return sorted(roster, key=self.hold_value)

    @cached_property
    def drop_pool(self) -> list[PlayerInfo]:
        """Drops worth trying: the DROP_POOL weakest plus flagged players (long injury, small or shrinking role)."""
        pool = self.drop_candidates[:DROP_POOL]
        pool += [p for p in self.drop_candidates[DROP_POOL:] if self.drop_flags(p)]
        return pool[:DROP_POOL_MAX]

    @property
    def has_open_spot(self) -> bool:
        active = [p for p in self.data.my_team.roster if not p.is_injured_reserve]
        return len(active) < self.data.roster_size

    def move_score(self, result: MoveResult, add: list[PlayerInfo], drop: list[PlayerInfo]) -> float:
        """Matchup gain plus the change in value beyond this matchup (see NEXT_WEIGHT / ROS_WEIGHT)."""
        return (self.matchup_gain(result) + sum(self.hold_value(p) for p in add)
                - sum(self.hold_value(p) for p in drop))

    def best_drop_for(self, add: PlayerInfo) -> tuple[PlayerInfo | None, MoveResult]:
        """Try each player in drop_pool as the drop and keep the best-scoring swap (move_score).

        The move is timed for the add's first game day, so the dropped player keeps any games before it.
        """
        on_sp = self.first_game_day(add)
        if self.has_open_spot:
            return None, self.simulate([add], [], on_sp)
        best = None
        for drop in self.drop_pool:
            result = self.simulate([add], [drop], on_sp, explain=False)
            score = self.move_score(result, [add], [drop])
            if best is None or score > best[0]:
                best = (score, drop, result)
        _, drop, result = best
        result.notes += self.move_notes([add], [drop], self.matchup_gain(result))
        return drop, result

    def score_free_agent(self, fa: PlayerInfo) -> dict:
        """One free agent scored on this-matchup impact (after the best drop) and on both horizons."""
        worst = self.drop_candidates[0] if self.drop_candidates else None
        drop, result = self.best_drop_for(fa)
        ros_delta = self.ros_delta([fa], [drop] if drop else [])
        return {
            "player": fa,
            "drop": drop,
            "result": result,
            "value": self.value(fa),
            "ros_value": self.ros_value(fa),
            "short_value": self.short_value(fa),
            "value_over_worst": round(self.ros_value(fa) - (self.ros_value(worst) if worst else 0), 2),
            "outlook": self.outlook(self.matchup_gain(result), ros_delta),
            "games_left": self.games_left(fa),
            "weighted_value": self.valuer.total(fa, self.weights, stats=fa.near_term),
            "add_sp": self.first_game_day(fa),
        }

    @cached_property
    def free_agent_board(self) -> list[dict]:
        """Every cached free agent that could play this season, scored."""
        return [self.score_free_agent(fa) for fa in self.data.free_agents()
                if fa.availability(None) > 0 or fa.expected_return]

    def free_agents_at(self, position: str, size: int = 40) -> list[dict]:
        """Score a fresh pull of free agents at one position (beyond the cached top-N pool).

        Cached per (position, size) for the life of this snapshot: each pull is an ESPN request
        plus a simulation per player.
        """
        key = (position, size)
        if key not in self._position_boards:
            self._position_boards[key] = [self.score_free_agent(fa)
                                          for fa in self.data.free_agents(size=size, position=position)]
        return self._position_boards[key]

    def ownership_notes(self, adds: list[PlayerInfo]) -> list[str]:
        """Flag "adds" that are on another fantasy roster: those are trade targets, not pickups."""
        mine = self.data.my_team_id
        taken = [f"{p.name} ({owner.name})" for p in adds
                 if (owner := self.data.owner_of(p)) and owner.id != mine]
        return [f"Already rostered elsewhere (trade target, not a pickup): {', '.join(taken)}"] if taken else []

    def matchup_gain(self, result: MoveResult) -> float:
        """Points leagues: projected fantasy points added. Category leagues: expected categories added."""
        return result.projected_delta.get("FPTS", 0.0) if self.data.is_points else result.gain

    def top_streamers(self, n: int = 10) -> list[dict]:
        rows = [r for r in self.free_agent_board if r["games_left"] > 0]
        return sorted(rows, key=lambda r: self.matchup_gain(r["result"]), reverse=True)[:n]

    def top_season_adds(self, n: int = 10) -> list[dict]:
        """Free agents by rest-of-season value (injury timeline and schedule priced in)."""
        return sorted(self.free_agent_board, key=lambda r: r["ros_value"], reverse=True)[:n]

    @cached_property
    def weekly_adds(self) -> tuple[int | None, int | None, list[str]]:
        """(league add limit per matchup, adds I've used this matchup, notes), read from ESPN once per snapshot.

        The limit is None when the league has none (ESPN reports 0, -1 or nothing); the count is None
        when there's no limit to count against or the activity feed couldn't be read.
        """
        try:
            limit = self.data.acquisition_rules.get("matchup_acquisition_limit")
        except Exception as e:
            return None, None, [f"Couldn't read the weekly add limit from ESPN ({type(e).__name__}), so the plan isn't capped."]
        if not isinstance(limit, int) or limit <= 0:
            return None, None, []
        try:
            used = self.data.adds_used_this_matchup()
        except Exception as e:
            return limit, None, [f"Your league allows {limit} adds per matchup, but this week's adds couldn't be "
                                 f"read from ESPN ({type(e).__name__}), so the plan isn't capped. Check your "
                                 "adds left before making them."]
        notes = []
        if used > self.data.my_team.acquisitions:  # season total from ESPN's transaction counter
            notes.append(f"ESPN's activity feed shows {used} adds this week but only "
                         f"{self.data.my_team.acquisitions} this season; the weekly count may be off.")
        return limit, used, notes

    @property
    def adds_left(self) -> int | None:
        """League add limit per matchup minus adds used this matchup; None when there's no limit or it couldn't be read."""
        limit, used, _ = self.weekly_adds
        if limit is None or used is None:
            return None
        return max(0, limit - used)

    @cached_property
    def move_plan(self) -> MovePlan:
        """Dated add/drop sequence for the rest of the matchup (today first while its games haven't tipped)."""
        proj = self.projection
        if proj.opponent is None:
            return MovePlan([], proj, proj, self.adds_left, notes=["No active matchup to plan for."])
        # No league limit: still keep it to about one add per day left, each worth making.
        max_adds = max(1, len(self.move_days))
        roster, fas = self.data.my_team.roster, self.data.free_agents()
        plan = plan_moves(self.data, proj, roster, fas, self.matchup_now[1], self.valuer, self.start_rank,
                          self.data.roster_size, self.move_days, adds_left=self.adds_left,
                          min_gain=HELPS_NOW_POINTS if self.data.is_points else HELPS_NOW_CATS, max_adds=max_adds,
                          drop_pool=DROP_POOL, hold={p.id: self.hold_value(p) for p in roster + fas},
                          flagged={p.id for p in self.drop_pool[DROP_POOL:]})
        for m in plan.moves:
            m.result.notes += self.move_notes([m.add], [m.drop] if m.drop else [], m.gain)
        if self.data.today_started():
            plan.notes.append("Today's games have tipped, so the plan starts tomorrow.")
        if self.adds_left is None and len(plan.moves) >= max_adds:
            plan.notes.append(f"Showing the best {max_adds} adds (about one per day left); more small "
                              "streaming moves may still help a little.")
        plan.notes.extend(self.weekly_adds[2])
        return plan

    def move_plan_summary(self) -> dict:
        plan = self.move_plan
        today = self.data.today_sp
        limit, used, _ = self.weekly_adds
        return {
            "weekly_add_limit": limit,
            "adds_used_this_week": used,
            "adds_left_this_week": plan.adds_left,
            "capped_by_weekly_limit": plan.capped,
            "matchup_gain_total": round(plan.gain, 3),
            "win_probability_before": round(plan.before.win_matchup_prob, 3),
            "win_probability_after": round(plan.after.win_matchup_prob, 3),
            "moves": [{
                "date": str(m.date), "day": "today" if m.sp == today else "tomorrow" if m.sp == today + 1 else None,
                "add": m.add.name, "drop": m.drop.name if m.drop else None,
                "fills_empty_slots": m.fills, "matchup_gain": round(m.gain, 3),
                "win_prob_after": m.result.win_prob_after, "notes": m.result.notes,
            } for m in plan.moves],
            "notes": plan.notes,
        }

    # ---------- daily lineup ----------

    def lineup_check(self) -> dict:
        """Compare today's ESPN lineup to the best legal lineup (only meaningful before tip-off)."""
        sp = self.data.today_sp
        roster = self.data.my_team.roster
        day = self.data.sp_date(sp)
        healthy = [p for p in roster if p.availability(day) > 0]
        best = {p.id for p in daily_starters(healthy, sp, self.data.lineup_slots, self.start_rank)}
        starting = [p for p in roster if p.lineup_slot not in ("BE", "IR", "")]
        # Only flag swaps that gain a game: bench players in the best lineup, and the idle starters they replace.
        start = [p.name for p in roster if p.id in best and p.lineup_slot in ("BE", "")]
        idle = [f"{p.name} ({'no game' if sp not in p.game_days else p.injury_status})"
                for p in starting if p.id not in best]
        ir_eligible = [p.name for p in roster if p.injury_status in ("OUT", "INJURY_RESERVE") and p.lineup_slot != "IR"]
        return {
            "date": str(day),
            "games_started": self.data.today_started(),
            "start": start,
            "bench": idle[:len(start)] if start else [],
            "starting_but_not_playing": idle,
            "ir_candidates": ir_eligible,
        }

    # ---------- trades ----------

    def evaluate_trade(self, give: list[PlayerInfo], get: list[PlayerInfo]) -> dict:
        cats = [c.stat for c in self.data.categories]
        def per_game_sum(players):
            return {c: round(sum(stat(p, c) for p in players), 2) for c in cats}
        give_z = {c: sum(self.valuer.z(p)[c] for p in give) for c in cats}
        get_z = {c: sum(self.valuer.z(p)[c] for p in get) for c in cats}
        roster_after = len(self.data.my_team.roster) - len(give) + len(get)
        return {
            "give": [self.player_summary(p) for p in give],
            "get": [self.player_summary(p) for p in get],
            "z_change_by_category": {c: round(get_z[c] - give_z[c], 2) for c in cats},
            "total_value_change": round(sum(self.value(p) for p in get) - sum(self.value(p) for p in give), 2),
            "rest_of_season_value_change": round(self.ros_delta(get, give), 2),
            "weighted_value_change_this_matchup": round(
                sum(self.valuer.total(p, self.weights) for p in get) - sum(self.valuer.total(p, self.weights) for p in give), 2),
            "per_game_change": {c: round(per_game_sum(get)[c] - per_game_sum(give)[c], 2) for c in cats},
            "ros_games_change": sum(self.ros_games(p) for p in get) - sum(self.ros_games(p) for p in give),
            "roster_count_after": roster_after,
            "roster_spots": self.data.roster_size,
            "this_matchup": asdict(self.simulate(get, give, explain=False)) if self.projection.opponent else None,
            "punted_categories": sorted(self.cfg.punt_categories),
        }

    # ---------- serialization helpers ----------

    def display_stats(self) -> list[str]:
        if self.data.is_points:
            return list(SHOW_STATS_POINTS)
        return [c.stat for c in self.data.categories]

    def player_summary(self, p: PlayerInfo, detail: bool = False) -> dict:
        owner = self.data.owner_of(p)
        out = {
            "name": p.name,
            "team": p.pro_team,
            "positions": [s for s in p.eligible_slots if s not in ("BE", "IR", "UT", "Rookie")],
            "lineup_slot": p.lineup_slot or None,
            "status": p.injury_status,
            "expected_return": str(p.expected_return) if p.expected_return else None,
            "fantasy_owner": owner.name if owner else "Free agent",
            "value": self.value(p),
            "value_next_2_weeks": self.short_value(p),
            "value_rest_of_season": self.ros_value(p),
            "z_scores": self.valuer.z(p),
            "games_left_this_matchup": self.games_left(p),
            "games_rest_of_season": self.ros_games(p),
            "expected_games_rest_of_season": round(self.expected_games(p), 1),
            "season_gp": p.gp,
            "stat_window": p.window,
            "projection": p.projection_note,
            "per_game": {k: round(stat(p, k), 3 if "%" in k else 1) for k in self.display_stats()},
        }
        if detail:
            out["projection_inputs"] = p.projection_weights
            if p.short_term:
                out["per_game_next_2_weeks"] = {k: round(float(p.near_term.get(k, 0) or 0), 3 if "%" in k else 1)
                                                for k in self.display_stats()}
            out["windows"] = {
                w: {k: round(float(v.get(k, 0) or 0), 3 if "%" in k else 1) for k in self.display_stats() + ["MIN", "GP"]}
                for w, v in p.windows.items() if v
            }
            ahead = set(self.data.rest_of_season_periods())  # excludes today once its games have tipped
            out["upcoming_games"] = [str(self.data.sp_date(sp)) for sp in sorted(p.game_days & ahead)][:10]
        return out

    def team_summary(self, t: TeamInfo) -> dict:
        return {
            "id": t.id, "name": t.name, "abbrev": t.abbrev, "record": t.record, "standing": t.standing,
            "points_for": t.points_for, "acquisitions": t.acquisitions,
            "roster": [self.player_summary(p) for p in sorted(t.roster, key=self.value, reverse=True)],
        }

    def projection_summary(self) -> dict:
        proj = self.projection
        elapsed, remaining = proj.elapsed, proj.remaining
        dates = lambda sps: [str(self.data.sp_date(s)) for s in sps]
        return {
            "opponent": proj.opponent.name if proj.opponent else None,
            "matchup_days_elapsed": dates(elapsed),
            "matchup_days_remaining": dates(remaining),
            "expected_categories_won": round(proj.expected_wins, 2),
            "categories_total": len(proj.categories),
            "matchup_win_probability": round(proj.win_matchup_prob, 3),
            "categories": [
                {"stat": c.stat, "me_now": round(c.mine_now, 3), "opp_now": round(c.theirs_now, 3),
                 "me_projected": round(c.mine_final, 3), "opp_projected": round(c.theirs_final, 3),
                 "win_prob": round(c.win_prob, 3), "leverage_weight": self.weights.get(c.stat)}
                for c in proj.categories
            ],
            "my_remaining_starts": round(proj.mine.remaining_games, 1),
            "opp_remaining_starts": round(proj.theirs.remaining_games, 1) if proj.theirs else None,
            "my_days": [asdict(d) | {"date": str(d.date)} for d in proj.mine.days],
            "opp_days": [{"date": str(d.date), "playing": d.playing, "starts": len(d.started)}
                         for d in (proj.theirs.days if proj.theirs else [])],
        }

    def fa_row(self, r: dict) -> dict:
        res: MoveResult = r["result"]
        return {
            **self.player_summary(r["player"]),
            "suggested_drop": r["drop"].name if r["drop"] else None,
            "add_on": str(self.data.sp_date(r["add_sp"])) if r["add_sp"] is not None else None,
            "matchup_expected_cat_gain": round(res.gain, 3),
            "matchup_projected_change": res.projected_delta,
            "matchup_win_prob_after": res.win_prob_after,
            "value_over_your_worst_player": r["value_over_worst"],
            "outlook": r["outlook"],
            "why": res.notes,
            "leverage_weighted_value": r["weighted_value"],
        }
