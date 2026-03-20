# Player Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hard-delete with a soft-archive mechanism on players, add bulk activate/deactivate/archive/unarchive to the players list, and keep archived data accessible for historical reports.

**Architecture:** Add `archived_at` (nullable DateTime) to `Player`; all normal queries filter `archived_at IS NULL` by default; a new `?archived=` query param exposes archived/all views. Six new backend endpoints handle single and bulk archive/unarchive/activate/deactivate. The JS bulk toolbar becomes context-aware, showing actions based on the state of selected rows.

**Tech Stack:** FastAPI, SQLAlchemy 2.x (Mapped/mapped_column), Alembic, Jinja2, vanilla JS, pytest (in-memory SQLite)

---

## File Map

| File | Change |
|---|---|
| `models/player.py` | Add `archived_at` column |
| `alembic/versions/<hash>_add_archived_at_to_player.py` | Migration (auto-generated) |
| `routes/players.py` | Add 4 bulk endpoints, rename delete to archive, add unarchive, update list filter |
| `services/notification_service.py` | Exclude archived players from recipient resolution |
| `routes/attendance.py` | Exclude archived players from member attendance query |
| `routes/notifications.py` | Exclude archived players from player lookup |
| `routes/users.py` | Exclude archived players from bulk-create eligibility |
| `templates/players/list.html` | Archived filter select; bulk toolbar buttons; row data attrs; per-row actions |
| `static/js/players-table.js` | Context-aware toolbar visibility; archive/unarchive/activate/deactivate handlers |
| `services/import_service.py` | No change needed — dedup check already queries all players (including archived), which is correct |
| `tests/test_players_bulk_archive.py` | New test file (15 tests — 14 from spec + 1 model smoke test) |
| `tests/test_players.py` | Update delete test to archive |

---

## Route ordering note

**IMPORTANT for Task 4:** In `routes/players.py`, all `/bulk-*` routes (`/bulk-archive`, `/bulk-unarchive`, `/bulk-activate`, `/bulk-deactivate`) **must be registered before** any `/{player_id}/*` dynamic routes. FastAPI matches routes in registration order; if a `/{player_id}` route appears first, the string `"bulk-archive"` will be matched as a `player_id`, causing a 422 error. The existing code already follows this pattern (see `bulk-assign`, `bulk-remove`, `bulk-update` which precede `/{player_id}` routes). Place all new bulk endpoints in the same bulk section, not after the delete/archive single-player endpoints.

---

## Task 1: Add `archived_at` to Player model + migration

**Files:**
- Modify: `models/player.py`
- Create: `alembic/versions/<hash>_add_archived_at_to_player.py` (auto-generated)

- [ ] **Step 1: Write the failing test**

Create `tests/test_players_bulk_archive.py`:

```python
"""Tests for player archive functionality."""
from __future__ import annotations

import pytest
from models.player import Player


def test_player_has_archived_at_field(db):
    """Player model has an archived_at column defaulting to None."""
    p = Player(first_name="Arch", last_name="Test", is_active=True)
    db.add(p)
    db.commit()
    db.refresh(p)
    assert p.archived_at is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_players_bulk_archive.py::test_player_has_archived_at_field -v
```
Expected: `FAILED` — `AttributeError: archived_at`

- [ ] **Step 3: Add `archived_at` to `models/player.py`**

Add to the imports at the top of `models/player.py`:
```python
from datetime import date, datetime  # add datetime
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String  # add DateTime
```

Add the column after `is_active`:
```python
archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_players_bulk_archive.py::test_player_has_archived_at_field -v
```
Expected: `PASSED`

- [ ] **Step 5: Generate and apply the migration**

```bash
source .venv/bin/activate
.venv/bin/alembic revision --autogenerate -m "add_archived_at_to_player"
.venv/bin/alembic upgrade head
```
Expected: migration file created, upgrade completes with no errors.

- [ ] **Step 6: Commit**

```bash
git add models/player.py alembic/versions/
git commit -m "feat: add archived_at column to Player model"
```

---

## Task 2: Update `GET /players` to filter by `archived_at`

**Files:**
- Modify: `routes/players.py` (list endpoint only)
- Modify: `tests/test_players.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_players_bulk_archive.py`:

