"""services/chat_service.py — Event chat business logic."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from models.event import Event
from models.event_message import EventMessage
from models.player import Player
from models.player_team import PlayerTeam
from models.user import User
from services.channels.inapp_channel import push_payload

logger = logging.getLogger(__name__)


def author_display_name(user: User | None) -> str:
    """Return 'First Last', first name only, username, or 'Deleted user'."""
    if user is None:
        return "Deleted user"
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    if user.first_name:
        return user.first_name
    return user.username


def message_to_dict(msg: EventMessage, author_name: str) -> dict:
    """Serialise an EventMessage to a JSON-safe dict."""
    return {
        "id": msg.id,
        "event_id": msg.event_id,
        "lane": msg.lane,
        "body": msg.body,
        "author": author_name,
        "user_id": msg.user_id,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


def resolve_event_player_ids(event_id: int, db: Session) -> list[int]:
    """Return all active player_ids for the event's team (no attendance filter).

    Returns empty list if the event has no team_id.
    """
    event = db.get(Event, event_id)
    if event is None or event.team_id is None:
        return []
    rows = (
        db.query(PlayerTeam.player_id)
        .join(Player, Player.id == PlayerTeam.player_id)
        .filter(
            PlayerTeam.team_id == event.team_id,
            PlayerTeam.membership_status == "active",
            Player.is_active.is_(True),
            Player.archived_at.is_(None),
        )
        .all()
    )
    return [r[0] for r in rows]


def push_chat_message_sse(event_id: int, msg_dict: dict, db: Session) -> None:
    """Push a chat_message SSE event to all connected players for the event."""
    player_ids = resolve_event_player_ids(event_id, db)
    payload = {"type": "chat_message", "event_id": event_id, "message": msg_dict}
    for pid in player_ids:
        push_payload(pid, payload)


def push_chat_delete_sse(event_id: int, message_id: int, db: Session) -> None:
    """Push a chat_delete SSE event to all connected players for the event."""
    player_ids = resolve_event_player_ids(event_id, db)
    payload = {"type": "chat_delete", "event_id": event_id, "message_id": message_id}
    for pid in player_ids:
        push_payload(pid, payload)


async def send_telegram_notifications(
    event_id: int,
    author_name: str,
    lane: str,
    body: str,
    exclude_user_id: int | None,
) -> None:
    """Send Telegram push notifications for a new chat message.

    Targets: players with present/maybe/unknown attendance + coaches/admins
    linked to the event's team. Excludes the message author.
    Opens its own DB session — safe to call as a BackgroundTask.
    """
    try:
        import bot as _bot  # noqa: PLC0415

        if _bot.telegram_app is None:
            return
    except Exception:
        return

    from telegram import InlineKeyboardButton, InlineKeyboardMarkup  # noqa: PLC0415

    import app.database as _db_mod  # noqa: PLC0415
    from models.attendance import Attendance  # noqa: PLC0415
    from models.user_team import UserTeam  # noqa: PLC0415

    db = _db_mod.SessionLocal()
    try:
        event = db.get(Event, event_id)
        if event is None:
            return

        lane_label = "📢 Announcement" if lane == "announcement" else "💬 Discussion"
        text = f"{lane_label} — {event.title}\n{author_name}: {body}"

        chat_ids: set[str] = set()

        if event.team_id is not None:
            # Players with non-absent attendance
            att_rows = (
                db.query(Attendance)
                .filter(
                    Attendance.event_id == event_id,
                    Attendance.status.in_(["present", "maybe", "unknown"]),
                )
                .all()
            )
            for att in att_rows:
                player = db.get(Player, att.player_id)
                if player and player.user_id and player.user_id != exclude_user_id:
                    u = db.get(User, player.user_id)
                    if u and u.telegram_chat_id:
                        chat_ids.add(u.telegram_chat_id)

            # Coaches/admins linked to the event's team via UserTeam
            coach_rows = (
                db.query(UserTeam).filter(UserTeam.team_id == event.team_id).all()
            )
            for row in coach_rows:
                if row.user_id != exclude_user_id:
                    u = db.get(User, row.user_id)
                    if u and u.telegram_chat_id:
                        chat_ids.add(u.telegram_chat_id)

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💬 Reply",
                        callback_data=f"chatreply:{event_id}:discussion",
                    )
                ]
            ]
        )

        for chat_id in chat_ids:
            try:
                await _bot.telegram_app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=keyboard,
                )
            except Exception:
                logger.warning(
                    "Failed to send Telegram chat notification to %s", chat_id
                )
    finally:
        db.close()
