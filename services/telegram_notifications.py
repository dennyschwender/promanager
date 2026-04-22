"""services/telegram_notifications.py — Telegram notifications for attendance changes."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def notify_coaches_via_telegram(
    event_id: int,
    player_id: int,
    new_status: str,
) -> None:
    """Send Telegram alert to coaches/admins via pinned notification summary."""
    import bot as _bot  # noqa: PLC0415

    if _bot.telegram_app is None:
        return

    import app.database as _db_mod  # noqa: PLC0415
    from models.event import Event  # noqa: PLC0415
    from models.player import Player  # noqa: PLC0415
    from models.user_team import UserTeam  # noqa: PLC0415

    db = _db_mod.SessionLocal()
    try:
        event = db.get(Event, event_id)
        if event is None:
            return
        player = db.get(Player, player_id)
        if player is None:
            return

        player_name = f"{player.first_name} {player.last_name}".strip() or f"Player {player_id}"
        date_str = event.event_date.strftime("%d %b") if event.event_date else ""

        coaches = db.query(UserTeam).filter(UserTeam.team_id == event.team_id).all()
        sent_chat_ids: set[str] = set()

        for ut in coaches:
            if not (ut.user and ut.user.telegram_chat_id and ut.user.telegram_chat_id not in sent_chat_ids):
                continue

            try:
                # Build notification text
                notif_line = f"📋 {player_name} → {new_status} ({event.title} · {date_str})"

                # Check if coach already has a pinned notification message
                if ut.user.telegram_notification_message_id:
                    # Edit existing message: fetch it first to append
                    try:
                        msg = await _bot.telegram_app.bot.get_message(
                            chat_id=ut.user.telegram_chat_id,
                            message_id=ut.user.telegram_notification_message_id,
                        )
                        # Parse existing text and append new notification
                        existing_text = msg.text or ""
                        # Keep last 5 notifications (rough limit by line count)
                        lines = existing_text.split("\n")
                        # Remove old header if present
                        if lines and lines[0].startswith("📬"):
                            lines = lines[1:]
                        # Keep only recent notifications (last 4 + new one = 5 total)
                        lines = lines[-4:] if lines else []
                        lines.append(notif_line)
                        updated_text = "📬 Recent Notifications:\n" + "\n".join(lines)

                        # Edit message with updated notifications + button
                        keyboard = InlineKeyboardMarkup([[
                            InlineKeyboardButton("👁 View Event", callback_data=f"evt:{event_id}"),
                        ]])
                        await _bot.telegram_app.bot.edit_message_text(
                            chat_id=ut.user.telegram_chat_id,
                            message_id=ut.user.telegram_notification_message_id,
                            text=updated_text,
                            reply_markup=keyboard,
                        )
                    except Exception as edit_exc:
                        # Message deleted or expired: send new one
                        logger.debug("Could not edit notification message, sending new: %s", edit_exc)
                        await _send_new_notification(
                            _bot, ut.user.telegram_chat_id, ut.user_id, notif_line, event_id, db
                        )
                else:
                    # First notification: send new message
                    await _send_new_notification(
                        _bot, ut.user.telegram_chat_id, ut.user_id, notif_line, event_id, db
                    )

                sent_chat_ids.add(ut.user.telegram_chat_id)

            except Exception as exc:
                logger.warning(
                    "notify_coaches_via_telegram: failed for user %s: %s",
                    ut.user_id, exc, exc_info=True,
                )
    finally:
        db.close()


async def _send_new_notification(bot_app, chat_id: str, user_id: int, notif_line: str, event_id: int, db) -> None:
    """Send a new notification message and store its ID."""
    text = "📬 Recent Notifications:\n" + notif_line
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("👁 View Event", callback_data=f"evt:{event_id}"),
    ]])

    msg = await bot_app.telegram_app.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=keyboard,
    )

    # Store message ID for future updates
    from models.user import User  # noqa: PLC0415
    user = db.get(User, user_id)
    if user:
        user.telegram_notification_message_id = msg.message_id
        db.commit()
