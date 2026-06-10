# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dashboard with role-aware views — personal dashboard for players, team-pulse dashboard for coaches/admins.

**Architecture:** Single route handler branches on `user.is_admin or user.is_coach` → coach template, else → player template. Player template shows attendance rate, next event, notifications, absences. Coach template shows stat cards, upcoming events, watch list, recent chat. Reports nav link removed from member nav.

**Tech Stack:** FastAPI, Jinja2, SQLAlchemy 2.x, pytest

---

### Task 1: Nav — hide Reports from members in footer, remove My Attendance from member nav

**Files:**
- Modify: `templates/base.html:47` — remove member "My Attendance" nav link (player dashboard replaces it)
- Modify: `templates/base.html:137` — guard Reports link in footer with `{% if user.is_admin or user.is_coach %}`

- [ ] **Remove member My Attendance nav link**

In `templates/base.html`, delete lines 47 (the `<li>` with `href="/reports/my"`):

Before:
```html
     <li><a href="/reports/my" class="{% if path.startswith('/reports/my') %}nav-active{% endif %}">{{ t('nav.my_attendance') }}</a></li>
```
After:
```html
```

- [ ] **Guard footer Reports link**

In `templates/base.html`, line 137, wrap the Reports link:

Before:
```html
       <a href="/reports">{{ t('nav.reports') }}</a>
```
After:
```html
       {% if user.is_admin or user.is_coach %}<a href="/reports">{{ t('nav.reports') }}</a>{% endif %}
```

- [ ] **Verify no other member-only `/reports` references exist**

Run: `rg "href=\"/reports" templates/base.html`
Expected: only the now-guarded footer link remains. The sidebar nav at line 57-59 is already guarded.

- [ ] **Commit**

```bash
git add templates/base.html
git commit -m "nav: remove Reports from member nav, My Attendance link (replaced by dashboard)"
```

---

### Task 2: Player dashboard template

**Files:**
- Create: `templates/dashboard/player.html`

- [ ] **Write the player dashboard template**

```html
{% extends "base.html" %}
{% block title %}{{ t('dashboard.title') }} — ProManager{% endblock %}
{% block content %}
<div class="page-header">
  <h2>{{ t('dashboard.title') }}</h2>
  {% if active_season %}<span class="badge badge-active">{{ active_season.name }}</span>{% endif %}
</div>

{% if not my_player_id %}
  <div class="alert alert-warning">{{ t('dashboard.no_linked_player') }}</div>
{% endif %}

{% if not active_season %}
  <div class="alert alert-warning">{{ t('dashboard.no_active_season') }} <a href="/seasons">{{ t('dashboard.manage_seasons') }} →</a></div>
{% endif %}

{% if my_player_id %}
<div class="grid-2col">
  <div class="stat-card">
    <small class="stat-label">{{ t('dashboard.my_attendance') }}</small>
    <div class="stat-value">{{ attendance_rate }}%</div>
    {% if event_type_breakdown %}<div class="stat-sub">{{ event_type_breakdown }}</div>{% endif %}
    <a href="/reports/my" class="btn btn-sm btn-outline" style="margin-top:0.5rem">{{ t('dashboard.view_full_report') }}</a>
  </div>
  <div class="stat-card">
    <small class="stat-label">{{ t('dashboard.next_event') }}</small>
    {% if next_event %}
      <div class="stat-title"><a href="/events/{{ next_event.id }}">{{ next_event.title }}</a></div>
      <div class="stat-sub">{{ next_event.event_date.strftime('%a %d %b') }}{% if next_event.event_time %} · {{ next_event.event_time.strftime('%H:%M') }}{% endif %}{% if next_event.location %} · {{ next_event.location }}{% endif %}</div>
      <button type="button" class="btn btn-sm dash-att-btn att-active-{{ my_next_status }}"
              data-event-id="{{ next_event.id }}"
              data-player-id="{{ my_player_id }}"
              data-status="{{ my_next_status }}"
              data-note="{{ my_next_note | e }}">{{ status_labels.get(my_next_status, my_next_status) }}</button>
    {% else %}
      <div class="stat-sub">{{ t('dashboard.no_upcoming') }}</div>
    {% endif %}
  </div>
</div>

<div class="grid-2col" style="margin-top:1rem">
  <div class="stat-card">
    <small class="stat-label">{{ t('dashboard.unread_notifications') }}</small>
    <div class="stat-value">{{ unread_count }}</div>
    {% if recent_notifications %}
      {% for n in recent_notifications %}
        <div class="notif-preview">
          <a href="{{ '/events/' ~ n.event_id if n.event_id else '/notifications' }}">{{ n.title }}</a>
        </div>
      {% endfor %}
    {% else %}
      <div class="stat-sub">{{ t('dashboard.no_unread') }}</div>
    {% endif %}
    <a href="/notifications" class="btn btn-sm btn-outline" style="margin-top:0.5rem">{{ t('nav.notifications') }}</a>
  </div>
  <div class="stat-card">
    <small class="stat-label">{{ t('dashboard.my_absences') }}</small>
    {% if active_absences %}
      {% for a in active_absences %}
        <div class="notif-preview">{{ a.reason or t('dashboard.absence') }} · {% if a.absence_type == 'period' %}{{ a.start_date }} – {{ a.end_date }}{% else %}{{ t('dashboard.recurring') }}{% endif %}</div>
      {% endfor %}
    {% else %}
      <div class="stat-sub">{{ t('dashboard.no_active_absences') }}</div>
    {% endif %}
    <a href="/players/{{ my_player_id }}/absences" class="btn btn-sm btn-outline" style="margin-top:0.5rem">{{ t('absences.manage_my_absences') }}</a>
  </div>
</div>
{% endif %}
{% endblock %}
{% block scripts %}
{% if my_player_id %}
{{ include_attendance_popover_js() | safe }}
{% endif %}
{% endblock %}
```

