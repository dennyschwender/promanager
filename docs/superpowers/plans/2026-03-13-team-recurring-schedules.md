# Team Recurring Schedules Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Recurring Schedules" section to the team edit page that lets admins define multiple recurring event patterns (e.g. Tuesday training, Thursday training), auto-generates events on save, and selectively regenerates when schedules change.

**Architecture:** A new `TeamRecurringSchedule` model stores schedule definitions. A `services/schedule_service.py` module handles event generation, change detection, and HMAC signing. The team edit route gains a two-step save flow: first POST detects changes and renders a confirmation step; second POST applies confirmed regenerations. The template adds a dynamic fieldset with JS for add/remove/re-index of schedule rows. A `<template>` element is used for adding new rows (avoids innerHTML).

**Tech Stack:** FastAPI, SQLAlchemy 2.x, SQLite, Alembic, Jinja2, Python 3.12+, pytest, existing `ensure_attendance_records` service, existing `settings.SECRET_KEY` for HMAC signing.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `models/team_recurring_schedule.py` | ORM model for schedule definitions |
| Create | `alembic/versions/abc1_add_team_recurring_schedules.py` | DB migration |
| Modify | `models/team.py` | Add `recurring_schedules` relationship |
| Modify | `models/__init__.py` | Export new model |
| Create | `services/schedule_service.py` | Generation, change detection, HMAC, helpers |
| Modify | `routes/events.py` | Import `advance_date` from service (remove local copy) |
| Modify | `routes/teams.py` | Two-step save flow, schedule parsing |
| Modify | `templates/teams/form.html` | Recurring Schedules fieldset + JS |
| Create | `tests/test_schedule_service.py` | Unit tests for service functions |
| Modify | `tests/test_teams.py` | Integration tests for schedule save flow |

---

## Chunk 1: Model, Migration, and Service

### Task 1: TeamRecurringSchedule model + migration

**Files:**
- Create: `models/team_recurring_schedule.py`
- Create: `alembic/versions/abc1_add_team_recurring_schedules.py`
- Modify: `models/__init__.py`
- Modify: `models/team.py`

- [ ] **Step 1: Create `models/team_recurring_schedule.py`**

```python
"""models/team_recurring_schedule.py — TeamRecurringSchedule model."""

from __future__ import annotations

from datetime import date, time

from sqlalchemy import Date, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class TeamRecurringSchedule(Base):
    __tablename__ = "team_recurring_schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    event_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="training"
    )
    recurrence_rule: Mapped[str] = mapped_column(
        String(32), nullable=False  # weekly | biweekly | monthly
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    event_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    event_end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    meeting_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    meeting_location: Mapped[str | None] = mapped_column(String(256), nullable=True)
    presence_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="normal"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # UUID string linking this schedule to the events it generated
    recurrence_group_id: Mapped[str] = mapped_column(
        String(36), nullable=False, unique=True, index=True
    )

    team: Mapped["Team"] = relationship(  # type: ignore[name-defined]
        "Team", back_populates="recurring_schedules"
    )

    def __repr__(self) -> str:
        return f"<TeamRecurringSchedule id={self.id} title={self.title!r}>"
```

- [ ] **Step 2: Add relationship to `models/team.py`**

Add this relationship to the `Team` class body (after the existing `events` relationship):
```python
    recurring_schedules: Mapped[list["TeamRecurringSchedule"]] = relationship(  # type: ignore[name-defined]
        "TeamRecurringSchedule",
        back_populates="team",
        cascade="all, delete-orphan",
        lazy="select",
    )
```

- [ ] **Step 3: Update `models/__init__.py`** — add import and export:

```python
from .team_recurring_schedule import TeamRecurringSchedule
```

Add `"TeamRecurringSchedule"` to `__all__`.

- [ ] **Step 4: Create Alembic migration**

Create `alembic/versions/abc1_add_team_recurring_schedules.py`:

```python
"""add team_recurring_schedules table

Revision ID: abc1add0sched
Revises: 7d6728f4bc65
Create Date: 2026-03-13 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "abc1add0sched"
down_revision: Union[str, Sequence[str], None] = "7d6728f4bc65"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "team_recurring_schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("recurrence_rule", sa.String(length=32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("event_time", sa.Time(), nullable=True),
        sa.Column("event_end_time", sa.Time(), nullable=True),
        sa.Column("location", sa.String(length=256), nullable=True),
        sa.Column("meeting_time", sa.Time(), nullable=True),
        sa.Column("meeting_location", sa.String(length=256), nullable=True),
        sa.Column("presence_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("recurrence_group_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recurrence_group_id"),
    )
    with op.batch_alter_table("team_recurring_schedules", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_team_recurring_schedules_id"), ["id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_team_recurring_schedules_team_id"), ["team_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_team_recurring_schedules_recurrence_group_id"),
            ["recurrence_group_id"],
            unique=True,
        )


def downgrade() -> None:
    op.drop_table("team_recurring_schedules")
```

- [ ] **Step 5: Run migration and verify table is created**

```bash
cd /home/denny/Development/promanager
alembic upgrade head
```

Expected: `Running upgrade 7d6728f4bc65 -> abc1add0sched, add team_recurring_schedules table`

- [ ] **Step 6: Verify model imports without error**

```bash
python -c "from models.team_recurring_schedule import TeamRecurringSchedule; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add models/team_recurring_schedule.py models/team.py models/__init__.py \
    alembic/versions/abc1_add_team_recurring_schedules.py
git commit -m "feat: add TeamRecurringSchedule model and migration"
```

---

### Task 2: Schedule service

**Files:**
- Create: `services/schedule_service.py`
- Create: `tests/test_schedule_service.py`
- Modify: `routes/events.py` (replace local `_advance_date` with import)

- [ ] **Step 1: Write failing unit tests for `advance_date`**

