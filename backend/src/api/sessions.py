import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from supabase import Client

from .. import config
from ..dependencies import get_db

router = APIRouter(prefix="/sessions", tags=["sessions"])


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=config.TITLE_MAX_LEN)


@router.post("")
def create_session(db: Client = Depends(get_db)):
    session_id = str(uuid.uuid4())
    db.table("sessions").insert({"id": session_id, "title": None}).execute()
    return {"session_id": session_id, "title": None}


@router.get("")
def list_sessions(db: Client = Depends(get_db)):
    result = (
        db.table("sessions")
        .select("id, title, created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


@router.patch("/{session_id}")
def rename_session(session_id: str, request: RenameRequest, db: Client = Depends(get_db)):
    result = db.table("sessions").update({"title": request.title}).eq("id", session_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Session not found")
    return result.data[0]


@router.delete("/{session_id}")
def delete_session(session_id: str, db: Client = Depends(get_db)):
    # messages.session_id is ON DELETE CASCADE, so the transcript goes too.
    db.table("sessions").delete().eq("id", session_id).execute()
    return {"status": "deleted"}


@router.get("/{session_id}/messages")
def get_messages(session_id: str, db: Client = Depends(get_db)):
    result = (
        db.table("messages")
        .select("role, content, created_at")
        .eq("session_id", session_id)
        .order("created_at")
        .execute()
    )
    return result.data