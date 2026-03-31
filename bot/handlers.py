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
    STATUS_ICON,
    event_admin_keyboard,
    event_status_keyboard,
    event_view_keyboard,
    events_keyboard,
)
from models.attendance import Attendance
from models.event import Event
from models.event_external import EventExternal
from models.player import Player
from models.player_team import PlayerTeam
from models.user_team import UserTeam
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


def _visible_team_ids(user, db) -> set[int] | None:
    """Return the set of team IDs the user should see events for.

    - Admin: None (no filter — sees everything)
    - Coach: teams they manage via UserTeam
    - Member: teams their linked player belongs to via PlayerTeam
    Returns an empty set if the user has no team associations (shows nothing).
    """
    if user.is_admin:
        return None
    if user.is_coach:
        rows = db.query(UserTeam.team_id).filter(UserTeam.user_id == user.id).all()
        return {r[0] for r in rows}
    # Member — find linked player's teams
    player = db.query(Player).filter(Player.user_id == user.id, Player.archived_at.is_(None)).first()
    if player is None:
        return set()
    rows = db.query(PlayerTeam.team_id).filter(PlayerTeam.player_id == player.id).all()
    return {r[0] for r in rows}


def _upcoming_events(db, user):
    """Return upcoming events visible to the user, ordered by date."""
    today = datetime.today().date()
    q = db.query(Event).filter(Event.event_date >= today)
    team_ids = _visible_team_ids(user, db)
    if team_ids is not None:
        q = q.filter(Event.team_id.in_(team_ids))
    return q.order_by(Event.event_date.asc()).all()


async def _send_events_list(message, user, db) -> None:
    """Send the upcoming events list as a new message with inline keyboard."""
    locale = _locale(user)
    all_upcoming = _upcoming_events(db, user)
    if not all_upcoming:
        await message.reply_text(t("telegram.no_events", locale))
        return
    total_pages = max(1, math.ceil(len(all_upcoming) / PAGE_SIZE))
    page_events = all_upcoming[:PAGE_SIZE]
    header = t("telegram.events_header", locale, page=1)
    keyboard = events_keyboard(page_events, 0, total_pages, locale=locale)
    await message.reply_text(header, reply_markup=keyboard)


def _phone_request_keyboard(locale: str = "en") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton(t("telegram.share_phone_button", locale), request_contact=True)]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )


def _start_over_keyboard(locale: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(t("telegram.start_over_button", locale), callback_data="restart:")]]
    )


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

    await update.message.reply_text(
        t("telegram.welcome", "en"),
        reply_markup=_phone_request_keyboard(),
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
            await update.message.reply_text(
                "\u200b",  # zero-width space — placeholder for the inline button
                reply_markup=_start_over_keyboard("en"),
            )
            return

        locale = _locale(user)
        result = link_telegram(db, user, chat_id)

    if result == AuthResult.SUCCESS:
        msg = t("telegram.auth_success", locale, username=user.username)
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())
    elif result == AuthResult.ALREADY_THIS:
        msg = t("telegram.auth_already_this", locale, username=user.username)
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())
    else:
        if result == AuthResult.CONFLICT_CHAT:
            msg = t("telegram.auth_conflict_chat", locale)
        else:  # CONFLICT_USER
            msg = t("telegram.auth_conflict_user", locale)
        await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text(
            "\u200b",
            reply_markup=_start_over_keyboard(locale),
        )

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

        # Clean up any pending prompts if the user navigated away via a button
        # Don't clean up awaiting_external when user is selecting the status (extsta: callbacks)
        _skip_ext_cleanup = data.startswith("extsta:")
        _skip_extn_cleanup = data.startswith("extn:")
        for _key in ("awaiting_note", "awaiting_chat_reply") + (() if _skip_ext_cleanup else ("awaiting_external",)) + (() if _skip_extn_cleanup else ("awaiting_ext_note",)):
            _pending = context.user_data.pop(_key, None)
            if _pending:
                _pmid = _pending.get("prompt_message_id")
                _pcid = _pending.get("chat_id")
                if _pmid and _pcid:
                    try:
                        await context.bot.delete_message(chat_id=_pcid, message_id=_pmid)
                    except Exception:
                        pass

        if data == "noop":
            await query.answer()
            return

        if data == "restart:":
            await query.answer()
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                t("telegram.welcome", "en"),
                reply_markup=_phone_request_keyboard(),
            )
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

        elif data.startswith("evte:"):
            await query.answer()
            # evte:{event_id}:{player_page}:{back_page}
            parts = data.split(":")
            await _show_event_detail(query, user, db, int(parts[1]), back_page=int(parts[3]), player_page=int(parts[2]), edit_mode=True)

        elif data.startswith("evtn:"):
            await query.answer()
            # evtn:{event_id}:{back_page}
            parts = data.split(":")
            await _show_event_notes(query, user, db, int(parts[1]), back_page=int(parts[2]))

        elif data.startswith("evtx:"):
            await query.answer()
            # evtx:{event_id}:{back_page}
            parts = data.split(":")
            await _show_event_externals(query, user, db, int(parts[1]), back_page=int(parts[2]))

        elif data.startswith("extadd:"):
            await query.answer()
            # extadd:{event_id}:{back_page} — start add-external flow
            parts = data.split(":")
            event_id_x, back_page_x = int(parts[1]), int(parts[2])
            prompt_msg = await query.message.reply_text(t("telegram.external_name_prompt", _locale(user)))
            context.user_data["awaiting_external"] = {
                "event_id": event_id_x,
                "back_page": back_page_x,
                "prompt_message_id": prompt_msg.message_id,
                "chat_id": query.message.chat_id,
                "step": "name",
            }

        elif data.startswith("extdel:"):
            await query.answer()
            # extdel:{ext_id}:{event_id}:{back_page}
            parts = data.split(":")
            ext_id_d, event_id_d, back_page_d = int(parts[1]), int(parts[2]), int(parts[3])
            ext = db.get(EventExternal, ext_id_d)
            if ext and ext.event_id == event_id_d:
                db.delete(ext)
                db.commit()
            await _show_event_externals(query, user, db, event_id_d, back_page=back_page_d)

        elif data.startswith("extedit:"):
            await query.answer()
            # extedit:{ext_id}:{event_id}:{back_page} — show status keyboard for existing external
            parts = data.split(":")
            ext_id_e, event_id_e, back_page_e = int(parts[1]), int(parts[2]), int(parts[3])
            ext = db.get(EventExternal, ext_id_e)
            if ext:
                locale_e = _locale(user)
                keyboard_e = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✓", callback_data=f"exts:{ext_id_e}:p:{event_id_e}:{back_page_e}"),
                        InlineKeyboardButton("✗", callback_data=f"exts:{ext_id_e}:a:{event_id_e}:{back_page_e}"),
                        InlineKeyboardButton("?", callback_data=f"exts:{ext_id_e}:u:{event_id_e}:{back_page_e}"),
                    ],
                    [InlineKeyboardButton(t("telegram.note_button", locale_e) + (" ✓" if ext.note else ""), callback_data=f"extn:{ext_id_e}:{event_id_e}:{back_page_e}")],
                    [InlineKeyboardButton(t("telegram.back_button", locale_e), callback_data=f"evtx:{event_id_e}:{back_page_e}")],
                ])
                icon = STATUS_ICON.get(ext.status, "?")
                await query.edit_message_text(
                    f"*{ext.full_name}* {icon}\n_{ext.note or ''}_" if ext.note else f"*{ext.full_name}* {icon}",
                    reply_markup=keyboard_e,
                    parse_mode=ParseMode.MARKDOWN,
                )

        elif data.startswith("exts:"):
            await query.answer()
            # exts:{ext_id}:{status_char}:{event_id}:{back_page} — update existing external status
            parts = data.split(":")
            ext_id_s, status_char_s, event_id_s, back_page_s = int(parts[1]), parts[2], int(parts[3]), int(parts[4])
            ext = db.get(EventExternal, ext_id_s)
            if ext:
                status_map = {"p": "present", "a": "absent", "u": "unknown"}
                ext.status = status_map.get(status_char_s, "unknown")
                db.commit()
            await _show_event_externals(query, user, db, event_id_s, back_page=back_page_s)

        elif data.startswith("extn:"):
            await query.answer()
            # extn:{ext_id}:{event_id}:{back_page} — add/edit note for existing external
            parts = data.split(":")
            ext_id_n2, event_id_n2, back_page_n2 = int(parts[1]), int(parts[2]), int(parts[3])
            prompt_msg = await query.message.reply_text(t("telegram.note_prompt", _locale(user)))
            context.user_data["awaiting_ext_note"] = {
                "ext_id": ext_id_n2,
                "event_id": event_id_n2,
                "back_page": back_page_n2,
                "prompt_message_id": prompt_msg.message_id,
                "chat_id": query.message.chat_id,
            }

        elif data.startswith("extsta:"):
            await query.answer()
            # extsta:{status} — select status for pending external
            pending_ext = context.user_data.get("awaiting_external")
            if pending_ext and pending_ext.get("step") == "status":
                status_char = data.split(":")[1]
                status_map = {"p": "present", "a": "absent", "u": "unknown"}
                status = status_map.get(status_char, "unknown")
                ext = EventExternal(
                    event_id=pending_ext["event_id"],
                    first_name=pending_ext["first_name"],
                    last_name=pending_ext["last_name"],
                    status=status,
                )
                db.add(ext)
                db.commit()
                context.user_data.pop("awaiting_external", None)
                locale_x = _locale(user)
                conf = await query.message.reply_text(t("telegram.external_added", locale_x))
                import asyncio  # noqa: PLC0415
                await asyncio.sleep(2)
                try:
                    await conf.delete()
                except Exception:
                    pass
                await _show_event_externals(query, user, db, pending_ext["event_id"], back_page=pending_ext["back_page"])

        elif data.startswith("note:"):
            await query.answer()
            # note:{event_id}:{player_id}:{back_page}
            parts = data.split(":")
            event_id_n, player_id_n, back_page_n = int(parts[1]), int(parts[2]), int(parts[3])
            prompt_msg = await query.message.reply_text(t("telegram.note_prompt", _locale(user)))
            context.user_data["awaiting_note"] = {
                "event_id": event_id_n,
                "player_id": player_id_n,
                "back_page": back_page_n,
                "prompt_message_id": prompt_msg.message_id,
                "chat_id": query.message.chat_id,
            }
            return

        elif data.startswith("sta:"):
            # _set_status calls query.answer() itself with the status toast
            parts = data.split(":")
            await _set_status(query, user, db, int(parts[1]), int(parts[2]), parts[3])

        elif data.startswith("chatreply:"):
            await query.answer()
            # chatreply:{event_id}:{lane}
            parts = data.split(":")
            event_id_cr = int(parts[1])
            locale_cr = _locale(user)
            prompt_msg = await query.message.reply_text(
                t("telegram.chat_reply_prompt", locale_cr)
            )
            context.user_data["awaiting_chat_reply"] = {
                "event_id": event_id_cr,
                "prompt_message_id": prompt_msg.message_id,
                "chat_id": query.message.chat_id,
            }


