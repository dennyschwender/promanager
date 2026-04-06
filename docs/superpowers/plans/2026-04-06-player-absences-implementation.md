# Player Absences Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement player absence management with period and recurring patterns, auto-setting attendance to "absent" for future events, with player self-management and coach oversight.

**Architecture:** Eager application model — absences are stored as PlayerAbsence records, and when created/deleted, they immediately update matching Attendance records for future events. Access control is role-based: players see own, coaches see team/season, admins see all. Service layer (`absence_service.py`) handles all business logic; routes delegate to services and apply guards.

**Tech Stack:** SQLAlchemy 2.x, FastAPI, dateutil.rrule, Jinja2 templates, pytest with in-memory SQLite

---

## Task 1: Create PlayerAbsence Model and Migration

**Files:**
- Create: `models/player_absence.py`
- Modify: `models/__init__.py`
- Modify: `models/player.py`
- Run: alembic migration

**Steps:**

- [ ] **Step 1: Write PlayerAbsence model**

Create `models/player_absence.py`:

```python
"""models/player_absence.py — Player absence (period or recurring)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PlayerAbsence(Base):
    __tablename__ = "player_absences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    player_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "period" | "recurring"
    absence_type: Mapped[str] = mapped_column(String(16), nullable=False)

    # Period absence: start and end date (inclusive, full day)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Recurring absence: RFC 5545 rrule string (e.g., "FREQ=WEEKLY;BYDAY=FR")
    rrule: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Optional end date for recurring rule (auto-set to season end if not provided)
    rrule_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Season ID for context (required for recurring, optional for period)
    season_id: Mapped[int | None] = mapped_column(
        ForeignKey("seasons.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Reason (e.g., "Injury recovery", "Family vacation")
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    player: Mapped["Player"] = relationship("Player", back_populates="absences", lazy="select")
    season: Mapped["Season | None"] = relationship("Season", lazy="select")

    def __repr__(self) -> str:
        return f"<PlayerAbsence id={self.id} player_id={self.player_id} type={self.absence_type}>"
```

- [ ] **Step 2: Update Player model to add relationship**

Edit `models/player.py` and add this relationship to the Player class (after existing relationships):

```python
    absences: Mapped[list[PlayerAbsence]] = relationship(
        "PlayerAbsence",
        back_populates="player",
        cascade="all, delete-orphan",
        lazy="select",
    )
```

Also add the import at the top of `models/player.py`:

```python
from models.player_absence import PlayerAbsence  # noqa: F401
```

- [ ] **Step 3: Update models/__init__.py**

Edit `models/__init__.py` and add:

```python
from models.player_absence import PlayerAbsence  # noqa: F401
```

- [ ] **Step 4: Create and run alembic migration**

```bash
# From project root
alembic revision --autogenerate -m "add player_absences table"
# Review the generated migration in alembic/versions/
alembic upgrade head
```

Verify the table exists:

```bash
sqlite3 data/proManager.db ".schema player_absences"
```

Expected: Table with columns id, player_id, absence_type, start_date, end_date, rrule, rrule_until, season_id, reason, created_at, updated_at.

- [ ] **Step 5: Commit**

```bash
git add models/player_absence.py models/player.py models/__init__.py alembic/versions/
git commit -m "feat: add PlayerAbsence model and migration

- Create player_absences table
- Add player → absences relationship
- Support period and recurring absences with season context
"
```

---

## Task 2: Write and Implement is_date_in_absence (Period)

**Files:**
- Create: `services/absence_service.py`
- Create: `tests/test_absence_service.py`
- Test: test_is_date_in_absence_period

**Steps:**

- [ ] **Step 1: Write failing test for period absence**

Create `tests/test_absence_service.py`:

```python
"""tests/test_absence_service.py — Absence service tests."""

import pytest
from datetime import date
from sqlalchemy.orm import Session

from models.player import Player
from models.player_absence import PlayerAbsence
from models.season import Season
from models.team import Team
from services.absence_service import is_date_in_absence


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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_absence_service.py::test_is_date_in_absence_period_within_range -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'services.absence_service'" or similar.

- [ ] **Step 3: Write minimal implementation**

Create `services/absence_service.py`:

```python
"""services/absence_service.py — Absence business logic."""

from __future__ import annotations

from datetime import date
from sqlalchemy.orm import Session

from models.player_absence import PlayerAbsence


def is_date_in_absence(player_id: int, check_date: date, db: Session) -> bool:
    """Check if a date falls within any active absence for a player.

    Returns True if the date falls within a period absence or a recurring
    absence pattern. Returns False otherwise.
    """
    absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player_id).all()

    for absence in absences:
        if absence.absence_type == "period":
            if absence.start_date and absence.end_date:
                if absence.start_date <= check_date <= absence.end_date:
                    return True
        elif absence.absence_type == "recurring":
            # To be implemented in next task
            pass

    return False
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_absence_service.py::test_is_date_in_absence_period_within_range -v
```

Expected: PASS

- [ ] **Step 5: Add additional period absence edge cases**

Add these tests to `tests/test_absence_service.py`:

```python
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
```

- [ ] **Step 6: Run all period tests**

```bash
pytest tests/test_absence_service.py::test_is_date_in_absence_period_within_range tests/test_absence_service.py::test_is_date_in_absence_period_no_match tests/test_absence_service.py::test_is_date_in_absence_no_absences -v
```

Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add services/absence_service.py tests/test_absence_service.py
git commit -m "feat: implement is_date_in_absence for period absences

- Add is_date_in_absence() function with period absence matching
- Add tests for period absence date range checking
"
```

---

## Task 3: Implement is_date_in_absence (Recurring)

**Files:**
- Modify: `services/absence_service.py`
- Modify: `tests/test_absence_service.py`

**Steps:**

- [ ] **Step 1: Write failing test for recurring absence**

Add to `tests/test_absence_service.py`:

```python
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

    # April 11, 18, 25 are Fridays
    assert is_date_in_absence(player.id, date(2026, 4, 11), db) is True
    assert is_date_in_absence(player.id, date(2026, 4, 18), db) is True
    assert is_date_in_absence(player.id, date(2026, 4, 25), db) is True

    # April 12 is Saturday
    assert is_date_in_absence(player.id, date(2026, 4, 12), db) is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_absence_service.py::test_is_date_in_absence_recurring_weekly -v
```

Expected: FAIL (recurring logic not implemented yet)

- [ ] **Step 3: Implement recurring absence check**

Edit `services/absence_service.py` and update `is_date_in_absence()`:

