"""Tests for services/notification_service.py."""
from __future__ import annotations

import pytest
from models.notification import Notification
from models.notification_preference import NotificationPreference, CHANNELS
from models.player import Player
from models.team import Team
from models.event import Event
from models.season import Season
from models.attendance import Attendance
import datetime
from services.notification_service import (
    create_default_preferences,
    get_preference,
    send_notifications,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def season(db):
    s = Season(name="2026", is_active=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@pytest.fixture()
def team(db, season):
    t = Team(name="Eagles", season_id=season.id)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@pytest.fixture()
def player(db, team):
    from models.player_team import PlayerTeam
    p = Player(first_name="Alice", last_name="Smith", email="alice@test.com",
               is_active=True)
    db.add(p)
    db.flush()
    db.add(PlayerTeam(
        player_id=p.id, team_id=team.id, priority=1,
        role="player", membership_status="active", absent_by_default=False,
    ))
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture()
def event(db, season, team):
    e = Event(title="Match", event_type="match", event_date=datetime.date(2026, 4, 1),
              season_id=season.id, team_id=team.id)
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


# ── create_default_preferences ────────────────────────────────────────────────

def test_create_default_preferences_creates_all_channels(db, player):
    create_default_preferences(player.id, db)
    prefs = db.query(NotificationPreference).filter(
        NotificationPreference.player_id == player.id
    ).all()
    assert {p.channel for p in prefs} == set(CHANNELS)
    assert all(p.enabled for p in prefs)


def test_create_default_preferences_idempotent(db, player):
    create_default_preferences(player.id, db)
    create_default_preferences(player.id, db)  # second call must not raise
    prefs = db.query(NotificationPreference).filter(
        NotificationPreference.player_id == player.id
    ).all()
    assert len(prefs) == len(CHANNELS)


# ── get_preference ─────────────────────────────────────────────────────────────

def test_get_preference_returns_true_when_enabled(db, player):
    create_default_preferences(player.id, db)
    assert get_preference(player.id, "email", db) is True


def test_get_preference_returns_true_when_missing(db, player):
    # No preferences created — defaults to True
    assert get_preference(player.id, "email", db) is True


def test_get_preference_returns_false_when_disabled(db, player):
    create_default_preferences(player.id, db)
    pref = db.query(NotificationPreference).filter(
        NotificationPreference.player_id == player.id,
        NotificationPreference.channel == "email",
    ).one()
    pref.enabled = False
    db.commit()
    assert get_preference(player.id, "email", db) is False


# ── send_notifications ────────────────────────────────────────────────────────

def test_send_creates_notification_rows(db, player, event):
    create_default_preferences(player.id, db)
    result = send_notifications(
        event=event,
        title="Test",
        body="Body",
        tag="direct",
        recipient_statuses=None,  # all
        admin_channels=["inapp"],
        db=db,
        background_tasks=None,
    )
    assert result["queued"] >= 1
    # _dispatch opens its own session — expire the test session to see committed rows
    db.expire_all()
    notifs = db.query(Notification).filter(Notification.player_id == player.id).all()
    assert len(notifs) == 1
    assert notifs[0].title == "Test"
    assert notifs[0].tag == "direct"


def test_send_skips_disabled_channel(db, player, event):
    create_default_preferences(player.id, db)
    # Disable inapp for player
    pref = db.query(NotificationPreference).filter(
        NotificationPreference.player_id == player.id,
        NotificationPreference.channel == "inapp",
    ).one()
    pref.enabled = False
    db.commit()

    result = send_notifications(
        event=event,
        title="Test",
        body="Body",
        tag="direct",
        recipient_statuses=None,
        admin_channels=["inapp"],
        db=db,
        background_tasks=None,
    )
    # Notification row is still created (for inbox persistence) even if channel skipped
    db.expire_all()
    notifs = db.query(Notification).filter(Notification.player_id == player.id).all()
    assert len(notifs) == 1
    assert result["queued"] == 1


def test_send_filters_by_attendance_status(db, player, event):
    create_default_preferences(player.id, db)
    # Give player an "absent" attendance record
    att = Attendance(event_id=event.id, player_id=player.id, status="absent")
    db.add(att)
    db.commit()

    # Only target "present" players — player should be excluded
    result = send_notifications(
        event=event,
        title="Test",
        body="Body",
        tag="direct",
        recipient_statuses=["present"],
        admin_channels=["inapp"],
        db=db,
        background_tasks=None,
    )
    assert result["queued"] == 0
    db.expire_all()
    notifs = db.query(Notification).filter(Notification.player_id == player.id).all()
    assert len(notifs) == 0


def test_send_event_without_team_targets_active_players(db, event, player):
    """When event has no team, all active players receive the notification."""
    event.team_id = None
    db.commit()
    create_default_preferences(player.id, db)

    result = send_notifications(
        event=event,
        title="Test",
        body="Body",
        tag="announcement",
        recipient_statuses=None,
        admin_channels=["inapp"],
        db=db,
        background_tasks=None,
    )
    assert result["queued"] >= 1
