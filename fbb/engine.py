"""Ties the ESPN snapshot to the analysis. Report and agent both call into this."""
from __future__ import annotations

from dataclasses import asdict
from functools import cached_property

from .analysis import (
    MatchupProjection,
    MoveResult,
    Valuer,
    category_weights,
    daily_starters,
    project_matchup,
    simulate,
    stat,
)
from .espn import LeagueData, PlayerInfo, TeamInfo

SHOW_STATS_POINTS = ("FPTS", "PTS", "REB", "AST", "STL", "BLK", "3PM", "TO", "MIN")


class Engine:
    def __init__(self, data: LeagueData):
        self.data = data
        self.cfg = data.cfg
        self._position_boards: dict[tuple[str, int], list[dict]] = {}

    # ---------- core pieces ----------

    @cached_property
    def valuer(self) -> Valuer:
        return Valuer(self.data.rostered_players, self.data.categories, self.cfg.punt_categories)

    @cached_property
    def rank(self) -> dict[int, float]:
        players = self.data.rostered_players + self.data.free_agents()
        return {p.id: self.valuer.total(p) for p in players}

    def value(self, p: PlayerInfo) -> float:
        return self.rank.get(p.id) if p.id in self.rank else self.valuer.total(p)

    @cached_property
    def matchup_now(self):
        return self.data.current_matchup()

    @cached_property
    def projection(self) -> MatchupProjection:
        opponent, mine_now, theirs_now = self.matchup_now
        elapsed, remaining = self.data.matchup_periods
        return project_matchup(self.data, self.data.my_team.roster, opponent, mine_now, theirs_now,
                               elapsed, remaining, self.rank)

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

    def simulate(self, add: list[PlayerInfo], drop: list[PlayerInfo]) -> MoveResult:
        return simulate(self.data, self.projection, self.data.my_team.roster, add, drop,
                        self.matchup_now[1], self.valuer, self.rank, self.data.roster_size)

    # ---------- roster decisions ----------

    @cached_property
    def drop_candidates(self) -> list[PlayerInfo]:
        """Healthy-or-not, non-IR players ordered by season value (worst first)."""
        roster = [p for p in self.data.my_team.roster if not p.is_injured_reserve]
        return sorted(roster, key=self.value)

    @property
    def has_open_spot(self) -> bool:
        active = [p for p in self.data.my_team.roster if not p.is_injured_reserve]
        return len(active) < self.data.roster_size

    def best_drop_for(self, add: PlayerInfo, candidates: int = 3) -> tuple[PlayerInfo | None, MoveResult]:
        """Try the weakest few roster players as the drop and keep the swap that helps the matchup most."""
        if self.has_open_spot:
            return None, self.simulate([add], [])
        best = None
        for drop in self.drop_candidates[:candidates]:
            result = self.simulate([add], [drop])
            score = self.matchup_gain(result) + 0.05 * result.season_value_delta
            if best is None or score > best[0]:
                best = (score, drop, result)
        return best[1], best[2]

    def score_free_agent(self, fa: PlayerInfo) -> dict:
        """One free agent scored on this-matchup impact (after the best drop) and season value."""
        worst = self.drop_candidates[0] if self.drop_candidates else None
        drop, result = self.best_drop_for(fa)
        return {
            "player": fa,
            "drop": drop,
            "result": result,
            "value": self.value(fa),
            "value_over_worst": round(self.value(fa) - (self.value(worst) if worst else 0), 2),
            "games_left": self.games_left(fa),
            "weighted_value": self.valuer.total(fa, self.weights),
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
        return sorted(self.free_agent_board, key=lambda r: r["value"], reverse=True)[:n]

    # ---------- daily lineup ----------

    def lineup_check(self) -> dict:
        """Compare today's ESPN lineup to the best legal lineup (only meaningful before tip-off)."""
        sp = self.data.today_sp
        roster = self.data.my_team.roster
        day = self.data.sp_date(sp)
        healthy = [p for p in roster if p.availability(day) > 0]
        best = {p.id for p in daily_starters(healthy, sp, self.data.lineup_slots, self.rank)}
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
            "weighted_value_change_this_matchup": round(
                sum(self.valuer.total(p, self.weights) for p in get) - sum(self.valuer.total(p, self.weights) for p in give), 2),
            "per_game_change": {c: round(per_game_sum(get)[c] - per_game_sum(give)[c], 2) for c in cats},
            "ros_games_change": sum(self.ros_games(p) for p in get) - sum(self.ros_games(p) for p in give),
            "roster_count_after": roster_after,
            "roster_spots": self.data.roster_size,
            "this_matchup": asdict(self.simulate(get, give)) if self.projection.opponent else None,
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
            "z_scores": self.valuer.z(p),
            "games_left_this_matchup": self.games_left(p),
            "games_rest_of_season": self.ros_games(p),
            "season_gp": p.gp,
            "stat_window": p.window,
            "per_game": {k: round(stat(p, k), 3 if "%" in k else 1) for k in self.display_stats()},
        }
        if detail:
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
            "matchup_expected_cat_gain": round(res.gain, 3),
            "matchup_projected_change": res.projected_delta,
            "matchup_win_prob_after": res.win_prob_after,
            "value_over_your_worst_player": r["value_over_worst"],
            "leverage_weighted_value": r["weighted_value"],
        }
