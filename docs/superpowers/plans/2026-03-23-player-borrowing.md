# Player Borrowing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow coaches/admins to add a player from another team to a single event's attendance via a search dialog on the attendance page. Borrowed players are shown with a ⟳ tooltip indicating their home team.

**Architecture:** Add a `borrowed_from_team_id` nullable FK column to the `attendances` table (one Alembic migration). Add `GET /players/search` to `routes/players.py` for live player search. Add `POST /attendance/{event_id}/borrow` to `routes/attendance.py` to create the attendance row. Update the attendance mark template with a dialog and tooltip CSS.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Alembic, Jinja2 templates, Pico CSS, vanilla JS

---

## File Map

| File | Change |
|---|---|
| `alembic/versions/<new>.py` | New migration: add `borrowed_from_team_id` to `attendances` |
| `models/attendance.py` | Add `borrowed_from_team_id` column + `borrowed_from_team` relationship |
| `routes/players.py` | Add `GET /players/search` endpoint |
| `routes/attendance.py` | Add `POST /attendance/{event_id}/borrow` endpoint; update GET to eager-load borrow team |
| `templates/attendance/mark.html` | Add "Add borrowed player" button, dialog, tooltip indicator |
| `static/css/main.css` | Add `.borrow-icon` tooltip styles |
| `locales/en.json`, `it.json`, `fr.json`, `de.json` | Add `attendance.borrow_*` keys |
| `tests/test_attendance.py` | Add 4 tests |

---

## Task 1: Database migration and model update

**Files:**
- Create: `alembic/versions/<new>.py`
- Modify: `models/attendance.py`

- [ ] **Step 1: Generate the migration**

```bash
source .venv/bin/activate
.venv/bin/alembic revision --autogenerate -m "add_borrowed_from_team_id_to_attendance"
```

This creates a new file in `alembic/versions/`. Open it. Verify the `upgrade()` function looks like this (autogenerate may differ — adjust if needed):

```python
def upgrade() -> None:
    with op.batch_alter_table("attendances", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("borrowed_from_team_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_attendance_borrowed_team",
            "teams",
            ["borrowed_from_team_id"],
            ["id"],
            ondelete="SET NULL",
        )

def downgrade() -> None:
    with op.batch_alter_table("attendances", schema=None) as batch_op:
        batch_op.drop_constraint("fk_attendance_borrowed_team", type_="foreignkey")
        batch_op.drop_column("borrowed_from_team_id")
```

**Note:** SQLite (used in dev/tests) does not support dropping foreign key constraints. The downgrade will work in production (PostgreSQL) but may fail in SQLite — that is acceptable for this project.

- [ ] **Step 2: Update `models/attendance.py`**

Open `models/attendance.py`. Add the column and relationship. The full updated file:

```python
"""models/attendance.py — Attendance model."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from models.team import Team


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Attendance(Base):
    __tablename__ = "attendances"
    __table_args__ = (UniqueConstraint("event_id", "player_id", name="uq_attendance_event_player"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    player_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "present" | "absent" | "maybe" | "unknown"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")

    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    # NULL = not borrowed; non-NULL = borrowed from this team
    borrowed_from_team_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("teams.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    event: Mapped[Event] = relationship("Event", back_populates="attendances", lazy="select")
    player: Mapped[Player] = relationship("Player", back_populates="attendances", lazy="select")
    borrowed_from_team: Mapped[Team | None] = relationship(
        "Team", lazy="select", foreign_keys=[borrowed_from_team_id]
    )

    def __repr__(self) -> str:
        return f"<Attendance id={self.id} event_id={self.event_id} player_id={self.player_id} status={self.status!r}>"
```

- [ ] **Step 3: Run migration**

```bash
.venv/bin/alembic upgrade head
```

Expected: migration applies cleanly.

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/ models/attendance.py
git commit -m "feat: add borrowed_from_team_id column to attendances"
```

---

## Task 2: Write failing tests

**Files:**
- Modify: `tests/test_attendance.py`

- [ ] **Step 1: Add 4 tests at the bottom of `tests/test_attendance.py`**

```python
# ---------------------------------------------------------------------------
# Player borrowing
# ---------------------------------------------------------------------------


