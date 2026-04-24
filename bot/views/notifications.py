"""bot/views/notifications.py — Notification view renderers."""
from __future__ import annotations

import math

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import t
from bot.views import ViewResult
from models.player import Player

NOTIF_PAGE_SIZE = 5


def render_notifications_list(user, db, page: int = 0) -> ViewResult:
    from models.notification import Notification  # noqa: PLC0415
    from models.telegram_notification import TelegramNotification  # noqa: PLC0415

    locale = user.locale or "en"
    is_admin_or_coach = user.is_admin or user.is_coach

    if is_admin_or_coach:
        notifs = (
            db.query(TelegramNotification)
            .filter(TelegramNotification.user_id == user.id)
            .order_by(TelegramNotification.created_at.desc())
            .all()
        )
        if not notifs:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home"),
            ]])
            return t("telegram.no_events", locale), keyboard

        total_pages = max(1, math.ceil(len(notifs) / NOTIF_PAGE_SIZE))
        page = max(0, min(page, total_pages - 1))
        page_notifs = notifs[page * NOTIF_PAGE_SIZE : (page + 1) * NOTIF_PAGE_SIZE]

        text_lines = ["🔔 Recent Notifications:"]
        rows = []
        for notif in page_notifs:
            player_name = notif.player.full_name if notif.player else f"Player {notif.player_id}"
            event_title = notif.event.title if notif.event else "Event"
            icon = {"present": "✓", "absent": "✗", "unknown": "?"}.get(notif.status, "?")
            text_lines.append(f"{icon} {player_name} → {notif.status}")
            rows.append([InlineKeyboardButton(
                f"👁 {event_title}",
                callback_data=f"n:{notif.id}",
            )])
    else:
        linked_player = db.query(Player).filter(
            Player.user_id == user.id, Player.archived_at.is_(None)
        ).first()
        if linked_player is None:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home"),
            ]])
            return t("telegram.no_events", locale), keyboard

        notifs = (
            db.query(Notification)
            .filter(Notification.player_id == linked_player.id)
            .order_by(Notification.created_at.desc())
            .all()
        )
        if not notifs:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home"),
            ]])
            return t("telegram.no_events", locale), keyboard

        db.query(Notification).filter(
            Notification.player_id == linked_player.id,
            Notification.is_read.is_(False),
        ).update({"is_read": True})
        db.commit()

        total_pages = max(1, math.ceil(len(notifs) / NOTIF_PAGE_SIZE))
        page = max(0, min(page, total_pages - 1))
        page_notifs = notifs[page * NOTIF_PAGE_SIZE : (page + 1) * NOTIF_PAGE_SIZE]

        text_lines = ["🔔 Notifications:"]
        rows = []
        for notif in page_notifs:
            event = notif.event
            event_date = str(event.event_date) if event else ""
            header = f"*{notif.title}*"
            if event_date:
                header += f" ({event_date})"
            text_lines.append(header)
            text_lines.append(notif.body)
            if event:
                rows.append([InlineKeyboardButton(
                    f"👁 {event.title}",
                    callback_data=f"e:{notif.event_id}",
                )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("← Prev", callback_data=f"nl:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next →", callback_data=f"nl:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home")])

    return "\n".join(text_lines), InlineKeyboardMarkup(rows)


def render_notification_detail(user, db, notif_id: int) -> ViewResult:
    """Show a single TelegramNotification with link to its event."""
    from models.telegram_notification import TelegramNotification  # noqa: PLC0415

    locale = user.locale or "en"
    notif = db.get(TelegramNotification, notif_id)
    if notif is None or notif.user_id != user.id:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(t("telegram.back_button", locale), callback_data="nl"),
        ]])
        return "Notification not found.", keyboard

    player_name = notif.player.full_name if notif.player else f"Player {notif.player_id}"
    event = notif.event
    event_title = event.title if event else "Event"
    event_date = str(event.event_date) if event else ""
    icon = {"present": "✓", "absent": "✗", "unknown": "?"}.get(notif.status, "?")
    ts = notif.created_at.strftime("%d %b %H:%M") if notif.created_at else ""

    text = f"📬 *{player_name}* {icon} → {notif.status}\n*{event_title}*"
    if event_date:
        text += f"\n{event_date}"
    if ts:
        text += f"\n_{ts}_"

    rows = []
    if event:
        rows.append([InlineKeyboardButton(f"📅 {event_title}", callback_data=f"e:{notif.event_id}")])
    rows.append([InlineKeyboardButton(t("telegram.back_button", locale), callback_data="nl")])

    return text, InlineKeyboardMarkup(rows)
