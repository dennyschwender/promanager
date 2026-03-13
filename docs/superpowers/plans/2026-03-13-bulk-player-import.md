# Bulk Player Import — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bulk player import page accessible from the Teams list, supporting paste-from-Excel (Jspreadsheet CE) and file upload (CSV/XLSX).

**Architecture:** A new `services/import_service.py` holds all parsing and validation logic, called by two new route handlers added to `routes/players.py`. A new template `templates/players/import.html` renders the two-tab UI with Jspreadsheet CE self-hosted assets.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Jinja2, Jspreadsheet CE v10 (MIT, self-hosted), openpyxl, Python csv module.

**Spec:** `docs/superpowers/specs/2026-03-13-bulk-player-import-design.md`

---

## Chunk 1: Assets + Service

### Task 1: Download and self-host Jspreadsheet CE assets

**Files:**
- Create: `static/js/jspreadsheet.min.js`
- Create: `static/js/jsuites.min.js`
- Create: `static/css/jspreadsheet.min.css`
- Create: `static/css/jsuites.min.css`

- [ ] **Step 1: Download Jspreadsheet CE and jsuites assets**

```bash
curl -sL "https://cdn.jsdelivr.net/npm/jspreadsheet-ce@4.13.4/dist/index.min.js" \
  -o static/js/jspreadsheet.min.js
curl -sL "https://cdn.jsdelivr.net/npm/jsuites@5.12.2/dist/jsuites.min.js" \
  -o static/js/jsuites.min.js
curl -sL "https://cdn.jsdelivr.net/npm/jspreadsheet-ce@4.13.4/dist/jspreadsheet.min.css" \
  -o static/css/jspreadsheet.min.css
curl -sL "https://cdn.jsdelivr.net/npm/jsuites@5.12.2/dist/jsuites.min.css" \
  -o static/css/jsuites.min.css
echo "Sizes:"
wc -c static/js/jspreadsheet.min.js static/js/jsuites.min.js \
       static/css/jspreadsheet.min.css static/css/jsuites.min.css
```

Expected: four files all > 0 bytes.

- [ ] **Step 2: Install openpyxl**

```bash
.venv/bin/pip install openpyxl
```

- [ ] **Step 3: Add openpyxl to requirements.txt**

Edit `requirements.txt` — add after `itsdangerous==2.2.0`:

```
openpyxl>=3.1.0
```

- [ ] **Step 4: Commit assets and dependency**

```bash
git add static/js/jspreadsheet.min.js static/js/jsuites.min.js \
        static/css/jspreadsheet.min.css static/css/jsuites.min.css \
        requirements.txt
git commit -m "feat: self-host Jspreadsheet CE v4 + jsuites; add openpyxl dep"
```

---

### Task 2: Import service — core logic

**Files:**
- Create: `services/import_service.py`
- Create: `tests/test_import.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_import.py`:

