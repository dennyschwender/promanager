"""services/absence_service.py — Absence business logic."""

from __future__ import annotations

from datetime import date, datetime
from sqlalchemy.orm import Session
from dateutil.rrule import rrulestr

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
