"""services/telegram_notifications.py — Telegram notifications for attendance changes."""
from __future__ import annotations

import logging

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
    from bot.navigation import inject_notification  # noqa: PLC0415
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

        coaches = db.query(UserTeam).filter(UserTeam.team_id == event.team_id).all()
        seen_chat_ids: set[str] = set()

        for ut in coaches:
            if not (ut.user and ut.user.telegram_chat_id):
                continue
            if ut.user.telegram_chat_id in seen_chat_ids:
                continue
            seen_chat_ids.add(ut.user.telegram_chat_id)

            # Respect notification preference
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
                # Create notification record
                notif = TelegramNotification(
                    user_id=ut.user_id,
                    event_id=event_id,
                    player_id=player_id,
                    status=new_status,
                )
                db.add(notif)
                db.flush()  # get notif.id before inject_notification

                # Inject 🔔 button into persistent message (or send homepage if first time)
                await inject_notification(ut.user, notif.id, _bot.telegram_app.bot, db)

            except Exception as exc:
                logger.warning(
                    "notify_coaches_via_telegram: failed for user %s: %s",
                    ut.user_id, exc, exc_info=True,
                )

        db.commit()
    finally:
        db.close()