def _make_team_season(db):
    """Return (team, season) committed to db."""
    from models.season import Season
    from models.team import Team

    season = Season(name="Borrow Season", is_active=True)
    team = Team(name="Borrow Team")
    db.add_all([season, team])
    db.commit()
    return team, season


def test_borrow_creates_attendance_with_team(admin_client, db):
    """Borrowing an active player creates an Attendance row with borrowed_from_team_id set."""
    from models.player_team import PlayerTeam
    from models.team import Team

    team, season = _make_team_season(db)
    event = Event(
        title="Borrow Event",
        event_type="training",
        event_date=date(2026, 6, 1),
        team_id=team.id,
        season_id=season.id,
    )
    db.add(event)
    db.commit()

    other_team = Team(name="Other Team")
    db.add(other_team)
    db.flush()
    player = _make_player(db, "Guest", "Player")
    db.add(PlayerTeam(player_id=player.id, team_id=other_team.id, season_id=season.id, priority=1))
    db.commit()

    resp = admin_client.post(
        f"/attendance/{event.id}/borrow",
        data={"player_id": player.id},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["team_name"] == "Other Team"

    att = db.query(Attendance).filter(
        Attendance.event_id == event.id, Attendance.player_id == player.id
    ).first()
    assert att is not None
    assert att.borrowed_from_team_id == other_team.id
    assert att.status == "unknown"


def test_borrow_duplicate_rejected(admin_client, db):
    """Borrowing a player already attending returns already_attending error."""
    event = _make_event(db, title="Dup Event")
    player = _make_player(db, "Dup", "Player")
    db.add(Attendance(event_id=event.id, player_id=player.id, status="present"))
    db.commit()

    resp = admin_client.post(
        f"/attendance/{event.id}/borrow",
        data={"player_id": player.id},
        follow_redirects=False,
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["ok"] is False
    assert body["error"] == "already_attending"


def test_borrow_inactive_player_rejected(admin_client, db):
    """Borrowing an inactive player returns player_not_found error."""
    event = _make_event(db, title="Inactive Borrow Event")
    inactive = Player(first_name="In", last_name="Active", is_active=False)
    db.add(inactive)
    db.commit()

    resp = admin_client.post(
        f"/attendance/{event.id}/borrow",
        data={"player_id": inactive.id},
        follow_redirects=False,
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["ok"] is False
    assert body["error"] == "player_not_found"


def test_borrow_no_season_stores_null_team(admin_client, db):
    """Event with season_id=None: borrow succeeds with borrowed_from_team_id=None."""
    event = Event(title="No Season Borrow", event_type="training", event_date=date(2026, 7, 1), season_id=None)
    db.add(event)
    db.commit()
    player = _make_player(db, "NoSeason", "Guest")

    resp = admin_client.post(
        f"/attendance/{event.id}/borrow",
        data={"player_id": player.id},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["team_name"] is None

    att = db.query(Attendance).filter(
        Attendance.event_id == event.id, Attendance.player_id == player.id
    ).first()
    assert att is not None
    assert att.borrowed_from_team_id is None


def test_player_search_excludes_existing_attendees(admin_client, db):
    """GET /players/search?q=&exclude_event_id= excludes players already attending."""
    from models.season import Season
    from models.team import Team

    season = Season(name="Search Season", is_active=True)
    team = Team(name="Search Team")
    db.add_all([season, team])
    db.flush()

    event = Event(
        title="Search Event",
        event_type="training",
        event_date=date(2026, 6, 3),
        season_id=season.id,
    )
    db.add(event)
    db.commit()

    already = _make_player(db, "Already", "There")
    not_yet = _make_player(db, "Notyet", "Player")

    db.add(Attendance(event_id=event.id, player_id=already.id, status="present"))
    db.commit()

    resp = admin_client.get(
        f"/players/search?q=player&exclude_event_id={event.id}",
        follow_redirects=False,
    )
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()]
    assert already.id not in ids
    assert not_yet.id in ids
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_attendance.py::test_borrow_creates_attendance_with_team \
       tests/test_attendance.py::test_borrow_duplicate_rejected \
       tests/test_attendance.py::test_borrow_inactive_player_rejected \
       tests/test_attendance.py::test_borrow_no_season_stores_null_team \
       tests/test_attendance.py::test_player_search_excludes_existing_attendees \
       -v
```

Expected: FAIL — routes don't exist yet.

---

## Task 3: Implement `GET /players/search`

**Files:**
- Modify: `routes/players.py`

- [ ] **Step 1: Add the search endpoint to `routes/players.py`**

Add this handler after the `router = APIRouter()` line. The `routes/players.py` file registers under the `/players` prefix in `app/main.py`, so this handler's final URL is `/players/search`.

```python
from fastapi.responses import JSONResponse
from sqlalchemy import or_


@router.get("/search")
async def player_search(
    request: Request,
    q: str = "",
    exclude_event_id: int | None = None,
    user: User = Depends(require_coach_or_admin),
    db: Session = Depends(get_db),
):
    """Return up to 20 active non-archived players matching `q` (name search).

    Excludes players who already have an Attendance row for `exclude_event_id`.
    Response: [{id, full_name, team_name}]
    """
    from models.attendance import Attendance  # noqa: PLC0415

    if len(q.strip()) < 2:
        return JSONResponse([])

    # Resolve season_id and existing attendees from the event
    season_id: int | None = None
    excluded_player_ids: set[int] = set()
    if exclude_event_id is not None:
        from models.event import Event as Ev  # noqa: PLC0415

        ev = db.get(Ev, exclude_event_id)
        if ev:
            season_id = ev.season_id
            excluded_player_ids = {
                row.player_id
                for row in db.query(Attendance.player_id)
                .filter(Attendance.event_id == exclude_event_id)
                .all()
            }

    term = f"%{q.strip()}%"
    query = (
        db.query(Player)
        .filter(
            Player.is_active.is_(True),
            Player.archived_at.is_(None),
            or_(Player.first_name.ilike(term), Player.last_name.ilike(term)),
        )
    )
    # Apply exclusion at the DB level so the LIMIT applies to valid candidates only
    if excluded_player_ids:
        query = query.filter(~Player.id.in_(excluded_player_ids))
    players = query.limit(20).all()

    # Resolve team_name per player in the event's season
    results = []
    for p in players:
        team_name = None
        if season_id is not None:
            mem = (
                db.query(PlayerTeam)
                .filter(PlayerTeam.player_id == p.id, PlayerTeam.season_id == season_id)
                .order_by(PlayerTeam.priority.asc())
                .first()
            )
            if mem is not None:
                team = db.get(Team, mem.team_id)
                if team:
                    team_name = team.name
        results.append({
            "id": p.id,
            "full_name": f"{p.first_name} {p.last_name}",
            "team_name": team_name,
        })

    return JSONResponse(results)
```

- [ ] **Step 2: Run the search test**

```bash
pytest tests/test_attendance.py::test_player_search_excludes_existing_attendees -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add routes/players.py
git commit -m "feat: add GET /players/search endpoint for borrow dialog"
```

---

## Task 4: Implement `POST /attendance/{event_id}/borrow`

**Files:**
- Modify: `routes/attendance.py`

- [ ] **Step 1: Add imports to `routes/attendance.py`**

The file currently imports:
```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
```

Update to also include:
```python
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from models.player_team import PlayerTeam
```

- [ ] **Step 2: Add the borrow endpoint at the end of `routes/attendance.py`**

```python
# ---------------------------------------------------------------------------
# Borrow a player for a single event
# ---------------------------------------------------------------------------


@router.post("/{event_id}/borrow")
async def borrow_player(
    event_id: int,
    request: Request,
    player_id: int = Form(...),
    user: User = Depends(require_coach_or_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    """Add a player from another team to this event's attendance."""
    event = db.get(Event, event_id)
    if event is None:
        return JSONResponse({"ok": False, "error": "event_not_found"}, status_code=404)

    player = db.get(Player, player_id)
    if player is None or not player.is_active:
        return JSONResponse({"ok": False, "error": "player_not_found"}, status_code=404)

    existing = (
        db.query(Attendance)
        .filter(Attendance.event_id == event_id, Attendance.player_id == player_id)
        .first()
    )
    if existing:
        return JSONResponse({"ok": False, "error": "already_attending"}, status_code=409)

    # Resolve player's home team for this event's season
    borrowed_from_team_id: int | None = None
    team_name: str | None = None
    if event.season_id is not None:
        mem = (
            db.query(PlayerTeam)
            .filter(PlayerTeam.player_id == player_id, PlayerTeam.season_id == event.season_id)
            .order_by(PlayerTeam.priority.asc())
            .first()
        )
        if mem is not None:
            from models.team import Team  # noqa: PLC0415

            team = db.get(Team, mem.team_id)
            if team:
                borrowed_from_team_id = team.id
                team_name = team.name

    att = Attendance(
        event_id=event_id,
        player_id=player_id,
        status="unknown",
        borrowed_from_team_id=borrowed_from_team_id,
    )
    db.add(att)
    db.commit()

    return JSONResponse({
        "ok": True,
        "player_id": player_id,
        "full_name": f"{player.first_name} {player.last_name}",
        "team_name": team_name,
    })
```

- [ ] **Step 3: Run the borrow tests**

```bash
pytest tests/test_attendance.py::test_borrow_creates_attendance_with_team \
       tests/test_attendance.py::test_borrow_duplicate_rejected \
       tests/test_attendance.py::test_borrow_inactive_player_rejected \
       -v
```

Expected: all 3 PASS.

- [ ] **Step 4: Run full test suite**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add routes/attendance.py
git commit -m "feat: add POST /attendance/{event_id}/borrow endpoint"
```

---

## Task 5: Add translation keys

**Files:**
- Modify: `locales/en.json`, `locales/it.json`, `locales/fr.json`, `locales/de.json`

- [ ] **Step 1: Add keys to `locales/en.json`**

Find the `"attendance"` object. Add inside it:

```json
"borrow_btn": "Add borrowed player",
"borrow_title": "Borrow a player",
"borrow_search_placeholder": "Search by name (min. 2 chars)...",
"borrow_add": "Add to event",
"borrow_no_team": "no team",
"borrow_tooltip": "Borrowed from %{team}",
"borrow_tooltip_no_team": "Borrowed — no home team",
"borrow_err_duplicate": "This player is already in the attendance list.",
"borrow_err_not_found": "Player not found or inactive.",
"borrow_err_event_not_found": "Event not found.",
"borrow_err_generic": "Could not add player. Please try again."
```

- [ ] **Step 2: Add keys to `locales/it.json`**

```json
"borrow_btn": "Aggiungi giocatore in prestito",
"borrow_title": "Prendi in prestito un giocatore",
"borrow_search_placeholder": "Cerca per nome (min. 2 caratteri)...",
"borrow_add": "Aggiungi all'evento",
"borrow_no_team": "nessuna squadra",
"borrow_tooltip": "In prestito da %{team}",
"borrow_tooltip_no_team": "In prestito — nessuna squadra di appartenenza",
"borrow_err_duplicate": "Questo giocatore è già nell'elenco presenze.",
"borrow_err_not_found": "Giocatore non trovato o non attivo.",
"borrow_err_event_not_found": "Evento non trovato.",
"borrow_err_generic": "Impossibile aggiungere il giocatore. Riprovare."
```

- [ ] **Step 3: Add keys to `locales/fr.json`**

```json
"borrow_btn": "Ajouter un joueur emprunté",
"borrow_title": "Emprunter un joueur",
"borrow_search_placeholder": "Rechercher par nom (min. 2 caractères)...",
"borrow_add": "Ajouter à l'événement",
"borrow_no_team": "sans équipe",
"borrow_tooltip": "Emprunté à %{team}",
"borrow_tooltip_no_team": "Emprunté — pas d'équipe d'origine",
"borrow_err_duplicate": "Ce joueur est déjà dans la liste des présences.",
"borrow_err_not_found": "Joueur introuvable ou inactif.",
"borrow_err_event_not_found": "Événement introuvable.",
"borrow_err_generic": "Impossible d'ajouter le joueur. Veuillez réessayer."
```

- [ ] **Step 4: Add keys to `locales/de.json`**

```json
"borrow_btn": "Ausgeliehenen Spieler hinzufügen",
"borrow_title": "Spieler ausleihen",
"borrow_search_placeholder": "Nach Name suchen (min. 2 Zeichen)...",
"borrow_add": "Zum Ereignis hinzufügen",
"borrow_no_team": "kein Team",
"borrow_tooltip": "Ausgeliehen von %{team}",
"borrow_tooltip_no_team": "Ausgeliehen — kein Heimteam",
"borrow_err_duplicate": "Dieser Spieler ist bereits in der Anwesenheitsliste.",
"borrow_err_not_found": "Spieler nicht gefunden oder inaktiv.",
"borrow_err_event_not_found": "Ereignis nicht gefunden.",
"borrow_err_generic": "Spieler konnte nicht hinzugefügt werden. Bitte erneut versuchen."
```

- [ ] **Step 5: Commit**

```bash
git add locales/
git commit -m "i18n: add borrow dialog translation keys for all 4 locales"
```

---

## Task 6: Update attendance template and CSS

**Files:**
- Modify: `templates/attendance/mark.html`
- Modify: `static/css/main.css`
- Modify: `templates/base.html`

- [ ] **Step 1: Add tooltip CSS to `static/css/main.css`**

Add at the end of the file:

```css
/* ── Borrowed player indicator ─────────────────────────────────── */
.borrow-icon {
  display: inline-block;
  cursor: default;
  font-size: .85em;
  margin-left: .3rem;
  position: relative;
}
.borrow-icon .borrow-tooltip {
  display: none;
  position: absolute;
  bottom: 125%;
  left: 50%;
  transform: translateX(-50%);
  background: var(--contrast);
  color: var(--contrast-inverse);
  font-size: .78rem;
  padding: .3rem .6rem;
  border-radius: 4px;
  white-space: nowrap;
  z-index: 100;
  pointer-events: none;
}
.borrow-icon:hover .borrow-tooltip,
.borrow-icon:focus .borrow-tooltip {
  display: block;
}
```

- [ ] **Step 2: Bump CSS cache-busting version in `templates/base.html`**

Change `?v=8` to `?v=9` in:
```html
<link rel="stylesheet" href="/static/css/main.css?v=9">
```

- [ ] **Step 3: Update the admin table to show borrow indicator**

In `templates/attendance/mark.html`, find the player name cell inside `{% for att in attendances %}`:

```html
        <td>{{ att.player.full_name if att.player else att.player_id }}</td>
```

Replace with:

```html
        <td>
          {{ att.player.full_name if att.player else att.player_id }}
          {% if att.borrowed_from_team_id is not none %}
          <span class="borrow-icon" tabindex="0">⟳<span class="borrow-tooltip">
            {% if att.borrowed_from_team %}{{ t('attendance.borrow_tooltip', team=att.borrowed_from_team.name) }}{% else %}{{ t('attendance.borrow_tooltip_no_team') }}{% endif %}
          </span></span>
          {% endif %}
        </td>
```

- [ ] **Step 4: Update the attendance GET route to eager-load borrowed_from_team**

In `routes/attendance.py`, the admin attendance query appears twice (once for admin role, once for coach role, around lines 39 and 47). Update **both** to add eager-load:

```python
        from sqlalchemy.orm import joinedload  # noqa: PLC0415
        attendances = (
            db.query(Attendance)
            .options(joinedload(Attendance.borrowed_from_team))
            .filter(Attendance.event_id == event_id)
            .all()
        )
```

- [ ] **Step 5: Add the "Add borrowed player" button**

In `templates/attendance/mark.html`, inside `{% if is_admin_view %}`, find:

```html
  {% if attendances %}
  <div class="table-responsive">
```

Add the button before it:

```html
  <div style="margin-bottom:1rem;">
    <button type="button" class="btn btn-outline btn-sm" onclick="openBorrowDialog()">
      + {{ t('attendance.borrow_btn') }}
    </button>
  </div>
  {% if attendances %}
  <div class="table-responsive">
```

- [ ] **Step 6: Add the borrow dialog and JS**

Add this block inside `{% if is_admin_view %}`, after the closing `</script>` tag of the existing AJAX attendance script and before `{% else %}` (the else that handles non-admin/member view).

**Important:** All DOM manipulation uses safe methods (`createElement`, `textContent`, `appendChild`) — never `innerHTML` with user-supplied data — to prevent XSS.

```html
  {# ── Borrow dialog ───────────────────────────────────────────── #}
  <dialog id="borrow-dialog" class="att-dialog">
    <article>
      <header>
        <h3>{{ t('attendance.borrow_title') }}</h3>
      </header>
      <input type="text" id="borrow-search-input"
             placeholder="{{ t('attendance.borrow_search_placeholder') }}"
             autocomplete="off">
      <div id="borrow-results" style="margin-top:.5rem;max-height:200px;overflow-y:auto;"></div>
      <p id="borrow-error" style="color:var(--tp-danger,#c0392b);display:none;margin-top:.5rem;"></p>
      <footer class="att-dialog-actions">
        <button type="button" class="btn btn-outline"
                onclick="document.getElementById('borrow-dialog').close()">
          {{ t('common.cancel') }}
        </button>
        <button type="button" class="btn btn-primary" id="borrow-add-btn" disabled
                onclick="submitBorrow()">
          {{ t('attendance.borrow_add') }}
        </button>
      </footer>
    </article>
  </dialog>

  <script>
  (function() {
    var _sel = null; // {id, fullName, teamName}
    var _debounce = null;
    var _csrf = '{{ request.state.csrf_token }}';
    var _eventId = {{ event.id }};
    var _i18n = {
      noTeam: {{ t('attendance.borrow_no_team') | tojson }},
      tooltipTpl: {{ t('attendance.borrow_tooltip', team='__TEAM__') | tojson }},
      tooltipNoTeam: {{ t('attendance.borrow_tooltip_no_team') | tojson }},
      errDuplicate: {{ t('attendance.borrow_err_duplicate') | tojson }},
      errNotFound: {{ t('attendance.borrow_err_not_found') | tojson }},
      errEventNotFound: {{ t('attendance.borrow_err_event_not_found') | tojson }},
      errGeneric: {{ t('attendance.borrow_err_generic') | tojson }},
      statusLabels: {{ enums.status | tojson }},
      editLabel: {{ t('common.edit') | tojson }}
    };

    window.openBorrowDialog = function() {
      _sel = null;
      document.getElementById('borrow-search-input').value = '';
      document.getElementById('borrow-results').textContent = '';
      document.getElementById('borrow-error').style.display = 'none';
      document.getElementById('borrow-add-btn').disabled = true;
      document.getElementById('borrow-dialog').showModal();
      setTimeout(function() { document.getElementById('borrow-search-input').focus(); }, 50);
    };

    document.getElementById('borrow-search-input').addEventListener('input', function() {
      clearTimeout(_debounce);
      var q = this.value;
      _debounce = setTimeout(function() { doSearch(q); }, 300);
    });

    function doSearch(q) {
      var container = document.getElementById('borrow-results');
      container.textContent = '';
      if (q.length < 2) return;
      fetch('/players/search?q=' + encodeURIComponent(q) + '&exclude_event_id=' + _eventId)
        .then(function(r) { return r.json(); })
        .then(function(players) {
          if (!players.length) {
            var p = document.createElement('p');
            p.className = 'text-muted';
            p.style.padding = '.4rem .6rem';
            p.textContent = 'No results';
            container.appendChild(p);
            return;
          }
          players.forEach(function(player) {
            var row = document.createElement('div');
            row.className = 'borrow-result';
            row.style.cssText = 'padding:.4rem .6rem;cursor:pointer;border-radius:4px;';

            var strong = document.createElement('strong');
            strong.textContent = player.full_name;
            row.appendChild(strong);

            var muted = document.createElement('span');
            muted.className = 'text-muted';
            muted.textContent = ' — ' + (player.team_name || _i18n.noTeam);
            row.appendChild(muted);

            row.addEventListener('click', function() {
              document.querySelectorAll('.borrow-result').forEach(function(r) {
                r.style.background = '';
              });
              row.style.background = 'var(--primary-focus, rgba(0,0,0,.1))';
              _sel = { id: player.id, fullName: player.full_name, teamName: player.team_name };
              document.getElementById('borrow-add-btn').disabled = false;
              document.getElementById('borrow-error').style.display = 'none';
            });
            container.appendChild(row);
          });
        });
    }

    window.submitBorrow = function() {
      if (!_sel) return;
      var form = new FormData();
      form.append('player_id', _sel.id);
      form.append('csrf_token', _csrf);
      fetch('/attendance/' + _eventId + '/borrow', { method: 'POST', body: form })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (data.ok) {
            document.getElementById('borrow-dialog').close();
            addBorrowRow(data);
          } else {
            var msg = data.error === 'already_attending' ? _i18n.errDuplicate
                    : data.error === 'player_not_found' ? _i18n.errNotFound
                    : data.error === 'event_not_found' ? _i18n.errEventNotFound
                    : _i18n.errGeneric;
            var errEl = document.getElementById('borrow-error');
            errEl.textContent = msg;
            errEl.style.display = 'block';
          }
        })
        .catch(function() {
          var errEl = document.getElementById('borrow-error');
          errEl.textContent = _i18n.errGeneric;
          errEl.style.display = 'block';
        });
    };

    function addBorrowRow(data) {
      var tbody = document.querySelector('table tbody');
      if (!tbody) { location.reload(); return; }

      var statusLabel = _i18n.statusLabels['unknown'] || 'Unknown';
      var tooltipText = data.team_name
        ? _i18n.tooltipTpl.replace('__TEAM__', data.team_name)
        : _i18n.tooltipNoTeam;

      var tr = document.createElement('tr');
      tr.dataset.playerId = data.player_id;

      // Cell 1: player name + borrow icon
      var tdName = document.createElement('td');
      tdName.textContent = data.full_name;
      var icon = document.createElement('span');
      icon.className = 'borrow-icon';
      icon.tabIndex = 0;
      icon.textContent = '⟳';
      var tip = document.createElement('span');
      tip.className = 'borrow-tooltip';
      tip.textContent = tooltipText;
      icon.appendChild(tip);
      tdName.appendChild(icon);
      tr.appendChild(tdName);

      // Cell 2: status badge
      var tdStatus = document.createElement('td');
      var badge = document.createElement('span');
      badge.className = 'badge badge-unknown att-status-badge';
      badge.textContent = statusLabel;
      tdStatus.appendChild(badge);
      tr.appendChild(tdStatus);

      // Cell 3: note (hidden on mobile)
      var tdNote = document.createElement('td');
      tdNote.className = 'col-hide-mobile att-note-cell';
      tr.appendChild(tdNote);

      // Cell 4: edit button
      var tdEdit = document.createElement('td');
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-sm btn-outline';
      btn.dataset.playerId = data.player_id;
      btn.dataset.playerName = data.full_name;
      btn.dataset.status = 'unknown';
      btn.dataset.note = '';
      btn.textContent = _i18n.editLabel;
      btn.addEventListener('click', function() { openAttDialog(this); });
      tdEdit.appendChild(btn);
      tr.appendChild(tdEdit);

      tbody.appendChild(tr);
    }
  })();
  </script>
```

- [ ] **Step 7: Start the dev server and verify visually**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 7000
```

Navigate to an event's attendance page as admin/coach. Verify:
- "Add borrowed player" button appears above the table.
- Clicking opens the search dialog.
- Typing 2+ chars shows player results with team name.
- Clicking a result enables "Add to event".
- Adding a player appends the row with ⟳ icon.
- Hovering ⟳ shows the tooltip with team name.
- Trying to add the same player twice shows the inline error.

- [ ] **Step 8: Run full test suite and lint**

```bash
pytest -v
ruff check . && ruff format .
```

Expected: all pass, no lint errors.

- [ ] **Step 9: Commit**

```bash
git add templates/attendance/mark.html templates/base.html static/css/main.css routes/attendance.py
git commit -m "feat: borrow player UI — search dialog, tooltip indicator, safe DOM row insertion"
```

---

## Task 7: Final push

- [ ] **Push to remote**

```bash
git push
```
