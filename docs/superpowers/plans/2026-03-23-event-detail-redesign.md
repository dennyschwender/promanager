# Event Detail Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the event detail page to be coach-focused with inline attendance management via a popover — no separate page navigation needed to update a player's status.

**Architecture:** Three changes: (1) add a richer attendance summary function that includes note data per player, (2) add a JSON response branch to the existing attendance POST endpoint for AJAX callers, (3) rewrite the event detail template with column-based attendance UI and vanilla JS popover.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Jinja2, vanilla JS (no libraries), Pico CSS, SQLite

---

## File Map

| File | Change |
|------|--------|
| `services/attendance_service.py` | Add `get_event_attendance_detail()` returning player + note per bucket |
| `routes/attendance.py` | Add JSON response branch to `POST /{event_id}/{player_id}` |
| `routes/events.py` | Use `get_event_attendance_detail()` instead of `get_event_attendance_summary()` |
| `templates/events/detail.html` | Full rewrite — new layout + JS popover |
| `tests/test_attendance.py` | Add 3 new tests for JSON branch |

---

## Task 1: Add `get_event_attendance_detail` service function

The existing `get_event_attendance_summary` returns bare `Player` objects, so note data is lost. We need a parallel function returning `{player, note}` dicts per bucket for the event detail page.

**Files:**
- Modify: `services/attendance_service.py`
- Test: `tests/test_attendance.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_attendance.py`:

```python
def test_get_event_attendance_detail_includes_notes(db):
    """get_event_attendance_detail returns player + note per bucket."""
    from services.attendance_service import get_event_attendance_detail

    event = _make_event(db, title="Detail Test")
    p1 = _make_player(db, "Alice", "Detail")
    set_attendance(db, event.id, p1.id, "present", note="On time")

    detail = get_event_attendance_detail(db, event.id)

    assert len(detail["present"]) == 1
    entry = detail["present"][0]
    assert entry["player"].first_name == "Alice"
    assert entry["note"] == "On time"
    assert len(detail["absent"]) == 0
    assert len(detail["unknown"]) == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_attendance.py::test_get_event_attendance_detail_includes_notes -v
```
Expected: `ImportError` or `AttributeError` — function doesn't exist yet.

- [ ] **Step 3: Implement `get_event_attendance_detail`**

Add after `get_event_attendance_summary` in `services/attendance_service.py`:

```python
def get_event_attendance_detail(db: Session, event_id: int) -> dict:
    """Return dict keyed by status, each value a list of {player, note} dicts.

    Unlike get_event_attendance_summary, this preserves the attendance note
    so it can be surfaced in the event detail UI.
    """
    from sqlalchemy.orm import joinedload  # noqa: PLC0415

    attendances = (
        db.query(Attendance)
        .options(joinedload(Attendance.player))
        .filter(Attendance.event_id == event_id)
        .all()
    )
    detail: dict[str, list[dict]] = {
        "present": [],
        "absent": [],
        "maybe": [],
        "unknown": [],
    }
    for att in attendances:
        bucket = att.status if att.status in detail else "unknown"
        if att.player:
            detail[bucket].append({"player": att.player, "note": att.note or ""})
    return detail
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_attendance.py::test_get_event_attendance_detail_includes_notes -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add services/attendance_service.py tests/test_attendance.py
git commit -m "feat: add get_event_attendance_detail service function with note data"
```

---

## Task 2: Add JSON response branch to attendance POST endpoint

When a request includes `Accept: application/json`, return JSON instead of redirecting. Existing redirect behaviour is preserved for all other callers.

**Files:**
- Modify: `routes/attendance.py`
- Test: `tests/test_attendance.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_attendance.py`:

