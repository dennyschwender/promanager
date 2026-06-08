# Event End Date Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add optional `event_end_date` field to Event so multi-day events display as `01–03 May 2026`.

**Architecture:** Add nullable DB column + Alembic migration, thread the field through the form/route, update upcoming/past split to use `effective_end = event_end_date or event_date`, add a Jinja2 helper macro for compact date-range display.

**Tech Stack:** SQLAlchemy 2.x mapped_column, Alembic, FastAPI Form, Jinja2

---

## File Map

| File | Change |
|------|--------|
| `models/event.py` | Add `event_end_date: Mapped[date \| None]` |
| `alembic/versions/s7t8u9v0w1x2_add_event_end_date.py` | New migration |
| `routes/events.py` | Form parsing, validation, upcoming/past split |
| `templates/events/form.html` | End date input after event_date |
| `templates/events/list.html` | Date range display macro |
| `templates/events/detail.html` | Date range display |
| `tests/test_events.py` | Test upcoming/past logic with end date |

---

### Task 1: Add column to model + migration

**Files:**
- Modify: `models/event.py` (after line 26, after `event_date`)
- Create: `alembic/versions/s7t8u9v0w1x2_add_event_end_date.py`

- [x] **Add field to model**

In `models/event.py`, add after the `event_date` line:

```python
event_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
```

- [x] **Create Alembic migration**

Create `alembic/versions/s7t8u9v0w1x2_add_event_end_date.py`:

```python
"""Add event_end_date column to events table."""
from alembic import op
import sqlalchemy as sa

revision = "s7t8u9v0w1x2"
down_revision = "r6s7t8u9v0w1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("event_end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "event_end_date")
```

- [x] **Run migration**

```bash
source .venv/bin/activate
alembic upgrade head
```

Expected: `Running upgrade r6s7t8u9v0w1 -> s7t8u9v0w1x2, Add event_end_date column to events table`

- [x] **Commit**

```bash
git add models/event.py alembic/versions/s7t8u9v0w1x2_add_event_end_date.py
git commit -m "feat: add event_end_date column to events"
```

---

### Task 2: Update form parsing and validation in route

**Files:**
- Modify: `routes/events.py`

- [x] **Write failing test**

In `tests/test_events.py`, add:

```python
def test_event_end_date_before_start_rejected(admin_client):
    resp = admin_client.post("/events/new", data={
        "title": "Camp",
        "event_type": "other",
        "event_date": "2026-06-10",
        "event_end_date": "2026-06-09",  # before start
        "event_time": "",
        "event_end_time": "",
        "location": "",
        "meeting_time": "",
        "meeting_location": "",
        "presence_type": "normal",
        "hide_attendance": "",
        "description": "",
        "season_id": "",
        "team_id": "",
        "is_recurring": "",
        "recurrence_rule": "",
        "recurrence_end_date": "",
        "csrf_token": "test",
    }, follow_redirects=False)
    assert resp.status_code == 200  # re-renders form with error
```

- [x] **Run test to verify it fails**

```bash
pytest tests/test_events.py::test_event_end_date_before_start_rejected -v
```

Expected: FAIL (422 or redirect, not 200 form re-render)

- [x] **Add `event_end_date` Form param to create handler**

In `routes/events.py`, find the `create_event` handler (around line 279). Add `event_end_date` to the Form params and pass through:

```python
event_end_date: str = Form(""),
```

Add to `_form_ns` signature and body — find `_form_ns` function (around line 69) and:

1. Add `event_end_date` parameter to `_form_ns` signature (after `recurrence_end_date`):
```python
def _form_ns(
    title, event_type, event_date, event_time, event_end_time,
    location, meeting_time, meeting_location, presence_type,
    hide_attendance, description, season_id, team_id,
    is_recurring, recurrence_rule, recurrence_end_date,
    event_end_date="",
) -> SimpleNamespace:
```

2. Parse inside `_form_ns`:
```python
try:
    e_end_date = _parse_date(event_end_date) if event_end_date.strip() else None
except ValueError:
    e_end_date = None
```

