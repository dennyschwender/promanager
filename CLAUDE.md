# ProManager — Claude Code Guide

## Project overview

ProManager is a self-hosted player presence and absence tracker for sports teams built with FastAPI. It lets coaches and managers handle seasons, teams, players, events, and attendance — all in a single Docker container.

## Tech stack

- **Framework**: FastAPI (Python 3.12)
- **ASGI server**: Uvicorn
- **ORM**: SQLAlchemy 2.x
- **Database**: SQLite (default) / PostgreSQL
- **Templates**: Jinja2
- **Auth**: Cookie-based signed sessions via itsdangerous + passlib[bcrypt]
- **Testing**: pytest + httpx TestClient
- **Containerisation**: Docker + Docker Compose

## Project structure

```
app/          # FastAPI application package (main.py, config, db, dependencies)
routes/       # Route modules (auth, seasons, teams, players, events, attendance, reports)
models/       # SQLAlchemy ORM models
services/     # Business logic (email reminders, reports, etc.)
templates/    # Jinja2 HTML templates
static/       # Static assets (CSS, JS)
scripts/      # Admin utility scripts (create_admin.py, backup_db.py)
tests/        # pytest test suite
alembic/      # Database migration scripts
```

## Running locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # set SECRET_KEY at minimum
uvicorn app.main:app --reload --host 0.0.0.0 --port 7000
```

## Running with Docker

```bash
cp .env.example .env   # edit SECRET_KEY and any SMTP settings
docker compose up -d
# App available at http://localhost:7000
```

## Running tests

```bash
pytest -v
```

Tests use an isolated SQLite database (`data/test_proManager.db`) and roll back each test's changes automatically.

## Creating the first admin

```bash
docker compose exec web python scripts/create_admin.py \
  --username admin \
  --email admin@example.com \
  --password changeme123
```

## Key environment variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | Signs session cookies — **must** be changed in production |
| `DATABASE_URL` | `sqlite:///./data/proManager.db` | SQLAlchemy database URL |
| `SMTP_HOST` | `localhost` | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | *(empty)* | SMTP username |
| `SMTP_PASSWORD` | *(empty)* | SMTP password |
| `SMTP_FROM` | `noreply@promanager.local` | From address for outgoing emails |
| `APP_NAME` | `ProManager` | Display name in browser title and emails |
| `REMINDER_HOURS_BEFORE` | `24` | Hours before an event to send reminder emails |

## Development notes

- The SQLite database is created automatically on first run via the FastAPI lifespan handler.
- Port **7000** is the default for both Docker and local dev.
- Role-based access: `admin` has full CRUD; `member` can view and update their own attendance only.
- Attendance records are auto-created (status `unknown`) for all relevant players when an event is added.