```python
def test_update_attendance_json_response(admin_client, db):
    """POST with Accept: application/json returns JSON success response."""
    event = _make_event(db, title="JSON Test Event")
    player = _make_player(db, "Json", "Player")

    resp = admin_client.post(
        f"/attendance/{event.id}/{player.id}",
        data={"status": "present", "note": "via ajax"},
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status"] == "present"
    assert body["note"] == "via ajax"


def test_update_attendance_json_invalid_status(admin_client, db):
    """POST with invalid status + Accept header returns ok=false."""
    event = _make_event(db, title="Invalid Status Event")
    player = _make_player(db, "Bad", "Status")

    resp = admin_client.post(
        f"/attendance/{event.id}/{player.id}",
        data={"status": "flying", "note": ""},
        headers={"Accept": "application/json"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["ok"] is False
    assert body["error"] == "invalid_status"


def test_update_attendance_form_redirect_unchanged(admin_client, db):
    """POST without Accept: application/json still redirects (regression guard)."""
    event = _make_event(db, title="Redirect Guard Event")
    player = _make_player(db, "Redirect", "Guard")

    resp = admin_client.post(
        f"/attendance/{event.id}/{player.id}",
        data={"status": "absent", "note": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert f"/attendance/{event.id}" in resp.headers["location"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_attendance.py::test_update_attendance_json_response tests/test_attendance.py::test_update_attendance_json_invalid_status tests/test_attendance.py::test_update_attendance_form_redirect_unchanged -v
```
Expected: first two FAIL (still returns 302), third PASS (already redirects).

- [ ] **Step 3: Modify `routes/attendance.py` to add JSON branch**

Note: `wants_json` must be evaluated **before** any early-return statements so all error paths can return JSON when requested.

Replace the `update_attendance` function with:

```python
@router.post("/{event_id}/{player_id}")
async def update_attendance(
    event_id: int,
    player_id: int,
    request: Request,
    status: str = Form(...),
    note: str = Form(""),
    user: User = Depends(require_login),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    from fastapi.responses import JSONResponse  # noqa: PLC0415

    # Detect AJAX caller — must happen first so all error paths can branch
    wants_json = "application/json" in request.headers.get("accept", "")

    # Validate status early so JSON callers get a proper error
    valid_statuses = {"present", "absent", "maybe", "unknown"}
    if status not in valid_statuses:
        if wants_json:
            return JSONResponse({"ok": False, "error": "invalid_status"}, status_code=400)
        return RedirectResponse(f"/attendance/{event_id}", status_code=302)

    # Authorization check
    if user.is_admin:
        pass  # full access
    elif user.is_coach:
        event = db.get(Event, event_id)
        if event is None:
            if wants_json:
                return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
            return RedirectResponse(f"/attendance/{event_id}", status_code=302)
        from routes._auth_helpers import check_team_access  # noqa: PLC0415

        check_team_access(user, event.team_id, db, season_id=event.season_id)
    else:
        player = db.get(Player, player_id)
        if player is None or player.user_id != user.id:
            if wants_json:
                return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=403)
            return RedirectResponse(f"/attendance/{event_id}", status_code=302)

    set_attendance(db, event_id, player_id, status, note)

    if wants_json:
        return JSONResponse({"ok": True, "status": status, "note": note})

    from urllib.parse import quote  # noqa: PLC0415

    flash_msg = quote(rt(request, "common.changes_saved"))
    return RedirectResponse(f"/attendance/{event_id}?flash={flash_msg}", status_code=302)
```

- [ ] **Step 4: Run tests to verify all three pass**