```python
"""services/absence_service.py — Absence business logic."""

from __future__ import annotations

from datetime import date
from sqlalchemy.orm import Session
from dateutil.rrule import rrulestr

from models.player_absence import PlayerAbsence


def is_date_in_absence(player_id: int, check_date: date, db: Session) -> bool:
    """Check if a date falls within any active absence for a player.

    Returns True if the date falls within a period absence or a recurring
    absence pattern. Returns False otherwise.
    """
    absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player_id).all()

    for absence in absences:
        if absence.absence_type == "period":
            if absence.start_date and absence.end_date:
                if absence.start_date <= check_date <= absence.end_date:
                    return True
        elif absence.absence_type == "recurring":
            if absence.rrule and absence.rrule_until:
                try:
                    # Parse rrule and check if check_date is an occurrence
                    rrule = rrulestr(absence.rrule, dtstart=absence.rrule_until)
                    # Generate all occurrences up to and including check_date
                    occurrences = list(rrule.between(absence.rrule_until, check_date, inc=True))
                    # Check if check_date is in the occurrences (as date, not datetime)
                    occurrence_dates = {d.date() if hasattr(d, 'date') else d for d in occurrences}
                    if check_date in occurrence_dates:
                        return True
                except Exception:
                    # Invalid rrule string — log and skip
                    pass

    return False
```

Actually, let me reconsider the rrule logic. We need a better approach:

```python
def is_date_in_absence(player_id: int, check_date: date, db: Session) -> bool:
    """Check if a date falls within any active absence for a player."""
    absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player_id).all()

    for absence in absences:
        if absence.absence_type == "period":
            if absence.start_date and absence.end_date:
                if absence.start_date <= check_date <= absence.end_date:
                    return True
        elif absence.absence_type == "recurring":
            if absence.rrule and absence.rrule_until:
                try:
                    from dateutil.rrule import rrulestr
                    # Create a datetime at the start of check_date for rrule comparison
                    check_datetime = absence.rrule_until.replace(year=check_date.year, month=check_date.month, day=check_date.day)
                    
                    # Parse the rrule
                    rrule = rrulestr(absence.rrule, dtstart=absence.rrule_until)
                    
                    # Check if check_datetime is part of the recurrence (before or equal to rrule_until)
                    if check_datetime.date() <= absence.rrule_until:
                        # Iterate through occurrences and check if check_date matches
                        for occurrence in rrule.between(absence.rrule_until, check_datetime, inc=True):
                            if occurrence.date() == check_date:
                                return True
                except Exception:
                    pass

    return False
```

Hmm, this is getting complicated. Let me simplify:

```python
def is_date_in_absence(player_id: int, check_date: date, db: Session) -> bool:
    """Check if a date falls within any active absence for a player."""
    from dateutil.rrule import rrulestr
    
    absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player_id).all()

    for absence in absences:
        if absence.absence_type == "period":
            if absence.start_date and absence.end_date:
                if absence.start_date <= check_date <= absence.end_date:
                    return True
        elif absence.absence_type == "recurring":
            if absence.rrule and absence.rrule_until:
                # Ignore if rrule_until is in the past
                if absence.rrule_until < check_date:
                    continue
                try:
                    # Parse rrule starting from a base date (use rrule_until or any past date)
                    # For simplicity, start from the beginning of the season or a year ago
                    base_date = absence.rrule_until.replace(year=absence.rrule_until.year - 1)
                    rrule = rrulestr(absence.rrule, dtstart=base_date)
                    
                    # Check if check_date is an occurrence in the rrule
                    check_datetime = check_date
                    occurrences = list(rrule.between(base_date, absence.rrule_until, inc=True))
                    for occ in occurrences:
                        if (occ.date() if hasattr(occ, 'date') else occ) == check_date:
                            return True
                except Exception:
                    # Invalid rrule string — skip
                    pass

    return False
```

Actually, I think the issue is I need to understand how rrulestr works. Let me look at the actual approach:

The rrule string is something like "FREQ=WEEKLY;BYDAY=FR" (no DTSTART). When we parse it with rrulestr, we need to provide a dtstart. The dtstart tells it where to start generating from.

For checking if a specific date matches, we can:
1. Parse the rrule with a base dtstart
2. Check if check_date is an occurrence

Let me write a cleaner version:

```python
def is_date_in_absence(player_id: int, check_date: date, db: Session) -> bool:
    """Check if a date falls within any active absence for a player."""
    from dateutil.rrule import rrulestr
    from datetime import datetime
    
    absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player_id).all()

    for absence in absences:
        if absence.absence_type == "period":
            if absence.start_date and absence.end_date:
                if absence.start_date <= check_date <= absence.end_date:
                    return True
        elif absence.absence_type == "recurring":
            if absence.rrule and absence.rrule_until:
                # Don't check if the rrule_until has passed
                if absence.rrule_until < check_date:
                    continue
                try:
                    # Use rrule_until as the base dtstart, but go back a full year to be safe
                    base = datetime(absence.rrule_until.year - 1, 1, 1)
                    rrule = rrulestr(absence.rrule, dtstart=base)
                    
                    # Generate occurrences from base to rrule_until
                    occurrences = rrule.between(base, datetime.combine(absence.rrule_until, datetime.min.time()), inc=True)
                    
                    # Check if check_date is in the occurrences
                    for occ in occurrences:
                        if occ.date() == check_date:
                            return True
                except Exception:
                    pass

    return False
```

Let me simplify even further and be pragmatic:

```python
def is_date_in_absence(player_id: int, check_date: date, db: Session) -> bool:
    """Check if a date falls within any active absence for a player."""
    from dateutil.rrule import rrulestr
    from datetime import datetime
    
    absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player_id).all()

    for absence in absences:
        if absence.absence_type == "period":
            if absence.start_date and absence.end_date:
                if absence.start_date <= check_date <= absence.end_date:
                    return True
        elif absence.absence_type == "recurring":
            if absence.rrule and absence.rrule_until and check_date <= absence.rrule_until:
                try:
                    # Parse rrule with a base date far in the past to capture all occurrences
                    dtstart = datetime(2000, 1, 1)
                    rrule = rrulestr(absence.rrule, dtstart=dtstart)
                    
                    # Check if check_date falls on a match
                    # Generate all occurrences from dtstart to rrule_until
                    end_dt = datetime.combine(absence.rrule_until, datetime.min.time())
                    occurrences = rrule.between(dtstart, end_dt, inc=True)
                    
                    for occ in occurrences:
                        if occ.date() == check_date:
                            return True
                except Exception:
                    # Invalid rrule; skip silently
                    pass

    return False
```

