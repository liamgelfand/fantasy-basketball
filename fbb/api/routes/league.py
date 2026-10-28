from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from ...report import build_report
from .. import presenters, schemas
from ..deps import EngineDep, LeagueServiceDep, SnapshotDep

log = logging.getLogger(__name__)
router = APIRouter(tags=["league"])


@router.get("/meta", response_model=schemas.LeagueMeta)
def meta(snap: SnapshotDep, request: Request):
    return presenters.league_meta(snap.engine, snap.loaded_at, request.app.state.chat_enabled)


@router.post("/refresh", status_code=status.HTTP_204_NO_CONTENT)
def refresh(service: LeagueServiceDep):
    service.refresh()


@router.get("/matchup", response_model=schemas.Matchup)
def matchup(engine: EngineDep):
    return presenters.matchup(engine)


@router.get("/standings", response_model=list[schemas.Standing])
def standings(engine: EngineDep):
    return presenters.standings(engine)


@router.get("/activity", response_model=list[schemas.Activity])
def activity(engine: EngineDep, limit: Annotated[int, Query(ge=1, le=100)] = 25):
    try:
        return engine.data.recent_activity(limit)
    except Exception as e:
        log.warning("Recent activity unavailable: %s", e)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ESPN didn't return recent activity.") from e


@router.get("/report", response_model=schemas.Report)
def report(engine: EngineDep):
    return schemas.Report(markdown=build_report(engine))
