# Recurrence-Aware Event Deletion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When deleting a recurring event, show a dialog with two options — "delete only this event" or "delete this and all future events in the series."

**Architecture:** Enhance the existing `POST /events/{event_id}/delete` route to accept an optional `scope` form field. The service functions `delete_future_events()` and `count_future_events()` in `schedule_service.py` already exist and handle the bulk deletion. The event detail template replaces the inline delete form with a `<dialog>` element. No new routes needed.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Jinja2 templates, Pico CSS, vanilla JS

---

## File Map

| File | Change |
|---|---|
| `routes/events.py` | Add `scope` param to `event_delete`; add `future_count` to `event_detail` context |
| `templates/events/detail.html` | Replace inline delete form with `<dialog>` |
| `locales/en.json`, `it.json`, `fr.json`, `de.json` | Add 4 new translation keys under `events` namespace |
| `tests/test_events.py` | Add 3 tests |

---

## Task 1: Write failing tests

**Files:**
- Modify: `tests/test_events.py`

- [ ] **Step 1: Add the three tests**

Open `tests/test_events.py`. Add these tests at the bottom of the file. The helper `_make_recurring_events` creates a series of events with the same `recurrence_group_id`.

```python
import uuid
from datetime import date, timedelta

from models.event import Event


def _make_recurring_events(db, count=3, start_days_ago=7):
    """Create `count` events sharing a recurrence_group_id.

    The first event is `start_days_ago` days in the past; subsequent events
    are 7 days apart (weekly). Returns list of Event objects sorted by date.
    """
    group_id = str(uuid.uuid4())
    events = []
    for i in range(count):
        ev = Event(
            title=f"Recurring {i}",
            event_type="training",
            event_date=date.today() - timedelta(days=start_days_ago) + timedelta(weeks=i),
            recurrence_group_id=group_id,
            recurrence_rule="weekly",
        )
        db.add(ev)
        events.append(ev)
    db.commit()
    for ev in events:
        db.refresh(ev)
    return events


def test_event_delete_single_leaves_series_intact(admin_client, db):
    """scope=single deletes only the targeted event; other series events survive."""
    evs = _make_recurring_events(db, count=3, start_days_ago=14)
    target = evs[0]  # past event
    sibling = evs[1]

    resp = admin_client.post(
        f"/events/{target.id}/delete",
        data={"scope": "single"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    assert db.get(Event, target.id) is None
    assert db.get(Event, sibling.id) is not None


def test_event_delete_future_removes_current_and_future(admin_client, db):
    """scope=future deletes the current event and all future events in the series,
    but leaves past events untouched."""
    # evs[0] is 7 days ago (past), evs[1] is today, evs[2] is 7 days from now
    evs = _make_recurring_events(db, count=3, start_days_ago=7)
    past_ev = evs[0]
    today_ev = evs[1]
    future_ev = evs[2]

    resp = admin_client.post(
        f"/events/{today_ev.id}/delete",
        data={"scope": "future"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    assert db.get(Event, past_ev.id) is not None   # past — untouched
    assert db.get(Event, today_ev.id) is None       # today — deleted
    assert db.get(Event, future_ev.id) is None      # future — deleted


def test_event_delete_future_on_nonrecurring_falls_back_to_single(admin_client, db):
    """scope=future on a non-recurring event silently deletes only that event."""
    ev = Event(title="Solo", event_type="training", event_date=date.today())
    db.add(ev)
    db.commit()
    db.refresh(ev)

    resp = admin_client.post(
        f"/events/{ev.id}/delete",
        data={"scope": "future"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert db.get(Event, ev.id) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate
pytest tests/test_events.py::test_event_delete_single_leaves_series_intact \
       tests/test_events.py::test_event_delete_future_removes_current_and_future \
       tests/test_events.py::test_event_delete_future_on_nonrecurring_falls_back_to_single \
       -v
```

Expected: FAIL — all three tests fail because the route ignores the `scope` field.

---

## Task 2: Enhance the delete route and detail context

**Files:**
- Modify: `routes/events.py`

- [ ] **Step 1: Add imports at the top of `routes/events.py`**

The file already imports from `services.schedule_service` (`advance_date`). Add `count_future_events` and `delete_future_events` to that import:

```python
# Change this line (around line 37):
from services.schedule_service import advance_date as _advance_date
# To:
from services.schedule_service import (
    advance_date as _advance_date,
    count_future_events,
    delete_future_events,
)
```

- [ ] **Step 2: Update `event_detail` to pass `future_count` to template**

Find the `event_detail` handler (around line 397). Change the `render()` call from:

