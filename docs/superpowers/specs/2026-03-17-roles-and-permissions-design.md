# Roles & Permissions Design

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a `coach` role with team-scoped management rights, and add a public `/schedule` page for unauthenticated visitors.

**Architecture:** Add a `UserTeam` join table linking coach users to their managed teams. Extend the auth helper layer with a `require_coach_or_admin` guard and a `check_team_access` utility. A new public route serves event schedule data without authentication.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Jinja2, Alembic, pytest

---

## 1. Roles

`User.role` gains a third value: `"coach"` (alongside existing `"admin"` and `"member"`).

| Role | Description |
|------|-------------|
| `admin` | Full CRUD across all resources, user management, season/team creation |
| `coach` | Team-scoped management — events, attendance, roster edits for assigned team(s) |
| `member` | View everything; edit own attendance and own player report only |
| *(public)* | View `/schedule` only — no login required |

Helper properties on `User`:
- `is_admin` — already exists (`role == "admin"`)
- `is_coach` — new (`role == "coach"`)

**A coach with no assigned `UserTeam` rows is functionally equivalent to a member** — they can view data but take no management actions until an admin assigns them to a team.

---

## 2. Data Model — `UserTeam`

New table linking a coach user to the team(s) they manage.

```python
class UserTeam(Base):
    __tablename__ = "user_team"

    id:        Mapped[int]        = mapped_column(primary_key=True)
    user_id:   Mapped[int]        = mapped_column(ForeignKey("user.id"), nullable=False)
    team_id:   Mapped[int]        = mapped_column(ForeignKey("team.id"), nullable=False)
    season_id: Mapped[int | None] = mapped_column(ForeignKey("season.id"), nullable=True)

    user:   Mapped["User"]          = relationship(back_populates="managed_teams")
    team:   Mapped["Team"]          = relationship(back_populates="coaches")
    season: Mapped["Season | None"] = relationship()
```

- `season_id = NULL` means the coach manages that team across all seasons.
- A coach may have multiple `UserTeam` rows (multiple teams or season-specific assignments).
- Add `managed_teams` back-reference on `User`, `coaches` back-reference on `Team`.

**Uniqueness:** SQLite does not enforce unique constraints when any column is NULL. Use an application-level guard in the admin UI: before inserting a `UserTeam` row, check for an existing row with the same `(user_id, team_id, season_id)` (comparing `season_id IS NULL` explicitly) and reject duplicates. No DB-level unique constraint is added.

**When a coach is removed from a team** (admin deletes the `UserTeam` row): existing events for that team remain unchanged and become admin-only editable. Access is revoked immediately going forward. No notification is sent.

**Alembic migration required.**

---

## 3. Auth Helpers

File: `routes/_auth_helpers.py`

### New helper: `get_coach_teams`
Returns the set of team IDs the user may manage. Only called for coach users.

```python
def get_coach_teams(user: User, db: Session, season_id: int | None = None) -> set[int]:
    """Return set of team_ids the coach user manages for the given season.
    Always returns empty set for non-coach users — callers should check is_admin first.
    """
    q = db.query(UserTeam.team_id).filter(UserTeam.user_id == user.id)
    if season_id:
        q = q.filter(or_(UserTeam.season_id == season_id, UserTeam.season_id.is_(None)))
    return {row[0] for row in q.all()}
```

### New dependency: `require_coach_or_admin`
```python
def require_coach_or_admin(user: User = Depends(require_login)) -> User:
    if not (user.is_admin or user.is_coach):
        raise NotAuthorized
    return user
```

### New utility: `check_team_access`
Called imperatively inside route handlers to verify the acting user has rights over a team.
`season_id` should be passed whenever the context has one (e.g. the event's season); this enforces season-scoped assignments correctly. A coach assigned to team X for season 2025 only (`season_id != NULL`) will be denied on season 2026 events for the same team.

```python
def check_team_access(
    user: User, team_id: int, db: Session, season_id: int | None = None
) -> None:
    """Raise NotAuthorized if user has no access to team_id (in the given season)."""
    if user.is_admin:
        return
    if team_id not in get_coach_teams(user, db, season_id=season_id):
        raise NotAuthorized
```

**Season-scope enforcement decision:** A coach with `season_id = NULL` on their `UserTeam` row manages that team across all seasons. A coach with `season_id = X` manages only season X. `check_team_access` always passes the context season so season-specific assignments are correctly enforced.

Both GET and POST handlers that are team-specific must call `check_team_access` — GET handlers need it so a coach cannot load the edit form for a team they don't manage.

---

## 4. Route Changes

### 4a. Events (`routes/events.py`)

| Route | Before | After |
|-------|--------|-------|
| GET `/events/new` | `require_admin` | `require_coach_or_admin` |
| POST `/events/new` | `require_admin` | `require_coach_or_admin`; `check_team_access(submitted_team_id)` |
| GET `/events/{id}/edit` | `require_admin` | `require_coach_or_admin` + `check_team_access(event.team_id)` |
| POST `/events/{id}/edit` | `require_admin` | `require_coach_or_admin` + `check_team_access(event.team_id)`; **coach may not change `team_id`** — the team field is hidden/ignored for coaches on save |
| POST `/events/{id}/delete` | `require_admin` | `require_coach_or_admin` + `check_team_access(event.team_id)` |
| GET `/events/{id}/notify` | `require_admin` | `require_coach_or_admin` + `check_team_access(event.team_id)` |
| POST `/events/{id}/notify` | `require_admin` | `require_coach_or_admin` + `check_team_access(event.team_id)` |
| POST `/events/{id}/send-reminders` | `require_admin` | `require_coach_or_admin` + `check_team_access(event.team_id)` |

For coaches: the team dropdown on the new event form is limited to their assigned teams.

**Coach cannot change `event.team_id`:** on the edit POST, if the user is a coach, the submitted `team_id` is ignored and the event's existing `team_id` is kept.

### 4b. Players (`routes/players.py`)

| Route | Before | After |
|-------|--------|-------|
| GET `/players` | `require_login` | unchanged; inline edit mode activated only if user is admin or coach |
| GET `/players/{id}/edit` | `require_admin` | stays `require_admin` (coaches use inline edit only) |
| POST `/players/bulk-assign` | `require_admin` | `require_coach_or_admin`; `check_team_access(submitted_team_id)` |
| POST `/players/bulk-remove` | `require_admin` | `require_coach_or_admin`; `check_team_access(submitted_team_id)` |
| POST `/players/bulk-update` | `require_admin` | `require_coach_or_admin`; only pt-fields allowed for coaches (shirt#, position, role, status, injured_until, absent_by_default, priority); `check_team_access(submitted_team_id)` |
| GET/POST `/players/new` | `require_admin` | stays `require_admin` |
| POST `/players/{id}/delete` | `require_admin` | stays `require_admin` |
| POST `/players/import` | `require_admin` | stays `require_admin` |

The inline edit form on `GET /players` is safe for coaches because the actual data mutation goes through `POST /players/bulk-update`, which calls `check_team_access`. No additional GET guard is needed beyond the existing `require_login`.

### 4c. Attendance (`routes/attendance.py`)

| Route | Before | After |
|-------|--------|-------|
| GET `/attendance/{event_id}` | member=own players only, admin=all | member=own only, **coach=all players on their team** (full admin-style view), admin=all |
| POST `/attendance/{event_id}/{player_id}` | member=own only, admin=all | member=own only, **coach=all players on their team**, admin=all |

For the GET handler: when the user is a coach, verify `check_team_access(event.team_id)` and render the full player list (same template path as admin).

### 4d. Reports (`routes/reports.py`)

| Route | Before | After |
|-------|--------|-------|
| GET `/reports` | `require_login` → redirect to active season | coach redirect includes `?team_id=<first_managed_team_id>` to pre-filter |
| GET `/reports/season/{season_id}` | `require_login`; shows all teams | coach: filter display to their managed team(s) only |
| GET `/reports/player/{player_id}` | member=own only, admin=all | member=own only, **coach=players on their team**, admin=all |

### 4e. New public route (`routes/schedule.py`)

```
GET /schedule
```

- No auth required — no `require_login` dependency.
- Renders `templates/schedule/index.html`.
- Accepts optional `?season_id=` and `?team_id=` query params.
- Exposes only: event date, time, location, type (match/training/other), team name, season name.
- Excludes: player names, attendance data, any admin/coach UI.
- Registered in `app/main.py` router list.

---

## 5. Admin UI — Assign Coaches

Admins need a way to assign coach users to teams. This fits on the existing team detail page (`/teams/{team_id}`).

### New section on team detail page: "Coaches"

Lists assigned coach users (name + season scope). Admin can:
- **Add coach:** select a user with `role = "coach"` + optional season → `POST /teams/{id}/coaches` creates `UserTeam` row (with application-level duplicate guard)
- **Remove coach:** `POST /teams/{id}/coaches/{user_team_id}/delete` deletes the row

New routes (admin-only):
```
POST /teams/{team_id}/coaches          — add coach assignment
POST /teams/{team_id}/coaches/{ut_id}/delete  — remove coach assignment
```

### User registration (`/auth/register`)

Stays `require_admin` guarded — no self-registration path. Add `"coach"` as a third option in the role dropdown. No other changes.

---

## 6. Template Changes

### Navigation (`templates/base.html`)
- "Schedule" link added for **all** visitors including unauthenticated — always visible in nav.
- Coaches see the same nav links as members, with one addition: **Reports** is shown to coaches (was admin-only).
- Seasons link remains admin-only.

### Events (`templates/events/`)
- New event form: coaches only see their assigned teams in the team dropdown.
- Edit form: team field is read-only (hidden) for coaches.
- Edit/delete/notify/reminders buttons: shown to admins and to coaches who own the event's team.

### Players (`templates/players/list.html`)
- Inline edit mode: available to coaches (pt-fields for players on their team).
- Bulk assign/remove: available to coaches for their teams only.
- "New player", "Delete", "Import" buttons: admin-only (unchanged).

### Attendance (`templates/attendance/mark.html`)
- Coaches get the full admin-style view (all team players), not the member-only-own-player view.

### Teams (`templates/teams/detail.html`)
- New "Coaches" section (admin-only): lists assigned coaches with season scope, add/remove form.

### Reports (`templates/reports/`)
- Season report: when user is coach, display only their team's data.

### Schedule (`templates/schedule/index.html`)
- New template. Season/team filter dropdowns (same style as events list). Table of upcoming events: date, time, location, type, team name. No player data. No login required.

---

## 7. i18n Keys

New keys required in all four locale files (`locales/en.json`, `it.json`, `fr.json`, `de.json`):

```
nav.schedule           — "Schedule" / "Calendario" / "Calendrier" / "Spielplan"
teams.coaches          — "Coaches" (section heading)
teams.add_coach        — "Add coach"
teams.remove_coach     — "Remove"
teams.no_coaches       — "No coaches assigned"
schedule.title         — "Schedule"
schedule.no_events     — "No upcoming events"
auth.role_coach        — "Coach"
```

---

## 8. Testing

New file: `tests/test_roles.py`

- Coach can create event on assigned team → 302
- Coach cannot create event on unassigned team → 403
- Coach can edit event on assigned team → 302
- Coach cannot edit event on unassigned team → 403
- Coach cannot change `team_id` on event edit
- Coach can edit pt-fields for player on their team → 200
- Coach cannot create/delete players → 403
- Coach can mark attendance for all players on their team → 302
- Coach cannot mark attendance for player on unassigned team's event → 403
- Member still limited to own attendance → 403 for others
- Public `/schedule` returns 200 without authentication
- Public `/schedule` response does not contain player names
- Coach with no assigned teams behaves like a member
- Coach assigned to team X for season A cannot manage events in season B for team X
- Coach assigned to team X with `season_id = NULL` can manage events across all seasons for team X

---

## 9. Migration

Alembic revision: add `user_team` table.

```python
def upgrade():
    op.create_table(
        "user_team",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("team.id"), nullable=False),
        sa.Column("season_id", sa.Integer(), sa.ForeignKey("season.id"), nullable=True),
    )
    op.create_index("ix_user_team_user_id", "user_team", ["user_id"])
    op.create_index("ix_user_team_team_id", "user_team", ["team_id"])
```
