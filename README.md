# ProManager

A self-hosted **player presence and absence tracker** for sports teams. ProManager gives coaches and team managers a simple web interface to manage seasons, teams, players, and training/match events — with per-event attendance marking, real-time event chat, Telegram bot integration, and multi-channel notifications.

## Key features

- Multi-season support with one active season at a time
- Team and player roster management with player archiving and bulk CSV import
- Event scheduling (matches, trainings, other) with recurring event support
- Per-player attendance tracking (present / absent / maybe / unknown) with free-text notes
- External participants per event (non-roster guests)
- Automatic attendance record creation when events are created
- Real-time event chat with SSE push (announcements + discussion lanes)
- Telegram bot — mark attendance, view events, add notes, reply to chat
- Multi-channel notifications: email reminders, in-app, and web push
- Season and player attendance reports
- User management with player linking (one-to-one)
- Role-based access: **admin** (full CRUD), **coach** (own teams), **member** (own attendance)
- Coach/team scoping — non-admin users see only their assigned teams
- Internationalisation: English, German, French, Italian (user-selectable)
- Dark / light theme (persisted per user)
- Cookie-based signed sessions (no JWT dependencies)
- Docker-ready single-container deployment

---

## Quick start with Docker

```bash
# 1. Clone the repository and copy the example env file
git clone https://github.com/dennyschwender/promanager.git
cd promanager
cp .env.example .env        # edit at minimum SECRET_KEY

# 2. Edit .env with your values (see Environment variables below)
nano .env

# 3. Start the application
docker compose up -d
```

The app will be available at **http://localhost:7000**.

Create the first admin account after the container starts:

```bash
docker compose exec web python scripts/create_admin.py \
  --username admin \
  --email admin@example.com \
  --password 'REPLACE_WITH_STRONG_PASSWORD'
```

> **Important:** Replace `REPLACE_WITH_STRONG_PASSWORD` with a strong, unique password. Keep the single quotes so shell special characters (`!`, `$`, spaces) are handled correctly.

---

## Local development setup

### Prerequisites

- Python 3.11+
- `virtualenv` or `venv`

### Steps

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install all dependencies (includes test tooling)
pip install -r requirements-dev.txt

# Configure environment
cp .env.example .env
# Edit .env to set SECRET_KEY and any other settings

# Apply database migrations
alembic upgrade head

# Run the development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 7000
```

### Running tests

```bash
pytest -v                                     # all tests
pytest tests/test_auth.py                     # single file
pytest --cov                                  # with coverage
```

Tests use an in-memory SQLite database (`StaticPool`); all tables are truncated between tests.

---

## Creating the first admin

```bash
python scripts/create_admin.py \
  --username admin \
  --email admin@example.com \
  --password 'REPLACE_WITH_STRONG_PASSWORD'
```

The script prints the new user's ID on success, or an error if the username already exists.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | Signs session cookies and CSRF tokens. **Must be changed in production.** Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | `sqlite:///./data/proManager.db` | SQLAlchemy database URL. SQLite is the default; PostgreSQL is supported. |
| `SMTP_HOST` | `localhost` | Hostname of the SMTP server for email notifications. |
| `SMTP_PORT` | `587` | SMTP port (587 for STARTTLS, 465 for SSL). |
| `SMTP_USER` | *(empty)* | SMTP authentication username. |
| `SMTP_PASSWORD` | *(empty)* | SMTP authentication password. |
| `SMTP_FROM` | `noreply@promanager.local` | From address for outgoing emails. |
| `APP_NAME` | `ProManager` | Display name shown in the browser title and emails. |
| `REMINDER_HOURS_BEFORE` | `24` | Hours before an event to send reminder emails. |
| `COOKIE_SECURE` | `False` | Set `True` when serving over HTTPS (marks session cookie Secure). |
| `DEBUG` | `False` | Raises `KeyError` on missing i18n translation keys (development aid). |
| `VAPID_PUBLIC_KEY` | *(empty)* | VAPID public key for web push notifications. Generate with `python scripts/generate_vapid.py`. |
| `VAPID_PRIVATE_KEY` | *(empty)* | VAPID private key for web push notifications. |
| `VAPID_SUBJECT` | *(empty)* | VAPID subject (e.g. `mailto:admin@example.com`). |
| `TELEGRAM_BOT_TOKEN` | *(empty)* | Bot token from @BotFather. Leave empty to disable the Telegram integration. |
| `TELEGRAM_WEBHOOK_URL` | *(empty)* | Public HTTPS base URL of this app (required for Telegram webhook mode). |
| `TELEGRAM_WEBHOOK_SECRET` | *(empty)* | Secret to validate incoming Telegram webhook requests. Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |

