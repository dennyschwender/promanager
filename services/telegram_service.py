"""services/telegram_service.py — Telegram bot authentication helpers."""

from __future__ import annotations

import re
from enum import Enum, auto

from sqlalchemy.orm import Session

from models.player import Player
from models.player_phone import PlayerPhone
from models.user import User


class AuthResult(Enum):
    SUCCESS = auto()
    ALREADY_THIS = auto()  # same chat_id already linked to this user
    CONFLICT_CHAT = auto()  # chat_id linked to a different user
    CONFLICT_USER = auto()  # user already linked to a different chat_id


def normalize_phone(phone: str) -> str:
    """Strip all non-digit characters (including leading +) for comparison."""
    return re.sub(r"\D", "", phone)


def find_user_by_phone(db: Session, telegram_phone: str) -> User | None:
    """Return the User whose linked player has a matching phone number.

    `telegram_phone` is already normalized (digits only, no +).
    Searches both Player.phone (legacy) and PlayerPhone rows.
    Returns None if no match or if the matched player has no linked user.
    """
    norm = normalize_phone(telegram_phone)
    if not norm:
        return None

    # Search legacy Player.phone
    players = db.query(Player).filter(Player.phone.isnot(None)).all()
    for player in players:
        if normalize_phone(player.phone) == norm and player.user_id is not None:
            return db.get(User, player.user_id)

    # Search PlayerPhone table
    phone_rows = db.query(PlayerPhone).all()
    for row in phone_rows:
        if normalize_phone(row.phone) == norm:
            player = db.get(Player, row.player_id)
            if player and player.user_id is not None:
                return db.get(User, player.user_id)

    return None


def link_telegram(db: Session, user: User, chat_id: str) -> AuthResult:
    """Try to link `chat_id` to `user`. Returns an AuthResult indicating outcome.

    Commits on SUCCESS.
    """
    # Already linked to this same chat
    if user.telegram_chat_id == chat_id:
        return AuthResult.ALREADY_THIS

    # User already linked to a different chat
    if user.telegram_chat_id is not None and user.telegram_chat_id != chat_id:
        return AuthResult.CONFLICT_USER

    # chat_id already linked to a different user
    existing = db.query(User).filter(User.telegram_chat_id == chat_id).first()
    if existing is not None and existing.id != user.id:
        return AuthResult.CONFLICT_CHAT

    user.telegram_chat_id = chat_id
    db.add(user)
    db.commit()
    return AuthResult.SUCCESS


def unlink_telegram(db: Session, user: User) -> None:
    """Remove the Telegram link from a user."""
    user.telegram_chat_id = None
    db.add(user)
    db.commit()


def get_user_by_chat_id(db: Session, chat_id: str) -> User | None:
    """Return the User linked to this Telegram chat ID, or None."""
    return db.query(User).filter(User.telegram_chat_id == str(chat_id)).first()