```python
"""Tests for services/import_service.py."""
import io
import csv as csv_mod
from datetime import date

import pytest
from models.player import Player
from models.player_team import PlayerTeam
from models.team import Team
from services.import_service import ImportResult, parse_csv, parse_xlsx, process_rows


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def team(db):
    t = Team(name="Eagles")
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@pytest.fixture()
def other_team(db):
    t = Team(name="Hawks")
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


# ── process_rows ──────────────────────────────────────────────────────────────

def test_valid_rows_imported(db, team):
    rows = [{"first_name": "Alice", "last_name": "Smith"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 1
    assert len(result.skipped) == 0
    player = db.query(Player).filter(Player.first_name == "Alice").first()
    assert player is not None
    assert player.is_active is True
    membership = db.query(PlayerTeam).filter(PlayerTeam.player_id == player.id).first()
    assert membership is not None
    assert membership.team_id == team.id
    assert membership.role == "player"
    assert membership.membership_status == "active"
    assert membership.priority == 1
    assert membership.absent_by_default is False


def test_missing_first_name_skipped(db, team):
    rows = [{"first_name": "", "last_name": "Smith"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 0
    assert result.skipped[0]["reason"] == "missing required field"


def test_missing_last_name_skipped(db, team):
    rows = [{"first_name": "Alice", "last_name": "  "}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 0
    assert result.skipped[0]["reason"] == "missing required field"


def test_duplicate_by_email_skipped(db, team):
    existing = Player(first_name="Bob", last_name="Old", email="bob@test.com", is_active=True)
    db.add(existing)
    db.commit()
    rows = [{"first_name": "Bob", "last_name": "New", "email": "bob@test.com"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 0
    assert result.skipped[0]["reason"] == "duplicate"


def test_duplicate_by_name_skipped(db, team):
    existing = Player(first_name="Carol", last_name="Jones", is_active=True)
    db.add(existing)
    db.commit()
    rows = [{"first_name": "Carol", "last_name": "Jones"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 0
    assert result.skipped[0]["reason"] == "duplicate"


def test_duplicate_within_batch_skipped(db, team):
    rows = [
        {"first_name": "Dan", "last_name": "X", "email": "dan@test.com"},
        {"first_name": "Dan", "last_name": "Y", "email": "dan@test.com"},
    ]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 1
    assert result.skipped[0]["reason"] == "duplicate (in batch)"


def test_unknown_team_falls_back_to_context(db, team):
    rows = [{"first_name": "Eve", "last_name": "X", "team": "Nonexistent"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 1
    assert any("team not found" in s["reason"] for s in result.skipped)
    membership = db.query(PlayerTeam).join(Player).filter(Player.first_name == "Eve").first()
    assert membership.team_id == team.id


def test_blank_team_column_uses_context(db, team):
    rows = [{"first_name": "Frank", "last_name": "X", "team": ""}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 1
    assert len(result.skipped) == 0


def test_named_team_column_resolved(db, team, other_team):
    rows = [{"first_name": "Grace", "last_name": "X", "team": "hawks"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 1
    membership = db.query(PlayerTeam).join(Player).filter(Player.first_name == "Grace").first()
    assert membership.team_id == other_team.id


def test_unknown_columns_ignored(db, team):
    rows = [{"first_name": "Hank", "last_name": "X", "favourite_colour": "blue"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 1


def test_invalid_date_of_birth_skipped(db, team):
    rows = [{"first_name": "Iris", "last_name": "X", "date_of_birth": "not-a-date"}]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 0
    assert result.skipped[0]["reason"] == "invalid date_of_birth"


def test_valid_date_formats_accepted(db, team):
    rows = [
        {"first_name": "J1", "last_name": "X", "date_of_birth": "2000-06-15"},
        {"first_name": "J2", "last_name": "X", "date_of_birth": "15/06/2000"},
        {"first_name": "J3", "last_name": "X", "date_of_birth": "15.06.2000"},
    ]
    result = process_rows(rows, context_team_id=team.id, db=db)
    assert len(result.imported) == 3
    players = db.query(Player).filter(Player.last_name == "X").all()
    for p in players:
        if p.first_name.startswith("J"):
            assert p.date_of_birth == date(2000, 6, 15)


# ── parse_csv ─────────────────────────────────────────────────────────────────

def test_parse_csv_basic():
    content = b"first_name,last_name,email\nAlice,Smith,alice@test.com\n"
    rows = parse_csv(io.BytesIO(content))
    assert len(rows) == 1
    assert rows[0]["first_name"] == "Alice"
    assert rows[0]["email"] == "alice@test.com"


def test_parse_csv_unknown_columns_passed_through():
    content = b"first_name,last_name,foo\nAlice,Smith,bar\n"
    rows = parse_csv(io.BytesIO(content))
    assert rows[0]["foo"] == "bar"  # import_service ignores these later


def test_parse_csv_case_insensitive_headers():
    content = b"First_Name,Last_Name\nAlice,Smith\n"
    rows = parse_csv(io.BytesIO(content))
    assert rows[0]["first_name"] == "Alice"


# ── parse_xlsx ────────────────────────────────────────────────────────────────

def test_parse_xlsx_basic():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["first_name", "last_name", "email"])
    ws.append(["Bob", "Jones", "bob@test.com"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    rows = parse_xlsx(buf)
    assert len(rows) == 1
    assert rows[0]["first_name"] == "Bob"
    assert rows[0]["email"] == "bob@test.com"


def test_parse_xlsx_case_insensitive_headers():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["First_Name", "Last_Name"])
    ws.append(["Bob", "Jones"])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    rows = parse_xlsx(buf)
    assert rows[0]["first_name"] == "Bob"
```

- [ ] **Step 2: Run tests to confirm they all fail (import error)**

```bash
.venv/bin/pytest tests/test_import.py -v 2>&1 | head -30
```