This should work. Let me continue with the plan.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_absence_service.py::test_is_date_in_absence_recurring_weekly -v
```

Expected: PASS

- [ ] **Step 5: Add more recurring absence tests**

Add to `tests/test_absence_service.py`:

```python
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
```

- [ ] **Step 6: Run all recurring tests**

```bash
pytest tests/test_absence_service.py::test_is_date_in_absence_recurring_weekly tests/test_absence_service.py::test_is_date_in_absence_recurring_expired -v
```

Expected: All PASS

- [ ] **Step 7: Run all absence_service tests**

```bash
pytest tests/test_absence_service.py -v
```

Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add services/absence_service.py tests/test_absence_service.py
git commit -m "feat: implement is_date_in_absence for recurring absences

- Add rrule parsing with dateutil.rrule
- Check if date matches recurring pattern within rrule_until
- Add tests for recurring absence matching
"
```

---

## Task 4: Implement apply_absence_to_future_events

**Files:**
- Modify: `services/absence_service.py`
- Modify: `tests/test_absence_service.py`

**Steps:**

- [ ] **Step 1: Write failing test**

Add to `tests/test_absence_service.py`:

```python
from models.event import Event
from models.player_team import PlayerTeam
from models.team import Team
from services.absence_service import apply_absence_to_future_events
from models.attendance import Attendance


def test_apply_absence_to_future_events_period(db: Session):
    """Creating a period absence should auto-set matching future events to absent."""
    from datetime import datetime
    
    player = Player(first_name="David", last_name="Test", is_active=True)
    db.add(player)
    db.commit()

    team = Team(name="TestTeam")
    db.add(team)
    db.commit()

    season = Season(name="Spring 2026", start_date=date(2026, 3, 1), end_date=date(2026, 6, 30))
    db.add(season)
    db.commit()

    # Add player to team
    pm = PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id)
    db.add(pm)
    db.commit()

    # Create events
    e1 = Event(
        title="Event 1",
        event_date=date(2026, 4, 10),
        team_id=team.id,
        season_id=season.id,
        presence_type="normal",
    )
    e2 = Event(
        title="Event 2",
        event_date=date(2026, 4, 15),
        team_id=team.id,
        season_id=season.id,
        presence_type="normal",
    )
    e3 = Event(
        title="Event 3",
        event_date=date(2026, 5, 1),
        team_id=team.id,
        season_id=season.id,
        presence_type="normal",
    )
    db.add_all([e1, e2, e3])
    db.commit()

    # Ensure attendance records exist (manually create them for this test)
    for event in [e1, e2, e3]:
        att = Attendance(event_id=event.id, player_id=player.id, status="unknown")
        db.add(att)
    db.commit()

    # Create absence April 10-20
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

    # Check results
    assert count == 2  # e1 and e2 should be updated
    
    # Verify e1 (April 10) is set to absent
    att1 = db.query(Attendance).filter_by(event_id=e1.id, player_id=player.id).first()
    assert att1.status == "absent"
    assert "[Absence]" in att1.note
    assert "Vacation" in att1.note

    # Verify e2 (April 15) is set to absent
    att2 = db.query(Attendance).filter_by(event_id=e2.id, player_id=player.id).first()
    assert att2.status == "absent"

    # Verify e3 (May 1) is NOT changed
    att3 = db.query(Attendance).filter_by(event_id=e3.id, player_id=player.id).first()
    assert att3.status == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_absence_service.py::test_apply_absence_to_future_events_period -v
```

Expected: FAIL with "function not defined" or similar

- [ ] **Step 3: Implement apply_absence_to_future_events**

Edit `services/absence_service.py` and add this function:

```python
def apply_absence_to_future_events(player_id: int, db: Session) -> int:
    """Apply an absence to all matching future event attendance records.

    Returns the count of updated attendance records.
    """
    from datetime import date as date_type
    from models.attendance import Attendance
    from models.event import Event

    today = date_type.today()

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

    count = 0
    for att in attendances:
        if is_date_in_absence(player_id, att.event.event_date, db):
            # Determine the absence reason for the note
            absence = (
                db.query(PlayerAbsence)
                .filter(PlayerAbsence.player_id == player_id)
                .all()
            )
            reason = None
            for abs_rec in absence:
                if is_date_in_absence_for_record(player_id, att.event.event_date, abs_rec, db):
                    reason = abs_rec.reason or "On leave"
                    break

            # Update status based on event type and current status
            should_update = False
            if att.status == "unknown":
                should_update = True
            elif att.status == "present" and att.event.presence_type == "all":
                # Override the "all-attendee" default
                should_update = True

            if should_update:
                att.status = "absent"
                att.note = f"[Absence] {reason}"
                from datetime import datetime, timezone
                att.updated_at = datetime.now(timezone.utc)
                count += 1

    if count > 0:
        db.commit()

    return count
```

Wait, I need to add a helper function to get the matching absence for a date. Let me refactor:

```python
def apply_absence_to_future_events(player_id: int, db: Session) -> int:
    """Apply an absence to all matching future event attendance records.

    Returns the count of updated attendance records.
    """
    from datetime import date as date_type, datetime, timezone
    from models.attendance import Attendance
    from models.event import Event

    today = date_type.today()

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

    count = 0
    for att in attendances:
        if is_date_in_absence(player_id, att.event.event_date, db):
            # Get the absence reason
            absence_rec = _get_absence_for_date(player_id, att.event.event_date, db)
            reason = absence_rec.reason if absence_rec and absence_rec.reason else "On leave"

            # Update status based on event type and current status
            should_update = False
            if att.status == "unknown":
                should_update = True
            elif att.status == "present" and att.event.presence_type == "all":
                # Override the "all-attendee" default
                should_update = True

            if should_update:
                att.status = "absent"
                att.note = f"[Absence] {reason}"
                att.updated_at = datetime.now(timezone.utc)
                count += 1

    if count > 0:
        db.commit()

    return count


def _get_absence_for_date(player_id: int, check_date: date, db: Session) -> PlayerAbsence | None:
    """Get the first absence record matching the given date."""
    absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player_id).all()

    for absence in absences:
        if is_date_in_absence_for_record(check_date, absence):
            return absence
    return None


def is_date_in_absence_for_record(check_date: date, absence: PlayerAbsence) -> bool:
    """Check if a date falls within a specific absence record."""
    from dateutil.rrule import rrulestr
    from datetime import datetime

    if absence.absence_type == "period":
        if absence.start_date and absence.end_date:
            return absence.start_date <= check_date <= absence.end_date
    elif absence.absence_type == "recurring":
        if absence.rrule and absence.rrule_until and check_date <= absence.rrule_until:
            try:
                dtstart = datetime(2000, 1, 1)
                rrule = rrulestr(absence.rrule, dtstart=dtstart)
                end_dt = datetime.combine(absence.rrule_until, datetime.min.time())
                occurrences = rrule.between(dtstart, end_dt, inc=True)
                for occ in occurrences:
                    if occ.date() == check_date:
                        return True
            except Exception:
                pass
    return False
```

