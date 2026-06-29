# Calendar Month Grid View — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Interactive month-grid calendar for events with server-rendered grid and vanilla JS navigation.

**Architecture:** New route module `routes/calendar_view.py` with 2 endpoints (full calendar page + day detail API). New template, JS file, CSS additions. Role-based visibility matching existing list view. No new dependencies.

**Tech Stack:** FastAPI, Jinja2, Pico CSS, vanilla JS (fetch API)

---

### Task 1: Route module — calendar view + day detail API

**Files:**
- Create: `routes/calendar_view.py`
- Test: `tests/test_calendar_view.py` (partial — tests for basic routing)

- [ ] **Step 1: Write failing test for calendar page**

```python
# tests/test_calendar_view.py
from datetime import datetime

import pytest

from models.event import Event


@pytest.fixture
def make_event(db):
    """Factory fixture — creates an Event and returns it."""
    def _make(
        title="Test Event",
        event_date="2026-06-15",
        event_time="18:30",
        event_type="training",
        team_id=None,
        season_id=None,
        location=None,
        meeting_time=None,
    ):
        ev = Event(
            title=title,
            event_type=event_type,
            event_date=datetime.strptime(event_date, "%Y-%m-%d").date(),
            event_time=datetime.strptime(event_time, "%H:%M").time() if event_time else None,
            location=location,
            meeting_time=datetime.strptime(meeting_time, "%H:%M").time() if meeting_time else None,
            team_id=team_id,
            season_id=season_id,
        )
        db.add(ev)
        db.commit()
        return ev
    return _make


def test_calendar_page_returns_200(client):
    response = client.get("/events/calendar")
    assert response.status_code == 200


def test_calendar_page_public(client):
    response = client.get("/events/calendar")
    assert response.status_code == 200


def test_calendar_page_with_events(admin_client, db, make_event):
    event = make_event(event_date="2026-06-15")
    response = admin_client.get("/events/calendar?year=2026&month=6")
    assert response.status_code == 200
    assert event.title.encode() in response.content


def test_calendar_empty_month(client):
    response = client.get("/events/calendar?year=2026&month=1")
    assert response.status_code == 200


def test_calendar_month_navigation(client):
    response = client.get("/events/calendar?year=2026&month=7")
    assert response.status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_calendar_view.py -v`
Expected: ModuleNotFoundError or 404 (route not registered yet)

- [ ] **Step 3: Create `routes/calendar_view.py`** with calendar page handler