Expected: `ImportError` — `services/import_service` not found.

- [ ] **Step 3: Implement `services/import_service.py`**

Create `services/import_service.py`:

```python
"""services/import_service.py — Bulk player import logic."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date
from typing import BinaryIO

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.player import Player
from models.player_team import PlayerTeam
from models.team import Team

# ── Supported column names (lower-cased) ──────────────────────────────────────
PLAYER_FIELDS = {
    "first_name", "last_name", "email", "phone",
    "sex", "date_of_birth", "street", "postcode", "city",
}


@dataclass
class ImportResult:
    imported: list[Player] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)  # {row, name, reason}


# ── Date parsing ──────────────────────────────────────────────────────────────

def _parse_date(value: str) -> date | None:
    """Return a date from YYYY-MM-DD, DD/MM/YYYY, or DD.MM.YYYY. Raise ValueError if invalid."""
    v = value.strip()
    if not v:
        return None
    # YYYY-MM-DD
    try:
        return date.fromisoformat(v)
    except ValueError:
        pass
    # DD/MM/YYYY or DD.MM.YYYY
    for sep in ("/", "."):
        parts = v.split(sep)
        if len(parts) == 3:
            try:
                day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
                return date(year, month, day)
            except (ValueError, TypeError):
                pass
    raise ValueError(f"Cannot parse date: {v!r}")


# ── File parsers ──────────────────────────────────────────────────────────────

def _normalise_headers(headers: list[str]) -> list[str]:
    return [h.strip().lower() for h in headers]


def parse_csv(stream: BinaryIO) -> list[dict]:
    """Parse a CSV stream; returns list of dicts with lower-cased header keys."""
    text = stream.read().decode("utf-8-sig")  # strip BOM if present
    reader = csv.DictReader(io.StringIO(text))
    rows = []
    for row in reader:
        rows.append({k.strip().lower(): (v or "").strip() for k, v in row.items()})
    return rows


def parse_xlsx(stream: BinaryIO) -> list[dict]:
    """Parse an XLSX stream; returns list of dicts with lower-cased header keys."""
    import openpyxl  # lazy import — only needed when xlsx is uploaded
    wb = openpyxl.load_workbook(stream, read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers = _normalise_headers([str(c) if c is not None else "" for c in next(rows_iter)])
    except StopIteration:
        return []
    result = []
    for row in rows_iter:
        result.append({
            headers[i]: str(cell).strip() if cell is not None else ""
            for i, cell in enumerate(row)
            if i < len(headers)
        })
    return result


# ── Core import logic ─────────────────────────────────────────────────────────

def process_rows(
    rows: list[dict],
    context_team_id: int,
    db: Session,
) -> ImportResult:
    """Process import rows best-effort (per-row independent commits)."""
    result = ImportResult()
    seen_keys: set[str] = set()

    # Pre-fetch all teams for name resolution (case-insensitive)
    all_teams = {t.name.lower(): t for t in db.query(Team).all()}

    for idx, raw in enumerate(rows, start=1):
        row = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
        first_name = row.get("first_name", "").strip()
        last_name = row.get("last_name", "").strip()
        display_name = f"{first_name} {last_name}".strip() or f"row {idx}"

        def skip(reason: str) -> None:
            result.skipped.append({"row": idx, "name": display_name, "reason": reason})

        # 1. Required fields
        if not first_name or not last_name:
            skip("missing required field")
            continue

        # 2. Duplicate detection
        email = row.get("email", "").strip().lower()
        batch_key = email if email else f"{first_name.lower()}|{last_name.lower()}"
        if batch_key in seen_keys:
            skip("duplicate (in batch)")
            continue

        if email:
            existing = db.query(Player).filter(
                Player.email.ilike(email)
            ).first()
        else:
            existing = db.query(Player).filter(
                Player.first_name.ilike(first_name),
                Player.last_name.ilike(last_name),
            ).first()

        if existing:
            skip("duplicate")
            continue

        # 3. Team resolution
        team_name = row.get("team", "").strip()
        resolved_team_id = context_team_id
        team_warning: str | None = None
        if team_name:
            matched = all_teams.get(team_name.lower())
            if matched:
                resolved_team_id = matched.id
            else:
                context_team = all_teams.get(
                    next((t.name for t in db.query(Team).filter(Team.id == context_team_id)), "").lower()
                )
                ctx_name = context_team.name if context_team else str(context_team_id)
                team_warning = f"team not found: {team_name}, assigned to {ctx_name}"

        # 4. Date parsing
        dob_raw = row.get("date_of_birth", "").strip()
        dob: date | None = None
        if dob_raw:
            try:
                dob = _parse_date(dob_raw)
            except ValueError:
                skip("invalid date_of_birth")
                continue

        # 5. Create player + membership within a savepoint
        try:
            sp = db.begin_nested()
            player = Player(
                first_name=first_name,
                last_name=last_name,
                email=row.get("email", "").strip() or None,
                phone=row.get("phone", "").strip() or None,
                sex=row.get("sex", "").strip() or None,
                date_of_birth=dob,
                street=row.get("street", "").strip() or None,
                postcode=row.get("postcode", "").strip() or None,
                city=row.get("city", "").strip() or None,
                is_active=True,
            )
            db.add(player)
            db.flush()

            db.add(PlayerTeam(
                player_id=player.id,
                team_id=resolved_team_id,
                priority=1,
                role="player",
                membership_status="active",
                absent_by_default=False,
            ))
            sp.commit()
        except IntegrityError:
            sp.rollback()
            skip("db error")
            continue

        seen_keys.add(batch_key)
        result.imported.append(player)
        if team_warning:
            result.skipped.append({"row": idx, "name": display_name, "reason": team_warning})

    db.commit()
    return result
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_import.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add services/import_service.py tests/test_import.py
git commit -m "feat: add import service with CSV/XLSX parsing and per-row best-effort logic"
```