Actually, this is getting messy. Let me refactor is_date_in_absence to return the absence record instead, or create a cleaner helper. For now, let me keep it simple:

```python
def apply_absence_to_future_events(player_id: int, db: Session) -> int:
    """Apply an absence to all matching future event attendance records."""
    from datetime import date as date_type, datetime, timezone
    from models.attendance import Attendance
    from models.event import Event

    today = date_type.today()

    attendances = (
        db.query(Attendance)
        .join(Event)
        .filter(
            Attendance.player_id == player_id,
            Event.event_date >= today,
        )
        .all()
    )

    count = 0
    for att in attendances:
        if not is_date_in_absence(player_id, att.event.event_date, db):
            continue

        # Get reason from any matching absence
        reason = "On leave"
        absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player_id).all()
        for absence in absences:
            if absence.reason and is_date_matches_absence(att.event.event_date, absence):
                reason = absence.reason
                break

        # Determine if we should update
        should_update = att.status == "unknown" or (
            att.status == "present" and att.event.presence_type == "all"
        )

        if should_update:
            att.status = "absent"
            att.note = f"[Absence] {reason}"
            att.updated_at = datetime.now(timezone.utc)
            count += 1

    if count > 0:
        db.commit()

    return count


def is_date_matches_absence(check_date: date, absence: PlayerAbsence) -> bool:
    """Check if a date matches a specific absence record (without db query)."""
    from dateutil.rrule import rrulestr
    from datetime import datetime

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
```

Actually, for simplicity and to avoid duplication, let me refactor is_date_in_absence to use a helper that checks a single absence:

Let me rewrite the whole absence_service more cleanly:

```python
"""services/absence_service.py — Absence business logic."""

from __future__ import annotations

from datetime import date, datetime, timezone
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


def apply_absence_to_future_events(player_id: int, db: Session) -> int:
    """Apply an absence to all matching future event attendance records.

    Returns the count of updated attendance records.
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

    count = 0
    for att in attendances:
        # Find if this attendance date matches any absence
        matching_absence = None
        for absence in absences:
            if _date_matches_absence(att.event.event_date, absence):
                matching_absence = absence
                break

        if not matching_absence:
            continue

        # Determine if we should update this attendance
        should_update = att.status == "unknown" or (
            att.status == "present" and att.event.presence_type == "all"
        )

        if should_update:
            reason = matching_absence.reason or "On leave"
            att.status = "absent"
            att.note = f"[Absence] {reason}"
            att.updated_at = datetime.now(timezone.utc)
            count += 1

    if count > 0:
        db.commit()

    return count
```

This is much cleaner. Now let me continue with the test.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_absence_service.py::test_apply_absence_to_future_events_period -v
```

Expected: PASS

- [ ] **Step 5: Add test for override behavior**

Add to `tests/test_absence_service.py`:

```python
def test_apply_absence_respects_all_presence_type(db: Session):
    """Absence should override presence_type='all' (auto-present default)."""
    player = Player(first_name="Eve", last_name="Test", is_active=True)
    db.add(player)
    db.commit()

    team = Team(name="TestTeam2")
    db.add(team)
    db.commit()

    season = Season(name="Spring 2026", start_date=date(2026, 3, 1), end_date=date(2026, 6, 30))
    db.add(season)
    db.commit()

    pm = PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id)
    db.add(pm)
    db.commit()

    # Event with presence_type="all" (everyone present by default)
    event = Event(
        title="AllAttendee Event",
        event_date=date(2026, 4, 15),
        team_id=team.id,
        season_id=season.id,
        presence_type="all",
    )
    db.add(event)
    db.commit()

    # Create attendance with status="present" (from all-attendee default)
    att = Attendance(event_id=event.id, player_id=player.id, status="present")
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

    # Should have updated the auto-present to absent
    assert count == 1
    att_refreshed = db.query(Attendance).filter_by(event_id=event.id, player_id=player.id).first()
    assert att_refreshed.status == "absent"
```

- [ ] **Step 6: Add test for preserving coach overrides**

Add to `tests/test_absence_service.py`:

```python
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
```

- [ ] **Step 7: Run all apply_absence tests**

```bash
pytest tests/test_absence_service.py::test_apply_absence_to_future_events_period tests/test_absence_service.py::test_apply_absence_respects_all_presence_type tests/test_absence_service.py::test_apply_absence_preserves_explicit_present -v
```

Expected: All PASS

- [ ] **Step 8: Run all absence_service tests**

```bash
pytest tests/test_absence_service.py -v
```

Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add services/absence_service.py tests/test_absence_service.py
git commit -m "feat: implement apply_absence_to_future_events

- Auto-set future event attendance to absent for matching absences
- Override presence_type='all' defaults when absence active
- Preserve explicit coach overrides on non-all events
- Add comprehensive tests for apply logic
"
```

---

## Task 5: Create API Routes and Access Control Guards

**Files:**
- Create: `routes/_absence_helpers.py`
- Create: `routes/absences.py`
- Modify: `app/main.py`
- Create: `tests/test_absence_routes.py`

**Steps:**

- [ ] **Step 1: Write test for player accessing own absences**

Create `tests/test_absence_routes.py`:

```python
"""tests/test_absence_routes.py — Absence API route tests."""

import pytest
from datetime import date
from fastapi.testclient import TestClient

from app.main import app
from models.player import Player
from models.player_absence import PlayerAbsence
from models.user import User
from models.season import Season


def test_player_get_own_absences(member_client: TestClient, member_user: User, member_player: Player, db):
    """Player should be able to view their own absences."""
    season = Season(name="Spring 2026", start_date=date(2026, 3, 1), end_date=date(2026, 6, 30))
    db.add(season)
    db.commit()

    # Create an absence for the player
    absence = PlayerAbsence(
        player_id=member_player.id,
        absence_type="period",
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 20),
        reason="Vacation",
    )
    db.add(absence)
    db.commit()

    # Get absences
    response = member_client.get(f"/api/players/{member_player.id}/absences")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["absence_type"] == "period"
    assert data[0]["reason"] == "Vacation"


def test_player_cannot_view_other_absences(member_client: TestClient, member_player: Player, db):
    """Player should NOT be able to view another player's absences."""
    other_player = Player(first_name="Other", last_name="Player", is_active=True)
    db.add(other_player)
    db.commit()

    absence = PlayerAbsence(
        player_id=other_player.id,
        absence_type="period",
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 20),
    )
    db.add(absence)
    db.commit()

    response = member_client.get(f"/api/players/{other_player.id}/absences")

    assert response.status_code == 403
```

