"""Claude endpoints. Replies stream as server-sent events so the UI can show tool progress."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ...agent import AI_REPORT_PROMPT
from .. import schemas
from ..deps import ChatSessionsDep, EngineDep
from ..streaming import agent_events, sse


def require_claude(request: Request) -> None:
    if not request.app.state.chat_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Add ANTHROPIC_API_KEY to your .env file and restart the server to enable Claude.")


router = APIRouter(prefix="/assistant", tags=["assistant"], dependencies=[Depends(require_claude)])


@router.post("/sessions", response_model=schemas.ChatSession, status_code=status.HTTP_201_CREATED)
def create_session(engine: EngineDep, chats: ChatSessionsDep):
    return schemas.ChatSession(id=chats.create(engine))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: str, chats: ChatSessionsDep):
    chats.delete(session_id)


@router.post("/sessions/{session_id}/messages")
def send_message(session_id: str, body: schemas.ChatMessage, engine: EngineDep, chats: ChatSessionsDep):
    """Answers use the snapshot for this request's settings, so a chat follows window/punt
    changes and refreshes instead of reasoning over stale data."""
    state = chats.get(session_id, engine)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat session expired. Start a new chat.")
    return sse(agent_events(
        lambda on_tool, cancel: chats.ask(session_id, state, engine, body.text, on_tool, cancel)))


@router.post("/game-plan")
def game_plan(engine: EngineDep, chats: ChatSessionsDep):
    agent = chats.new_agent(engine)
    return sse(agent_events(lambda on_tool, cancel: agent.ask(AI_REPORT_PROMPT, on_tool=on_tool, cancel=cancel)))
