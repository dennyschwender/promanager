"""bot/navigation.py — Persistent message navigation and notification injection."""
from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)


async def navigate(query, user, db, view_key: str, text: str, keyboard: InlineKeyboardMarkup) -> None:
    """Edit the persistent message to show a new view and update the view state."""
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    except Exception:
        await query.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    user.telegram_current_view = view_key
    db.commit()


async def inject_notification(user, notif_id: int, bot, db) -> None:
    """Inject a 🔔 button into the current view when a new notification arrives.

    If user has no persistent message yet, sends the homepage as the first message.
    """
    if not user.telegram_chat_id:
        return

    if user.telegram_notification_message_id is None:
        # No persistent message yet — send homepage first
        from bot.views.home import render_home  # noqa: PLC0415
        text, keyboard = render_home(user, db)
        try:
            msg = await bot.send_message(
                chat_id=user.telegram_chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN,
            )
            user.telegram_notification_message_id = msg.message_id
            user.telegram_current_view = "home"
            db.commit()
        except Exception as exc:
            logger.warning("inject_notification: failed to send homepage for user %s: %s", user.id, exc)
            return

    # Re-render current view with 🔔 button injected
    text, keyboard = _rerender_current_view(user, db, notif_id)
    try:
        await bot.edit_message_text(
            chat_id=user.telegram_chat_id,
            message_id=user.telegram_notification_message_id,
            text=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as exc:
        logger.warning("inject_notification: failed to edit message for user %s: %s", user.id, exc)


def _rerender_current_view(user, db, notif_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Re-render the current view and prepend a 🔔 notification button."""
    view_key = user.telegram_current_view or "home"
    text, keyboard = _render_view(user, db, view_key)

    preview = _notif_preview(user, db, notif_id)
    notif_row = [InlineKeyboardButton(f"🔔 {preview}", callback_data=f"n:{notif_id}")]

    new_rows = [notif_row] + list(keyboard.inline_keyboard)
    new_keyboard = InlineKeyboardMarkup(new_rows)
    return text, new_keyboard


def _render_view(user, db, view_key: str) -> tuple[str, InlineKeyboardMarkup]:
    """Dispatch view key string to the appropriate renderer."""
    from bot.views.home import render_home  # noqa: PLC0415
    from bot.views.events import render_events_list, render_event_detail, render_event_chat  # noqa: PLC0415
    from bot.views.notifications import render_notifications_list, render_notification_detail  # noqa: PLC0415
    from bot.views.other import render_other  # noqa: PLC0415

    locale = user.locale or "en"

    if view_key == "home":
        return render_home(user, db)
    if view_key == "nl":
        return render_notifications_list(user, db, 0)
    if view_key.startswith("nl:"):
        page = int(view_key.split(":")[1])
        return render_notifications_list(user, db, page)
    if view_key.startswith("n:"):
        return render_notification_detail(user, db, int(view_key.split(":")[1]))
    if view_key == "el":
        return render_events_list(user, db, 0)
    if view_key.startswith("el:"):
        page = int(view_key.split(":")[1])
        return render_events_list(user, db, page)
    if view_key.startswith("e:"):
        return render_event_detail(user, db, int(view_key.split(":")[1]))
    if view_key.startswith("ec:"):
        return render_event_chat(user, db, int(view_key.split(":")[1]))
    if view_key in ("ab", "other"):
        return render_other(user, locale)
    # Fallback
    return render_home(user, db)


def _notif_preview(user, db, notif_id: int) -> str:
    """Short text for the 🔔 button label (max ~30 chars)."""
    from models.telegram_notification import TelegramNotification  # noqa: PLC0415

    notif = db.get(TelegramNotification, notif_id)
    if notif is None:
        return "New notification"
    player_name = notif.player.full_name if notif.player else "Player"
    icon = {"present": "✓", "absent": "✗", "unknown": "?"}.get(notif.status, "?")
    preview = f"{player_name} {icon}"
    return preview[:30]


async def inject_chat_notification(user, event_id: int, event_title: str, bot, db) -> None:
    """Inject a 💬 chat button into the user's persistent message."""
    if not user.telegram_chat_id:
        return

    if user.telegram_notification_message_id is None:
        from bot.views.home import render_home  # noqa: PLC0415
        text, keyboard = render_home(user, db)
        try:
            msg = await bot.send_message(
                chat_id=user.telegram_chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN,
            )
            user.telegram_notification_message_id = msg.message_id
            user.telegram_current_view = "home"
            db.commit()
        except Exception as exc:
            logger.warning("inject_chat_notification: failed to send homepage for user %s: %s", user.id, exc)
            return

    view_key = user.telegram_current_view or "home"
    text, keyboard = _render_view(user, db, view_key)

    label = f"💬 {event_title[:28]}"
    chat_row = [InlineKeyboardButton(label, callback_data=f"ec:{event_id}")]
    new_rows = [chat_row] + list(keyboard.inline_keyboard)
    new_keyboard = InlineKeyboardMarkup(new_rows)

    try:
        await bot.edit_message_text(
            chat_id=user.telegram_chat_id,
            message_id=user.telegram_notification_message_id,
            text=text,
            reply_markup=new_keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as exc:
        logger.warning("inject_chat_notification: failed to edit message for user %s: %s", user.id, exc)
