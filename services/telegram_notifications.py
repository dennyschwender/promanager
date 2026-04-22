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
    """Send Telegram message to coaches/admins of event's team when player changes status."""
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
        text = f"📋 {player_name} → {new_status}\n{event.title} · {date_str}"

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("👁 View Event", callback_data=f"evt:{event_id}"),
        ]])

        coaches = db.query(UserTeam).filter(UserTeam.team_id == event.team_id).all()
        sent_chat_ids: set[str] = set()
        for ut in coaches:
            if ut.user and ut.user.telegram_chat_id and ut.user.telegram_chat_id not in sent_chat_ids:
                try:
                    await _bot.telegram_app.bot.send_message(
                        chat_id=ut.user.telegram_chat_id,
                        text=text,
                        reply_markup=keyboard,
                    )
                    sent_chat_ids.add(ut.user.telegram_chat_id)
                except Exception as exc:
                    logger.warning(
                        "notify_coaches_via_telegram: failed for user %s: %s",
                        ut.user_id, exc, exc_info=True,
                    )
    finally:
        db.close()