```python
def test_archived_filter_hides_archived_by_default(admin_client, db):
    """Default /players view excludes archived players."""
    from datetime import datetime, timezone
    p = Player(first_name="Hidden", last_name="Archived", is_active=True,
               archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    resp = admin_client.get("/players")
    assert resp.status_code == 200
    assert "Hidden" not in resp.text


def test_archived_filter_only(admin_client, db):
    """?archived=only shows only archived players."""
    from datetime import datetime, timezone
    active = Player(first_name="Active", last_name="Player", is_active=True)
    archived = Player(first_name="Gone", last_name="Player", is_active=True,
                      archived_at=datetime.now(timezone.utc))
    db.add_all([active, archived])
    db.commit()
    resp = admin_client.get("/players?archived=only")
    assert resp.status_code == 200
    assert "Gone" in resp.text
    assert "Active" not in resp.text


def test_archived_filter_all(admin_client, db):
    """?archived=all shows both active and archived players."""
    from datetime import datetime, timezone
    active = Player(first_name="Active", last_name="P", is_active=True)
    archived = Player(first_name="Gone", last_name="P", is_active=True,
                      archived_at=datetime.now(timezone.utc))
    db.add_all([active, archived])
    db.commit()
    resp = admin_client.get("/players?archived=all")
    assert resp.status_code == 200
    assert "Active" in resp.text
    assert "Gone" in resp.text
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_players_bulk_archive.py::test_archived_filter_hides_archived_by_default tests/test_players_bulk_archive.py::test_archived_filter_only tests/test_players_bulk_archive.py::test_archived_filter_all -v
```
Expected: all `FAILED`

- [ ] **Step 3: Update `players_list` in `routes/players.py`**

Change the function signature to accept the new param:

```python
@router.get("")
@router.get("/")
async def players_list(
    request: Request,
    team_id: int | None = None,
    season_id: int | None = None,
    archived: str | None = None,          # <-- add this
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
```

Apply the archived filter to the player query (after `q = db.query(Player)`):

```python
    q = db.query(Player)
    # Archive filter
    if archived == "only":
        q = q.filter(Player.archived_at.isnot(None))
    elif archived == "all":
        pass  # no filter
    else:
        q = q.filter(Player.archived_at.is_(None))  # default: active only
```

Pass `archived_filter` to the template context:
```python
    return render(
        request,
        "players/list.html",
        {
            ...
            "archived_filter": archived or "",   # <-- add
        },
    )
```

- [ ] **Step 4: Run the archive filter tests to verify they pass**

```bash
pytest tests/test_players_bulk_archive.py::test_archived_filter_hides_archived_by_default tests/test_players_bulk_archive.py::test_archived_filter_only tests/test_players_bulk_archive.py::test_archived_filter_all -v
```
Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add routes/players.py tests/test_players_bulk_archive.py
git commit -m "feat: add archived filter to GET /players"
```

---

## Task 3: Single-player archive and unarchive endpoints

**Files:**
- Modify: `routes/players.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_players_bulk_archive.py`:

```python
def test_single_player_archive(admin_client, db):
    """POST /players/{id}/archive sets archived_at."""
    p = Player(first_name="Solo", last_name="Archive", is_active=True)
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post(f"/players/{p.id}/archive", follow_redirects=False)
    assert resp.status_code == 302
    db.refresh(p)
    assert p.archived_at is not None


