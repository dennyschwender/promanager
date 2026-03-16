# Players Bulk Edit / Column Select Table — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add column-visibility toggles, inline row editing, row selection with checkboxes, and bulk actions (assign to team, set active/inactive, multi-row save) to the `/players` page.

**Architecture:** Two new JSON POST endpoints (`/players/bulk-update`, `/players/bulk-assign`) are added to `routes/players.py` using a new header-based CSRF dependency. A standalone vanilla-JS module (`static/js/players-table.js`) drives all client-side state; the Jinja2 template is extended to embed the necessary HTML hooks and expose the CSRF token via a `<meta>` tag.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Jinja2, SQLite, vanilla JS, PicoCSS v1

---

## Chunk 1: Backend

### Task 1: Header-based CSRF dependency

**Files:**
- Modify: `app/csrf.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_csrf_header.py` (new)

Background: The existing `require_csrf` reads `request.form()` which corrupts a JSON body. We need a separate dependency for JSON endpoints that reads only the `X-CSRF-Token` request header.

- [ ] **Step 1: Write the failing test**

Create `tests/test_csrf_header.py`:

```python
"""Tests for the header-based CSRF dependency."""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.csrf import generate_csrf_token, require_csrf_header

app_test = FastAPI()


@app_test.post("/json-endpoint")
async def json_ep(_=Depends(require_csrf_header)):
    return {"ok": True}


SESSION_COOKIE = "abc123"
VALID_TOKEN = generate_csrf_token(SESSION_COOKIE)


def make_client():
    return TestClient(app_test, raise_server_exceptions=False)


def test_valid_header_passes():
    c = make_client()
    resp = c.post(
        "/json-endpoint",
        json={},
        headers={"X-CSRF-Token": VALID_TOKEN},
        cookies={"session_user_id": SESSION_COOKIE},
    )
    assert resp.status_code == 200


def test_missing_header_returns_403():
    c = make_client()
    resp = c.post(
        "/json-endpoint", json={}, cookies={"session_user_id": SESSION_COOKIE}
    )
    assert resp.status_code == 403


def test_wrong_token_returns_403():
    c = make_client()
    resp = c.post(
        "/json-endpoint",
        json={},
        headers={"X-CSRF-Token": "badtoken"},
        cookies={"session_user_id": SESSION_COOKIE},
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run test — expect FAIL (ImportError)**

```bash
pytest tests/test_csrf_header.py -v
```

Expected: `ImportError: cannot import name 'require_csrf_header'`

- [ ] **Step 3: Add `require_csrf_header` to `app/csrf.py`**

Add after the existing `require_csrf` function (end of file):

```python
async def require_csrf_header(request: Request) -> None:
    """FastAPI dependency: validate CSRF token from X-CSRF-Token header.

    Use this (not require_csrf) for JSON POST endpoints — it never reads
    request.form(), which would corrupt the JSON body.
    """
    token = request.headers.get("X-CSRF-Token", "")
    session_cookie = request.cookies.get(COOKIE_NAME, "")
    if not verify_csrf_token(token, session_cookie):
        raise HTTPException(
            status_code=403,
            detail="CSRF token invalid or missing.",
        )
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_csrf_header.py -v
```

Expected: 3 passed

- [ ] **Step 5: Update `tests/conftest.py`**

Two edits:

**Edit 1** — extend the existing CSRF import on line ~17 (the `from app.csrf import require_csrf` line):

```python
# Before:
from app.csrf import require_csrf  # noqa: E402

# After:
from app.csrf import require_csrf, require_csrf_header  # noqa: E402
```

**Edit 2** — inside the `client` fixture body, add exactly these two lines right after the existing `async def override_csrf(): pass` definition (do NOT rewrite the whole fixture — other fixtures in conftest.py like `admin_client` and `csrf_client` must be left untouched):

```python
    # ADD these two lines after "async def override_csrf(): pass"
    async def override_csrf_header():
        pass

    # ADD this line alongside the existing app.dependency_overrides assignments:
    app.dependency_overrides[require_csrf_header] = override_csrf_header
```

- [ ] **Step 6: Run full test suite — expect no regressions**

```bash
pytest -v
```

Expected: all existing tests still pass

- [ ] **Step 7: Commit**

```bash
git add app/csrf.py tests/conftest.py tests/test_csrf_header.py
git commit -m "feat: add require_csrf_header dependency for JSON endpoints"
```

---

### Task 2: `POST /players/bulk-assign` endpoint

**Files:**
- Modify: `routes/players.py`
- Test: `tests/test_players.py`

This endpoint creates `PlayerTeam` rows for a list of players in a given team+season, skipping any that already exist. Each row is inserted inside a SQLAlchemy savepoint (`begin_nested`) so a failure on one player does not roll back the others.

- [ ] **Step 1: Add `Season` to top-level imports in `tests/test_players.py`**

The file currently imports `Player`, `PlayerTeam`, `Team` at the top. Add `Season`:

```python
# Before (line 3-5):
from models.player import Player
from models.player_team import PlayerTeam
from models.team import Team

# After:
from models.player import Player
from models.player_team import PlayerTeam
from models.season import Season
from models.team import Team
```

- [ ] **Step 2: Write the failing tests**

Add to the bottom of `tests/test_players.py`:

```python
# ---------------------------------------------------------------------------
# Helpers (used by bulk-assign and bulk-update tests)
# ---------------------------------------------------------------------------

def _make_season(db, name="2025/26", is_active=True):
    s = Season(name=name, is_active=is_active)
    db.add(s)
    db.flush()
    return s


def _make_team(db, name="U21"):
    t = Team(name=name)
    db.add(t)
    db.flush()
    return t


def _make_player(db, first="Alice", last="Smith"):
    p = Player(first_name=first, last_name=last, is_active=True)
    db.add(p)
    db.flush()
    return p


# ---------------------------------------------------------------------------
# Bulk assign
# ---------------------------------------------------------------------------

