"""bot/keyboards.py — Inline keyboard builders for the Telegram bot."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from models.attendance import Attendance
from models.event import Event
from models.player import Player

PAGE_SIZE = 5
PLAYER_PAGE_SIZE = 10


def events_keyboard(events: list[Event], page: int, total_pages: int) -> InlineKeyboardMarkup:
    """One row per event with a View button, plus Prev/Next navigation."""
    rows = []
    for event in events:
        label = f"{event.event_date} — {event.title}"
        rows.append([InlineKeyboardButton(label, callback_data=f"evt:{event.id}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("← Prev", callback_data=f"evts:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next →", callback_data=f"evts:{page + 1}"))
    if nav:
        rows.append(nav)

    return InlineKeyboardMarkup(rows)


def event_status_keyboard(event_id: int, player_id: int, back_page: int = 0) -> InlineKeyboardMarkup:
    """Status buttons for a single player (member self-service)."""
    rows = [
        [
            InlineKeyboardButton("✓ Present", callback_data=f"sta:{event_id}:{player_id}:p"),
            InlineKeyboardButton("✗ Absent", callback_data=f"sta:{event_id}:{player_id}:a"),
            InlineKeyboardButton("? Unknown", callback_data=f"sta:{event_id}:{player_id}:u"),
        ],
        [InlineKeyboardButton("← Back", callback_data=f"evts:{back_page}")],
    ]
    return InlineKeyboardMarkup(rows)


def event_admin_keyboard(
    event_id: int,
    players: list[Player],
    attendances: dict[int, Attendance],
    page: int,
    total_pages: int,
    back_page: int = 0,
) -> InlineKeyboardMarkup:
    """Player list with per-player status buttons for coaches/admins."""
    STATUS_ICON = {"present": "✓", "absent": "✗", "unknown": "?", "maybe": "~"}
    rows = []
    for player in players:
        att = attendances.get(player.id)
        current = att.status if att else "unknown"
        icon = STATUS_ICON.get(current, "?")
        name_btn = InlineKeyboardButton(
            f"{icon} {player.full_name}",
            callback_data="noop",
        )
        rows.append([
            name_btn,
            InlineKeyboardButton("✓", callback_data=f"sta:{event_id}:{player.id}:p"),
            InlineKeyboardButton("✗", callback_data=f"sta:{event_id}:{player.id}:a"),
            InlineKeyboardButton("?", callback_data=f"sta:{event_id}:{player.id}:u"),
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("← Players prev", callback_data=f"evtp:{event_id}:{page - 1}:{back_page}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Players next →", callback_data=f"evtp:{event_id}:{page + 1}:{back_page}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("← Back to Events", callback_data=f"evts:{back_page}")])
    return InlineKeyboardMarkup(rows)
