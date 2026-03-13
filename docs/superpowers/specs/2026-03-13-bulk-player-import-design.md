# Bulk Player Import — Design Spec

**Date:** 2026-03-13
**Status:** Approved

---

## Overview

Add a bulk player import feature accessible from the Teams page. Users can either paste data copied from Excel into an interactive spreadsheet table (Jspreadsheet CE), or upload a `.xlsx` / `.csv` file. Both paths converge at the same server-side import logic.

---

## Entry Point

An "Import Players" button on each row of the Teams list (`/teams`) links to `/players/import?team_id=<id>`. The `team_id` query parameter establishes the **context team** — the team all imported players are assigned to by default.

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
  - `email` format invalid (basic regex) → cell background yellow (warning, non-blocking)
- On **"Import"** button click, table data serialised to JSON is submitted via a hidden `<form>` POST (with `csrf_token` as a hidden input) to `POST /players/import`. This keeps CSRF handling identical to all other forms.
- If the POST returns errors, the page re-renders with Tab 1 active and a summary; the user must re-paste or re-enter data (no state restoration of the grid).

### Tab 2 — Upload File

- Standard `<input type="file">` accepting `.xlsx` and `.csv`, max **5 MB** (enforced server-side; client hint via `accept` attribute).
- Standard form POST (`multipart/form-data`) to `POST /players/import`.
- Server parses and returns the result page directly (no client-side preview).

### Distinguishing POST Sources

A hidden `<input name="import_source" value="paste|file">` field in each tab's form lets the route detect which path was used.

---

## Supported Column Headers

Matching is **case-insensitive**; whitespace is stripped. Unknown columns are silently ignored.

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

`position` and `shirt_number` are not imported; they default to `NULL` in `PlayerTeam`.

---

## Server-Side Import Logic (`services/import_service.py`)

### `process_rows(rows, context_team_id, db) -> ImportResult`

Processing is **best-effort per row**: each row is validated and committed independently. A failure on one row never affects others. Each row is processed as follows:

1. **Whitespace normalisation** — strip all string fields.
2. **Required field check** — skip row if `first_name` or `last_name` is blank; reason: "missing required field".
3. **Duplicate detection** — track seen keys across the batch and check against the database:
   - If row has a non-empty `email`: key is `email` (case-insensitive); match in DB by email.
   - Otherwise: key is `first_name + last_name` (case-insensitive); match in DB by both fields.
   - If key was already seen earlier in this batch → skip; reason: "duplicate (in batch)".
   - If key matches an existing DB player → skip; reason: "duplicate".
4. **Team resolution** — if `team` column is present and non-empty:
   - Look up team by name (case-insensitive); if multiple teams share a name, take the first.
   - If not found → assign to context team; reason: "team not found: X, assigned to Y" (warning; player still imported).
   - If `team` column is absent or blank → assign to context team silently.
5. **Date parsing** — `date_of_birth` accepted as `YYYY-MM-DD`, `DD/MM/YYYY`, or `DD.MM.YYYY`. Whitespace stripped before parsing. If unparseable or invalid (e.g. Feb 30) → skip row; reason: "invalid date_of_birth".
6. **Create** `Player` (`is_active=True`) + `PlayerTeam` (`role="player"`, `membership_status="active"`, `priority=1`, `absent_by_default=False`, remaining fields `NULL`) and **commit immediately** within a per-row `try/except`. If the commit raises a DB integrity error, roll back that row's savepoint, skip the row; reason: "db error".
7. Add successfully created player to `ImportResult.imported`; add skipped rows to `ImportResult.skipped`.

### `ImportResult`

```python
@dataclass
class ImportResult:
    imported: list[Player]
    skipped: list[dict]   # {"row": int, "name": str, "reason": str}
```

### File Parsing

- **CSV:** Python built-in `csv.DictReader` — first row as headers.
- **XLSX:** `openpyxl` (read-only mode) — first row as headers, remaining rows as data. Corrupt or unreadable files return a user-facing error (no 500).
- **File size:** reject files > 5 MB before parsing; return error message.
- **File type:** validate by extension and/or magic bytes; return error message if invalid.

`openpyxl` is added to `requirements.txt`.

---

## Route (`routes/players.py` additions)

```
GET  /players/import?team_id=<id>   — render import page (require_admin)
POST /players/import?team_id=<id>   — process paste or file upload (require_admin)
```

POST uses `import_source` form field to branch:
- `paste` → read `rows_json` hidden field, parse JSON, call `process_rows`.
- `file` → read uploaded file, parse CSV/XLSX, call `process_rows`.

**HTTP responses:**
- `200 OK` — page re-rendered with `ImportResult` summary below the tabs.
- `400 Bad Request` — file too large, wrong file type, or unparseable JSON; error shown inline.
- Auth failures handled by existing `require_admin` dependency (302 or 403).

---

## Result Display

After import, a summary section appears below the tabs:

- **Success banner:** "X players imported successfully." (collapsible list of names)
- **Warnings table** (if any skipped rows): columns — Row, Name, Reason.
- If zero rows were imported and all were skipped, display an error-style banner.

---

## Static Assets

Jspreadsheet CE and its peer library jsuites downloaded and self-hosted:
- `static/js/jspreadsheet.min.js`
- `static/js/jsuites.min.js`
- `static/css/jspreadsheet.min.css`
- `static/css/jsuites.min.css`

Loaded only on the import page via `{% block scripts %}` / `{% block head_extra %}`.

---

## Tests (`tests/test_import.py`)

Service-level tests (no HTTP) for speed:

- Valid rows → players created, assigned to context team, `is_active=True`
- Duplicate by email → skipped, correct reason
- Duplicate by name (no email) → skipped
- Two rows in same batch with same email → first imported, second skipped
- Unknown team name → player created, assigned to context team, warning in skipped
- Blank `team` column → player assigned to context team silently
- Missing `first_name` or `last_name` → row skipped
- Unknown columns ignored
- CSV file parsed correctly
- XLSX file parsed correctly
- Invalid `date_of_birth` → row skipped
- File > 5 MB → rejected before parsing

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
