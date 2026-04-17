"""tests/test_absence_service.py — Absence service tests."""

from datetime import date

from sqlalchemy.orm import Session

from models.attendance import Attendance
from models.event import Event
from models.player import Player
from models.player_absence import PlayerAbsence
from models.player_team import PlayerTeam
from models.season import Season
from models.team import Team
from services.absence_service import apply_absence_to_future_events, is_date_in_absence


def test_is_date_in_absence_period_within_range(db: Session):
    """Period absence should match dates within start_date to end_date (inclusive)."""
    # Create a player
    player = Player(first_name="John", last_name="Doe", is_active=True)
    db.add(player)
    db.commit()

    # Create a period absence: April 10-20
    absence = PlayerAbsence(
        player_id=player.id,
        absence_type="period",
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 20),
        reason="Vacation",
    )
    db.add(absence)
    db.commit()

    # Test dates within range
    assert is_date_in_absence(player.id, date(2026, 4, 10), db) is True  # start
    assert is_date_in_absence(player.id, date(2026, 4, 15), db) is True  # middle
    assert is_date_in_absence(player.id, date(2026, 4, 20), db) is True  # end

    # Test dates outside range
    assert is_date_in_absence(player.id, date(2026, 4, 9), db) is False
    assert is_date_in_absence(player.id, date(2026, 4, 21), db) is False


def test_is_date_in_absence_period_no_match(db: Session):
    """Period absence should not match dates outside the range."""
    player = Player(first_name="Jane", last_name="Smith", is_active=True)
    db.add(player)
    db.commit()

    absence = PlayerAbsence(
        player_id=player.id,
        absence_type="period",
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 20),
    )
    db.add(absence)
    db.commit()

    assert is_date_in_absence(player.id, date(2026, 5, 1), db) is False


def test_is_date_in_absence_no_absences(db: Session):
    """Player with no absences should return False."""
    player = Player(first_name="Bob", last_name="Jones", is_active=True)
    db.add(player)
    db.commit()

    assert is_date_in_absence(player.id, date(2026, 4, 15), db) is False


def test_is_date_in_absence_recurring_weekly(db: Session):
    """Recurring absence with FREQ=WEEKLY;BYDAY=FR should match Fridays."""
    player = Player(first_name="Alice", last_name="Wonder", is_active=True)
    db.add(player)
    db.commit()

    season = Season(name="Spring 2026", start_date=date(2026, 3, 1), end_date=date(2026, 6, 30))
    db.add(season)
    db.commit()

    # Every Friday until end of season
    absence = PlayerAbsence(
        player_id=player.id,
        absence_type="recurring",
        rrule="FREQ=WEEKLY;BYDAY=FR",
        rrule_until=date(2026, 6, 30),
        season_id=season.id,
        reason="Weekly training conflict",
    )
    db.add(absence)
    db.commit()

    # April 10, 17, 24 are Fridays
    assert is_date_in_absence(player.id, date(2026, 4, 10), db) is True
    assert is_date_in_absence(player.id, date(2026, 4, 17), db) is True
    assert is_date_in_absence(player.id, date(2026, 4, 24), db) is True

    # April 11 is Saturday
    assert is_date_in_absence(player.id, date(2026, 4, 11), db) is False


def test_is_date_in_absence_recurring_expired(db: Session):
    """Recurring absence should not match dates after rrule_until."""
    player = Player(first_name="Charlie", last_name="Brown", is_active=True)
    db.add(player)
    db.commit()

    season = Season(name="Spring 2026", start_date=date(2026, 3, 1), end_date=date(2026, 6, 30))
    db.add(season)
    db.commit()

    # Every Friday until April 30
    absence = PlayerAbsence(
        player_id=player.id,
        absence_type="recurring",
        rrule="FREQ=WEEKLY;BYDAY=FR",
        rrule_until=date(2026, 4, 30),
        season_id=season.id,
    )
    db.add(absence)
    db.commit()

    # May 1 is a Friday, but after rrule_until
    assert is_date_in_absence(player.id, date(2026, 5, 1), db) is False
    # But April 24 (Friday) should match
    assert is_date_in_absence(player.id, date(2026, 4, 24), db) is True


