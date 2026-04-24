"""bot/absence_keyboards.py — Inline keyboard builders for absence management."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import t

ABSENCE_PAGE_SIZE = 8
PLAYER_PAGE_SIZE = 10


def other_menu_keyboard(back_page: int, locale: str = "en") -> InlineKeyboardMarkup:
    """'⚙️ Other' mini-menu: Absences entry + Back to events list."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("telegram.absences_button", locale), callback_data=f"absm:{back_page}")],
        [InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home")],
    ])


def absence_player_list_keyboard(
    players: list,
    page: int,
    total_pages: int,
    back_page: int,
    locale: str = "en",
) -> InlineKeyboardMarkup:
    """Paginated player list for coach/admin absence selection.

    Each player button navigates to their absence list (page 0).
    Pagination uses ``absp:{page}:{back_page}`` callbacks.
    Back returns to the Other menu.
    """
    rows = []
    for player in players:
        rows.append([
            InlineKeyboardButton(
                player.full_name,
                callback_data=f"absl:{player.id}:0:{back_page}",
            )
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            t("telegram.prev_button", locale),
            callback_data=f"absp:{page - 1}:{back_page}",
        ))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(
            t("telegram.next_button", locale),
            callback_data=f"absp:{page + 1}:{back_page}",
        ))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(
        t("telegram.back_button", locale),
        callback_data="other:0",
    )])
    return InlineKeyboardMarkup(rows)


def absence_list_keyboard(
    absences: list,
    player_id: int,
    page: int,
    total_pages: int,
    back_page: int,
    is_member: bool,
    locale: str = "en",
) -> InlineKeyboardMarkup:
    """One delete button per absence, Add button, pagination, and Back.

    Back destination differs by role:
    - Member → ``other:{back_page}`` (Other menu, since absm: skips player list)
    - Coach/Admin → ``absm:{back_page}`` (player list)
    """
    rows = []
    for absence in absences:
        dates = f"{absence.start_date} → {absence.end_date}"
        rows.append([InlineKeyboardButton(
            t("telegram.absence_del_button", locale, dates=dates),
            callback_data=f"absd:{absence.id}:{player_id}:{page}:{back_page}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            t("telegram.prev_button", locale),
            callback_data=f"absl:{player_id}:{page - 1}:{back_page}",
        ))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(
            t("telegram.next_button", locale),
            callback_data=f"absl:{player_id}:{page + 1}:{back_page}",
        ))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(
        t("telegram.absence_add_button", locale),
        callback_data=f"absa:{player_id}:{back_page}",
    )])

    back_dest = "other:0" if is_member else f"absm:{back_page}"
    rows.append([InlineKeyboardButton(
        t("telegram.back_button", locale),
        callback_data=back_dest,
    )])
    return InlineKeyboardMarkup(rows)


def absence_delete_confirm_keyboard(
    absence_id: int,
    player_id: int,
    page: int,
    back_page: int,
    locale: str = "en",
) -> InlineKeyboardMarkup:
    """Yes/No confirmation before deleting an absence."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            t("telegram.absence_confirm_yes", locale),
            callback_data=f"absdc:{absence_id}:{player_id}:{page}:{back_page}",
        ),
        InlineKeyboardButton(
            t("telegram.absence_confirm_no", locale),
            callback_data=f"absl:{player_id}:{page}:{back_page}",
        ),
    ]])
