"""FastAPI application factory. Serves the JSON API under /api and the built web client at /."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ..config import ROOT, load_config
from .routes import assistant, league, moves, players
from .services import ChatSessions, LeagueService, UpstreamError, default_agent_factory

WEB_DIST = ROOT / "web" / "dist"


def create_app(league_service: LeagueService | None = None, chats: ChatSessions | None = None,
               chat_enabled: bool | None = None, web_dist: Path | None = WEB_DIST) -> FastAPI:
    app = FastAPI(title="Fantasy HQ", version="1.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.league = league_service or LeagueService(load_config())
    app.state.chats = chats or ChatSessions(default_agent_factory)
    app.state.chat_enabled = bool(os.getenv("ANTHROPIC_API_KEY")) if chat_enabled is None else chat_enabled

    @app.exception_handler(UpstreamError)
    def upstream_error(_request: Request, exc: UpstreamError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    for module in (league, players, moves, assistant):
        app.include_router(module.router, prefix="/api")

    if web_dist and (web_dist / "index.html").is_file():
        _mount_web_client(app, web_dist)
    return app


def _mount_web_client(app: FastAPI, dist: Path) -> None:
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    index = dist / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        file = (dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(dist.resolve()):
            return FileResponse(file)
        return FileResponse(index)  # client-side routes (/roster, /chat, ...) all load the app shell
