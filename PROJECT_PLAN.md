# ProManager — Detailed Project Plan

**Project Name:** ProManager  
**Stack:** Python 3.12, FastAPI, Uvicorn, SQLite, SQLAlchemy, Jinja2, Docker  
**Goal:** Self-hosted player presence/absence tracker to replace ProManager

---

## 1. Core Features

| Feature | Priority | Notes |
|---------|----------|-------|
| User authentication (login/logout) | P1 | username+password, bcrypt hashing, session cookie |
| Admin & club-member roles | P1 | Admins manage everything; members mark own attendance |
| Season management | P1 | Create, activate, archive seasons; events belong to a season |
| Team management | P1 | CRUD; players belong to teams |
| Player management | P1 | CRUD; linked to optional user account |
| Event scheduling | P1 | Match / training / other; date, time, location, description |
| Presence/absence marking | P1 | Member sets own status (Present / Absent / Maybe); admin can override |
| Attendance reports | P2 | Per-player, per-event, per-season summaries |
| Email notifications | P2 | Event reminders, attendance confirmation (smtplib, no extra dep) |
| Admin dashboard | P2 | Overview of upcoming events, attendance stats |
| iCalendar export | P3 | .ics export per team/season (calendar integration later) |

---

## 2. Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Python | 3.12 | Current stable |
| Web framework | FastAPI | Async, minimal, Uvicorn native |
| ASGI server | Uvicorn | Production-ready |
| Database | SQLite | Zero-config, single file, easy backup |
| ORM | SQLAlchemy 2.x (sync) | Mature, minimal deps with SQLite |
| Templating | Jinja2 | Ships with FastAPI ecosystem |
| Auth | passlib[bcrypt] + itsdangerous (signed sessions) | Minimal, secure |
| Email | smtplib (stdlib) | Zero extra dep |
| Static files | Starlette StaticFiles | Zero extra dep (ships with FastAPI) |
| CSS | Pico CSS (CDN) | Minimal, no build step |
| Tests | pytest + httpx | Standard |
| Container | Docker + docker-compose | Portability |

### Full `requirements.txt` (minimal)
```
fastapi==0.115.0
uvicorn[standard]==0.29.0
sqlalchemy==2.0.36
jinja2==3.1.4
python-multipart==0.0.9
passlib[bcrypt]==1.7.4
itsdangerous==2.2.0
```

### `requirements-dev.txt`
```
-r requirements.txt
httpx==0.27.0
pytest==8.3.0
pytest-asyncio==0.23.0
```

---

## 3. Data Model

```
Season        id, name, start_date, end_date, is_active
Team          id, name, season_id (FK), description
Player        id, first_name, last_name, email, phone, team_id (FK), user_id (FK nullable)
User          id, username, email, hashed_password, role (admin|member), is_active, created_at
Event         id, title, type (match|training|other), date, time, location, description,
              season_id (FK), team_id (FK), reminder_sent (bool)
Attendance    id, event_id (FK), player_id (FK), status (present|absent|maybe|unknown),
              note, updated_at
              UNIQUE (event_id, player_id)
```

---

## 4. Project Structure

```
promanager/
  app/
    __init__.py
    main.py           # FastAPI app factory, lifespan, middleware
    config.py         # Settings from env vars / .env
    database.py       # SQLAlchemy engine & session
  models/
    __init__.py
    user.py
    season.py
    team.py
    player.py
    event.py
    attendance.py
  routes/
    __init__.py
    auth.py           # login, logout, register
    dashboard.py      # home/admin overview
    seasons.py        # season CRUD
    teams.py          # team CRUD
    players.py        # player CRUD
    events.py         # event CRUD + detail + attendance list
    attendance.py     # mark/update attendance
    reports.py        # attendance reports
  services/
    __init__.py
    auth_service.py   # password hashing, session management
    email_service.py  # smtplib wrappers, reminder sending
    attendance_service.py  # aggregate stats
  templates/
    base.html
    auth/
      login.html
    dashboard/
      index.html
    seasons/
      list.html  form.html
    teams/
      list.html  form.html
    players/
      list.html  form.html  detail.html
    events/
      list.html  form.html  detail.html
    attendance/
      mark.html  report.html
  static/
    css/main.css
    js/main.js
  tests/
    conftest.py
    test_auth.py
    test_seasons.py
    test_teams.py
    test_players.py
    test_events.py
    test_attendance.py
    test_reports.py
  scripts/
    create_admin.py   # CLI: create first admin user
    backup_db.py      # CLI: copy SQLite file with timestamp
  data/               # SQLite DB lives here (volume-mounted in Docker)
  Dockerfile
  docker-compose.yml
  .env.example
  requirements.txt
  requirements-dev.txt
  README.md
  PROJECT_PLAN.md
```

---

## 5. Authentication & Sessions

- Passwords hashed with **bcrypt** via passlib
- Session managed via **signed cookie** (itsdangerous `TimestampSigner`)
- No JWT complexity — cookie stores user ID, verified on every request
- Middleware injects `request.state.user` (or None for anonymous)
- Role check decorators: `require_login`, `require_admin`
- Admin can also generate **API tokens** (static bearer token stored hashed in DB) for simple integrations

---

## 6. Email Notifications

- Config: SMTP host/port/user/password via env vars
- Events: "Event reminder" (sent N hours before event), "Attendance request" (sent on event creation)
- Implemented in `services/email_service.py` using stdlib `smtplib` + `email.mime`
- Background sending: FastAPI `BackgroundTasks` (no Celery/RQ)

---

## 7. Docker Setup

```yaml
# docker-compose.yml
services:
  web:
    build: .
    ports: ["8000:8000"]
    volumes:
      - ./data:/app/data   # SQLite persistence
    env_file: .env
    restart: unless-stopped
```

```dockerfile
# Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 8. Implementation Phases (Subagents)

### Phase 1 — Foundation
**Subagent A** creates:
- `requirements.txt`, `requirements-dev.txt`, `.env.example`
- `Dockerfile`, `docker-compose.yml`
- `app/__init__.py`, `app/main.py`, `app/config.py`, `app/database.py`
- All models: `models/__init__.py`, `models/user.py`, `models/season.py`,
  `models/team.py`, `models/player.py`, `models/event.py`, `models/attendance.py`
- `data/.gitkeep`

### Phase 2 — Services & Routes
**Subagent B** creates (building on Phase 1 models):
- `services/__init__.py`, `services/auth_service.py`, `services/email_service.py`, `services/attendance_service.py`
- All routes: `routes/__init__.py`, `routes/auth.py`, `routes/dashboard.py`,
  `routes/seasons.py`, `routes/teams.py`, `routes/players.py`,
  `routes/events.py`, `routes/attendance.py`, `routes/reports.py`

### Phase 3 — Templates
**Subagent C** creates (building on Phase 2 routes):
- All Jinja2 templates with Pico CSS
- `static/css/main.css`, `static/js/main.js`

### Phase 4 — Tests, Scripts & Docs
**Subagent D** creates (building on full implementation):
- All tests in `tests/`
- `scripts/create_admin.py`, `scripts/backup_db.py`
- `README.md` with setup & usage instructions

---

## 9. Future / Phase 3+
- iCalendar (.ics) export
- REST API for mobile app
- Per-team notification preferences
- Bulk player import via CSV
- Recurring events
