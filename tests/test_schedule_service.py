"""Unit tests for services/schedule_service.py."""
from __future__ import annotations

from datetime import date, time
from unittest.mock import patch

import pytest

from services.schedule_service import (
    advance_date,
    delete_future_events,
    generate_events_for_schedule,
    is_changed,
    sign_payload,
    verify_payload,
)

# ── advance_date ────────────────────────────────────────────────────────────

def test_advance_date_weekly():
    assert advance_date(date(2026, 3, 10), "weekly") == date(2026, 3, 17)


def test_advance_date_biweekly():
    assert advance_date(date(2026, 3, 10), "biweekly") == date(2026, 3, 24)


def test_advance_date_monthly_same_day():
    assert advance_date(date(2026, 3, 15), "monthly") == date(2026, 4, 15)


def test_advance_date_monthly_caps_to_last_day():
    assert advance_date(date(2026, 1, 31), "monthly") == date(2026, 2, 28)


def test_advance_date_monthly_december_to_january():
    assert advance_date(date(2026, 12, 15), "monthly") == date(2027, 1, 15)


# ── is_changed ──────────────────────────────────────────────────────────────

def test_is_changed_returns_false_when_identical(db):
    from models.team_recurring_schedule import TeamRecurringSchedule
    sched = TeamRecurringSchedule(
        team_id=1, title="T", event_type="training", recurrence_rule="weekly",
        start_date=date(2026, 3, 10), end_date=date(2026, 6, 30),
        event_time=time(18, 0), presence_type="normal",
        recurrence_group_id="test-uuid",
    )
    submitted = {
        "start_date": "2026-03-10", "end_date": "2026-06-30",
        "recurrence_rule": "weekly", "event_type": "training",
        "event_time": "18:00", "event_end_time": "",
        "location": "", "meeting_time": "", "meeting_location": "",
        "presence_type": "normal",
    }
    assert is_changed(sched, submitted) is False


def test_is_changed_detects_time_change(db):
    from models.team_recurring_schedule import TeamRecurringSchedule
    sched = TeamRecurringSchedule(
        team_id=1, title="T", event_type="training", recurrence_rule="weekly",
        start_date=date(2026, 3, 10), event_time=time(18, 0),
        presence_type="normal", recurrence_group_id="uuid1",
    )
    submitted = {
        "start_date": "2026-03-10", "end_date": "", "recurrence_rule": "weekly",
        "event_type": "training", "event_time": "19:00", "event_end_time": "",
        "location": "", "meeting_time": "", "meeting_location": "",
        "presence_type": "normal",
    }
    assert is_changed(sched, submitted) is True


def test_is_changed_ignores_description(db):
    from models.team_recurring_schedule import TeamRecurringSchedule
    sched = TeamRecurringSchedule(
        team_id=1, title="T", event_type="training", recurrence_rule="weekly",
        start_date=date(2026, 3, 10), presence_type="normal",
        description="old desc", recurrence_group_id="uuid2",
    )
    submitted = {
        "start_date": "2026-03-10", "end_date": "", "recurrence_rule": "weekly",
        "event_type": "training", "event_time": "", "event_end_time": "",
        "location": "", "meeting_time": "", "meeting_location": "",
        "presence_type": "normal",
        "description": "new desc",  # changed, but not a key field
    }
    assert is_changed(sched, submitted) is False


# ── generate_events_for_schedule ────────────────────────────────────────────

def test_generate_events_weekly(db):
    from models.team import Team
    from models.team_recurring_schedule import TeamRecurringSchedule

    team = Team(name="Eagles")
    db.add(team)
    db.commit()
    db.refresh(team)

    sched = TeamRecurringSchedule(
        team_id=team.id, title="Eagles - Training Tuesday",
        event_type="training", recurrence_rule="weekly",
        start_date=date(2026, 3, 3), end_date=date(2026, 3, 24),
        presence_type="normal", recurrence_group_id="gen-uuid-1",
    )
    db.add(sched)
    db.commit()

    with patch("services.schedule_service.ensure_attendance_records"):
        events = generate_events_for_schedule(db, sched, team)

    assert len(events) == 4
    assert events[0].event_date == date(2026, 3, 3)
    assert events[3].event_date == date(2026, 3, 24)
    assert all(e.recurrence_group_id == "gen-uuid-1" for e in events)


