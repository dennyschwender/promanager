# Roles & Permissions Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `coach` role with team-scoped management rights, and a public `/schedule` page for unauthenticated visitors.

**Architecture:** New `UserTeam` model links coach users to their managed teams. Three new auth helpers (`get_coach_teams`, `require_coach_or_admin`, `check_team_access`) gate access. Events, players, attendance, and reports routes are updated to allow coaches to act within their teams. A new unauthenticated `/schedule` route shows upcoming events publicly.

**Tech Stack:** FastAPI, SQLAlchemy 2.x mapped columns, Jinja2, Alembic, pytest, itsdangerous session cookies.

---

## Codebase Context

- **Auth guards** live in `routes/_auth_helpers.py`: `require_login` and `require_admin`. Both are FastAPI `Depends()` parameters.
- **User model**: `models/user.py`. Has `role: str` (values `"admin"` or `"member"`), `is_admin` property.
- **Routes** are registered in `app/main.py` via `_routers` list using `importlib`.
- **Templates** use `render()` from `app/templates.py` which injects `t()`, `current_locale`, `current_theme`.
- **i18n** files are `locales/en.json`, `it.json`, `fr.json`, `de.json`.
- **Tests** use in-memory SQLite (`StaticPool`), CSRF disabled on default `client` fixture in `conftest.py`. The DB fixture is named `db` (not `db`). Use `create_session_cookie(user.id)` from `services.auth_service` and `client.cookies.set("session_user_id", cookie_val)` to authenticate a test client (same pattern as `admin_client` fixture).
- **Alembic migrations** are in `alembic/versions/`. Use `op.batch_alter_table()` for SQLite compatibility. The latest migration file is `b2c3d4e5f6a7_add_season_id_to_recurring_schedules.py`.
- **Table names** (pluralised): `users`, `teams`, `seasons`, `players`, `events`, `player_teams`. Always use these in `ForeignKey()` calls.
- **Event date field**: `Event.event_date` (not `Event.date`). Construct events with `event_date=date(...)`.
- **BulkUpdateRequest** body uses key `"players"` (list of `PlayerDiff`) not `"updates"`. `PlayerDiff` has `id: int` and extra fields via `model_config = {"extra": "allow"}`.
- **`_PT_FIELDS`** in `routes/players.py` is exactly `frozenset({"shirt_number", "position", "injured_until", "absent_by_default", "priority"})`. Use this exact set for coach-only field filtering — do not add `"role"` or `"membership_status"`.

---

## File Map

**Create:**
- `models/user_team.py` — UserTeam ORM model
- `routes/schedule.py` — public schedule route
- `templates/schedule/index.html` — public schedule template
- `tests/test_roles.py` — all role permission tests
- `alembic/versions/<new_hash>_add_user_team.py` — migration

**Modify:**
- `models/user.py` — add `is_coach` property + `managed_teams` relationship
- `models/team.py` — add `coaches` relationship
- `models/__init__.py` — import UserTeam
- `routes/_auth_helpers.py` — add `get_coach_teams`, `require_coach_or_admin`, `check_team_access`
- `routes/events.py` — relax guards, add team filtering for coaches
- `routes/players.py` — relax bulk-assign/remove/update guards
- `routes/attendance.py` — coach gets full-team view
- `routes/reports.py` — filter for coaches, update redirect
- `routes/teams.py` — add coach assignment routes
- `app/main.py` — register schedule router
- `templates/base.html` — Schedule nav link, Reports visible to coaches
- `templates/auth/register.html` — add coach role option
- `templates/events/form.html` — restrict team dropdown for coaches
- `templates/events/detail.html` — show action buttons to coaches
- `templates/events/list.html` — show edit button to coaches
- `templates/attendance/mark.html` — coach gets full admin view
- `templates/players/list.html` — expose edit mode to coaches
- `templates/teams/detail.html` — add Coaches section
- `templates/reports/season.html` — filter stats for coaches
- `locales/en.json`, `it.json`, `fr.json`, `de.json` — new keys

---

## Task 1: UserTeam Model + Migration

**Files:**
- Create: `models/user_team.py`
- Modify: `models/user.py`
- Modify: `models/team.py`
- Modify: `models/__init__.py`
- Create: `alembic/versions/<hash>_add_user_team.py`

- [ ] **Step 1: Write a failing test that imports UserTeam**

```python
# tests/test_roles.py
import pytest
from models.user_team import UserTeam

def test_user_team_importable():
    assert UserTeam.__tablename__ == "user_team"
```

Run: `pytest tests/test_roles.py::test_user_team_importable -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 2: Create `models/user_team.py`**

```python
"""models/user_team.py — Coach-to-team assignment."""

from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserTeam(Base):
    """Links a coach User to a Team they manage, optionally scoped to a Season."""

    __tablename__ = "user_team"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    season_id: Mapped[int | None] = mapped_column(ForeignKey("seasons.id"), nullable=True)

    user: Mapped["User"] = relationship(back_populates="managed_teams")  # type: ignore[name-defined]  # noqa: F821
    team: Mapped["Team"] = relationship(back_populates="coaches")  # type: ignore[name-defined]  # noqa: F821
    season: Mapped["Season | None"] = relationship()  # type: ignore[name-defined]  # noqa: F821
```

- [ ] **Step 3: Add `is_coach` property and `managed_teams` relationship to `models/user.py`**

Find the `is_admin` property and add after it:
```python
@property
def is_coach(self) -> bool:
    return self.role == "coach"