---

## Chunk 2: Routes + Template + Entry Point

### Task 3: Add import routes to `routes/players.py`

**Files:**
- Modify: `routes/players.py` (add two new route handlers before `/{player_id}` catch-all)

- [ ] **Step 1: Add imports at the top of `routes/players.py`**

After the existing imports block, add:

```python
import json

from fastapi import Form, UploadFile, File
from fastapi.responses import HTMLResponse

from services.import_service import ImportResult, parse_csv, parse_xlsx, process_rows
```

- [ ] **Step 2: Add GET `/import` handler**

Add this block in `routes/players.py` **before** the `/{player_id}` route (to avoid path collision):

```python
# ---------------------------------------------------------------------------
# Bulk import
# ---------------------------------------------------------------------------

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB

IMPORT_COLUMNS = [
    "first_name", "last_name", "email", "phone",
    "sex", "date_of_birth", "street", "postcode", "city", "team",
]


@router.get("/import")
async def player_import_get(
    request: Request,
    team_id: int,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    context_team = db.get(Team, team_id)
    if context_team is None:
        return RedirectResponse("/teams", status_code=302)
    return templates.TemplateResponse(request, "players/import.html", {
        "user": user,
        "context_team": context_team,
        "columns": IMPORT_COLUMNS,
        "result": None,
        "error": None,
    })
```

- [ ] **Step 3: Add POST `/import` handler**

```python
@router.post("/import")
async def player_import_post(
    request: Request,
    team_id: int,
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    form = await request.form()
    context_team = db.get(Team, team_id)
    if context_team is None:
        return RedirectResponse("/teams", status_code=302)

    import_source = (form.get("import_source") or "").strip()
    error: str | None = None
    result: ImportResult | None = None

    def _render(status: int = 200):
        return templates.TemplateResponse(request, "players/import.html", {
            "user": user,
            "context_team": context_team,
            "columns": IMPORT_COLUMNS,
            "result": result,
            "error": error,
        }, status_code=status)

    if import_source == "paste":
        rows_json = (form.get("rows_json") or "").strip()
        try:
            rows = json.loads(rows_json)
            if not isinstance(rows, list):
                raise ValueError("expected list")
        except (json.JSONDecodeError, ValueError):
            error = "Invalid data submitted. Please try again."
            return _render(400)
        result = process_rows(rows, context_team_id=team_id, db=db)

    elif import_source == "file":
        upload: UploadFile | None = form.get("import_file")
        if upload is None or not upload.filename:
            error = "No file selected."
            return _render(400)

        content = await upload.read()
        if len(content) > MAX_UPLOAD_BYTES:
            error = "File too large. Maximum size is 5 MB."
            return _render(400)

        filename = upload.filename.lower()
        try:
            if filename.endswith(".csv"):
                rows = parse_csv(__import__("io").BytesIO(content))
            elif filename.endswith(".xlsx"):
                rows = parse_xlsx(__import__("io").BytesIO(content))
            else:
                error = "Unsupported file type. Please upload a .csv or .xlsx file."
                return _render(400)
        except Exception:
            error = "Could not read the file. Make sure it is a valid CSV or Excel file."
            return _render(400)

        result = process_rows(rows, context_team_id=team_id, db=db)

    else:
        error = "Invalid submission."
        return _render(400)

    return _render()
```