def test_apply_absence_to_future_events_period(db: Session):
    """Creating a period absence should auto-set matching future events to absent."""
    from datetime import timedelta
    today = date.today()

    player = Player(first_name="David", last_name="Test", is_active=True)
    db.add(player)
    db.commit()

    team = Team(name="TestTeam")
    db.add(team)
    db.commit()

    season = Season(name="Spring 2026", start_date=today, end_date=today + timedelta(days=90))
    db.add(season)
    db.commit()

    # Add player to team
    pm = PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id)
    db.add(pm)
    db.commit()

    # Create events: two within absence window, one outside
    d_in1 = today + timedelta(days=2)
    d_in2 = today + timedelta(days=5)
    d_out = today + timedelta(days=20)

    e1 = Event(title="Event 1", event_date=d_in1, team_id=team.id, season_id=season.id, presence_type="normal")
    e2 = Event(title="Event 2", event_date=d_in2, team_id=team.id, season_id=season.id, presence_type="normal")
    e3 = Event(title="Event 3", event_date=d_out, team_id=team.id, season_id=season.id, presence_type="normal")
    db.add_all([e1, e2, e3])
    db.commit()

    for event in [e1, e2, e3]:
        att = Attendance(event_id=event.id, player_id=player.id, status="unknown")
        db.add(att)
    db.commit()

    # Absence covers d_in1 and d_in2 but not d_out
    absence = PlayerAbsence(
        player_id=player.id,
        absence_type="period",
        start_date=today + timedelta(days=1),
        end_date=today + timedelta(days=10),
        reason="Vacation",
    )
    db.add(absence)
    db.commit()

    count = apply_absence_to_future_events(player.id, db)

    assert count == 2  # e1 and e2 should be updated

    att1 = db.query(Attendance).filter_by(event_id=e1.id, player_id=player.id).first()
    assert att1.status == "absent"
    assert "[Absence]" in att1.note
    assert "Vacation" in att1.note

    att2 = db.query(Attendance).filter_by(event_id=e2.id, player_id=player.id).first()
    assert att2.status == "absent"

    att3 = db.query(Attendance).filter_by(event_id=e3.id, player_id=player.id).first()
    assert att3.status == "unknown"


def test_apply_absence_respects_all_presence_type(db: Session):
    """Absence should override presence_type='all' (auto-present default)."""
    from datetime import timedelta
    today = date.today()

    player = Player(first_name="Eve", last_name="Test", is_active=True)
    db.add(player)
    db.commit()

    team = Team(name="TestTeam2")
    db.add(team)
    db.commit()

    season = Season(name="Spring 2026", start_date=today, end_date=today + timedelta(days=90))
    db.add(season)
    db.commit()

    pm = PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id)
    db.add(pm)
    db.commit()

    future_date = today + timedelta(days=5)

    event = Event(
        title="AllAttendee Event",
        event_date=future_date,
        team_id=team.id,
        season_id=season.id,
        presence_type="all",
    )
    db.add(event)
    db.commit()

    att = Attendance(event_id=event.id, player_id=player.id, status="present")
    db.add(att)
    db.commit()

    absence = PlayerAbsence(
        player_id=player.id,
        absence_type="period",
        start_date=today + timedelta(days=1),
        end_date=today + timedelta(days=10),
        reason="Vacation",
    )
    db.add(absence)
    db.commit()

    count = apply_absence_to_future_events(player.id, db)

    assert count == 1
    att_refreshed = db.query(Attendance).filter_by(event_id=event.id, player_id=player.id).first()
    assert att_refreshed.status == "absent"


def test_apply_absence_preserves_explicit_present(db: Session):
    """Absence should NOT override explicit 'present' on non-'all' events."""
    player = Player(first_name="Frank", last_name="Test", is_active=True)
    db.add(player)
    db.commit()

    team = Team(name="TestTeam3")
    db.add(team)
    db.commit()

    season = Season(name="Spring 2026", start_date=date(2026, 3, 1), end_date=date(2026, 6, 30))
    db.add(season)
    db.commit()

    pm = PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id)
    db.add(pm)
    db.commit()

    # Event with presence_type="normal" (not all-attendee)
    event = Event(
        title="Normal Event",
        event_date=date(2026, 4, 15),
        team_id=team.id,
        season_id=season.id,
        presence_type="normal",
    )
    db.add(event)
    db.commit()

    # Create attendance with status="present" (coach explicitly set it)
    att = Attendance(event_id=event.id, player_id=player.id, status="present", note="Coach confirmed")
    db.add(att)
    db.commit()

    # Create absence covering this date
    absence = PlayerAbsence(
        player_id=player.id,
        absence_type="period",
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 20),
        reason="Vacation",
    )
    db.add(absence)
    db.commit()

    # Apply absence
    count = apply_absence_to_future_events(player.id, db)

    # Should NOT have updated (explicit present preserved)
    assert count == 0
    att_refreshed = db.query(Attendance).filter_by(event_id=event.id, player_id=player.id).first()
    assert att_refreshed.status == "present"
    assert att_refreshed.note == "Coach confirmed"