```bash
pytest tests/test_attendance.py::test_update_attendance_json_response tests/test_attendance.py::test_update_attendance_json_invalid_status tests/test_attendance.py::test_update_attendance_form_redirect_unchanged -v
```
Expected: all 3 PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```
Expected: all tests pass (no regressions)

- [ ] **Step 6: Commit**

```bash
git add routes/attendance.py tests/test_attendance.py
git commit -m "feat: add JSON response branch to attendance POST endpoint"
```

---

## Task 3: Wire `get_event_attendance_detail` into the event detail route

The event detail route currently passes `summary` from `get_event_attendance_summary` (bare Player objects). Switch to `get_event_attendance_detail` so the template has note data.

**Files:**
- Modify: `routes/events.py`

- [ ] **Step 1: Find the import and usage in `routes/events.py`**

```bash
grep -n "get_event_attendance_summary\|attendance_detail\|summary" routes/events.py | head -20
```

- [ ] **Step 2: Update import**

In `routes/events.py`, find the line:
```python
from services.attendance_service import ...
```
Add `get_event_attendance_detail` to the import (keep any existing imports from that module).

- [ ] **Step 3: Update the event detail route**

Find the `event_detail` route handler (around line 398). It calls `get_event_attendance_summary(db, event.id)` and passes `summary=summary` to the template.

Replace:
```python
summary = get_event_attendance_summary(db, event.id)
```
With:
```python
summary = get_event_attendance_detail(db, event.id)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_events.py -v
```
Expected: all pass (template doesn't exist yet so render may fail — if so, that's expected and will be fixed in Task 4)

- [ ] **Step 5: Commit**

```bash
git add routes/events.py
git commit -m "feat: use get_event_attendance_detail in event detail route"
```

---

## Task 4: Rewrite `templates/events/detail.html`

Full replacement of the template with the new layout: compact header, action bar with dropdown, attendance columns, and JS popover.

**Files:**
- Modify: `templates/events/detail.html`

- [ ] **Step 1: Check the existing route context variables**

Open `routes/events.py` and find the `event_detail` handler. Note all variables passed to the template context: `event`, `user`, `summary`, `coach_team_ids`, `enums`, `t()` (injected by render()).

- [ ] **Step 2: Rewrite the template**

Replace the entire contents of `templates/events/detail.html` with:

```html
{% extends "base.html" %}
{% block head_extra %}<meta name="csrf-token" content="{{ request.state.csrf_token }}">{% endblock %}
{% block title %}{{ event.title }} — ProManager{% endblock %}
{% block breadcrumb %}
<nav class="breadcrumb">
  <a href="/dashboard">{{ t('common.home') }}</a><span class="breadcrumb-sep"></span>
  <a href="/events">{{ t('events.title') }}</a><span class="breadcrumb-sep"></span>
  <span>{{ event.title }}</span>
</nav>
{% endblock %}
{% block content %}