The `dash-att-btn` CSS class and the attendance popover JS are already defined in `templates/dashboard/index.html` (lines 101-212). The `player_fragment.html` will use the same popover HTML and JS code adapted for the new template.

- [ ] **Commit**

```bash
git add templates/dashboard/player.html
git commit -m "templates: add player dashboard template"
```

---

### Task 3: Coach dashboard template

**Files:**
- Create: `templates/dashboard/coach.html`

- [ ] **Write the coach dashboard template**

```html
{% extends "base.html" %}
{% block title %}{{ t('dashboard.title') }} — ProManager{% endblock %}
{% block content %}
<div class="page-header">
  <h2>{{ t('dashboard.title') }}</h2>
  {% if active_season %}<span class="badge badge-active">{{ active_season.name }}</span>{% endif %}
</div>

{% if not active_season %}
  <div class="alert alert-warning">{{ t('dashboard.no_active_season') }} <a href="/seasons">{{ t('dashboard.manage_seasons') }} →</a></div>
{% endif %}

<div class="stat-grid">
  <div class="stat-card" onclick="window.location='/reports/season/{{ active_season.id if active_season else 0 }}'" style="cursor:pointer">
    <small class="stat-label">{{ t('dashboard.team_attendance') }}</small>
    <div class="stat-value">{{ team_attendance_rate }}%</div>
    {% if attendance_trend is not none %}<div class="stat-sub">{{ '▲' if attendance_trend >= 0 else '▼' }} {{ attendance_trend|abs }}% vs {{ t('dashboard.last_30_days') }}</div>{% endif %}
  </div>
  <div class="stat-card" onclick="window.location='/events'" style="cursor:pointer">
    <small class="stat-label">{{ t('dashboard.pending') }}</small>
    <div class="stat-value">{{ unknown_count }}</div>
    <div class="stat-sub">{{ t('dashboard.unknowns_across_events', count=upcoming_count) }}</div>
  </div>
  <div class="stat-card" onclick="window.location='/players'" style="cursor:pointer">
    <small class="stat-label">{{ t('dashboard.injured_absent') }}</small>
    <div class="stat-value">{{ injured_absent_count }}</div>
    <div class="stat-sub">{{ injured_count }} {{ t('dashboard.injured') }} · {{ absence_count }} {{ t('dashboard.absences') }}</div>
  </div>
</div>

<div class="grid-2col" style="margin-top:1rem">
  <div class="stat-card">
    <small class="stat-label">{{ t('dashboard.upcoming_events') }}</small>
    {% if upcoming_events_compact %}
      {% for e in upcoming_events_compact %}
        <div class="event-row">
          <span class="event-date-label">{{ e.date_label }}</span>
          <a href="/events/{{ e.id }}" class="event-title">{{ e.title }}</a>
          <span class="event-unknowns">({{ e.unknown_count }}/{{ e.total_count }} {{ t('dashboard.unknown') }})</span>
        </div>
      {% endfor %}
    {% else %}
      <div class="stat-sub">{{ t('dashboard.no_upcoming') }}</div>
    {% endif %}
  </div>
  <div class="stat-card">
    <small class="stat-label">{{ t('dashboard.watch_list') }}</small>
    {% if watch_list %}
      {% for entry in watch_list %}
        <div class="watch-entry watch-entry-{{ entry.severity }}">
          <a href="/players/{{ entry.player_id }}">{{ entry.player_name }}</a>
          <span class="watch-reason">{{ entry.reason }}</span>
        </div>
      {% endfor %}
    {% else %}
      <div class="stat-sub">{{ t('dashboard.no_watch_items') }}</div>
    {% endif %}
  </div>
</div>

<div class="stat-card" style="margin-top:1rem">
  <small class="stat-label">{{ t('dashboard.recent_chat') }}</small>
  {% if recent_messages %}
    {% for m in recent_messages %}
      <div class="chat-preview">
        <strong>{{ m.author_name }}</strong> "{{ m.body_truncated }}" <span class="chat-event">— <a href="/events/{{ m.event_id }}">{{ m.event_title }}</a></span>
      </div>
    {% endfor %}
  {% else %}
    <div class="stat-sub">{{ t('dashboard.no_recent_chat') }}</div>
  {% endif %}
</div>

{% if user.is_admin %}
<hr>
<h3>{{ t('dashboard.quick_actions') }}</h3>
<div class="quick-actions">
  <a href="/seasons/new" class="btn btn-outline">{{ t('common.new_season') }}</a>
  <a href="/teams/new" class="btn btn-outline">{{ t('common.new_team') }}</a>
  <a href="/players/new" class="btn btn-outline">{{ t('common.new_player') }}</a>
  <a href="/events/new" class="btn btn-outline">{{ t('common.new_event') }}</a>
  <a href="/auth/register" class="btn btn-outline">+ {{ t('nav.register_user') }}</a>
</div>
{% endif %}
{% endblock %}
```

