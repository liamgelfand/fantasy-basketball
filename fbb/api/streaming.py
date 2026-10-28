"""Server-sent events for the Claude tool loop: tool progress as it happens, then the answer."""
from __future__ import annotations

import json
import logging
import queue
import threading
from typing import Iterator

from fastapi.responses import StreamingResponse

from .services import Agent

log = logging.getLogger(__name__)
_DONE = object()


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"


def _tool_label(name: str, args: dict) -> str:
    detail = ", ".join(f"{k}={v}" for k, v in args.items() if v not in (None, "", []))
    return name.replace("_", " ") + (f" ({detail})" if detail else "")


def agent_events(agent: Agent, question: str, lock: threading.Lock | None = None) -> Iterator[str]:
    """Run `agent.ask` on a worker thread and yield `tool`, then `answer` or `error`, events."""
    events: queue.Queue = queue.Queue()

    def run() -> None:
        try:
            if lock:
                lock.acquire()
            answer = agent.ask(question, on_tool=lambda n, a: events.put(
                _event("tool", {"name": n, "label": _tool_label(n, a or {})})))
            events.put(_event("answer", {"text": answer}))
        except Exception as e:
            log.exception("Agent request failed")
            events.put(_event("error", {"message": f"Something went wrong talking to Claude: {type(e).__name__}: {e}"}))
        finally:
            if lock:
                lock.release()
            events.put(_DONE)

    threading.Thread(target=run, daemon=True).start()
    while (item := events.get()) is not _DONE:
        yield item


def sse(stream: Iterator[str]) -> StreamingResponse:
    return StreamingResponse(stream, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
