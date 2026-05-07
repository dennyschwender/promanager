"""services/telegram_notifications.py — Telegram + web notifications for attendance changes."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def notify_coaches_attendance_change(
    event_id: int,
    player_id: int,
    new_status: str,
) -> None:
    """Send attendance change notification to all coaches for the event's team.

    Notifies via Telegram (for coaches with a bot account) AND creates
    Notification records / pushes SSE + web push for ALL coaches regardless
    of whether they have Telegram configured.
    """
    import app.database as _db_mod  # noqa: PLC0415
    import bot as _bot  # noqa: PLC0415
    from bot.navigation import inject_notification  # noqa: PLC0415
    from models.event import Event  # noqa: PLC0415
    from models.notification import Notification  # noqa: PLC0415
    from models.notification_preference import NotificationPreference  # noqa: PLC0415
    from models.player import Player  # noqa: PLC0415
    from models.telegram_notification import TelegramNotification  # noqa: PLC0415
    from models.user_team import UserTeam  # noqa: PLC0415
    from services.channels.inapp_channel import push_unread_count, push_unread_count_to_user  # noqa: PLC0415
    from services.channels.webpush_channel import WebPushChannel  # noqa: PLC0415

    has_bot = _bot.telegram_app is not None
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
        notif_title = f"{icon} {player.full_name} → {new_status}"
        notif_body = event.title
        tg_alert = f"🔔 {player.full_name} {icon} — {event.title}"

        coaches = db.query(UserTeam).filter(UserTeam.team_id == event.team_id).all()
        seen_user_ids: set[int] = set()
        seen_telegram_ids: set[str] = set()

        for ut in coaches:
            if not ut.user:
                continue
            if ut.user_id in seen_user_ids:
                continue
            seen_user_ids.add(ut.user_id)

            coach_player = ut.user.players[0] if ut.user.players else None
            has_telegram = (
                has_bot and bool(ut.user.telegram_chat_id) and ut.user.telegram_chat_id not in seen_telegram_ids
            )

            # Telegram preference check (only gates telegram, not web channels)
            telegram_enabled = True
            if has_telegram and coach_player is not None:
                pref = (
                    db.query(NotificationPreference)
                    .filter(
                        NotificationPreference.player_id == coach_player.id,
                        NotificationPreference.channel == "telegram",
                    )
                    .first()
                )
                if pref is not None and not pref.enabled:
                    telegram_enabled = False

            if has_telegram and telegram_enabled:
                seen_telegram_ids.add(ut.user.telegram_chat_id)

            try:
                # ── Telegram channel ──────────────────────────────────────
                if has_telegram and telegram_enabled:
                    tg_notif = TelegramNotification(
                        user_id=ut.user_id,
                        event_id=event_id,
                        player_id=player_id,
                        status=new_status,
                    )
                    db.add(tg_notif)
                    db.flush()
                    await inject_notification(ut.user, tg_notif.id, _bot.telegram_app.bot, db)
                    await _bot.telegram_app.bot.send_message(
                        chat_id=ut.user.telegram_chat_id,
                        text=tg_alert,
                    )

                # ── Unified web/in-app/web-push (ALL coaches) ─────────────
                web_notif = Notification(
                    player_id=coach_player.id if coach_player else None,
                    user_id=ut.user_id if not coach_player else None,
                    event_id=event_id,
                    title=notif_title,
                    body=notif_body,
                    tag="direct",
                )
                db.add(web_notif)
                db.flush()

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
                    from services.channels.email_channel import EmailChannel  # noqa: PLC0415
                    from services.notification_service import get_preference  # noqa: PLC0415
                    if get_preference(coach_player.id, "email", db):
                        EmailChannel().send(coach_player, web_notif)
                else:
                    push_unread_count_to_user(ut.user_id, unread)
                    _webpush.send_to_user(ut.user_id, web_notif, db)

            except Exception as exc:
                logger.warning(
                    "notify_coaches_attendance_change: failed for user %s: %s",
                    ut.user_id,
                    exc,
                    exc_info=True,
                )

        db.commit()
    finally:
        db.close()


async def notify_coaches_about_external_change(
    event_id: int,
    ext_id: int,
    new_status: str,
) -> None:
    """Send external-player attendance change notification to all coaches."""
    import app.database as _db_mod  # noqa: PLC0415
    import bot as _bot  # noqa: PLC0415
    from models.event import Event  # noqa: PLC0415
    from models.event_external import EventExternal  # noqa: PLC0415
    from models.notification import Notification  # noqa: PLC0415
    from models.notification_preference import NotificationPreference  # noqa: PLC0415
    from models.user_team import UserTeam  # noqa: PLC0415
    from services.channels.inapp_channel import push_unread_count, push_unread_count_to_user  # noqa: PLC0415
    from services.channels.webpush_channel import WebPushChannel  # noqa: PLC0415

    has_bot = _bot.telegram_app is not None
    _webpush = WebPushChannel()

    db = _db_mod.SessionLocal()
    try:
        event = db.get(Event, event_id)
        if event is None:
            return
        ext = db.get(EventExternal, ext_id)
        if ext is None:
            return

        icon = {"present": "✓", "absent": "✗", "unknown": "?"}.get(new_status, "?")
        notif_title = f"{icon} {ext.full_name} (ext) → {new_status}"
        notif_body = event.title
        tg_alert = f"🔔 {ext.full_name} (ext) {icon} — {event.title}"

        coaches = db.query(UserTeam).filter(UserTeam.team_id == event.team_id).all()
        seen_user_ids: set[int] = set()
        seen_telegram_ids: set[str] = set()

        for ut in coaches:
            if not ut.user:
                continue
            if ut.user_id in seen_user_ids:
                continue
            seen_user_ids.add(ut.user_id)

            coach_player = ut.user.players[0] if ut.user.players else None
            has_telegram = (
                has_bot and bool(ut.user.telegram_chat_id) and ut.user.telegram_chat_id not in seen_telegram_ids
            )

            telegram_enabled = True
            if has_telegram and coach_player is not None:
                pref = (
                    db.query(NotificationPreference)
                    .filter(
                        NotificationPreference.player_id == coach_player.id,
                        NotificationPreference.channel == "telegram",
                    )
                    .first()
                )
                if pref is not None and not pref.enabled:
                    telegram_enabled = False

            if has_telegram and telegram_enabled:
                seen_telegram_ids.add(ut.user.telegram_chat_id)

            try:
                if has_telegram and telegram_enabled:
                    await _bot.telegram_app.bot.send_message(
                        chat_id=ut.user.telegram_chat_id,
                        text=tg_alert,
                    )

                web_notif = Notification(
                    player_id=coach_player.id if coach_player else None,
                    user_id=ut.user_id if not coach_player else None,
                    event_id=event_id,
                    title=notif_title,
                    body=notif_body,
                    tag="direct",
                )
                db.add(web_notif)
                db.flush()

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
                    from services.channels.email_channel import EmailChannel  # noqa: PLC0415
                    from services.notification_service import get_preference  # noqa: PLC0415
                    if get_preference(coach_player.id, "email", db):
                        EmailChannel().send(coach_player, web_notif)
                else:
                    push_unread_count_to_user(ut.user_id, unread)
                    _webpush.send_to_user(ut.user_id, web_notif, db)

            except Exception as exc:
                logger.warning(
                    "notify_coaches_about_external_change: failed for user %s: %s",
                    ut.user_id,
                    exc,
                    exc_info=True,
                )

        db.commit()
    finally:
        db.close()