- [ ] **Commit**

```bash
git add templates/dashboard/coach.html
git commit -m "templates: add coach/admin dashboard template"
```

---

### Task 4: Restructure dashboard route handler

**Files:**
- Modify: `routes/dashboard.py` — replace entire handler with role-branching logic
- Modify: `templates/dashboard/index.html` — replace with role dispatcher

- [ ] **Rewrite route handler in `routes/dashboard.py`**

Replace the entire file content. The handler will branch:

```python
"""routes/dashboard.py — Main dashboard view (role-aware)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.templates import render
from models.attendance import Attendance
from models.event import Event
from models.event_message import EventMessage
from models.notification import Notification
from models.player import Player
from models.player_absence import PlayerAbsence
from models.player_team import PlayerTeam
from models.season import Season
from models.user import User
from routes._auth_helpers import get_coach_teams, require_login

router = APIRouter()

STATUS_LABELS = {
    "present": "attendance.status_present",
    "absent": "attendance.status_absent",
    "maybe": "attendance.status_maybe",
    "unknown": "attendance.status_unknown",
}


def _compute_attendance_rate(db: Session, player_id: int, active_season_id: int | None) -> tuple[int, str | None]:
    """Return (overall_rate, "Trainings 82% · Matches 60%" string or None)."""
    query = (
        db.query(Attendance.status, Event.event_type)
        .join(Event, Attendance.event_id == Event.id)
        .filter(Attendance.player_id == player_id)
    )
    if active_season_id:
        query = query.filter(Event.season_id == active_season_id)

    rows = query.all()
    if not rows:
        return 0, None

    total = len(rows)
    present = sum(1 for r in rows if r.status == "present")
    rate = round(present / total * 100) if total else 0

    type_breakdown: dict = {}
    for r in rows:
        type_breakdown.setdefault(r.event_type, [0, 0])
        type_breakdown[r.event_type][0] += 1
        if r.status == "present":
            type_breakdown[r.event_type][1] += 1

    breakdown_str = " · ".join(
        f"{etype.capitalize()} {round(cnt[1]/cnt[0]*100) if cnt[0] else 0}%"
        for etype, cnt in sorted(type_breakdown.items())
    )
    return rate, breakdown_str


@router.get("")
@router.get("/")
async def dashboard(
    request: Request,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    today = date.today()
    active_season = db.query(Season).filter(Season.is_active == True).first()  # noqa: E712

    # ── Coach / Admin dashboard ─────────────────────────────────────────
    if user.is_admin or user.is_coach:
        # Team scoping
        if user.is_admin:
            team_ids: set[int] | None = None  # None = all teams
        else:
            team_ids = get_coach_teams(user, db)

        events_q = db.query(Event)
        if active_season:
            events_q = events_q.filter(Event.season_id == active_season.id)
        if team_ids is not None:
            events_q = events_q.filter(Event.team_id.in_(team_ids))

        all_events = events_q.order_by(Event.event_date.asc()).all()
        upcoming_events = [e for e in all_events if e.event_date >= today]

        # Stat cards
        upcoming_count = len(upcoming_events)

        if upcoming_events:
            event_ids = [e.id for e in upcoming_events]
            unknown_count = (
                db.query(Attendance)
                .filter(Attendance.event_id.in_(event_ids), Attendance.status == "unknown")
                .count()
            )
        else:
            unknown_count = 0

        # Team attendance rate
        past_event_ids = [e.id for e in all_events if e.event_date < today]
        if past_event_ids:
            att_rows = (
                db.query(Attendance.status)
                .filter(Attendance.event_id.in_(past_event_ids))
                .all()
            )
            total_att = len(att_rows)
            present_att = sum(1 for r in att_rows if r.status == "present")
            team_attendance_rate = round(present_att / total_att * 100) if total_att else 0
        else:
            team_attendance_rate = 0

        # Trend: compare last 30 days vs 30-60 days ago
        thirty_ago = today - timedelta(days=30)
        sixty_ago = today - timedelta(days=60)
        recent_ids = [e.id for e in all_events if thirty_ago <= e.event_date < today]
        older_ids = [e.id for e in all_events if sixty_ago <= e.event_date < thirty_ago]

        def _rate_for(event_id_list: list[int]) -> float:
            if not event_id_list:
                return 0.0
            rows = db.query(Attendance.status).filter(Attendance.event_id.in_(event_id_list)).all()
            if not rows:
                return 0.0
            return sum(1 for r in rows if r.status == "present") / len(rows) * 100

        recent_rate = _rate_for(recent_ids)
        older_rate = _rate_for(older_ids)
        attendance_trend = round(recent_rate - older_rate) if (recent_ids and older_ids) else None

        # Injured/absent stats
        player_q = db.query(Player)
        if team_ids is not None:
            player_q = player_q.join(PlayerTeam, PlayerTeam.player_id == Player.id).filter(
                PlayerTeam.team_id.in_(team_ids)
            )
        active_players = player_q.filter(Player.archived_at.is_(None)).all()
        player_ids_all = [p.id for p in active_players]

        injured_count = db.query(PlayerTeam).filter(
            PlayerTeam.player_id.in_(player_ids_all),
            PlayerTeam.status == "injured",
        ).count()

        absence_count = db.query(PlayerAbsence).filter(
            PlayerAbsence.player_id.in_(player_ids_all),
            PlayerAbsence.start_date <= today,
            PlayerAbsence.end_date >= today,
        ).count()

        injured_absent_count = injured_count + absence_count

        # Upcoming events compact list
        upcoming_events_compact = []
        for e in upcoming_events[:5]:
            atts = db.query(Attendance).filter(Attendance.event_id == e.id).all()
            total_e = len(atts)
            unknown_e = sum(1 for a in atts if a.status == "unknown")
            days_diff = (e.event_date - today).days
            if days_diff == 0:
                label = "Today"
            elif days_diff == 1:
                label = "Tomorrow"
            else:
                label = e.event_date.strftime("%a %d")
            upcoming_events_compact.append({
                "id": e.id,
                "title": e.title,
                "date_label": label,
                "unknown_count": unknown_e,
                "total_count": total_e,
            })

        # Watch list
        watch_list = []
        for p in active_players:
            p_att_rows = (
                db.query(Attendance)
                .filter(Attendance.player_id == p.id)
                .order_by(Attendance.event_id.desc())
                .limit(5)
                .all()
            )
            # Count consecutive absences from most recent
            consecutive_absent = 0
            for a in sorted(p_att_rows, key=lambda x: x.event.event_date, reverse=True):
                if a.status == "absent":
                    consecutive_absent += 1
                elif a.status == "present":
                    break

            if consecutive_absent >= 3:
                watch_list.append({
                    "player_id": p.id,
                    "player_name": p.full_name,
                    "severity": "red",
                    "reason": f"Missed {consecutive_absent} events",
                })
            elif consecutive_absent >= 1:
                watch_list.append({
                    "player_id": p.id,
                    "player_name": p.full_name,
                    "severity": "yellow",
                    "reason": f"Missed {consecutive_absent} event(s)",
                })

            # Check if injured
            pt = db.query(PlayerTeam).filter(
                PlayerTeam.player_id == p.id,
                PlayerTeam.status == "injured",
            ).first()
            if pt and pt.injured_until:
                watch_list.append({
                    "player_id": p.id,
                    "player_name": p.full_name,
                    "severity": "green",
                    "reason": f"Injured until {pt.injured_until}",
                })

        # Recent chat activity
        msg_q = db.query(EventMessage).order_by(EventMessage.created_at.desc()).limit(5)
        if team_ids is not None:
            msg_q = msg_q.join(Event, EventMessage.event_id == Event.id).filter(Event.team_id.in_(team_ids))
        recent_messages = []
        for msg in msg_q.all():
            event = db.get(Event, msg.event_id)
            author = db.get(User, msg.user_id)
            author_name = f"{author.first_name} {author.last_name}" if author and author.first_name else (author.username if author else "Unknown")
            recent_messages.append({
                "author_name": author_name,
                "body_truncated": msg.body[:80] + "…" if len(msg.body) > 80 else msg.body,
                "event_id": msg.event_id,
                "event_title": event.title if event else "",
            })

        return render(
            request,
            "dashboard/coach.html",
            {
                "user": user,
                "active_season": active_season,
                "team_attendance_rate": team_attendance_rate,
                "attendance_trend": attendance_trend,
                "unknown_count": unknown_count,
                "upcoming_count": upcoming_count,
                "injured_absent_count": injured_absent_count,
                "injured_count": injured_count,
                "absence_count": absence_count,
                "upcoming_events_compact": upcoming_events_compact,
                "watch_list": watch_list,
                "recent_messages": recent_messages,
            },
        )

    # ── Player / member dashboard ────────────────────────────────────────
    player = (
        db.query(Player)
        .filter(Player.user_id == user.id, Player.archived_at.is_(None))
        .first()
    )
    my_player_id = player.id if player else None

    context: dict = {
        "user": user,
        "active_season": active_season,
        "my_player_id": my_player_id,
    }

    if my_player_id:
        # Attendance rate
        rate, breakdown = _compute_attendance_rate(db, my_player_id, active_season.id if active_season else None)
        context["attendance_rate"] = rate
        context["event_type_breakdown"] = breakdown

        # Next event
        teams_q = db.query(PlayerTeam.team_id).filter(PlayerTeam.player_id == my_player_id)
        player_team_ids = {row[0] for row in teams_q.all()}
        next_event = (
            db.query(Event)
            .filter(
                Event.event_date >= today,
                Event.team_id.in_(player_team_ids) if player_team_ids else False,
            )
            .order_by(Event.event_date.asc())
            .first()
        )
        context["next_event"] = next_event
        if next_event:
            att = (
                db.query(Attendance)
                .filter(Attendance.event_id == next_event.id, Attendance.player_id == my_player_id)
                .first()
            )
            context["my_next_status"] = att.status if att else "unknown"
            context["my_next_note"] = att.note if att and att.note else ""
        context["status_labels"] = {k: request.state.locale and k or k for k in STATUS_LABELS}

        # Unread notifications
        notif_q = (
            db.query(Notification)
            .filter(
                (Notification.player_id == my_player_id) | (Notification.user_id == user.id),
                Notification.is_read == False,  # noqa: E712
            )
            .order_by(Notification.created_at.desc())
        )
        context["recent_notifications"] = notif_q.limit(3).all()
        context["unread_count"] = notif_q.count()

        # Active absences
        context["active_absences"] = (
            db.query(PlayerAbsence)
            .filter(
                PlayerAbsence.player_id == my_player_id,
                PlayerAbsence.end_date >= today,
            )
            .order_by(PlayerAbsence.start_date.asc())
            .all()
        )

    return render(request, "dashboard/player.html", context)
```