- [ ] **Step 4: Fix the `io` import — replace the `__import__("io")` calls**

The `__import__("io")` calls are a shortcut to avoid a conflict; add `import io` to the top of `routes/players.py` instead:

```python
import io
import json
```

Then replace `__import__("io").BytesIO(content)` with `io.BytesIO(content)` in both places.

- [ ] **Step 5: Run existing player tests to confirm nothing broke**

```bash
.venv/bin/pytest tests/test_players.py -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add routes/players.py
git commit -m "feat: add GET/POST /players/import route handlers"
```

---

### Task 4: Create the import template

**Files:**
- Create: `templates/players/import.html`

- [ ] **Step 1: Create `templates/players/import.html`**

```html
{% extends "base.html" %}
{% block title %}Import Players — ProManager{% endblock %}

{% block head_extra %}
<link rel="stylesheet" href="/static/css/jsuites.min.css">
<link rel="stylesheet" href="/static/css/jspreadsheet.min.css">
{% endblock %}

{% block breadcrumb %}
<nav class="breadcrumb">
  <a href="/dashboard">Home</a><span class="breadcrumb-sep"></span>
  <a href="/teams">Teams</a><span class="breadcrumb-sep"></span>
  <span>Import Players — {{ context_team.name }}</span>
</nav>
{% endblock %}

{% block content %}
<div class="page-header">
  <h2>Import Players into {{ context_team.name }}</h2>
</div>

{% if error %}
  <div class="alert alert-error">{{ error }}</div>
{% endif %}

{% if result %}
  {% if result.imported %}
    <details class="alert alert-success" style="margin-bottom:1rem;">
      <summary style="cursor:pointer;font-weight:600;">
        ✓ {{ result.imported|length }} player{{ 's' if result.imported|length != 1 else '' }} imported successfully
      </summary>
      <ul style="margin:.5rem 0 0 1rem;">
        {% for p in result.imported %}<li>{{ p.full_name }}</li>{% endfor %}
      </ul>
    </details>
  {% else %}
    <div class="alert alert-error">No players were imported.</div>
  {% endif %}

  {% set warnings = result.skipped | selectattr("reason", "ne", "duplicate") | selectattr("reason", "ne", "duplicate (in batch)") | selectattr("reason", "ne", "missing required field") | selectattr("reason", "ne", "invalid date_of_birth") | selectattr("reason", "ne", "db error") | list %}
  {% set errors = result.skipped | rejectattr("reason", "in", warnings | map(attribute="reason") | list) | list %}

  {% if result.skipped %}
    <div class="alert alert-warning" style="margin-bottom:1rem;">
      <strong>{{ result.skipped|length }} row{{ 's' if result.skipped|length != 1 else '' }} skipped or warned:</strong>
      <table style="margin-top:.5rem;width:100%;font-size:.88rem;">
        <thead><tr><th>Row</th><th>Name</th><th>Reason</th></tr></thead>
        <tbody>
          {% for s in result.skipped %}
            <tr>
              <td>{{ s.row }}</td>
              <td>{{ s.name }}</td>
              <td>{{ s.reason }}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  {% endif %}
{% endif %}

<!-- ── Tabs ─────────────────────────────────────────────────────────────── -->
<div class="import-tabs">
  <div class="tab-bar">
    <button class="tab-btn active" data-tab="paste">Paste from Excel</button>
    <button class="tab-btn" data-tab="file">Upload File</button>
  </div>

  <!-- Tab 1: Paste -->
  <div class="tab-panel" id="tab-paste">
    <p class="text-muted" style="margin:.75rem 0;">
      Paste rows copied from Excel, or type directly. Right-click a column header to remove it.
      Use the dropdown to add more columns.
    </p>

    <div style="display:flex;gap:.5rem;align-items:center;margin-bottom:.75rem;flex-wrap:wrap;">
      <select id="add-col-select" class="select-sm">
        <option value="">— Add column —</option>
        {% for col in columns %}<option value="{{ col }}">{{ col }}</option>{% endfor %}
      </select>
      <button type="button" class="btn btn-sm btn-outline" id="add-col-btn">Add</button>
    </div>

    <div id="spreadsheet"></div>

    <form method="post" action="/players/import?team_id={{ context_team.id }}"
          id="paste-form" style="margin-top:1rem;">
      <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
      <input type="hidden" name="import_source" value="paste">
      <input type="hidden" name="rows_json" id="rows-json-input">
      <button type="submit" class="btn btn-primary" id="paste-submit-btn">Import</button>
      <a href="/teams" class="btn btn-outline" style="margin-left:.5rem;">Cancel</a>
    </form>
  </div>

  <!-- Tab 2: File Upload -->
  <div class="tab-panel" id="tab-file" style="display:none;">
    <p class="text-muted" style="margin:.75rem 0;">
      Upload a <strong>.csv</strong> or <strong>.xlsx</strong> file (max 5 MB).
      The first row must be column headers matching the supported names
      (<code>first_name</code>, <code>last_name</code>, <code>email</code>, etc.).
      Unknown columns are ignored.
    </p>
    <form method="post" action="/players/import?team_id={{ context_team.id }}"
          enctype="multipart/form-data">
      <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
      <input type="hidden" name="import_source" value="file">
      <label>
        File
        <input type="file" name="import_file" accept=".csv,.xlsx" required>
      </label>
      <div class="form-footer">
        <button type="submit" class="btn btn-primary">Import</button>
        <a href="/teams" class="btn btn-outline">Cancel</a>
      </div>
    </form>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script src="/static/js/jsuites.min.js"></script>
<script src="/static/js/jspreadsheet.min.js"></script>
<script>
(function () {
  const CONTEXT_TEAM = {{ context_team.name | tojson }};
  const DEFAULT_COLS = ["first_name", "last_name", "email", "phone", "team"];
  const ALL_COLS = {{ columns | tojson }};

  // ── Tab switching ────────────────────────────────────────────────────────
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach(p => p.style.display = "none");
      btn.classList.add("active");
      document.getElementById("tab-" + btn.dataset.tab).style.display = "block";
    });
  });

  // ── Jspreadsheet setup ───────────────────────────────────────────────────
  let activeCols = [...DEFAULT_COLS];

  function makeColumns(cols) {
    return cols.map(c => ({ title: c, width: 130 }));
  }

  function makeInitialData(cols, rows = 20) {
    return Array.from({ length: rows }, () => {
      return cols.map(c => c === "team" ? CONTEXT_TEAM : "");
    });
  }

  const container = document.getElementById("spreadsheet");
  let sheet = jspreadsheet(container, {
    data: makeInitialData(activeCols),
    columns: makeColumns(activeCols),
    minDimensions: [activeCols.length, 20],
    allowInsertColumn: false,
    allowDeleteColumn: true,
    columnSorting: false,
    contextMenu: function(obj, x, y, e, items) {
      // Keep only the delete-column entry from the default context menu
      return items.filter(i => i && i.title && i.title.toLowerCase().includes("delete col"));
    },
    onchange: validateCell,
    ondeletecolumn: function(el, col) {
      activeCols.splice(col, 1);
    },
  });

  // ── Add column ────────────────────────────────────────────────────────────
  document.getElementById("add-col-btn").addEventListener("click", () => {
    const sel = document.getElementById("add-col-select");
    const col = sel.value;
    if (!col || activeCols.includes(col)) return;
    activeCols.push(col);
    sheet.insertColumn([], activeCols.length - 1, 1, [{ title: col, width: 130 }]);
    sel.value = "";
  });

  // ── Live validation ───────────────────────────────────────────────────────
  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const DATE_RE  = /^(\d{4}-\d{2}-\d{2}|\d{2}[\/\.]\d{2}[\/\.]\d{4})$/;

  function validateCell(el, cell, x, y, value) {
    const col = activeCols[parseInt(x)];
    const td = sheet.getCellFromCoords(x, y);
    if (!td) return;
    td.style.backgroundColor = "";

    if ((col === "first_name" || col === "last_name") && !value.trim()) {
      td.style.backgroundColor = "#fde8e8";
    } else if (col === "date_of_birth" && value.trim() && !DATE_RE.test(value.trim())) {
      td.style.backgroundColor = "#fde8e8";
    } else if (col === "email" && value.trim() && !EMAIL_RE.test(value.trim())) {
      td.style.backgroundColor = "#fff3cd";
    }
  }

  // ── Serialise to JSON on submit ───────────────────────────────────────────
  document.getElementById("paste-form").addEventListener("submit", function (e) {
    const data = sheet.getData();
    const rows = [];
    for (const rowVals of data) {
      const obj = {};
      let hasValue = false;
      activeCols.forEach((col, i) => {
        const v = (rowVals[i] || "").trim();
        obj[col] = v;
        if (v) hasValue = true;
      });
      if (hasValue) rows.push(obj);
    }
    if (rows.length === 0) {
      e.preventDefault();
      alert("No data to import. Please enter at least one row.");
      return;
    }
    document.getElementById("rows-json-input").value = JSON.stringify(rows);
  });
})();
</script>

<style>
.import-tabs { margin-top: 1rem; }
.tab-bar { display: flex; gap: 0; border-bottom: 2px solid var(--pico-muted-border-color, #e0e0e0); margin-bottom: 1rem; }
.tab-btn { background: none; border: none; border-bottom: 2px solid transparent; margin-bottom: -2px; padding: .5rem 1.25rem; font-size: .92rem; cursor: pointer; color: var(--tp-muted); font-weight: 500; }
.tab-btn.active { border-bottom-color: var(--tp-primary); color: var(--tp-primary); }
.tab-btn:hover { color: var(--tp-primary); }
</style>
{% endblock %}
```

