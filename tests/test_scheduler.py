"""Tests for services/scheduler.py — reminder job logic."""

from datetime import date, time, timedelta
from unittest.mock import patch

from models.attendance import Attendance
from models.event import Event
from models.notification_preference import NotificationPreference
from models.player import Player
from models.season import Season
from models.team import Team


def _make_player(db, email="player@test.com"):
    p = Player(first_name="Test", last_name="Player", is_active=True, email=email)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _make_event(db, days_ahead=1, has_time=True, reminder_sent=False):
    event_date = date.today() + timedelta(days=days_ahead)
    event = Event(
        title="Scheduled Event",
        event_type="training",
        event_date=event_date,
        event_time=time(18, 0) if has_time else None,
        reminder_sent=reminder_sent,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def test_send_due_reminders_sends_to_unknown_players(db):
    """Reminder job sends email to players with unknown attendance within the window."""
    from services.scheduler import send_due_reminders

    player = _make_player(db)
    # Event within 24h window (REMINDER_HOURS_BEFORE default = 24)
    event = _make_event(db, days_ahead=0, has_time=False)
    att = Attendance(event_id=event.id, player_id=player.id, status="unknown")
    db.add(att)
    db.commit()

    with patch("services.scheduler.send_event_reminder", return_value=True) as mock_send:
        count = send_due_reminders()

    assert count == 1
    mock_send.assert_called_once()
    db.refresh(event)
    assert event.reminder_sent is True


def test_send_due_reminders_skips_already_sent(db):
    """Reminder job skips events where reminder_sent is True."""
    from services.scheduler import send_due_reminders

    player = _make_player(db, email="skip@test.com")
    event = _make_event(db, days_ahead=0, has_time=False, reminder_sent=True)
    att = Attendance(event_id=event.id, player_id=player.id, status="unknown")
    db.add(att)
    db.commit()

    with patch("services.scheduler.send_event_reminder", return_value=True) as mock_send:
        count = send_due_reminders()

    assert count == 0
    mock_send.assert_not_called()


def test_send_due_reminders_skips_present_players(db):
    """Reminder job only emails players with unknown status, not present/absent."""
    from services.scheduler import send_due_reminders

    player = _make_player(db, email="present@test.com")
    event = _make_event(db, days_ahead=0, has_time=False)
    att = Attendance(event_id=event.id, player_id=player.id, status="present")
    db.add(att)
    db.commit()

    with patch("services.scheduler.send_event_reminder", return_value=True) as mock_send:
        count = send_due_reminders()

    assert count == 0
    mock_send.assert_not_called()


def test_send_due_reminders_respects_email_preference(db):
    """Reminder job skips players who have disabled email notifications."""
    from services.scheduler import send_due_reminders

    player = _make_player(db, email="noemail@test.com")
    event = _make_event(db, days_ahead=0, has_time=False)
    att = Attendance(event_id=event.id, player_id=player.id, status="unknown")
    db.add(att)
    # Explicitly disable email for this player
    pref = NotificationPreference(player_id=player.id, channel="email", enabled=False)
    db.add(pref)
    db.commit()

    with patch("services.scheduler.send_event_reminder", return_value=True) as mock_send:
        count = send_due_reminders()

    assert count == 0
    mock_send.assert_not_called()


def test_send_due_reminders_respects_team_auto_reminders_flag(db):
    """Reminder job skips events on teams that have auto_reminders=False."""
    from models.team import Team
    from services.scheduler import send_due_reminders

    team = Team(name="Silent Team", auto_reminders=False)
    db.add(team)
    db.commit()
    db.refresh(team)

    player = _make_player(db, email="silent@test.com")
    event = _make_event(db, days_ahead=0, has_time=False)
    event.team_id = team.id
    db.add(event)
    db.commit()

    att = Attendance(event_id=event.id, player_id=player.id, status="unknown")
    db.add(att)
    db.commit()

    with patch("services.scheduler.send_event_reminder", return_value=True) as mock_send:
        count = send_due_reminders()

    assert count == 0
    mock_send.assert_not_called()


def test_send_due_reminders_skips_far_future_events(db):
    """Reminder job does not email for events outside the reminder window."""
    from services.scheduler import send_due_reminders

    player = _make_player(db, email="future@test.com")
    # 10 days ahead — well outside the 24h default window
    event = _make_event(db, days_ahead=10, has_time=False)
    att = Attendance(event_id=event.id, player_id=player.id, status="unknown")
    db.add(att)
    db.commit()

    with patch("services.scheduler.send_event_reminder", return_value=True) as mock_send:
        count = send_due_reminders()

    assert count == 0
    mock_send.assert_not_called()
