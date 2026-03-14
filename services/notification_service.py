"""services/notification_service.py — Notification dispatch orchestration."""
from __future__ import annotations

import logging

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from models.attendance import Attendance
from models.notification import Notification
from models.notification_preference import CHANNELS, NotificationPreference
from models.player import Player
from services.channels.email_channel import EmailChannel
from services.channels.inapp_channel import InAppChannel

logger = logging.getLogger(__name__)

_email_channel = EmailChannel()
_inapp_channel = InAppChannel()


# ── Preference helpers ────────────────────────────────────────────────────────

def create_default_preferences(player_id: int, db: Session) -> None:
    """Create enabled preferences for all channels if they don't exist."""
    for channel in CHANNELS:
        existing = (
            db.query(NotificationPreference)
            .filter(
                NotificationPreference.player_id == player_id,
                NotificationPreference.channel == channel,
            )
            .first()
        )
        if existing is None:
            db.add(NotificationPreference(player_id=player_id, channel=channel, enabled=True))
    db.commit()


def get_preference(player_id: int, channel: str, db: Session) -> bool:
    """Return True if the player has the channel enabled (defaults to True if missing)."""
    pref = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.player_id == player_id,
            NotificationPreference.channel == channel,
        )
        .first()
    )
    return pref.enabled if pref is not None else True


# ── Recipient resolution ──────────────────────────────────────────────────────

def _resolve_players(event, recipient_statuses: list[str] | None, db: Session) -> list[Player]:
    """Return the list of players to notify."""
    if event.team_id is not None:
        from models.player_team import PlayerTeam  # noqa: PLC0415
        base_q = (
            db.query(Player)
            .join(PlayerTeam, PlayerTeam.player_id == Player.id)
            .filter(
                PlayerTeam.team_id == event.team_id,
                PlayerTeam.membership_status == "active",
                Player.is_active.is_(True),
            )
        )
    else:
        base_q = db.query(Player).filter(Player.is_active.is_(True))

    if not recipient_statuses:
        return base_q.all()

    # Filter by attendance status
    player_ids_with_status = (
        db.query(Attendance.player_id)
        .filter(
            Attendance.event_id == event.id,
            Attendance.status.in_(recipient_statuses),
        )
        .subquery()
    )
    return base_q.filter(Player.id.in_(player_ids_with_status)).all()


# ── Core dispatch ─────────────────────────────────────────────────────────────

def _dispatch(
    player_ids: list[int],
    event_id: int | None,
    title: str,
    body: str,
    tag: str,
    admin_channels: list[str],
) -> int:
    """Create notification rows and dispatch to channels. Opens its own DB session.

    Called either synchronously (tests) or as a FastAPI BackgroundTask.
    Never receives a request-scoped session — those are closed before
    background tasks run.
    """
    import app.database as _db_mod  # noqa: PLC0415
    from services.channels.webpush_channel import WebPushChannel  # noqa: PLC0415
    _webpush_channel = WebPushChannel()

    db = _db_mod.SessionLocal()
    try:
        queued = 0
        for player_id in player_ids:
            player = db.get(Player, player_id)
            if player is None:
                continue

            notif = Notification(
                player_id=player.id,
                event_id=event_id,
                title=title,
                body=body,
                tag=tag,
            )
            db.add(notif)
            db.flush()

            # Count unread for SSE badge
            unread = (
                db.query(Notification)
                .filter(
                    Notification.player_id == player.id,
                    Notification.is_read.is_(False),
                )
                .count()
            )

            if "inapp" in admin_channels and get_preference(player.id, "inapp", db):
                _inapp_channel.send(player, notif, unread_count=unread)

            if "email" in admin_channels and get_preference(player.id, "email", db):
                _email_channel.send(player, notif)

            if "webpush" in admin_channels and get_preference(player.id, "webpush", db):
                _webpush_channel.send(player, notif, db=db)

            queued += 1

        db.commit()
        return queued
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def send_notifications(
    *,
    event,
    title: str,
    body: str,
    tag: str,
    recipient_statuses: list[str] | None,
    admin_channels: list[str],
    db: Session,
    background_tasks: BackgroundTasks | None,
) -> dict:
    """Resolve players, then dispatch channels.

    Player IDs are resolved synchronously (within the request session).
    Actual dispatch (_dispatch) always opens its own session — safe whether
    called synchronously (tests, background_tasks=None) or as a BackgroundTask
    (where the request session is already closed).
    """
    players = _resolve_players(event, recipient_statuses, db)
    if not players:
        return {"queued": 0}

    player_ids = [p.id for p in players]
    event_id = event.id if event else None

    if background_tasks is not None:
        background_tasks.add_task(
            _dispatch, player_ids, event_id, title, body, tag, admin_channels
        )
        return {"queued": len(player_ids)}
    else:
        count = _dispatch(player_ids, event_id, title, body, tag, admin_channels)
        return {"queued": count}