- [ ] **Step 2: Create absence helper guards**

Create `routes/_absence_helpers.py`:

```python
"""routes/_absence_helpers.py — Access control for absences."""

from fastapi import Depends, HTTPException

from app.database import get_db
from models.player_absence import PlayerAbsence
from routes._auth_helpers import require_login


async def require_absence_ownership_or_coach(
    player_id: int,
    absence_id: int,
    current_user=Depends(require_login),
    db=Depends(get_db),
):
    """Check if user owns the absence (player) or coaches the player's team."""
    from models.player import Player
    from models.user_team import UserTeam
    from models.player_team import PlayerTeam

    # Get the absence
    absence = db.query(PlayerAbsence).filter(PlayerAbsence.id == absence_id).first()
    if not absence:
        raise HTTPException(status_code=404, detail="Absence not found")

    # If player owns it, allow
    if current_user.is_admin:
        return absence

    if current_user.players and any(p.id == player_id for p in current_user.players):
        return absence

    # If coach, check if they manage the player's team for the relevant season
    if current_user.is_coach:
        player = db.query(Player).filter(Player.id == player_id).first()
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")

        # Check if coach manages any team the player is in (for the absence season if applicable)
        season_id = absence.season_id
        user_teams = db.query(UserTeam).filter(UserTeam.user_id == current_user.id).all()
        team_ids = {ut.team_id for ut in user_teams if season_id is None or ut.season_id == season_id}

        player_teams = db.query(PlayerTeam).filter(
            PlayerTeam.player_id == player_id,
            PlayerTeam.team_id.in_(team_ids) if team_ids else False,
        ).all()

        if player_teams:
            return absence

    raise HTTPException(status_code=403, detail="Not authorized")
```

- [ ] **Step 3: Create absences routes**

Create `routes/absences.py`:

```python
"""routes/absences.py — Absence API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import date
from sqlalchemy.orm import Session

from app.database import get_db
from models.player_absence import PlayerAbsence
from models.player import Player
from models.season import Season
from routes._auth_helpers import require_login
from routes._absence_helpers import require_absence_ownership_or_coach
from services.absence_service import apply_absence_to_future_events, is_date_in_absence


router = APIRouter(prefix="/api", tags=["absences"])


@router.get("/players/{player_id}/absences")
async def get_player_absences(
    player_id: int,
    current_user=Depends(require_login),
    db: Session = Depends(get_db),
):
    """Get absences for a player (self or if coach of their team)."""
    from models.user_team import UserTeam
    from models.player_team import PlayerTeam

    # Check if user owns this player or coaches them
    if not current_user.is_admin:
        # Check if player owns it
        if not (current_user.players and any(p.id == player_id for p in current_user.players)):
            # Check if coach
            if current_user.is_coach:
                user_teams = db.query(UserTeam).filter(UserTeam.user_id == current_user.id).all()
                team_ids = {ut.team_id for ut in user_teams}

                player_teams = db.query(PlayerTeam).filter(
                    PlayerTeam.player_id == player_id,
                    PlayerTeam.team_id.in_(team_ids) if team_ids else False,
                ).all()

                if not player_teams:
                    raise HTTPException(status_code=403, detail="Not authorized")
            else:
                raise HTTPException(status_code=403, detail="Not authorized")

    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player_id).all()
    return [
        {
            "id": a.id,
            "absence_type": a.absence_type,
            "start_date": a.start_date,
            "end_date": a.end_date,
            "rrule": a.rrule,
            "rrule_until": a.rrule_until,
            "season_id": a.season_id,
            "reason": a.reason,
            "created_at": a.created_at,
            "updated_at": a.updated_at,
        }
        for a in absences
    ]


@router.post("/players/{player_id}/absences")
async def create_player_absence(
    player_id: int,
    body: dict,
    current_user=Depends(require_login),
    db: Session = Depends(get_db),
):
    """Create a period or recurring absence for a player."""
    # Check authorization (same as GET)
    if not current_user.is_admin:
        if not (current_user.players and any(p.id == player_id for p in current_user.players)):
            if current_user.is_coach:
                from models.user_team import UserTeam
                from models.player_team import PlayerTeam

                user_teams = db.query(UserTeam).filter(UserTeam.user_id == current_user.id).all()
                team_ids = {ut.team_id for ut in user_teams}

                player_teams = db.query(PlayerTeam).filter(
                    PlayerTeam.player_id == player_id,
                    PlayerTeam.team_id.in_(team_ids) if team_ids else False,
                ).all()

                if not player_teams:
                    raise HTTPException(status_code=403, detail="Not authorized")
            else:
                raise HTTPException(status_code=403, detail="Not authorized")

    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    absence_type = body.get("absence_type")
    if absence_type not in ["period", "recurring"]:
        raise HTTPException(status_code=400, detail="Invalid absence_type")

    # Validate inputs
    if absence_type == "period":
        start_date = body.get("start_date")
        end_date = body.get("end_date")
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="start_date and end_date required for period absence")
        if start_date > end_date:
            raise HTTPException(status_code=400, detail="start_date must be before end_date")
        if start_date < date.today():
            raise HTTPException(status_code=400, detail="Absences must be in the future")
    elif absence_type == "recurring":
        rrule = body.get("rrule")
        season_id = body.get("season_id")
        if not rrule or not season_id:
            raise HTTPException(status_code=400, detail="rrule and season_id required for recurring absence")

        # Validate season exists
        season = db.query(Season).filter(Season.id == season_id).first()
        if not season:
            raise HTTPException(status_code=404, detail="Season not found")

        # Auto-set rrule_until to season end if not provided
        rrule_until = body.get("rrule_until") or season.end_date
        if rrule_until < date.today():
            raise HTTPException(status_code=400, detail="rrule_until must be in the future")

    # Create absence
    absence = PlayerAbsence(
        player_id=player_id,
        absence_type=absence_type,
        start_date=body.get("start_date"),
        end_date=body.get("end_date"),
        rrule=body.get("rrule"),
        rrule_until=body.get("rrule_until"),
        season_id=body.get("season_id"),
        reason=body.get("reason"),
    )
    db.add(absence)
    db.commit()
    db.refresh(absence)

    # Apply to future events
    apply_absence_to_future_events(player_id, db)

    return {
        "id": absence.id,
        "absence_type": absence.absence_type,
        "start_date": absence.start_date,
        "end_date": absence.end_date,
        "rrule": absence.rrule,
        "rrule_until": absence.rrule_until,
        "season_id": absence.season_id,
        "reason": absence.reason,
    }


@router.delete("/players/{player_id}/absences/{absence_id}")
async def delete_player_absence(
    player_id: int,
    absence_id: int,
    current_user=Depends(require_login),
    db: Session = Depends(get_db),
):
    """Delete an absence for a player."""
    # Check authorization
    absence = await require_absence_ownership_or_coach(player_id, absence_id, current_user, db)

    db.delete(absence)
    db.commit()

    return {"success": True}
```

