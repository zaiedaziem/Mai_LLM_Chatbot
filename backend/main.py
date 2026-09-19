import json
import os
import uuid
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from groq import Groq
from pydantic import BaseModel, Field
from supabase import Client, create_client

load_dotenv()

MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

app = FastAPI(title="LLM Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# Clients are built lazily so the module imports without credentials and tests
# can swap them out via app.dependency_overrides.
@lru_cache
def get_db() -> Client:
    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set")
    return create_client(url, key)


@lru_cache
def get_llm() -> Groq:
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY must be set")
    return Groq(api_key=key)


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=8000)


@app.post("/sessions")
def create_session(db: Client = Depends(get_db)):
    session_id = str(uuid.uuid4())
    db.table("sessions").insert({"id": session_id}).execute()
    return {"session_id": session_id}


@app.get("/messages/{session_id}")
def get_messages(session_id: str, db: Client = Depends(get_db)):
    result = (
        db.table("messages")
        .select("role, content, created_at")
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    )
    return result.data


@app.delete("/sessions/{session_id}")
def clear_session(session_id: str, db: Client = Depends(get_db)):
    db.table("messages").delete().eq("session_id", session_id).execute()
    return {"status": "cleared"}


@app.post("/chat/stream")
def chat_stream(
    request: ChatRequest,
    db: Client = Depends(get_db),
    llm: Groq = Depends(get_llm),
):
    session = db.table("sessions").select("id").eq("id", request.session_id).execute()
    if not session.data:
        raise HTTPException(status_code=404, detail="Session not found")

    db.table("messages").insert(
        {"session_id": request.session_id, "role": "user", "content": request.message}
    ).execute()

    # Replaying the stored turns is what gives the model its memory of the
    # conversation; the user's new message is already among them.
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
            stream = llm.chat.completions.create(
                model=MODEL,
                messages=conversation,
                stream=True,
                max_tokens=1024,
            )
            for chunk in stream:
                token = chunk.choices[0].delta.content or ""
                if token:
                    reply += token
                    yield f"data: {json.dumps({'content': token})}\n\n"
        except Exception as exc:
            # The response status was already committed when streaming began,
            # so failures have to travel in-band instead of as an HTTP error.
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
            return

        db.table("messages").insert(
            {"session_id": request.session_id, "role": "assistant", "content": reply}
        ).execute()
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
