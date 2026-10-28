"""FastAPI dependencies: resolve the shared services and the snapshot a request asks for."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request

from ..config import STAT_WINDOWS
from ..engine import Engine
from .services import ChatSessions, LeagueService, Snapshot


def league_service(request: Request) -> LeagueService:
    return request.app.state.league


def chat_sessions(request: Request) -> ChatSessions:
    return request.app.state.chats


def snapshot(
    service: Annotated[LeagueService, Depends(league_service)],
    window: Annotated[str | None, Query(description=f"Stat window: one of {', '.join(STAT_WINDOWS)}")] = None,
    punt: Annotated[list[str] | None, Query(description="Punted category; repeat for several")] = None,
) -> Snapshot:
    if window is not None and window not in STAT_WINDOWS:
        raise HTTPException(422, f"window must be one of {STAT_WINDOWS}")
    punts = frozenset(p.strip().upper() for p in punt if p.strip()) if punt is not None else None
    return service.snapshot(window, punts)


def engine(snap: Annotated[Snapshot, Depends(snapshot)]) -> Engine:
    return snap.engine


SnapshotDep = Annotated[Snapshot, Depends(snapshot)]
EngineDep = Annotated[Engine, Depends(engine)]
LeagueServiceDep = Annotated[LeagueService, Depends(league_service)]
ChatSessionsDep = Annotated[ChatSessions, Depends(chat_sessions)]