# ---------------------------------------------------------------------------
# Events list
# ---------------------------------------------------------------------------


async def _show_events(query, user, db, page: int) -> None:
    locale = _locale(user)
    all_upcoming = _upcoming_events(db, user)
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


async def _show_event_detail(query, user, db, event_id: int, back_page: int = 0, player_page: int = 0, edit_mode: bool = False) -> None:
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

    # Attendance summary (players + externals)
    atts = db.query(Attendance).filter(Attendance.event_id == event_id).all()
    att_by_player: dict[int, Attendance] = {a.player_id: a for a in atts}
    ext_rows = db.query(EventExternal).filter(EventExternal.event_id == event_id).order_by(EventExternal.created_at).all()
    counts: dict[str, int] = {"present": 0, "absent": 0, "unknown": 0, "maybe": 0}
    for a in atts:
        counts[a.status] = counts.get(a.status, 0) + 1
    for ext in ext_rows:
        counts[ext.status] = counts.get(ext.status, 0) + 1
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
            own_note = own_att.note if own_att else ""
            status_label = t(f"telegram.status_{own_status}", locale)
            text += f"\n\n{t('telegram.your_status_label', locale)}: {status_label}"
            if own_note:
                text += f"\n_{t('telegram.note_label', locale)}: {own_note}_"
            keyboard = event_status_keyboard(event_id, own_player.id, back_page=back_page, locale=locale, note=own_note or "")
        else:
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton(t("telegram.back_button", locale), callback_data=f"evts:{back_page}")]]
            )
    else:
        # Coach/Admin: show players for this event's team/season
        if event.team_id and event.season_id:
            # Filter to players assigned to this event's team+season
            pt_rows = (
                db.query(PlayerTeam)
                .filter(
                    PlayerTeam.team_id == event.team_id,
                    PlayerTeam.season_id == event.season_id,
                )
                .all()
            )
            player_ids = {pt.player_id: pt.position for pt in pt_rows}
            players_q = (
                db.query(Player)
                .filter(Player.id.in_(player_ids.keys()), Player.archived_at.is_(None))
                .order_by(Player.last_name, Player.first_name)
                .all()
            )
            # Attach position from PlayerTeam for grouping
            for p in players_q:
                p._bot_position = player_ids.get(p.id)  # type: ignore[attr-defined]
            players = players_q
        else:
            players = (
                db.query(Player)
                .filter(Player.archived_at.is_(None))
                .order_by(Player.last_name, Player.first_name)
                .all()
            )
            for p in players:
                p._bot_position = None  # type: ignore[attr-defined]

        # Group players by position in the message text
        _POS_ORDER = ["goalie", "defender", "center", "forward", None]
        _POS_LABEL = {
            "goalie": t("telegram.pos_goalie", locale),
            "defender": t("telegram.pos_defender", locale),
            "center": t("telegram.pos_center", locale),
            "forward": t("telegram.pos_forward", locale),
            None: t("telegram.pos_other", locale),
        }
        grouped: dict[str | None, list[Player]] = {pos: [] for pos in _POS_ORDER}
        for p in players:
            pos = getattr(p, "_bot_position", None)
            if pos not in grouped:
                pos = None
            grouped[pos].append(p)

        pos_lines: list[str] = []
        for pos in _POS_ORDER:
            group = grouped[pos]
            if not group:
                continue
            pos_lines.append(f"\n*{_POS_LABEL[pos]}*")
            for p in group:
                att = att_by_player.get(p.id)
                icon = STATUS_ICON.get(att.status if att else "unknown", "?")
                pos_lines.append(f"{icon} {p.full_name}")
        if ext_rows:
            pos_lines.append(f"\n*{t('telegram.externals_header', locale)}*")
            for ext in ext_rows:
                icon = STATUS_ICON.get(ext.status, "?")
                ext_line = f"{icon} 👤 _{ext.full_name}_"
                if ext.note:
                    ext_line += f" — {ext.note}"
                pos_lines.append(ext_line)
        text += "\n" + "\n".join(pos_lines)

        if edit_mode:
            total_player_pages = max(1, math.ceil(len(players) / PLAYER_PAGE_SIZE))
            player_page = max(0, min(player_page, total_player_pages - 1))
            page_players = players[player_page * PLAYER_PAGE_SIZE : (player_page + 1) * PLAYER_PAGE_SIZE]
            keyboard = event_admin_keyboard(
                event_id, page_players, att_by_player, player_page, total_player_pages, back_page=back_page, locale=locale
            )
        else:
            keyboard = event_view_keyboard(event_id, back_page=back_page, locale=locale, is_privileged=True)

    await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# /cancel — abort pending note input