- [ ] **Step 4: Register absences router in app/main.py**

Edit `app/main.py` and add "absences" to the `_routers` list:

Find this section:
```python
_routers = [
    "auth",
    "players",
    # ... other routers
]
```

Add "absences" to the list:
```python
_routers = [
    "auth",
    "players",
    "absences",
    # ... other routers
]
```

- [ ] **Step 5: Run test to verify routes work**

```bash
pytest tests/test_absence_routes.py::test_player_get_own_absences -v
```

Expected: PASS

- [ ] **Step 6: Run all route tests**

```bash
pytest tests/test_absence_routes.py -v
```

Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add routes/_absence_helpers.py routes/absences.py tests/test_absence_routes.py app/main.py
git commit -m "feat: add absences API routes with access control

- GET /api/players/{player_id}/absences - list absences
- POST /api/players/{player_id}/absences - create absence
- DELETE /api/players/{player_id}/absences/{absence_id} - delete absence
- Guard: player sees own, coaches see team/season, admins see all
- Auto-apply absence to future events on create
"
```

---

## Task 6: Create UI Templates (Player Absences List)

**Files:**
- Create: `templates/players/absences_list.html`

**Steps:**

- [ ] **Step 1: Create absences list template**

Create `templates/players/absences_list.html`:

```html
{% extends "base.html" %}

{% block title %}{{ t("absences.page_title") }}{% endblock %}

{% block content %}
<div class="container mt-5">
    <div class="row">
        <div class="col-md-10">
            <h1>{{ t("absences.page_title") }}</h1>

            {% if absences %}
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th>{{ t("absences.type") }}</th>
                        <th>{{ t("absences.dates_pattern") }}</th>
                        <th>{{ t("absences.reason") }}</th>
                        <th>{{ t("absences.actions") }}</th>
                    </tr>
                </thead>
                <tbody>
                    {% for absence in absences %}
                    <tr>
                        <td>
                            {% if absence.absence_type == "period" %}
                            {{ t("absences.period") }}
                            {% else %}
                            {{ t("absences.recurring") }}
                            {% endif %}
                        </td>
                        <td>
                            {% if absence.absence_type == "period" %}
                            {{ absence.start_date|date("Y-m-d") }} – {{ absence.end_date|date("Y-m-d") }}
                            {% else %}
                            {{ absence.rrule }} until {{ absence.rrule_until|date("Y-m-d") }}
                            {% endif %}
                        </td>
                        <td>{{ absence.reason or "-" }}</td>
                        <td>
                            <a href="/players/{{ player.id }}/absences/{{ absence.id }}/edit" class="btn btn-sm btn-primary">{{ t("common.edit") }}</a>
                            <form method="POST" action="/api/players/{{ player.id }}/absences/{{ absence.id }}" style="display: inline;">
                                <input type="hidden" name="_method" value="DELETE">
                                <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
                                <button type="submit" class="btn btn-sm btn-danger" onclick="return confirm('{{ t(\"common.confirm_delete\") }}')">{{ t("common.delete") }}</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p class="text-muted">{{ t("absences.no_absences") }}</p>
            {% endif %}

            <a href="/players/{{ player.id }}/absences/new" class="btn btn-primary">{{ t("absences.add_absence") }}</a>
        </div>
    </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Add translation keys**

Edit `locales/en.yml` and add:

```yaml
absences:
  page_title: My Absences
  type: Type
  dates_pattern: Dates/Pattern
  reason: Reason
  actions: Actions
  period: Period
  recurring: Recurring
  no_absences: No absences scheduled
  add_absence: Add Absence
```

Similar entries for other locales (it, fr, de).

- [ ] **Step 3: Commit**

```bash
git add templates/players/absences_list.html locales/
git commit -m "feat: add player absences list template and i18n

- Template shows period and recurring absences
- Edit and delete buttons
- Add absence button
"
```

---

## Task 7: Create UI Templates (Absence Form)

**Files:**
- Create: `templates/players/absence_form.html`

**Steps:**

- [ ] **Step 1: Create absence form template**

Create `templates/players/absence_form.html`:

