# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

ProManager is a self-hosted player presence/absence tracker for sports teams built with FastAPI. Coaches and managers handle seasons, teams, players, events, and attendance in a single Docker container.

## Commands

```bash
# Local dev (activate venv first)
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                          # set SECRET_KEY at minimum
.venv/bin/alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 7000

# Tests
pytest -v                                     # all tests
pytest tests/test_auth.py                     # single file
pytest tests/test_auth.py::test_login_success # single test
pytest --cov                                  # with coverage

# Lint / format
ruff check .
ruff format .
mypy .

# Docker
docker compose up -d   # app at http://localhost:7000
```

## Architecture

### Request lifecycle

1. **`AuthMiddleware`** (in `app/main.py`) runs first: resolves the signed session cookie → `request.state.user`, generates CSRF token → `request.state.csrf_token`, and fetches unread notification count.
2. **`LocaleMiddleware`** (`app/middleware/locale.py`) runs next: resolves locale from user DB preference → locale cookie → `"en"` default → `request.state.locale`.
3. Route handlers use FastAPI `Depends()` for auth guards (`require_login`, `require_admin` from `routes/_auth_helpers.py`) and `get_db` for DB sessions.

### Authentication & authorization

- Session cookie `session_user_id` is signed with `itsdangerous.TimestampSigner` (7-day expiry).
- `require_login` / `require_admin` are `Depends()` guards. Raising `NotAuthenticated` → redirect to `/auth/login`; `NotAuthorized` → 403 page.
- Roles: `"admin"` (full CRUD, user management) vs `"member"` (view + own attendance only).
- CSRF: stateless HMAC-SHA256 token (key = `SECRET_KEY`, message = session cookie value). Applied to all mutating endpoints via `require_csrf` dependency. Tests override this with a no-op.

### Database

- SQLAlchemy 2.x with `Mapped[]` / `mapped_column()` style. All models inherit from `Base` in `app/database.py`.
- `models/__init__.py` imports all models so `Base.metadata` is fully populated before `create_all()` / Alembic.
- `get_db()` in `app/database.py` is the FastAPI dependency that yields a `SessionLocal` session.
- **Python 3.14 compat**: SQLAlchemy is pinned to `>=2.0.48` — earlier versions break on 3.14 due to `Union` type handling.

### Routes

Routes are registered dynamically in `app/main.py` via `importlib.import_module`. Each `routes/*.py` exports a `router = APIRouter()`. To add a new router: create the file, add an entry to `_routers` list in `app/main.py`.

### Templating & i18n

- `app/templates.py` provides a `render()` helper that injects `t(key)` (translation) and `current_locale` into every template context.
- Translation YAML files live in `locales/` (en, it, fr, de). Keys are dot-namespaced: `"players.form.name_label"`.
- Setting `DEBUG=true` raises `KeyError` on missing translation keys.

### Services layer

Business logic lives in `services/` and is called from routes. Key services: `auth_service` (bcrypt hashing, session cookies), `attendance_service` (auto-create `unknown` records when an event is added), `email_service` (SMTP), `notification_service` (multi-channel dispatch via `services/channels/`).

### Testing conventions

- Tests use an in-memory SQLite database (`StaticPool`); all tables are truncated between tests.
- `conftest.py` provides: `client` (CSRF disabled), `csrf_client` (CSRF enabled), `admin_client`, `member_client`, `admin_user`, `member_user`.
- Dependency overrides pattern: `app.dependency_overrides[get_db] = override_get_db`.

## Key environment variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | Session signing + CSRF — change in production |
| `DATABASE_URL` | `sqlite:///./data/proManager.db` | SQLAlchemy URL |
| `SMTP_HOST/PORT/USER/PASSWORD` | localhost/587/""/""  | Email delivery |
| `SMTP_FROM` | `noreply@promanager.local` | From address |
| `APP_NAME` | `ProManager` | Display name |
| `REMINDER_HOURS_BEFORE` | `24` | Event reminder lead time |
| `COOKIE_SECURE` | `False` | Set `True` for HTTPS |
| `DEBUG` | `False` | Raises on missing i18n keys |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` | `""` | Web Push credentials |

## Notes

- Port **7000** is the default for both local dev and Docker.
- Attendance records are auto-created with status `unknown` for all players when an event is added.
- `ruff` line length is 120; `models/*.py` suppresses `F821` (SQLAlchemy forward refs).