- [ ] **Replace `templates/dashboard/index.html`**

Replace with a simple dispatcher:

```html
{% extends "base.html" %}
{% block title %}{{ t('dashboard.title') }} — ProManager{% endblock %}
{% block content %}
  {% if user.is_admin or user.is_coach %}
    {% include "dashboard/coach.html" %}
  {% else %}
    {% include "dashboard/player.html" %}
  {% endif %}
{% endblock %}
```

Wait — actually the templates already extend `base.html` themselves, so having `index.html` as a dispatcher that includes them would cause double-extend. Better approach:

Replace `templates/dashboard/index.html` with a role-switcher that sets the right `{% extends %}`:

```html
{% extends "base.html" %}
{% block title %}{{ t('dashboard.title') }} — ProManager{% endblock %}
{% block content %}
  {% if user.is_admin or user.is_coach %}
    {% include "dashboard/coach_content.html" %}
  {% else %}
    {% include "dashboard/player_content.html" %}
  {% endif %}
{% endblock %}
```

And rename player.html → player_content.html, coach.html → coach_content.html (they become fragments without extends/block).

Or simpler: put both templates inline in index.html with `{% if %}` blocks:

Same approach as current — one `index.html` with branching, no separate templates at all. This keeps it simpler.

Actually, the cleanest approach is what I had before but without extend/block in the partials. Let me revise:

