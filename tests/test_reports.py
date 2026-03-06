from datetime import date
"""Tests for /reports routes and report service helpers."""
import pytest
from models.attendance import Attendance
from models.event import Event
from models.player import Player
from models.season import Season
from services.attendance_service import get_season_attendance_stats, set_attendance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_season(db, name="Test Season"):
    season = Season(name=name, is_active=False)
    db.add(season)
    db.commit()
    db.refresh(season)
    return season


def _make_event(db, season_id, title="Report Event", event_date=date(2026, 3, 1)):
    event = Event(
        title=title,
        event_type="training",
        event_date=event_date,
        season_id=season_id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def _make_player(db, first="Rep", last="Player"):
    player = Player(first_name=first, last_name=last, is_active=True)
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


# ---------------------------------------------------------------------------
# Season report page
# ---------------------------------------------------------------------------


def test_season_report(admin_client, db):
    season = _make_season(db, name="Report Season")
    resp = admin_client.get(f"/reports/season/{season.id}", follow_redirects=False)
    assert resp.status_code == 200


def test_season_report_redirects_for_missing_season(admin_client):
    resp = admin_client.get("/reports/season/99999", follow_redirects=False)
    assert resp.status_code == 302


def test_season_report_requires_login(client, db):
    season = _make_season(db, name="Auth Report Season")
    resp = client.get(f"/reports/season/{season.id}", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Player report page
# ---------------------------------------------------------------------------


def test_player_report(admin_client, db):
    player = _make_player(db, "Rep", "PlayerDetail")
    resp = admin_client.get(f"/reports/player/{player.id}", follow_redirects=False)
    assert resp.status_code == 200


def test_player_report_redirects_for_missing_player(admin_client):
    resp = admin_client.get("/reports/player/99999", follow_redirects=False)
    assert resp.status_code == 302


# ---------------------------------------------------------------------------
# Service-level stats
# ---------------------------------------------------------------------------


def test_season_stats_counts(db):
    season = _make_season(db, name="Stats Season")
    e1 = _make_event(db, season.id, title="Event 1", event_date=date(2026, 3, 1))
    e2 = _make_event(db, season.id, title="Event 2", event_date=date(2026, 3, 8))

    player = _make_player(db, "Stats", "Player")

    set_attendance(db, e1.id, player.id, "present")
    set_attendance(db, e2.id, player.id, "absent")

    stats = get_season_attendance_stats(db, season.id)

    # There should be exactly one player entry
    assert len(stats) == 1
    entry = stats[0]
    assert entry["present_count"] == 1
    assert entry["absent_count"] == 1
    assert entry["total_events"] == 2


def test_season_stats_empty_season(db):
    season = _make_season(db, name="Empty Season")
    stats = get_season_attendance_stats(db, season.id)
    assert stats == []