```python
"""routes/calendar_view.py — Calendar month grid view."""

from __future__ import annotations

import calendar
from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.templates import render
from models.event import Event
from models.player import Player
from models.season import Season
from models.team import Team
from models.user import User
from routes._auth_helpers import optional_user, get_coach_teams

router = APIRouter()

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
MONTH_NAMES = [
    "", "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]


def _filter_events_query(q, user: User | None, db: Session):
    """Apply role-based event visibility — same logic as events_list."""
    if user is None:
        return q  # public: no filter (events are all public)
    if user.is_admin:
        return q
    if user.is_coach:
        my_team_ids = get_coach_teams(user, db)
        return q.filter(Event.team_id.in_(my_team_ids))
    # member: resolve teams via player
    player = (
        db.query(Player)
        .filter(
            Player.user_id == user.id,
            Player.archived_at.is_(None),
        )
        .first()
    )
    if player:
        from models.player_team import PlayerTeam
        my_team_ids = {
            row[0]
            for row in db.query(PlayerTeam.team_id)
            .filter(PlayerTeam.player_id == player.id)
            .all()
        }
        return q.filter(Event.team_id.in_(my_team_ids))
    return q.filter(Event.team_id.is_(None))  # no teams → no events


@router.get("/events/calendar", include_in_schema=False)
async def calendar_view(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    team_id: str | None = None,
    season_id: str | None = None,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    today = date.today()
    if year is None:
        year = today.year
    if month is None:
        month = today.month

    # Validate month
    if month < 1:
        month = 1
        year -= 1
    elif month > 12:
        month = 12
        year += 1

    # Calendar grid boundaries
    cal = calendar.Calendar(firstweekday=0)
    month_dates = cal.monthdatescalendar(year, month)
    grid_start = month_dates[0][0]
    grid_end = month_dates[-1][-1]

    # Compute prev/next month
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year
    if month == 12:
        next_month, next_year = 1, year + 1
    else:
        next_month, next_year = month + 1, year

    # Query events
    q = db.query(Event).filter(Event.event_date >= grid_start, Event.event_date <= grid_end)
    season_id_val = int(season_id) if season_id and season_id.strip() else None
    team_id_val = int(team_id) if team_id and team_id.strip() else None
    if season_id_val is not None:
        q = q.filter(Event.season_id == season_id_val)
    if team_id_val is not None:
        q = q.filter(Event.team_id == team_id_val)
    q = _filter_events_query(q, user, db)
    q = q.order_by(Event.event_date.asc(), Event.event_time.asc())
    events = q.all()

    # Index events by date
    events_by_date: dict[date, list[Event]] = {}
    for ev in events:
        events_by_date.setdefault(ev.event_date, []).append(ev)

    # Attach events to day cells
    weeks = []
    for week in month_dates:
        row = []
        for d in week:
            row.append({
                "date": d,
                "is_current_month": d.month == month,
                "is_today": d == today,
                "events": events_by_date.get(d, []),
            })
        weeks.append(row)

    seasons = db.query(Season).order_by(Season.name).all()
    teams = db.query(Team).order_by(Team.name).all()

    return render(
        request,
        "events/calendar.html",
        {
            "user": user,
            "weeks": weeks,
            "year": year,
            "month": month,
            "month_name": MONTH_NAMES[month],
            "prev_month": prev_month,
            "prev_year": prev_year,
            "next_month": next_month,
            "next_year": next_year,
            "weekdays": WEEKDAYS,
            "seasons": seasons,
            "teams": teams,
            "selected_season_id": season_id_val,
            "selected_team_id": team_id_val,
            "today": today,
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass with the handler**

Run: `pytest tests/test_calendar_view.py -v`
Expected: Tests pass (errors if route not registered yet — that's fine, Task 5 handles registration)

- [ ] **Step 5: Add day detail API endpoint** to `routes/calendar_view.py`

```python
@router.get("/api/events/calendar-day", include_in_schema=False)
async def calendar_day_detail(
    request: Request,
    date_str: str,
    team_id: str | None = None,
    season_id: str | None = None,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    from fastapi.responses import HTMLResponse

    try:
        day = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return HTMLResponse("<p>Invalid date</p>", status_code=400)

    q = db.query(Event).filter(Event.event_date == day)
    season_id_val = int(season_id) if season_id and season_id.strip() else None
    team_id_val = int(team_id) if team_id and team_id.strip() else None
    if season_id_val is not None:
        q = q.filter(Event.season_id == season_id_val)
    if team_id_val is not None:
        q = q.filter(Event.team_id == team_id_val)
    q = _filter_events_query(q, user, db)
    q = q.order_by(Event.event_time.asc())
    events = q.all()

    lines = [f'<div class="day-detail-header">Events on {day.strftime("%B %d, %Y")}</div>']
    if not events:
        lines.append('<p class="day-detail-empty">No events on this date.</p>')
    else:
        lines.append('<ul class="day-detail-list">')
        for ev in events:
            time_str = ""
            display_time = ev.meeting_time or ev.event_time
            if display_time:
                time_str = display_time.strftime("%H:%M ") if display_time else ""
            lines.append(
                f'<li class="day-detail-item event-type-{ev.event_type}">'
                f'<a href="/events/{ev.id}">{time_str}{ev.title}</a>'
                f'</li>'
            )
        lines.append("</ul>")
    lines.append(f'<a href="/events?date_from={day}&date_to={day}" class="day-detail-all">View all</a>')

    return HTMLResponse("".join(lines))
```

- [ ] **Step 6: Write and run day API tests**

```python
# Add to tests/test_calendar_view.py

def test_calendar_day_api_returns_events(admin_client, db, make_event):
    event = make_event(event_date="2026-06-15")
    response = admin_client.get("/api/events/calendar-day?date_str=2026-06-15")
    assert response.status_code == 200
    assert event.title in response.text

def test_calendar_day_api_no_events(client):
    response = client.get("/api/events/calendar-day?date_str=2026-06-15")
    assert response.status_code == 200
    assert "No events on this date" in response.text

def test_calendar_day_api_invalid_date(client):
    response = client.get("/api/events/calendar-day?date_str=not-a-date")
    assert response.status_code == 400
```

Run: `pytest tests/test_calendar_view.py::test_calendar_day_api_returns_events -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add routes/calendar_view.py tests/test_calendar_view.py
git commit -m "feat: add calendar view route and day detail API"
```

---

### Task 2: Calendar template

**Files:**
- Create: `templates/events/calendar.html`

- [ ] **Step 1: Write the calendar template**

```html
{# templates/events/calendar.html #}
{% extends "base.html" %}
{% block title %}Calendar — {{ app_name }}{% endblock %}
{% block head_extra %}
<link rel="stylesheet" href="/static/css/calendar.css?v={{ static_v }}">
{% endblock %}
{% block breadcrumb %}
<nav class="breadcrumb"><a href="/dashboard">{{ t('common.home') }}</a><span class="breadcrumb-sep"></span><span>{{ t('nav.events') }}</span></nav>
{% endblock %}
{% block content %}
<div class="page-header">
  <h2>{{ t('calendar.' + month_name) }} {{ year }}</h2>
  <div class="page-header-actions">
    <a href="/events" class="btn">{{ t('events.list_view') }}</a>
    {% if user and (user.is_admin or user.is_coach) %}
    <a href="/events/new" class="btn btn-primary">{{ t('events.new') }}</a>
    {% endif %}
  </div>
</div>

<form method="get" action="{{ request.url.path }}" class="filter-row" id="calendar-filters">
  <input type="hidden" name="year" value="{{ year }}">
  <input type="hidden" name="month" value="{{ month }}">
  <label>{{ t('events.season') }}
    <select name="season_id" onchange="this.form.submit()">
      <option value="">{{ t('events.all_seasons') }}</option>
      {% for s in seasons %}
        <option value="{{ s.id }}" {% if selected_season_id == s.id %}selected{% endif %}>{{ s.name }}</option>
      {% endfor %}
    </select>
  </label>
  <label>{{ t('events.team') }}
    <select name="team_id" onchange="this.form.submit()">
      <option value="">{{ t('events.all_teams') }}</option>
      {% for team in teams %}
        <option value="{{ team.id }}" {% if selected_team_id == team.id %}selected{% endif %}>{{ team.name }}</option>
      {% endfor %}
    </select>
  </label>
</form>

<div class="calendar-nav">
  <a href="/events/calendar?year={{ prev_year }}&month={{ prev_month }}&season_id={{ selected_season_id or '' }}&team_id={{ selected_team_id or '' }}" class="calendar-nav-btn" data-year="{{ prev_year }}" data-month="{{ prev_month }}">&lsaquo; {{ t('calendar.prev_month') }}</a>
  <span class="calendar-nav-title">{{ t('calendar.' + month_name) }} {{ year }}</span>
  <a href="/events/calendar?year={{ next_year }}&month={{ next_month }}&season_id={{ selected_season_id or '' }}&team_id={{ selected_team_id or '' }}" class="calendar-nav-btn" data-year="{{ next_year }}" data-month="{{ next_month }}">{{ t('calendar.next_month') }} &rsaquo;</a>
</div>

<div class="calendar-grid" id="calendar-grid">
  <div class="calendar-header-row">
    {% for wd in weekdays %}
    <div class="calendar-header-day">{{ t('calendar.' + wd) }}</div>
    {% endfor %}
  </div>
  {% for week in weeks %}
  <div class="calendar-week">
    {% for day in week %}
    <div class="calendar-day-cell {% if not day.is_current_month %}calendar-day-other{% endif %} {% if day.is_today %}calendar-day-today{% endif %}" data-date="{{ day.date.isoformat() }}">
      <div class="calendar-day-number">{{ day.date.day }}</div>
      <div class="calendar-day-events">
        {% for ev in day.events %}
        {% set _time = ev.meeting_time or ev.event_time %}
        <a href="/events/{{ ev.id }}" class="calendar-event-item event-type-{{ ev.event_type }}" title="{{ ev.title }}">
          {% if _time %}{{ _time.strftime('%H:%M') }} {% endif %}{{ ev.title }}
        </a>
        {% endfor %}
      </div>
    </div>
    {% endfor %}
  </div>
  {% endfor %}
</div>

<div id="calendar-day-detail" class="calendar-day-detail hidden"></div>
{% endblock %}
{% block scripts_extra %}
<script src="/static/js/calendar.js?v={{ static_v }}"></script>
{% endblock %}
```

- [ ] **Step 2: Verify template renders** (manual check after route is registered)

Open `/events/calendar` in browser. Verify grid renders with correct month.

- [ ] **Step 3: Commit**

```bash
git add templates/events/calendar.html
git commit -m "feat: add calendar month grid template"
```

---

### Task 3: CSS styles for calendar

**Files:**
- Create: `static/css/calendar.css`

- [ ] **Step 1: Create `static/css/calendar.css`**

```css
/* Calendar grid */
.calendar-grid {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--tp-border);
  border-radius: var(--tp-radius);
  overflow: hidden;
  margin-bottom: 1rem;
}

.calendar-header-row,
.calendar-week {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
}

.calendar-header-row {
  background: var(--tp-surface);
  border-bottom: 1px solid var(--tp-border);
}

.calendar-header-day {
  padding: 0.4rem 0.3rem;
  text-align: center;
  font-weight: 600;
  font-size: 0.8rem;
  color: var(--tp-muted);
  text-transform: uppercase;
}

.calendar-week + .calendar-week {
  border-top: 1px solid var(--tp-border);
}

.calendar-day-cell {
  min-height: 80px;
  padding: 0.25rem;
  border-right: 1px solid var(--tp-border);
  cursor: pointer;
  position: relative;
  background: #fff;
}

.calendar-day-cell:last-child {
  border-right: none;
}

.calendar-day-other {
  background: var(--tp-surface);
}

.calendar-day-other .calendar-day-number {
  color: var(--tp-muted);
  opacity: 0.5;
}

.calendar-day-today .calendar-day-number {
  background: var(--tp-primary);
  color: #fff;
  border-radius: 50%;
  width: 1.6rem;
  height: 1.6rem;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}

.calendar-day-number {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--tp-muted);
  margin-bottom: 0.15rem;
}

