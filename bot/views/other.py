"""bot/views/other.py — 'Other' menu view renderer."""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import t
from bot.views import ViewResult


def render_other(user, locale: str = "en") -> ViewResult:
    """Other mini-menu: entry point to absences + back home."""
    text = t("telegram.other_button", locale)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("telegram.absences_button", locale), callback_data="ab")],
        [InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home")],
    ])
    return text, keyboard
