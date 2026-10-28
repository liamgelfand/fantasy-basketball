"""ESPN data layer: wraps espn_api and normalizes everything into plain dataclasses.

Everything downstream (analysis, report, agent) works on PlayerInfo / TeamInfo,
never on espn_api objects, so the analysis can be tested without network access.
"""
from __future__ import annotations

import datetime as dt
import difflib
from dataclasses import dataclass, field
from functools import cached_property

from espn_api.basketball import League
from espn_api.basketball.constant import POSITION_MAP, PRO_TEAM_MAP, STATS_MAP

from .config import Config

PRO_TEAM_ID = {abbr: tid for tid, abbr in PRO_TEAM_MAP.items() if isinstance(tid, int)}
NON_STARTING_SLOTS = {"BE", "IR"}

# Chance a player suits up given his ESPN injury designation.
AVAILABILITY = {
    "OUT": 0.0,
    "INJURY_RESERVE": 0.0,
    "SUSPENSION": 0.0,
    "DOUBTFUL": 0.25,
    "QUESTIONABLE": 0.6,
    "DAY_TO_DAY": 0.7,
}

WINDOW_KEYS = {
    "season": "total",
    "last_30": "last_30",
    "last_15": "last_15",
    "last_7": "last_7",
    "projected": "projected",
}
# Season stats are trusted more as games accumulate; below this many games they
# are blended with ESPN's projection (weight = gp / (gp + BLEND_GAMES)).
BLEND_GAMES = 10


@dataclass
class PlayerInfo:
    id: int
    name: str
    pro_team: str
    position: str
    eligible_slots: list[str]
    lineup_slot: str
    injury_status: str
    expected_return: dt.date | None
    per_game: dict[str, float]  # per-game stats for the configured window, plus "FPTS"
    gp: float
    window: str
    windows: dict[str, dict[str, float]] = field(default_factory=dict)  # every window, for display
    game_days: set[int] = field(default_factory=set)  # scoring periods with a game
    on_waivers: bool = False

    def availability(self, day: dt.date | None) -> float:
        if self.expected_return and day and day >= self.expected_return:
            return 1.0
        return AVAILABILITY.get((self.injury_status or "ACTIVE").upper(), 1.0)

    def can_fill(self, slot: str) -> bool:
        return slot in self.eligible_slots

    @property
    def is_injured_reserve(self) -> bool:
        return self.lineup_slot == "IR"


@dataclass
class TeamInfo:
    id: int
    name: str
    abbrev: str
    wins: int
    losses: int
    ties: int
    standing: int
    points_for: float
    acquisitions: int
    owners: list[str]
    roster: list[PlayerInfo]

    @property
    def record(self) -> str:
        return f"{self.wins}-{self.losses}" + (f"-{self.ties}" if self.ties else "")


@dataclass(frozen=True)
class Category:
    stat: str
    reverse: bool = False  # lower is better (e.g. TO)


def _window_stats(player, year: int, window: str) -> tuple[dict[str, float], float, float]:
    """Return (per-game stats, games played, fantasy points per game) for one window."""
    split = player.stats.get(f"{year}_{WINDOW_KEYS[window]}") or {}
    # ESPN occasionally puts non-numeric values in stat maps; keep numbers only.
    avg = {k: float(v) for k, v in (split.get("avg") or {}).items() if isinstance(v, (int, float))}
    total = split.get("total") or {}
    gp = float(total.get("GP") or avg.get("GP") or 0)
    if window == "projected" and not gp:
        gp = float(total.get("GP", 0))
    return avg, gp, float(split.get("applied_avg") or 0)


def _blend(season: dict, season_gp: float, projected: dict) -> dict[str, float]:
    if not projected:
        return season
    if not season or not season_gp:
        return projected
    w = season_gp / (season_gp + BLEND_GAMES)
    keys = set(season) | set(projected)
    return {k: w * season.get(k, 0.0) + (1 - w) * projected.get(k, 0.0) for k in keys}