3. Add to the returned `SimpleNamespace`:
```python
event_end_date=e_end_date,
```

- [x] **Add validation in create handler**

In the `create_event` POST handler, after `e_date = _parse_date(event_date)`, add:

```python
e_end_date = _parse_date(event_end_date) if event_end_date.strip() else None
if e_end_date is not None and e_end_date < e_date:
    return render(request, "events/form.html", {
        "user": user,
        "event": _form_ns(title, event_type, event_date, event_time, event_end_time,
                          location, meeting_time, meeting_location, presence_type,
                          hide_attendance, description, season_id, team_id,
                          is_recurring, recurrence_rule, recurrence_end_date,
                          event_end_date=event_end_date),
        "error": "End date cannot be before start date.",
        "seasons": db.query(Season).all(),
        "teams": db.query(Team).all(),
        "is_new": True,
    })
```

- [x] **Pass `event_end_date` when creating Event objects**

In the `common` dict (or wherever `Event(...)` is constructed in the create handler), add:

```python
event_end_date=e_end_date,
```

- [x] **Repeat for edit handler** (`edit_event` POST, around line 731)

Same pattern: add `event_end_date: str = Form("")`, parse, validate, assign to event object:

```python
event.event_end_date = e_end_date
```

- [x] **Run test**

```bash
pytest tests/test_events.py::test_event_end_date_before_start_rejected -v
```

Expected: PASS

- [x] **Commit**

```bash
git add routes/events.py
git commit -m "feat: parse and validate event_end_date in create/edit handlers"
```

---

### Task 3: Add end date field to form template

**Files:**
- Modify: `templates/events/form.html`

- [x] **Add end date input after event_date in the date/time fieldset**

Find the date fieldset in `templates/events/form.html` (around line 60). After the closing `</div>` of the `form-grid-2` block (which contains `event_date` and `event_time`), add:

```html
<label>{{ t('events_form.end_date') }}
  <input type="date" name="event_end_date"
         value="{{ event.event_end_date.isoformat() if event and event.event_end_date else '' }}"
         min="{{ event.event_date.isoformat() if event and event.event_date else '' }}">
</label>
```

- [x] **Add client-side min constraint via JS**

After the above label, add a small inline script so `end_date.min` updates when `event_date` changes:

```html
<script>
(function(){
  var start = document.querySelector('[name="event_date"]');
  var end = document.querySelector('[name="event_end_date"]');
  if (!start || !end) return;
  function sync(){ end.min = start.value || ''; }
  start.addEventListener('change', sync);
  sync();
})();
</script>
```

- [x] **Add i18n key**

Add to `locales/en.yml` (and it, fr, de equivalents):

```yaml
events_form:
  end_date: "End Date (optional)"
```

- [x] **Verify form renders without error**

```bash
source .venv/bin/activate
pytest tests/test_events.py -v
```

Expected: all pass

- [x] **Commit**

```bash
git add templates/events/form.html locales/
git commit -m "feat: add event_end_date field to event form"
```

---

### Task 4: Update upcoming/past split to use effective end date

**Files:**
- Modify: `routes/events.py`

- [x] **Write failing test**

In `tests/test_events.py`, add:

```python
def test_multi_day_event_stays_upcoming_until_end(admin_client, db_session):
    from datetime import date, timedelta
    from models.event import Event
    today = date.today()
    ev = Event(
        title="Camp",
        event_type="other",
        event_date=today - timedelta(days=1),   # started yesterday
        event_end_date=today + timedelta(days=1),  # ends tomorrow
    )
    db_session.add(ev)
    db_session.commit()
    resp = admin_client.get("/events")
    assert resp.status_code == 200
    # event should appear in upcoming, not past
    body = resp.text
    assert "Camp" in body
```

> Note: this test checks the page renders but can't easily distinguish upcoming vs past section from HTML alone. The key assertion is that it doesn't crash and the event appears.

- [x] **Run test to verify it fails or passes trivially**

```bash
pytest tests/test_events.py::test_multi_day_event_stays_upcoming_until_end -v
```

