"""routes/notifications.py — In-app inbox, SSE stream, Web Push management."""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.csrf import require_csrf
from app.database import get_db
from app.session import get_user_from_cookie
from app.templates import render
from models.notification import Notification
from models.notification_preference import CHANNELS, NotificationPreference
from models.player import Player
from models.web_push_subscription import WebPushSubscription
from routes._auth_helpers import require_login
from services.channels.inapp_channel import register_connection, unregister_connection
from services.notification_service import create_default_preferences

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_linked_players(user, db: Session) -> list[Player]:
    """Return all active Player rows linked to *user*."""
    return db.query(Player).filter(Player.user_id == user.id, Player.is_active.is_(True)).all()


def _player_ids_for_user(user, db: Session) -> list[int]:
    return [p.id for p in _get_linked_players(user, db)]


# ── VAPID public key ──────────────────────────────────────────────────────────


@router.get("/vapid-public-key")
async def vapid_public_key():
    """Return the VAPID public key for the browser push subscription flow."""
    return JSONResponse({"publicKey": settings.VAPID_PUBLIC_KEY})


# ── SSE stream ────────────────────────────────────────────────────────────────


@router.get("/stream")
async def notification_stream(request: Request, db: Session = Depends(get_db)):
    """Server-Sent Events stream for real-time notification badge updates."""
    user = get_user_from_cookie(request)
    if user is None:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    player_ids = _player_ids_for_user(user, db)
    if not player_ids:

        async def keepalive() -> AsyncGenerator[str, None]:
            while True:
                if await request.is_disconnected():
                    break
                yield ": keepalive\n\n"
                await asyncio.sleep(30)

        return StreamingResponse(keepalive(), media_type="text/event-stream")

    player_id = player_ids[0]
    q = register_connection(player_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            unregister_connection(player_id, q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Inbox ─────────────────────────────────────────────────────────────────────


@router.get("")
async def inbox(
    request: Request,
    user=Depends(require_login),
    db: Session = Depends(get_db),
):
    player_ids = _player_ids_for_user(user, db)
    notifications = []
    if player_ids:
        notifications = (
            db.query(Notification)
            .filter(Notification.player_id.in_(player_ids))
            .order_by(Notification.created_at.desc())
            .all()
        )
    return render(
        request,
        "notifications/inbox.html",
        {"user": user, "notifications": notifications},
    )


# ── Mark read ─────────────────────────────────────────────────────────────────


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    request: Request,
    user=Depends(require_login),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    player_ids = _player_ids_for_user(user, db)
    notif = db.get(Notification, notification_id)
    if notif is None or notif.player_id not in player_ids:
        raise HTTPException(status_code=404)
    notif.is_read = True
    db.commit()
    redirect_url = str(request.headers.get("referer", "/notifications"))
    return RedirectResponse(redirect_url, status_code=302)


@router.post("/read-all")
async def mark_read_all(
    request: Request,
    user=Depends(require_login),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    player_ids = _player_ids_for_user(user, db)
    if player_ids:
        db.query(Notification).filter(
            Notification.player_id.in_(player_ids),
            Notification.is_read.is_(False),
        ).update({"is_read": True}, synchronize_session="fetch")
        db.commit()
    return RedirectResponse("/notifications", status_code=302)


# ── Notification preferences ──────────────────────────────────────────────────


@router.post("/preferences")
async def update_preferences(
    request: Request,
    user=Depends(require_login),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    form = await request.form()
    player_ids = _player_ids_for_user(user, db)
    for player_id in player_ids:
        create_default_preferences(player_id, db)
        for channel in CHANNELS:
            enabled = form.get(channel) == "on"
            pref = (
                db.query(NotificationPreference)
                .filter(
                    NotificationPreference.player_id == player_id,
                    NotificationPreference.channel == channel,
                )
                .first()
            )
            if pref:
                pref.enabled = enabled
    db.commit()
    return RedirectResponse("/profile", status_code=302)


# ── Web Push subscribe / unsubscribe ──────────────────────────────────────────


@router.post("/webpush/subscribe")
async def webpush_subscribe(
    request: Request,
    endpoint: str = Form(...),
    p256dh: str = Form(...),
    auth: str = Form(...),
    user=Depends(require_login),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    player_ids = _player_ids_for_user(user, db)
    if not player_ids:
        return JSONResponse({"detail": "No linked player"}, status_code=400)

    for player_id in player_ids:
        existing = (
            db.query(WebPushSubscription)
            .filter(
                WebPushSubscription.player_id == player_id,
                WebPushSubscription.endpoint == endpoint,
            )
            .first()
        )
        if existing is None:
            db.add(
                WebPushSubscription(
                    player_id=player_id,
                    endpoint=endpoint,
                    p256dh_key=p256dh,
                    auth_key=auth,
                )
            )
    db.commit()
    return JSONResponse({"status": "ok"})


@router.post("/webpush/unsubscribe-all")
async def webpush_unsubscribe_all(
    request: Request,
    user=Depends(require_login),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    player_ids = _player_ids_for_user(user, db)
    if player_ids:
        db.query(WebPushSubscription).filter(WebPushSubscription.player_id.in_(player_ids)).delete(
            synchronize_session="fetch"
        )
        db.commit()
    return RedirectResponse("/profile", status_code=302)


@router.post("/webpush/resubscribe")
async def webpush_resubscribe(
    request: Request,
    endpoint: str = Form(...),
    p256dh: str = Form(...),
    auth: str = Form(...),
    user=Depends(require_login),
    db: Session = Depends(get_db),
):
    """CSRF-exempt endpoint for service worker pushsubscriptionchange renewal."""
    player_ids = _player_ids_for_user(user, db)
    if not player_ids:
        return JSONResponse({"detail": "No linked player"}, status_code=400)
    for player_id in player_ids:
        existing = (
            db.query(WebPushSubscription)
            .filter(
                WebPushSubscription.player_id == player_id,
                WebPushSubscription.endpoint == endpoint,
            )
            .first()
        )
        if existing is None:
            db.add(
                WebPushSubscription(
                    player_id=player_id,
                    endpoint=endpoint,
                    p256dh_key=p256dh,
                    auth_key=auth,
                )
            )
    db.commit()
    return JSONResponse({"status": "ok"})