- [ ] **Step 2: Add `{% block head_extra %}` hook to `templates/base.html`**

In `templates/base.html`, inside `<head>`, after the existing `<link>` tags add:

```html
  {% block head_extra %}{% endblock %}
```

- [ ] **Step 3: Smoke-test the page manually**

Visit `http://localhost:7000/teams`, click "Import Players" on a team (once the button exists — or navigate directly to `http://localhost:7000/players/import?team_id=1`). Confirm the page renders without errors.

- [ ] **Step 4: Commit**

```bash
git add templates/players/import.html templates/base.html
git commit -m "feat: add bulk import template with Jspreadsheet CE paste table and file upload tab"
```

---

### Task 5: Add "Import Players" button to teams list

**Files:**
- Modify: `templates/teams/list.html`

- [ ] **Step 1: Add the Import Players link**

In `templates/teams/list.html`, in the `action-group` div for each team, add the link after the "Players" link:

```html
<a href="/players/import?team_id={{ t.id }}" class="btn btn-sm btn-outline">Import Players</a>
```

Full updated actions block:

```html
<div class="action-group">
  {% if user.is_admin %}
    <a href="/teams/{{ t.id }}/edit" class="btn btn-sm btn-outline">Edit</a>
    <a href="/players?team_id={{ t.id }}" class="btn btn-sm btn-outline">Players</a>
    <a href="/players/import?team_id={{ t.id }}" class="btn btn-sm btn-outline">Import Players</a>
    <form method="post" action="/teams/{{ t.id }}/delete" style="display:contents;"
          onsubmit="return confirm('Delete team {{ t.name }}?')">
      <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
      <button type="submit" class="btn btn-sm btn-danger">Delete</button>
    </form>
  {% endif %}
</div>
```

- [ ] **Step 2: Run the full test suite**

```bash
.venv/bin/pytest -v
```

Expected: all 56 existing tests + all new import tests pass.

- [ ] **Step 3: Commit and push**

```bash
git add templates/teams/list.html
git commit -m "feat: add Import Players button to teams list"
git push
```

---

## Done

All tasks complete. The feature is live at `/players/import?team_id=<id>`, accessible via the "Import Players" button on the Teams list.

**Manual smoke-test checklist:**
- [ ] Teams list shows "Import Players" button per row
- [ ] Import page loads with Jspreadsheet table (default cols: first_name, last_name, email, phone, team)
- [ ] `team` column pre-fills with context team name
- [ ] Pasting from Excel fills the grid correctly
- [ ] Red highlight on empty first_name/last_name; yellow on bad email
- [ ] "Add column" dropdown adds a new column
- [ ] Paste import creates players and shows summary
- [ ] File tab: CSV upload imports players
- [ ] File tab: XLSX upload imports players
- [ ] Duplicate rows show in the skipped table
- [ ] File > 5 MB shows error message