.calendar-day-events {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.calendar-event-item {
  display: block;
  font-size: 0.7rem;
  padding: 0.1rem 0.25rem;
  border-radius: 0.2rem;
  text-decoration: none;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
  border-left: 3px solid transparent;
}

.calendar-event-item:hover {
  text-decoration: underline;
}

.event-type-match {
  border-left-color: var(--tp-danger);
  background: rgba(192, 57, 43, 0.08);
}

.event-type-training {
  border-left-color: var(--tp-primary);
  background: rgba(26, 107, 196, 0.08);
}

.event-type-other {
  border-left-color: var(--tp-muted);
  background: rgba(108, 117, 125, 0.08);
}

.calendar-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0.75rem;
  padding: 0.4rem 0;
}

.calendar-nav-title {
  font-size: 1.1rem;
  font-weight: 700;
}

.calendar-nav-btn {
  text-decoration: none;
  font-size: 0.9rem;
  padding: 0.3rem 0.6rem;
  border: 1px solid var(--tp-border);
  border-radius: var(--tp-radius);
  color: var(--tp-primary);
}

.calendar-nav-btn:hover {
  background: var(--tp-surface);
}

/* Day detail panel */
.calendar-day-detail {
  border: 1px solid var(--tp-border);
  border-radius: var(--tp-radius);
  padding: 0.75rem;
  margin-bottom: 1rem;
  background: #fff;
}