def test_single_player_unarchive(admin_client, db):
    """POST /players/{id}/unarchive clears archived_at."""
    from datetime import datetime, timezone
    p = Player(first_name="Solo", last_name="Unarchive", is_active=True,
               archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post(f"/players/{p.id}/unarchive", follow_redirects=False)
    assert resp.status_code == 302
    db.refresh(p)
    assert p.archived_at is None


def test_member_cannot_archive(member_client, db):
    """Non-admin gets 403 when trying to archive a player."""
    p = Player(first_name="Protected", last_name="Player", is_active=True)
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = member_client.post(f"/players/{p.id}/archive", follow_redirects=False)
    assert resp.status_code == 403


def test_member_cannot_unarchive(member_client, db):
    """Non-admin gets 403 when trying to unarchive a player."""
    from datetime import datetime, timezone
    p = Player(first_name="Protected", last_name="Player", is_active=True,
               archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = member_client.post(f"/players/{p.id}/unarchive", follow_redirects=False)
    assert resp.status_code == 403
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_players_bulk_archive.py::test_single_player_archive tests/test_players_bulk_archive.py::test_single_player_unarchive tests/test_players_bulk_archive.py::test_member_cannot_archive tests/test_players_bulk_archive.py::test_member_cannot_unarchive -v
```
Expected: all `FAILED`

- [ ] **Step 3: Replace the delete endpoint; add unarchive in `routes/players.py`**

Add `from datetime import datetime, timezone` to the imports at the top.

Replace the existing `# Delete` section at the bottom of the file:

```python
# ---------------------------------------------------------------------------
# Archive / Unarchive
# ---------------------------------------------------------------------------


@router.post("/{player_id}/archive")
async def player_archive(
    player_id: int,
    _user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    player = db.get(Player, player_id)
    if player:
        player.archived_at = datetime.now(timezone.utc)
        db.commit()
    return RedirectResponse("/players", status_code=302)


@router.post("/{player_id}/unarchive")
async def player_unarchive(
    player_id: int,
    _user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    player = db.get(Player, player_id)
    if player:
        player.archived_at = None
        db.commit()
    return RedirectResponse("/players", status_code=302)
```

- [ ] **Step 4: Update `tests/test_players.py` — rename delete test to use archive endpoint**

```python
def test_delete_player(admin_client, db):
    player = Player(first_name="Dave", last_name="Delete", is_active=True)
    db.add(player)
    db.commit()
    db.refresh(player)
    pid = player.id

    resp = admin_client.post(f"/players/{pid}/archive", follow_redirects=False)
    assert resp.status_code == 302
    db.refresh(player)
    assert player.archived_at is not None   # soft-archived, not gone
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_players_bulk_archive.py::test_single_player_archive tests/test_players_bulk_archive.py::test_single_player_unarchive tests/test_players_bulk_archive.py::test_member_cannot_archive tests/test_players_bulk_archive.py::test_member_cannot_unarchive tests/test_players.py::test_delete_player -v
```
Expected: all `PASSED`

- [ ] **Step 6: Commit**

```bash
git add routes/players.py tests/test_players_bulk_archive.py tests/test_players.py
git commit -m "feat: replace player hard-delete with archive/unarchive endpoints"
```

---

## Task 4: Bulk archive, unarchive, activate, deactivate endpoints

**Files:**
- Modify: `routes/players.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_players_bulk_archive.py`:

```python
def test_bulk_archive_sets_archived_at(admin_client, db):
    """bulk-archive sets archived_at on multiple players."""
    p1 = Player(first_name="Bulk1", last_name="A", is_active=True)
    p2 = Player(first_name="Bulk2", last_name="A", is_active=True)
    db.add_all([p1, p2])
    db.commit()
    db.refresh(p1)
    db.refresh(p2)
    resp = admin_client.post(
        "/players/bulk-archive",
        json={"player_ids": [p1.id, p2.id]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["archived"] == 2
    assert data["skipped"] == 0
    db.refresh(p1)
    db.refresh(p2)
    assert p1.archived_at is not None
    assert p2.archived_at is not None


def test_bulk_archive_skips_already_archived(admin_client, db):
    """bulk-archive skips players already archived."""
    from datetime import datetime, timezone
    p = Player(first_name="Already", last_name="Archived", is_active=True,
               archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post("/players/bulk-archive", json={"player_ids": [p.id]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["archived"] == 0
    assert data["skipped"] == 1


def test_bulk_unarchive_clears_archived_at(admin_client, db):
    """bulk-unarchive clears archived_at."""
    from datetime import datetime, timezone
    p = Player(first_name="Restore", last_name="Me", is_active=True,
               archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post("/players/bulk-unarchive", json={"player_ids": [p.id]})
    assert resp.status_code == 200
    assert resp.json()["unarchived"] == 1
    db.refresh(p)
    assert p.archived_at is None


def test_bulk_activate(admin_client, db):
    """bulk-activate sets is_active=True."""
    p = Player(first_name="Inactive", last_name="P", is_active=False)
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post("/players/bulk-activate", json={"player_ids": [p.id]})
    assert resp.status_code == 200
    assert resp.json()["activated"] == 1
    db.refresh(p)
    assert p.is_active is True


def test_bulk_deactivate(admin_client, db):
    """bulk-deactivate sets is_active=False."""
    p = Player(first_name="Active", last_name="P", is_active=True)
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post("/players/bulk-deactivate", json={"player_ids": [p.id]})
    assert resp.status_code == 200
    assert resp.json()["deactivated"] == 1
    db.refresh(p)
    assert p.is_active is False


def test_bulk_activate_skips_archived_players(admin_client, db):
    """bulk-activate skips archived players."""
    from datetime import datetime, timezone
    p = Player(first_name="Arch", last_name="Skip", is_active=False,
               archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post("/players/bulk-activate", json={"player_ids": [p.id]})
    assert resp.status_code == 200
    assert resp.json()["skipped"] == 1
    assert resp.json()["activated"] == 0


def test_bulk_deactivate_skips_archived_players(admin_client, db):
    """bulk-deactivate skips archived players."""
    from datetime import datetime, timezone
    p = Player(first_name="Arch", last_name="Skip2", is_active=True,
               archived_at=datetime.now(timezone.utc))
    db.add(p)
    db.commit()
    db.refresh(p)
    resp = admin_client.post("/players/bulk-deactivate", json={"player_ids": [p.id]})
    assert resp.status_code == 200
    assert resp.json()["skipped"] == 1
    assert resp.json()["deactivated"] == 0
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_players_bulk_archive.py -k "bulk_archive or bulk_unarchive or bulk_activate or bulk_deactivate" -v
```
Expected: all `FAILED` (404 on missing endpoints)

- [ ] **Step 3: Add the four bulk endpoints to `routes/players.py`**

Add this Pydantic model and the four endpoints in the bulk section (alongside `BulkAssignRequest`):

```python
class BulkPlayerIdsRequest(BaseModel):
    player_ids: list[int]


@router.post("/bulk-archive")
async def player_bulk_archive(
    body: BulkPlayerIdsRequest,
    _user: User = Depends(require_admin),
    _csrf=Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    archived = 0
    skipped = 0
    errors = []
    for pid in body.player_ids:
        player = db.get(Player, pid)
        if player is None:
            errors.append({"id": pid, "message": "Player not found."})
            continue
        if player.archived_at is not None:
            skipped += 1
            continue
        try:
            sp = db.begin_nested()
            player.archived_at = datetime.now(timezone.utc)
            sp.commit()
            archived += 1
        except Exception:
            sp.rollback()
            errors.append({"id": pid, "message": "Could not archive player."})
    db.commit()
    return {"archived": archived, "skipped": skipped, "errors": errors}


@router.post("/bulk-unarchive")
async def player_bulk_unarchive(
    body: BulkPlayerIdsRequest,
    _user: User = Depends(require_admin),
    _csrf=Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    unarchived = 0
    skipped = 0
    errors = []
    for pid in body.player_ids:
        player = db.get(Player, pid)
        if player is None:
            errors.append({"id": pid, "message": "Player not found."})
            continue
        if player.archived_at is None:
            skipped += 1
            continue
        try:
            sp = db.begin_nested()
            player.archived_at = None
            sp.commit()
            unarchived += 1
        except Exception:
            sp.rollback()
            errors.append({"id": pid, "message": "Could not unarchive player."})
    db.commit()
    return {"unarchived": unarchived, "skipped": skipped, "errors": errors}


@router.post("/bulk-activate")
async def player_bulk_activate(
    body: BulkPlayerIdsRequest,
    _user: User = Depends(require_admin),
    _csrf=Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    activated = 0
    skipped = 0
    errors = []
    for pid in body.player_ids:
        player = db.get(Player, pid)
        if player is None:
            errors.append({"id": pid, "message": "Player not found."})
            continue
        if player.is_active or player.archived_at is not None:
            skipped += 1
            continue
        try:
            sp = db.begin_nested()
            player.is_active = True
            sp.commit()
            activated += 1
        except Exception:
            sp.rollback()
            errors.append({"id": pid, "message": "Could not activate player."})
    db.commit()
    return {"activated": activated, "skipped": skipped, "errors": errors}


@router.post("/bulk-deactivate")
async def player_bulk_deactivate(
    body: BulkPlayerIdsRequest,
    _user: User = Depends(require_admin),
    _csrf=Depends(require_csrf_header),
    db: Session = Depends(get_db),
):
    deactivated = 0
    skipped = 0
    errors = []
    for pid in body.player_ids:
        player = db.get(Player, pid)
        if player is None:
            errors.append({"id": pid, "message": "Player not found."})
            continue
        if not player.is_active or player.archived_at is not None:
            skipped += 1
            continue
        try:
            sp = db.begin_nested()
            player.is_active = False
            sp.commit()
            deactivated += 1
        except Exception:
            sp.rollback()
            errors.append({"id": pid, "message": "Could not deactivate player."})
    db.commit()
    return {"deactivated": deactivated, "skipped": skipped, "errors": errors}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_players_bulk_archive.py -v
```
Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add routes/players.py tests/test_players_bulk_archive.py
git commit -m "feat: add bulk-archive, bulk-unarchive, bulk-activate, bulk-deactivate endpoints"
```

---

## Task 5: Exclude archived players from notification, attendance, and user routes

**Files:**
- Modify: `services/notification_service.py`
- Modify: `routes/attendance.py`
- Modify: `routes/notifications.py`
- Modify: `routes/users.py`
- No change: `services/import_service.py` — the email deduplication check at lines 126-135 intentionally queries **all** players including archived ones (prevents re-creating a record for an archived player with the same email/name). Do not add an archive filter here.
- No change: `services/attendance_service.py` — auto-creation queries `PlayerTeam`, not `Player` directly.

No new tests needed — defensive guards; existing tests continue to pass.

- [ ] **Step 1: `services/notification_service.py` — exclude archived players**

In `_resolve_players`, both branches currently filter `Player.is_active.is_(True)`. Add `Player.archived_at.is_(None)` to each:

```python
# In the team_id branch:
.filter(
    PlayerTeam.team_id == event.team_id,
    PlayerTeam.membership_status == "active",
    Player.is_active.is_(True),
    Player.archived_at.is_(None),   # <-- add
)
# In the else branch:
base_q = db.query(Player).filter(
    Player.is_active.is_(True),
    Player.archived_at.is_(None),   # <-- add
)
```

- [ ] **Step 2: `routes/attendance.py` — exclude archived players from member view**

On the member-view query at line 51 that fetches `Player` by `user_id`:
```python
my_players = db.query(Player).filter(
    Player.user_id == user.id,
    Player.archived_at.is_(None),   # <-- add
).all()
```
Note: attendance auto-creation uses `attendance_service.py` which queries `PlayerTeam`, not `Player` — no change needed there.

- [ ] **Step 3: `routes/notifications.py` — exclude archived players**

The helper `_get_linked_players` at lines 33-35 is the single query site used for all player lookups in this route. Update it:
```python
def _get_linked_players(user, db: Session) -> list[Player]:
    """Return all active Player rows linked to *user*."""
    return db.query(Player).filter(
        Player.user_id == user.id,
        Player.is_active.is_(True),
        Player.archived_at.is_(None),   # <-- add
    ).all()
```

- [ ] **Step 4: `routes/users.py` — exclude archived players from bulk-create**

In `bulk_create_get`, add to the base query filter (around line 62):
```python
Player.archived_at.is_(None),   # <-- add to existing filter
```

Also apply to the `no_email_q` query (around line 85):
```python
Player.archived_at.is_(None),   # <-- add
```

Apply the same two additions in `bulk_create_post` — find the identical `Player.is_active == True` query patterns and apply the same filter to both.

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add services/notification_service.py routes/attendance.py routes/notifications.py routes/users.py
git commit -m "fix: exclude archived players from notification, attendance, and user-creation queries"
```

---

## Task 6: Template — archived filter select + row data attributes + per-row actions

**Files:**
- Modify: `templates/players/list.html`

- [ ] **Step 1: Add the `archived` filter select to the filter bar**

In `templates/players/list.html`, find the `<form>` filter bar. Add after the Team `<label>` block:

```html
<label style="margin:0;">
  <span style="display:block;font-size:.78rem;color:var(--tp-muted,#6c757d);margin-bottom:.15rem;">Archived</span>
  <select name="archived" onchange="filterSubmit(this.form)" class="sel-inline">
    <option value="">Active only</option>
    <option value="only" {% if archived_filter == 'only' %}selected{% endif %}>Archived only</option>
    <option value="all" {% if archived_filter == 'all' %}selected{% endif %}>All</option>
  </select>
</label>
```

- [ ] **Step 2: Add `data-is-active` and `data-archived-at` to each `<tr>`**

Find the `<tr data-player-id="{{ p.id }}"` line and add:

```html
<tr data-player-id="{{ p.id }}"
    data-dob="{{ p.date_of_birth or '' }}"
    data-is-active="{{ 'true' if p.is_active else 'false' }}"
    data-archived-at="{{ p.archived_at.isoformat() if p.archived_at else '' }}">
```

- [ ] **Step 3: Update per-row Actions dropdown**

Replace the current Actions cell content:

```html
<td data-col="Actions">
  <div class="action-dropdown">
    <button type="button" class="btn btn-sm btn-outline action-dropdown-toggle" aria-haspopup="true">&#8943;</button>
    <div class="action-dropdown-menu">
      {% if user.is_admin %}
        <a href="/players/{{ p.id }}/edit">Edit</a>
        <a href="/reports/player/{{ p.id }}">Report</a>
        {% if p.is_active %}
          <button type="button" class="row-deactivate-btn" data-id="{{ p.id }}">Deactivate</button>
        {% else %}
          <button type="button" class="row-activate-btn" data-id="{{ p.id }}">Activate</button>
        {% endif %}
        {% if p.archived_at %}
          <form method="post" action="/players/{{ p.id }}/unarchive">
            <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
            <button type="submit">Unarchive</button>
          </form>
        {% else %}
          <button type="button" class="row-archive-btn danger"
                  data-id="{{ p.id }}"
                  data-name="{{ p.full_name | e }}"
                  data-dob="{{ p.date_of_birth or '' }}">Archive</button>
        {% endif %}
      {% else %}
        <a href="/reports/player/{{ p.id }}">Report</a>
      {% endif %}
    </div>
  </div>
</td>
```

- [ ] **Step 4: Add new bulk toolbar buttons**

In the `#bulk-toolbar` div, add after the Remove from team button, before the Clear selection button:

```html
<button type="button" class="btn btn-sm btn-outline" id="bulk-activate-btn"
        style="display:none;">Activate</button>
<button type="button" class="btn btn-sm btn-outline" id="bulk-deactivate-btn"
        style="display:none;">Deactivate</button>
<button type="button" class="btn btn-sm btn-outline" id="bulk-archive-btn"
        style="display:none;border-color:var(--tp-danger,#dc3545);color:var(--tp-danger,#dc3545);">Archive</button>
<button type="button" class="btn btn-sm btn-outline" id="bulk-unarchive-btn"
        style="display:none;border-color:var(--tp-danger,#dc3545);color:var(--tp-danger,#dc3545);">Unarchive</button>
```

- [ ] **Step 5: Add the archive confirmation dialog**

Before the closing `{% endblock %}`, add:

```html
<dialog id="archive-dialog">
  <article>
    <h3>Archive players?</h3>
    <p>The following players will be archived and hidden from day-to-day views:</p>
    <ul id="archive-dialog-list" style="margin:.5rem 0 1rem;padding-left:1.5rem;"></ul>
    <footer style="display:flex;gap:.5rem;justify-content:flex-end;">
      <button type="button" class="btn btn-outline" id="archive-dialog-cancel">Cancel</button>
      <button type="button" class="btn btn-danger" id="archive-dialog-confirm">Archive</button>
    </footer>
  </article>
</dialog>
```

- [ ] **Step 6: Smoke-test the page renders**

```bash
source .venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 7000
```
Visit `http://localhost:7000/players` — confirm the Archived filter appears, page loads cleanly.

- [ ] **Step 7: Commit**

```bash
git add templates/players/list.html
git commit -m "feat: add archived filter, row data attrs, and archive actions to players list template"
```

---

## Task 7: JavaScript — context-aware bulk toolbar + action handlers

**Files:**
- Modify: `static/js/players-table.js`

- [ ] **Step 1: Update `updateToolbar` to show/hide context-aware buttons**

Find `function updateToolbar()` and replace it entirely:

```javascript
function updateToolbar() {
  var checked = getCheckedRows();
  var toolbar = document.getElementById('bulk-toolbar');
  var countEl = document.getElementById('bulk-count');
  if (!toolbar) return;
  toolbar.style.display = checked.length > 0 ? 'flex' : 'none';
  if (countEl) countEl.textContent = checked.length + ' row' + (checked.length !== 1 ? 's' : '') + ' selected';

  var hasInactive = false, hasActive = false, hasNotArchived = false, hasArchived = false;
  checked.forEach(function (cb) {
    var row = cb.closest('tr');
    var isActive = row.dataset.isActive === 'true';
    var isArchived = !!row.dataset.archivedAt;
    if (!isArchived && !isActive) hasInactive = true;
    if (!isArchived && isActive)  hasActive   = true;
    if (!isArchived)              hasNotArchived = true;
    if (isArchived)               hasArchived  = true;
  });

  var activateBtn   = document.getElementById('bulk-activate-btn');
  var deactivateBtn = document.getElementById('bulk-deactivate-btn');
  var archiveBtn    = document.getElementById('bulk-archive-btn');
  var unarchiveBtn  = document.getElementById('bulk-unarchive-btn');
  if (activateBtn)   activateBtn.style.display   = hasInactive    ? '' : 'none';
  if (deactivateBtn) deactivateBtn.style.display = hasActive      ? '' : 'none';
  if (archiveBtn)    archiveBtn.style.display    = hasNotArchived ? '' : 'none';
  if (unarchiveBtn)  unarchiveBtn.style.display  = hasArchived    ? '' : 'none';
}
```

- [ ] **Step 2: Wire up bulk activate and deactivate in `initBulkToolbar`**

The existing `bulkSetActive` function uses the old `bulk-update` endpoint. Keep `bulkSetActive` in place (it is used by the inline edit mode elsewhere), but wire the new toolbar buttons to the dedicated endpoints.

Replace the existing `setActiveBtn` / `setInactiveBtn` wiring:
```javascript
// Remove these two lines:
//   if (setActiveBtn) setActiveBtn.addEventListener('click', function () { bulkSetActive(true); });
//   if (setInactiveBtn) setInactiveBtn.addEventListener('click', function () { bulkSetActive(false); });
```

Add inside `initBulkToolbar`:

```javascript
function bulkPost(url, ids, resultKey, reloadOnCount) {
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
    body: JSON.stringify({ player_ids: ids }),
  })
  .then(function (r) { return r.ok ? r.json() : r.json().then(function (e) { throw new Error(e.detail || 'Error'); }); })
  .then(function (data) {
    var count = data[resultKey] || 0;
    showBanner(data.errors && data.errors.length ? 'warning' : 'success',
      count + ' ' + resultKey + ', ' + (data.skipped || 0) + ' skipped.', null);
    if (count > 0) setTimeout(function () { location.reload(); }, 800);
  })
  .catch(function (err) { showBanner('error', (err && err.message) || 'Network error.', null); });
}

var bulkActivateBtn = document.getElementById('bulk-activate-btn');
if (bulkActivateBtn) {
  bulkActivateBtn.addEventListener('click', function () {
    var ids = getCheckedRows()
      .map(function (cb) { return cb.closest('tr'); })
      .filter(function (row) { return row.dataset.isActive === 'false' && !row.dataset.archivedAt; })
      .map(function (row) { return parseInt(row.dataset.playerId, 10); });
    if (ids.length) bulkPost('/players/bulk-activate', ids, 'activated', true);
  });
}

var bulkDeactivateBtn = document.getElementById('bulk-deactivate-btn');
if (bulkDeactivateBtn) {
  bulkDeactivateBtn.addEventListener('click', function () {
    var ids = getCheckedRows()
      .map(function (cb) { return cb.closest('tr'); })
      .filter(function (row) { return row.dataset.isActive === 'true' && !row.dataset.archivedAt; })
      .map(function (row) { return parseInt(row.dataset.playerId, 10); });
    if (ids.length) bulkPost('/players/bulk-deactivate', ids, 'deactivated', true);
  });
}

var bulkUnarchiveBtn = document.getElementById('bulk-unarchive-btn');
if (bulkUnarchiveBtn) {
  bulkUnarchiveBtn.addEventListener('click', function () {
    var ids = getCheckedRows()
      .map(function (cb) { return cb.closest('tr'); })
      .filter(function (row) { return !!row.dataset.archivedAt; })
      .map(function (row) { return parseInt(row.dataset.playerId, 10); });
    if (ids.length) bulkPost('/players/bulk-unarchive', ids, 'unarchived', true);
  });
}
```

- [ ] **Step 3: Add bulk archive button handler (with confirmation dialog)**

Inside `initBulkToolbar`:

```javascript
var bulkArchiveBtn = document.getElementById('bulk-archive-btn');
if (bulkArchiveBtn) {
  bulkArchiveBtn.addEventListener('click', function () {
    var rows = getCheckedRows()
      .map(function (cb) { return cb.closest('tr'); })
      .filter(function (row) { return !row.dataset.archivedAt; });
    if (!rows.length) return;
    openArchiveDialog(
      rows.map(function (row) {
        return {
          id: parseInt(row.dataset.playerId, 10),
          name: (row.querySelector('td:nth-child(2) a') || {}).textContent || 'Player',
          dob: row.dataset.dob || '',
        };
      })
    );
  });
}
```

- [ ] **Step 4: Add the shared `openArchiveDialog` helper and dialog wiring**

Add outside `initBulkToolbar` (at module level inside the IIFE):

```javascript
function openArchiveDialog(players) {
  var dialog = document.getElementById('archive-dialog');
  var list   = document.getElementById('archive-dialog-list');
  if (!dialog || !list) return;
  // Clear existing items safely
  while (list.firstChild) { list.removeChild(list.firstChild); }
  players.forEach(function (p) {
    var li = document.createElement('li');
    li.textContent = p.name.trim() + (p.dob ? '  (' + p.dob + ')' : '');
    list.appendChild(li);
  });
  dialog._pendingIds = players.map(function (p) { return p.id; });
  dialog.showModal();
}

var archiveDialog  = document.getElementById('archive-dialog');
var archiveConfirm = document.getElementById('archive-dialog-confirm');
var archiveCancel  = document.getElementById('archive-dialog-cancel');
if (archiveCancel && archiveDialog) {
  archiveCancel.addEventListener('click', function () { archiveDialog.close(); });
}
if (archiveConfirm && archiveDialog) {
  archiveConfirm.addEventListener('click', function () {
    var ids = archiveDialog._pendingIds || [];
    archiveDialog.close();
    if (!ids.length) return;
    bulkPost('/players/bulk-archive', ids, 'archived', true);
  });
}
```

**IMPORTANT:** `bulkPost` must be defined at module level (outside `initBulkToolbar`), not inside it. The `openArchiveDialog` confirm handler (added in Step 4) calls `bulkPost` from outside `initBulkToolbar`'s scope. If `bulkPost` is scoped inside the function, the confirm handler will get a `ReferenceError` at runtime. Define `bulkPost` before `initBulkToolbar` in the file.

- [ ] **Step 5: Add per-row archive/activate/deactivate delegated handlers**

Add outside `initBulkToolbar`:

```javascript
document.addEventListener('click', function (e) {
  var btn = e.target.closest('.row-archive-btn');
  if (!btn) return;
  openArchiveDialog([{
    id: parseInt(btn.dataset.id, 10),
    name: btn.dataset.name || 'Player',
    dob:  btn.dataset.dob  || '',
  }]);
});

document.addEventListener('click', function (e) {
  var btn = e.target.closest('.row-activate-btn');
  if (!btn) return;
  bulkPost('/players/bulk-activate', [parseInt(btn.dataset.id, 10)], 'activated', true);
});

document.addEventListener('click', function (e) {
  var btn = e.target.closest('.row-deactivate-btn');
  if (!btn) return;
  bulkPost('/players/bulk-deactivate', [parseInt(btn.dataset.id, 10)], 'deactivated', true);
});
```

- [ ] **Step 6: Run full test suite**

```bash
pytest -v
```
Expected: all tests pass

- [ ] **Step 7: Smoke-test in browser**

- Select a player row — verify Activate/Deactivate/Archive buttons appear based on their state
- Click Archive: confirm dialog lists the player name and DOB; after confirming, player disappears from the active list
- Switch to "Archived only" filter — player appears with Unarchive option
- Unarchive: player returns to active view

- [ ] **Step 8: Commit**

```bash
git add static/js/players-table.js
git commit -m "feat: context-aware bulk toolbar with archive, unarchive, activate, deactivate"
```

---

## Task 8: Final verification

- [ ] **Step 1: Run the full test suite with coverage**

```bash
pytest -v --cov
```
Expected: all tests pass, `tests/test_players_bulk_archive.py` shows 15 tests passing (14 from spec + 1 model smoke test added in Task 1)

- [ ] **Step 2: Run linter**

```bash
ruff check .
ruff format .
```
Fix any issues.

- [ ] **Step 3: Commit lint fixes if needed**

```bash
git add -A
git commit -m "chore: lint fixes for player archive feature"
```
Skip if there are no changes.
