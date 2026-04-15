"""bot/absence_handlers.py — Telegram absence management handler functions.

All public async functions are called from bot/handlers.py dispatch blocks.
They follow the same pattern as the private helpers in handlers.py:
  - accept (query, user, db, ...) for callback-driven screens
  - open their own SessionLocal for text-input handlers
"""

from __future__ import annotations

import asyncio
import math
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

from app.database import SessionLocal
from app.i18n import t
from bot.absence_keyboards import (
    ABSENCE_PAGE_SIZE,
    PLAYER_PAGE_SIZE,
    absence_delete_confirm_keyboard,
    absence_list_keyboard,
    absence_player_list_keyboard,
    other_menu_keyboard,
)
from models.player import Player
from models.player_absence import PlayerAbsence
from models.player_team import PlayerTeam
from models.user_team import UserTeam
from services.absence_service import apply_absence_to_future_events
from services.telegram_service import get_user_by_chat_id


def _locale(user) -> str:
    return user.locale if user and user.locale else "en"


# ---------------------------------------------------------------------------
# Other menu
# ---------------------------------------------------------------------------


async def show_other_menu(query, user, back_page: int) -> None:
    """Render the '⚙️ Other' mini-menu."""
    locale = _locale(user)
    await query.edit_message_text(
        t("telegram.other_button", locale),
        reply_markup=other_menu_keyboard(back_page, locale),
    )


# ---------------------------------------------------------------------------
# Absence root — branches by role
# ---------------------------------------------------------------------------


async def show_absence_root(query, user, db, back_page: int) -> None:
    """Entry point from the Other menu.

    Members go directly to their own absence list.
    Coaches/admins see the paginated player list.
    """
    if user.is_admin or user.is_coach:
        await show_absence_player_list(query, user, db, page=0, back_page=back_page)
    else:
        player = db.query(Player).filter(
            Player.user_id == user.id,
            Player.archived_at.is_(None),
        ).first()
        if player is None:
            await query.edit_message_text(t("telegram.not_authenticated", _locale(user)))
            return
        await show_absence_list(query, user, db, player_id=player.id, page=0, back_page=back_page, is_member=True)


# ---------------------------------------------------------------------------
# Player list (coach/admin only)
# ---------------------------------------------------------------------------