```python
    return render(
        request,
        "events/detail.html",
        {
            "user": user,
            "event": event,
            "summary": summary,
            "coach_team_ids": get_coach_teams(user, db) if user.is_coach else set(),
        },
    )
```

To:

```python
    future_count = (
        count_future_events(db, event.recurrence_group_id)
        if event.recurrence_group_id
        else 0
    )

    return render(
        request,
        "events/detail.html",
        {
            "user": user,
            "event": event,
            "summary": summary,
            "coach_team_ids": get_coach_teams(user, db) if user.is_coach else set(),
            "future_count": future_count,
        },
    )
```

- [ ] **Step 3: Update `event_delete` to handle `scope` with flash messages**

Flash messages use the `?flash=<url-encoded-message>` query param pattern already established in the codebase. Add `from urllib.parse import quote` if not already imported in `routes/events.py` (it likely isn't — add it to the top-level imports).

Find `event_delete` (around line 583). Replace the entire function body:

```python
@router.post("/{event_id}/delete")
async def event_delete(
    event_id: int,
    request: Request,
    scope: str = Form("single"),
    _user: User = Depends(require_coach_or_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    from urllib.parse import quote  # noqa: PLC0415

    event = db.get(Event, event_id)
    if not event:
        return RedirectResponse("/events", status_code=302)

    check_team_access(_user, event.team_id, db, season_id=event.season_id)

    if scope == "future" and event.recurrence_group_id:
        n = delete_future_events(db, event.recurrence_group_id)
        db.commit()
        msg = quote(rt(request, "events.deleted_series", count=n))
        return RedirectResponse(f"/events?flash={msg}", status_code=302)

    # Default: delete single event
    db.delete(event)
    db.commit()
    msg = quote(rt(request, "events.deleted_single"))
    return RedirectResponse(f"/events?flash={msg}", status_code=302)
```

- [ ] **Step 4: Update `events_list` route to pass flash to template**

Find `events_list` (around line 61). In the `render()` call (around line 85), add `"flash"` to the context dict:

```python
    return render(
        request,
        "events/list.html",
        {
            "user": user,
            "upcoming": upcoming,
            "past": past,
            "seasons": seasons,
            "teams": teams,
            "selected_season_id": season_id,
            "selected_team_id": team_id,
            "coach_team_ids": get_coach_teams(user, db) if user and user.is_coach else set(),
            "flash": request.query_params.get("flash"),
        },
    )
```

- [ ] **Step 5: Update `templates/events/list.html` to show flash message**

Find the opening of `{% block content %}` (around line 6). Right after `<div class="page-header">...</div>`, add:

```html
{% if flash %}
  <div class="alert alert-success">{{ flash }}</div>
{% endif %}
```

- [ ] **Step 6: Run the tests — they should pass now**

```bash
pytest tests/test_events.py::test_event_delete_single_leaves_series_intact \
       tests/test_events.py::test_event_delete_future_removes_current_and_future \
       tests/test_events.py::test_event_delete_future_on_nonrecurring_falls_back_to_single \
       -v
```

Expected: all 3 PASS.

- [ ] **Step 7: Run full test suite to check for regressions**

```bash
pytest -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add routes/events.py templates/events/list.html tests/test_events.py locales/
git commit -m "feat: recurrence-aware event deletion (scope param, flash messages, future_count)"
```

---

## Task 3: Add translation keys

**Files:**
- Modify: `locales/en.json`, `locales/it.json`, `locales/fr.json`, `locales/de.json`

- [ ] **Step 1: Add keys to `locales/en.json`**

Find the `"events"` object (around line 65). Add these four keys inside it (before the closing `}`):

```json
"delete_title": "Delete Event",
"delete_scope_single": "Delete only this event",
"delete_scope_future": "Delete this and all %{count} events in this series (including today)",
"delete_future_confirm": "This will permanently delete %{count} event(s). Are you sure?",
"deleted_single": "Event deleted.",
"deleted_series": "Deleted %{count} events in this series."
```

- [ ] **Step 2: Add keys to `locales/it.json`**

```json
"delete_title": "Elimina evento",
"delete_scope_single": "Elimina solo questo evento",
"delete_scope_future": "Elimina questo e tutti i %{count} eventi della serie (incluso oggi)",
"delete_future_confirm": "Verranno eliminati definitivamente %{count} evento/i. Confermi?",
"deleted_single": "Evento eliminato.",
"deleted_series": "%{count} eventi della serie eliminati."
```

- [ ] **Step 3: Add keys to `locales/fr.json`**

```json
"delete_title": "Supprimer l'événement",
"delete_scope_single": "Supprimer seulement cet événement",
"delete_scope_future": "Supprimer cet événement et les %{count} de la série (aujourd'hui inclus)",
"delete_future_confirm": "Cela supprimera définitivement %{count} événement(s). Êtes-vous sûr ?",
"deleted_single": "Événement supprimé.",
"deleted_series": "%{count} événements de la série supprimés."
```

- [ ] **Step 4: Add keys to `locales/de.json`**

```json
"delete_title": "Ereignis löschen",
"delete_scope_single": "Nur dieses Ereignis löschen",
"delete_scope_future": "Dieses und alle %{count} Ereignisse der Serie löschen (heute eingeschlossen)",
"delete_future_confirm": "Es werden %{count} Ereignis(se) dauerhaft gelöscht. Sind Sie sicher?",
"deleted_single": "Ereignis gelöscht.",
"deleted_series": "%{count} Ereignisse der Serie gelöscht."
```

- [ ] **Step 5: Commit**

```bash
git add locales/
git commit -m "i18n: add delete-dialog translation keys for all 4 locales"
```

---

## Task 4: Replace inline delete form with dialog

**Files:**
- Modify: `templates/events/detail.html`

- [ ] **Step 1: Replace the delete form in the action dropdown**

Find this block in the dropdown menu (around line 63–67):

```html
          <form method="post" action="/events/{{ event.id }}/delete" class="form-contents"
                onsubmit="return confirm('{{ t('events.confirm_delete') }}')">
            <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
            <button type="submit" class="btn-danger-text">{{ t('events.delete') }}</button>
          </form>
```

Replace with:

```html
          <button type="button" class="btn-danger-text" onclick="openDeleteDialog()">{{ t('events.delete') }}</button>
```

- [ ] **Step 2: Add the delete dialog before `{% endblock %}`**

Add this block at the very end of `{% block content %}`, just before `{% endblock %}`:

```html
{# ── Delete dialog ─────────────────────────────────────────────── #}
{% if user.is_admin or (user.is_coach and event.team_id in coach_team_ids) %}
<dialog id="delete-dialog" class="att-dialog">
  <article>
    <header>
      <h3>{{ t('events.delete_title') }}</h3>
    </header>
    <form method="post" action="/events/{{ event.id }}/delete" id="delete-dialog-form">
      <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
      {% if future_count > 0 %}
      <fieldset>
        <label class="att-dialog-radio">
          <input type="radio" name="scope" value="single" checked>
          {{ t('events.delete_scope_single') }}
        </label>
        <label class="att-dialog-radio">
          <input type="radio" name="scope" value="future">
          {{ t('events.delete_scope_future', count=future_count) }}
        </label>
      </fieldset>
      <p id="delete-future-warning" class="text-muted" style="display:none;font-size:.9rem;">
        {{ t('events.delete_future_confirm', count=future_count) }}
      </p>
      {% else %}
      <input type="hidden" name="scope" value="single">
      <p>{{ t('events.confirm_delete') }}</p>
      {% endif %}
      <footer class="att-dialog-actions">
        <button type="button" class="btn btn-outline"
                onclick="document.getElementById('delete-dialog').close()">
          {{ t('common.cancel') }}
        </button>
        <button type="submit" class="btn btn-outline btn-danger-text">
          {{ t('events.delete') }}
        </button>
      </footer>
    </form>
  </article>
</dialog>
<script>
function openDeleteDialog() {
  document.getElementById('delete-dialog').showModal();
}
{% if future_count > 0 %}
document.getElementById('delete-dialog-form').querySelectorAll('input[name=scope]').forEach(function(r) {
  r.addEventListener('change', function() {
    document.getElementById('delete-future-warning').style.display =
      this.value === 'future' ? 'block' : 'none';
  });
});
{% endif %}
</script>
{% endif %}
```

- [ ] **Step 3: Start the dev server and verify visually**

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 7000
```

Navigate to a recurring event detail page. Click ⋯ → Delete Event. Verify:
- Dialog appears with two radio options.
- Selecting "future" shows the warning paragraph.
- Cancelling closes the dialog without navigating.
- Navigate to a non-recurring event — dialog shows simple confirm text (no radios).

- [ ] **Step 4: Commit**

```bash
git add templates/events/detail.html
git commit -m "feat: replace event delete form with recurrence-aware dialog"
```

---

## Task 5: Final check

- [ ] **Run full test suite**

```bash
pytest -v
ruff check . && ruff format .
```

Expected: all tests pass, no lint errors.

- [ ] **Final commit**

```bash
git push
```
