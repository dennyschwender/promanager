# Bulk Player Import — Design Spec

**Date:** 2026-03-13
**Status:** Approved

---

## Overview

Add a bulk player import feature accessible from the Teams page. Users can either paste data copied from Excel into an interactive spreadsheet table, or upload a `.xlsx` / `.csv` file. Both paths feed the same server-side import logic.

---

## Entry Point

A "Import Players" button on the Teams list page (`/teams`) links to `/players/import?team_id=<id>`. The `team_id` query parameter establishes the **context team** — the team all imported players are assigned to by default.

---

## UI: Two-Tab Page (`GET /players/import`)

### Tab 1 — Paste / Edit (Jspreadsheet CE)

- Jspreadsheet CE (MIT, ~300KB) renders an editable spreadsheet.
- **Default columns:** `first_name`, `last_name`, `email`, `phone`, `team`
- **Add column** dropdown lists all remaining supported columns; user can add any.
- **Remove column** via right-click context menu (standard Jspreadsheet behaviour).
- The `team` column pre-fills every new row with the context team name.
- **Live client-side validation:**
  - `first_name` / `last_name` empty → cell background red
  - `date_of_birth` not parseable as a date → cell background red
  - `email` format invalid → cell background yellow (warning, non-blocking)
- On **"Import"** button click, table data is serialised to JSON and POSTed to `POST /players/import`.

### Tab 2 — Upload File

- Standard `<input type="file">` accepting `.xlsx` and `.csv`.
- On submit, POSTs to `POST /players/import` with `multipart/form-data`.
- No client-side preview — server parses and returns the result page directly.

---

## Supported Column Headers

Matching is **case-insensitive**. Unknown columns are silently ignored.

| Header | Model field | Required |
|---|---|---|
| `first_name` | `Player.first_name` | Yes |
| `last_name` | `Player.last_name` | Yes |
| `email` | `Player.email` | No |
| `phone` | `Player.phone` | No |
| `sex` | `Player.sex` | No |
| `date_of_birth` | `Player.date_of_birth` | No |
| `street` | `Player.street` | No |
| `postcode` | `Player.postcode` | No |
| `city` | `Player.city` | No |
| `team` | `PlayerTeam` (name lookup) | No |

---

## Server-Side Import Logic (`services/import_service.py`)

### `process_rows(rows, context_team_id, db) -> ImportResult`

Each row is processed independently:

1. **Required field check** — skip row if `first_name` or `last_name` is blank; add to skipped list with reason "missing required field".
2. **Duplicate detection** — match by `email` (if present) or `first_name` + `last_name`:
   - If a match is found → skip row, reason: "duplicate".
3. **Team resolution** — if `team` column present:
   - Look up team by name (case-insensitive).
   - If not found → assign to context team, reason: "team not found: X, assigned to Y" (warning, player still imported).
   - If no `team` column → assign to context team silently.
4. **Date parsing** — `date_of_birth` parsed as `YYYY-MM-DD`, `DD/MM/YYYY`, or `DD.MM.YYYY`. If unparseable → skip row, reason: "invalid date_of_birth".
5. **Create** `Player` + `PlayerTeam` record (role=`player`, membership_status=`active`, priority=1).

### `ImportResult`

```python
@dataclass
class ImportResult:
    imported: list[Player]
    skipped: list[dict]   # {row: int, name: str, reason: str}
```

### File Parsing

- **CSV:** Python built-in `csv.DictReader` — first row as headers.
- **XLSX:** `openpyxl` — first row as headers, remaining rows as data.

`openpyxl` is added to `requirements.txt`.

---

## Route (`routes/players.py` addition)

```
GET  /players/import?team_id=<id>   — render import page
POST /players/import?team_id=<id>   — process paste JSON or file upload
```

Both require `require_admin` auth guard (same as create/edit/delete player).

POST returns the same import page with an `ImportResult` rendered below the tabs.

---

## Result Display

After import, a summary section appears below the tabs:

- **Success banner:** "X players imported successfully." (collapsible list of names)
- **Warnings table** (if any skipped rows): columns — Row, Name, Reason.

---

## Static Assets

Jspreadsheet CE downloaded and self-hosted:
- `static/js/jspreadsheet.min.js`
- `static/js/jsuites.min.js` (required peer)
- `static/css/jspreadsheet.min.css`
- `static/css/jsuites.min.css`

Loaded only on the import page via `{% block scripts %}`.

---

## Tests (`tests/test_import.py`)

- Valid rows → players created and assigned to context team
- Duplicate by email → skipped, correct reason
- Duplicate by name (no email) → skipped
- Unknown team name → player created, assigned to context team, warning in skipped
- Missing `first_name` or `last_name` → row skipped
- Unknown columns ignored
- CSV file parsed correctly
- XLSX file parsed correctly
- `team` column absent → all players assigned to context team

Import service tested directly (no HTTP layer) for speed.

---

## Files Created / Modified

| File | Change |
|---|---|
| `services/import_service.py` | New — all parsing and import logic |
| `routes/players.py` | Add `GET/POST /players/import` endpoints |
| `templates/players/import.html` | New — two-tab import page |
| `templates/teams/list.html` | Add "Import Players" button per row |
| `requirements.txt` | Add `openpyxl` |
| `static/js/jspreadsheet.min.js` | New (self-hosted) |
| `static/js/jsuites.min.js` | New (self-hosted) |
| `static/css/jspreadsheet.min.css` | New (self-hosted) |
| `static/css/jsuites.min.css` | New (self-hosted) |
| `tests/test_import.py` | New — import service tests |
