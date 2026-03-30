"""bot/handlers.py — Telegram bot command and callback handlers."""

from __future__ import annotations

import logging
import math
from datetime import datetime

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.database import SessionLocal
from app.i18n import t
from bot.keyboards import (
    PAGE_SIZE,
    PLAYER_PAGE_SIZE,
    event_admin_keyboard,
    event_status_keyboard,
    events_keyboard,
)
from models.attendance import Attendance
from models.event import Event
from models.player import Player
from services.attendance_service import set_attendance
from services.telegram_service import (
    AuthResult,
    find_user_by_phone,
    get_user_by_chat_id,
    link_telegram,
    normalize_phone,
    unlink_telegram,
)

logger = logging.getLogger(__name__)

# Status char → full status string
_STATUS_MAP = {"p": "present", "a": "absent", "u": "unknown"}


def _locale(user) -> str:
    return user.locale if user and user.locale else "en"


async def _send_events_list(message, user, db) -> None:
    """Send the upcoming events list as a new message with inline keyboard."""
    locale = _locale(user)
    today = datetime.today().date()
    all_upcoming = (
        db.query(Event)
        .filter(Event.event_date >= today)
        .order_by(Event.event_date.asc())
        .all()
    )
    if not all_upcoming:
        await message.reply_text(t("telegram.no_events", locale))
        return
    total_pages = max(1, math.ceil(len(all_upcoming) / PAGE_SIZE))
    page_events = all_upcoming[:PAGE_SIZE]
    header = t("telegram.events_header", locale, page=1)
    keyboard = events_keyboard(page_events, 0, total_pages, locale=locale)
    await message.reply_text(header, reply_markup=keyboard)


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    with SessionLocal() as db:
        user = get_user_by_chat_id(db, chat_id)
        if user is not None:
            locale = _locale(user)
            await update.message.reply_text(
                t("telegram.auth_already_this", locale, username=user.username),
                reply_markup=ReplyKeyboardRemove(),
            )
            await _send_events_list(update.message, user, db)
            return

    # Not authenticated — ask for phone
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton(t("telegram.share_phone_button", "en"), request_contact=True)]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )
    await update.message.reply_text(
        t("telegram.welcome", "en"),
        reply_markup=keyboard,
    )


# ---------------------------------------------------------------------------
# /refresh
# ---------------------------------------------------------------------------


async def handle_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    with SessionLocal() as db:
        user = get_user_by_chat_id(db, chat_id)
        if user is None:
            await update.message.reply_text(t("telegram.not_authenticated", "en"))
            return
        await _send_events_list(update.message, user, db)


# ---------------------------------------------------------------------------
# /logout
# ---------------------------------------------------------------------------


async def handle_logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    with SessionLocal() as db:
        user = get_user_by_chat_id(db, chat_id)
        if user is None:
            await update.message.reply_text(t("telegram.not_authenticated", "en"))
            return
        locale = _locale(user)
        unlink_telegram(db, user)
    await update.message.reply_text(t("telegram.logout_success", locale))


