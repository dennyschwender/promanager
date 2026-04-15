"""Unit tests for bot/absence_keyboards.py."""

from types import SimpleNamespace

import pytest

from bot.absence_keyboards import (
    absence_delete_confirm_keyboard,
    absence_list_keyboard,
    absence_player_list_keyboard,
    other_menu_keyboard,
)


def _cb_data(keyboard):
    """Flatten all callback_data values from an InlineKeyboardMarkup."""
    return [btn.callback_data for row in keyboard.inline_keyboard for btn in row]


# ---------------------------------------------------------------------------
# other_menu_keyboard
# ---------------------------------------------------------------------------


def test_other_menu_has_absences_and_back():
    kb = other_menu_keyboard(back_page=2, locale="en")
    data = _cb_data(kb)
    assert any(d.startswith("absm:2") for d in data)
    assert any(d == "evts:2" for d in data)


# ---------------------------------------------------------------------------
# absence_player_list_keyboard
# ---------------------------------------------------------------------------


def _make_player(id_, name):
    p = SimpleNamespace(id=id_, full_name=name)
    return p


def test_player_list_keyboard_buttons():
    players = [_make_player(1, "Alice"), _make_player(2, "Bob")]
    kb = absence_player_list_keyboard(players, page=0, total_pages=1, back_page=3, locale="en")
    data = _cb_data(kb)
    assert "absl:1:0:3" in data
    assert "absl:2:0:3" in data
    assert "other:3" in data


def test_player_list_keyboard_pagination():
    players = [_make_player(i, f"P{i}") for i in range(3)]
    kb = absence_player_list_keyboard(players, page=1, total_pages=3, back_page=0, locale="en")
    data = _cb_data(kb)
    assert any(d.startswith("absp:0:") for d in data)  # Prev
    assert any(d.startswith("absp:2:") for d in data)  # Next


def test_player_list_no_prev_on_first_page():
    players = [_make_player(1, "Alice")]
    kb = absence_player_list_keyboard(players, page=0, total_pages=2, back_page=0, locale="en")
    data = _cb_data(kb)
    # No prev button when on page 0 (page-1 = -1 is never added)
    assert not any(d == "absp:-1:0" for d in data)


# ---------------------------------------------------------------------------
# absence_list_keyboard
# ---------------------------------------------------------------------------


def _make_absence(id_, start, end):
    return SimpleNamespace(id=id_, start_date=start, end_date=end)


def test_absence_list_has_delete_add_back_member():
    absences = [_make_absence(10, "2026-05-01", "2026-05-05")]
    kb = absence_list_keyboard(
        absences, player_id=7, page=0, total_pages=1,
        back_page=2, is_member=True, locale="en"
    )
    data = _cb_data(kb)
    assert "absd:10:7:0:2" in data          # delete button
    assert "absa:7:2" in data               # add button
    assert "other:2" in data               # back → Other menu for member


def test_absence_list_back_goes_to_player_list_for_coach():
    kb = absence_list_keyboard(
        [], player_id=5, page=0, total_pages=1,
        back_page=1, is_member=False, locale="en"
    )
    data = _cb_data(kb)
    assert "absm:1" in data                # back → player list for coach


def test_absence_list_pagination():
    absences = [_make_absence(i, f"2026-05-{i:02d}", f"2026-05-{i+1:02d}") for i in range(1, 4)]
    kb = absence_list_keyboard(
        absences, player_id=3, page=1, total_pages=3,
        back_page=0, is_member=False, locale="en"
    )
    data = _cb_data(kb)
    assert "absl:3:0:0" in data   # Prev
    assert "absl:3:2:0" in data   # Next


# ---------------------------------------------------------------------------
# absence_delete_confirm_keyboard
# ---------------------------------------------------------------------------


def test_delete_confirm_keyboard():
    kb = absence_delete_confirm_keyboard(
        absence_id=99, player_id=7, page=0, back_page=2, locale="en"
    )
    data = _cb_data(kb)
    assert "absdc:99:7:0:2" in data   # confirm
    assert "absl:7:0:2" in data       # cancel → back to list
