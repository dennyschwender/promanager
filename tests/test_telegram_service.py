"""tests/test_telegram_service.py"""
import pytest
from sqlalchemy.orm import Session

from models.player import Player
from models.player_phone import PlayerPhone
from models.user import User
from services.telegram_service import (
    AuthResult,
    find_user_by_phone,
    get_user_by_chat_id,
    link_telegram,
    normalize_phone,
    unlink_telegram,
)


# ── normalize_phone ───────────────────────────────────────────────────────────

def test_normalize_strips_spaces_and_dashes():
    assert normalize_phone("+39 123-456-7890") == "391234567890"


def test_normalize_strips_plus():
    assert normalize_phone("+391234567890") == "391234567890"


def test_normalize_strips_parens():
    assert normalize_phone("(039) 123 4567") == "0391234567"


def test_normalize_digits_only_unchanged():
    assert normalize_phone("391234567890") == "391234567890"


# ── find_user_by_phone ────────────────────────────────────────────────────────

def test_find_user_by_legacy_phone(db):
    user = User(username="u1", email="u1@x.com", hashed_password="x", role="member")
    db.add(user)
    db.flush()
    player = Player(first_name="A", last_name="B", phone="+39 123 456 7890", user_id=user.id)
    db.add(player)
    db.commit()

    found = find_user_by_phone(db, "391234567890")
    assert found is not None
    assert found.id == user.id


def test_find_user_by_player_phone_table(db):
    user = User(username="u2", email="u2@x.com", hashed_password="x", role="member")
    db.add(user)
    db.flush()
    player = Player(first_name="C", last_name="D", user_id=user.id)
    db.add(player)
    db.flush()
    pp = PlayerPhone(player_id=player.id, phone="+39 987 654 3210", label="mobile")
    db.add(pp)
    db.commit()

    found = find_user_by_phone(db, "399876543210")
    assert found is not None
    assert found.id == user.id


def test_find_user_returns_none_when_no_match(db):
    assert find_user_by_phone(db, "0000000000") is None


def test_find_user_returns_none_when_player_has_no_user(db):
    player = Player(first_name="E", last_name="F", phone="111222333")
    db.add(player)
    db.commit()
    assert find_user_by_phone(db, "111222333") is None


# ── link_telegram ─────────────────────────────────────────────────────────────

def test_link_telegram_success(db):
    user = User(username="u3", email="u3@x.com", hashed_password="x", role="member")
    db.add(user)
    db.commit()

    result = link_telegram(db, user, chat_id="111")
    assert result == AuthResult.SUCCESS
    db.refresh(user)
    assert user.telegram_chat_id == "111"


def test_link_telegram_already_this_chat(db):
    user = User(username="u4", email="u4@x.com", hashed_password="x", role="member", telegram_chat_id="222")
    db.add(user)
    db.commit()

    result = link_telegram(db, user, chat_id="222")
    assert result == AuthResult.ALREADY_THIS


def test_link_telegram_conflict_chat_id(db):
    """chat_id already linked to a different user."""
    other = User(username="u5", email="u5@x.com", hashed_password="x", role="member", telegram_chat_id="333")
    user = User(username="u6", email="u6@x.com", hashed_password="x", role="member")
    db.add_all([other, user])
    db.commit()

    result = link_telegram(db, user, chat_id="333")
    assert result == AuthResult.CONFLICT_CHAT


def test_link_telegram_conflict_user_already_linked(db):
    """The target user already has a different chat_id."""
    user = User(username="u7", email="u7@x.com", hashed_password="x", role="member", telegram_chat_id="444")
    db.add(user)
    db.commit()

    result = link_telegram(db, user, chat_id="555")
    assert result == AuthResult.CONFLICT_USER


# ── unlink_telegram ───────────────────────────────────────────────────────────

def test_unlink_telegram(db):
    user = User(username="u8", email="u8@x.com", hashed_password="x", role="member", telegram_chat_id="666")
    db.add(user)
    db.commit()

    unlink_telegram(db, user)
    db.refresh(user)
    assert user.telegram_chat_id is None


# ── get_user_by_chat_id ───────────────────────────────────────────────────────

def test_get_user_by_chat_id_found(db):
    user = User(username="u9", email="u9@x.com", hashed_password="x", role="member", telegram_chat_id="777")
    db.add(user)
    db.commit()

    found = get_user_by_chat_id(db, "777")
    assert found is not None
    assert found.id == user.id


def test_get_user_by_chat_id_not_found(db):
    assert get_user_by_chat_id(db, "999") is None
