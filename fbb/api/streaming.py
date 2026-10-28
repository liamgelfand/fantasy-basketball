"""Server-sent events for the Claude tool loop: tool progress as it happens, then the answer.

The blocking agent call runs on a worker thread. If the client goes away (Stop button, closed
tab), the stream is cancelled and the worker is told to stop before its next API round, so a
dropped request doesn't keep spending tokens.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections.abc import AsyncIterator, Callable

from fastapi.responses import StreamingResponse

log = logging.getLogger(__name__)

ToolCallback = Callable[[str, dict], None]
AgentRun = Callable[[ToolCallback, threading.Event], str]
_DONE = object()


def _event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"


def tool_label(name: str, args: dict) -> str:
    detail = ", ".join(f"{k}={v}" for k, v in args.items() if v not in (None, "", []))
    return name.replace("_", " ") + (f" ({detail})" if detail else "")


async def agent_events(run: AgentRun) -> AsyncIterator[str]:
    """Yield `tool` events while `run` works, then one `answer` or `error` event."""
    loop = asyncio.get_running_loop()
    events: asyncio.Queue = asyncio.Queue()
    cancel = threading.Event()

    def emit(item) -> None:
        loop.call_soon_threadsafe(events.put_nowait, item)

    def work() -> None:
        try:
            answer = run(lambda n, a: emit(_event("tool", {"name": n, "label": tool_label(n, a or {})})), cancel)
            emit(_event("answer", {"text": answer}))
        except Exception as e:
            log.exception("Agent request failed")
            emit(_event("error", {"message": f"Something went wrong talking to Claude: {type(e).__name__}: {e}"}))
        finally:
            emit(_DONE)

    threading.Thread(target=work, name="claude-agent", daemon=True).start()
    try:
        while (item := await events.get()) is not _DONE:
            yield item
    finally:  # normal end, or the client disconnected and the stream was cancelled
        cancel.set()


def sse(stream: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(stream, media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