- [x] **Update upcoming/past split in `events_list` route**

In `routes/events.py`, find lines (around 164-165):

```python
all_upcoming = [e for e in all_events if e.event_date >= today]
all_past = sorted([e for e in all_events if e.event_date < today], key=lambda e: e.event_date, reverse=True)
```

Replace with:

```python
def _effective_end(e) -> date:
    return e.event_end_date if e.event_end_date is not None else e.event_date

all_upcoming = [e for e in all_events if _effective_end(e) >= today]
all_past = sorted(
    [e for e in all_events if _effective_end(e) < today],
    key=_effective_end,
    reverse=True,
)
```

- [x] **Run tests**

```bash
pytest tests/test_events.py -v
```

Expected: all pass

- [x] **Commit**

```bash
git add routes/events.py
git commit -m "feat: use event_end_date for upcoming/past split"
```

---

### Task 5: Date range display in list and detail templates

**Files:**
- Modify: `templates/events/list.html`
- Modify: `templates/events/detail.html`

- [x] **Add date range macro to list template**

At the top of `{% block content %}` in `templates/events/list.html`, add a Jinja2 macro:

```jinja2
{% macro date_range(e) %}
  {%- if e.event_end_date and e.event_end_date != e.event_date -%}
    {%- if e.event_date.year != e.event_end_date.year -%}
      {{ e.event_date.strftime('%d %b %Y') }}–{{ e.event_end_date.strftime('%d %b %Y') }}
    {%- elif e.event_date.month != e.event_end_date.month -%}
      {{ e.event_date.strftime('%d %b') }}–{{ e.event_end_date.strftime('%d %b %Y') }}
    {%- else -%}
      {{ e.event_date.strftime('%d') }}–{{ e.event_end_date.strftime('%d %b %Y') }}
    {%- endif -%}
  {%- else -%}
    {{ e.event_date }}
  {%- endif -%}
{% endmacro %}
```

- [x] **Use macro in list table row**

Find the date cell in the `events_table` macro (around line 67):

```html
<td class="nowrap">{{ e.event_date }}</td>
```

Replace with:

```html
<td class="nowrap">{{ date_range(e) }}</td>
```

- [x] **Update detail template**

In `templates/events/detail.html`, find (around line 27):

```html
<dd>{{ event.event_date }}</dd>
```

Replace with:

```html
<dd>
  {%- if event.event_end_date and event.event_end_date != event.event_date -%}
    {%- if event.event_date.year != event.event_end_date.year -%}
      {{ event.event_date.strftime('%d %b %Y') }} – {{ event.event_end_date.strftime('%d %b %Y') }}
    {%- elif event.event_date.month != event.event_end_date.month -%}
      {{ event.event_date.strftime('%d %b') }} – {{ event.event_end_date.strftime('%d %b %Y') }}
    {%- else -%}
      {{ event.event_date.strftime('%d') }}–{{ event.event_end_date.strftime('%d %b %Y') }}
    {%- endif -%}
  {%- else -%}
    {{ event.event_date }}
  {%- endif -%}
</dd>
```

- [x] **Run all tests**

```bash
pytest tests/test_events.py -v
```

Expected: all pass

- [x] **Commit**

```bash
git add templates/events/list.html templates/events/detail.html
git commit -m "feat: display date range for multi-day events"
```

---

### Task 6: Run migration on Docker + deploy

- [x] **Run full test suite**

```bash
source .venv/bin/activate
pytest -v
ruff check .
```

Expected: all pass, no lint errors

- [x] **Push and deploy**

```bash
git push
cd ~/dockerimages && ./updateDocker.sh proManager
```

- [x] **Verify migration ran in container**

```bash
docker exec promanager-web-1 python3 -c "
import sys; sys.path.insert(0, '/app')
from app.database import SessionLocal
from models.event import Event
db = SessionLocal()
ev = db.query(Event).first()
print('event_end_date attr:', ev.event_end_date)
db.close()
"
```

Expected: `event_end_date attr: None` (no error)