.calendar-day-detail.hidden {
  display: none;
}

.day-detail-header {
  font-weight: 700;
  font-size: 1rem;
  margin-bottom: 0.5rem;
}

.day-detail-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.day-detail-item {
  padding: 0.3rem 0.4rem;
  border-left: 3px solid transparent;
  margin-bottom: 0.2rem;
}

.day-detail-item a {
  text-decoration: none;
  color: inherit;
}

.day-detail-item a:hover {
  text-decoration: underline;
}

.day-detail-empty {
  color: var(--tp-muted);
  font-style: italic;
}

.day-detail-all {
  display: inline-block;
  margin-top: 0.5rem;
  font-size: 0.85rem;
}

/* Responsive: stack days into single column on small screens */
@media (max-width: 600px) {
  .calendar-day-cell {
    min-height: auto;
    padding: 0.4rem;
  }

  .calendar-header-row,
  .calendar-week {
    grid-template-columns: repeat(7, 1fr);
  }

  .calendar-event-item {
    font-size: 0.65rem;
  }

  .calendar-header-day {
    font-size: 0.65rem;
    padding: 0.25rem 0.15rem;
  }
}
```

- [ ] **Step 2: Verify styles work** (browser check)

Load `/events/calendar`, confirm grid layout, event coloring, hover effects, today highlight.

- [ ] **Step 3: Commit**

```bash
git add static/css/calendar.css
git commit -m "feat: add calendar CSS styles"
```

---

### Task 4: JavaScript enhancements

**Files:**
- Create: `static/js/calendar.js`

- [ ] **Step 1: Create `static/js/calendar.js`**

```javascript
(function () {
  'use strict';

  const grid = document.getElementById('calendar-grid');
  const detailPanel = document.getElementById('calendar-day-detail');
  const filtersForm = document.getElementById('calendar-filters');

  if (!grid) return;

  // ── Month navigation via fetch (no full reload) ──
  document.querySelectorAll('.calendar-nav-btn').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      var year = btn.getAttribute('data-year');
      var month = btn.getAttribute('data-month');
      var filters = filtersForm ? new URLSearchParams(new FormData(filtersForm)) : new URLSearchParams();
      filters.set('year', year);
      filters.set('month', month);
      fetch('/events/calendar?' + filters.toString(), { headers: { 'Accept': 'text/html' } })
        .then(function (r) { return r.text(); })
        .then(function (html) {
          var parser = new DOMParser();
          var doc = parser.parseFromString(html, 'text/html');
          var newGrid = doc.getElementById('calendar-grid');
          var newDetail = doc.getElementById('calendar-day-detail');
          var newNav = doc.querySelector('.calendar-nav');
          if (newGrid) grid.innerHTML = newGrid.innerHTML;
          if (newDetail && detailPanel) detailPanel.outerHTML = newDetail.outerHTML;
          if (newNav) {
            var oldNav = document.querySelector('.calendar-nav');
            if (oldNav) oldNav.innerHTML = newNav.innerHTML;
          }
          history.pushState({ year: year, month: month }, '', '/events/calendar?' + filters.toString());
          attachDayClickHandlers();
          updateNavButtons();
        })
        .catch(function (err) { console.error('Calendar nav error:', err); });
    });
  });

  // ── Day click handler ──
  function attachDayClickHandlers() {
    document.querySelectorAll('.calendar-day-cell').forEach(function (cell) {
      cell.addEventListener('click', function (e) {
        // Don't open day detail if clicking on an event link
        if (e.target.closest('.calendar-event-item')) return;
        var date = cell.getAttribute('data-date');
        if (!date) return;
        var filters = filtersForm ? new URLSearchParams(new FormData(filtersForm)) : new URLSearchParams();
        fetch('/api/events/calendar-day?' + filters.toString() + '&date_str=' + encodeURIComponent(date))
          .then(function (r) { return r.text(); })
          .then(function (html) {
            if (detailPanel) {
              detailPanel.innerHTML = html;
              detailPanel.classList.remove('hidden');
            }
          })
          .catch(function (err) { console.error('Day detail error:', err); });
      });
    });
  }

  // ── Update nav button data attributes after fetch ──
  function updateNavButtons() {
    var navBtns = document.querySelectorAll('.calendar-nav-btn');
    var urlParams = new URLSearchParams(window.location.search);
    var year = urlParams.get('year') || '';
    var month = urlParams.get('month') || '';
    if (year && month) {
      var y = parseInt(year, 10);
      var m = parseInt(month, 10);
      if (navBtns.length >= 2) {
        var prevM = m === 1 ? 12 : m - 1;
        var prevY = m === 1 ? y - 1 : y;
        var nextM = m === 12 ? 1 : m + 1;
        var nextY = m === 12 ? y + 1 : y;
        navBtns[0].setAttribute('data-year', prevY);
        navBtns[0].setAttribute('data-month', prevM);
        navBtns[1].setAttribute('data-year', nextY);
        navBtns[1].setAttribute('data-month', nextM);
      }
    }
  }

  // ── Close day panel on outside click ──
  document.addEventListener('click', function (e) {
    if (detailPanel && !detailPanel.classList.contains('hidden')) {
      if (!detailPanel.contains(e.target) && !e.target.closest('.calendar-day-cell')) {
        detailPanel.classList.add('hidden');
      }
    }
  });

  // ── Initialise ──
  attachDayClickHandlers();
})();
```

- [ ] **Step 2: Verify JS works** (manual browser test)

1. Load `/events/calendar`
2. Click prev/next month — grid updates without page reload
3. Click day cell — detail panel appears below grid
4. Click event in day cell — navigates to event detail
5. Click outside detail panel — panel hides

- [ ] **Step 3: Commit**

```bash
git add static/js/calendar.js
git commit -m "feat: add calendar JS navigation and day detail"
```

---

### Task 5: Register route + update nav

**Files:**
- Modify: `app/main.py`
- Modify: `templates/base.html`

- [ ] **Step 1: Add route to `_routers` in `app/main.py`**

```python
# Add to the _routers list (after events):
("routes.calendar_view", "", "events"),
```

Place it right after the `("routes.events", "/events", "events")` entry.

- [ ] **Step 2: Update nav link in `templates/base.html`**

Change line:
```html
<li><a href="/events" class="{% if path.startswith('/events') %}nav-active{% endif %}">{{ t('nav.events') }}</a></li>
```
To:
```html
<li><a href="/events/calendar" class="{% if path.startswith('/events') %}nav-active{% endif %}">{{ t('nav.events') }}</a></li>
```

- [ ] **Step 3: Verify route registration**

Run: `python -c "from app.main import app; routes = [(r.path, r.name) for r in app.routes]; print([r for r in routes if 'calendar' in str(r[0])])"`
Expected: Shows both `/events/calendar` and `/api/events/calendar-day` in the route list.

- [ ] **Step 4: Run existing tests to verify no regressions**

Run: `pytest tests/test_events.py -v`
Expected: All pass

- [ ] **Step 5: Run new calendar tests**

Run: `pytest tests/test_calendar_view.py -v`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add app/main.py templates/base.html
git commit -m "feat: register calendar view route and update nav link"
```

