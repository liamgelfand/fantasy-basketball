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
def send_message(session_id: str, body: schemas.ChatMessage, chats: ChatSessionsDep):
    state = chats.get(session_id)
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chat session expired. Start a new chat.")
    if state.lock.locked():
        raise HTTPException(status.HTTP_409_CONFLICT, "Claude is still answering the last message.")
    return sse(agent_events(state.agent, body.text, state.lock))


@router.post("/game-plan")
def game_plan(engine: EngineDep, chats: ChatSessionsDep):
    return sse(agent_events(chats.new_agent(engine), AI_REPORT_PROMPT))
