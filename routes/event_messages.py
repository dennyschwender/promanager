"""routes/event_messages.py — Event chat message endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.csrf import require_csrf_header
from app.database import get_db
from models.event import Event
from models.event_message import EventMessage
from models.user import User
from routes._auth_helpers import require_login
from services.chat_service import (
    author_display_name,
    message_to_dict,
    push_chat_delete_sse,
    push_chat_message_sse,
    send_telegram_notifications,
)

router = APIRouter()


class _PostBody(BaseModel):
    lane: str
    body: str


@router.get("/events/{event_id}/messages")
async def list_messages(
    event_id: int,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
) -> JSONResponse:
    if db.get(Event, event_id) is None:
        raise HTTPException(status_code=404)
    messages = (
        db.query(EventMessage)
        .filter(EventMessage.event_id == event_id)
        .order_by(EventMessage.created_at.asc())
        .all()
    )
    result = []
    for msg in messages:
        author = db.get(User, msg.user_id) if msg.user_id else None
        result.append(message_to_dict(msg, author_display_name(author)))
    return JSONResponse(result)


@router.post("/events/{event_id}/messages")
async def post_message(
    event_id: int,
    body: _PostBody,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_login),
    _csrf: None = Depends(require_csrf_header),
    db: Session = Depends(get_db),
) -> JSONResponse:
    if db.get(Event, event_id) is None:
        raise HTTPException(status_code=404)
    if body.lane not in ("announcement", "discussion"):
        raise HTTPException(status_code=400, detail="Invalid lane")
    if body.lane == "announcement" and not (user.is_admin or user.is_coach):
        raise HTTPException(status_code=403, detail="Only coaches and admins can post announcements")
    if not body.body.strip():
        raise HTTPException(status_code=400, detail="Message body cannot be empty")

    msg = EventMessage(
        event_id=event_id,
        user_id=user.id,
        lane=body.lane,
        body=body.body.strip(),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    author_name = author_display_name(user)
    msg_dict = message_to_dict(msg, author_name)

    push_chat_message_sse(event_id, msg_dict, db)
    background_tasks.add_task(
        send_telegram_notifications,
        event_id,
        author_name,
        body.lane,
        body.body.strip(),
        user.id,
    )

    return JSONResponse(msg_dict, status_code=201)


@router.delete("/events/{event_id}/messages/{msg_id}")
async def delete_message(
    event_id: int,
    msg_id: int,
    _csrf: None = Depends(require_csrf_header),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
) -> JSONResponse:
    msg = db.get(EventMessage, msg_id)
    if msg is None or msg.event_id != event_id:
        raise HTTPException(status_code=404)
    if msg.user_id != user.id and not (user.is_admin or user.is_coach):
        raise HTTPException(status_code=403)
    db.delete(msg)
    db.commit()
    push_chat_delete_sse(event_id, msg_id, db)
    return JSONResponse({"ok": True})
