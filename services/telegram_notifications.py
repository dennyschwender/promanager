"""services/telegram_notifications.py — Telegram notifications for attendance changes."""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def notify_coaches_via_telegram(
    event_id: int,
    player_id: int,
    new_status: str,
) -> None:
    """Send/update Telegram alert to coaches/admins via single pinned notification."""
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
                # Build notification text (latest only)
                text = f"📬 {player_name} → {new_status}\n{event.title} · {date_str}"
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("👁 View Event", callback_data=f"evt:{event_id}"),
                ]])

                # Check if coach already has a pinned notification message
                if ut.user.telegram_notification_message_id:
                    # Edit existing message with latest notification
                    try:
                        await _bot.telegram_app.bot.edit_message_text(
                            chat_id=ut.user.telegram_chat_id,
                            message_id=ut.user.telegram_notification_message_id,
                            text=text,
                            reply_markup=keyboard,
                        )
                    except Exception as edit_exc:
                        # Message deleted or expired: send new one
                        logger.debug("Could not edit notification message, sending new: %s", edit_exc)
                        await _send_new_notification(
                            _bot, ut.user.telegram_chat_id, ut.user_id, text, keyboard, db
                        )
                else:
                    # First notification: send new message
                    await _send_new_notification(
                        _bot, ut.user.telegram_chat_id, ut.user_id, text, keyboard, db
                    )

                sent_chat_ids.add(ut.user.telegram_chat_id)

            except Exception as exc:
                logger.warning(
                    "notify_coaches_via_telegram: failed for user %s: %s",
                    ut.user_id, exc, exc_info=True,
                )
    finally:
        db.close()


async def _send_new_notification(bot_app, chat_id: str, user_id: int, text: str, keyboard, db) -> None:
    """Send a new notification message and store its ID."""
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