Create `tests/test_schedule_service.py`:

```python
"""Unit tests for services/schedule_service.py."""
from __future__ import annotations

from datetime import date, time
from unittest.mock import patch

import pytest

from services.schedule_service import (
    advance_date,
    count_future_events,
    delete_future_events,
    generate_events_for_schedule,
    is_changed,
    propagate_nonkey_changes,
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
    from models.event import Event

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
    from models.season import Season
    from models.team import Team
    from models.team_recurring_schedule import TeamRecurringSchedule

    season = Season(name="S1", end_date=date(2026, 3, 17), is_active=True)
    db.add(season)
    db.commit()
    db.refresh(season)

    team = Team(name="Lions", season_id=season.id)
    db.add(team)
    db.commit()
    db.refresh(team)

    sched = TeamRecurringSchedule(
        team_id=team.id, title="T", event_type="training",
        recurrence_rule="weekly", start_date=date(2026, 3, 3),
        end_date=None,  # falls back to season end 2026-03-17
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
```

- [ ] **Step 2: Run tests to confirm they all fail**

```bash
cd /home/denny/Development/promanager
pytest tests/test_schedule_service.py -v 2>&1 | head -20
```

Expected: `ImportError` — module doesn't exist yet

- [ ] **Step 3: Create `services/schedule_service.py`**

```python
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

    datetime.time  → "HH:MM"  (matches form input format)
    datetime.date  → "YYYY-MM-DD"  (matches form input format)
    str / other    → stripped string
    None           → ""

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
```

- [ ] **Step 4: Update `routes/events.py`** — replace the local `_advance_date` with an import

Add this import near the top of `routes/events.py` (after existing imports):
```python
from services.schedule_service import advance_date as _advance_date
```

Then remove the local `_advance_date` function definition (the full function block starting with `def _advance_date(d, rule: str):`).

Also remove `import calendar` from `routes/events.py` if it is no longer used elsewhere in that file (check: search for other `calendar.` usages first).

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_schedule_service.py tests/test_events.py -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add services/schedule_service.py tests/test_schedule_service.py routes/events.py
git commit -m "feat: add schedule service with generation, change detection, and HMAC helpers"
```

---

## Chunk 2: Route and Template

### Task 3: Update `routes/teams.py` — two-step save flow

**Files:**
- Modify: `routes/teams.py`

- [ ] **Step 1: Add imports and helper functions to `routes/teams.py`**

Add these imports at the top (after existing imports):
```python
from datetime import datetime

from models.team_recurring_schedule import TeamRecurringSchedule
from services.schedule_service import (
    count_future_events,
    delete_future_events,
    generate_events_for_schedule,
    is_changed,
    new_group_id,
    propagate_nonkey_changes,
    sign_payload,
    verify_payload,
)
```

Add these helper functions after the imports, before the router definition:

```python
def _parse_schedule_rows(form, count: int) -> list[dict]:
    """Parse sched_* form fields into a list of raw string dicts."""
    rows = []
    for i in range(count):
        rows.append({
            "id": (form.get(f"sched_id_{i}") or "").strip(),
            "title": (form.get(f"sched_title_{i}") or "").strip(),
            "event_type": (form.get(f"sched_event_type_{i}") or "training").strip(),
            "recurrence_rule": (form.get(f"sched_rule_{i}") or "weekly").strip(),
            "start_date": (form.get(f"sched_start_{i}") or "").strip(),
            "end_date": (form.get(f"sched_end_{i}") or "").strip(),
            "event_time": (form.get(f"sched_time_{i}") or "").strip(),
            "event_end_time": (form.get(f"sched_end_time_{i}") or "").strip(),
            "location": (form.get(f"sched_location_{i}") or "").strip(),
            "meeting_time": (form.get(f"sched_meeting_time_{i}") or "").strip(),
            "meeting_location": (form.get(f"sched_meeting_location_{i}") or "").strip(),
            "presence_type": (form.get(f"sched_presence_{i}") or "normal").strip(),
            "description": (form.get(f"sched_desc_{i}") or "").strip(),
        })
    return rows


def _parse_dt(s: str):
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()


def _parse_tm(s: str):
    if not s:
        return None
    return datetime.strptime(s, "%H:%M").time()


def _schedule_to_dict(s: TeamRecurringSchedule) -> dict:
    return {
        "id": str(s.id),
        "title": s.title,
        "event_type": s.event_type,
        "recurrence_rule": s.recurrence_rule,
        "start_date": s.start_date.isoformat() if s.start_date else "",
        "end_date": s.end_date.isoformat() if s.end_date else "",
        "event_time": s.event_time.strftime("%H:%M") if s.event_time else "",
        "event_end_time": s.event_end_time.strftime("%H:%M") if s.event_end_time else "",
        "location": s.location or "",
        "meeting_time": s.meeting_time.strftime("%H:%M") if s.meeting_time else "",
        "meeting_location": s.meeting_location or "",
        "presence_type": s.presence_type,
        "description": s.description or "",
        "recurrence_group_id": s.recurrence_group_id,
    }


def _apply_row_to_schedule(sched: TeamRecurringSchedule, row: dict) -> None:
    sched.title = row["title"]
    sched.event_type = row["event_type"]
    sched.recurrence_rule = row["recurrence_rule"]
    sched.start_date = _parse_dt(row["start_date"])
    sched.end_date = _parse_dt(row["end_date"])
    sched.event_time = _parse_tm(row["event_time"])
    sched.event_end_time = _parse_tm(row["event_end_time"])
    sched.location = row["location"] or None
    sched.meeting_time = _parse_tm(row["meeting_time"])
    sched.meeting_location = row["meeting_location"] or None
    sched.presence_type = row["presence_type"]
    sched.description = row["description"] or None
