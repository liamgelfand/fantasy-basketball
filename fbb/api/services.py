"""Long-lived server state: cached league snapshots and Claude chat sessions."""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, replace
from typing import Callable, Protocol

from ..config import Config
from ..engine import Engine

log = logging.getLogger(__name__)


class UpstreamError(RuntimeError):
    """ESPN (or config) failed while building a snapshot; surfaced to the client as 503."""


@dataclass(frozen=True)
class Snapshot:
    engine: Engine
    loaded_at: dt.datetime


def build_engine(cfg: Config) -> Engine:
    from ..espn import LeagueData

    engine = Engine(LeagueData(cfg))
    _ = engine.free_agent_board  # score free agents up front so the first page load is fast
    return engine


class LeagueService:
    """Caches one Engine per (stat window, punts) combination for `ttl` seconds."""

    def __init__(self, base: Config, factory: Callable[[Config], Engine] = build_engine, ttl: float = 600,
                 clock: Callable[[], float] = time.monotonic):
        self.base = base
        self._factory = factory
        self._ttl = ttl
        self._clock = clock
        self._cache: dict[tuple[str, frozenset[str]], tuple[float, Snapshot]] = {}
        self._lock = threading.Lock()

    def snapshot(self, window: str | None = None, punts: frozenset[str] | None = None) -> Snapshot:
        key = (window or self.base.stat_window, self.base.punt_categories if punts is None else punts)
        with self._lock:  # serialize builds: concurrent first loads share one ESPN pull
            hit = self._cache.get(key)
            if hit and self._clock() - hit[0] < self._ttl:
                return hit[1]
            cfg = replace(self.base, stat_window=key[0], punt_categories=key[1])
            try:
                snap = Snapshot(self._factory(cfg), dt.datetime.now().astimezone())
            except SystemExit as e:  # config/espn layers exit with a readable message
                raise UpstreamError(str(e)) from None
            except Exception as e:
                log.exception("Failed to load league snapshot")
                raise UpstreamError(f"Couldn't load your league from ESPN: {type(e).__name__}: {e}") from e
            self._cache[key] = (self._clock(), snap)
            return snap

    def refresh(self) -> None:
        with self._lock:
            self._cache.clear()


class Agent(Protocol):
    def ask(self, question: str, on_tool: Callable[[str, dict], None] | None = None) -> str: ...


@dataclass
class ChatSessionState:
    agent: Agent
    lock: threading.Lock


class ChatSessions:
    """In-memory conversations. Each keeps its Claude message history; oldest are evicted past `limit`."""

    def __init__(self, agent_factory: Callable[[Engine], Agent], limit: int = 50):
        self._factory = agent_factory
        self._limit = limit
        self._sessions: OrderedDict[str, ChatSessionState] = OrderedDict()
        self._lock = threading.Lock()

    def new_agent(self, engine: Engine) -> Agent:
        return self._factory(engine)

    def create(self, engine: Engine) -> str:
        sid = uuid.uuid4().hex
        state = ChatSessionState(self._factory(engine), threading.Lock())
        with self._lock:
            self._sessions[sid] = state
            while len(self._sessions) > self._limit:
                self._sessions.popitem(last=False)
        return sid

    def get(self, sid: str) -> ChatSessionState | None:
        with self._lock:
            state = self._sessions.get(sid)
            if state:
                self._sessions.move_to_end(sid)
            return state

    def delete(self, sid: str) -> None:
        with self._lock:
            self._sessions.pop(sid, None)

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()


def default_agent_factory(engine: Engine) -> Agent:
    from ..agent import FantasyAgent

    return FantasyAgent(engine)
