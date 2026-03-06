# ProManager

A self-hosted **player presence and absence tracker** for sports teams. ProManager gives coaches and team managers a simple web interface to manage seasons, teams, players, and training/match events — with per-event attendance marking and season-level reporting.

## Key features

- Multi-season support with one active season at a time
- Team and player roster management
- Event scheduling (matches, trainings, other)
- Per-player attendance tracking (present / absent / maybe / unknown)
- Automatic attendance record creation when events are created
- Email reminder notifications before upcoming events
- Season and player attendance reports
- Role-based access: **admin** (full CRUD) and **member** (view own attendance)
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
  --password REPLACE_WITH_STRONG_PASSWORD
```

> **Important:** Replace `REPLACE_WITH_STRONG_PASSWORD` with a strong, unique password of your own choosing before running this command.

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
# Edit .env to set SECRET_KEY and any SMTP settings you want

# Run the development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 7000
```

The app auto-creates the SQLite database on first run via the lifespan handler.

### Running tests

```bash
pytest -v
```

Tests use an isolated SQLite database (`data/test_proManager.db`) and roll back each test's changes automatically.

---

## Creating the first admin

```bash
python scripts/create_admin.py \
  --username admin \
  --email admin@example.com \
  --password REPLACE_WITH_STRONG_PASSWORD
```

> **Important:** Replace `REPLACE_WITH_STRONG_PASSWORD` with a strong, unique password of your own choosing before running this command.

The script prints the new user's ID on success or an error message if the username already exists.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | Secret used to sign session cookies. **Must be changed in production.** Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | `sqlite:///./data/proManager.db` | SQLAlchemy database URL. SQLite is the default; PostgreSQL is supported. |
| `SMTP_HOST` | `localhost` | Hostname of the SMTP server used to send email reminders. |
| `SMTP_PORT` | `587` | SMTP port (587 for STARTTLS, 465 for SSL). |
| `SMTP_USER` | *(empty)* | SMTP authentication username. |
| `SMTP_PASSWORD` | *(empty)* | SMTP authentication password. |
| `SMTP_FROM` | `noreply@promanager.local` | From address used in outgoing emails. |
| `APP_NAME` | `ProManager` | Display name shown in the browser title and emails. |
| `REMINDER_HOURS_BEFORE` | `24` | How many hours before an event to send reminder emails. |

---

## Feature overview

### Seasons

Create and manage multiple seasons (e.g. *2025/26*). Only one season can be **active** at a time; activating a season automatically deactivates all others. Seasons have an optional start and end date.

### Teams

Teams belong to a season and act as a container for players. A player can belong to one team, and events can be scoped to a specific team.

### Players

Player profiles store first/last name, email, and phone. A player can be **linked to a user account**, allowing members to log in and mark their own attendance. Players can be filtered by team on the roster page.

### Events

Events can be of type **match**, **training**, or **other**. When an event is created, attendance records are automatically initialised (with status `unknown`) for all active players in the event's team (or all players if no team is set).

Admins can trigger email reminders to all players with an email address via the event detail page.

### Attendance

Admins can mark all players present/absent/maybe from the attendance page. Members see only their own linked player(s) and can update their own status. Each record supports a free-text note.

### Reports

- **Season report**: per-player breakdown of present / absent / maybe / unknown counts across all events in a season.
- **Player report**: full attendance history for a single player, showing each event and their status.

---

## Database backup

```bash
# Back up to the default location (data/backups/)
python scripts/backup_db.py

# Back up to a custom directory
python scripts/backup_db.py --dest /var/backups/promanager
```

The backup file is a timestamped copy of the SQLite file, e.g. `proManager_2026-02-27T14-30-00.db`. The script uses `shutil.copy2` to preserve filesystem metadata.

---

## Tech stack

| Layer | Technology |
|---|---|
| Web framework | [FastAPI](https://fastapi.tiangolo.com/) |
| ASGI server | [Uvicorn](https://www.uvicorn.org/) |
| ORM | [SQLAlchemy 2.x](https://docs.sqlalchemy.org/) |
| Database | SQLite (default) / PostgreSQL |
| Templates | [Jinja2](https://jinja.palletsprojects.com/) |
| Password hashing | [passlib\[bcrypt\]](https://passlib.readthedocs.io/) |
| Session signing | [itsdangerous](https://itsdangerous.palletsprojects.com/) |
| Form parsing | [python-multipart](https://github.com/andrew-mccall/python-multipart) |
| Testing | [pytest](https://pytest.org/) + [httpx](https://www.python-httpx.org/) (via `TestClient`) |
| Containerisation | Docker + Docker Compose |