# ---------------------------------------------------------------------------


async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    cancelled = (
        context.user_data.pop("awaiting_note", None)
        or context.user_data.pop("awaiting_ext_note", None)
        or context.user_data.pop("awaiting_external", None)
        or context.user_data.pop("awaiting_chat_reply", None)
    )
    if cancelled:
        with SessionLocal() as db:
            user = get_user_by_chat_id(db, chat_id)
            locale = _locale(user) if user else "en"
        await update.message.reply_text(t("telegram.note_cancelled", locale))
    else:
        await update.message.reply_text("OK.")


# ---------------------------------------------------------------------------
# Free-text message handler — captures note input
# ---------------------------------------------------------------------------


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)

    # Handle external name input
    pending_ext = context.user_data.get("awaiting_external")
    if pending_ext and pending_ext.get("step") == "name":
        name_text = (update.message.text or "").strip()
        parts = name_text.split(None, 1)
        first = parts[0] if parts else name_text
        last = parts[1] if len(parts) > 1 else ""
        pending_ext["first_name"] = first
        pending_ext["last_name"] = last
        pending_ext["step"] = "status"
        # Delete prompt + user message
        prompt_msg_id = pending_ext.get("prompt_message_id")
        ext_chat_id = pending_ext.get("chat_id")
        if prompt_msg_id and ext_chat_id:
            try:
                await context.bot.delete_message(chat_id=ext_chat_id, message_id=prompt_msg_id)
            except Exception:
                pass
        try:
            await update.message.delete()
        except Exception:
            pass
        # Ask for status
        with SessionLocal() as db:
            user = get_user_by_chat_id(db, chat_id)
            locale = _locale(user) if user else "en"
        status_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✓ Present", callback_data="extsta:p"),
            InlineKeyboardButton("✗ Absent", callback_data="extsta:a"),
            InlineKeyboardButton("? Unknown", callback_data="extsta:u"),
        ]])
        full_name = f"{first} {last}".strip()
        prompt2 = await update.message.reply_text(
            t("telegram.external_select_status", locale, name=full_name),
            reply_markup=status_keyboard,
        )
        pending_ext["prompt_message_id"] = prompt2.message_id
        return

    # Handle external note input
    pending_ext_note = context.user_data.get("awaiting_ext_note")
    if pending_ext_note:
        note_text = (update.message.text or "").strip()
        prompt_msg_id = pending_ext_note.get("prompt_message_id")
        note_chat_id = pending_ext_note.get("chat_id")
        if prompt_msg_id and note_chat_id:
            try:
                await context.bot.delete_message(chat_id=note_chat_id, message_id=prompt_msg_id)
            except Exception:
                pass
        try:
            await update.message.delete()
        except Exception:
            pass
        with SessionLocal() as db:
            user = get_user_by_chat_id(db, chat_id)
            if user:
                ext = db.get(EventExternal, pending_ext_note["ext_id"])
                if ext:
                    ext.note = note_text or None
                    db.commit()
        context.user_data.pop("awaiting_ext_note", None)
        import asyncio as _asyncio  # noqa: PLC0415
        conf = await update.message.reply_text(t("telegram.note_saved", _locale(user) if user else "en"))
        await _asyncio.sleep(2)
        try:
            await conf.delete()
        except Exception:
            pass
        return

    # Handle chat reply input
    pending_chat = context.user_data.get("awaiting_chat_reply")
    if pending_chat:
        body_text = (update.message.text or "").strip()
        prompt_msg_id = pending_chat.get("prompt_message_id")
        reply_chat_id = pending_chat.get("chat_id")
        if prompt_msg_id and reply_chat_id:
            try:
                await context.bot.delete_message(chat_id=reply_chat_id, message_id=prompt_msg_id)
            except Exception:
                pass
        try:
            await update.message.delete()
        except Exception:
            pass
        context.user_data.pop("awaiting_chat_reply", None)
        locale_cr = "en"
        if body_text:
            with SessionLocal() as db:
                user = get_user_by_chat_id(db, chat_id)
                locale_cr = _locale(user) if user else "en"
                if user:
                    from models.event_message import EventMessage as _EventMessage  # noqa: PLC0415
                    from services.chat_service import (  # noqa: PLC0415
                        author_display_name,
                        message_to_dict,
                        push_chat_message_sse,
                    )
                    msg = _EventMessage(
                        event_id=pending_chat["event_id"],
                        user_id=user.id,
                        lane="discussion",
                        body=body_text,
                    )
                    db.add(msg)
                    db.commit()
                    db.refresh(msg)
                    author_name = author_display_name(user)
                    msg_dict = message_to_dict(msg, author_name)
                    push_chat_message_sse(pending_chat["event_id"], msg_dict, db)
        import asyncio as _asyncio  # noqa: PLC0415
        conf = await update.message.reply_text(t("telegram.chat_reply_posted", locale_cr))
        await _asyncio.sleep(2)
        try:
            await conf.delete()
        except Exception:
            pass
        return

    pending = context.user_data.get("awaiting_note")
    if not pending:
        return  # ignore unrecognised text

    event_id = pending["event_id"]
    player_id = pending["player_id"]
    back_page = pending["back_page"]
    note_text = (update.message.text or "").strip()

    with SessionLocal() as db:
        user = get_user_by_chat_id(db, chat_id)
        if user is None:
            return
        locale = _locale(user)
        att = db.query(Attendance).filter(
            Attendance.event_id == event_id,
            Attendance.player_id == player_id,
        ).first()
        if att is None:
            from services.attendance_service import get_or_create_attendance  # noqa: PLC0415
            att = get_or_create_attendance(db, event_id, player_id)
        att.note = note_text or None
        db.commit()

    prompt_message_id = pending.get("prompt_message_id")
    chat_id = pending.get("chat_id")
    context.user_data.pop("awaiting_note", None)

    # Delete the prompt message and the user's note message to keep chat clean
    if prompt_message_id and chat_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prompt_message_id)
        except Exception:
            pass
    try:
        await update.message.delete()
    except Exception:
        pass

    import asyncio  # noqa: PLC0415
    confirmation = await update.message.reply_text(t("telegram.note_saved", locale))
    await asyncio.sleep(2)
    try:
        await confirmation.delete()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Event externals (coach/admin)