# ---------------------------------------------------------------------------
# Contact share — authentication
# ---------------------------------------------------------------------------


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    contact = update.message.contact
    chat_id = str(update.effective_chat.id)
    telegram_phone = normalize_phone(contact.phone_number)

    with SessionLocal() as db:
        user = find_user_by_phone(db, telegram_phone)

        if user is None:
            await update.message.reply_text(
                t("telegram.auth_not_found", "en"),
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        locale = _locale(user)
        result = link_telegram(db, user, chat_id)

    reply_markup = ReplyKeyboardRemove()
    if result == AuthResult.SUCCESS:
        msg = t("telegram.auth_success", locale, username=user.username)
    elif result == AuthResult.ALREADY_THIS:
        msg = t("telegram.auth_already_this", locale, username=user.username)
    elif result == AuthResult.CONFLICT_CHAT:
        msg = t("telegram.auth_conflict_chat", locale)
    else:  # CONFLICT_USER
        msg = t("telegram.auth_conflict_user", locale)

    await update.message.reply_text(msg, reply_markup=reply_markup)

    if result in (AuthResult.SUCCESS, AuthResult.ALREADY_THIS):
        with SessionLocal() as db:
            await _send_events_list(update.message, user, db)


# ---------------------------------------------------------------------------
# Callback query dispatcher
# ---------------------------------------------------------------------------


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = str(update.effective_chat.id)

    with SessionLocal() as db:
        user = get_user_by_chat_id(db, chat_id)
        if user is None:
            await query.answer()
            await query.edit_message_text(t("telegram.not_authenticated", "en"))
            return

        data = query.data or ""

        if data == "noop":
            await query.answer()
            return

        if data.startswith("ref:"):
            await query.answer()
            page = int(data.split(":")[1])
            await _show_events(query, user, db, page)

        elif data.startswith("evts:"):
            await query.answer()
            page = int(data.split(":")[1])
            await _show_events(query, user, db, page)

        elif data.startswith("evt:"):
            await query.answer()
            event_id = int(data.split(":")[1])
            await _show_event_detail(query, user, db, event_id, back_page=0)

        elif data.startswith("evtp:"):
            await query.answer()
            # evtp:{event_id}:{player_page}:{back_page}
            parts = data.split(":")
            await _show_event_detail(query, user, db, int(parts[1]), back_page=int(parts[3]), player_page=int(parts[2]))

        elif data.startswith("sta:"):
            # _set_status calls query.answer() itself with the status toast
            parts = data.split(":")
            await _set_status(query, user, db, int(parts[1]), int(parts[2]), parts[3])


# ---------------------------------------------------------------------------
# Events list
# ---------------------------------------------------------------------------


async def _show_events(query, user, db, page: int) -> None:
    locale = _locale(user)
    today = datetime.today().date()
    all_upcoming = db.query(Event).filter(Event.event_date >= today).order_by(Event.event_date.asc()).all()
    total_pages = max(1, math.ceil(len(all_upcoming) / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    page_events = all_upcoming[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    if not all_upcoming:
        await query.edit_message_text(t("telegram.no_events", locale))
        return

    header = t("telegram.events_header", locale, page=page + 1)
    keyboard = events_keyboard(page_events, page, total_pages, locale=locale)
    await query.edit_message_text(header, reply_markup=keyboard)


# ---------------------------------------------------------------------------
# Event detail
# ---------------------------------------------------------------------------


async def _show_event_detail(query, user, db, event_id: int, back_page: int = 0, player_page: int = 0) -> None:
    locale = _locale(user)
    event = db.get(Event, event_id)
    if event is None:
        await query.edit_message_text(t("telegram.no_events", locale))
        return

    # Build event info text
    if event.event_type in ("training", "match"):
        event_type_str = t(f"telegram.event_type_{event.event_type}", locale)
    else:
        event_type_str = t("telegram.event_type_other", locale)

    lines = [f"*{event_type_str}: {event.title}*"]
    lines.append(f"{t('telegram.date_label', locale)}: {event.event_date}")

    if event.event_time:
        time_str = str(event.event_time)[:5]
        if event.event_end_time:
            time_str += f" - {str(event.event_end_time)[:5]}"
        lines.append(f"{t('telegram.time_label', locale)}: {time_str}")

    if event.location:
        lines.append(f"{t('telegram.location_label', locale)}: {event.location}")

    if event.meeting_time:
        meet = str(event.meeting_time)[:5]
        if event.meeting_location:
            meet += f" @ {event.meeting_location}"
        lines.append(f"{t('telegram.meeting_label', locale)}: {meet}")

    if event.description:
        lines.append(f"\n{event.description}")

    # Attendance summary
    atts = db.query(Attendance).filter(Attendance.event_id == event_id).all()
    att_by_player: dict[int, Attendance] = {a.player_id: a for a in atts}
    counts: dict[str, int] = {"present": 0, "absent": 0, "unknown": 0, "maybe": 0}
    for a in atts:
        counts[a.status] = counts.get(a.status, 0) + 1
    lines.append(
        f"\n{t('telegram.attendance_label', locale)}: ✓ {counts['present']} | ✗ {counts['absent']} | ? {counts['unknown']}"
    )

    text = "\n".join(lines)

    is_admin_or_coach = user.is_admin or user.is_coach

    if not is_admin_or_coach:
        # Member: show own status + status buttons
        own_player = db.query(Player).filter(Player.user_id == user.id, Player.archived_at.is_(None)).first()
        if own_player:
            own_att = att_by_player.get(own_player.id)
            own_status = own_att.status if own_att else "unknown"
            status_label = t(f"telegram.status_{own_status}", locale)
            text += f"\n\n{t('telegram.your_status_label', locale)}: {status_label}"
            keyboard = event_status_keyboard(event_id, own_player.id, back_page=back_page, locale=locale)
        else:
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton(t("telegram.back_button", locale), callback_data=f"evts:{back_page}")]]
            )
    else:
        # Coach/Admin: show full player list with status buttons
        players = (
            db.query(Player).filter(Player.archived_at.is_(None)).order_by(Player.last_name, Player.first_name).all()
        )
        total_player_pages = max(1, math.ceil(len(players) / PLAYER_PAGE_SIZE))
        player_page = max(0, min(player_page, total_player_pages - 1))
        page_players = players[player_page * PLAYER_PAGE_SIZE : (player_page + 1) * PLAYER_PAGE_SIZE]

        text += f"\n\n{t('telegram.players_header', locale)}"
        keyboard = event_admin_keyboard(
            event_id, page_players, att_by_player, player_page, total_player_pages, back_page=back_page, locale=locale
        )

    await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# Set attendance status
# ---------------------------------------------------------------------------


async def _set_status(query, user, db, event_id: int, player_id: int, status_char: str) -> None:
    locale = _locale(user)
    status = _STATUS_MAP.get(status_char, "unknown")

    # Authorization: member can only update their own player
    if not (user.is_admin or user.is_coach):
        own_player = db.query(Player).filter(Player.user_id == user.id, Player.archived_at.is_(None)).first()
        if own_player is None or own_player.id != player_id:
            await query.answer("Not authorized.", show_alert=True)
            return

    set_attendance(db, event_id, player_id, status)

    status_label = t(f"telegram.status_{status}", locale)
    await query.answer(t("telegram.status_updated", locale, status=status_label), show_alert=False)

    # Re-render the event detail in place
    await _show_event_detail(query, user, db, event_id, back_page=0)
