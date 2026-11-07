"""Loads settings from .env / environment variables."""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

STAT_WINDOWS = ("blend", "season", "last_30", "last_15", "last_7", "projected")


def _default_season() -> int:
    # ESPN labels an NBA season by the year it ends (2026-27 -> 2027).
    today = dt.date.today()
    return today.year + 1 if today.month >= 9 else today.year


def _opt_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    return int(value) if value else None


def _opt_str(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


@dataclass(frozen=True)
class Config:
    league_id: int
    year: int
    team_id: int | None
    espn_s2: str | None
    swid: str | None
    model: str
    effort: str
    stat_window: str
    punt_categories: frozenset[str] = field(default_factory=frozenset)
    matchup_end_date: dt.date | None = None
    matchup_end_weekday: int = 6  # 0=Mon ... 6=Sun
    free_agent_pool: int = 75
    web_search: bool = True
    reports_dir: Path = ROOT / "reports"


def load_config() -> Config:
    league_id = _opt_int("ESPN_LEAGUE_ID")
    if league_id is None:
        raise SystemExit("ESPN_LEAGUE_ID is not set. Copy .env.example to .env and fill it in.")

    window = os.getenv("STAT_WINDOW", "blend").strip()
    if window not in STAT_WINDOWS:
        raise SystemExit(f"STAT_WINDOW must be one of {STAT_WINDOWS}, got {window!r}")

    end_date = _opt_str("MATCHUP_END_DATE")
    punts = _opt_str("PUNT_CATEGORIES") or ""

    return Config(
        league_id=league_id,
        year=_opt_int("ESPN_SEASON") or _default_season(),
        team_id=_opt_int("ESPN_TEAM_ID"),
        espn_s2=_opt_str("ESPN_S2"),
        swid=_opt_str("ESPN_SWID"),
        model=os.getenv("CLAUDE_MODEL", "claude-opus-5-5").strip(),
        effort=os.getenv("CLAUDE_EFFORT", "high").strip(),
        stat_window=window,
        punt_categories=frozenset(c.strip().upper() for c in punts.split(",") if c.strip()),
        matchup_end_date=dt.date.fromisoformat(end_date) if end_date else None,
        matchup_end_weekday=_opt_int("MATCHUP_END_WEEKDAY") if _opt_int("MATCHUP_END_WEEKDAY") is not None else 6,
        free_agent_pool=_opt_int("FREE_AGENT_POOL") or 75,
        web_search=os.getenv("CLAUDE_WEB_SEARCH", "true").strip().lower() not in {"0", "false", "no"},
    )