def test_generate_events_uses_season_end_date(db):
    """Teams are no longer linked to seasons; schedule must have its own end_date."""
    from models.team import Team
    from models.team_recurring_schedule import TeamRecurringSchedule

    team = Team(name="Lions")
    db.add(team)
    db.commit()
    db.refresh(team)

    sched = TeamRecurringSchedule(
        team_id=team.id, title="T", event_type="training",
        recurrence_rule="weekly", start_date=date(2026, 3, 3),
        end_date=date(2026, 3, 17),  # explicit end date required
        presence_type="normal", recurrence_group_id="gen-uuid-2",
    )
    db.add(sched)
    db.commit()

    with patch("services.schedule_service.ensure_attendance_records"):
        events = generate_events_for_schedule(db, sched, team)

    assert len(events) == 3  # Mar 3, 10, 17


def test_generate_events_raises_without_end_date(db):
    from models.team import Team
    from models.team_recurring_schedule import TeamRecurringSchedule

    team = Team(name="Bears")
    db.add(team)
    db.commit()
    db.refresh(team)

    sched = TeamRecurringSchedule(
        team_id=team.id, title="T", event_type="training",
        recurrence_rule="weekly", start_date=date(2026, 3, 3),
        end_date=None, presence_type="normal", recurrence_group_id="gen-uuid-3",
    )
    db.add(sched)
    db.commit()

    with pytest.raises(ValueError, match="end date"):
        generate_events_for_schedule(db, sched, team)


def test_generate_events_raises_start_after_end(db):
    from models.team import Team
    from models.team_recurring_schedule import TeamRecurringSchedule

    team = Team(name="Wolves")
    db.add(team)
    db.commit()
    db.refresh(team)

    sched = TeamRecurringSchedule(
        team_id=team.id, title="T", event_type="training",
        recurrence_rule="weekly", start_date=date(2026, 4, 1),
        end_date=date(2026, 3, 1), presence_type="normal",
        recurrence_group_id="gen-uuid-4",
    )
    db.add(sched)
    db.commit()

    with pytest.raises(ValueError, match="on or before"):
        generate_events_for_schedule(db, sched, team)


# ── delete_future_events ────────────────────────────────────────────────────

def test_past_events_not_deleted(db):
    from models.event import Event

    past_ev = Event(
        title="Old", event_type="training",
        event_date=date(2026, 1, 1),
        recurrence_group_id="del-uuid-1",
    )
    future_ev = Event(
        title="Future", event_type="training",
        event_date=date(2099, 1, 1),
        recurrence_group_id="del-uuid-1",
    )
    db.add_all([past_ev, future_ev])
    db.commit()

    count = delete_future_events(db, "del-uuid-1")
    db.commit()

    assert count == 1
    remaining = db.query(Event).filter(Event.recurrence_group_id == "del-uuid-1").all()
    assert len(remaining) == 1
    assert remaining[0].event_date == date(2026, 1, 1)


# ── sign_payload / verify_payload ───────────────────────────────────────────

def test_sign_and_verify_roundtrip():
    data = {"schedules": [{"id": 1, "title": "Training"}]}
    token = sign_payload(data)
    result = verify_payload(token)
    assert result["schedules"][0]["title"] == "Training"


def test_verify_rejects_tampered_payload():
    token = sign_payload({"x": 1})
    tampered = token[:-4] + "0000"
    with pytest.raises(ValueError):
        verify_payload(tampered)


def test_verify_rejects_malformed_token():
    with pytest.raises(ValueError):
        verify_payload("notvalid")