async def show_absence_player_list(query, user, db, page: int, back_page: int) -> None:
    """Paginated list of players for coach/admin to pick from."""
    locale = _locale(user)

    if user.is_admin:
        players_q = (
            db.query(Player)
            .filter(Player.archived_at.is_(None))
            .order_by(Player.first_name, Player.last_name)
            .all()
        )
    else:
        team_ids = {
            r[0] for r in db.query(UserTeam.team_id).filter(UserTeam.user_id == user.id).all()
        }
        player_ids = {
            r[0] for r in db.query(PlayerTeam.player_id).filter(PlayerTeam.team_id.in_(team_ids)).all()
        }
        players_q = (
            db.query(Player)
            .filter(Player.id.in_(player_ids), Player.archived_at.is_(None))
            .order_by(Player.first_name, Player.last_name)
            .all()
        )

    total_pages = max(1, math.ceil(len(players_q) / PLAYER_PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    page_players = players_q[page * PLAYER_PAGE_SIZE : (page + 1) * PLAYER_PAGE_SIZE]

    keyboard = absence_player_list_keyboard(page_players, page, total_pages, back_page, locale)
    await query.edit_message_text(t("telegram.select_player", locale), reply_markup=keyboard)


# ---------------------------------------------------------------------------
# Absence list for one player
# ---------------------------------------------------------------------------


async def show_absence_list(query, user, db, player_id: int, page: int, back_page: int, is_member: bool) -> None:
    """Show all period absences for a player with delete buttons."""
    locale = _locale(user)

    player = db.get(Player, player_id)
    if player is None:
        await query.edit_message_text(t("telegram.unknown_error", locale))
        return

    absences = (
        db.query(PlayerAbsence)
        .filter(PlayerAbsence.player_id == player_id, PlayerAbsence.absence_type == "period")
        .order_by(PlayerAbsence.start_date)
        .all()
    )

    total_pages = max(1, math.ceil(len(absences) / ABSENCE_PAGE_SIZE)) if absences else 1
    page = max(0, min(page, total_pages - 1))
    page_absences = absences[page * ABSENCE_PAGE_SIZE : (page + 1) * ABSENCE_PAGE_SIZE]

    header = t("telegram.absences_header", locale, name=player.full_name)
    if not absences:
        header += f"\n\n{t('telegram.absences_empty', locale)}"

    keyboard = absence_list_keyboard(page_absences, player_id, page, total_pages, back_page, is_member, locale)
    await query.edit_message_text(header, reply_markup=keyboard)


# ---------------------------------------------------------------------------
# Add absence — multi-step text flow
# ---------------------------------------------------------------------------


async def start_add_absence(query, user, context: ContextTypes.DEFAULT_TYPE, player_id: int, back_page: int) -> None:
    """Begin the add-absence multi-step flow (step 1: start date)."""
    locale = _locale(user)
    prompt_msg = await query.message.reply_text(t("telegram.absence_start_prompt", locale))
    context.user_data["awaiting_absence"] = {
        "player_id": player_id,
        "back_page": back_page,
        "step": "start",
        "start_date": None,
        "end_date": None,
        "prompt_message_id": prompt_msg.message_id,
        "chat_id": query.message.chat_id,
    }


async def handle_absence_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Process one step of the add-absence multi-step input flow.

    Returns True if this message was consumed by the absence flow (caller
    should ``return`` immediately). Returns False if no absence flow is active.

    Steps: start date → end date → reason → create absence → show list.
    """
    pending = context.user_data.get("awaiting_absence")
    if not pending:
        return False

    chat_id = str(update.effective_chat.id)
    text = (update.message.text or "").strip()
    step = pending["step"]
    prompt_msg_id = pending.get("prompt_message_id")
    abs_chat_id = pending.get("chat_id")

    # Clean up previous prompt + user message
    if prompt_msg_id and abs_chat_id:
        try:
            await context.bot.delete_message(chat_id=abs_chat_id, message_id=prompt_msg_id)
        except Exception:
            pass
    try:
        await update.message.delete()
    except Exception:
        pass

    with SessionLocal() as db:
        user = get_user_by_chat_id(db, chat_id)
        if user is None:
            context.user_data.pop("awaiting_absence", None)
            return True
        locale = _locale(user)

        if step == "start":
            try:
                parsed = date.fromisoformat(text)
            except ValueError:
                new_prompt = await update.message.reply_text(t("telegram.absence_date_error", locale))
                pending["prompt_message_id"] = new_prompt.message_id
                return True
            if parsed < date.today():
                new_prompt = await update.message.reply_text(t("telegram.absence_past_error", locale))
                pending["prompt_message_id"] = new_prompt.message_id
                return True
            pending["start_date"] = parsed.isoformat()
            pending["step"] = "end"
            new_prompt = await update.message.reply_text(t("telegram.absence_end_prompt", locale))
            pending["prompt_message_id"] = new_prompt.message_id
            return True

        elif step == "end":
            try:
                parsed = date.fromisoformat(text)
            except ValueError:
                new_prompt = await update.message.reply_text(t("telegram.absence_date_error", locale))
                pending["prompt_message_id"] = new_prompt.message_id
                return True
            start = date.fromisoformat(pending["start_date"])
            if parsed < start:
                new_prompt = await update.message.reply_text(t("telegram.absence_range_error", locale))
                pending["prompt_message_id"] = new_prompt.message_id
                return True
            pending["end_date"] = parsed.isoformat()
            pending["step"] = "reason"
            new_prompt = await update.message.reply_text(t("telegram.absence_reason_prompt", locale))
            pending["prompt_message_id"] = new_prompt.message_id
            return True

        elif step == "reason":
            reason = None if text.lower() == "/skip" or not text else text
            player_id = pending["player_id"]
            back_page = pending["back_page"]
            start_date = date.fromisoformat(pending["start_date"])
            end_date = date.fromisoformat(pending["end_date"])

            absence = PlayerAbsence(
                player_id=player_id,
                absence_type="period",
                start_date=start_date,
                end_date=end_date,
                reason=reason,
            )
            db.add(absence)
            db.commit()
            count = apply_absence_to_future_events(player_id, db)

            context.user_data.pop("awaiting_absence", None)

            conf = await update.message.reply_text(
                t("telegram.absence_added", locale, count=count)
            )
            await asyncio.sleep(2)
            try:
                await conf.delete()
            except Exception:
                pass

            # Send a fresh absence list message (can't edit the old bot message from handle_text)
            is_member = not (user.is_admin or user.is_coach)
            player = db.get(Player, player_id)
            absences = (
                db.query(PlayerAbsence)
                .filter(PlayerAbsence.player_id == player_id, PlayerAbsence.absence_type == "period")
                .order_by(PlayerAbsence.start_date)
                .all()
            )
            page = 0
            total_pages = max(1, math.ceil(len(absences) / ABSENCE_PAGE_SIZE)) if absences else 1
            page_absences = absences[page * ABSENCE_PAGE_SIZE : (page + 1) * ABSENCE_PAGE_SIZE]

            header = t("telegram.absences_header", locale, name=player.full_name)
            keyboard = absence_list_keyboard(page_absences, player_id, page, total_pages, back_page, is_member, locale)
            await update.message.reply_text(header, reply_markup=keyboard)
            return True

    return True


# ---------------------------------------------------------------------------
# Delete absence
# ---------------------------------------------------------------------------


async def confirm_delete_absence(query, user, db, absence_id: int, player_id: int, page: int, back_page: int) -> None:
    """Show a Yes/No confirmation screen before deleting."""
    locale = _locale(user)
    absence = db.get(PlayerAbsence, absence_id)
    if absence is None or absence.player_id != player_id:
        await query.edit_message_text(t("telegram.unknown_error", locale))
        return
    dates = f"{absence.start_date} → {absence.end_date}"
    keyboard = absence_delete_confirm_keyboard(absence_id, player_id, page, back_page, locale)
    await query.edit_message_text(
        f"{t('telegram.absence_confirm_del', locale)}\n{dates}",
        reply_markup=keyboard,
    )


async def delete_absence(query, user, db, absence_id: int, player_id: int, page: int, back_page: int) -> None:
    """Delete the absence and refresh the absence list."""
    absence = db.get(PlayerAbsence, absence_id)
    if absence and absence.player_id == player_id:
        db.delete(absence)
        db.commit()
    is_member = not (user.is_admin or user.is_coach)
    await show_absence_list(query, user, db, player_id, page, back_page, is_member)