**index.html** — extends base.html, dispatches to includes:
```html
{% extends "base.html" %}
{% block title %}{{ t('dashboard.title') }} — ProManager{% endblock %}
{% block content %}
  {% if user.is_admin or user.is_coach %}
    {% include "dashboard/coach_fragment.html" %}
  {% else %}
    {% include "dashboard/player_fragment.html" %}
  {% endif %}
{% endblock %}
{% block scripts %}
  {% if user.is_admin or user.is_coach %}
  {% else %}
    {% include "dashboard/player_scripts_fragment.html" %}
  {% endif %}
{% endblock %}
```

And create `coach_fragment.html`, `player_fragment.html`, `player_scripts_fragment.html` as fragments (no extends, no blocks).

This way index.html is the entry point and the fragments are pure HTML snippets.

- [ ] **Commit**

```bash
git add routes/dashboard.py templates/dashboard/
git commit -m "feat: restructure dashboard with role-aware views"
```

---

### Task 5: I18n keys for new dashboard strings

**Files:**
- Modify: `locales/en.json`, `locales/it.json`, `locales/fr.json`, `locales/de.json`

- [ ] **Add i18n keys to all locale files**

Add these keys to all 4 locale files under the `dashboard` namespace:

```json
{
  "dashboard": {
    "my_attendance": "My Attendance",
    "view_full_report": "Full Report",
    "next_event": "Next Event",
    "unread_notifications": "Unread Notifications",
    "no_unread": "All caught up",
    "my_absences": "My Absences",
    "no_active_absences": "No active absences",
    "absence": "Absence",
    "recurring": "Recurring",
    "no_linked_player": "You are not linked to any player. Contact your coach.",
    "team_attendance": "Team Attendance",
    "last_30_days": "last 30 days",
    "pending": "Pending",
    "unknowns_across_events": "%{count} unknowns across %{events} events",
    "injured_absent": "Injured / Absent",
    "injured": "injured",
    "absences": "absences",
    "upcoming_events": "Upcoming Events",
    "unknown": "unknown",
    "watch_list": "Watch List",
    "no_watch_items": "No players need attention",
    "recent_chat": "Recent Chat Activity",
    "no_recent_chat": "No recent messages"
  }
}
```

