"""services/absence_service.py — Absence business logic."""

from __future__ import annotations

from datetime import date, datetime, timezone

from dateutil.rrule import rrulestr
from sqlalchemy.orm import Session

from models.player_absence import PlayerAbsence


def _date_matches_absence(check_date: date, absence: PlayerAbsence) -> bool:
    """Check if a date matches a specific absence record (pure logic, no DB)."""
    if absence.absence_type == "period":
        return (
            absence.start_date
            and absence.end_date
            and absence.start_date <= check_date <= absence.end_date
        )
    elif absence.absence_type == "recurring":
        if not (absence.rrule and absence.rrule_until):
            return False
        if check_date > absence.rrule_until:
            return False
        try:
            dtstart = datetime(2000, 1, 1)
            rrule = rrulestr(absence.rrule, dtstart=dtstart)
            end_dt = datetime.combine(absence.rrule_until, datetime.min.time())
            occurrences = rrule.between(dtstart, end_dt, inc=True)
            return any(occ.date() == check_date for occ in occurrences)
        except Exception:
            return False
    return False


def is_date_in_absence(player_id: int, check_date: date, db: Session) -> bool:
    """Check if a date falls within any active absence for a player."""
    absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player_id).all()
    return any(_date_matches_absence(check_date, abs_rec) for abs_rec in absences)


def apply_absence_to_future_events(player_id: int, db: Session) -> list[tuple[int, int, str]]:
    """Apply an absence to all matching future event attendance records.

    Returns a list of (event_id, player_id, status) tuples for each updated
    attendance record so callers can dispatch coach notifications.
    """
    from models.attendance import Attendance
    from models.event import Event

    today = date.today()

    # Query all attendance records for this player on future events
    attendances = (
        db.query(Attendance)
        .join(Event)
        .filter(
            Attendance.player_id == player_id,
            Event.event_date >= today,
        )
        .all()
    )

    # Fetch all absences for this player
    absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player_id).all()

    updated: list[tuple[int, int, str]] = []
    for att in attendances:
        # Find if this attendance date matches any absence
        matching_absence = None
        for absence in absences:
            if _date_matches_absence(att.event.event_date, absence):
                matching_absence = absence
                break

        if not matching_absence:
            continue

        if att.status in ("unknown", "present"):
            reason = matching_absence.reason or "On leave"
            att.status = "absent"
            att.note = f"[Absence] {reason}"
            att.updated_at = datetime.now(timezone.utc)
            updated.append((att.event_id, att.player_id, att.status))

    if updated:
        db.commit()

    return updated


def sync_attendance_to_absences_for_event(event_id: int, db: Session) -> int:
    """Re-evaluate attendance records for an event against active absences.

    Called when an event date changes. Updates attendance status if:
    - Event date now falls within an active absence
    - Should respect override logic (auto-defaults vs coach overrides)

    Returns the count of updated attendance records.
    """
    from models.attendance import Attendance
    from models.event import Event

    event = db.query(Event).filter(Event.id == event_id).first()
    if not event:
        return 0

    today = date.today()
    if event.event_date < today:
        # Don't update past events
        return 0

    # Query all attendance records for this event
    attendances = db.query(Attendance).filter(Attendance.event_id == event_id).all()

    count = 0
    for att in attendances:
        # Check if this player has an active absence matching the new event date
        if is_date_in_absence(att.player_id, event.event_date, db):
            # Get the matching absence for the note
            absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == att.player_id).all()
            matching_absence = None
            for absence in absences:
                if _date_matches_absence(event.event_date, absence):
                    matching_absence = absence
                    break

            # Determine if we should update
            should_update = att.status == "unknown" or (
                att.status == "present" and event.presence_type == "all"
            )

            if should_update:
                reason = matching_absence.reason if matching_absence else "On leave"
                att.status = "absent"
                att.note = f"[Absence] {reason}"
                att.updated_at = datetime.now(timezone.utc)
                count += 1
        else:
            # Event date is no longer in an absence period
            # Only clear if the status was set by an absence (has "[Absence]" prefix)
            if att.status == "absent" and att.note and att.note.startswith("[Absence]"):
                att.status = "unknown"
                att.note = None
                att.updated_at = datetime.now(timezone.utc)
                count += 1

    if count > 0:
        db.commit()

    return count


def apply_default_absence_to_future_events(player_id: int, team_id: int, season_id: int, db: Session) -> int:
    """Mark future 'unknown' attendance records absent due to absent_by_default flag.

    Only affects events for the given team/season. Returns count of updated records.
    """
    from models.attendance import Attendance
    from models.event import Event

    today = date.today()

    attendances = (
        db.query(Attendance)
        .join(Event)
        .filter(
            Attendance.player_id == player_id,
            Event.team_id == team_id,
            Event.season_id == season_id,
            Event.event_date >= today,
            Attendance.status == "unknown",
        )
        .all()
    )

    count = 0
    for att in attendances:
        att.status = "absent"
        att.note = "[Default Absent]"
        att.updated_at = datetime.now(timezone.utc)
        count += 1

    if count > 0:
        db.commit()

    return count


def revert_default_absence_from_events(player_id: int, team_id: int, season_id: int, db: Session) -> int:
    """Revert future attendance records set by absent_by_default back to unknown.

    Only affects events for the given team/season. Returns count of updated records.
    """
    from models.attendance import Attendance
    from models.event import Event

    today = date.today()

    attendances = (
        db.query(Attendance)
        .join(Event)
        .filter(
            Attendance.player_id == player_id,
            Event.team_id == team_id,
            Event.season_id == season_id,
            Event.event_date >= today,
            Attendance.status == "absent",
            Attendance.note == "[Default Absent]",
        )
        .all()
    )

    count = 0
    for att in attendances:
        att.status = "unknown"
        att.note = None
        att.updated_at = datetime.now(timezone.utc)
        count += 1

    if count > 0:
        db.commit()

    return count


def revert_absence_from_events(player_id: int, db: Session) -> int:
    """Revert future attendance records auto-set absent by absence logic back to unknown.

    Called when an absence is deleted or injury cleared.
    Only affects future events where note starts with '[Absence]'.
    Returns count of updated records.
    """
    from models.attendance import Attendance
    from models.event import Event

    today = date.today()

    attendances = (
        db.query(Attendance)
        .join(Event)
        .filter(
            Attendance.player_id == player_id,
            Attendance.status == "absent",
            Attendance.note.like("[Absence]%"),
            Event.event_date >= today,
        )
        .all()
    )

    count = 0
    for att in attendances:
        att.status = "unknown"
        att.note = None
        att.updated_at = datetime.now(timezone.utc)
        count += 1

    if count > 0:
        db.commit()

    return count