---

### Task 6: Full test suite

**Files:**
- Modify: `tests/test_calendar_view.py`

- [ ] **Step 1: Write comprehensive tests**

```python
"""tests/test_calendar_view.py — Calendar month grid tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from models.event import Event


@pytest.fixture
def make_event(db):
    """Factory fixture — creates an Event and returns it."""
    def _make(
        title="Test Event",
        event_date="2026-06-15",
        event_time="18:30",
        event_type="training",
        team_id=None,
        season_id=None,
        location=None,
        meeting_time=None,
    ):
        ev = Event(
            title=title,
            event_type=event_type,
            event_date=datetime.strptime(event_date, "%Y-%m-%d").date(),
            event_time=datetime.strptime(event_time, "%H:%M").time() if event_time else None,
            location=location,
            meeting_time=datetime.strptime(meeting_time, "%H:%M").time() if meeting_time else None,
            team_id=team_id,
            season_id=season_id,
        )
        db.add(ev)
        db.commit()
        return ev
    return _make


# ── Calendar page ──

def test_calendar_page_returns_200(client):
    response = client.get("/events/calendar")
    assert response.status_code == 200


def test_calendar_page_public(client):
    response = client.get("/events/calendar")
    assert response.status_code == 200


def test_calendar_page_with_events(admin_client, db, make_event):
    ev = make_event(event_date="2026-06-15")
    response = admin_client.get("/events/calendar?year=2026&month=6")
    assert response.status_code == 200
    assert ev.title.encode() in response.content


def test_calendar_empty_month(client):
    response = client.get("/events/calendar?year=2026&month=1")
    assert response.status_code == 200


def test_calendar_month_navigation(client):
    response = client.get("/events/calendar?year=2026&month=7")
    assert response.status_code == 200


def test_calendar_invalid_month_clamps(client):
    response = client.get("/events/calendar?year=2026&month=13")
    assert response.status_code == 200


# ── Day detail API ──

def test_calendar_day_api_returns_events(admin_client, db, make_event):
    ev = make_event(event_date="2026-06-15")
    response = admin_client.get("/api/events/calendar-day?date_str=2026-06-15")
    assert response.status_code == 200
    assert ev.title in response.text


def test_calendar_day_api_no_events(client):
    response = client.get("/api/events/calendar-day?date_str=2026-06-15")
    assert response.status_code == 200
    assert "No events on this date." in response.text


def test_calendar_day_api_invalid_date(client):
    response = client.get("/api/events/calendar-day?date_str=not-a-date")
    assert response.status_code == 400
```

