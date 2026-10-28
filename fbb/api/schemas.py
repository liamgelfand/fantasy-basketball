"""Response and request models: the HTTP contract the web client is built against."""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field


class TeamRef(BaseModel):
    id: int
    name: str
    abbrev: str
    record: str
    standing: int


class CategoryInfo(BaseModel):
    stat: str
    reverse: bool


class LeagueMeta(BaseModel):
    name: str
    scoring_type: str
    is_points: bool
    categories: list[CategoryInfo]
    lineup_slots: list[str]
    roster_size: int
    my_team: TeamRef
    teams: list[TeamRef]
    stat_window: str
    stat_windows: list[str]
    punt_categories: list[str]
    loaded_at: dt.datetime
    chat_enabled: bool
    model: str


# ---------------------------------------------------------------- matchup

class CategoryOutlookOut(BaseModel):
    stat: str
    win_prob: float
    mine_now: float
    theirs_now: float
    mine_final: float
    theirs_final: float


class StartsDay(BaseModel):
    date: dt.date
    mine_starts: int
    mine_open_slots: int
    mine_benched: list[str]
    opp_starts: int
    opp_open_slots: int
    opp_benched: list[str]


CellState = Literal["starts", "bench", "out"]


class ScheduleRow(BaseModel):
    player_id: int
    player: str
    status: str
    cells: list[CellState | None] = Field(description="One entry per day in ScheduleGrid.days; null = no game")


class ScheduleGrid(BaseModel):
    days: list[dt.date]
    rows: list[ScheduleRow]


class LineupAdvice(BaseModel):
    date: dt.date
    games_started: bool
    start: list[str]
    bench: list[str]
    ir_candidates: list[str]


class Matchup(BaseModel):
    opponent: TeamRef | None
    start_date: dt.date | None
    end_date: dt.date | None
    days_left: int
    categories_total: int
    expected_wins: float
    win_prob: float
    my_starts_left: float
    opp_starts_left: float
    points_margin_sd: float | None = None
    categories: list[CategoryOutlookOut]
    days: list[StartsDay]
    schedule: ScheduleGrid
    lineup: LineupAdvice


# ---------------------------------------------------------------- players

class PlayerRow(BaseModel):
    id: int
    name: str
    pro_team: str
    positions: list[str]
    lineup_slot: str | None
    status: str
    value: float
    games_left: int
    ros_games: int
    gp: float
    minutes: float
    fpts: float
    stat_window: str
    stats: dict[str, float]


class WeakSpot(BaseModel):
    name: str
    value: float


class Roster(BaseModel):
    team: TeamRef
    stats: list[str]
    players: list[PlayerRow]
    weakest: list[WeakSpot]


class FreeAgentRow(PlayerRow):
    matchup_gain: float
    win_prob_after: float
    best_drop: str | None
    low_sample: bool


class FreeAgentBoard(BaseModel):
    gain_label: str
    rows: list[FreeAgentRow]


class NewsItem(BaseModel):
    published: str
    headline: str
    story: str


class PlayerDetail(PlayerRow):
    owner: str | None = Field(description="Fantasy team that rosters the player; null for free agents")
    is_mine: bool
    expected_return: dt.date | None
    windows: dict[str, dict[str, float]] = Field(description="Per-game stats by window (season, last_30, ...)")
    upcoming_games: list[dt.date]
    news: list[NewsItem]
    news_error: str | None = None


class TeamRoster(BaseModel):
    team: TeamRef
    players: list[str]


# ---------------------------------------------------------------- moves

class SimulationRequest(BaseModel):
    add: list[str] = Field(default_factory=list)
    drop: list[str] = Field(default_factory=list)


class MoveResultOut(BaseModel):
    add: list[str]
    drop: list[str]
    expected_wins_before: float
    expected_wins_after: float
    win_prob_before: float
    win_prob_after: float
    matchup_gain: float
    games_delta: float
    season_value_delta: float
    category_deltas: dict[str, float]
    projected_delta: dict[str, float]
    notes: list[str]


class TradeRequest(BaseModel):
    partner_id: int
    give: list[str] = Field(min_length=1)
    get: list[str] = Field(min_length=1)


class TradeResult(BaseModel):
    value_change: float
    ros_games_change: int
    matchup_change: float | None = Field(description="Expected categories (or FPTS in points leagues) this matchup")
    per_game_change: dict[str, float]
    z_change: dict[str, float]
    roster_overflow: int


# ---------------------------------------------------------------- league

class Standing(TeamRef):
    points_for: float
    is_me: bool


class Activity(BaseModel):
    date: str
    team: str
    action: str
    player: str


class Report(BaseModel):
    markdown: str


# ---------------------------------------------------------------- assistant

class ChatSession(BaseModel):
    id: str


class ChatMessage(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
