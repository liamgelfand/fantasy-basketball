from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, status

from .. import presenters, schemas
from ..deps import EngineDep

log = logging.getLogger(__name__)
router = APIRouter(tags=["players"])

Position = Literal["PG", "SG", "SF", "PF", "C", "G", "F"]


@router.get("/roster", response_model=schemas.Roster)
def roster(engine: EngineDep):
    return presenters.roster(engine)


@router.get("/free-agents", response_model=schemas.FreeAgentBoard)
def free_agents(engine: EngineDep, position: Position | None = None, include_injured: bool = False):
    return presenters.free_agents(engine, position, include_injured)


@router.get("/teams/{team_id}/roster", response_model=schemas.TeamRoster)
def team_roster(team_id: int, engine: EngineDep):
    team = engine.data.teams.get(team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No team with id {team_id}")
    return presenters.team_roster(engine, team)


@router.get("/players/{player_id}", response_model=schemas.PlayerDetail)
def player(player_id: int, engine: EngineDep, include_news: bool = True):
    p = engine.data.player_by_id(player_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No player with id {player_id}")
    news, news_error = [], None
    if include_news:
        try:
            news = engine.data.player_news(p)
        except Exception as e:  # news is a nice-to-have; the stats still render
            log.warning("News unavailable for %s: %s", p.name, e)
            news_error = "ESPN news is unavailable right now."
    return presenters.player_detail(engine, p, news, news_error)
