from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, status

from .. import presenters, schemas
from ..deps import EngineDep

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
