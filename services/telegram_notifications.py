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
    from models.notification import Notification  # noqa: PLC0415
    from models.notification_preference import NotificationPreference  # noqa: PLC0415
    from models.player import Player  # noqa: PLC0415
    from models.telegram_notification import TelegramNotification  # noqa: PLC0415
    from models.user_team import UserTeam  # noqa: PLC0415
    from services.channels.inapp_channel import push_unread_count, push_unread_count_to_user  # noqa: PLC0415
    from services.channels.webpush_channel import WebPushChannel  # noqa: PLC0415

    _webpush = WebPushChannel()

    db = _db_mod.SessionLocal()
    try:
        event = db.get(Event, event_id)
        if event is None:
            return
        player = db.get(Player, player_id)
        if player is None:
            return

        icon = {"present": "✓", "absent": "✗", "unknown": "?"}.get(new_status, "?")

        coaches = db.query(UserTeam).filter(UserTeam.team_id == event.team_id).all()
        seen_chat_ids: set[str] = set()

        for ut in coaches:
            if not (ut.user and ut.user.telegram_chat_id):
                continue
            if ut.user.telegram_chat_id in seen_chat_ids:
                continue
            seen_chat_ids.add(ut.user.telegram_chat_id)

            # Respect notification preference (check via linked player if exists)
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
                # Create TelegramNotification for bot UI state (inject_notification)
                tg_notif = TelegramNotification(
                    user_id=ut.user_id,
                    event_id=event_id,
                    player_id=player_id,
                    status=new_status,
                )
                db.add(tg_notif)
                db.flush()

                # Inject 🔔 button into persistent message (or send homepage if first time)
                await inject_notification(ut.user, tg_notif.id, _bot.telegram_app.bot, db)

                # edit_message_text is silent — separate message triggers phone push
                alert_text = f"🔔 {player.full_name} {icon} — {event.title}"
                await _bot.telegram_app.bot.send_message(
                    chat_id=ut.user.telegram_chat_id,
                    text=alert_text,
                )

                # Create unified Notification record for inbox + badge + SSE + web push.
                # Use player_id when coach has a linked player, user_id otherwise.
                web_notif = Notification(
                    player_id=coach_player.id if coach_player else None,
                    user_id=ut.user_id if coach_player is None else None,
                    event_id=event_id,
                    title=f"{icon} {player.full_name} → {new_status}",
                    body=event.title,
                    tag="direct",
                )
                db.add(web_notif)
                db.flush()

                # Push SSE badge update
                unread = (
                    db.query(Notification)
                    .filter(
                        Notification.player_id == coach_player.id
                        if coach_player
                        else Notification.user_id == ut.user_id,
                        Notification.is_read.is_(False),
                    )
                    .count()
                )
                if coach_player:
                    push_unread_count(coach_player.id, unread)
                    _webpush.send(coach_player, web_notif, db)
                else:
                    push_unread_count_to_user(ut.user_id, unread)
                    _webpush.send_to_user(ut.user_id, web_notif, db)

            except Exception as exc:
                logger.warning(
                    "notify_coaches_via_telegram: failed for user %s: %s",
                    ut.user_id,
                    exc,
                    exc_info=True,
                )

        db.commit()
    finally:
        db.close()
