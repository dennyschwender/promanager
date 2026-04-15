"""Tests for services/event_text_service.py."""

from datetime import date, time

import pytest

from models.attendance import Attendance
from models.event import Event
from models.event_external import EventExternal
from models.player import Player
from models.player_team import PlayerTeam
from models.season import Season
from models.team import Team
from services.event_text_service import format_attendance_body, format_attendance_text


# ---------------------------------------------------------------------------
# format_attendance_body
# ---------------------------------------------------------------------------


def _make_player(id_, first, last, position=None):
    p = Player(id=id_, first_name=first, last_name=last)
    p._position = position
    return p


def _make_att(player_id, status, note=None):
    return Attendance(player_id=player_id, status=status, note=note)


def _make_ext(id_, first, last, status, note=None):
    return EventExternal(id=id_, first_name=first, last_name=last, status=status, note=note)


def test_body_position_counts_grouped():
    players = [
        _make_player(1, "Alice", "A", "goalie"),
        _make_player(2, "Bob", "B", "goalie"),
        _make_player(3, "Carl", "C", "defender"),
    ]
    att = {
        1: _make_att(1, "present"),
        2: _make_att(2, "present"),
        3: _make_att(3, "present"),
    }
    result = format_attendance_body(players, att, [], "en", grouped=True, markdown=False)
    assert "Goalies (2)" in result
    assert "Defenders (1)" in result
    assert "Alice A" in result
    assert "Carl C" in result


def test_body_externals_integrated_by_status():
    players = [_make_player(1, "Dave", "D", "forward")]
    att = {1: _make_att(1, "present")}
    exts = [
        _make_ext(10, "Eve", "E", "present"),
        _make_ext(11, "Frank", "F", "absent"),
    ]
    result = format_attendance_body(players, att, exts, "en", grouped=True, markdown=False)
    # Eve (present external) should appear BEFORE the absent section
    assert "👤 Eve E" in result
    assert "👤 Frank F" in result
    present_idx = result.index("✓ Present")
    absent_idx = result.index("✗ Absent")
    eve_idx = result.index("👤 Eve E")
    frank_idx = result.index("👤 Frank F")
    assert present_idx < eve_idx < absent_idx
    assert absent_idx < frank_idx


def test_body_no_externals_block_header():
    """No separate 'Externals' heading should appear."""
    players = [_make_player(1, "Alice", "A", "goalie")]
    att = {1: _make_att(1, "present")}
    exts = [_make_ext(10, "Eve", "E", "present")]
    result = format_attendance_body(players, att, exts, "en", grouped=True, markdown=False)
    assert "Externals" not in result


def test_body_flat_list_no_position_headers():
    players = [
        _make_player(1, "Alice", "A", "goalie"),
        _make_player(2, "Bob", "B", "defender"),
    ]
    att = {
        1: _make_att(1, "present"),
        2: _make_att(2, "present"),
    }
    result = format_attendance_body(players, att, [], "en", grouped=False, markdown=False)
    assert "Goalies" not in result
    assert "Defenders" not in result
    assert "Alice A" in result
    assert "Bob B" in result


def test_body_markdown_bold_italic():
    players = [_make_player(1, "Alice", "A", "goalie")]
    att = {1: _make_att(1, "present")}
    result = format_attendance_body(players, att, [], "en", grouped=True, markdown=True)
    assert "*" in result   # bold status header
    assert "_Goalies" in result  # italic position label


def test_body_skips_empty_statuses():
    players = [_make_player(1, "Alice", "A")]
    att = {1: _make_att(1, "present")}
    result = format_attendance_body(players, att, [], "en", grouped=True, markdown=False)
    assert "✗ Absent" not in result
    assert "? Unknown" not in result


def test_body_player_note_included():
    players = [_make_player(1, "Alice", "A", "goalie")]
    att = {1: _make_att(1, "present", note="knee injury")}
    result = format_attendance_body(players, att, [], "en", grouped=True, markdown=False)
    assert "knee injury" in result


# ---------------------------------------------------------------------------
# format_attendance_text  (integration — needs a real DB session)
# ---------------------------------------------------------------------------


def test_format_attendance_text_header(db):
    team = Team(name="T1")
    season = Season(name="S1", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.add_all([team, season])
    db.commit()

    event = Event(
        title="NLB Final",
        event_type="match",
        event_date=date(2026, 4, 16),
        event_time=time(19, 30),
        event_end_time=time(22, 0),
        location="SAM Bellinzona",
        team_id=team.id,
        season_id=season.id,
    )
    db.add(event)
    db.commit()

    player = Player(first_name="Alex", last_name="Smith")
    db.add(player)
    db.commit()

    db.add(PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id, position="goalie"))
    db.add(Attendance(event_id=event.id, player_id=player.id, status="present"))
    db.commit()

    result = format_attendance_text(db, event, "en", grouped=True, markdown=False)

    assert "NLB Final" in result
    assert "2026-04-16" in result
    assert "19:30" in result
    assert "22:00" in result
    assert "SAM Bellinzona" in result
    assert "Attendance:" in result
    assert "Alex Smith" in result
    assert "Goalies (1)" in result


def test_format_attendance_text_external_in_status(db):
    team = Team(name="T2")
    season = Season(name="S2", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.add_all([team, season])
    db.commit()

    event = Event(
        title="Training",
        event_type="training",
        event_date=date(2026, 4, 20),
        team_id=team.id,
        season_id=season.id,
    )
    db.add(event)
    db.commit()

    ext = EventExternal(event_id=event.id, first_name="Mauro", last_name="Ochsner", status="present")
    db.add(ext)
    db.commit()

    result = format_attendance_text(db, event, "en", grouped=True, markdown=False)
    assert "👤 Mauro Ochsner" in result
    assert "Externals" not in result  # no separate block
