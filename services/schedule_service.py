"""services/schedule_service.py — Recurring schedule helpers."""

from __future__ import annotations

import calendar
import hashlib
import hmac
import json
import uuid
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from models.event import Event
from models.team_recurring_schedule import TeamRecurringSchedule
from services.attendance_service import ensure_attendance_records

# Fields whose change triggers event regeneration (confirmation required).
KEY_FIELDS = (
    "start_date",
    "end_date",
    "recurrence_rule",
    "event_type",
    "event_time",
    "event_end_time",
    "location",
    "meeting_time",
    "meeting_location",
    "presence_type",
)


def advance_date(d: date, rule: str) -> date:
    """Return the next occurrence date for *d* given *rule*.

    Rules: "weekly" (+7 days), "biweekly" (+14 days), "monthly" (same day
    next month, capped at last day of that month).
    """
    if rule == "weekly":
        return d + timedelta(days=7)
    if rule == "biweekly":
        return d + timedelta(days=14)
    # monthly: advance month by 1, keep same day (cap to last day of month)
    month = d.month % 12 + 1
    year = d.year + (1 if d.month == 12 else 0)
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


def generate_events_for_schedule(
    db: Session,
    schedule: TeamRecurringSchedule,
    team,  # models.team.Team
) -> list[Event]:
    """Generate Event rows for a schedule. Does NOT commit — caller commits."""
    end = schedule.end_date
    if end is None and team.season is not None:
        end = team.season.end_date
    if end is None:
        raise ValueError(
            "Set an end date on the schedule or assign the team to a season "
            "with an end date."
        )
    if schedule.start_date > end:
        raise ValueError("Start date must be on or before end date.")

    # At this point `end` is always a concrete date — the None case raised above.
    # The while loop is therefore always finite.
    events: list[Event] = []
    cur = schedule.start_date
    while cur <= end:
        ev = Event(
            title=schedule.title,
            event_type=schedule.event_type,
            event_date=cur,
            event_time=schedule.event_time,
            event_end_time=schedule.event_end_time,
            location=schedule.location,
            meeting_time=schedule.meeting_time,
            meeting_location=schedule.meeting_location,
            presence_type=schedule.presence_type,
            description=schedule.description,
            season_id=team.season_id,
            team_id=team.id,
            recurrence_group_id=schedule.recurrence_group_id,
            recurrence_rule=schedule.recurrence_rule,
        )
        db.add(ev)
        db.flush()
        ensure_attendance_records(db, ev)
        events.append(ev)
        cur = advance_date(cur, schedule.recurrence_rule)
    return events


def delete_future_events(db: Session, recurrence_group_id: str) -> int:
    """Delete future events (event_date >= today) for the given group. Returns count.

    Uses >= today (inclusive) per spec: today's event is considered future
    and is eligible for deletion during regeneration.
    """
    today = datetime.today().date()
    rows = (
        db.query(Event)
        .filter(
            Event.recurrence_group_id == recurrence_group_id,
            Event.event_date >= today,
        )
        .all()
    )
    for ev in rows:
        db.delete(ev)
    return len(rows)


def count_future_events(db: Session, recurrence_group_id: str) -> int:
    """Count future events (event_date >= today) for the given group."""
    today = datetime.today().date()
    return (
        db.query(Event)
        .filter(
            Event.recurrence_group_id == recurrence_group_id,
            Event.event_date >= today,
        )
        .count()
    )


def propagate_nonkey_changes(
    db: Session,
    recurrence_group_id: str,
    title: str,
    description: str | None,
) -> None:
    """Update title/description in-place on future events (no regeneration)."""
    today = datetime.today().date()
    db.query(Event).filter(
        Event.recurrence_group_id == recurrence_group_id,
        Event.event_date >= today,
    ).update({"title": title, "description": description})


def _norm(v) -> str:
    """Normalise a field value to a comparable string.

    datetime.time  -> "HH:MM"  (matches form input format)
    datetime.date  -> "YYYY-MM-DD"  (matches form input format)
    str / other    -> stripped string
    None           -> ""

    Note: date has isoformat() but NOT hour; time has both isoformat() and hour.
    Checking hour first ensures time objects use %H:%M not isoformat() ("%H:%M:%S").
    """
    if v is None:
        return ""
    if hasattr(v, "hour"):  # datetime.time
        return v.strftime("%H:%M")
    if hasattr(v, "isoformat"):  # datetime.date
        return v.isoformat()
    return str(v).strip()


def is_changed(stored: TeamRecurringSchedule, submitted_raw: dict) -> bool:
    """Return True if any key field differs between stored schedule and submitted form data."""
    for field in KEY_FIELDS:
        if _norm(getattr(stored, field, None)) != _norm(submitted_raw.get(field, "")):
            return True
    return False


def new_group_id() -> str:
    return str(uuid.uuid4())


# ── HMAC payload signing ────────────────────────────────────────────────────


def sign_payload(data: dict) -> str:
    """Serialise *data* as JSON and append an HMAC-SHA256 signature.

    Returns a string of the form ``{json}.{hex_signature}``.
    """
    payload = json.dumps(data, default=str, sort_keys=True)
    sig = hmac.new(
        settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    return f"{payload}.{sig}"


def verify_payload(token: str) -> dict:
    """Verify the HMAC signature and return the parsed dict.

    Raises ValueError if the signature is missing or invalid.
    """
    try:
        payload, sig = token.rsplit(".", 1)
    except ValueError:
        raise ValueError("Invalid payload format.")
    expected = hmac.new(
        settings.SECRET_KEY.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise ValueError("Payload signature invalid.")
    return json.loads(payload)
