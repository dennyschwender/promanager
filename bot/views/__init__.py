"""bot/views/ — Pure view renderers returning (text, InlineKeyboardMarkup)."""
from __future__ import annotations

from telegram import InlineKeyboardMarkup

ViewResult = tuple[str, InlineKeyboardMarkup]
