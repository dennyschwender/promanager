"""routes/notifications.py — In-app inbox, SSE stream, Web Push management."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
from typing import AsyncGenerator
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from sqlalchemy import or_
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
from routes._auth_helpers import require_login, safe_redirect
from services.channels.inapp_channel import (
    register_connection,
    register_user_connection,
    unregister_connection,
    unregister_user_connection,
)
from services.notification_service import create_default_preferences

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _get_linked_players(user, db: Session) -> list[Player]:
    """Return all active Player rows linked to *user*."""
    return (
        db.query(Player)
        .filter(Player.user_id == user.id, Player.is_active.is_(True), Player.archived_at.is_(None))
        .all()
    )


def _player_ids_for_user(user, db: Session) -> list[int]:
    return [p.id for p in _get_linked_players(user, db)]


def _notification_filter(user, player_ids: list[int]):
    """SQLAlchemy filter clause: notifications owned by this user via player OR user_id."""
    conditions = [Notification.user_id == user.id]
    if player_ids:
        conditions.append(Notification.player_id.in_(player_ids))
    return or_(*conditions)


# ── VAPID public key ──────────────────────────────────────────────────────────


@router.get("/vapid-public-key")
async def vapid_public_key():
    """Return the VAPID public key for the browser push subscription flow."""
    return JSONResponse({"publicKey": settings.VAPID_PUBLIC_KEY})


@router.get("/unread-count")
async def unread_count(
    request: Request,
    user=Depends(require_login),
    db: Session = Depends(get_db),
):
    player_ids = _player_ids_for_user(user, db)
    count = (
        db.query(Notification)
        .filter(
            or_(
                Notification.player_id.in_(player_ids) if player_ids else False,
                Notification.user_id == user.id,
            ),
            Notification.is_read.is_(False),
        )
        .count()
    )
    return JSONResponse({"unread_count": count})


# ── SSE stream ────────────────────────────────────────────────────────────────


@router.get("/stream")
async def notification_stream(request: Request):
    """Server-Sent Events stream for real-time notification badge updates."""
    from app.database import SessionLocal

    user = get_user_from_cookie(request)
    if user is None:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    with SessionLocal() as db:
        player_ids = _player_ids_for_user(user, db)

    from app.main import shutdown_event

    async def _sleep_or_shutdown(seconds: float) -> bool:
        done, pending = await asyncio.wait(
            [
                asyncio.ensure_future(asyncio.sleep(seconds)),
                asyncio.ensure_future(shutdown_event.wait()),
            ],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
        return shutdown_event.is_set()

    # Choose connection key: player-keyed for members, user-keyed for unlinked admins
    if player_ids:
        conn_id = player_ids[0]
        q = register_connection(conn_id)
        unregister = lambda: unregister_connection(conn_id, q)  # noqa: E731
    else:
        conn_id = user.id
        q = register_user_connection(conn_id)
        unregister = lambda: unregister_user_connection(conn_id, q)  # noqa: E731

    async def event_generator() -> AsyncGenerator[str, None]:
        ticks = 0
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    get_task = asyncio.ensure_future(q.get())
                    shutdown_task = asyncio.ensure_future(shutdown_event.wait())
                    done, pending = await asyncio.wait(
                        [get_task, shutdown_task],
                        timeout=2.0,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for t in pending:
                        t.cancel()
                    if shutdown_event.is_set():
                        break
                    if get_task in done:
                        yield f"data: {get_task.result()}\n\n"
                        ticks = 0
                    else:
                        if await request.is_disconnected():
                            break
                        ticks += 1
                        if ticks >= 15:
                            yield ": keepalive\n\n"
                            ticks = 0
                except asyncio.CancelledError:
                    break
        finally:
            unregister()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Inbox ─────────────────────────────────────────────────────────────────────


@router.get("")
async def inbox(
    request: Request,
    user=Depends(require_login),
    db: Session = Depends(get_db),
):
    player_ids = _player_ids_for_user(user, db)
    notifications = (
        db.query(Notification)
        .filter(_notification_filter(user, player_ids))
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
    if notif is None:
        raise HTTPException(status_code=404)
    # Verify ownership: either via player or via user_id
    owns = (notif.player_id in player_ids) or (notif.user_id == user.id)
    if not owns:
        raise HTTPException(status_code=404)
    notif.is_read = True
    db.commit()
    referer = str(request.headers.get("referer", ""))
    redirect_url = safe_redirect(referer, fallback="/notifications")
    return RedirectResponse(redirect_url, status_code=302)


@router.post("/read-all")
async def mark_read_all(
    request: Request,
    user=Depends(require_login),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    player_ids = _player_ids_for_user(user, db)
    db.query(Notification).filter(
        _notification_filter(user, player_ids),
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
    if player_ids:
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
    else:
        # Unlinked admin/coach: save user-keyed preferences
        from services.notification_service import create_default_user_preferences  # noqa: PLC0415

        create_default_user_preferences(user.id, db)
        for channel in CHANNELS:
            enabled = form.get(channel) == "on"
            pref = (
                db.query(NotificationPreference)
                .filter(
                    NotificationPreference.user_id == user.id,
                    NotificationPreference.channel == channel,
                )
                .first()
            )
            if pref:
                pref.enabled = enabled
    db.commit()
    return RedirectResponse("/profile", status_code=302)


# ── Web Push subscribe / unsubscribe ──────────────────────────────────────────

_PRIVATE_IP_RE = re.compile(
    r"^(localhost|.*\.local)" r"|^(10|127|169\.254|192\.168)\." r"|^172\.(1[6-9]|2[0-9]|3[0-1])\."
)


def _validate_webpush_endpoint(endpoint: str) -> None:
    """Raise HTTPException(400) if endpoint is not a safe HTTPS push-service URL."""
    try:
        parsed = urlparse(endpoint)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid push endpoint")
    if parsed.scheme != "https":
        raise HTTPException(status_code=400, detail="Push endpoint must use HTTPS")
    host = parsed.hostname or ""
    if not host:
        raise HTTPException(status_code=400, detail="Invalid push endpoint")
    # Block private/loopback IP addresses and hostnames
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            raise HTTPException(status_code=400, detail="Push endpoint must be a public URL")
    except ValueError:
        pass  # host is a domain name, not an IP — check against known private patterns
    if _PRIVATE_IP_RE.match(host):
        raise HTTPException(status_code=400, detail="Push endpoint must be a public URL")


def _save_subscription(
    db: Session, *, player_id: int | None, user_id: int | None, endpoint: str, p256dh: str, auth: str
) -> None:
    """Upsert a WebPushSubscription keyed by player_id or user_id + endpoint."""
    existing = (
        db.query(WebPushSubscription)
        .filter(
            WebPushSubscription.player_id == player_id if player_id else WebPushSubscription.user_id == user_id,
            WebPushSubscription.endpoint == endpoint,
        )
        .first()
    )
    if existing is None:
        db.add(
            WebPushSubscription(
                player_id=player_id, user_id=user_id, endpoint=endpoint, p256dh_key=p256dh, auth_key=auth
            )
        )


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
    _validate_webpush_endpoint(endpoint)
    player_ids = _player_ids_for_user(user, db)
    if player_ids:
        for player_id in player_ids:
            _save_subscription(db, player_id=player_id, user_id=None, endpoint=endpoint, p256dh=p256dh, auth=auth)
    else:
        _save_subscription(db, player_id=None, user_id=user.id, endpoint=endpoint, p256dh=p256dh, auth=auth)
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
    db.query(WebPushSubscription).filter(
        or_(
            WebPushSubscription.player_id.in_(player_ids) if player_ids else False,
            WebPushSubscription.user_id == user.id,
        )
    ).delete(synchronize_session="fetch")
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
    _validate_webpush_endpoint(endpoint)
    player_ids = _player_ids_for_user(user, db)
    if player_ids:
        for player_id in player_ids:
            _save_subscription(db, player_id=player_id, user_id=None, endpoint=endpoint, p256dh=p256dh, auth=auth)
    else:
        _save_subscription(db, player_id=None, user_id=user.id, endpoint=endpoint, p256dh=p256dh, auth=auth)
    db.commit()
    return JSONResponse({"status": "ok"})