{# ── Header ────────────────────────────────────────────────────── #}
<div class="page-header">
  <h2>{{ event.title }}</h2>
  <div style="display:flex;gap:.4rem;flex-wrap:wrap;align-items:center;">
    <span class="badge badge-{{ event.event_type }}">{{ enums.event_type.get(event.event_type, event.event_type|capitalize) }}</span>
    {% set pt_labels = {"normal": t('events_detail.pt_normal'), "all": t('events_detail.pt_all'), "selection": t('events_detail.pt_selection'), "available": t('events_detail.pt_available'), "no_registration": t('events_detail.pt_no_reg')} %}
    <span class="badge badge-outline">{{ pt_labels.get(event.presence_type, event.presence_type) }}</span>
    {% if event.recurrence_group_id %}<span class="badge-recurring">&#8635; {{ t('events_detail.recurring_label') }}</span>{% endif %}
  </div>
</div>

{# ── Compact info strip ────────────────────────────────────────── #}
<p class="text-muted" style="margin-bottom:1rem;font-size:.92rem;">
  📅 {{ event.event_date }}
  {% if event.event_time %} · {{ event.event_time.strftime('%H:%M') }}{% if event.event_end_time %} → {{ event.event_end_time.strftime('%H:%M') }}{% endif %}{% endif %}
  {% if event.location %} · 📍 <a href="https://www.openstreetmap.org/search?query={{ event.location | urlencode }}" target="_blank" rel="noopener">{{ event.location }}</a>{% endif %}
  {% if event.meeting_time %} · {{ t('events_detail.meeting_point') }}: {{ event.meeting_time.strftime('%H:%M') }}{% if event.meeting_location %} @ {{ event.meeting_location }}{% endif %}{% endif %}
  {% if event.description %} · {{ event.description }}{% endif %}
</p>

{# ── Action bar ────────────────────────────────────────────────── #}
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.5rem;flex-wrap:wrap;gap:.5rem;">
  <a href="/events" class="btn btn-outline btn-sm">← {{ t('events.back_to_events') }}</a>
  <div style="display:flex;gap:.5rem;align-items:center;">
    {% if user.is_admin or (user.is_coach and event.team_id in coach_team_ids) %}
      <a href="/events/{{ event.id }}/edit" class="btn btn-outline btn-sm">{{ t('events.edit') }}</a>
      <div class="action-dropdown">
        <button type="button" class="btn btn-sm btn-outline action-dropdown-toggle" aria-haspopup="true">⋯</button>
        <div class="action-dropdown-menu">
          <a href="/events/{{ event.id }}/notify">{{ t('events.notify_players') }}</a>
          <form method="post" action="/events/{{ event.id }}/send-reminders" style="display:contents;">
            <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
            <button type="submit">{{ t('events.send_reminders') }}</button>
          </form>
          <hr style="margin:.25rem 0;">
          <form method="post" action="/events/{{ event.id }}/delete" style="display:contents;"
                onsubmit="return confirm('{{ t('events.confirm_delete') }}')">
            <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
            <button type="submit" style="color:var(--tp-danger,#dc3545);">{{ t('events.delete') }}</button>
          </form>
        </div>
      </div>
    {% endif %}
  </div>
</div>

{# ── Flash / alert messages ────────────────────────────────────── #}
{% if request.query_params.get("reminders_sent") %}
  <div class="alert alert-success">{{ t('events_detail.reminders_sent_msg', count=request.query_params.get("reminders_sent")) }}</div>
{% endif %}
{% if request.query_params.get("notified") %}
  <div class="alert alert-success">{{ t('events_detail.notified_msg', count=request.query_params.get("notified")) }}</div>
{% endif %}

{# ── Attendance columns ────────────────────────────────────────── #}
{% if event.presence_type == "no_registration" %}
  <p class="text-muted">{{ t('events_detail.no_registration_note') }}</p>
{% else %}
<h3>{{ t('events.attendance_summary') }}</h3>
<div id="attendance-columns" style="display:flex;gap:1rem;flex-wrap:wrap;align-items:flex-start;">
  {% for bucket, label in [
    ("present",  t('attendance.status_attend')),
    ("absent",   t('attendance.status_absent')),
    ("maybe",    t('events_detail.maybe')),
    ("unknown",  t('attendance.status_unknown'))
  ] %}
  <div class="att-col" data-bucket="{{ bucket }}"
       style="flex:1;min-width:160px;{% if not summary[bucket] %}display:none;{% endif %}">
    <div class="att-col-header">
      <span class="badge badge-{{ bucket }}" id="badge-{{ bucket }}">{{ label }} (<span class="att-count">{{ summary[bucket]|length }}</span>)</span>
    </div>
    <ul class="att-player-list" style="list-style:none;padding:0;margin:.5rem 0 0;">
      {% for entry in summary[bucket] %}
      <li>
        <button type="button" class="att-player-btn"
                data-player-id="{{ entry.player.id }}"
                data-player-name="{{ entry.player.full_name | e }}"
                data-status="{{ bucket }}"
                data-note="{{ entry.note | e }}"
                style="background:none;border:none;padding:.2rem 0;cursor:pointer;text-align:left;width:100%;color:inherit;text-decoration:underline dotted;">
          {{ entry.player.full_name }}
        </button>
      </li>
      {% endfor %}
    </ul>
  </div>
  {% endfor %}
</div>

{# ── Shared popover (single DOM node, reused for each player) ──── #}
{% if user.is_admin or (user.is_coach and event.team_id in coach_team_ids) %}
<div id="att-popover" style="display:none;position:absolute;z-index:200;background:var(--card-background-color,#fff);border:1px solid var(--muted-border-color,#ddd);border-radius:.5rem;padding:1rem;box-shadow:0 4px 16px rgba(0,0,0,.2);min-width:240px;">
  <strong id="pop-name" style="display:block;margin-bottom:.75rem;"></strong>
  <div style="display:flex;gap:.4rem;flex-wrap:wrap;margin-bottom:.75rem;">
    {% for s, lbl in [("present", t('attendance.status_attend')),("absent", t('attendance.status_absent')),("maybe", t('events_detail.maybe')),("unknown", t('attendance.status_unknown'))] %}
    <button type="button" class="btn btn-sm btn-outline pop-status-btn" data-status="{{ s }}">{{ lbl }}</button>
    {% endfor %}
  </div>
  <textarea id="pop-note" rows="2" style="width:100%;margin-bottom:.75rem;font-size:.88rem;" placeholder="{{ t('attendance.note_optional') }}"></textarea>
  <div id="pop-error" style="display:none;color:var(--tp-danger,#dc3545);font-size:.82rem;margin-bottom:.5rem;"></div>
  <div style="display:flex;gap:.5rem;justify-content:flex-end;">
    <button type="button" class="btn btn-sm btn-outline" id="pop-cancel">{{ t('common.cancel') }}</button>
    <button type="button" class="btn btn-sm btn-primary" id="pop-save">{{ t('common.save') }}</button>
  </div>
</div>

<script>
(function () {
  var EVENT_ID = {{ event.id }};
  var CSRF = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
  var popover = document.getElementById('att-popover');
  var popName = document.getElementById('pop-name');
  var popNote = document.getElementById('pop-note');
  var popError = document.getElementById('pop-error');
  var popSave = document.getElementById('pop-save');
  var activePlayerId = null;
  var activeStatus = null;

  // Highlight the active status button
  function highlightStatus(status) {
    popover.querySelectorAll('.pop-status-btn').forEach(function (btn) {
      btn.classList.toggle('btn-primary', btn.dataset.status === status);
      btn.classList.toggle('btn-outline', btn.dataset.status !== status);
    });
    activeStatus = status;
  }

  // Open popover below the clicked element
  function openPopover(btn) {
    var rect = btn.getBoundingClientRect();
    popover.style.top = (rect.bottom + window.scrollY + 6) + 'px';
    popover.style.left = Math.min(rect.left + window.scrollX, window.innerWidth - 260) + 'px';
    popName.textContent = btn.dataset.playerName;
    popNote.value = btn.dataset.note || '';
    popError.style.display = 'none';
    highlightStatus(btn.dataset.status);
    activePlayerId = parseInt(btn.dataset.playerId, 10);
    popSave.disabled = false;
    popover.style.display = 'block';
  }

  function closePopover() {
    popover.style.display = 'none';
    activePlayerId = null;
    activeStatus = null;
  }

  // Move a player button from one column to another
  function movePlayer(playerId, newStatus, note) {
    var btn = document.querySelector('.att-player-btn[data-player-id="' + playerId + '"]');
    if (!btn) return;
    var oldStatus = btn.dataset.status;
    btn.dataset.status = newStatus;
    btn.dataset.note = note;

    // Move the <li> element
    var li = btn.closest('li');
    var targetList = document.querySelector('.att-col[data-bucket="' + newStatus + '"] .att-player-list');
    targetList.appendChild(li);

    // Update counts and column visibility
    updateColumn(oldStatus);
    updateColumn(newStatus);
  }

  function updateColumn(bucket) {
    var col = document.querySelector('.att-col[data-bucket="' + bucket + '"]');
    var count = col.querySelectorAll('.att-player-btn').length;
    col.querySelector('.att-count').textContent = count;
    col.style.display = count === 0 ? 'none' : '';
  }

  // Save button
  popSave.addEventListener('click', function () {
    if (!activePlayerId || !activeStatus) return;
    popSave.disabled = true;
    popError.style.display = 'none';
    var note = popNote.value;
    var body = new FormData();
    body.append('status', activeStatus);
    body.append('note', note);
    body.append('csrf_token', CSRF);
    fetch('/attendance/' + EVENT_ID + '/' + activePlayerId, {
      method: 'POST',
      headers: { 'Accept': 'application/json' },
      body: body,
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.ok) {
          movePlayer(activePlayerId, data.status, data.note);
          closePopover();
        } else {
          popError.textContent = '{{ t('common.save_error') | e }}';
          popError.style.display = 'block';
          popSave.disabled = false;
        }
      })
      .catch(function () {
        popError.textContent = '{{ t('common.save_error') | e }}';
        popError.style.display = 'block';
        popSave.disabled = false;
      });
  });

  // Status button clicks inside popover
  popover.querySelectorAll('.pop-status-btn').forEach(function (btn) {
    btn.addEventListener('click', function () { highlightStatus(btn.dataset.status); });
  });

  // Cancel button
  document.getElementById('pop-cancel').addEventListener('click', closePopover);

  // Open popover on player name click
  document.getElementById('attendance-columns').addEventListener('click', function (e) {
    var btn = e.target.closest('.att-player-btn');
    if (btn) { e.stopPropagation(); openPopover(btn); }
  });

  // Close on outside click
  document.addEventListener('click', function (e) {
    if (popover.style.display !== 'none' && !popover.contains(e.target)) {
      closePopover();
    }
  });

  // Dropdown reuse (same script as events/list.html)
  document.addEventListener('click', function (e) {
    var toggle = e.target.closest('.action-dropdown-toggle');
    if (toggle) {
      e.stopPropagation();
      var menu = toggle.nextElementSibling;
      var isOpen = menu.classList.contains('open');
      document.querySelectorAll('.action-dropdown-menu.open').forEach(function (m) { m.classList.remove('open'); });
      if (!isOpen) menu.classList.add('open');
      return;
    }
    document.querySelectorAll('.action-dropdown-menu.open').forEach(function (m) { m.classList.remove('open'); });
  });
})();
</script>
{% endif %}
{% endif %}
{% endblock %}
```

- [ ] **Step 3: Add missing translation key `events_detail.no_registration_note`**

In `locales/en.json`, find `events_detail` section and add:
```json
"no_registration_note": "Attendance tracking is disabled for this event."
```

In `locales/it.json`:
```json
"no_registration_note": "Il tracciamento delle presenze è disabilitato per questo evento."
```

In `locales/fr.json`:
```json
"no_registration_note": "Le suivi des présences est désactivé pour cet événement."
```

In `locales/de.json`:
```json
"no_registration_note": "Die Anwesenheitsverfolgung ist für dieses Ereignis deaktiviert."
```

Also add `common.save_error` to all 4 locale files:

`en.json`: `"save_error": "Could not save. Please try again."`
`it.json`: `"save_error": "Salvataggio non riuscito. Riprova."`
`fr.json`: `"save_error": "Impossible de sauvegarder. Veuillez réessayer."`
`de.json`: `"save_error": "Speichern fehlgeschlagen. Bitte erneut versuchen."`

- [ ] **Step 4: Run tests**

```bash
pytest -v
```
Expected: all tests pass

- [ ] **Step 5: Start dev server and manually test**

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 7000
```

Open http://localhost:7000/events, navigate to an event detail page and verify:
- [ ] Compact info strip shows date, time, location
- [ ] Action bar: Back left, Edit center, ⋯ dropdown right
- [ ] ⋯ dropdown contains Notify, Send reminders, Delete
- [ ] Attendance columns show only non-empty buckets
- [ ] Clicking a player name opens the popover
- [ ] Popover shows player name, current status highlighted, note pre-filled
- [ ] Clicking a status button highlights it
- [ ] Clicking Save moves the player, updates count, hides empty column
- [ ] Clicking outside popover closes it
- [ ] `no_registration` event shows the note instead of columns

- [ ] **Step 6: Commit**

```bash
git add templates/events/detail.html locales/en.json locales/it.json locales/fr.json locales/de.json
git commit -m "feat: redesign event detail page with inline attendance management"
```

---

## Task 5: Final regression check and push

- [ ] **Step 1: Run full test suite**

```bash
pytest -v
```
Expected: all tests pass

- [ ] **Step 2: Lint**

```bash
ruff check . && ruff format .
```

- [ ] **Step 3: Push**

```bash
git push
```
