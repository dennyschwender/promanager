"""bot/views/events.py — Events view renderers."""
from __future__ import annotations

import math
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

from app.i18n import t
from bot.keyboards import (
    PLAYER_PAGE_SIZE,
    STATUS_ICON,
    event_admin_keyboard,
    event_view_keyboard,
    event_status_keyboard,
)
from bot.views import ViewResult
from models.attendance import Attendance
from models.event import Event
from models.event_external import EventExternal
from models.player import Player
from models.player_team import PlayerTeam

PAGE_SIZE = 5


def _locale(user) -> str:
    return user.locale or "en"


def _visible_team_ids(user, db) -> set[int] | None:
    from models.user_team import UserTeam  # noqa: PLC0415

    if user.is_admin:
        return None
    if user.is_coach:
        rows = db.query(UserTeam.team_id).filter(UserTeam.user_id == user.id).all()
        return {r[0] for r in rows}
    player = db.query(Player).filter(Player.user_id == user.id, Player.archived_at.is_(None)).first()
    if player is None:
        return set()
    rows = db.query(PlayerTeam.team_id).filter(PlayerTeam.player_id == player.id).all()
    return {r[0] for r in rows}


def _upcoming_events(db, user) -> list[Event]:
    today = datetime.today().date()
    q = db.query(Event).filter(Event.event_date >= today)
    team_ids = _visible_team_ids(user, db)
    if team_ids is not None:
        q = q.filter(Event.team_id.in_(team_ids))
    return q.order_by(Event.event_date.asc()).all()