class LeagueData:
    """One snapshot of the league. Construct once per run; all methods read the cached snapshot."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.year = cfg.year
        self.league = League(league_id=cfg.league_id, year=cfg.year, espn_s2=cfg.espn_s2, swid=cfg.swid)
        self.settings_raw = self.league.espn_request.league_get(params={"view": "mSettings"})["settings"]
        self.today_sp: int = self.league.scoringPeriodId
        self.pro_schedule = self.league.pro_schedule
        self.sp_start = self._build_scoring_period_starts()
        self.teams: dict[int, TeamInfo] = {t.team_id: self._team(t) for t in self.league.teams}
        self.my_team_id = self._find_my_team()
        self._fa_cache: list[PlayerInfo] | None = None
        self._player_cache: dict[int, PlayerInfo] = {}

    # ---------- league settings ----------

    @property
    def name(self) -> str:
        return self.league.settings.name

    @property
    def scoring_type(self) -> str:
        return self.league.settings.scoring_type or "H2H_CATEGORY"

    @property
    def is_points(self) -> bool:
        return "POINTS" in self.scoring_type

    @cached_property
    def categories(self) -> list[Category]:
        if self.is_points:
            return [Category("FPTS")]
        items = self.settings_raw.get("scoringSettings", {}).get("scoringItems", [])
        cats = [
            Category(STATS_MAP.get(str(i["statId"]), str(i["statId"])), bool(i.get("isReverseItem")))
            for i in items
        ]
        return cats or [Category(s, s == "TO") for s in ("PTS", "REB", "AST", "STL", "BLK", "3PM", "FG%", "FT%", "TO")]

    @cached_property
    def lineup_slots(self) -> list[str]:
        """Starting slots, one entry per slot (e.g. ['PG','SG','SF','PF','C','G','F','UT','UT','UT'])."""
        counts = self.settings_raw.get("rosterSettings", {}).get("lineupSlotCounts", {})
        slots = []
        for slot_id, n in sorted(counts.items(), key=lambda kv: int(kv[0])):
            name = POSITION_MAP.get(int(slot_id), "")
            if name and name not in NON_STARTING_SLOTS:
                slots.extend([name] * int(n))
        return slots

    @cached_property
    def roster_size(self) -> int:
        """Non-IR roster spots (starters + bench)."""
        counts = self.settings_raw.get("rosterSettings", {}).get("lineupSlotCounts", {})
        return sum(int(n) for k, n in counts.items() if POSITION_MAP.get(int(k)) != "IR")

    @cached_property
    def acquisition_rules(self) -> dict:
        s = self.league.settings
        return {
            "matchup_acquisition_limit": s.matchup_acquisition_limit,
            "season_acquisition_limit": s.acquisition_limit,
            "faab": s.faab,
            "faab_budget": s.acquisition_budget,
            "waiver_process_days": s.waiver_process_days,
        }

    # ---------- calendar ----------

    def _build_scoring_period_starts(self) -> dict[int, dt.datetime]:
        starts: dict[int, dt.datetime] = {}
        for games_by_sp in self.pro_schedule.values():
            for sp, games in games_by_sp.items():
                for g in games:
                    t = dt.datetime.fromtimestamp(g["date"] / 1000.0)
                    if int(sp) not in starts or t < starts[int(sp)]:
                        starts[int(sp)] = t
        return starts

    def sp_date(self, sp: int) -> dt.date | None:
        if sp in self.sp_start:
            return self.sp_start[sp].date()
        if self.today_sp in self.sp_start:  # scoring periods are consecutive days
            return self.sp_start[self.today_sp].date() + dt.timedelta(days=sp - self.today_sp)
        return dt.date.today() + dt.timedelta(days=sp - self.today_sp)

    def today_started(self) -> bool:
        start = self.sp_start.get(self.today_sp)
        return start is None or dt.datetime.now() >= start

    @cached_property
    def matchup_periods(self) -> tuple[list[int], list[int]]:
        """(elapsed scoring periods, remaining scoring periods) of the current matchup.

        Today counts as elapsed once its first game has tipped, because ESPN's
        live matchup totals already include it.
        """
        cur = self.league.currentMatchupPeriod
        known = sorted(int(s) for s in self.league.matchup_ids.get(cur, []))
        configured = [int(x) for x in self.settings_raw.get("scheduleSettings", {}).get("matchupPeriods", {}).get(str(cur), [])]

        if len(configured) > 1 and (not known or set(known) <= set(configured)):
            days = configured  # ESPN listed this matchup's scoring periods explicitly
        else:
            start = known[0] if known else self.today_sp
            end_date = self.cfg.matchup_end_date
            if end_date is None:
                today = self.sp_date(self.today_sp) or dt.date.today()
                end_date = today + dt.timedelta(days=(self.cfg.matchup_end_weekday - today.weekday()) % 7)
            days, sp = [], start
            while (d := self.sp_date(sp)) is not None and d <= end_date and sp <= self.league.finalScoringPeriod:
                days.append(sp)
                sp += 1

        cutoff = self.today_sp + (1 if self.today_started() else 0)
        return [d for d in days if d < cutoff], [d for d in days if d >= cutoff]

    def rest_of_season_periods(self) -> list[int]:
        start = self.today_sp + (1 if self.today_started() else 0)
        return list(range(start, self.league.finalScoringPeriod + 1))

    # ---------- players & teams ----------

    def _game_days(self, pro_team: str) -> set[int]:
        games = self.pro_schedule.get(PRO_TEAM_ID.get(pro_team, -1), {})
        return {int(sp) for sp, g in games.items() if g}

    def to_player(self, p, on_waivers: bool = False) -> PlayerInfo:
        windows: dict[str, dict[str, float]] = {}
        gps: dict[str, float] = {}
        for w in WINDOW_KEYS:
            avg, gp, fpts = _window_stats(p, self.year, w)
            if avg or fpts:
                windows[w] = {**avg, "FPTS": fpts}
                gps[w] = gp
        windows["blend"] = _blend(windows.get("season", {}), gps.get("season", 0), windows.get("projected", {}))

        chosen = self.cfg.stat_window
        per_game = windows.get(chosen) or windows.get("season") or windows.get("projected") or {}
        return PlayerInfo(
            id=p.playerId,
            name=p.name,
            pro_team=p.proTeam,
            position=p.position,
            eligible_slots=list(p.eligibleSlots),
            lineup_slot=getattr(p, "lineupSlot", "") or "",
            injury_status=(p.injuryStatus or "ACTIVE") if isinstance(p.injuryStatus, str) else "ACTIVE",
            expected_return=p.expected_return_date,
            per_game=per_game,
            gp=gps.get("season", 0.0),
            window=chosen if windows.get(chosen) else ("season" if windows.get("season") else "projected"),
            windows=windows,
            game_days=self._game_days(p.proTeam),
            on_waivers=on_waivers,
        )

    def _team(self, t) -> TeamInfo:
        return TeamInfo(
            id=t.team_id,
            name=t.team_name,
            abbrev=t.team_abbrev,
            wins=t.wins,
            losses=t.losses,
            ties=t.ties,
            standing=t.standing,
            points_for=t.points_for,
            acquisitions=t.acquisitions,
            owners=[o.get("id", "") for o in t.owners],
            roster=[self.to_player(p) for p in t.roster],
        )

    def _find_my_team(self) -> int:
        if self.cfg.team_id is not None:
            if self.cfg.team_id not in self.teams:
                raise SystemExit(f"ESPN_TEAM_ID={self.cfg.team_id} is not in this league. Team ids: {sorted(self.teams)}")
            return self.cfg.team_id
        if self.cfg.swid:
            swid = self.cfg.swid.strip("{}").lower()
            for team in self.teams.values():
                if any(o.strip("{}").lower() == swid for o in team.owners):
                    return team.id
        raise SystemExit(
            "Could not tell which team is yours. Set ESPN_TEAM_ID in .env. Teams: "
            + ", ".join(f"{t.id}={t.name}" for t in self.teams.values())
        )

    @property
    def my_team(self) -> TeamInfo:
        return self.teams[self.my_team_id]

    @property
    def rostered_players(self) -> list[PlayerInfo]:
        return [p for t in self.teams.values() for p in t.roster]

    def free_agents(self, size: int | None = None, position: str | None = None) -> list[PlayerInfo]:
        if position is None and size is None and self._fa_cache is not None:
            return self._fa_cache
        raw = self.league.free_agents(size=size or self.cfg.free_agent_pool, position=position)
        players = [self.to_player(p) for p in raw]
        if position is None and size is None:
            self._fa_cache = players
        return players

    def find_team(self, query: str) -> TeamInfo | None:
        q = query.strip().lower()
        for t in self.teams.values():
            if q in (t.name.lower(), t.abbrev.lower(), str(t.id)):
                return t
        names = {t.name.lower(): t for t in self.teams.values()}
        match = difflib.get_close_matches(q, list(names), n=1, cutoff=0.4)
        return names[match[0]] if match else None

    def find_player(self, name: str) -> PlayerInfo | None:
        """Resolve a player by (fuzzy) name: rosters and cached free agents first, then ESPN's player card."""
        known = {p.name.lower(): p for p in self.rostered_players + (self._fa_cache or [])}
        if name.lower() in known:
            return known[name.lower()]
        names = [k for k in self.league.player_map if isinstance(k, str)]
        match = difflib.get_close_matches(name, names, n=1, cutoff=0.6)
        if not match:
            return None
        if match[0].lower() in known:
            return known[match[0].lower()]
        player_id = self.league.player_map[match[0]]
        if player_id not in self._player_cache:
            card = self.league.player_info(playerId=player_id)
            if card is None:
                return None
            self._player_cache[player_id] = self.to_player(card)
        return self._player_cache[player_id]

    def owner_of(self, player: PlayerInfo) -> TeamInfo | None:
        for t in self.teams.values():
            if any(p.id == player.id for p in t.roster):
                return t
        return None

    def player_news(self, player: PlayerInfo, limit: int = 5) -> list[dict]:
        card = self.league.player_info(playerId=player.id, include_news=True)
        news = getattr(card, "news", None) or []
        return [
            {"published": n.get("published", ""), "headline": n.get("headline", ""), "story": (n.get("story") or "")[:600]}
            for n in news[:limit]
        ]

    # ---------- matchup ----------

    @cached_property
    def current_box_score(self):
        for box in self.league.box_scores():
            home = getattr(box.home_team, "team_id", box.home_team)
            away = getattr(box.away_team, "team_id", box.away_team)
            if self.my_team_id in (home, away):
                return box
        return None

    def current_matchup(self) -> tuple[TeamInfo | None, dict[str, float], dict[str, float]]:
        """(opponent, my current stat totals, opponent current stat totals)."""
        box = self.current_box_score
        if box is None:
            return None, {}, {}
        home = getattr(box.home_team, "team_id", box.home_team)
        away = getattr(box.away_team, "team_id", box.away_team)
        mine_home = home == self.my_team_id
        opp_id = away if mine_home else home
        opponent = self.teams.get(opp_id)

        if self.is_points:
            mine = {"FPTS": float(box.home_score if mine_home else box.away_score)}
            theirs = {"FPTS": float(box.away_score if mine_home else box.home_score)}
        else:
            def flat(stats):
                return {k: float(v.get("value", 0) or 0) for k, v in (stats or {}).items()}
            mine = flat(box.home_stats if mine_home else box.away_stats)
            theirs = flat(box.away_stats if mine_home else box.home_stats)
        return opponent, mine, theirs

    def standings(self) -> list[TeamInfo]:
        return sorted(self.teams.values(), key=lambda t: t.standing or 99)

    def recent_activity(self, size: int = 15) -> list[dict]:
        out = []
        for act in self.league.recent_activity(size=size):
            when = dt.datetime.fromtimestamp(act.date / 1000.0).strftime("%Y-%m-%d %H:%M")
            for team, action, player, _pos in act.actions:
                out.append({
                    "date": when,
                    "team": getattr(team, "team_name", str(team)),
                    "action": action,
                    "player": getattr(player, "name", str(player)),
                })
        return out