def test_bulk_assign_creates_player_teams(admin_client, db):
    season = _make_season(db)
    team = _make_team(db)
    p1 = _make_player(db, "Alice", "A")
    p2 = _make_player(db, "Bob", "B")
    db.commit()

    resp = admin_client.post(
        "/players/bulk-assign",
        json={"player_ids": [p1.id, p2.id], "team_id": team.id, "season_id": season.id},
        headers={"X-CSRF-Token": "test"},  # overridden in fixture
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["assigned"] == 2
    assert data["skipped"] == 0
    assert data["errors"] == []
    rows = db.query(PlayerTeam).filter(PlayerTeam.team_id == team.id).all()
    assert len(rows) == 2


def test_bulk_assign_skips_existing(admin_client, db):
    season = _make_season(db)
    team = _make_team(db)
    p1 = _make_player(db, "Alice", "A")
    db.add(PlayerTeam(player_id=p1.id, team_id=team.id, season_id=season.id))
    db.commit()

    resp = admin_client.post(
        "/players/bulk-assign",
        json={"player_ids": [p1.id], "team_id": team.id, "season_id": season.id},
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["assigned"] == 0
    assert data["skipped"] == 1


def test_bulk_assign_requires_admin(client, db):
    resp = client.post(
        "/players/bulk-assign",
        json={"player_ids": [1], "team_id": 1, "season_id": 1},
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code in (302, 403)
```

- [ ] **Step 3: Run — expect FAIL (404)**

```bash
pytest tests/test_players.py::test_bulk_assign_creates_player_teams -v
```

Expected: FAIL (endpoint doesn't exist yet)

- [ ] **Step 4: Add imports to `routes/players.py`**

Extend the existing import lines:

```python
# Extend the fastapi import (currently: APIRouter, Depends, Request):
from fastapi import APIRouter, Depends, HTTPException, Request

# Extend the app.csrf import (currently: require_csrf):
from app.csrf import require_csrf, require_csrf_header

# Add new import after existing imports:
from pydantic import BaseModel
```

- [ ] **Step 5: Add `BulkAssignRequest` model and endpoint to `routes/players.py`**

Place after the existing helper functions and before the `@router.get("")` route:

```python
class BulkAssignRequest(BaseModel):
    player_ids: list[int]
    team_id: int
    season_id: int


@router.post("/bulk-assign")
async def player_bulk_assign(
    body: BulkAssignRequest,
    _user=Depends(require_admin),
    _csrf=Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    assigned = 0
    skipped = 0
    errors = []
    for pid in body.player_ids:
        existing = db.get(PlayerTeam, (pid, body.team_id, body.season_id))
        if existing:
            skipped += 1
            continue
        try:
            sp = db.begin_nested()  # savepoint — failure here won't roll back prior rows
            db.add(PlayerTeam(
                player_id=pid,
                team_id=body.team_id,
                season_id=body.season_id,
            ))
            sp.commit()
            assigned += 1
        except Exception as exc:
            sp.rollback()
            errors.append({"id": pid, "message": str(exc)})
    db.commit()
    return {"assigned": assigned, "skipped": skipped, "errors": errors}
```

- [ ] **Step 6: Run bulk-assign tests — expect PASS**

```bash
pytest tests/test_players.py -k "bulk_assign" -v
```

Expected: 3 passed

- [ ] **Step 7: Run full suite — expect no regressions**

```bash
pytest -v
```

- [ ] **Step 8: Commit**

```bash
git add routes/players.py tests/test_players.py
git commit -m "feat: add POST /players/bulk-assign endpoint"
```

---

### Task 3: `POST /players/bulk-update` endpoint

**Files:**
- Modify: `routes/players.py`
- Test: `tests/test_players.py`

This endpoint accepts a list of player diffs and updates `Player` and `PlayerTeam` fields independently per row. Each row uses a savepoint for true partial-success isolation.

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/test_players.py`:

```python
# ---------------------------------------------------------------------------
# Bulk update
# ---------------------------------------------------------------------------

def test_bulk_update_player_fields(admin_client, db):
    p = _make_player(db, "Alice", "Old")
    db.commit()

    resp = admin_client.post(
        "/players/bulk-update",
        json={"players": [{"id": p.id, "email": "alice@new.com", "is_active": False}]},
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert p.id in data["saved"]
    assert data["errors"] == []
    db.refresh(p)
    assert p.email == "alice@new.com"
    assert p.is_active is False


def test_bulk_update_player_team_fields(admin_client, db):
    season = _make_season(db)
    team = _make_team(db)
    p = _make_player(db, "Bob", "B")
    db.add(PlayerTeam(player_id=p.id, team_id=team.id, season_id=season.id, shirt_number=None))
    db.commit()

    resp = admin_client.post(
        "/players/bulk-update",
        json={
            "season_id": season.id,
            "team_id": team.id,
            "players": [{"id": p.id, "shirt_number": 7}],
        },
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert p.id in data["saved"]
    pt = db.get(PlayerTeam, (p.id, team.id, season.id))
    assert pt.shirt_number == 7


def test_bulk_update_creates_player_team_if_missing(admin_client, db):
    season = _make_season(db)
    team = _make_team(db)
    p = _make_player(db, "Carol", "C")
    db.commit()

    resp = admin_client.post(
        "/players/bulk-update",
        json={
            "season_id": season.id,
            "team_id": team.id,
            "players": [{"id": p.id, "position": "goalie"}],
        },
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 200
    pt = db.get(PlayerTeam, (p.id, team.id, season.id))
    assert pt is not None
    assert pt.position == "goalie"


def test_bulk_update_shirt_number_conflict(admin_client, db):
    season = _make_season(db)
    team = _make_team(db)
    p1 = _make_player(db, "Dan", "D")
    p2 = _make_player(db, "Eve", "E")
    db.add(PlayerTeam(player_id=p1.id, team_id=team.id, season_id=season.id, shirt_number=9))
    db.add(PlayerTeam(player_id=p2.id, team_id=team.id, season_id=season.id, shirt_number=None))
    db.commit()

    resp = admin_client.post(
        "/players/bulk-update",
        json={
            "season_id": season.id,
            "team_id": team.id,
            "players": [{"id": p2.id, "shirt_number": 9}],
        },
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert p2.id in [e["id"] for e in data["errors"]]
    assert data["saved"] == []


def test_bulk_update_shirt_number_self_conflict_ok(admin_client, db):
    """Submitting the unchanged shirt number for its owner must not conflict."""
    season = _make_season(db)
    team = _make_team(db)
    p = _make_player(db, "Fred", "F")
    db.add(PlayerTeam(player_id=p.id, team_id=team.id, season_id=season.id, shirt_number=5))
    db.commit()

    resp = admin_client.post(
        "/players/bulk-update",
        json={
            "season_id": season.id,
            "team_id": team.id,
            "players": [{"id": p.id, "shirt_number": 5, "position": "goalie"}],
        },
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert p.id in data["saved"]


def test_bulk_update_playerteam_fields_without_team_returns_400(admin_client, db):
    season = _make_season(db)
    p = _make_player(db, "Gail", "G")
    db.commit()

    resp = admin_client.post(
        "/players/bulk-update",
        json={
            "season_id": season.id,
            # team_id intentionally omitted
            "players": [{"id": p.id, "shirt_number": 3}],
        },
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 400


def test_bulk_update_partial_success(admin_client, db):
    season = _make_season(db)
    team = _make_team(db)
    p1 = _make_player(db, "Han", "H")
    p2 = _make_player(db, "Ida", "I")
    db.add(PlayerTeam(player_id=p1.id, team_id=team.id, season_id=season.id, shirt_number=1))
    db.add(PlayerTeam(player_id=p2.id, team_id=team.id, season_id=season.id, shirt_number=None))
    db.commit()

    resp = admin_client.post(
        "/players/bulk-update",
        json={
            "season_id": season.id,
            "team_id": team.id,
            "players": [
                {"id": p1.id, "email": "han@ok.com"},   # succeeds
                {"id": p2.id, "shirt_number": 1},       # conflicts with p1
            ],
        },
        headers={"X-CSRF-Token": "test"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert p1.id in data["saved"]
    assert p2.id in [e["id"] for e in data["errors"]]
```

- [ ] **Step 2: Run — expect FAIL (404)**

```bash
pytest tests/test_players.py -k "bulk_update" -v
```

- [ ] **Step 3: Implement `POST /players/bulk-update` in `routes/players.py`**

Add right after `player_bulk_assign`:

```python
# ── Allowed fields per model ───────────────────────────────────────────────
# All of these exist as mapped columns on Player (verified against models/player.py).
_PLAYER_FIELDS = frozenset({
    "email", "phone", "is_active", "date_of_birth",
    "sex", "street", "postcode", "city",
})
_PT_FIELDS = frozenset({
    "shirt_number", "position", "injured_until",
    "absent_by_default", "priority",
})


class PlayerDiff(BaseModel):
    id: int
    model_config = {"extra": "allow"}


class BulkUpdateRequest(BaseModel):
    players: list[PlayerDiff]
    season_id: int | None = None
    team_id: int | None = None


@router.post("/bulk-update")
async def player_bulk_update(
    body: BulkUpdateRequest,
    _user=Depends(require_admin),
    _csrf=Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    saved: list[int] = []
    errors: list[dict] = []

    # Reject early if PlayerTeam fields are present but team_id is missing
    pt_keys_present = any(
        bool(_PT_FIELDS & set((diff.model_extra or {}).keys()))
        for diff in body.players
    )
    if pt_keys_present and body.team_id is None:
        raise HTTPException(
            status_code=400,
            detail="team_id is required when updating PlayerTeam fields.",
        )

    for diff in body.players:
        extra = diff.model_extra or {}
        player_changes = {k: v for k, v in extra.items() if k in _PLAYER_FIELDS}
        pt_changes = {k: v for k, v in extra.items() if k in _PT_FIELDS}

        # ── Shirt number uniqueness check (exclude self) ──────────────────
        if "shirt_number" in pt_changes and pt_changes["shirt_number"] is not None:
            conflict = (
                db.query(PlayerTeam)
                .filter(
                    PlayerTeam.team_id == body.team_id,
                    PlayerTeam.season_id == body.season_id,
                    PlayerTeam.shirt_number == pt_changes["shirt_number"],
                    PlayerTeam.player_id != diff.id,
                )
                .first()
            )
            if conflict:
                errors.append({
                    "id": diff.id,
                    "message": (
                        f"Shirt number {pt_changes['shirt_number']} "
                        "already taken in this team/season."
                    ),
                })
                continue

        try:
            sp = db.begin_nested()  # savepoint — isolates this row from others

            player = db.get(Player, diff.id)
            if player is None:
                sp.rollback()
                errors.append({"id": diff.id, "message": "Player not found."})
                continue

            # Apply Player-level fields
            for field, value in player_changes.items():
                if field == "date_of_birth" and isinstance(value, str) and value:
                    try:
                        value = date.fromisoformat(value)
                    except ValueError:
                        value = None
                setattr(player, field, value)

            # Apply PlayerTeam fields (upsert)
            if pt_changes:
                pt = db.get(PlayerTeam, (diff.id, body.team_id, body.season_id))
                if pt is None:
                    pt = PlayerTeam(
                        player_id=diff.id,
                        team_id=body.team_id,
                        season_id=body.season_id,
                    )
                    db.add(pt)
                for field, value in pt_changes.items():
                    if field == "injured_until" and isinstance(value, str) and value:
                        try:
                            value = date.fromisoformat(value)
                        except ValueError:
                            value = None
                    setattr(pt, field, value)

            sp.commit()
            saved.append(diff.id)

        except Exception as exc:
            sp.rollback()
            errors.append({"id": diff.id, "message": str(exc)})

    db.commit()
    return {"saved": saved, "errors": errors}
```

- [ ] **Step 4: Run bulk-update tests — expect PASS**

```bash
pytest tests/test_players.py -k "bulk_update" -v
```

Expected: 7 passed

- [ ] **Step 5: Run full suite — no regressions**

```bash
pytest -v
```

- [ ] **Step 6: Commit**

```bash
git add routes/players.py tests/test_players.py
git commit -m "feat: add POST /players/bulk-update endpoint"
```

---

## Chunk 2: Frontend

### Task 4: Update `templates/players/list.html`

**Files:**
- Modify: `templates/players/list.html`

Add CSRF meta tag, checkbox column, Columns button, Edit/Save/Cancel controls, and bulk-action toolbar. All dynamic behaviour is driven by `players-table.js` (Task 5); this task only adds the static HTML structure.

- [ ] **Step 1: Read the current template in full**

Read `templates/players/list.html` before making any changes.

- [ ] **Step 2: Add `{% block head_extra %}` with CSRF meta tag**

Insert after line 1 (`{% extends "base.html" %}`):

```html
{% block head_extra %}
<meta name="csrf-token" content="{{ request.state.csrf_token }}">
{% endblock %}
```

- [ ] **Step 3: Replace the page-header block**

Replace:
```html
<div class="page-header">
  <h2>{{ t('players.title') }}</h2>
  {% if user.is_admin %}<a href="/players/new" class="btn btn-primary">{{ t('players.new') }}</a>{% endif %}
  {% if user.is_admin and selected_team_id %}<a href="/players/import?team_id={{ selected_team_id }}" class="btn btn-outline">{{ t('players.import') }}</a>{% endif %}
</div>
```

With:
```html
<div class="page-header">
  <h2>{{ t('players.title') }}</h2>
  <div style="display:flex;gap:.5rem;flex-wrap:wrap;align-items:center;">
    {% if user.is_admin %}<a href="/players/new" class="btn btn-primary">{{ t('players.new') }}</a>{% endif %}
    {% if user.is_admin and selected_team_id %}<a href="/players/import?team_id={{ selected_team_id }}" class="btn btn-outline">{{ t('players.import') }}</a>{% endif %}
    {% if user.is_admin %}
    <div style="position:relative;display:inline-block;">
      <button type="button" class="btn btn-outline" id="columns-btn">Columns ▾</button>
      <div id="columns-popover" style="display:none;position:absolute;right:0;top:2.2rem;background:var(--card-background-color,#fff);border:1px solid var(--muted-border-color,#ddd);border-radius:.4rem;padding:.75rem 1rem;min-width:180px;z-index:100;box-shadow:0 4px 16px rgba(0,0,0,.15);">
        {% for col in ["Team","Email","Phone","Date of birth","Active","Shirt number","Position","Injured until","Absent by default","Priority","Actions"] %}
        <label style="display:flex;align-items:center;gap:.5rem;margin-bottom:.35rem;cursor:pointer;">
          <input type="checkbox" class="col-toggle" data-col="{{ col }}" checked> {{ col }}
        </label>
        {% endfor %}
      </div>
    </div>
    <button type="button" class="btn btn-outline" id="edit-btn">Edit</button>
    <button type="button" class="btn btn-primary" id="save-btn" style="display:none;" disabled>Save changes</button>
    <button type="button" class="btn btn-outline" id="cancel-btn" style="display:none;">Cancel</button>
    {% endif %}
  </div>
</div>
```

- [ ] **Step 4: Add bulk-action toolbar and banner**

After the closing `</script>` of the existing `filterSubmit` script block, add:

```html
{% if user.is_admin %}
<div id="bulk-toolbar" style="display:none;align-items:center;gap:.5rem;flex-wrap:wrap;padding:.5rem 0;border-bottom:1px solid var(--muted-border-color,#ddd);margin-bottom:.5rem;">
  <span id="bulk-count" style="font-weight:600;"></span>
  <div style="position:relative;">
    <!-- assign-btn: disabled when selected_season_id is None (no seasons defined).
         The season filter has no "All Seasons" option, so selected_season_id is always
         set to the active or user-chosen season when any season exists. -->
    <button type="button" class="btn btn-sm btn-outline" id="assign-btn"
            {% if not selected_season_id %}disabled title="Select a season first"{% endif %}>
      Assign to team ▾
    </button>
    <select id="assign-team-select" style="display:none;position:absolute;top:2rem;left:0;min-width:160px;z-index:50;background:var(--card-background-color,#fff);border:1px solid var(--muted-border-color,#ddd);border-radius:.3rem;padding:.3rem;">
      {% for tm in teams %}
      <option value="{{ tm.id }}">{{ tm.name }}</option>
      {% endfor %}
      {% if not teams %}<option disabled>No teams available</option>{% endif %}
    </select>
  </div>
  <button type="button" class="btn btn-sm btn-outline" id="set-active-btn">Set active</button>
  <button type="button" class="btn btn-sm btn-outline" id="set-inactive-btn">Set inactive</button>
  <button type="button" class="btn btn-sm btn-outline" id="age-filter-toggle">Filter by age ▾</button>
  <div id="age-filter-panel" style="display:none;align-items:center;gap:.4rem;">
    <label style="font-size:.85rem;">Born after <input type="date" id="age-after" style="width:auto;"></label>
    <label style="font-size:.85rem;">Born before <input type="date" id="age-before" style="width:auto;"></label>
  </div>
  <button type="button" class="btn btn-sm btn-outline" id="clear-selection-btn">Clear selection</button>
</div>
<div id="bulk-banner" style="display:none;margin-bottom:.5rem;" role="alert"></div>
{% endif %}
```

- [ ] **Step 5: Replace the `{% if players %}` table block**

Replace the existing `{% if players %}...{% endif %}` block with:

```html
{% if players %}
<div style="overflow-x:auto;">
<table id="players-table">
  <thead>
    <tr>
      {% if user.is_admin %}<th style="width:2rem;"><input type="checkbox" id="select-all"></th>{% endif %}
      <th>{{ t('players.name') }}</th>
      <th data-col="Team">{{ t('players.team') }}</th>
      <th data-col="Email">{{ t('players.email') }}</th>
      <th data-col="Phone">Phone</th>
      <th data-col="Date of birth">Date of birth</th>
      <th data-col="Active">{{ t('players.active') }}</th>
      <th data-col="Shirt number">Shirt #</th>
      <th data-col="Position">Position</th>
      <th data-col="Injured until">Injured until</th>
      <th data-col="Absent by default">Absent by default</th>
      <th data-col="Priority">Priority</th>
      <th data-col="Actions">{{ t('players.actions') }}</th>
    </tr>
  </thead>
  <tbody>
  {% for p in players %}
    {% set pt = player_team_map.get(p.id) %}
    <tr data-player-id="{{ p.id }}"
        data-dob="{{ p.date_of_birth or '' }}">
      {% if user.is_admin %}<td><input type="checkbox" class="row-check"></td>{% endif %}
      <td><a href="/players/{{ p.id }}"><strong>{{ p.full_name }}</strong></a></td>
      <td data-col="Team">
        {% if p.team_memberships %}
          {% for m in p.team_memberships %}
            <span>{{ m.team.name if m.team else '?' }}</span>{% if not loop.last %}, {% endif %}
          {% endfor %}
        {% else %}—{% endif %}
      </td>
      <td data-col="Email" data-field="email" data-value="{{ p.email or '' }}">
        <span class="cell-view">{{ p.email or '—' }}</span>
        <input type="email" class="cell-input" style="display:none;" value="{{ p.email or '' }}" maxlength="128">
      </td>
      <td data-col="Phone" data-field="phone" data-value="{{ p.phone or '' }}">
        <span class="cell-view">{{ p.phone or '—' }}</span>
        <input type="tel" class="cell-input" style="display:none;" value="{{ p.phone or '' }}" maxlength="32">
      </td>
      <td data-col="Date of birth" data-field="date_of_birth" data-value="{{ p.date_of_birth or '' }}">
        <span class="cell-view">{{ p.date_of_birth or '—' }}</span>
        <input type="date" class="cell-input" style="display:none;" value="{{ p.date_of_birth or '' }}">
      </td>
      <td data-col="Active" data-field="is_active" data-value="{{ 'true' if p.is_active else 'false' }}">
        <span class="cell-view">{% if p.is_active %}<span class="badge badge-active">Active</span>{% else %}<span class="badge">Inactive</span>{% endif %}</span>
        <input type="checkbox" class="cell-input" style="display:none;" {% if p.is_active %}checked{% endif %}>
      </td>
      <td data-col="Shirt number" data-field="shirt_number" data-value="{{ pt.shirt_number if pt and pt.shirt_number is not none else '' }}">
        <span class="cell-view">{{ pt.shirt_number if pt and pt.shirt_number is not none else '—' }}</span>
        <input type="number" class="cell-input pt-field" style="display:none;" min="0"
               value="{{ pt.shirt_number if pt and pt.shirt_number is not none else '' }}"
               {% if not selected_season_id or not selected_team_id %}disabled title="Select a season and team to edit this field"{% endif %}>
      </td>
      <td data-col="Position" data-field="position" data-value="{{ pt.position or '' if pt else '' }}">
        <span class="cell-view">{{ pt.position or '—' if pt else '—' }}</span>
        <input type="text" class="cell-input pt-field" style="display:none;" maxlength="32"
               value="{{ pt.position or '' if pt else '' }}"
               {% if not selected_season_id or not selected_team_id %}disabled title="Select a season and team to edit this field"{% endif %}>
      </td>
      <td data-col="Injured until" data-field="injured_until" data-value="{{ pt.injured_until or '' if pt else '' }}">
        <span class="cell-view">{{ pt.injured_until or '—' if pt else '—' }}</span>
        <input type="date" class="cell-input pt-field" style="display:none;"
               value="{{ pt.injured_until or '' if pt else '' }}"
               {% if not selected_season_id or not selected_team_id %}disabled title="Select a season and team to edit this field"{% endif %}>
      </td>
      <td data-col="Absent by default" data-field="absent_by_default" data-value="{{ 'true' if pt and pt.absent_by_default else 'false' }}">
        <span class="cell-view">{{ 'Yes' if pt and pt.absent_by_default else '—' }}</span>
        <input type="checkbox" class="cell-input pt-field" style="display:none;"
               {% if pt and pt.absent_by_default %}checked{% endif %}
               {% if not selected_season_id or not selected_team_id %}disabled title="Select a season and team to edit this field"{% endif %}>
      </td>
      <td data-col="Priority" data-field="priority" data-value="{{ pt.priority if pt else '' }}">
        <span class="cell-view">{{ pt.priority if pt else '—' }}</span>
        <input type="number" class="cell-input pt-field" style="display:none;" min="1"
               value="{{ pt.priority if pt else '' }}"
               {% if not selected_season_id or not selected_team_id %}disabled title="Select a season and team to edit this field"{% endif %}>
      </td>
      <td data-col="Actions">
        <div class="action-group">
          {% if user.is_admin %}
            <a href="/players/{{ p.id }}/edit" class="btn btn-sm btn-outline">{{ t('players.edit') }}</a>
            <form method="post" action="/players/{{ p.id }}/delete" style="display:contents;"
                  onsubmit="return confirm('Delete {{ p.full_name }}?')">
              <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
              <button type="submit" class="btn btn-sm btn-danger">Delete</button>
            </form>
          {% endif %}
          <a href="/reports/player/{{ p.id }}" class="btn btn-sm btn-outline">Report</a>
        </div>
      </td>
    </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% else %}
  <p>{{ t('players.no_players') }}</p>
{% endif %}
```

- [ ] **Step 6: Add `PLAYERS_CONFIG` and script tag at the bottom**

Before `{% endblock %}`:

```html
{% if user.is_admin %}
<script>
  window.PLAYERS_CONFIG = {
    seasonId: {{ selected_season_id | tojson }},
    teamId: {{ selected_team_id | tojson }},
  };
</script>
<script src="/static/js/players-table.js"></script>
{% endif %}
```

- [ ] **Step 7: Update `players_list` in `routes/players.py` to pass `player_team_map`**

In the `players_list` function, after the existing `players` list is assembled and before the `return render(...)` call, add:

```python
# Build {player_id: PlayerTeam} for the template (requires both filters set)
player_team_map: dict = {}
if selected_season_id is not None and team_id is not None:
    pts = (
        db.query(PlayerTeam)
        .filter(
            PlayerTeam.season_id == selected_season_id,
            PlayerTeam.team_id == team_id,
            PlayerTeam.player_id.in_([p.id for p in players]),
        )
        .all()
    )
    player_team_map = {pt.player_id: pt for pt in pts}
```

Add `"player_team_map": player_team_map` to the template context dict.

- [ ] **Step 8: Create empty JS file to prevent 404**

```bash
touch /home/denny/Development/promanager/static/js/players-table.js
```

- [ ] **Step 9: Run existing player list test**

```bash
pytest tests/test_players.py::test_players_list -v
```

Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add templates/players/list.html routes/players.py static/js/players-table.js
git commit -m "feat: add bulk-edit HTML structure to players list template"
```

---

### Task 5: `static/js/players-table.js` — all client-side logic

**Files:**
- Modify: `static/js/players-table.js`

One file, one IIFE. Implements: column visibility (localStorage), edit mode (inline inputs, yellow highlight, save POST), row selection (checkboxes, select-all, toolbar), bulk-assign (with age filter), bulk set-active/inactive. All DOM manipulation uses safe methods (`textContent`, `createElement`) — no `innerHTML` with user-provided data.

- [ ] **Step 1: Write the full `static/js/players-table.js`**

```javascript
(function () {
  'use strict';

  // ── Constants ──────────────────────────────────────────────────────────────
  var LS_KEY = 'promanager_player_columns';
  var DEFAULT_COLS = ['Team', 'Email', 'Active', 'Actions'];
  var ALL_COLS = [
    'Team', 'Email', 'Phone', 'Date of birth', 'Active',
    'Shirt number', 'Position', 'Injured until', 'Absent by default',
    'Priority', 'Actions'
  ];

  var cfg = window.PLAYERS_CONFIG || {};

  // ── localStorage helpers ───────────────────────────────────────────────────
  function loadVisibleCols() {
    try {
      var raw = localStorage.getItem(LS_KEY);
      if (!raw) return DEFAULT_COLS.slice();
      var parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) return DEFAULT_COLS.slice();
      var valid = parsed.filter(function (c) { return ALL_COLS.indexOf(c) !== -1; });
      return valid.length ? valid : DEFAULT_COLS.slice();
    } catch (e) {
      return DEFAULT_COLS.slice();
    }
  }

  function saveVisibleCols(cols) {
    try { localStorage.setItem(LS_KEY, JSON.stringify(cols)); } catch (e) {}
  }

  // ── Column visibility ──────────────────────────────────────────────────────
  function applyColumnVisibility(visibleCols) {
    ALL_COLS.forEach(function (col) {
      var show = visibleCols.indexOf(col) !== -1;
      document.querySelectorAll('[data-col="' + col + '"]').forEach(function (el) {
        el.style.display = show ? '' : 'none';
      });
    });
  }

  function initColumnsPopover() {
    var btn = document.getElementById('columns-btn');
    var popover = document.getElementById('columns-popover');
    if (!btn || !popover) return;

    var visibleCols = loadVisibleCols();

    popover.querySelectorAll('.col-toggle').forEach(function (cb) {
      cb.checked = visibleCols.indexOf(cb.dataset.col) !== -1;
    });
    applyColumnVisibility(visibleCols);

    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      popover.style.display = popover.style.display === 'none' ? 'block' : 'none';
    });

    popover.addEventListener('change', function (e) {
      if (!e.target.classList.contains('col-toggle')) return;
      var col = e.target.dataset.col;
      if (e.target.checked) {
        if (visibleCols.indexOf(col) === -1) visibleCols.push(col);
      } else {
        visibleCols = visibleCols.filter(function (c) { return c !== col; });
      }
      saveVisibleCols(visibleCols);
      applyColumnVisibility(visibleCols);
    });

    document.addEventListener('click', function (e) {
      if (!popover.contains(e.target) && e.target !== btn) {
        popover.style.display = 'none';
      }
    });
  }

  // ── CSRF ───────────────────────────────────────────────────────────────────
  function getCsrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
  }

  // ── Banner (safe DOM — no innerHTML with user data) ────────────────────────
  function showBanner(type, message, errors) {
    var banner = document.getElementById('bulk-banner');
    if (!banner) return;

    while (banner.firstChild) banner.removeChild(banner.firstChild);

    var bg = type === 'error' ? '#fde8e8'
           : type === 'success' ? '#d4edda'
           : '#fff3cd';
    banner.style.cssText = 'display:block;padding:.75rem 1rem;border-radius:.35rem;background:' + bg + ';position:relative;';
    banner.appendChild(document.createTextNode(message));

    if (errors && errors.length) {
      var details = document.createElement('details');
      details.style.marginTop = '.5rem';
      var summary = document.createElement('summary');
      summary.textContent = errors.length + ' error(s)';
      details.appendChild(summary);
      var ul = document.createElement('ul');
      ul.style.cssText = 'margin:.25rem 0 0 1rem;';
      errors.forEach(function (err) {
        var li = document.createElement('li');
        li.textContent = 'Player ' + err.id + ': ' + err.message;
        ul.appendChild(li);
      });
      details.appendChild(ul);
      banner.appendChild(details);
    }

    var closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.textContent = '×';
    closeBtn.style.cssText = 'position:absolute;top:.5rem;right:.75rem;background:none;border:none;cursor:pointer;font-size:1rem;line-height:1;';
    closeBtn.addEventListener('click', function () { banner.style.display = 'none'; });
    banner.appendChild(closeBtn);
  }

  // ── Edit mode ──────────────────────────────────────────────────────────────
  var pendingChanges = {};

  function enterEditMode() {
    document.getElementById('edit-btn').style.display = 'none';
    document.getElementById('save-btn').style.display = '';
    document.getElementById('cancel-btn').style.display = '';
    document.querySelectorAll('#players-table tbody tr').forEach(function (row) {
      row.querySelectorAll('td[data-field]').forEach(function (cell) {
        cell.querySelector('.cell-view').style.display = 'none';
        var input = cell.querySelector('.cell-input');
        if (input) input.style.display = '';
      });
    });
  }

  function exitEditMode(discard) {
    document.getElementById('edit-btn').style.display = '';
    document.getElementById('save-btn').style.display = 'none';
    document.getElementById('cancel-btn').style.display = 'none';

    document.querySelectorAll('#players-table tbody tr').forEach(function (row) {
      row.querySelectorAll('td[data-field]').forEach(function (cell) {
        cell.querySelector('.cell-view').style.display = '';
        var input = cell.querySelector('.cell-input');
        if (input) {
          input.style.display = 'none';
          if (discard) {
            var orig = cell.dataset.value;
            if (input.type === 'checkbox') {
              input.checked = orig === 'true';
            } else {
              input.value = orig;
            }
            cell.style.backgroundColor = '';
          }
        }
      });
      var errSpan = row.querySelector('.row-error');
      if (errSpan) errSpan.remove();
    });
    if (discard) pendingChanges = {};
  }

  function trackCellChange(cell, input) {
    var pid = cell.closest('tr').dataset.playerId;
    var field = cell.dataset.field;
    var orig = cell.dataset.value;

    function onChange() {
      var newVal = input.type === 'checkbox'
        ? (input.checked ? 'true' : 'false')
        : input.value;
      var changed = newVal !== orig;
      cell.style.backgroundColor = changed ? '#fff9c4' : '';

      if (!pendingChanges[pid]) pendingChanges[pid] = {};
      if (changed) {
        pendingChanges[pid][field] = input.type === 'checkbox' ? input.checked : input.value;
      } else {
        delete pendingChanges[pid][field];
        if (Object.keys(pendingChanges[pid]).length === 0) delete pendingChanges[pid];
      }

      var saveBtn = document.getElementById('save-btn');
      if (saveBtn) saveBtn.disabled = Object.keys(pendingChanges).length === 0;
    }

    input.addEventListener('change', onChange);
    input.addEventListener('input', onChange);
  }

  function initEditMode() {
    var editBtn = document.getElementById('edit-btn');
    var saveBtn = document.getElementById('save-btn');
    var cancelBtn = document.getElementById('cancel-btn');
    if (!editBtn) return;

    editBtn.addEventListener('click', enterEditMode);
    cancelBtn.addEventListener('click', function () { exitEditMode(true); });

    document.querySelectorAll('#players-table tbody tr').forEach(function (row) {
      row.querySelectorAll('td[data-field]').forEach(function (cell) {
        var input = cell.querySelector('.cell-input');
        if (input) trackCellChange(cell, input);
      });
    });

    saveBtn.addEventListener('click', function () {
      if (Object.keys(pendingChanges).length === 0) return;
      doSave();
    });
  }

  function doSave() {
    var players = Object.keys(pendingChanges).map(function (pid) {
      return Object.assign({ id: parseInt(pid, 10) }, pendingChanges[pid]);
    });
    var body = { players: players };
    if (cfg.seasonId) body.season_id = cfg.seasonId;
    if (cfg.teamId) body.team_id = cfg.teamId;

    fetch('/players/bulk-update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
      body: JSON.stringify(body),
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      data.saved.forEach(function (pid) {
        var row = document.querySelector('#players-table tr[data-player-id="' + pid + '"]');
        if (!row) return;
        row.querySelectorAll('td[data-field]').forEach(function (cell) {
          cell.style.backgroundColor = '';
          var input = cell.querySelector('.cell-input');
          if (input) {
            cell.dataset.value = input.type === 'checkbox'
              ? (input.checked ? 'true' : 'false')
              : input.value;
          }
        });
        delete pendingChanges[pid];
      });

      data.errors.forEach(function (err) {
        var row = document.querySelector('#players-table tr[data-player-id="' + err.id + '"]');
        if (!row) return;
        row.querySelectorAll('td[data-field]').forEach(function (cell) {
          cell.style.backgroundColor = '#fde8e8';
        });
        var existing = row.querySelector('.row-error');
        if (existing) existing.remove();
        var span = document.createElement('span');
        span.className = 'row-error';
        span.style.cssText = 'color:#c00;font-size:.8rem;margin-left:.5rem;';
        span.textContent = err.message;
        row.querySelector('td:last-child').appendChild(span);
      });

      var saveBtn = document.getElementById('save-btn');
      if (saveBtn) saveBtn.disabled = Object.keys(pendingChanges).length === 0;
      if (data.errors.length === 0) exitEditMode(false);
    })
    .catch(function () {
      showBanner('error', 'Save failed — network error. Please try again.', null);
    });
  }

  // ── Row selection & bulk toolbar ───────────────────────────────────────────
  function getCheckedRows() {
    return Array.from(document.querySelectorAll('#players-table .row-check:checked'));
  }

  function updateToolbar() {
    var checked = getCheckedRows();
    var toolbar = document.getElementById('bulk-toolbar');
    var countEl = document.getElementById('bulk-count');
    if (!toolbar) return;
    toolbar.style.display = checked.length > 0 ? 'flex' : 'none';
    if (countEl) countEl.textContent = checked.length + ' row' + (checked.length !== 1 ? 's' : '') + ' selected';
  }

  function initBulkToolbar() {
    var selectAll = document.getElementById('select-all');
    if (!selectAll) return;

    selectAll.addEventListener('change', function () {
      document.querySelectorAll('#players-table .row-check').forEach(function (cb) {
        cb.checked = selectAll.checked;
      });
      updateToolbar();
    });

    document.querySelectorAll('#players-table .row-check').forEach(function (cb) {
      cb.addEventListener('change', function () {
        updateToolbar();
        var all = document.querySelectorAll('#players-table .row-check');
        var allChecked = Array.from(all).every(function (c) { return c.checked; });
        selectAll.checked = allChecked;
        selectAll.indeterminate = !allChecked && Array.from(all).some(function (c) { return c.checked; });
      });
    });

    var clearBtn = document.getElementById('clear-selection-btn');
    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        document.querySelectorAll('#players-table .row-check').forEach(function (cb) { cb.checked = false; });
        selectAll.checked = false;
        selectAll.indeterminate = false;
        updateToolbar();
      });
    }

    var setActiveBtn = document.getElementById('set-active-btn');
    var setInactiveBtn = document.getElementById('set-inactive-btn');
    if (setActiveBtn) setActiveBtn.addEventListener('click', function () { bulkSetActive(true); });
    if (setInactiveBtn) setInactiveBtn.addEventListener('click', function () { bulkSetActive(false); });

    // Assign to team dropdown
    var assignBtn = document.getElementById('assign-btn');
    var assignSelect = document.getElementById('assign-team-select');
    if (assignBtn && assignSelect) {
      assignBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        if (assignBtn.disabled) return;
        assignSelect.style.display = assignSelect.style.display === 'none' ? 'block' : 'none';
      });
      assignSelect.addEventListener('change', function () {
        var teamId = parseInt(assignSelect.value, 10);
        if (!teamId) return;
        assignSelect.value = '';
        assignSelect.style.display = 'none';
        bulkAssign(teamId);
      });
      document.addEventListener('click', function (e) {
        if (e.target !== assignBtn && e.target !== assignSelect) {
          assignSelect.style.display = 'none';
        }
      });
    }

    // Age filter
    var ageToggle = document.getElementById('age-filter-toggle');
    var agePanel = document.getElementById('age-filter-panel');
    if (ageToggle && agePanel) {
      ageToggle.addEventListener('click', function () {
        agePanel.style.display = agePanel.style.display === 'none' ? 'flex' : 'none';
      });
    }
    var ageAfter = document.getElementById('age-after');
    var ageBefore = document.getElementById('age-before');
    if (ageAfter) ageAfter.addEventListener('input', applyAgeFilter);
    if (ageBefore) ageBefore.addEventListener('input', applyAgeFilter);
  }

  function applyAgeFilter() {
    var ageAfter = document.getElementById('age-after');
    var ageBefore = document.getElementById('age-before');
    var after = ageAfter && ageAfter.value ? new Date(ageAfter.value) : null;
    var before = ageBefore && ageBefore.value ? new Date(ageBefore.value) : null;
    if (!after && !before) return;

    document.querySelectorAll('#players-table tbody tr').forEach(function (row) {
      var cb = row.querySelector('.row-check');
      if (!cb) return;
      var dob = row.dataset.dob;
      if (!dob) { cb.checked = false; return; }
      var d = new Date(dob);
      cb.checked = (!after || d >= after) && (!before || d <= before);
    });

    var selectAll = document.getElementById('select-all');
    if (selectAll) selectAll.indeterminate = true;
    updateToolbar();
  }

  function bulkSetActive(isActive) {
    var ids = getCheckedRows().map(function (cb) {
      return parseInt(cb.closest('tr').dataset.playerId, 10);
    });
    if (!ids.length) return;

    fetch('/players/bulk-update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
      body: JSON.stringify({ players: ids.map(function (id) { return { id: id, is_active: isActive }; }) }),
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var msg = data.saved.length + ' player(s) updated.';
      showBanner(
        data.errors.length ? 'warning' : 'success',
        data.errors.length ? msg + ' ' + data.errors.length + ' failed.' : msg,
        data.errors.length ? data.errors : null
      );
      if (data.saved.length) setTimeout(function () { location.reload(); }, 800);
    })
    .catch(function () { showBanner('error', 'Network error. Please try again.', null); });
  }

  function bulkAssign(teamId) {
    var ids = getCheckedRows().map(function (cb) {
      return parseInt(cb.closest('tr').dataset.playerId, 10);
    });
    if (!ids.length || !cfg.seasonId) return;

    fetch('/players/bulk-assign', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
      body: JSON.stringify({ player_ids: ids, team_id: teamId, season_id: cfg.seasonId }),
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var msg = data.assigned + ' assigned, ' + data.skipped + ' skipped.';
      showBanner(
        data.errors.length ? 'warning' : 'success',
        msg,
        data.errors.length ? data.errors : null
      );
      if (data.assigned > 0) setTimeout(function () { location.reload(); }, 800);
    })
    .catch(function () { showBanner('error', 'Network error. Please try again.', null); });
  }

  // ── Boot ───────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    initColumnsPopover();
    initEditMode();
    initBulkToolbar();
  });

})();
```

- [ ] **Step 2: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass

- [ ] **Step 3: Manual smoke test**

1. `/players` — no JS errors in console.
2. Columns popover: toggle a column → hides; reload → restored from localStorage.
3. Click Edit → inputs appear; change a value → yellow; Cancel → reverts.
4. Change a value → click Save → POST fires; on success edit mode exits.
5. Check a row → toolbar appears with count.
6. Select all → all rows checked; age filter → only matching rows checked, count updates.
7. Set active/inactive → banner appears, page reloads.
8. With a season selected, Assign to team → dropdown appears; pick team → POST fires, banner shows.

- [ ] **Step 4: Commit**

```bash
git add static/js/players-table.js
git commit -m "feat: players table JS — column visibility, edit mode, bulk actions"
```

---

## Summary of files changed

| File | Change |
|---|---|
| `app/csrf.py` | Add `require_csrf_header` dependency |
| `tests/conftest.py` | Override `require_csrf_header` in `client` fixture |
| `tests/test_csrf_header.py` | New: header CSRF tests |
| `routes/players.py` | Add `HTTPException` to fastapi imports; `require_csrf_header` to csrf imports; `BaseModel` from pydantic; `BulkAssignRequest`, `PlayerDiff`, `BulkUpdateRequest`, `_PLAYER_FIELDS`, `_PT_FIELDS`; `bulk-assign` and `bulk-update` endpoints; `player_team_map` in list context |
| `tests/test_players.py` | Add `Season` to top-level imports; new helper functions; bulk-assign (3) and bulk-update (7) tests |
| `templates/players/list.html` | CSRF meta tag, Columns popover, Edit/Save/Cancel, checkbox column, bulk toolbar, inline input/view pairs, `PLAYERS_CONFIG`, script tag |
| `static/js/players-table.js` | New: column visibility, edit mode, row selection, age filter, bulk-assign, bulk-update |