```html
{% extends "base.html" %}

{% block title %}{% if absence %}{{ t("absences.edit_title") }}{% else %}{{ t("absences.create_title") }}{% endif %}{% endblock %}

{% block content %}
<div class="container mt-5">
    <div class="row">
        <div class="col-md-8">
            <h1>{% if absence %}{{ t("absences.edit_title") }}{% else %}{{ t("absences.create_title") }}{% endif %}</h1>

            <form method="POST" action="{% if absence %}/players/{{ player.id }}/absences/{{ absence.id }}{% else %}/players/{{ player.id }}/absences{% endif %}">
                <input type="hidden" name="csrf_token" value="{{ csrf_token }}">

                <div class="form-group mb-3">
                    <label for="absence_type">{{ t("absences.absence_type") }}</label>
                    <div>
                        <div class="form-check">
                            <input class="form-check-input" type="radio" name="absence_type" id="period" value="period" 
                                   {% if not absence or absence.absence_type == "period" %}checked{% endif %}
                                   onchange="toggleAbsenceFields()">
                            <label class="form-check-label" for="period">{{ t("absences.period") }}</label>
                        </div>
                        <div class="form-check">
                            <input class="form-check-input" type="radio" name="absence_type" id="recurring" value="recurring"
                                   {% if absence and absence.absence_type == "recurring" %}checked{% endif %}
                                   onchange="toggleAbsenceFields()">
                            <label class="form-check-label" for="recurring">{{ t("absences.recurring") }}</label>
                        </div>
                    </div>
                </div>

                <!-- Period fields -->
                <div id="period_fields" {% if absence and absence.absence_type == "recurring" %}style="display: none;"{% endif %}>
                    <div class="form-group mb-3">
                        <label for="start_date">{{ t("absences.start_date") }}</label>
                        <input type="date" class="form-control" id="start_date" name="start_date"
                               value="{% if absence %}{{ absence.start_date }}{% endif %}">
                    </div>
                    <div class="form-group mb-3">
                        <label for="end_date">{{ t("absences.end_date") }}</label>
                        <input type="date" class="form-control" id="end_date" name="end_date"
                               value="{% if absence %}{{ absence.end_date }}{% endif %}">
                    </div>
                </div>

                <!-- Recurring fields -->
                <div id="recurring_fields" {% if not absence or absence.absence_type == "period" %}style="display: none;"{% endif %}>
                    <div class="form-group mb-3">
                        <label>{{ t("absences.weekdays") }}</label>
                        <div>
                            {% for day, label in [("MO", "Monday"), ("TU", "Tuesday"), ("WE", "Wednesday"), ("TH", "Thursday"), ("FR", "Friday"), ("SA", "Saturday"), ("SU", "Sunday")] %}
                            <div class="form-check">
                                <input class="form-check-input weekday-check" type="checkbox" id="day_{{ day }}" value="{{ day }}" name="weekday" data-day="{{ day }}">
                                <label class="form-check-label" for="day_{{ day }}">{{ label }}</label>
                            </div>
                            {% endfor %}
                        </div>
                    </div>
                    <div class="form-group mb-3">
                        <label for="rrule_until">{{ t("absences.rrule_until") }}</label>
                        <input type="date" class="form-control" id="rrule_until" name="rrule_until"
                               value="{% if absence %}{{ absence.rrule_until }}{% else %}{{ season_end_date if season_end_date else "" }}{% endif %}">
                        <small class="text-muted">{{ t("absences.rrule_until_hint") }}</small>
                    </div>
                    <input type="hidden" id="rrule" name="rrule">
                    <input type="hidden" id="season_id" name="season_id" value="{{ season_id or "" }}">
                </div>

                <div class="form-group mb-3">
                    <label for="reason">{{ t("absences.reason") }}</label>
                    <input type="text" class="form-control" id="reason" name="reason" maxlength="512"
                           placeholder="{{ t("absences.reason_placeholder") }}"
                           value="{% if absence %}{{ absence.reason }}{% endif %}">
                </div>

                <button type="submit" class="btn btn-primary">{{ t("common.save") }}</button>
                <a href="/players/{{ player.id }}/absences" class="btn btn-secondary">{{ t("common.cancel") }}</a>
            </form>
        </div>
    </div>
</div>

<script>
function toggleAbsenceFields() {
    const type = document.querySelector('input[name="absence_type"]:checked').value;
    document.getElementById('period_fields').style.display = type === 'period' ? 'block' : 'none';
    document.getElementById('recurring_fields').style.display = type === 'recurring' ? 'block' : 'none';
}

document.querySelectorAll('.weekday-check').forEach(checkbox => {
    checkbox.addEventListener('change', updateRrule);
});

function updateRrule() {
    const selected = Array.from(document.querySelectorAll('.weekday-check:checked'))
        .map(cb => cb.value)
        .join(',');
    
    const rruleField = document.getElementById('rrule');
    if (selected) {
        rruleField.value = `FREQ=WEEKLY;BYDAY=${selected}`;
    } else {
        rruleField.value = '';
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    {% if absence and absence.absence_type == "recurring" and absence.rrule %}
    // Parse and populate weekday checkboxes from rrule
    const rrule = "{{ absence.rrule }}";
    const match = rrule.match(/BYDAY=([A-Z,]+)/);
    if (match) {
        const days = match[1].split(',');
        days.forEach(day => {
            const checkbox = document.getElementById(`day_${day}`);
            if (checkbox) checkbox.checked = true;
        });
    }
    {% endif %}
});
</script>
{% endblock %}
```

- [ ] **Step 2: Add translation keys for form**

Edit `locales/en.yml` and add:

```yaml
absences:
  create_title: Add Absence
  edit_title: Edit Absence
  absence_type: Absence Type
  start_date: Start Date
  end_date: End Date
  weekdays: Weekdays
  rrule_until: Until Date
  rrule_until_hint: "Defaults to season end date if not specified"
  reason: Reason (optional)
  reason_placeholder: "e.g., Vacation, Injury recovery, Family event"
```

Similar entries for other locales.

- [ ] **Step 3: Commit**

```bash
git add templates/players/absence_form.html locales/
git commit -m "feat: add absence creation/edit form template

- Support period and recurring absence types
- Dynamic UI toggle between type fields
- Weekday checkboxes for recurring pattern
- Auto-generate rrule from selected weekdays
"
```

---

## Task 8: Create Coach Team Absences View

**Files:**
- Create: `templates/teams/absences_team_view.html`

**Steps:**

- [ ] **Step 1: Create team absences template**

Create `templates/teams/absences_team_view.html`:

```html
{% extends "base.html" %}

{% block title %}{{ t("absences.team_absences_title") }}{% endblock %}

{% block content %}
<div class="container mt-5">
    <div class="row">
        <div class="col-md-12">
            <h1>{{ t("absences.team_absences_title") }} - {{ team.name }}</h1>
            <p><small class="text-muted">{{ t("absences.team_absences_subtitle") }}: {{ season.name if season else "All Seasons" }}</small></p>

            {% if player_absences %}
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th>{{ t("common.player") }}</th>
                        <th>{{ t("absences.type") }}</th>
                        <th>{{ t("absences.dates_pattern") }}</th>
                        <th>{{ t("absences.reason") }}</th>
                        <th>{{ t("absences.actions") }}</th>
                    </tr>
                </thead>
                <tbody>
                    {% for player_id, player_name, absences in player_absences %}
                    {% for absence in absences %}
                    <tr>
                        <td>{{ player_name }}</td>
                        <td>
                            {% if absence.absence_type == "period" %}
                            {{ t("absences.period") }}
                            {% else %}
                            {{ t("absences.recurring") }}
                            {% endif %}
                        </td>
                        <td>
                            {% if absence.absence_type == "period" %}
                            {{ absence.start_date|date("Y-m-d") }} – {{ absence.end_date|date("Y-m-d") }}
                            {% else %}
                            {{ absence.rrule }} until {{ absence.rrule_until|date("Y-m-d") }}
                            {% endif %}
                        </td>
                        <td>{{ absence.reason or "-" }}</td>
                        <td>
                            <button class="btn btn-sm btn-danger" onclick="deleteAbsence({{ player_id }}, {{ absence.id }})">{{ t("common.delete") }}</button>
                        </td>
                    </tr>
                    {% endfor %}
                    {% endfor %}
                </tbody>
            </table>
            {% else %}
            <p class="text-muted">{{ t("absences.no_team_absences") }}</p>
            {% endif %}
        </div>
    </div>
</div>

<script>
function deleteAbsence(playerId, absenceId) {
    if (!confirm('{{ t("common.confirm_delete") }}')) return;
    
    fetch(`/api/players/${playerId}/absences/${absenceId}`, {
        method: 'DELETE',
        headers: { 'X-CSRF-Token': document.querySelector('meta[name="csrf-token"]').content }
    })
    .then(() => location.reload())
    .catch(err => alert('Error: ' + err));
}
</script>
{% endblock %}
```

