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
- Composite PK becomes `(player_id, team_id, season_id)` — requires `batch_alter_table` in migration (SQLite does not support `ALTER TABLE ... ADD PRIMARY KEY`)
- Drop old unique constraint `uq_player_team` (no replacement needed — the PK already enforces uniqueness on the triple)
- Add `season: Mapped[Season]` relationship (`back_populates="player_memberships"`)

### `models/team.py`
- Remove `season_id` field and FK
- Remove `season: Season | None` relationship
- Remove `players: list[Player]` direct relationship (back-populated via legacy `Player.team_id`) — this relationship returns players across all seasons after the refactor and must be removed. Callers should use `player_memberships` filtered by season instead.

### `models/season.py`
- Remove `teams: list[Team]` back-reference (was inverse of `Team.season_id`)
- Add `player_memberships: list[PlayerTeam]` relationship (`back_populates="season"`) — this is the new way to query "all players in a season"

### `models/player.py`
- No field changes
- `Player.team` (legacy direct relationship via `team_id`) — leave as-is; `team_id` column remains for now.
- **Remove `Player.teams` property** — currently returns `[m.team for m in self.team_memberships]` with no season filter. After the refactor this silently returns a cross-season union of teams, making it semantically incorrect. Remove the property entirely. Any caller must instead query `PlayerTeam` directly with an explicit `season_id` filter.

---

## Migration

Single Alembic migration using `batch_alter_table` (required for SQLite PK changes).

### Pre-flight check
Before running, validate that **exactly one** active season exists (`SELECT COUNT(*) FROM seasons WHERE is_active = 1`). If zero or more than one: raise `RuntimeError` with a clear message — migration aborts, no changes are made.

### `upgrade()` — executed in order

1. Add `season_id` column to `player_teams` (nullable initially)
2. Populate: `UPDATE player_teams SET season_id = (SELECT id FROM seasons WHERE is_active = 1)`
3. Use `batch_alter_table("player_teams")` to:
   - Drop old PK `(player_id, team_id)`
   - Drop unique constraint `uq_player_team`
   - Set `season_id` NOT NULL
   - Add FK `season_id` → `seasons.id` (ondelete=CASCADE)
   - Add new PK `(player_id, team_id, season_id)` — PK already enforces uniqueness; no separate unique constraint needed
   - Add index `ix_player_teams_season_id`
4. Use `batch_alter_table("teams")` to:
   - Drop FK on `season_id`
   - Drop index `ix_teams_season_id`
   - Drop column `season_id`

### `downgrade()` — intentionally not supported
This migration is **irreversible**. The `downgrade()` function raises `NotImplementedError("This migration cannot be reversed — season_id data on teams is permanently lost.")`. Document this prominently in the migration file header.

---

## Routes & UI

### `routes/teams.py`
- Remove `season_id` form field from create/edit
- Remove seasons list from template context
- Team list removes season column

### `routes/players.py`
- Add `season_id: int | None` query param; default to active season id (query `Season.is_active == True`)
- If no active season exists, pass `season_id=None` and show an info banner in the template prompting the admin to activate a season
- Pass `seasons` list and `selected_season_id` to templates
- `_parse_team_memberships()` — include `season_id` per membership (taken from the selected season, not per-team)
- `_sync_memberships()` — scoped delete/create: only delete `PlayerTeam` rows where `player_id == player.id AND season_id == selected_season_id`; other seasons' memberships are untouched
- Player list filters: `PlayerTeam.season_id == selected_season_id` (if None: show all players, no membership join)

### `routes/seasons.py`
- New endpoint: `POST /seasons/{season_id}/copy-roster` — **admin only** (`Depends(require_admin)`)
  - Form param: `source_season_id` (required)
  - Copies all `PlayerTeam` rows from source season to target season
  - Copied fields: `player_id`, `team_id`, `season_id` (new), `priority`, `role`, `position`, `shirt_number`, `membership_status`
  - Reset on copy: `injured_until = None`, `absent_by_default = False` (prior season injury/absence state is stale)
  - Server-side validation: if `source_season_id == season_id` (target), return 400 immediately — do not rely on UI dropdown exclusion alone
  - Skip rows where `(player_id, team_id, season_id)` already exists in target
  - Redirects to seasons list with flash message showing count of copied rows

### Templates
| Template | Change |
|---|---|
| `templates/teams/form.html` | Remove season field |
| `templates/teams/list.html` | Remove season column |
| `templates/players/list.html` | Add season selector dropdown (defaults to active season; shows all if none active) |
| `templates/players/form.html` | Add season selector at top; team assignment table saves for selected season only; if no active season show info banner |
| `templates/seasons/list.html` | Add "Copy roster from…" form per season row (admin only); source season dropdown excludes self |

---

## Attendance Service

### `services/attendance_service.py`

**`ensure_attendance_records(db, event)`:**
- Add `PlayerTeam.season_id == event.season_id` to the player fetch query
- If `event.season_id is None`: do **not** fall back to team-only query (that would return players from all seasons). Instead, create no attendance records and log a warning. Events without a season must be fixed by the admin before attendance can be tracked.

**`_has_higher_prio_conflict(db, player, event)`:**
- Add `PlayerTeam.season_id == event.season_id` to **both** internal queries: (1) the `my_pt` lookup that finds the player's own membership in the event's team, and (2) the `higher_team_ids` lookup that finds higher-priority teams. Both must be season-scoped to avoid mixing memberships from different seasons.
- If `event.season_id is None`: skip the conflict check and return `False` (no conflict assumed).

No other changes to the service.

---

## Testing

All tests use the existing in-memory SQLite fixture from `conftest.py`. All existing `PlayerTeam` fixture rows must be updated to include a `season_id`.

### Updates to existing tests
- Remove `season_id` from all team creation fixtures/assertions
- Add `season_id` to all `PlayerTeam` fixture rows

### New test cases
| File | Test |
|---|---|
| `tests/test_teams.py` | Team create/edit does not store or return `season_id` |
| `tests/test_players.py` | Player list filters by selected season |
| `tests/test_players.py` | Sync only deletes memberships for the target season; other seasons intact |
| `tests/test_players.py` | Assigning player to team in season A leaves season B membership intact |
| `tests/test_seasons.py` | Copy-roster duplicates correct fields; resets `injured_until` and `absent_by_default` |
| `tests/test_seasons.py` | Copy-roster skips existing `(player_id, team_id, season_id)` duplicates |
| `tests/test_seasons.py` | Copy-roster returns 403 for member role |
| `tests/test_seasons.py` | Copy-roster with `source_season_id == season_id` returns 400 |
| `tests/test_seasons.py` | Copy-roster with empty source season returns success with 0 rows copied |
| `tests/test_attendance.py` | `ensure_attendance_records` only includes players with matching `(team_id, season_id)` |
| `tests/test_attendance.py` | `ensure_attendance_records` with `event.season_id = None` creates no records |

> **Note:** Migration behaviour (pre-flight check, abort on zero/multiple active seasons) is not covered by automated tests. The pre-flight logic should be extracted into a testable helper function in the migration file.

---

## Out of Scope

- No changes to events, attendance status, notifications, or reports
- No UI changes to the attendance marking page
- No bulk-delete of memberships by season
- No removal of legacy `Player.team_id` field (left for a future cleanup)
