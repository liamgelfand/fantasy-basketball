"""Long-lived server state: cached league snapshots and Claude chat sessions."""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from ..config import Config
from ..engine import Engine

log = logging.getLogger(__name__)

SnapshotKey = tuple[str, frozenset[str]]


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
    """Caches one Engine per (stat window, punts) combination for `ttl` seconds.

    Builds are locked per key: a slow ESPN pull for one setting never blocks requests that are
    served from another setting's cached snapshot, and concurrent first loads share one pull.
    """

    def __init__(self, base: Config, factory: Callable[[Config], Engine] = build_engine, ttl: float = 600,
                 clock: Callable[[], float] = time.monotonic):
        self.base = base
        self._factory = factory
        self._ttl = ttl
        self._clock = clock
        self._cache: dict[SnapshotKey, tuple[float, Snapshot]] = {}
        self._key_locks: dict[SnapshotKey, threading.Lock] = {}
        self._lock = threading.Lock()  # guards the two dicts above, never held during a build

    def _fresh(self, key: SnapshotKey) -> Snapshot | None:
        hit = self._cache.get(key)
        return hit[1] if hit and self._clock() - hit[0] < self._ttl else None

    def snapshot(self, window: str | None = None, punts: frozenset[str] | None = None) -> Snapshot:
        key = (window or self.base.stat_window, self.base.punt_categories if punts is None else punts)
        with self._lock:
            if snap := self._fresh(key):
                return snap
            key_lock = self._key_locks.setdefault(key, threading.Lock())

        with key_lock:
            with self._lock:
                if snap := self._fresh(key):  # another request finished the build while we waited
                    return snap
            cfg = replace(self.base, stat_window=key[0], punt_categories=key[1])
            try:
                snap = Snapshot(self._factory(cfg), dt.datetime.now().astimezone())
            except SystemExit as e:  # config/espn layers exit with a readable message
                raise UpstreamError(str(e)) from None
            except Exception as e:
                log.exception("Failed to load league snapshot")
                raise UpstreamError(f"Couldn't load your league from ESPN: {type(e).__name__}: {e}") from e
            with self._lock:
                now = self._clock()
                self._cache = {k: v for k, v in self._cache.items() if now - v[0] < self._ttl}  # drop expired
                self._cache[key] = (now, snap)
            return snap

    def refresh(self) -> None:
        with self._lock:
            self._cache.clear()


# ---------------------------------------------------------------- chat

class Agent(Protocol):
    def ask(self, question: str, on_tool: Callable[[str, dict], None] | None = None,
            cancel: threading.Event | None = None) -> str: ...

    def export_messages(self) -> list[dict]: ...

    def import_messages(self, messages: list[dict]) -> None: ...


ToolCallback = Callable[[str, dict], None]
_SESSION_ID = re.compile(r"^[0-9a-f]{32}$")


class ChatStore:
    """One JSON file per conversation, so chats survive a server restart. Files idle for
    `max_age_days` are deleted on startup."""

    def __init__(self, directory: Path, max_age_days: int = 30):
        self.dir = directory
        self.dir.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - max_age_days * 86400
        for f in self.dir.glob("*.json"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)

    def _path(self, sid: str) -> Path:
        return self.dir / f"{sid}.json"

    def load(self, sid: str) -> list[dict] | None:
        try:
            return json.loads(self._path(sid).read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def save(self, sid: str, messages: list[dict]) -> None:
        tmp = self._path(sid).with_suffix(".tmp")
        tmp.write_text(json.dumps(messages, default=str), encoding="utf-8")
        tmp.replace(self._path(sid))  # atomic: a crash never leaves a half-written history

    def delete(self, sid: str) -> None:
        self._path(sid).unlink(missing_ok=True)


@dataclass
class ChatSessionState:
    agent: Agent
    engine: Engine
    lock: threading.Lock


class ChatSessions:
    """Conversations keyed by id. Each keeps its Claude message history (in memory, and on disk
    when a store is given); the least recently used are dropped from memory past `limit`."""

    def __init__(self, agent_factory: Callable[[Engine], Agent], store: ChatStore | None = None, limit: int = 50):
        self._factory = agent_factory
        self._store = store
        self._limit = limit
        self._sessions: OrderedDict[str, ChatSessionState] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def valid_id(sid: str) -> bool:
        return bool(_SESSION_ID.match(sid))

    def new_agent(self, engine: Engine) -> Agent:
        return self._factory(engine)

    def _remember(self, sid: str, state: ChatSessionState) -> None:
        with self._lock:
            self._sessions[sid] = state
            self._sessions.move_to_end(sid)
            while len(self._sessions) > self._limit:
                self._sessions.popitem(last=False)

    def create(self, engine: Engine) -> str:
        sid = uuid.uuid4().hex
        self._remember(sid, ChatSessionState(self._factory(engine), engine, threading.Lock()))
        return sid

    def get(self, sid: str, engine: Engine) -> ChatSessionState | None:
        """The live session, or one restored from disk after a restart; None if unknown."""
        if not self.valid_id(sid):
            return None
        with self._lock:
            state = self._sessions.get(sid)
            if state:
                self._sessions.move_to_end(sid)
                return state
        history = self._store.load(sid) if self._store else None
        if history is None:
            return None
        agent = self._factory(engine)
        agent.import_messages(history)
        state = ChatSessionState(agent, engine, threading.Lock())
        self._remember(sid, state)
        return state

    def ask(self, sid: str, state: ChatSessionState, engine: Engine, question: str,
            on_tool: ToolCallback | None, cancel: threading.Event | None) -> str:
        """Answer one message, waiting for any earlier answer in this chat to finish first.

        If the league snapshot changed since the chat started (new settings or a refresh), the
        conversation moves onto a fresh agent over the new data, keeping its history.
        """
        with state.lock:
            if state.engine is not engine:
                fresh = self._factory(engine)
                fresh.import_messages(state.agent.export_messages())
                state.agent, state.engine = fresh, engine
            try:
                return state.agent.ask(question, on_tool=on_tool, cancel=cancel)
            finally:
                if self._store:
                    self._store.save(sid, state.agent.export_messages())

    def delete(self, sid: str) -> None:
        if not self.valid_id(sid):
            return
        with self._lock:
            self._sessions.pop(sid, None)
        if self._store:
            self._store.delete(sid)


def default_agent_factory(engine: Engine) -> Agent:
    from ..agent import FantasyAgent

    return FantasyAgent(engine)