---

## Feature overview

### Seasons

Create and manage multiple seasons (e.g. *2025/26*). Only one season can be **active** at a time; activating a season automatically deactivates all others.

### Teams & Players

Teams belong to a season. Players belong to teams via flexible memberships. Player profiles store name, email, and phone. A player can be **linked to a user account**, allowing members to log in and manage their own attendance.

Inactive players can be **archived** (soft-delete) to keep historical data intact. Players can be imported in bulk via CSV from the players list page.

### Events

Events can be of type **match**, **training**, or **other**. Attendance records are automatically initialised (`unknown`) for all active players in the event's team when an event is created.

**Recurring events** can be created on a weekly, biweekly, or monthly schedule — ProManager generates the full set of events automatically.

**External participants** (non-roster guests) can be added per event and appear inline in the attendance columns.

### Attendance

Admins can mark all players' attendance. Members see only their own linked player and can update their status and note. Each record supports a free-text note. Attendance can also be updated via the Telegram bot.

### Event Chat

Each event has a real-time chat panel with two lanes:
- **Announcements** — coach/admin only
- **Discussion** — all attendees

Messages are pushed live to all connected clients via Server-Sent Events (SSE). Telegram users receive a push notification and can reply directly from the bot.

### Telegram Bot

Connect players to the bot via phone number matching. Once authenticated, players can:
- View upcoming events and their attendance status
- Mark themselves present / absent / maybe
- Add or edit attendance notes
- View and reply to event chat messages

Enable the bot by setting `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_URL` in `.env`.

### Notifications

ProManager delivers notifications through three channels (configurable per user):
- **Email** — event reminders N hours before an event (see `REMINDER_HOURS_BEFORE`)
- **In-app** — unread count shown in the nav bar
- **Web push** — browser push notifications (requires VAPID keys)

### Reports

- **Season report**: per-player breakdown of present / absent / maybe / unknown counts across all events in a season.
- **Player report**: full attendance history for a single player across all events.

### Internationalisation & Theme

The UI is available in **English, German, French, and Italian**. Users can switch language from their profile. Translation files live in `locales/` (YAML format, dot-namespaced keys).

Dark and light themes are supported and persisted per user.

---

## Database backup

```bash
# Back up to the default location (data/backups/)
python scripts/backup_db.py

# Back up to a custom directory
python scripts/backup_db.py --dest /var/backups/promanager
```

The backup file is a timestamped copy of the SQLite file, e.g. `proManager_2026-02-27T14-30-00.db`.

---

## Tech stack

| Layer | Technology |
|---|---|
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) |
| ASGI server | [Uvicorn](https://www.uvicorn.org/) |
| ORM | [SQLAlchemy 2.x](https://docs.sqlalchemy.org/) |
| Database migrations | [Alembic](https://alembic.sqlalchemy.org/) |
| Database | SQLite (default) / PostgreSQL |
| Templates | [Jinja2](https://jinja.palletsprojects.com/) |
| Password hashing | [passlib\[bcrypt\]](https://passlib.readthedocs.io/) |
| Session signing | [itsdangerous](https://itsdangerous.palletsprojects.com/) |
| Form parsing | [python-multipart](https://github.com/andrew-mccall/python-multipart) |
| Telegram bot | [python-telegram-bot](https://python-telegram-bot.org/) |
| Web push | [pywebpush](https://github.com/web-push-libs/pywebpush) |
| Testing | [pytest](https://pytest.org/) + [httpx](https://www.python-httpx.org/) (via `TestClient`) |
| Containerisation | Docker + Docker Compose |