# ---------------------------------------------------------------------------


async def _show_event_externals(query, user, db, event_id: int, back_page: int = 0) -> None:
    locale = _locale(user)
    externals = db.query(EventExternal).filter(EventExternal.event_id == event_id).order_by(EventExternal.created_at).all()

    rows = []
    if externals:
        lines = [f"*{t('telegram.externals_header', locale)}*"]
        for ext in externals:
            icon = STATUS_ICON.get(ext.status, "?")
            line = f"{icon} _{ext.full_name}_"
            if ext.note:
                line += f" — {ext.note}"
            lines.append(line)
            rows.append([
                InlineKeyboardButton(f"✎ {ext.full_name}", callback_data=f"extedit:{ext.id}:{event_id}:{back_page}"),
                InlineKeyboardButton("🗑", callback_data=f"extdel:{ext.id}:{event_id}:{back_page}"),
            ])
        text = "\n".join(lines)
    else:
        text = t("telegram.no_externals", locale)

    rows.append([InlineKeyboardButton(f"+ {t('externals.add', locale)}", callback_data=f"extadd:{event_id}:{back_page}")])
    rows.append([InlineKeyboardButton(t("telegram.back_button", locale), callback_data=f"evtp:{event_id}:0:{back_page}")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows), parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# Event notes (coach/admin)
# ---------------------------------------------------------------------------


async def _show_event_notes(query, user, db, event_id: int, back_page: int = 0) -> None:
    locale = _locale(user)
    atts = (
        db.query(Attendance)
        .filter(Attendance.event_id == event_id, Attendance.note.isnot(None))
        .all()
    )
    if not atts:
        text = t("telegram.no_notes", locale)
    else:
        lines = []
        for att in atts:
            player = db.get(Player, att.player_id)
            name = player.full_name if player else f"#{att.player_id}"
            icon = STATUS_ICON.get(att.status, "?")
            lines.append(f"{icon} *{name}*: {att.note}")
        text = "\n".join(lines)

    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(t("telegram.back_button", locale), callback_data=f"evtp:{event_id}:0:{back_page}")]]
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

    # Re-render the event detail in edit mode
    await _show_event_detail(query, user, db, event_id, back_page=0, edit_mode=True)
