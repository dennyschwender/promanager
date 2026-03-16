# Team / Season / Player Membership Refactor — Design Spec

## Goal

Decouple teams from seasons so that a team (e.g. "U21") persists across multiple seasons, while player–team assignments are scoped to a specific season. A player's membership is always a `(player, team, season)` triple.

---

## Context & Problem

Currently `Team` has a `season_id` FK, meaning each team belongs to exactly one season. `PlayerTeam` has no season context, so there is no way to represent "player X is in U21 for 2024/25 but not 2025/26". This forces admins to recreate teams every season and makes cross-season roster comparison impossible.

---

## Chosen Approach

**Option A — Minimal surgery on `PlayerTeam`.**

- Remove `season_id` from `Team` (teams become season-independent).
- Add `season_id` (NOT NULL) to `PlayerTeam` — the membership triple is `(player_id, team_id, season_id)`.
- All routes and services that touch rosters filter by the active (or selected) season.
- A "copy roster" action lets admins duplicate last season's memberships into a new season.

---

## Data Model

### `models/player_team.py`
- Add `season_id: Mapped[int]` — NOT NULL, FK → `seasons.id`, `ondelete="CASCADE"`
- Composite PK becomes `(player_id, team_id, season_id)`
- Rename unique constraint: `uq_player_team_season` on `(player_id, team_id, season_id)`
- Add `season: Mapped[Season]` relationship

### `models/team.py`
- Remove `season_id` field and FK
- Remove `season: Season | None` relationship

### `models/season.py`
- Remove `teams` back-reference

### `models/player.py`
- No field changes
- `teams` property (currently returns all memberships regardless of season) — routes will query `PlayerTeam` directly with explicit season filter instead of relying on this property

---

## Migration

Single Alembic migration, executed in this order:

1. Add `season_id` column to `player_teams` (nullable initially)
2. Populate `season_id` from the active season (`WHERE is_active = 1 LIMIT 1`) — **abort if no active season exists**
3. Set `season_id` NOT NULL, add FK + index
4. Drop `uq_player_team`, add `uq_player_team_season` on `(player_id, team_id, season_id)`
5. Drop FK, index, and `season_id` column from `teams`

---

## Routes & UI

### `routes/teams.py`
- Remove `season_id` form field from create/edit
- Remove seasons list from template context
- Team list removes season column

### `routes/players.py`
- Add `season_id: int | None` query param; default to active season
- Pass `seasons` list and `selected_season_id` to templates
- `_parse_team_memberships()` — include `season_id` per membership
- `_sync_memberships()` — scoped delete/create to `(player_id, season_id)` only; other seasons untouched
- Player list filters: `PlayerTeam.season_id == selected_season_id`

### `routes/seasons.py`
- New endpoint: `POST /seasons/{season_id}/copy-roster`
  - Form param: `source_season_id`
  - Duplicates all `PlayerTeam` rows from source → target season
  - Skips rows that already exist (upsert-safe)
  - Redirects to seasons list with flash message

### Templates
| Template | Change |
|---|---|
| `templates/teams/form.html` | Remove season field |
| `templates/teams/list.html` | Remove season column |
| `templates/players/list.html` | Add season selector dropdown (defaults to active season) |
| `templates/players/form.html` | Add season selector; team assignment table saves for selected season only |
| `templates/seasons/list.html` | Add "Copy roster from…" button + source season dropdown per season row |

---

## Attendance Service

### `services/attendance_service.py`

`ensure_attendance_records(db, event)`:
- Add `PlayerTeam.season_id == event.season_id` to the player fetch query
- If `event.season_id` is None, fall back to team-only filter (existing behaviour)

`_has_higher_prio_conflict(db, player, event)`:
- Add the same `season_id` filter so priority conflicts are season-scoped

No other changes.

---

## Testing

### Updates to existing tests
- Remove `season_id` from all team creation fixtures
- Add `season_id` to all `PlayerTeam` fixture rows

### New test cases
| File | Test |
|---|---|
| `tests/test_teams.py` | Team create/edit does not store `season_id` |
| `tests/test_players.py` | Player list filters by season; sync only touches target season |
| `tests/test_players.py` | Assigning player to team in season A leaves season B membership intact |
| `tests/test_seasons.py` | Copy-roster duplicates rows correctly; skips duplicates |
| `tests/test_seasons.py` | Copy-roster fails gracefully on empty source season |
| `tests/test_attendance.py` | `ensure_attendance_records` only includes players with matching `(team_id, season_id)` |

---

## Out of Scope

- No changes to events, attendance status, notifications, or reports
- No UI changes to the attendance marking page
- No bulk-delete of memberships by season
