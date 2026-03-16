# Players Bulk Edit / Column Select Table — Design Spec

## Goal

Replace the static players list with an interactive table that supports column visibility toggles, inline editing of individual cells, row selection with checkboxes, and bulk actions (assign to team, set active/inactive, save multi-row edits at once).

---

## 1. Overall Layout

The `/players` page retains its existing season + team filter row. Above the table, two buttons are added to the right of the page header:

- **Columns** — opens a checklist popover to toggle column visibility
- **Edit** — enters edit mode (label changes to **Cancel** while active)

A **Save changes** button appears in edit mode only, next to Cancel.

The filter row, table, and pagination (if added later) remain unchanged structurally.

The CSRF token is exposed to JavaScript via a `<meta name="csrf-token" content="{{ request.state.csrf_token }}">` tag in the template `<head>`. The JS reads it with `document.querySelector('meta[name="csrf-token"]').content`.

---

## 2. Column Visibility

There are 12 columns available. **Name** is always visible and pinned left (not toggleable). The remaining 11 are:

| Column | DB field | Notes |
|---|---|---|
| Team | PlayerTeam | Read-only; not inline-editable |
| Email | Player.email | |
| Phone | Player.phone | |
| Date of birth | Player.date_of_birth | |
| Active | Player.is_active | |
| Shirt number | PlayerTeam.shirt_number | Requires season + team filter |
| Position | PlayerTeam.position | Requires season + team filter |
| Injured until | PlayerTeam.injured_until | Requires season + team filter |
| Absent by default | PlayerTeam.absent_by_default | Requires season + team filter |
| Priority | PlayerTeam.priority | Requires season + team filter |
| Actions | — | Edit / Delete / Report links |

`PlayerTeam.role` and `PlayerTeam.membership_status` are intentionally excluded from this feature; they remain editable on the individual player edit page.

The **Columns** button opens a small dropdown popover with a checkbox per column. Checking/unchecking immediately shows/hides the column. Selections are persisted to `localStorage` under the key `promanager_player_columns` (per-browser, not server-synced — intentional). Restored on page load. Parse errors or unrecognised keys in localStorage fall back silently to the default visible set: Name, Team, Email, Active, Actions.

**PlayerTeam columns** require **both a season filter and a team filter** to be set. When either is missing, these columns display "—" and inputs are disabled (tooltip: "Select a season and team to edit this field.").

The "Filter by team" dropdown lists only teams that have at least one `PlayerTeam` row in the currently selected season. When the season filter is "All Seasons," all teams in the DB are shown. If no teams exist for the selected season, the dropdown shows a "No teams available" placeholder.

When both season and team filters are set, each player row shows the `PlayerTeam` row for that `(player_id, team_id, season_id)` combination, or "—" if none exists. If the user edits a PlayerTeam field for a player who has no existing `PlayerTeam` row for that `(player_id, team_id, season_id)`, the backend **creates** the row (upsert semantics) on save.

---

## 3. Edit Mode — Inline Inputs

Clicking **Edit** turns every editable cell in every visible row into an inline input. Input types per column:

| Column | Input type | Constraints |
|---|---|---|
| Email | `<input type="email">` | Optional |
| Phone | `<input type="tel">` | Optional |
| Date of birth | `<input type="date">` | Optional |
| Active | `<input type="checkbox">` | |
| Shirt number | `<input type="number" min="0">` | 0 is a valid shirt number; requires season + team filter |
| Position | `<input type="text" maxlength="32">` | Free text; no enum enforced; requires season + team filter |
| Injured until | `<input type="date">` | Requires season + team filter |
| Absent by default | `<input type="checkbox">` | Requires season + team filter |
| Priority | `<input type="number" min="1">` | ≥ 1, no maximum; requires season + team filter |

When a cell value is changed from its original value, the cell background turns yellow (`#fff9c4`). **Team** is not inline-editable.

**Cancel** discards all pending changes and exits edit mode without a server call.

---

## 4. Row Selection & Bulk Action Toolbar

Each row has a checkbox on its far left. A master checkbox in the column header selects/deselects all currently visible (filtered) rows.

When 1 or more rows are checked, a toolbar appears between the filter row and the table:

```
[ N rows selected ]  [ Assign to team ▾ ]  [ Set active ]  [ Set inactive ]  [ Clear selection ]
```

The toolbar is hidden when no rows are checked.

- **Assign to team**: dropdown listing teams scoped to the selected season (same as the filter dropdown). Disabled with tooltip "Select a season first" when season is "All Seasons". Triggers `POST /players/bulk-assign`.
- **Set active / Set inactive**: bulk-toggles `Player.is_active` via `POST /players/bulk-update`.
- **Clear selection**: unchecks all rows.

Row selection and edit mode are independent — both can be active simultaneously.

