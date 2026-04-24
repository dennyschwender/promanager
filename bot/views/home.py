"""bot/views/home.py — Homepage view renderer."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import t
from app.config import settings
from bot.views import ViewResult


def render_home(user, db) -> ViewResult:
    from models.notification import Notification  # noqa: PLC0415
    from models.player import Player  # noqa: PLC0415
    from models.telegram_notification import TelegramNotification  # noqa: PLC0415

    locale = user.locale or "en"
    is_admin_or_coach = user.is_admin or user.is_coach

    last_notif_text: str | None = None
    last_notif_ts: str | None = None

    if is_admin_or_coach:
        notif = (
            db.query(TelegramNotification)
            .filter(TelegramNotification.user_id == user.id)
            .order_by(TelegramNotification.created_at.desc())
            .first()
        )
        if notif:
            player = notif.player
            player_name = player.full_name if player else f"Player {notif.player_id}"
            event = notif.event
            event_title = event.title if event else "Event"
            icon = {"present": "✓", "absent": "✗", "unknown": "?"}.get(notif.status, "?")
            last_notif_text = f"{icon} {player_name} → {notif.status}\n{event_title}"
            if notif.created_at:
                last_notif_ts = notif.created_at.strftime("%d %b %H:%M")
    else:
        linked_player = db.query(Player).filter(
            Player.user_id == user.id, Player.archived_at.is_(None)
        ).first()
        if linked_player:
            notif = (
                db.query(Notification)
                .filter(Notification.player_id == linked_player.id)
                .order_by(Notification.created_at.desc())
                .first()
            )
            if notif:
                body = notif.body[:200] + "…" if len(notif.body) > 200 else notif.body
                last_notif_text = f"*{notif.title}*\n{body}"
                if notif.created_at:
                    last_notif_ts = notif.created_at.strftime("%d %b %H:%M")

    parts = [f"🏠 *{settings.APP_NAME}*\n"]
    if last_notif_text:
        parts.append("📣 Last notification:")
        parts.append(last_notif_text)
        if last_notif_ts:
            parts.append(f"_{last_notif_ts}_")
    else:
        parts.append("_No notifications yet_")

    text = "\n".join(parts)
    keyboard = _home_keyboard(locale)
    return text, keyboard


def _home_keyboard(locale: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("telegram.notifications_button", locale), callback_data="nl"),
            InlineKeyboardButton(t("telegram.events_button", locale), callback_data="el"),
        ],
        [
            InlineKeyboardButton(t("telegram.other_button", locale), callback_data="other:0"),
        ],
    ])
