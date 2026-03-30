"""bot/keyboards.py — Inline keyboard builders for the Telegram bot."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import t
from models.attendance import Attendance
from models.event import Event
from models.player import Player

PAGE_SIZE = 5
PLAYER_PAGE_SIZE = 10

# Display icon per attendance status. "maybe" can be displayed but is not offered
# as an action button — the bot simplifies the UI to present/absent/unknown only.
STATUS_ICON: dict[str, str] = {"present": "✓", "absent": "✗", "unknown": "?", "maybe": "~"}


def events_keyboard(events: list[Event], page: int, total_pages: int, locale: str = "en") -> InlineKeyboardMarkup:
    """One row per event with a View button, plus Prev/Next/Refresh navigation."""
    rows = []
    for event in events:
        label = f"{event.event_date} — {event.title}"
        rows.append([InlineKeyboardButton(label, callback_data=f"evt:{event.id}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(t("telegram.prev_button", locale), callback_data=f"evts:{page - 1}"))
    nav.append(InlineKeyboardButton(t("telegram.refresh_button", locale), callback_data=f"ref:{page}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(t("telegram.view_more_button", locale), callback_data=f"evts:{page + 1}"))
    rows.append(nav)

    return InlineKeyboardMarkup(rows)


def event_view_keyboard(event_id: int, back_page: int = 0, locale: str = "en", is_privileged: bool = False) -> InlineKeyboardMarkup:
    """Read-only event detail keyboard: Modify Attendance + Back."""
    rows = [
        [InlineKeyboardButton(t("telegram.edit_attendance_button", locale), callback_data=f"evte:{event_id}:0:{back_page}")],
    ]
    if is_privileged:
        rows.append([
            InlineKeyboardButton(t("telegram.notes_button", locale), callback_data=f"evtn:{event_id}:{back_page}"),
            InlineKeyboardButton(t("telegram.externals_button", locale), callback_data=f"evtx:{event_id}:{back_page}"),
        ])
    rows.append([InlineKeyboardButton(t("telegram.back_button", locale), callback_data=f"evts:{back_page}")])
    return InlineKeyboardMarkup(rows)


def event_status_keyboard(
    event_id: int, player_id: int, back_page: int = 0, locale: str = "en", note: str = ""
) -> InlineKeyboardMarkup:
    """Status buttons for a single player (member self-service).

    Offers present/absent/unknown — "maybe" is intentionally omitted for simplicity.
    """
    note_label = t("telegram.note_button", locale)
    if note:
        note_label += " ✓"
    rows = [
        [
            InlineKeyboardButton(t("telegram.status_present", locale), callback_data=f"sta:{event_id}:{player_id}:p"),
            InlineKeyboardButton(t("telegram.status_absent", locale), callback_data=f"sta:{event_id}:{player_id}:a"),
            InlineKeyboardButton(t("telegram.status_unknown", locale), callback_data=f"sta:{event_id}:{player_id}:u"),
        ],
        [InlineKeyboardButton(note_label, callback_data=f"note:{event_id}:{player_id}:{back_page}")],
        [InlineKeyboardButton(t("telegram.back_button", locale), callback_data=f"evts:{back_page}")],
    ]
    return InlineKeyboardMarkup(rows)


def event_admin_keyboard(
    event_id: int,
    players: list[Player],
    attendances: dict[int, Attendance],
    page: int,
    total_pages: int,
    back_page: int = 0,
    locale: str = "en",
) -> InlineKeyboardMarkup:
    """Player list with per-player status buttons for coaches/admins.

    Action buttons offer present/absent/unknown — "maybe" is intentionally omitted.
    """
    rows = []
    for player in players:
        att = attendances.get(player.id)
        current = att.status if att else "unknown"
        icon = STATUS_ICON.get(current, "?")
        name_btn = InlineKeyboardButton(
            f"{icon} {player.full_name}",
            callback_data="noop",
        )
        rows.append(
            [
                name_btn,
                InlineKeyboardButton("✓", callback_data=f"sta:{event_id}:{player.id}:p"),
                InlineKeyboardButton("✗", callback_data=f"sta:{event_id}:{player.id}:a"),
                InlineKeyboardButton("?", callback_data=f"sta:{event_id}:{player.id}:u"),
            ]
        )

    nav = []
    if page > 0:
        nav.append(
            InlineKeyboardButton(
                t("telegram.prev_button", locale), callback_data=f"evte:{event_id}:{page - 1}:{back_page}"
            )
        )
    if page < total_pages - 1:
        nav.append(
            InlineKeyboardButton(
                t("telegram.next_button", locale), callback_data=f"evte:{event_id}:{page + 1}:{back_page}"
            )
        )
    if nav:
        rows.append(nav)

    # Back returns to view mode (not the events list)
    rows.append([InlineKeyboardButton(t("telegram.back_button", locale), callback_data=f"evtp:{event_id}:0:{back_page}")])
    return InlineKeyboardMarkup(rows)