When a bulk-assign completes while edit mode is active, pending unsaved edits for reassigned players are discarded. The page performs a **full page reload** (with current filter params preserved in the URL) to refresh row data.

---

## 5. Bulk Assign to Team with Age Filter

An optional **"Filter by age"** toggle above the Assign dropdown expands to two date inputs:

- **Born after** (date, inclusive)
- **Born before** (date, inclusive)

Every date change recalculates checkboxes from scratch (prior manual adjustments are discarded): rows whose `date_of_birth` falls within the range are checked; rows outside are unchecked. Rows with no `date_of_birth` are always unchecked when any age filter is active. The toolbar's "N rows selected" count updates immediately to reflect the new checkbox state.

The bulk assign POST:
```json
POST /players/bulk-assign
X-CSRF-Token: <token>
Content-Type: application/json

{ "player_ids": [1, 2, 3], "team_id": 5, "season_id": 2 }
```

The backend does not validate team-season association — any team can be assigned to any season. This is intentional to support pre-season roster setup.

**Skip vs Error:**
- **Skipped**: a `PlayerTeam` row for `(player_id, team_id, season_id)` already exists — left unchanged.
- **Error**: DB error, invalid IDs, or other server-side failure.

Response:
```json
{ "assigned": 3, "skipped": 0, "errors": [] }
```

Result replaces any previous bulk-action banner above the table. The banner has a close (×) button; it does not auto-dismiss. Errors are shown in a collapsible list inside the banner.

---

## 6. Save / Partial Success

On **Save changes**:

1. Client-side diff: only changed rows are included.
2. If no team filter is set (editing only `Player` fields), the top-level `team_id` is omitted. The backend accepts a missing `team_id` when no player diff contains PlayerTeam fields; it must reject (400) any diff that includes PlayerTeam fields without a resolvable `team_id`.
3. JSON POST:
   ```json
   POST /players/bulk-update
   X-CSRF-Token: <token>
   Content-Type: application/json

   {
     "season_id": 2,
     "team_id": 5,
     "players": [
       { "id": 12, "email": "new@example.com", "is_active": true },
       { "id": 17, "shirt_number": 9 }
     ]
   }
   ```
4. Server processes each player independently; failures do not block others.
5. Shirt number uniqueness is enforced in application logic per `(team_id, season_id)`, **excluding the current `player_id`** from the uniqueness scan (so submitting an unchanged shirt number does not self-conflict).
6. Response (player IDs only; client treats submitted values as canonical for saved rows):
   ```json
   { "saved": [12], "errors": [{ "id": 17, "message": "Shirt number already taken in this team/season" }] }
   ```
7. Saved rows: yellow highlight removed; submitted values kept.
   Errored rows: background turns red (`#fde8e8`); inline error message to the right of the row.
8. Edit mode stays active after partial save.
9. Edit mode exits only when all rows saved with no errors. Clicking **Save changes** when there are no pending changes is a no-op (button can be visually disabled in this state).
10. Bulk-assign banner (above table) and bulk-update row errors can coexist. A new bulk action replaces the previous banner.

---

## Architecture

**Frontend:**
- `templates/players/list.html` — adds `<meta name="csrf-token">`, column toggle popover, edit mode controls, checkbox column, bulk toolbar
- `static/js/players-table.js` (new) — column visibility (localStorage), edit mode, change tracking, row selection, age filter logic, bulk-assign and bulk-update fetch calls

**Backend:**
- `routes/players.py` — two new endpoints:
  - `POST /players/bulk-update` — body `{ season_id?, team_id?, players: [{id, ...fields}] }`, returns `{ saved: [ids], errors: [{id, message}] }`
  - `POST /players/bulk-assign` — body `{ player_ids, team_id, season_id }`, returns `{ assigned, skipped, errors }`
- `app/csrf.py` — add `require_csrf_header` dependency that reads `X-CSRF-Token` header without touching the request body; existing `require_csrf` is unchanged

**No new models or migrations needed.**

---

## Error Handling

- PlayerTeam fields: disabled inputs with tooltip when season or team filter unset.
- Bulk-assign dropdown: disabled with tooltip when no season selected; "No teams available" placeholder when season has no teams.
- Missing `team_id` on bulk-update with PlayerTeam fields: 400 response.
- Network or 500 errors: show banner; no client state changed.
- localStorage parse errors: silently fall back to default column set.

---

## Testing

- Unit tests for `bulk_update` service: happy path, partial failure, missing player ID, shirt number conflict (excluding self), PlayerTeam fields without season/team returns 400.
- Unit tests for `bulk_assign` service: happy path, skip existing membership, invalid IDs.
- Integration tests via pytest httpx: admin required, `X-CSRF-Token` header required, correct response shape for both endpoints.
- No frontend tests.