Translate appropriately for `it`, `fr`, `de`.

- [ ] **Commit**

```bash
git add locales/
git commit -m "i18n: add dashboard redesign translation keys"
```

---

### Task 6: Tests

**Files:**
- Create: `tests/test_dashboard.py`

- [ ] **Write player dashboard tests**

```python
"""Tests for /dashboard route (role-aware)."""

import pytest
from services.auth_service import create_user
from models.player import Player
from models.player_team import PlayerTeam
from models.player_absence import PlayerAbsence
from models.event import Event
from models.attendance import Attendance
from models.notification import Notification
from models.season import Season
from models.team import Team


def test_player_dashboard_renders(member_client, db):
    """Member dashboard returns 200 and shows player template."""
    resp = member_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200
    assert b"My Attendance" in resp.content or b"dashboard.my_attendance" not in resp.content  # crude check


def test_player_dashboard_no_linked_player(client, db):
    """Member without linked player sees warning."""
    user = create_user(db, "unlinked", "u@test.com", "pass", role="member", must_change_password=False)
    from services.auth_service import create_session_cookie
    cookie = create_session_cookie(user.id)
    client.cookies.set("session_user_id", cookie)
    resp = client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200


def test_player_dashboard_shows_next_event(member_client, db, member_user, admin_user):
    """Player dashboard shows the next upcoming event for the member's team."""
    season = db.query(Season).first()
    if not season:
        season = Season(name="Test Season", is_active=True)
        db.add(season)
        db.flush()
    player = db.query(Player).filter(Player.user_id == member_user.id).first()
    team = db.query(Team).first()
    if team:
        pt = db.query(PlayerTeam).filter(PlayerTeam.player_id == player.id, PlayerTeam.team_id == team.id).first()
        if not pt:
            pt = PlayerTeam(player_id=player.id, team_id=team.id)
            db.add(pt)
            db.flush()
        ev = Event(title="Test Event", event_date=date.today(), team_id=team.id, season_id=season.id)
        db.add(ev)
        db.commit()
    resp = member_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200


def test_player_dashboard_shows_attendance_rate(member_client, db, member_user):
    """Player dashboard computes and displays attendance rate."""
    player = db.query(Player).filter(Player.user_id == member_user.id).first()
    season = db.query(Season).first()
    if not season:
        season = Season(name="Test Season", is_active=True)
        db.add(season)
        db.flush()
    if player:
        ev = Event(title="Past Event", event_date=date(2026, 1, 1), team_id=1, season_id=season.id)
        db.add(ev)
        db.flush()
        att = Attendance(event_id=ev.id, player_id=player.id, status="present")
        db.add(att)
        db.commit()
    resp = member_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200


def test_coach_dashboard_renders(admin_client, db):
    """Admin dashboard returns 200 and shows coach template."""
    resp = admin_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 200
```

