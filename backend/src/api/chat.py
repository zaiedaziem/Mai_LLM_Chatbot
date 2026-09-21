import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from supabase import Client

from .. import config
from ..dependencies import get_db, get_llm, get_system_prompt
from ..llm import LLMProvider
from ..middleware.rate_limit import rate_limit

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=8000)


def make_title(message: str) -> str:
    message = " ".join(message.split())
    if len(message) <= config.TITLE_MAX_LEN:
        return message
    return message[: config.TITLE_MAX_LEN - 1].rstrip() + "…"


def sse(payload: dict) -> str:
    """One Server-Sent Events frame."""
    return f"data: {json.dumps(payload)}\n\n"


# dependencies=[...] runs rate_limit before the handler; we don't need its return value.
@router.post("/stream", dependencies=[Depends(rate_limit)])
def chat_stream(
    request: ChatRequest,
    db: Client = Depends(get_db),
    llm: LLMProvider = Depends(get_llm),
    system_prompt: str | None = Depends(get_system_prompt),
):
    session = db.table("sessions").select("id, title").eq("id", request.session_id).execute()
    if not session.data:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.data[0]["title"] is None:
        db.table("sessions").update({"title": make_title(request.message)}).eq("id", request.session_id).execute()

    db.table("messages").insert(
        {"session_id": request.session_id, "role": "user", "content": request.message}
    ).execute()

    # Replaying stored turns is what gives the model its memory.
    history = (
        db.table("messages")
        .select("role, content")
        .eq("session_id", request.session_id)
        .order("created_at")
        .execute()
    )
    conversation = [{"role": m["role"], "content": m["content"]} for m in history.data]

    def generate():
        reply = ""
        try:
            # The endpoint has no idea this is Groq. That's the point.
            for token in llm.stream(conversation, system_prompt):
                reply += token
                yield sse({"content": token})
        except Exception as exc:
            # HTTP 200 is already on the wire; errors must travel in-band.
            yield sse({"error": str(exc)})
            return

        db.table("messages").insert(
            {"session_id": request.session_id, "role": "assistant", "content": reply}
        ).execute()
        yield sse({"done": True})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )