# Roles & Permissions Design

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a `coach` role with team-scoped management rights, and add a public `/schedule` page for unauthenticated visitors.

**Architecture:** Add a `UserTeam` join table linking coach users to their managed teams. Extend the auth helper layer with a `require_coach_for_team` guard. A new public route serves event schedule data without authentication.

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

    __table_args__ = (UniqueConstraint("user_id", "team_id", "season_id"),)
```

- `season_id = NULL` means the coach manages that team across all seasons.
- A coach may have multiple `UserTeam` rows (multiple teams or season-specific assignments).
- Add `managed_teams` back-reference on `User`, `coaches` back-reference on `Team`.

**Alembic migration required.**

---

## 3. Auth Helpers

File: `routes/_auth_helpers.py`

### New helper: `get_coach_teams`
```python
def get_coach_teams(user: User, db: Session, season_id: int | None = None) -> set[int]:
    """Return the set of team_ids the user may manage for the given season."""
    if user.is_admin:
        return None  # None = all teams
    if not user.is_coach:
        return set()
    q = db.query(UserTeam.team_id).filter(UserTeam.user_id == user.id)
    if season_id:
        q = q.filter(or_(UserTeam.season_id == season_id, UserTeam.season_id.is_(None)))
    else:
        q = q  # no season filter — return all assigned teams
    return {row[0] for row in q.all()}
```

### New dependency: `require_coach_or_admin`
```python
def require_coach_or_admin(user=Depends(require_login)):
    if not (user.is_admin or user.is_coach):
        raise NotAuthorized
    return user
```

### New dependency factory: `require_team_access(team_id)`
Used in route handlers to verify the coach (or admin) has rights to a specific team:
```python
def check_team_access(user: User, team_id: int, db: Session) -> None:
    """Raise NotAuthorized if user has no access to team_id."""
    if user.is_admin:
        return
    managed = get_coach_teams(user, db)
    if team_id not in managed:
        raise NotAuthorized
```

---

## 4. Route Changes

### 4a. Events (`routes/events.py`)

| Route | Before | After |
|-------|--------|-------|
| GET/POST `/events/new` | `require_admin` | `require_coach_or_admin`; new event must belong to a team the coach manages |
| GET/POST `/events/{id}/edit` | `require_admin` | `require_coach_or_admin` + `check_team_access(event.team_id)` |
| POST `/events/{id}/delete` | `require_admin` | `require_coach_or_admin` + `check_team_access(event.team_id)` |
| POST `/events/{id}/notify` | `require_admin` | `require_coach_or_admin` + `check_team_access(event.team_id)` |
| POST `/events/{id}/send-reminders` | `require_admin` | `require_coach_or_admin` + `check_team_access(event.team_id)` |

For coaches: the "team" dropdown on the new event form is limited to their assigned teams.

### 4b. Players (`routes/players.py`)

| Route | Before | After |
|-------|--------|-------|
| POST `/players/bulk-assign` | `require_admin` | `require_coach_or_admin`; coach can only assign to their teams |
| POST `/players/bulk-remove` | `require_admin` | `require_coach_or_admin`; coach can only remove from their teams |
| POST `/players/bulk-update` | `require_admin` | `require_coach_or_admin`; only pt-fields (shirt#, position, role, status, injured_until, absent_by_default, priority); scoped to coach's teams |
| GET/POST `/players/new` | `require_admin` | stays `require_admin` |
| POST `/players/{id}/delete` | `require_admin` | stays `require_admin` |
| POST `/players/import` | `require_admin` | stays `require_admin` |

### 4c. Attendance (`routes/attendance.py`)

| Route | Before | After |
|-------|--------|-------|
| POST `/attendance/{event_id}/{player_id}` | member=own only, admin=all | member=own only, coach=all players on their team, admin=all |

### 4d. Reports (`routes/reports.py`)

| Route | Before | After |
|-------|--------|-------|
| GET `/reports/season/{season_id}` | `require_login` | coach sees only their team's stats on the page |
| GET `/reports/player/{player_id}` | member=own only | coach=players on their team, admin=all |

### 4e. New public route (`routes/schedule.py`)

```
GET /schedule
```

- No auth required (no `require_login` dependency).
- Renders `templates/schedule/index.html`.
- Accepts optional `?season_id=` and `?team_id=` query params.
- Returns only: event date, time, location, type, team name, season name.
- Excludes: player names, attendance data, any admin UI.

---

## 5. Admin UI — Assign Coaches

Admins need a way to create coach users and assign them to teams. This fits naturally into the existing team detail page (`/teams/{team_id}`).

**New section on team detail page:** "Coaches" card listing assigned coach users with season scope. An admin can:
- Add a coach: select user (filtered to `role = "coach"`) + optional season → creates `UserTeam` row
- Remove a coach: delete the `UserTeam` row

**User registration (`/auth/register`):** The existing form already collects username/email/password/role. Add `"coach"` as a selectable role option (was limited to admin/member).

---

## 6. Template Changes

### Navigation (`templates/base.html`)
- Add "Schedule" link visible to **all** users including unauthenticated (always shown).
- Coaches see the same nav as members (no Seasons or Reports links), except Reports becomes visible if they have at least one assigned team.

### Events (`templates/events/`)
- New event form: coaches only see their assigned teams in the team dropdown.
- Edit/delete/notify buttons: shown to admins and to coaches who own the event's team.

### Players (`templates/players/list.html`)
- Inline edit mode: coaches can edit pt-fields for players on their team.
- Bulk assign/remove: coaches can use these for their teams only.
- "New player", "Delete", "Import" buttons: admin-only (unchanged).

### Teams (`templates/teams/detail.html`)
- New "Coaches" section (admin-only): lists assigned coaches, add/remove form.

### Schedule (`templates/schedule/index.html`)
- New template. Season/team filter dropdowns. Table of upcoming events (date, time, location, type, team). No login required.

---

## 7. Testing

- `tests/test_roles.py` — new file covering:
  - Coach can create/edit/delete event on assigned team
  - Coach cannot modify event on a different team (403)
  - Coach can edit pt-fields for players on their team
  - Coach cannot create/delete players
  - Coach can mark attendance for all players on their team
  - Coach cannot mark attendance on a different team's event
  - Public `/schedule` returns 200 without authentication
  - Public `/schedule` does not expose player names
  - Member still limited to own attendance

---

## 8. Migration

Alembic revision to add `user_team` table:
- `user_id` FK → `user.id`
- `team_id` FK → `team.id`
- `season_id` FK → `season.id` (nullable)
- Unique constraint on `(user_id, team_id, season_id)`