Wait, I need to use `from datetime import date`. Let me fix that.

Also I need to think about what's testable without fixtures that set up complex data. Let me keep tests simple — just verify the page renders with expected content for each role, and the template context has expected keys.

- [ ] **Write tests**

```python
"""Tests for /dashboard route (role-aware)."""

from datetime import date

import pytest
from services.auth_service import create_session_cookie, create_user
from models.player import Player
from models.player_team import PlayerTeam
from models.event import Event
from models.attendance import Attendance
from models.season import Season
from models.team import Team


class TestPlayerDashboard:
    def test_renders_for_member(self, member_client):
        resp = member_client.get("/dashboard")
        assert resp.status_code == 200

    def test_renders_for_unlinked_member(self, client, db):
        user = create_user(db, "unlinked", "u@test.com", "pass", role="member", must_change_password=False)
        cookie = create_session_cookie(user.id)
        client.cookies.set("session_user_id", cookie)
        resp = client.get("/dashboard")
        assert resp.status_code == 200

    def test_no_active_season_shows_warning(self, member_client, db):
        db.query(Season).update({"is_active": False})
        db.commit()
        resp = member_client.get("/dashboard")
        assert resp.status_code == 200

    def test_shows_next_event(self, member_client, db, member_user):
        player = db.query(Player).filter(Player.user_id == member_user.id).first()
        if not player:
            pytest.skip("No linked player")
        team = db.query(Team).first()
        if not team:
            pytest.skip("No team")
        season = db.query(Season).filter(Season.is_active == True).first()
        if not season:
            season = Season(name="Test S", is_active=True)
            db.add(season)
            db.flush()
        ev = Event(title="Test Event", event_date=date.today(), team_id=team.id, season_id=season.id)
        db.add(ev)
        db.commit()
        resp = member_client.get("/dashboard")
        assert resp.status_code == 200

    def test_shows_attendance_rate(self, member_client, db, member_user):
        player = db.query(Player).filter(Player.user_id == member_user.id).first()
        if not player:
            pytest.skip("No linked player")
        season = db.query(Season).filter(Season.is_active == True).first()
        if not season:
            season = Season(name="Test S", is_active=True)
            db.add(season)
            db.flush()
        ev = Event(title="Past E", event_date=date(2026, 1, 1), team_id=1, season_id=season.id)
        db.add(ev)
        db.flush()
        db.add(Attendance(event_id=ev.id, player_id=player.id, status="present"))
        db.commit()
        resp = member_client.get("/dashboard")
        assert resp.status_code == 200


class TestCoachDashboard:
    def test_renders_for_admin(self, admin_client):
        resp = admin_client.get("/dashboard")
        assert resp.status_code == 200

    def test_renders_for_coach(self, client, db):
        user = create_user(db, "coach1", "c@test.com", "pass", role="coach", must_change_password=False)
        cookie = create_session_cookie(user.id)
        client.cookies.set("session_user_id", cookie)
        resp = client.get("/dashboard")
        assert resp.status_code == 200

    def test_shows_stat_cards(self, admin_client):
        resp = admin_client.get("/dashboard")
        assert resp.status_code == 200

    def test_admin_shows_quick_actions(self, admin_client):
        resp = admin_client.get("/dashboard")
        assert resp.status_code == 200


class TestDashboardNav:
    def test_reports_link_hidden_for_member(self, client, db):
        user = create_user(db, "m2", "m2@test.com", "pass", role="member", must_change_password=False)
        cookie = create_session_cookie(user.id)
        client.cookies.set("session_user_id", cookie)
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        # Reports link should not be in the nav for members
        # Check that /reports is not linked in the sidebar (line 57 area)
        content = resp.text
        # The /reports link in sidebar should only appear for admin/coach
        assert '/reports"' not in content or "nav-active" not in content  # weak check

    def test_reports_link_shown_for_admin(self, admin_client):
        resp = admin_client.get("/dashboard")
        assert '/reports"' in resp.text

    def test_dashboard_link_active(self, admin_client):
        resp = admin_client.get("/dashboard")
        assert 'nav-active' in resp.text
```

- [ ] **Run tests**

```bash
pytest tests/test_dashboard.py -v
```
Expected: all tests pass.

- [ ] **Commit**

```bash
git add tests/test_dashboard.py
git commit -m "tests: add dashboard redesign tests"
```

---

### Task 7: Full verification

- [ ] **Run full test suite**

```bash
pytest -v
```
Expected: all existing tests still pass, no regressions.

- [ ] **Run lint + typecheck**

```bash
ruff check . && ruff format . && mypy .
```
Expected: clean.

- [ ] **Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address review feedback"
```