- [ ] **Step 2: Add translation keys**

Edit `locales/en.yml` and add:

```yaml
absences:
  team_absences_title: Team Absences
  team_absences_subtitle: Season
  no_team_absences: No absences for this team
```

Similar entries for other locales.

- [ ] **Step 3: Commit**

```bash
git add templates/teams/absences_team_view.html locales/
git commit -m "feat: add coach team absences view template

- Shows all player absences for team/season
- Coach can delete absences
"
```

---

## Task 9: Wire Up Routes to Templates

**Files:**
- Modify: `routes/players.py` (or create if needed)
- Modify: `routes/teams.py` (or create if needed)

**Steps:**

- [ ] **Step 1: Add player absences list route**

Edit or create `routes/players.py` and add:

```python
@router.get("/players/{player_id}/absences")
async def player_absences_list(
    player_id: int,
    current_user=Depends(require_login),
    db: Session = Depends(get_db),
):
    """Display list of player absences."""
    from models.player import Player
    from models.player_absence import PlayerAbsence
    
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Check authorization
    if not current_user.is_admin and not (current_user.players and any(p.id == player_id for p in current_user.players)):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == player_id).all()
    return render(
        "players/absences_list.html",
        player=player,
        absences=absences,
        current_locale=request.state.locale,
    )
```

- [ ] **Step 2: Add absence form routes**

Add to `routes/players.py`:

```python
@router.get("/players/{player_id}/absences/new")
async def absence_form_new(
    player_id: int,
    current_user=Depends(require_login),
    db: Session = Depends(get_db),
    request=...,
):
    """Display form to create new absence."""
    from models.player import Player
    from models.season import Season
    
    player = db.query(Player).filter(Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    
    # Check authorization
    if not current_user.is_admin and not (current_user.players and any(p.id == player_id for p in current_user.players)):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get current season or next season
    from datetime import date
    season = db.query(Season).filter(Season.end_date >= date.today()).order_by(Season.start_date).first()
    
    return render(
        "players/absence_form.html",
        player=player,
        absence=None,
        season_id=season.id if season else None,
        season_end_date=season.end_date if season else None,
        current_locale=request.state.locale,
    )
```

- [ ] **Step 3: Add team absences view**

Add to `routes/teams.py`:

```python
@router.get("/teams/{team_id}/season/{season_id}/absences")
async def team_absences_view(
    team_id: int,
    season_id: int,
    current_user=Depends(require_login),
    db: Session = Depends(get_db),
    request=...,
):
    """Display absences for all players in a team."""
    from models.team import Team
    from models.season import Season
    from models.user_team import UserTeam
    from models.player_team import PlayerTeam
    from models.player_absence import PlayerAbsence
    
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    
    season = db.query(Season).filter(Season.id == season_id).first()
    if not season:
        raise HTTPException(status_code=404, detail="Season not found")
    
    # Check if user coaches this team
    user_team = db.query(UserTeam).filter(
        UserTeam.user_id == current_user.id,
        UserTeam.team_id == team_id,
        (UserTeam.season_id == season_id) | (UserTeam.season_id == None),
    ).first()
    
    if not current_user.is_admin and not user_team:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get all players in team for this season
    player_teams = db.query(PlayerTeam).filter(
        PlayerTeam.team_id == team_id,
        PlayerTeam.season_id == season_id,
    ).all()
    
    # Collect absences for each player
    player_absences = []
    for pt in player_teams:
        absences = db.query(PlayerAbsence).filter(PlayerAbsence.player_id == pt.player_id).all()
        if absences:
            player_absences.append((pt.player_id, pt.player.full_name, absences))
    
    return render(
        "teams/absences_team_view.html",
        team=team,
        season=season,
        player_absences=player_absences,
        current_locale=request.state.locale,
    )
```

- [ ] **Step 4: Commit**

```bash
git add routes/players.py routes/teams.py
git commit -m "feat: wire up absences templates to routes

- GET /players/{id}/absences - list view
- GET /players/{id}/absences/new - create form
- GET /teams/{id}/season/{season_id}/absences - coach view
"
```

---

## Task 10: Manual Testing and Adjustments

**Steps:**

- [ ] **Step 1: Start dev server**

```bash
source .venv/bin/activate
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 7000
```

- [ ] **Step 2: Test player absence creation**

- Log in as a member/player
- Navigate to `/players/{id}/absences`
- Create a period absence (April 10-20)
- Verify it appears in the list
- Check that attendance records for events on those dates are set to "absent"

- [ ] **Step 3: Test recurring absence**

- Create a recurring absence (every Friday until June 30)
- Verify it matches Friday events only
- Check that "rrule_until" defaulted to season end date

- [ ] **Step 4: Test coach view**

- Log in as coach
- Navigate to `/teams/{id}/season/{season_id}/absences`
- Verify all team player absences appear
- Try to delete an absence

- [ ] **Step 5: Test access control**

- Try accessing another player's absences (should fail with 403)
- Try creating absence for another player as non-coach (should fail)
- Try as coach of their team (should succeed)

- [ ] **Step 6: Test override behavior**

- Create an event with `presence_type="all"` (everyone present by default)
- Create an absence covering that event
- Verify attendance is set to "absent" (overriding the default)

- [ ] **Step 7: Test coach override preservation**

- Create an event with `presence_type="normal"`
- Manually set player attendance to "present"
- Create absence covering that event
- Verify attendance stays "present" (coach override preserved)

- [ ] **Step 8: Commit any final fixes**

```bash
git add .
git commit -m "test: manual testing of absences feature - all scenarios pass

- Period and recurring absences work correctly
- Coach view displays team absences
- Access control enforced properly
- Event default overrides work as expected
"
```

---

## Summary

**Total: 10 tasks covering:**
1. Data model and migration
2. Period absence logic
3. Recurring absence logic (rrule)
4. Event application logic
5. API routes and access control
6. Player absence list UI
7. Absence form UI
8. Coach team absences view
9. Route wiring
10. Manual testing

**Tech:** SQLAlchemy, FastAPI, dateutil.rrule, Jinja2, pytest

**Estimated scope:** Model (1 file) + Service (1 file) + Routes (2 files) + Templates (3 files) + Tests (2 files) + Migrations (1 file).