def render_events_list(user, db, page: int = 0) -> ViewResult:
    locale = _locale(user)
    all_events = _upcoming_events(db, user)
    total_pages = max(1, math.ceil(len(all_events) / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    page_events = all_events[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    if not all_events:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home"),
        ]])
        return t("telegram.no_events", locale), keyboard

    header = t("telegram.events_header", locale, page=page + 1)
    rows = []
    for event in page_events:
        time_val = event.meeting_time or event.event_time
        time_str = f" {str(time_val)[:5]}" if time_val else ""
        label = f"{event.event_date}{time_str} — {event.title}"
        rows.append([InlineKeyboardButton(label, callback_data=f"e:{event.id}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(t("telegram.prev_button", locale), callback_data=f"el:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(t("telegram.view_more_button", locale), callback_data=f"el:{page + 1}"))
    rows.append(nav if nav else [InlineKeyboardButton("—", callback_data="noop")])
    rows.append([InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home")])

    return header, InlineKeyboardMarkup(rows)


def render_event_detail(user, db, event_id: int, back: str = "el") -> ViewResult:
    locale = _locale(user)
    event = db.get(Event, event_id)
    if event is None:
        return t("telegram.no_events", locale), InlineKeyboardMarkup([[
            InlineKeyboardButton(t("telegram.back_button", locale), callback_data=back),
        ]])

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

    atts = db.query(Attendance).filter(Attendance.event_id == event_id).all()
    att_by_player: dict[int, Attendance] = {a.player_id: a for a in atts}
    ext_rows = (
        db.query(EventExternal)
        .filter(EventExternal.event_id == event_id)
        .order_by(EventExternal.created_at)
        .all()
    )
    counts: dict[str, int] = {"present": 0, "absent": 0, "unknown": 0, "maybe": 0}
    for a in atts:
        counts[a.status] = counts.get(a.status, 0) + 1
    for ext in ext_rows:
        counts[ext.status] = counts.get(ext.status, 0) + 1
    lines.append(
        f"\n{t('telegram.attendance_label', locale)}: ✓ {counts['present']} | ✗ {counts['absent']} | ? {counts['unknown']}"
    )

    from models.event_message import EventMessage  # noqa: PLC0415
    msg_count = db.query(EventMessage).filter(EventMessage.event_id == event_id).count()

    text = "\n".join(lines)
    is_admin_or_coach = user.is_admin or user.is_coach

    back_page = 0

    if not is_admin_or_coach:
        own_player = db.query(Player).filter(
            Player.user_id == user.id, Player.archived_at.is_(None)
        ).first()
        if own_player:
            own_att = att_by_player.get(own_player.id)
            own_status = own_att.status if own_att else "unknown"
            own_note = own_att.note if own_att else ""
            status_label = t(f"telegram.status_{own_status}", locale)
            text += f"\n\n{t('telegram.your_status_label', locale)}: {status_label}"
            if own_note:
                text += f"\n_{t('telegram.note_label', locale)}: {own_note}_"
            keyboard = event_status_keyboard(
                event_id, own_player.id, back_page=back_page, locale=locale, note=own_note or ""
            )
        else:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(t("telegram.back_button", locale), callback_data=back),
            ]])
    else:
        if event.team_id and event.season_id:
            pt_rows = (
                db.query(PlayerTeam)
                .filter(
                    PlayerTeam.team_id == event.team_id,
                    PlayerTeam.season_id == event.season_id,
                )
                .all()
            )
            player_ids = {pt.player_id: pt.position for pt in pt_rows}
            players = (
                db.query(Player)
                .filter(Player.id.in_(player_ids.keys()), Player.archived_at.is_(None))
                .order_by(Player.first_name, Player.last_name)
                .all()
            )
            for p in players:
                p._position = player_ids.get(p.id)  # type: ignore[attr-defined]
        else:
            players = (
                db.query(Player)
                .filter(Player.archived_at.is_(None))
                .order_by(Player.first_name, Player.last_name)
                .all()
            )
            for p in players:
                p._position = None  # type: ignore[attr-defined]

        from services.event_text_service import format_attendance_body  # noqa: PLC0415
        text += "\n" + format_attendance_body(
            players, att_by_player, ext_rows, locale, grouped=True, markdown=True
        )

        rows = [
            [InlineKeyboardButton(t("telegram.edit_attendance_button", locale), callback_data=f"evte:{event_id}:0:{back_page}")],
        ]
        rows.append([
            InlineKeyboardButton(t("telegram.notes_button", locale), callback_data=f"evtn:{event_id}:{back_page}"),
            InlineKeyboardButton(t("telegram.externals_button", locale), callback_data=f"evtx:{event_id}:{back_page}"),
        ])
        if msg_count > 0:
            rows.append([InlineKeyboardButton(
                f"💬 Chat ({msg_count})", callback_data=f"ec:{event_id}",
            )])
        rows.append([InlineKeyboardButton(t("telegram.back_button", locale), callback_data=back)])
        keyboard = InlineKeyboardMarkup(rows)

    return text, keyboard


def render_event_chat(user, db, event_id: int, back: str = "el") -> ViewResult:
    from models.event_message import EventMessage  # noqa: PLC0415

    locale = _locale(user)
    event = db.get(Event, event_id)
    if event is None:
        return t("telegram.no_events", locale), InlineKeyboardMarkup([[
            InlineKeyboardButton(t("telegram.back_button", locale), callback_data=back),
        ]])

    messages = (
        db.query(EventMessage)
        .filter(EventMessage.event_id == event_id)
        .order_by(EventMessage.created_at.asc())
        .limit(20)
        .all()
    )

    lines = [f"*💬 {event.title}*\n"]
    if not messages:
        lines.append("_No messages yet_")
    else:
        for msg in messages:
            author = msg.user.username if msg.user else "System"
            lane_icon = "📢" if msg.lane == "announcement" else "💬"
            ts = msg.created_at.strftime("%d %b %H:%M") if msg.created_at else ""
            lines.append(f"{lane_icon} *{author}* _{ts}_")
            lines.append(msg.body)
            lines.append("")

    text = "\n".join(lines)
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(t("telegram.back_button", locale), callback_data=back),
    ]])
    return text, keyboard
