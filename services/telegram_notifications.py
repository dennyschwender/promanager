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
    """Send Telegram alert to coaches/admins about attendance change."""
    import bot as _bot  # noqa: PLC0415

    if _bot.telegram_app is None:
        return

    import app.database as _db_mod  # noqa: PLC0415
    from models.event import Event  # noqa: PLC0415
    from models.notification_preference import NotificationPreference  # noqa: PLC0415
    from models.player import Player  # noqa: PLC0415
    from models.telegram_notification import TelegramNotification  # noqa: PLC0415
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

        seen_chat_ids: set[str] = set()
        for ut in coaches:
            if not (ut.user and ut.user.telegram_chat_id):
                continue
            if ut.user.telegram_chat_id in seen_chat_ids:
                continue
            seen_chat_ids.add(ut.user.telegram_chat_id)

            # Bug 2 fix: check NotificationPreference for the coach's linked player.
            # A coach user may have a linked Player record; if so, respect their telegram
            # preference. If no player record or no preference row exists, default to enabled.
            coach_player = ut.user.players[0] if ut.user.players else None
            if coach_player is not None:
                pref = (
                    db.query(NotificationPreference)
                    .filter(
                        NotificationPreference.player_id == coach_player.id,
                        NotificationPreference.channel == "telegram",
                    )
                    .first()
                )
                if pref is not None and not pref.enabled:
                    continue

            try:
                # Bug 1 fix: delete the previously stored notification message before
                # sending a new one, so rapid notifications don't pile up in chat.
                if ut.user.telegram_notification_message_id is not None:
                    try:
                        await _bot.telegram_app.bot.delete_message(
                            chat_id=ut.user.telegram_chat_id,
                            message_id=ut.user.telegram_notification_message_id,
                        )
                    except Exception:
                        pass  # message may already be gone or too old
                    ut.user.telegram_notification_message_id = None
                    db.commit()

                # Create notification record in DB
                notif = TelegramNotification(
                    user_id=ut.user_id,
                    event_id=event_id,
                    player_id=player_id,
                    status=new_status,
                )
                db.add(notif)
                db.commit()

                # Build notification text
                text = f"📬 {player_name} → {new_status}\n{event.title} · {date_str}"
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("👁 View Event", callback_data=f"evt:{event_id}"),
                ]])

                # Send as new message (will be cleared when user navigates)
                msg = await _bot.telegram_app.bot.send_message(
                    chat_id=ut.user.telegram_chat_id,
                    text=text,
                    reply_markup=keyboard,
                )
                # Store message ID on user for cleanup on next nav action
                ut.user.telegram_notification_message_id = msg.message_id
                db.commit()

            except Exception as exc:
                logger.warning(
                    "notify_coaches_via_telegram: failed for user %s: %s",
                    ut.user_id, exc, exc_info=True,
                )
    finally:
        db.close()