```

Find the `players` relationship and add a `managed_teams` relationship. It should look like:
```python
managed_teams: Mapped[list["UserTeam"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # noqa: F821
```

- [ ] **Step 4: Add `coaches` relationship to `models/team.py`**

Find the existing relationships and add:
```python
coaches: Mapped[list["UserTeam"]] = relationship(back_populates="team", cascade="all, delete-orphan")  # noqa: F821
```

- [ ] **Step 5: Import UserTeam in `models/__init__.py`**

Add to the existing imports:
```python
from models.user_team import UserTeam as UserTeam  # noqa: F401
```

- [ ] **Step 6: Run test to confirm import works**

Run: `pytest tests/test_roles.py::test_user_team_importable -v`
Expected: PASS

- [ ] **Step 7: Generate the Alembic migration**

```bash
source .venv/bin/activate
alembic revision --autogenerate -m "add_user_team"
```

Open the generated file in `alembic/versions/` and verify it contains a `create_table("user_team", ...)` call. If it is empty or wrong, write it manually:

```python
"""add_user_team

Revision ID: <generated>
Revises: b2c3d4e5f6a7
Create Date: 2026-03-17
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "<generated>"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_team",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("season_id", sa.Integer(), sa.ForeignKey("seasons.id"), nullable=True),
    )
    op.create_index("ix_user_team_user_id", "user_team", ["user_id"])
    op.create_index("ix_user_team_team_id", "user_team", ["team_id"])


def downgrade() -> None:
    op.drop_index("ix_user_team_team_id", "user_team")
    op.drop_index("ix_user_team_user_id", "user_team")
    op.drop_table("user_team")
```

- [ ] **Step 8: Apply the migration to confirm it runs cleanly**

```bash
alembic upgrade head
```
Expected: no errors

- [ ] **Step 9: Run full test suite to confirm nothing is broken**

```bash
pytest -v --tb=short
```
Expected: all existing tests pass

- [ ] **Step 10: Commit**

```bash
git add models/user_team.py models/user.py models/team.py models/__init__.py alembic/versions/ tests/test_roles.py
git commit -m "feat: add UserTeam model, is_coach property, and migration"
```

---

## Task 2: Auth Helpers

**Files:**
- Modify: `routes/_auth_helpers.py`
- Test: `tests/test_roles.py`

- [ ] **Step 1: Write failing tests for the new helpers**

Add to `tests/test_roles.py`. First read `tests/conftest.py` to understand the `client`, `admin_user`, `member_user` fixtures, then add:

```python
from sqlalchemy.orm import Session
from models.user import User
from models.user_team import UserTeam
from routes._auth_helpers import get_coach_teams, check_team_access, NotAuthorized


def _make_coach(db: Session) -> User:
    from services.auth_service import hash_password
    u = User(username="coach1", email="coach1@test.com",
             hashed_password=hash_password("Pass1234!"), role="coach")
    db.add(u)
    db.flush()
    return u


def test_get_coach_teams_returns_empty_for_unassigned(db):
    coach = _make_coach(db)
    result = get_coach_teams(coach, db)
    assert result == set()


def test_get_coach_teams_returns_assigned_team(db):
    from models.team import Team
    coach = _make_coach(db)
    team = Team(name="Test Team")
    db.add(team)
    db.flush()
    ut = UserTeam(user_id=coach.id, team_id=team.id, season_id=None)
    db.add(ut)
    db.flush()
    result = get_coach_teams(coach, db)
    assert team.id in result


def test_check_team_access_admin_always_passes(db, admin_user):
    # Should not raise for any team_id
    check_team_access(admin_user, 99999, db)


def test_check_team_access_coach_denied_unassigned(db):
    coach = _make_coach(db)
    with pytest.raises(NotAuthorized):
        check_team_access(coach, 99999, db)


def test_check_team_access_coach_passes_assigned(db):
    from models.team import Team
    coach = _make_coach(db)
    team = Team(name="Allowed Team")
    db.add(team)
    db.flush()
    ut = UserTeam(user_id=coach.id, team_id=team.id, season_id=None)
    db.add(ut)
    db.flush()
    check_team_access(coach, team.id, db)  # should not raise
```

Note: `conftest.py` already has a `db` fixture that uses the in-memory test database. No new fixture needed.

Run: `pytest tests/test_roles.py -v -k "auth_helpers or coach_teams or team_access" 2>&1 | head -30`
Expected: FAIL with ImportError on `get_coach_teams`

- [ ] **Step 2: Add helpers to `routes/_auth_helpers.py`**

Read the current file first. Then add at the bottom (after existing functions), importing what's needed:

```python
from sqlalchemy import or_
from sqlalchemy.orm import Session as _Session

from models.user_team import UserTeam as _UserTeam


def get_coach_teams(
    user: "User",
    db: "_Session",
    season_id: int | None = None,
) -> set[int]:
    """Return set of team_ids the coach manages (optionally scoped to a season).

    season_id=None → return all assigned teams regardless of season.
    season_id=X   → return teams assigned for season X OR with no season scope (NULL).
    Always returns empty set for non-coach users; callers should check is_admin first.
    """
    q = db.query(_UserTeam.team_id).filter(_UserTeam.user_id == user.id)
    if season_id:
        q = q.filter(
            or_(_UserTeam.season_id == season_id, _UserTeam.season_id.is_(None))
        )
    return {row[0] for row in q.all()}


def check_team_access(
    user: "User",
    team_id: int,
    db: "_Session",
    season_id: int | None = None,
) -> None:
    """Raise NotAuthorized if the user cannot manage the given team.

    Admins always pass. Coaches pass only if a matching UserTeam row exists.
    Pass season_id to enforce season-scoped assignments.
    """
    if user.is_admin:
        return
    if team_id not in get_coach_teams(user, db, season_id=season_id):
        raise NotAuthorized


def require_coach_or_admin(user: "User" = Depends(require_login)) -> "User":
    """FastAPI dependency: allows admins and coaches only."""
    if not (user.is_admin or user.is_coach):
        raise NotAuthorized
    return user
```

Note: `Depends` and `require_login` are already imported in the file. The `User` type hint uses a string because of circular imports.

- [ ] **Step 3: Run auth helper tests**

```bash
pytest tests/test_roles.py -v -k "coach_teams or team_access"
```
Expected: all 5 tests PASS

- [ ] **Step 4: Run full test suite**

```bash
pytest -v --tb=short
```
Expected: all existing tests still pass

- [ ] **Step 5: Commit**

```bash
git add routes/_auth_helpers.py tests/test_roles.py
git commit -m "feat: add get_coach_teams, check_team_access, require_coach_or_admin auth helpers"
```

---

## Task 3: i18n Keys

**Files:**
- Modify: `locales/en.json`, `locales/it.json`, `locales/fr.json`, `locales/de.json`

- [ ] **Step 1: Add keys to `locales/en.json`**

Read the file first to find the right sections. Add inside the `"nav"` object:
```json
"schedule": "Schedule"
```

Add inside the `"teams"` object:
```json
"coaches": "Coaches",
"add_coach": "Add coach",
"remove_coach": "Remove",
"no_coaches": "No coaches assigned"
```

Add inside the `"auth"` object:
```json
"role_coach": "Coach"
```

Add a new top-level `"schedule"` object (after `"reports"` or similar):
```json
"schedule": {
  "title": "Schedule",
  "no_events": "No upcoming events"
}
```

- [ ] **Step 2: Add keys to `locales/it.json`**

Same positions, Italian translations:
- `nav.schedule` → `"Calendario"`
- `teams.coaches` → `"Allenatori"`
- `teams.add_coach` → `"Aggiungi allenatore"`
- `teams.remove_coach` → `"Rimuovi"`
- `teams.no_coaches` → `"Nessun allenatore assegnato"`
- `auth.role_coach` → `"Allenatore"`
- `schedule.title` → `"Calendario"`
- `schedule.no_events` → `"Nessun evento in programma"`

- [ ] **Step 3: Add keys to `locales/fr.json`**

French translations:
- `nav.schedule` → `"Calendrier"`
- `teams.coaches` → `"Entraîneurs"`
- `teams.add_coach` → `"Ajouter un entraîneur"`
- `teams.remove_coach` → `"Retirer"`
- `teams.no_coaches` → `"Aucun entraîneur assigné"`
- `auth.role_coach` → `"Entraîneur"`
- `schedule.title` → `"Calendrier"`
- `schedule.no_events` → `"Aucun événement à venir"`

- [ ] **Step 4: Add keys to `locales/de.json`**

German translations:
- `nav.schedule` → `"Spielplan"`
- `teams.coaches` → `"Trainer"`
- `teams.add_coach` → `"Trainer hinzufügen"`
- `teams.remove_coach` → `"Entfernen"`
- `teams.no_coaches` → `"Kein Trainer zugewiesen"`
- `auth.role_coach` → `"Trainer"`
- `schedule.title` → `"Spielplan"`
- `schedule.no_events` → `"Keine bevorstehenden Ereignisse"`

- [ ] **Step 5: Run tests to confirm no missing key errors**

```bash
pytest -v --tb=short
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add locales/
git commit -m "feat: add i18n keys for coach role, schedule page, team coaches section"
```

---

## Task 4: Public Schedule Route + Template

**Files:**
- Create: `routes/schedule.py`
- Create: `templates/schedule/index.html`
- Modify: `app/main.py`
- Modify: `templates/base.html`
- Test: `tests/test_roles.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_roles.py`:

```python
def test_public_schedule_no_auth(client):
    """Public /schedule returns 200 without authentication."""
    resp = client.get("/schedule")
    assert resp.status_code == 200


def test_public_schedule_has_no_player_names(client, db):
    """Schedule page does not expose player names."""
    from models.player import Player
    p = Player(first_name="Secret", last_name="Player", is_active=True)
    db.add(p)
    db.commit()
    resp = client.get("/schedule")
    assert "Secret" not in resp.text
    assert "Player" not in resp.text  # surname also not shown
```

Run: `pytest tests/test_roles.py -v -k "schedule" 2>&1 | head -20`
Expected: FAIL with 404

- [ ] **Step 2: Create `routes/schedule.py`**

```python
"""routes/schedule.py — Public event schedule (no authentication required)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.templates import render
from models.event import Event
from models.season import Season
from models.team import Team

router = APIRouter()


@router.get("", include_in_schema=False)
@router.get("/", include_in_schema=False)
async def schedule_page(
    request: Request,
    season_id: int | None = None,
    team_id: int | None = None,
    db: Session = Depends(get_db),
):
    seasons = db.query(Season).order_by(Season.start_date.desc()).all()
    teams = db.query(Team).order_by(Team.name).all()

    # Default to active season if none selected
    if not season_id:
        active = db.query(Season).filter(Season.is_active.is_(True)).first()
        if active:
            season_id = active.id

    q = db.query(Event).filter(Event.event_date >= date.today())
    if season_id:
        q = q.filter(Event.season_id == season_id)
    if team_id:
        q = q.filter(Event.team_id == team_id)
    events = q.order_by(Event.event_date, Event.time).all()

    return render(
        request,
        "schedule/index.html",
        {
            "events": events,
            "seasons": seasons,
            "teams": teams,
            "selected_season_id": season_id,
            "selected_team_id": team_id,
        },
    )
```

- [ ] **Step 3: Create `templates/schedule/index.html`**

```html
{% extends "base.html" %}
{% block title %}{{ t('schedule.title') }} — ProManager{% endblock %}
{% block breadcrumb %}
<nav class="breadcrumb"><span>{{ t('schedule.title') }}</span></nav>
{% endblock %}
{% block content %}
<div class="page-header">
  <h2>{{ t('schedule.title') }}</h2>
</div>

<form method="get" action="/schedule"
      style="display:flex;gap:.5rem;flex-wrap:wrap;align-items:flex-end;margin-bottom:.75rem;">
  <label style="margin:0;">
    <span style="display:block;font-size:.78rem;color:var(--tp-muted,#6c757d);margin-bottom:.15rem;">Season</span>
    <select name="season_id" onchange="this.form.submit()" class="sel-inline">
      <option value="">All Seasons</option>
      {% for s in seasons %}
        <option value="{{ s.id }}" {% if s.id == selected_season_id %}selected{% endif %}>
          {{ s.name }}{% if s.is_active %} ✓{% endif %}
        </option>
      {% endfor %}
    </select>
  </label>
  <label style="margin:0;">
    <span style="display:block;font-size:.78rem;color:var(--tp-muted,#6c757d);margin-bottom:.15rem;">Team</span>
    <select name="team_id" onchange="this.form.submit()" class="sel-inline">
      <option value="">All Teams</option>
      {% for tm in teams %}
        <option value="{{ tm.id }}" {% if tm.id == selected_team_id %}selected{% endif %}>{{ tm.name }}</option>
      {% endfor %}
    </select>
  </label>
</form>

{% if events %}
<div class="table-responsive">
<table>
  <thead>
    <tr>
      <th>Date</th>
      <th>Time</th>
      <th>Type</th>
      <th>Team</th>
      <th>Location</th>
    </tr>
  </thead>
  <tbody>
  {% for ev in events %}
    <tr>
      <td>{{ ev.event_date }}</td>
      <td>{{ ev.time or '—' }}</td>
      <td><span class="badge badge-{{ ev.event_type }}">{{ ev.event_type | capitalize }}</span></td>
      <td>{{ ev.team.name if ev.team else '—' }}</td>
      <td>{{ ev.location or '—' }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% else %}
  <p>{{ t('schedule.no_events') }}</p>
{% endif %}
{% endblock %}
```

- [ ] **Step 4: Register the schedule router in `app/main.py`**

Read `app/main.py` and find the notifications router block (around line 148). Add the schedule router in a similar pattern, after the notifications block and before the locale switcher:

```python
    # ── Schedule (public) ─────────────────────────────────────────────────────
    try:
        from routes import schedule as _schedule_mod  # noqa: PLC0415

        app.include_router(_schedule_mod.router, prefix="/schedule", tags=["schedule"])
    except ModuleNotFoundError:
        logger.debug("Schedule router not found — skipping.")
```

- [ ] **Step 5: Add Schedule link to `templates/base.html`**

Read `base.html`. Find the `<nav>` section. The "Schedule" link should be visible to ALL visitors including unauthenticated. Add it to the always-visible brand `<ul>` at the top OR as a standalone `<ul>` between brand and `#nav-links`. The cleanest approach: add it inside `#nav-links` but also show it for unauthenticated users.

Find the nav structure and add the Schedule link so it appears for everyone. The simplest approach — add it to the nav-links list before the auth-gated links:

Inside `<ul id="nav-links">`, add as the first item (before dashboard):
```html
<li><a href="/schedule" class="{% if path.startswith('/schedule') %}nav-active{% endif %}">{{ t('nav.schedule') }}</a></li>
```

For unauthenticated users, the `#nav-links` is not shown. Add a separate `<ul>` for the public Schedule link, before the `{% if user %}` block:

After the brand `<ul>` and before `{% if user %}`:
```html
<ul>
  <li><a href="/schedule">{{ t('nav.schedule') }}</a></li>
</ul>
```

Actually — look at how the existing nav is structured and pick the cleanest approach that makes Schedule visible both when logged in and when not. The key constraint: for logged-in users it should appear in `#nav-links` so the hamburger menu includes it; for guests it should appear alongside the login button.

- [ ] **Step 6: Run schedule tests**

```bash
pytest tests/test_roles.py -v -k "schedule"
```
Expected: PASS

- [ ] **Step 7: Run full test suite**

```bash
pytest -v --tb=short
```
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add routes/schedule.py templates/schedule/ app/main.py templates/base.html
git commit -m "feat: add public /schedule page and nav link"
```

---

## Task 5: User Registration — Coach Role Option

**Files:**
- Modify: `templates/auth/register.html`

- [ ] **Step 1: Read `templates/auth/register.html`**

Find the `<select name="role">` element. It currently has two `<option>` elements: member and admin.

- [ ] **Step 2: Add coach option**

Add between member and admin:
```html
<option value="coach">{{ t('auth.role_coach') }}</option>
```

The final select should be:
```html
<select name="role" required>
  <option value="member" {% if form_data and form_data.role == 'member' %}selected{% endif %}>{{ t('auth.role_member') }}</option>
  <option value="coach" {% if form_data and form_data.role == 'coach' %}selected{% endif %}>{{ t('auth.role_coach') }}</option>
  <option value="admin" {% if form_data and form_data.role == 'admin' %}selected{% endif %}>{{ t('auth.role_admin') }}</option>
</select>
```

Check how the existing options are written and match that exact pattern. If `t('auth.role_member')` and `t('auth.role_admin')` keys don't exist, use plain text "Member" / "Coach" / "Admin" as the other options do.

- [ ] **Step 3: Also check `routes/auth.py` register handler**

Read `routes/auth.py`. Find the `register` POST handler. If it validates `role` against an allowlist, add `"coach"` to it. Look for something like:
```python
if role not in {"admin", "member"}:
```
Change to:
```python
if role not in {"admin", "coach", "member"}:
```

- [ ] **Step 4: Run existing auth tests**

```bash
pytest tests/test_auth.py -v --tb=short
```
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add templates/auth/register.html routes/auth.py
git commit -m "feat: add coach option to user registration form"
```

---

## Task 6: Team Coach Assignment UI

**Files:**
- Modify: `routes/teams.py`
- Modify: `templates/teams/detail.html`
- Test: `tests/test_roles.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_roles.py`:

```python
def test_admin_can_assign_coach(admin_client, db):
    from models.team import Team
    from models.user import User
    from services.auth_service import hash_password

    team = Team(name="Team Alpha")
    db.add(team)
    coach_user = User(username="coachy", email="coachy@test.com",
                      hashed_password=hash_password("Pass1234!"), role="coach")
    db.add(coach_user)
    db.commit()

    resp = admin_client.post(
        f"/teams/{team.id}/coaches",
        data={"user_id": coach_user.id, "season_id": "", "csrf_token": "test"},
    )
    assert resp.status_code in (200, 302)
    from models.user_team import UserTeam
    ut = db.query(UserTeam).filter_by(user_id=coach_user.id, team_id=team.id).first()
    assert ut is not None


def test_admin_can_remove_coach(admin_client, db):
    from models.team import Team
    from models.user import User
    from models.user_team import UserTeam
    from services.auth_service import hash_password

    team = Team(name="Team Beta")
    db.add(team)
    coach_user = User(username="coachy2", email="coachy2@test.com",
                      hashed_password=hash_password("Pass1234!"), role="coach")
    db.add(coach_user)
    db.flush()
    ut = UserTeam(user_id=coach_user.id, team_id=team.id, season_id=None)
    db.add(ut)
    db.commit()

    resp = admin_client.post(f"/teams/{team.id}/coaches/{ut.id}/delete",
                             data={"csrf_token": "test"})
    assert resp.status_code in (200, 302)
    assert db.get(UserTeam, ut.id) is None
```

Run: `pytest tests/test_roles.py -v -k "assign_coach or remove_coach" 2>&1 | head -20`
Expected: FAIL with 404 or 405

- [ ] **Step 2: Add coach assignment routes to `routes/teams.py`**

Read `routes/teams.py` to find where to add these routes. Find the imports at the top and add:
```python
from models.user import User as _User
from models.user_team import UserTeam
```

Add two new routes at the end of the file, before or after the delete route:

```python
@router.post("/{team_id}/coaches", dependencies=[Depends(require_admin)])
async def add_team_coach(
    team_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _csrf=Depends(require_csrf),
):
    team = db.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404)

    form = await request.form()
    user_id = int(form.get("user_id", 0))
    season_id_raw = form.get("season_id", "").strip()
    season_id = int(season_id_raw) if season_id_raw else None

    # Application-level duplicate guard (SQLite NULLs bypass unique constraints)
    existing_q = db.query(UserTeam).filter(
        UserTeam.user_id == user_id,
        UserTeam.team_id == team_id,
    )
    if season_id is None:
        existing_q = existing_q.filter(UserTeam.season_id.is_(None))
    else:
        existing_q = existing_q.filter(UserTeam.season_id == season_id)

    if not existing_q.first():
        db.add(UserTeam(user_id=user_id, team_id=team_id, season_id=season_id))
        db.commit()

    return RedirectResponse(f"/teams/{int(team_id)}", status_code=302)


@router.post("/{team_id}/coaches/{ut_id}/delete", dependencies=[Depends(require_admin)])
async def remove_team_coach(
    team_id: int,
    ut_id: int,
    db: Session = Depends(get_db),
    _csrf=Depends(require_csrf),
):
    ut = db.get(UserTeam, ut_id)
    if ut and ut.team_id == team_id:
        db.delete(ut)
        db.commit()
    return RedirectResponse(f"/teams/{int(team_id)}", status_code=302)
```

- [ ] **Step 3: Pass coach data to the team detail template**

Read `routes/teams.py` and find the `team_detail` GET handler. It renders `teams/detail.html`. Add to its context dict:
```python
from models.user import User as _User  # already imported above
coach_users = db.query(_User).filter(_User.role == "coach", _User.is_active.is_(True)).all()
seasons = db.query(Season).order_by(Season.start_date.desc()).all()
```

Then pass `"coach_users": coach_users` and update `"seasons": seasons` in the render context (seasons may already be there; check first).

- [ ] **Step 4: Add Coaches section to `templates/teams/detail.html`**

Read the template. Find the bottom of the page, before `{% endblock %}`. Add an admin-only coaches section:

```html
{% if user.is_admin %}
<article style="margin-top:1.5rem;">
  <header><strong>{{ t('teams.coaches') }}</strong></header>
  {% if team.coaches %}
  <table>
    <thead><tr><th>Coach</th><th>Season scope</th><th></th></tr></thead>
    <tbody>
    {% for ut in team.coaches %}
      <tr>
        <td>{{ ut.user.username }}</td>
        <td>{{ ut.season.name if ut.season else 'All seasons' }}</td>
        <td>
          <form method="post" action="/teams/{{ team.id }}/coaches/{{ ut.id }}/delete">
            <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
            <button type="submit" class="btn btn-sm btn-outline"
                    style="color:var(--tp-danger,#dc3545);"
                    onclick="return confirm('Remove this coach?')">{{ t('teams.remove_coach') }}</button>
          </form>
        </td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p class="text-muted">{{ t('teams.no_coaches') }}</p>
  {% endif %}

  <form method="post" action="/teams/{{ team.id }}/coaches"
        style="display:flex;gap:.5rem;flex-wrap:wrap;align-items:flex-end;margin-top:1rem;">
    <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
    <label style="margin:0;">
      <span style="display:block;font-size:.78rem;margin-bottom:.15rem;">Coach</span>
      <select name="user_id" class="sel-inline" required>
        <option value="">— Select coach —</option>
        {% for cu in coach_users %}
          <option value="{{ cu.id }}">{{ cu.username }}</option>
        {% endfor %}
      </select>
    </label>
    <label style="margin:0;">
      <span style="display:block;font-size:.78rem;margin-bottom:.15rem;">Season (optional)</span>
      <select name="season_id" class="sel-inline">
        <option value="">All seasons</option>
        {% for s in seasons %}
          <option value="{{ s.id }}">{{ s.name }}</option>
        {% endfor %}
      </select>
    </label>
    <button type="submit" class="btn btn-primary">{{ t('teams.add_coach') }}</button>
  </form>
</article>
{% endif %}
```

- [ ] **Step 5: Run coach assignment tests**

```bash
pytest tests/test_roles.py -v -k "assign_coach or remove_coach"
```
Expected: PASS

- [ ] **Step 6: Run full test suite**

```bash
pytest -v --tb=short
```
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add routes/teams.py templates/teams/detail.html tests/test_roles.py
git commit -m "feat: admin UI to assign/remove coaches on team detail page"
```

---

## Task 7: Events Route + Template Changes

**Files:**
- Modify: `routes/events.py`
- Modify: `templates/events/form.html` (if it exists; may be part of new/edit templates)
- Modify: `templates/events/detail.html`
- Modify: `templates/events/list.html`
- Test: `tests/test_roles.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_roles.py`:

```python
def _setup_coach_with_team(db):
    """Helper: creates a coach user, a team, a season, and UserTeam assignment. Returns (coach, team, season)."""
    from models.season import Season
    from models.team import Team
    from models.user import User
    from models.user_team import UserTeam
    from services.auth_service import hash_password

    season = Season(name="S2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    team = Team(name="Coach Team")
    db.add_all([season, team])
    db.flush()

    coach = User(username="coach_ev", email="coach_ev@test.com",
                 hashed_password=hash_password("Pass1234!"), role="coach")
    db.add(coach)
    db.flush()

    ut = UserTeam(user_id=coach.id, team_id=team.id, season_id=None)
    db.add(ut)
    db.commit()
    return coach, team, season


def _coach_client(app, db_override, coach_user):
    """Build a TestClient logged in as the given coach user.

    Mirrors the admin_client fixture pattern from conftest.py:
      create_session_cookie(user.id) → set "session_user_id" cookie.
    Also disables CSRF and overrides get_db with the in-memory test DB.
    """
    from fastapi.testclient import TestClient
    from app.database import get_db
    from routes._auth_helpers import require_csrf, require_csrf_header
    from services.auth_service import create_session_cookie

    async def _no_csrf():
        pass

    app.dependency_overrides[get_db] = lambda: (yield db_override)
    app.dependency_overrides[require_csrf] = _no_csrf
    app.dependency_overrides[require_csrf_header] = _no_csrf

    cookie_val = create_session_cookie(coach_user.id)
    c = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
    c.cookies.set("session_user_id", cookie_val)
    return c


def test_coach_can_create_event_on_assigned_team(db):
    from app.main import app

    coach, team, season = _setup_coach_with_team(db)
    c = _coach_client(app, db, coach)
    resp = c.post("/events/new", data={
        "title": "Training 1",
        "event_type": "training",
        "date": "2025-06-01",
        "team_id": str(team.id),
        "season_id": str(season.id),
        "csrf_token": "test",
    })
    app.dependency_overrides.clear()
    assert resp.status_code == 302


def test_coach_cannot_create_event_on_unassigned_team(db):
    from models.team import Team
    from app.main import app

    coach, _, season = _setup_coach_with_team(db)
    other_team = Team(name="Other Team")
    db.add(other_team)
    db.commit()

    c = _coach_client(app, db, coach)
    resp = c.post("/events/new", data={
        "title": "Should Fail",
        "event_type": "training",
        "date": "2025-06-01",
        "team_id": str(other_team.id),
        "season_id": str(season.id),
        "csrf_token": "test",
    })
    app.dependency_overrides.clear()
    assert resp.status_code == 403
```

Run: `pytest tests/test_roles.py -v -k "create_event" 2>&1 | head -30`
Expected: FAIL (403 returned instead of 302 for assigned team, because guard is still `require_admin`)

- [ ] **Step 2: Update `routes/events.py`**

Read the full file. Make these changes:

**a) Add imports at the top** (find existing imports and add alongside them):
```python
from routes._auth_helpers import check_team_access, require_coach_or_admin
```

**b) New event GET handler** — find `@router.get("/new")` and change its dependency from `require_admin` to `require_coach_or_admin`. Also: when building the `teams` list for the form, filter to coach's teams:

Inside the handler body, after getting `user`, add:
```python
if user.is_admin:
    teams = db.query(Team).order_by(Team.name).all()
else:
    from routes._auth_helpers import get_coach_teams  # noqa: PLC0415
    managed_ids = get_coach_teams(user, db)
    teams = db.query(Team).filter(Team.id.in_(managed_ids)).order_by(Team.name).all()
```

**c) New event POST handler** — find `@router.post("/new")` and:
- Change dependency from `require_admin` to `require_coach_or_admin`
- After parsing `team_id` from the form, add:
```python
if not user.is_admin:
    check_team_access(user, team_id, db)
```

**d) Edit event GET** — find `@router.get("/{event_id}/edit")`, change to `require_coach_or_admin`. In handler body, after fetching the event:
```python
check_team_access(user, event.team_id, db, season_id=event.season_id)
```

**e) Edit event POST** — find `@router.post("/{event_id}/edit")`, change to `require_coach_or_admin`. After fetching event:
```python
check_team_access(user, event.team_id, db, season_id=event.season_id)
# Coach cannot change team_id
if not user.is_admin:
    team_id = event.team_id  # ignore submitted value
```

**f) Delete event POST** — find `@router.post("/{event_id}/delete")`, change to `require_coach_or_admin`. Add after fetching event:
```python
check_team_access(user, event.team_id, db, season_id=event.season_id)
```

**g) Notify GET and POST** — same pattern: change to `require_coach_or_admin`, add `check_team_access`.

**h) Send reminders POST** — same: change to `require_coach_or_admin`, add `check_team_access`.

- [ ] **Step 3: Update event templates**

Read `templates/events/detail.html`. Find the block that shows Edit/Delete/Notify/Reminders buttons — currently gated by `{% if user.is_admin %}`. Change to:
```html
{% if user.is_admin or (user.is_coach and event.team_id in coach_team_ids) %}
```

To support this, the route handler must pass `coach_team_ids` to the template. In `events.py` GET handler for event detail, add to the render context:
```python
"coach_team_ids": get_coach_teams(user, db) if user.is_coach else set(),
```

Read `templates/events/list.html`. Find the Edit button (currently `{% if user.is_admin %}`). Change to:
```html
{% if user.is_admin or (user.is_coach and ev.team_id in coach_team_ids) %}
```

Pass `coach_team_ids` from the list route handler similarly.

Read the event form template (may be `templates/events/form.html` or inline in `new.html` / `edit.html`). Find the team dropdown. For coaches, the teams list is already filtered in the GET handler — no template change needed beyond checking the team field is read-only on edit:

In `templates/events/edit.html` (or wherever the edit form is), find the team field and add:
```html
{% if not user.is_admin %}
  <input type="hidden" name="team_id" value="{{ event.team_id }}">
  <p>{{ event.team.name if event.team else '—' }}</p>
{% else %}
  <select name="team_id">...</select>
{% endif %}
```

- [ ] **Step 4: Run events tests**

```bash
pytest tests/test_roles.py -v -k "event"
```
Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest -v --tb=short
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add routes/events.py templates/events/ tests/test_roles.py
git commit -m "feat: allow coaches to manage events on their assigned teams"
```

---

## Task 8: Attendance Route + Template Changes

**Files:**
- Modify: `routes/attendance.py`
- Modify: `templates/attendance/mark.html`
- Test: `tests/test_roles.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_roles.py`:

```python
def test_coach_can_mark_attendance_on_their_team(db):
    from datetime import date
    from models.event import Event
    from models.player import Player
    from models.player_team import PlayerTeam
    from app.main import app

    coach, team, season = _setup_coach_with_team(db)

    player = Player(first_name="Alice", last_name="Smith", is_active=True)
    db.add(player)
    db.flush()
    db.add(PlayerTeam(player_id=player.id, team_id=team.id,
                               season_id=season.id, priority=1))

    event = Event(title="Match", event_type="match", event_date=date(2025, 6, 1),
                  team_id=team.id, season_id=season.id)
    db.add(event)
    db.commit()

    c = _coach_client(app, db, coach)
    resp = c.post(f"/attendance/{event.id}/{player.id}",
                  data={"status": "present", "csrf_token": "test"},
                  follow_redirects=False)
    app.dependency_overrides.clear()
    assert resp.status_code == 302


def test_coach_cannot_mark_attendance_on_other_team(db):
    from datetime import date
    from models.event import Event
    from models.player import Player
    from models.team import Team
    from models.player_team import PlayerTeam
    from models.season import Season
    from app.main import app

    coach, _, _ = _setup_coach_with_team(db)

    other_team = Team(name="Other Team2")
    db.add(other_team)
    other_season = Season(name="S2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.add(other_season)
    player = Player(first_name="Bob", last_name="Jones", is_active=True)
    db.add(player)
    db.flush()
    db.add(PlayerTeam(player_id=player.id, team_id=other_team.id,
                               season_id=other_season.id, priority=1))
    event = Event(title="Other Match", event_type="match", event_date=date(2026, 6, 1),
                  team_id=other_team.id, season_id=other_season.id)
    db.add(event)
    db.commit()

    c = _coach_client(app, db, coach)
    resp = c.post(f"/attendance/{event.id}/{player.id}",
                  data={"status": "present", "csrf_token": "test"},
                  follow_redirects=False)
    app.dependency_overrides.clear()
    assert resp.status_code == 403
```

Run: `pytest tests/test_roles.py -v -k "attendance" 2>&1 | head -20`
Expected: FAIL

- [ ] **Step 2: Update `routes/attendance.py`**

Read the full file. Find the `attendance_page` GET handler and `update_attendance` POST handler.

**GET handler** — currently splits on `is_admin`. Add a middle case for coaches:

```python
if user.is_admin:
    players = ...  # existing admin logic
elif user.is_coach:
    from routes._auth_helpers import check_team_access, get_coach_teams  # noqa: PLC0415
    check_team_access(user, event.team_id, db, season_id=event.season_id)
    # Coach sees all players on their team — same as admin path
    players = ...  # same query as admin
    is_admin_view = True  # flag so template renders full view
else:
    players = ...  # existing member logic (own players only)
    is_admin_view = False
```

Look at the exact variable names used in the existing handler and mirror that logic for the coach path.

**POST handler** — currently:
```python
if not user.is_admin and player.user_id != user.id:
    raise NotAuthorized
```

Change to:
```python
if user.is_admin:
    pass  # admin can update anyone
elif user.is_coach:
    from routes._auth_helpers import check_team_access  # noqa: PLC0415
    check_team_access(user, event.team_id, db, season_id=event.season_id)
elif player.user_id != user.id:
    raise NotAuthorized
```

- [ ] **Step 3: Update `templates/attendance/mark.html`**

Read the template. The admin view and member view are in separate branches. The coach should use the admin-style view. Pass an `is_admin_view` (or similar) boolean from the route, and change the template condition from `{% if user.is_admin %}` to `{% if is_admin_view %}` (or `{% if user.is_admin or user.is_coach %}`).

Check the exact template variable the route passes and use that.

- [ ] **Step 4: Run attendance tests**

```bash
pytest tests/test_roles.py -v -k "attendance"
```
Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest -v --tb=short
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add routes/attendance.py templates/attendance/mark.html tests/test_roles.py
git commit -m "feat: coach can mark attendance for all players on their assigned team"
```

---

## Task 9: Players Route + Template Changes

**Files:**
- Modify: `routes/players.py`
- Modify: `templates/players/list.html`
- Test: `tests/test_roles.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_roles.py`:

```python
def test_coach_can_bulk_update_pt_fields(db):
    from models.player import Player
    from models.player_team import PlayerTeam
    from app.main import app

    coach, team, season = _setup_coach_with_team(db)
    player = Player(first_name="Carol", last_name="White", is_active=True)
    db.add(player)
    db.flush()
    db.add(PlayerTeam(player_id=player.id, team_id=team.id,
                               season_id=season.id, priority=1))
    db.commit()

    c = _coach_client(app, db, coach)
    # BulkUpdateRequest uses key "players" (list of PlayerDiff with extra fields)
    resp = c.post("/players/bulk-update", json={
        "players": [{"id": player.id, "shirt_number": 7}],
        "team_id": team.id,
        "season_id": season.id,
    }, follow_redirects=False)
    app.dependency_overrides.clear()
    assert resp.status_code == 200


def test_coach_cannot_create_player(db):
    from app.main import app

    coach, _, _ = _setup_coach_with_team(db)

    c = _coach_client(app, db, coach)
    resp = c.post("/players/new", data={
        "first_name": "New", "last_name": "Player", "csrf_token": "test"
    }, follow_redirects=False)
    app.dependency_overrides.clear()
    assert resp.status_code == 403
```

Run: `pytest tests/test_roles.py -v -k "bulk_update or create_player" 2>&1 | head -20`
Expected: FAIL for bulk_update (403), PASS for create_player already (since require_admin)

- [ ] **Step 2: Update `routes/players.py`**

Read the file. Find `bulk-assign`, `bulk-remove`, `bulk-update` handlers.

For each, import and use the new helpers:
```python
from routes._auth_helpers import check_team_access, require_coach_or_admin
```

**bulk-assign POST**: change `require_admin` → `require_coach_or_admin`. After parsing `team_id`:
```python
check_team_access(user, body.team_id, db)
```

**bulk-remove POST**: same pattern.

**bulk-update POST**: change `require_admin` → `require_coach_or_admin`. After parsing `team_id`:
```python
check_team_access(user, body.team_id, db)
```
Also, for coach users, filter allowed fields to PT-fields only:
```python
PT_FIELDS = frozenset({
    "shirt_number", "position", "injured_until", "absent_by_default", "priority",
})
if not user.is_admin:
    # coaches may only update team-specific (PT) fields
    updates = [u for u in updates if u.field in PT_FIELDS]
```

Look at the exact shape of the `bulk-update` request body to apply this correctly.

- [ ] **Step 3: Update `templates/players/list.html`**

Read the file. The Edit, Save, Cancel buttons and the Columns/Filter/Import/New buttons are all inside `{% if user.is_admin %}`. Change the edit-mode buttons to also show for coaches:

```html
{% if user.is_admin or user.is_coach %}
<button type="button" class="btn btn-outline" id="edit-btn">Edit</button>
<button type="button" class="btn btn-primary" id="save-btn" style="display:none;" disabled>Save changes</button>
<button type="button" class="btn btn-outline" id="cancel-btn" style="display:none;">Cancel</button>
{% endif %}
```

Keep "New player", "Import", "Columns", "Filter", "Bulk toolbar" as admin-only.

Also ensure `window.PLAYERS_CONFIG` is exposed to coaches. Find:
```html
{% if user.is_admin %}
<script>
  window.PLAYERS_CONFIG = { ... };
</script>
<script src="/static/js/players-table.js"></script>
{% endif %}
```

Change to:
```html
{% if user.is_admin or user.is_coach %}
<script>
  window.PLAYERS_CONFIG = { ... };
</script>
<script src="/static/js/players-table.js"></script>
{% endif %}
```

- [ ] **Step 4: Run players tests**

```bash
pytest tests/test_roles.py -v -k "bulk_update or create_player"
```
Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest -v --tb=short
```
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add routes/players.py templates/players/list.html tests/test_roles.py
git commit -m "feat: coaches can use inline edit and bulk operations on their team"
```

---

## Task 10: Reports Route + Template Changes

**Files:**
- Modify: `routes/reports.py`
- Modify: `templates/reports/season.html`
- Test: `tests/test_roles.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_roles.py`:

```python
def test_coach_can_view_season_report(db):
    from models.season import Season
    from app.main import app

    coach, team, season = _setup_coach_with_team(db)

    c = _coach_client(app, db, coach)
    resp = c.get(f"/reports/season/{season.id}")
    app.dependency_overrides.clear()
    assert resp.status_code == 200


def test_coach_cannot_view_other_player_report(db):
    from models.player import Player
    from app.main import app

    coach, _, _ = _setup_coach_with_team(db)
    other_player = Player(first_name="Other", last_name="Guy", is_active=True)
    db.add(other_player)
    db.commit()

    c = _coach_client(app, db, coach)
    resp = c.get(f"/reports/player/{other_player.id}")
    app.dependency_overrides.clear()
    assert resp.status_code in (302, 403)
```

Run: `pytest tests/test_roles.py -v -k "report" 2>&1 | head -20`
Expected: FAIL (403 on season report for coach since it's admin-only nav, but route may allow it)

- [ ] **Step 2: Update `routes/reports.py`**

Read the full file.

**`reports_index` (redirect)**: The route is `require_login`. For coaches, redirect to the active season report with their first managed team pre-filtered:

```python
if user.is_coach:
    from routes._auth_helpers import get_coach_teams  # noqa: PLC0415
    managed = get_coach_teams(user, db)
    if managed:
        first_team_id = next(iter(managed))
        return RedirectResponse(f"/reports/season/{season.id}?team_id={first_team_id}", status_code=302)
```

**`report_season`**: Currently `require_login`. No guard change needed. But pass coach team filter context. After querying stats, if the user is a coach, filter the `stats` to only their managed teams:

```python
if user.is_coach:
    from routes._auth_helpers import get_coach_teams  # noqa: PLC0415
    managed_ids = get_coach_teams(user, db, season_id=season_id)
    # filter the stats dict/list to managed teams only
    # Look at what `get_season_attendance_stats` returns and filter accordingly
```

Pass `"coach_team_ids": managed_ids if user.is_coach else None` to the template.

**`report_player`**: Currently restricts members to their own players. Extend for coaches:

```python
if not user.is_admin:
    if user.is_coach:
        from routes._auth_helpers import get_coach_teams  # noqa: PLC0415
        # Coach can view reports for players on their teams
        managed_ids = get_coach_teams(user, db)
        player_team_ids = {pt.team_id for pt in player.team_memberships}
        if not managed_ids.intersection(player_team_ids):
            return RedirectResponse("/dashboard", status_code=302)
    elif player.user_id != user.id:
        return RedirectResponse("/dashboard", status_code=302)
```

- [ ] **Step 3: Update `templates/reports/season.html`**

Read the template. The season report shows per-team stats. If `coach_team_ids` is passed and not None, filter the displayed teams. Find where teams/stats are iterated and wrap with:

```html
{% if coach_team_ids is none or team_id in coach_team_ids %}
  ... existing team stats block ...
{% endif %}
```

Look at the exact variable names in the template.

- [ ] **Step 4: Update `templates/base.html` — Reports nav link for coaches**

Read base.html. Find:
```html
{% if user.is_admin %}
  ...
  <li><a href="/reports" ...>{{ t('nav.reports') }}</a></li>
{% endif %}
```

Change to show Reports for both admins and coaches:
```html
{% if user.is_admin or user.is_coach %}
  <li><a href="/reports" ...>{{ t('nav.reports') }}</a></li>
{% endif %}
```

Keep Seasons admin-only.

- [ ] **Step 5: Run reports tests**

```bash
pytest tests/test_roles.py -v -k "report"
```
Expected: PASS

- [ ] **Step 6: Run full test suite**

```bash
pytest -v --tb=short
```
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add routes/reports.py templates/reports/ templates/base.html tests/test_roles.py
git commit -m "feat: coaches can view reports for their teams and players"
```

---

## Task 11: Season-Scope Tests + Final Verification

**Files:**
- Test: `tests/test_roles.py`

- [ ] **Step 1: Write season-scope tests**

Add to `tests/test_roles.py`:

```python
def test_coach_season_scoped_denied_other_season(db):
    """Coach assigned to team X for season A cannot manage events in season B."""
    from datetime import date
    from models.event import Event
    from models.season import Season
    from models.team import Team
    from models.user import User
    from models.user_team import UserTeam
    from services.auth_service import hash_password
    from app.main import app

    season_a = Season(name="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    season_b = Season(name="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    team = Team(name="Scoped Team")
    db.add_all([season_a, season_b, team])
    db.flush()

    coach = User(username="scoped_coach", email="scoped@test.com",
                 hashed_password=hash_password("Pass1234!"), role="coach")
    db.add(coach)
    db.flush()

    # Assign coach to team X for season A ONLY
    db.add(UserTeam(user_id=coach.id, team_id=team.id, season_id=season_a.id))

    event_b = Event(title="Season B Event", event_type="training",
                    event_date=date(2026, 3, 1), team_id=team.id, season_id=season_b.id)
    db.add(event_b)
    db.commit()

    c = _coach_client(app, db, coach)
    resp = c.get(f"/events/{event_b.id}/edit", follow_redirects=False)
    app.dependency_overrides.clear()
    assert resp.status_code == 403


def test_coach_null_season_can_access_all_seasons(db):
    """Coach assigned with season_id=NULL can manage events in any season."""
    from datetime import date
    from models.event import Event
    from models.season import Season
    from models.team import Team
    from models.user import User
    from models.user_team import UserTeam
    from services.auth_service import hash_password
    from app.main import app

    season_c = Season(name="2027", start_date=date(2027, 1, 1), end_date=date(2027, 12, 31))
    team = Team(name="All Season Team")
    db.add_all([season_c, team])
    db.flush()

    coach = User(username="all_season_coach", email="allseason@test.com",
                 hashed_password=hash_password("Pass1234!"), role="coach")
    db.add(coach)
    db.flush()

    # Assign with season_id=NULL → all seasons
    db.add(UserTeam(user_id=coach.id, team_id=team.id, season_id=None))

    event_c = Event(title="Future Event", event_type="training",
                    event_date=date(2027, 5, 1), team_id=team.id, season_id=season_c.id)
    db.add(event_c)
    db.commit()

    c = _coach_client(app, db, coach)
    resp = c.get(f"/events/{event_c.id}/edit", follow_redirects=False)
    app.dependency_overrides.clear()
    assert resp.status_code == 200


def test_coach_with_no_teams_behaves_like_member(db):
    """A coach with no UserTeam rows cannot edit events."""
    from datetime import date
    from models.event import Event
    from models.season import Season
    from models.team import Team
    from models.user import User
    from services.auth_service import hash_password
    from app.main import app

    season = Season(name="S_no_team", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    team = Team(name="Unassigned Team")
    db.add_all([season, team])
    db.flush()

    coach = User(username="no_team_coach", email="noteam@test.com",
                 hashed_password=hash_password("Pass1234!"), role="coach")
    db.add(coach)
    db.flush()
    # No UserTeam row added

    event = Event(title="No Access Event", event_type="training",
                  event_date=date(2025, 7, 1), team_id=team.id, season_id=season.id)
    db.add(event)
    db.commit()

    c = _coach_client(app, db, coach)
    resp = c.get(f"/events/{event.id}/edit", follow_redirects=False)
    app.dependency_overrides.clear()
    assert resp.status_code == 403
```

- [ ] **Step 2: Run all new role tests**

```bash
pytest tests/test_roles.py -v
```
Expected: all 15+ tests PASS

- [ ] **Step 3: Run complete test suite**

```bash
pytest -v --tb=short
```
Expected: all tests pass, 0 failures

- [ ] **Step 4: Lint check**

```bash
ruff check . --fix
ruff format .
```
Expected: no errors

- [ ] **Step 5: Commit**

```bash
git add tests/test_roles.py
git commit -m "test: add season-scope and no-team coach boundary tests"
```

- [ ] **Step 6: Push**

```bash
git push
```