```

- [ ] **Step 2: Update the GET route**

Replace `team_edit_get`:

```python
@router.get("/{team_id}/edit")
async def team_edit_get(
    team_id: int,
    request: Request,
    saved: str = "",
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    team = db.get(Team, team_id)
    if team is None:
        return RedirectResponse("/teams", status_code=302)

    seasons = db.query(Season).order_by(Season.name).all()
    return templates.TemplateResponse(request, "teams/form.html", {
        "user": user,
        "team": team,
        "seasons": seasons,
        "schedule_rows": [_schedule_to_dict(s) for s in team.recurring_schedules],
        "error": None,
        "saved": bool(saved),
        "confirm_mode": False,
        "flagged": [],
        "_schedules_json": "",
    })
```

- [ ] **Step 3: Rewrite `team_edit_post`**

> **Implementation notes:**
> - `_confirm_step` is declared as a typed `Form(...)` parameter in the function signature. `sched_count` and all dynamic indexed fields (`sched_id_0`, `sched_title_0`, etc.) are read via `form = await request.form()` — they cannot be declared as typed params since their names are runtime-determined.
> - The `_schedules_json` hidden field is populated by the server when rendering the confirmation step (`schedules_json=signed` in `_render`). The JS submit handler does **not** write to this field — it only re-indexes row `name` attributes and injects `sched_count`. The field's value is whatever the server rendered.
> - Row re-indexing works by directly mutating the `name` attribute of each form element (e.g. `el.name = 'sched_title_' + i`). This approach requires no FormData manipulation and works with native form submission.
> - The `team_new_get` and `team_new_post` routes (for creating a new team) also render `teams/form.html`. They must pass the new context variables with safe defaults: `schedule_rows=[]`, `saved=False`, `confirm_mode=False`, `flagged=[]`, `_schedules_json=""`. Add these to the existing `TemplateResponse` calls in those routes.

Replace the existing `team_edit_post` function entirely with:

```python
@router.post("/{team_id}/edit")
async def team_edit_post(
    team_id: int,
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    season_id: str = Form(""),
    _confirm_step: str = Form(""),
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    team = db.get(Team, team_id)
    if team is None:
        return RedirectResponse("/teams", status_code=302)

    seasons = db.query(Season).order_by(Season.name).all()
    form = await request.form()

    def _render(error=None, confirm_mode=False, flagged=None,
                schedule_rows=None, schedules_json="", saved=False):
        return templates.TemplateResponse(request, "teams/form.html", {
            "user": user,
            "team": team,
            "seasons": seasons,
            "schedule_rows": (
                schedule_rows
                if schedule_rows is not None
                else [_schedule_to_dict(s) for s in team.recurring_schedules]
            ),
            "error": error,
            "saved": saved,
            "confirm_mode": confirm_mode,
            "flagged": flagged or [],
            "_schedules_json": schedules_json,
        })

    if not name.strip():
        return _render(error="Team name is required.")

    # Apply core team fields
    old_season_id = team.season_id
    team.name = name.strip()
    team.description = description.strip() or None
    team.season_id = int(season_id) if season_id.strip() else None
    season_changed = old_season_id != team.season_id

    # ── CONFIRMATION POST ────────────────────────────────────────────────────
    if _confirm_step == "1":
        raw_json = (form.get("_schedules_json") or "").strip()
        try:
            payload = verify_payload(raw_json)
        except ValueError:
            return _render(error="Invalid confirmation payload. Please try again.")

        # Verify team_id binding — prevents cross-team replay of a signed payload
        if payload.get("team_id") != team_id:
            return _render(error="Invalid confirmation payload. Please try again.")

        submitted_rows = payload.get("rows", [])
        stored_map = {s.id: s for s in team.recurring_schedules}
        submitted_ids = {int(r["id"]) for r in submitted_rows if r.get("id")}

        for row in submitted_rows:
            sched_id_str = row.get("id", "")
            confirm_key = f"confirm_schedule_{sched_id_str or ('new_' + row.get('recurrence_group_id', ''))}"
            confirmed = form.get(confirm_key) == "on"

            if not sched_id_str:
                sched = TeamRecurringSchedule(
                    team_id=team_id,
                    recurrence_group_id=row.get("recurrence_group_id") or new_group_id(),
                )
                _apply_row_to_schedule(sched, row)
                db.add(sched)
                db.flush()
                try:
                    generate_events_for_schedule(db, sched, team)
                except ValueError:
                    pass
            else:
                sched_id = int(sched_id_str)
                sched = stored_map.get(sched_id)
                if sched is None:
                    continue
                if confirmed:
                    delete_future_events(db, sched.recurrence_group_id)
                    sched.recurrence_group_id = new_group_id()
                    _apply_row_to_schedule(sched, row)
                    db.add(sched)
                    db.flush()
                    try:
                        generate_events_for_schedule(db, sched, team)
                    except ValueError:
                        pass
                else:
                    # Determine if unchanged BEFORE mutating sched — is_changed
                    # compares stored ORM values vs submitted dict.
                    truly_unchanged = not is_changed(sched, row)
                    _apply_row_to_schedule(sched, row)
                    db.add(sched)
                    if truly_unchanged:
                        # Unchanged schedule: propagate non-key fields (title, description)
                        # in-place to future events, per spec.
                        propagate_nonkey_changes(
                            db, sched.recurrence_group_id,
                            sched.title, sched.description,
                        )
                    # else: changed-but-unchecked — save fields, do NOT touch events

        # Handle removed schedules
        for sched_id, sched in stored_map.items():
            if sched_id not in submitted_ids:
                confirm_key = f"confirm_schedule_{sched_id}"
                if form.get(confirm_key) == "on":
                    delete_future_events(db, sched.recurrence_group_id)
                    db.delete(sched)
                # else: keep schedule and events untouched

        try:
            db.add(team)
            db.commit()
        except Exception:
            db.rollback()
            return _render(error="An error occurred saving the schedules. Please try again.")
        return RedirectResponse(f"/teams/{team_id}/edit?saved=1", status_code=302)

    # ── FIRST POST ───────────────────────────────────────────────────────────
    sched_count = int((form.get("sched_count") or "0").strip() or "0")
    submitted_rows = _parse_schedule_rows(form, sched_count)

    stored = team.recurring_schedules
    stored_map = {s.id: s for s in stored}
    submitted_ids = {int(r["id"]) for r in submitted_rows if r["id"]}

    flagged = []
    new_rows = []
    unchanged_rows = []

    for row in submitted_rows:
        if not row["title"]:
            continue
        sched_id_str = row["id"]

        if not sched_id_str:
            row["recurrence_group_id"] = new_group_id()
            new_rows.append(row)
        else:
            sched_id = int(sched_id_str)
            stored_sched = stored_map.get(sched_id)
            if stored_sched is None:
                continue
            if is_changed(stored_sched, row) or (
                season_changed and stored_sched.end_date is None
            ):
                future_count = count_future_events(db, stored_sched.recurrence_group_id)
                flagged.append({
                    "type": "changed",
                    "sched_id": sched_id,
                    "title": row["title"],
                    "future_count": future_count,
                    "confirm_key": f"confirm_schedule_{sched_id}",
                    "row": row,
                })
            else:
                unchanged_rows.append((stored_sched, row))

    for sched_id, sched in stored_map.items():
        if sched_id not in submitted_ids:
            future_count = count_future_events(db, sched.recurrence_group_id)
            flagged.append({
                "type": "removed",
                "sched_id": sched_id,
                "title": sched.title,
                "future_count": future_count,
                "confirm_key": f"confirm_schedule_{sched_id}",
                "row": _schedule_to_dict(sched),
            })

    if flagged:
        # Bind team_id into the payload to prevent cross-team replay attacks.
        # Filter empty-title rows: they were already skipped in the first-POST loop
        # and must not be re-processed on the confirm POST.
        payload_data = {"team_id": team_id, "rows": [r for r in submitted_rows if r["title"]]}
        signed = sign_payload(payload_data)
        return _render(
            confirm_mode=True,
            flagged=flagged,
            schedule_rows=[r for r in submitted_rows if r["title"]],
            schedules_json=signed,
        )

    # No confirmation needed — apply everything in a single transaction
    for row in new_rows:
        sched = TeamRecurringSchedule(
            team_id=team_id,
            recurrence_group_id=row["recurrence_group_id"],
        )
        _apply_row_to_schedule(sched, row)
        db.add(sched)
        db.flush()
        try:
            generate_events_for_schedule(db, sched, team)
        except ValueError:
            pass

    for stored_sched, row in unchanged_rows:
        _apply_row_to_schedule(stored_sched, row)
        propagate_nonkey_changes(
            db, stored_sched.recurrence_group_id,
            stored_sched.title, stored_sched.description,
        )
        db.add(stored_sched)

    try:
        db.add(team)
        db.commit()
    except Exception:
        db.rollback()
        return _render(error="An error occurred saving the schedules. Please try again.")
    return RedirectResponse(f"/teams/{team_id}/edit?saved=1", status_code=302)
```

- [ ] **Step 4: Verify imports compile**

```bash
python -c "from routes.teams import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Run existing team tests**

```bash
pytest tests/test_teams.py -v
```

Expected: all existing tests pass

- [ ] **Step 6: Commit**

```bash
git add routes/teams.py
git commit -m "feat: two-step schedule save flow in teams route"
```

---

### Task 4: Update `templates/teams/form.html` — Recurring Schedules fieldset

**Files:**
- Modify: `templates/teams/form.html`

Replace the entire file with the following. Note: the JS for adding rows uses a `<template>` element and `cloneNode(true)` — no `innerHTML` is used.

```html
{% extends "base.html" %}
{% block title %}{% if team %}Edit Team{% else %}New Team{% endif %} — ProManager{% endblock %}
{% block breadcrumb %}
<nav class="breadcrumb">
  <a href="/dashboard">Home</a><span class="breadcrumb-sep"></span>
  <a href="/teams">Teams</a><span class="breadcrumb-sep"></span>
  <span>{% if team %}Edit{% else %}New{% endif %}</span>
</nav>
{% endblock %}
{% block content %}
<div class="form-container">
<h2>{% if team %}Edit Team: {{ team.name }}{% else %}New Team{% endif %}</h2>

{% if saved %}
  <div class="alert alert-success">Changes saved.</div>
{% endif %}
{% if error %}
  <div class="alert alert-error">{{ error }}</div>
{% endif %}

<form method="post" action="{% if team %}/teams/{{ team.id }}/edit{% else %}/teams/new{% endif %}"
      id="team-form">
  <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
  <input type="hidden" name="_confirm_step" value="{% if confirm_mode %}1{% endif %}">
  <input type="hidden" name="_schedules_json" id="schedules-json-field"
         value="{{ _schedules_json }}">

  {# ── Core team fields ── #}
  <label for="name">Team Name *
    <input type="text" id="name" name="name" required
           value="{{ team.name if team else '' }}">
  </label>
  <label for="description">Description
    <textarea id="description" name="description">{{ team.description if team and team.description else '' }}</textarea>
  </label>
  <label for="season_id">Season
    <select id="season_id" name="season_id">
      <option value="">— None —</option>
      {% for s in seasons %}
        <option value="{{ s.id }}"
                {% if team and team.season_id == s.id %}selected{% endif %}>
          {{ s.name }}
        </option>
      {% endfor %}
    </select>
  </label>

  {# ── Confirmation warning ── #}
  {% if confirm_mode and flagged %}
  <div class="alert alert-warning" style="margin-top:1.5rem;">
    <strong>The following schedules have changes that affect generated events.</strong>
    <p class="recurrence-hint" style="margin:.25rem 0 .75rem;">
      Check a box to delete all future events in that series (including manually
      edited ones) and regenerate them. Leave unchecked to save schedule fields
      but keep existing events.
    </p>
    {% for item in flagged %}
    <div style="margin-bottom:.75rem;padding:.5rem;border:1px solid var(--muted-border-color);border-radius:var(--tp-radius);">
      <label style="display:flex;gap:.5rem;align-items:flex-start;">
        <input type="checkbox" name="{{ item.confirm_key }}" style="margin-top:.2rem;">
        <span>
          <strong>{{ item.title }}</strong>
          {% if item.type == 'removed' %}&mdash; will be removed
          {% else %}&mdash; schedule changed{% endif %}
          <br>
          <small>
            {% if item.future_count %}
              {{ item.future_count }} future event{{ 's' if item.future_count != 1 }} would be deleted
            {% else %}
              No future events to delete
            {% endif %}
          </small>
        </span>
      </label>
    </div>
    {% endfor %}
  </div>
  {% endif %}

  {# ── Recurring Schedules (edit-only) ── #}
  {% if team %}
  <fieldset style="margin-top:1.5rem;">
    <legend>Recurring Schedules</legend>
    <p class="recurrence-hint">
      Define recurring event patterns for this team. Events are auto-generated
      on save. Leave <em>End Date</em> blank to use the season's end date.
    </p>

    <div id="schedule-rows">
      {% for row in schedule_rows %}
      <div class="schedule-row"
           style="border:1px solid var(--muted-border-color);border-radius:var(--tp-radius);padding:1rem;margin-bottom:.75rem;">
        <input type="hidden" class="sched-id" value="{{ row.id }}">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem;">
          <strong style="font-size:.9rem;">Schedule</strong>
          <button type="button" class="btn btn-sm btn-danger"
                  onclick="removeRow(this)">Remove</button>
        </div>
        <label>Title *
          <input type="text" class="sched-title" required value="{{ row.title }}"
                 oninput="this.dataset.auto=''"
                 {% if row.id %}data-auto=""{% endif %}
                 placeholder="Team - Training Tuesday">
        </label>
        <div class="form-grid-2">
          <label>Event Type
            <select class="sched-event-type"
                    onchange="updateDefaultTitle(this.closest('.schedule-row'))">
              {% for val, lbl in [('training','Training'),('match','Match'),('other','Other')] %}
                <option value="{{ val }}"
                        {% if row.event_type == val %}selected{% endif %}>{{ lbl }}</option>
              {% endfor %}
            </select>
          </label>
          <label>Recurrence
            <select class="sched-rule"
                    onchange="updateDefaultTitle(this.closest('.schedule-row'))">
              {% for val, lbl in [('weekly','Weekly'),('biweekly','Biweekly'),('monthly','Monthly')] %}
                <option value="{{ val }}"
                        {% if row.recurrence_rule == val %}selected{% endif %}>{{ lbl }}</option>
              {% endfor %}
            </select>
          </label>
        </div>
        <div class="form-grid-2">
          <label>Start Date *
            <input type="date" class="sched-start" required value="{{ row.start_date }}"
                   onchange="updateDefaultTitle(this.closest('.schedule-row'))">
          </label>
          <label>End Date <small>(blank = season end)</small>
            <input type="date" class="sched-end" value="{{ row.end_date }}">
          </label>
        </div>
        <div class="form-grid-2">
          <label>Start Time
            <input type="time" class="sched-time" value="{{ row.event_time }}">
          </label>
          <label>End Time
            <input type="time" class="sched-end-time" value="{{ row.event_end_time }}">
          </label>
        </div>
        <label>Location
          <input type="text" class="sched-location" value="{{ row.location }}">
        </label>
        <details style="margin-top:.5rem;">
          <summary style="cursor:pointer;font-size:.88rem;color:var(--tp-muted);">
            Meeting details
          </summary>
          <div style="margin-top:.5rem;" class="form-grid-2">
            <label>Meeting Time
              <input type="time" class="sched-meeting-time"
                     value="{{ row.meeting_time }}">
            </label>
            <label>Meeting Location
              <input type="text" class="sched-meeting-location"
                     value="{{ row.meeting_location }}">
            </label>
          </div>
        </details>
        <label style="margin-top:.5rem;">Presence
          <select class="sched-presence">
            {% for val, lbl in [('normal','Normal'),('all','All'),('selection','Selection'),('available','Available'),('no_registration','No Registration')] %}
              <option value="{{ val }}"
                      {% if row.presence_type == val %}selected{% endif %}>{{ lbl }}</option>
            {% endfor %}
          </select>
        </label>
        <label>Description
          <textarea class="sched-desc">{{ row.description }}</textarea>
        </label>
      </div>
      {% endfor %}
    </div>

    <button type="button" class="btn btn-outline btn-sm"
            onclick="addScheduleRow()" style="margin-top:.25rem;">
      + Add Schedule
    </button>
  </fieldset>
  {% endif %}

  <div class="form-footer">
    <button type="submit" class="btn btn-primary">
      {% if confirm_mode %}Confirm &amp; Save
      {% elif team %}Save Changes
      {% else %}Create Team{% endif %}
    </button>
    <a href="/teams" class="btn btn-outline">Cancel</a>
  </div>
</form>
</div>

{# ── Row template (hidden, cloned by JS) ── #}
{% if team %}
<template id="schedule-row-tpl">
  <div class="schedule-row"
       style="border:1px solid var(--muted-border-color);border-radius:var(--tp-radius);padding:1rem;margin-bottom:.75rem;">
    <input type="hidden" class="sched-id" value="">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem;">
      <strong style="font-size:.9rem;">Schedule</strong>
      <button type="button" class="btn btn-sm btn-danger"
              onclick="removeRow(this)">Remove</button>
    </div>
    <label>Title *
      <input type="text" class="sched-title" required value=""
             oninput="this.dataset.auto=''"
             placeholder="Team - Training Tuesday">
    </label>
    <div class="form-grid-2">
      <label>Event Type
        <select class="sched-event-type"
                onchange="updateDefaultTitle(this.closest('.schedule-row'))">
          <option value="training">Training</option>
          <option value="match">Match</option>
          <option value="other">Other</option>
        </select>
      </label>
      <label>Recurrence
        <select class="sched-rule"
                onchange="updateDefaultTitle(this.closest('.schedule-row'))">
          <option value="weekly">Weekly</option>
          <option value="biweekly">Biweekly</option>
          <option value="monthly">Monthly</option>
        </select>
      </label>
    </div>
    <div class="form-grid-2">
      <label>Start Date *
        <input type="date" class="sched-start" required value=""
               onchange="updateDefaultTitle(this.closest('.schedule-row'))">
      </label>
      <label>End Date <small>(blank = season end)</small>
        <input type="date" class="sched-end" value="">
      </label>
    </div>
    <div class="form-grid-2">
      <label>Start Time
        <input type="time" class="sched-time" value="">
      </label>
      <label>End Time
        <input type="time" class="sched-end-time" value="">
      </label>
    </div>
    <label>Location
      <input type="text" class="sched-location" value="">
    </label>
    <details style="margin-top:.5rem;">
      <summary style="cursor:pointer;font-size:.88rem;color:var(--tp-muted);">
        Meeting details
      </summary>
      <div style="margin-top:.5rem;" class="form-grid-2">
        <label>Meeting Time
          <input type="time" class="sched-meeting-time" value="">
        </label>
        <label>Meeting Location
          <input type="text" class="sched-meeting-location" value="">
        </label>
      </div>
    </details>
    <label style="margin-top:.5rem;">Presence
      <select class="sched-presence">
        <option value="normal">Normal</option>
        <option value="all">All</option>
        <option value="selection">Selection</option>
        <option value="available">Available</option>
        <option value="no_registration">No Registration</option>
      </select>
    </label>
    <label>Description
      <textarea class="sched-desc"></textarea>
    </label>
  </div>
</template>

<script>
const TEAM_NAME = {{ team.name | tojson }};
const DAYS = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];

function updateDefaultTitle(row) {
  const titleInput = row.querySelector('.sched-title');
  // data-auto attribute present means user has manually edited — skip auto-fill
  if ('auto' in titleInput.dataset) return;
  const eventType = row.querySelector('.sched-event-type').value;
  const rule = row.querySelector('.sched-rule').value;
  const startDate = row.querySelector('.sched-start').value;
  const labelMap = {training: 'Training', match: 'Match', other: 'Other'};
  let title = TEAM_NAME + ' - ' + (labelMap[eventType] || eventType);
  if (rule === 'weekly' && startDate) {
    // Append T00:00:00 to prevent UTC timezone offset from shifting the day
    const d = new Date(startDate + 'T00:00:00');
    title += ' ' + DAYS[d.getDay()];
  }
  titleInput.value = title;
}

function addScheduleRow() {
  const tpl = document.getElementById('schedule-row-tpl');
  const clone = tpl.content.cloneNode(true);
  document.getElementById('schedule-rows').appendChild(clone);
}

function removeRow(btn) {
  btn.closest('.schedule-row').remove();
}

// Re-index all rows to 0..N-1 and inject sched_count before submit
document.getElementById('team-form').addEventListener('submit', function() {
  const rows = document.querySelectorAll('#schedule-rows .schedule-row');
  rows.forEach(function(row, i) {
    row.querySelector('.sched-id').name            = 'sched_id_'            + i;
    row.querySelector('.sched-title').name         = 'sched_title_'         + i;
    row.querySelector('.sched-event-type').name    = 'sched_event_type_'    + i;
    row.querySelector('.sched-rule').name          = 'sched_rule_'          + i;
    row.querySelector('.sched-start').name         = 'sched_start_'         + i;
    row.querySelector('.sched-end').name           = 'sched_end_'           + i;
    row.querySelector('.sched-time').name          = 'sched_time_'          + i;
    row.querySelector('.sched-end-time').name      = 'sched_end_time_'      + i;
    row.querySelector('.sched-location').name      = 'sched_location_'      + i;
    row.querySelector('.sched-meeting-time').name  = 'sched_meeting_time_'  + i;
    row.querySelector('.sched-meeting-location').name = 'sched_meeting_location_' + i;
    row.querySelector('.sched-presence').name      = 'sched_presence_'      + i;
    row.querySelector('.sched-desc').name          = 'sched_desc_'          + i;
  });
  let countField = document.getElementById('sched-count-field');
  if (!countField) {
    countField = document.createElement('input');
    countField.type = 'hidden';
    countField.id = 'sched-count-field';
    countField.name = 'sched_count';
    this.appendChild(countField);
  }
  countField.value = rows.length;
});
</script>
{% endif %}
{% endblock %}
```

- [ ] **Step 5: Verify the page renders**

Visit `http://localhost:7000/teams/1/edit`. The page should show the Recurring Schedules fieldset with an "+ Add Schedule" button. Click it — a new blank schedule row should appear without a page reload.

- [ ] **Step 6: Commit**

```bash
git add templates/teams/form.html
git commit -m "feat: add Recurring Schedules fieldset to team edit page"
```

---

## Chunk 3: Tests

### Task 5: Integration tests for the schedule save flow

**Files:**
- Modify: `tests/test_teams.py`

- [ ] **Step 1: Append integration tests to `tests/test_teams.py`**

```python
# ---------------------------------------------------------------------------
# Recurring schedules
# ---------------------------------------------------------------------------

from datetime import date
from unittest.mock import patch


def _make_team_for_sched(db, name="Eagles"):
    from models.team import Team
    team = Team(name=name)
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


def _sched_form_data(i=0, title="Eagles - Training Tuesday", event_type="training",
                     rule="weekly", start="2026-03-03", end="2026-03-24",
                     sched_id=""):
    return {
        f"sched_id_{i}": sched_id,
        f"sched_title_{i}": title,
        f"sched_event_type_{i}": event_type,
        f"sched_rule_{i}": rule,
        f"sched_start_{i}": start,
        f"sched_end_{i}": end,
        f"sched_time_{i}": "18:00",
        f"sched_end_time_{i}": "",
        f"sched_location_{i}": "Gym A",
        f"sched_meeting_time_{i}": "",
        f"sched_meeting_location_{i}": "",
        f"sched_presence_{i}": "normal",
        f"sched_desc_{i}": "",
        "sched_count": "1",
    }


def test_new_schedule_creates_events(admin_client, db):
    team = _make_team_for_sched(db)
    data = {"name": team.name, "description": "", "season_id": ""}
    data.update(_sched_form_data(start="2026-03-03", end="2026-03-24"))

    with patch("services.schedule_service.ensure_attendance_records"):
        resp = admin_client.post(f"/teams/{team.id}/edit", data=data,
                                 follow_redirects=False)

    assert resp.status_code == 302

    from models.event import Event
    from models.team_recurring_schedule import TeamRecurringSchedule
    db.expire_all()

    scheds = db.query(TeamRecurringSchedule).filter_by(team_id=team.id).all()
    assert len(scheds) == 1

    events = (db.query(Event).filter_by(team_id=team.id)
              .order_by(Event.event_date).all())
    assert len(events) == 4  # Mar 3, 10, 17, 24
    assert events[0].event_date == date(2026, 3, 3)
    assert all(e.recurrence_group_id == scheds[0].recurrence_group_id for e in events)


def test_changed_schedule_triggers_confirmation(admin_client, db):
    from models.team_recurring_schedule import TeamRecurringSchedule
    from services.schedule_service import new_group_id

    team = _make_team_for_sched(db)
    sched = TeamRecurringSchedule(
        team_id=team.id, title="Eagles - Training Tuesday",
        event_type="training", recurrence_rule="weekly",
        start_date=date(2026, 3, 3), end_date=date(2026, 3, 24),
        presence_type="normal", recurrence_group_id=new_group_id(),
    )
    db.add(sched)
    db.commit()
    db.refresh(sched)

    # Change the start_date — should trigger confirmation step
    data = {"name": team.name, "description": "", "season_id": ""}
    data.update(_sched_form_data(sched_id=str(sched.id), start="2026-03-10"))

    resp = admin_client.post(f"/teams/{team.id}/edit", data=data,
                             follow_redirects=False)

    assert resp.status_code == 200
    assert b"confirm" in resp.content.lower()


def test_confirmed_schedule_regenerates_events(admin_client, db):
    from models.event import Event
    from models.team_recurring_schedule import TeamRecurringSchedule
    from services.schedule_service import new_group_id, sign_payload

    team = _make_team_for_sched(db)
    group_id = new_group_id()
    sched = TeamRecurringSchedule(
        team_id=team.id, title="Eagles - Training Tuesday",
        event_type="training", recurrence_rule="weekly",
        start_date=date(2026, 3, 3), end_date=date(2026, 3, 24),
        presence_type="normal", recurrence_group_id=group_id,
    )
    db.add(sched)
    future_ev = Event(
        title="Eagles - Training Tuesday", event_type="training",
        event_date=date(2099, 3, 10), recurrence_group_id=group_id,
        team_id=team.id,
    )
    db.add(future_ev)
    db.commit()
    db.refresh(sched)
    old_ev_id = future_ev.id

    payload = sign_payload({"team_id": team.id, "rows": [{
        "id": str(sched.id),
        "recurrence_group_id": group_id,
        "title": "Eagles - Training Tuesday",
        "event_type": "training",
        "recurrence_rule": "weekly",
        "start_date": "2026-03-10",  # changed
        "end_date": "2026-03-24",
        "event_time": "",
        "event_end_time": "",
        "location": "",
        "meeting_time": "",
        "meeting_location": "",
        "presence_type": "normal",
        "description": "",
    }]})

    data = {
        "name": team.name, "description": "", "season_id": "",
        "_confirm_step": "1",
        "_schedules_json": payload,
        f"confirm_schedule_{sched.id}": "on",
    }

    with patch("services.schedule_service.ensure_attendance_records"):
        resp = admin_client.post(f"/teams/{team.id}/edit", data=data,
                                 follow_redirects=False)

    assert resp.status_code == 302

    db.expire_all()
    # Old future event was deleted
    assert db.query(Event).filter_by(id=old_ev_id).first() is None
    # New events start from new start_date
    events = (db.query(Event).filter_by(team_id=team.id)
              .order_by(Event.event_date).all())
    assert len(events) > 0
    assert events[0].event_date == date(2026, 3, 10)
    # New events must have a different recurrence_group_id (regeneration assigns new UUID)
    assert events[0].recurrence_group_id != group_id


def test_removed_schedule_without_confirm_keeps_events(admin_client, db):
    from models.event import Event
    from models.team_recurring_schedule import TeamRecurringSchedule
    from services.schedule_service import new_group_id, sign_payload

    team = _make_team_for_sched(db)
    group_id = new_group_id()
    sched = TeamRecurringSchedule(
        team_id=team.id, title="T", event_type="training",
        recurrence_rule="weekly", start_date=date(2026, 3, 3),
        end_date=date(2026, 3, 24), presence_type="normal",
        recurrence_group_id=group_id,
    )
    db.add(sched)
    future_ev = Event(
        title="T", event_type="training", event_date=date(2099, 1, 1),
        recurrence_group_id=group_id, team_id=team.id,
    )
    db.add(future_ev)
    db.commit()
    db.refresh(sched)
    ev_id = future_ev.id
    sched_id = sched.id

    # Confirmation step: schedule removed, checkbox NOT checked
    payload = sign_payload({"team_id": team.id, "rows": []})
    data = {
        "name": team.name, "description": "", "season_id": "",
        "_confirm_step": "1",
        "_schedules_json": payload,
        # confirm_schedule_{id} absent = unchecked
    }

    resp = admin_client.post(f"/teams/{team.id}/edit", data=data,
                             follow_redirects=False)

    assert resp.status_code == 302
    db.expire_all()
    assert db.query(TeamRecurringSchedule).filter_by(id=sched_id).first() is not None
    assert db.query(Event).filter_by(id=ev_id).first() is not None


def test_removed_schedule_with_confirm_deletes_events(admin_client, db):
    from models.event import Event
    from models.team_recurring_schedule import TeamRecurringSchedule
    from services.schedule_service import new_group_id, sign_payload

    team = _make_team_for_sched(db)
    group_id = new_group_id()
    sched = TeamRecurringSchedule(
        team_id=team.id, title="T", event_type="training",
        recurrence_rule="weekly", start_date=date(2026, 3, 3),
        end_date=date(2026, 3, 24), presence_type="normal",
        recurrence_group_id=group_id,
    )
    db.add(sched)
    future_ev = Event(
        title="T", event_type="training", event_date=date(2099, 1, 1),
        recurrence_group_id=group_id, team_id=team.id,
    )
    db.add(future_ev)
    db.commit()
    db.refresh(sched)
    ev_id = future_ev.id
    sched_id = sched.id

    # Confirmation step: schedule removed, checkbox IS checked
    payload = sign_payload({"team_id": team.id, "rows": []})
    data = {
        "name": team.name, "description": "", "season_id": "",
        "_confirm_step": "1",
        "_schedules_json": payload,
        f"confirm_schedule_{sched_id}": "on",  # checked
    }

    resp = admin_client.post(f"/teams/{team.id}/edit", data=data,
                             follow_redirects=False)

    assert resp.status_code == 302
    db.expire_all()
    # Schedule is deleted
    assert db.query(TeamRecurringSchedule).filter_by(id=sched_id).first() is None
    # Future event is deleted
    assert db.query(Event).filter_by(id=ev_id).first() is None


def test_changed_schedule_unconfirmed_saves_fields_keeps_events(admin_client, db):
    """Changed schedule with checkbox unchecked: fields updated, events untouched."""
    from models.event import Event
    from models.team_recurring_schedule import TeamRecurringSchedule
    from services.schedule_service import new_group_id, sign_payload

    team = _make_team_for_sched(db)
    group_id = new_group_id()
    sched = TeamRecurringSchedule(
        team_id=team.id, title="Eagles - Training Tuesday",
        event_type="training", recurrence_rule="weekly",
        start_date=date(2026, 3, 3), end_date=date(2026, 3, 24),
        event_time=None, presence_type="normal",
        recurrence_group_id=group_id,
    )
    db.add(sched)
    future_ev = Event(
        title="Eagles - Training Tuesday", event_type="training",
        event_date=date(2099, 3, 10), recurrence_group_id=group_id,
        team_id=team.id,
    )
    db.add(future_ev)
    db.commit()
    db.refresh(sched)
    ev_id = future_ev.id
    sched_id = sched.id
    original_ev_date = future_ev.event_date

    # Confirmation step: start_date changed, checkbox NOT checked
    payload = sign_payload({"team_id": team.id, "rows": [{
        "id": str(sched.id),
        "recurrence_group_id": group_id,
        "title": "Eagles - Training Tuesday",
        "event_type": "training",
        "recurrence_rule": "weekly",
        "start_date": "2026-03-10",  # key field changed
        "end_date": "2026-03-24",
        "event_time": "",
        "event_end_time": "",
        "location": "",
        "meeting_time": "",
        "meeting_location": "",
        "presence_type": "normal",
        "description": "",
    }]})
    data = {
        "name": team.name, "description": "", "season_id": "",
        "_confirm_step": "1",
        "_schedules_json": payload,
        # confirm_schedule_{id} absent = unchecked
    }

    resp = admin_client.post(f"/teams/{team.id}/edit", data=data,
                             follow_redirects=False)

    assert resp.status_code == 302
    db.expire_all()
    # Schedule fields were updated
    updated = db.query(TeamRecurringSchedule).filter_by(id=sched_id).first()
    assert updated is not None
    assert updated.start_date == date(2026, 3, 10)
    # Future event was NOT touched (same id, same date, same recurrence_group_id)
    ev = db.query(Event).filter_by(id=ev_id).first()
    assert ev is not None
    assert ev.event_date == original_ev_date
    assert ev.recurrence_group_id == group_id
```

- [ ] **Step 2: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_teams.py
git commit -m "test: integration tests for recurring schedule save flow"
```

---

## Final Verification

- [ ] **Full test suite**

```bash
pytest tests/ -v
```

Expected: all green

- [ ] **Manual smoke test**

1. Visit `http://localhost:7000/teams/1/edit`
2. Click "+ Add Schedule" — a blank row appears
3. Fill in Title, pick Weekly, set a Start Date (a Tuesday) and End Date a few weeks out, set a time
4. Save — redirects back, "Changes saved" banner; check `/events?team_id=1` to confirm events exist
5. Return to team edit, change the schedule's Start Date by one week
6. Save — confirmation warning appears with checkbox
7. Check the box and submit — events regenerated from new start date
8. Remove the schedule row, save — confirmation warning; check box and submit — future events deleted

- [ ] **Final commit**

```bash
git add -A
git commit -m "feat: team recurring schedules — complete implementation"
```