- [ ] **Step 2: Run all calendar tests**

Run: `pytest tests/test_calendar_view.py -v`
Expected: All tests pass

- [ ] **Step 3: Run full test suite to check regressions**

Run: `pytest -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_calendar_view.py
git commit -m "test: add calendar view tests"
```

---

### Task 7: i18n translations — add calendar-related translation keys

**Files:**
- Modify: `app/i18n/translations/*.json`

- [ ] **Step 1: Find existing translation files and add keys**

Search for translation files:
```
grep -r "list_view" app/i18n/ --include="*.json" -l
```

Add the following keys to each locale's translation JSON:

```json
{
  "calendar.mon": "Mon",
  "calendar.tue": "Tue",
  "calendar.wed": "Wed",
  "calendar.thu": "Thu",
  "calendar.fri": "Fri",
  "calendar.sat": "Sat",
  "calendar.sun": "Sun",
  "calendar.prev_month": "Prev",
  "calendar.next_month": "Next",
  "calendar.january": "January",
  "calendar.february": "February",
  "calendar.march": "March",
  "calendar.april": "April",
  "calendar.may": "May",
  "calendar.june": "June",
  "calendar.july": "July",
  "calendar.august": "August",
  "calendar.september": "September",
  "calendar.october": "October",
  "calendar.november": "November",
  "calendar.december": "December",
  "events.list_view": "List View"
}
```

For Italian locale (`it.json`):
```json
{
  "calendar.mon": "Lun",
  "calendar.tue": "Mar",
  "calendar.wed": "Mer",
  "calendar.thu": "Gio",
  "calendar.fri": "Ven",
  "calendar.sat": "Sab",
  "calendar.sun": "Dom",
  "calendar.prev_month": "Prec",
  "calendar.next_month": "Succ",
  "calendar.january": "Gennaio",
  "calendar.february": "Febbraio",
  "calendar.march": "Marzo",
  "calendar.april": "Aprile",
  "calendar.may": "Maggio",
  "calendar.june": "Giugno",
  "calendar.july": "Luglio",
  "calendar.august": "Agosto",
  "calendar.september": "Settembre",
  "calendar.october": "Ottobre",
  "calendar.november": "Novembre",
  "calendar.december": "Dicembre",
  "events.list_view": "Vista Elenco"
}
```

For other locales (FR, DE), add appropriate translations or fallback to English.

- [ ] **Step 2: Verify translations load**

Run: `pytest -v`
Expected: No i18n-related failures

- [ ] **Step 3: Commit**

```bash
git add app/i18n/
git commit -m "feat: add calendar i18n translations"
```
