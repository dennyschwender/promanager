# AGENTS.md — ProManager

FastAPI self-hosted player presence/absence tracker for sports teams.

## Commands

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt   # installs locked deps from requirements/dev.txt
cp .env.example .env                  # set SECRET_KEY at minimum
alembic upgrade head                  # run migrations before first start
uvicorn app.main:app --reload --host 0.0.0.0 --port 7000

pytest -v                             # all tests (in-memory SQLite, tables truncated per test)
pytest tests/test_auth.py::test_name  # single test
pytest --cov                          # with coverage

ruff check . && ruff format . && mypy .   # lint → format → typecheck (CI runs in this order)
```

## Architecture

### Request lifecycle

1. **`AuthMiddleware`** (`app/main.py:38`) — resolves signed `session_user_id` cookie → `request.state.user`, generates CSRF token, fetches unread notification count, throttled `last_seen_at` update (max 5 min).
2. **`LocaleMiddleware`** (`app/middleware/locale.py`) — resolves locale: user DB preference → cookie → `"en"` default → `request.state.locale`.
3. Route handlers use `Depends()` guards (`require_login`, `require_admin` from `routes/_auth_helpers.py`) and `get_db` for DB sessions.

### Auth & CSRF

- Session: `itsdangerous.TimestampSigner` cookie, 7-day expiry, `logout_all_at` invalidation (`app/session.py`).
- Roles: `"admin"` (full CRUD, user management), `"coach"` (own teams), `"member"` (view + own attendance only).
- CSRF: stateless HMAC-SHA256 (`app/csrf.py`). Form endpoints use `require_csrf` (reads form body), JSON endpoints use `require_csrf_header` (reads `X-CSRF-Token` header). Tests override both with no-op.
- `NotAuthenticated` → redirect to `/auth/login`; `NotAuthorized` → 403 page.

### Database

- SQLAlchemy 2.x `Mapped[]` / `mapped_column()`. All models in `models/`, imported by `models/__init__.py` to populate `Base.metadata`.
- `get_db()` in `app/database.py` yields `SessionLocal` session. SQLite uses `NullPool` + `check_same_thread=False`.
- Alembic with `render_as_batch=True` (required for SQLite ALTER TABLE). `alembic/env.py` reads `DATABASE_URL` from settings.

### Routes

Registered dynamically in `app/main.py:215` via `importlib.import_module`. Each `routes/*.py` exports `router = APIRouter()`. Add entry to `_routers` list to register.

### Templating & i18n

- `app/templates.py` provides `render()` injecting `t(key)` (translation), `current_locale`, `current_theme`, `enums` dict into every template.
- Translation JSON files in `locales/` (en, it, fr, de). `DEBUG=true` raises `KeyError` on missing keys.
- Default locale is `"it"` (not `"en"`).

### Services layer

Business logic in `services/`. Key: `auth_service` (bcrypt, session cookies), `attendance_service` (auto-create `unknown` records on event add), `email_service` (SMTP), `notification_service` (multi-channel via `services/channels/`), `calendar_service` (RFC 5545 iCal at `/{token}/feed.ics`).

### Telegram bot

Single persistent inline-keyboard message per user (`User.telegram_notification_message_id`). Navigation = `edit_message_text` on that message. `User.telegram_current_view` tracks active view for notification injection.

- `bot/views/` — renderers returning `ViewResult = (str, InlineKeyboardMarkup)`
- `bot/navigation.py` — `navigate()` edits message + updates view; `inject_notification()` / `inject_chat_notification()` prepend 🔔/💬 row
- Callback scheme documented in `bot/handlers.py` and `bot/absence_handlers.py`

### Background tasks

Started in `app/main.py` lifespan: `reminder_loop()` and `backup_loop()` from `services/scheduler.py`.

## Testing

- In-memory SQLite with `StaticPool`; all tables truncated between tests via `conftest.py:db` fixture.
- `conftest.py` provides: `client` (CSRF disabled), `csrf_client` (CSRF enabled), `admin_client`, `member_client`, `admin_user`, `member_user`.
- Dependency overrides: `app.dependency_overrides[get_db] = override_get_db`.
- `DATABASE_URL` must be set to `sqlite:///:memory:` **before** any app imports — done at top of `conftest.py:14`.

## Key env vars

| Variable | Default | Note |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | Session signing + CSRF |
| `DATABASE_URL` | `sqlite:///./data/proManager.db` | PostgreSQL also supported |
| `APP_URL` | `http://localhost:7000` | Magic links omitted when default |
| `COOKIE_SECURE` | `False` | Set `True` for HTTPS |
| `DEBUG` | `False` | Raises `KeyError` on missing i18n keys |
| `TELEGRAM_BOT_TOKEN` | `""` | Leave empty to disable bot |
| `TELEGRAM_WEBHOOK_URL` | `""` | Required for webhook mode |
| `TELEGRAM_WEBHOOK_SECRET` | `""` | Validates incoming webhooks |

## Config & tooling

- `ruff` line length 120; `models/*.py` suppresses `F821` (SQLAlchemy forward refs); `alembic/*` suppresses `E501`, `W291`, `I001`.
- `mypy` ignores `misc`, `valid-type`, `import-untyped` errors; excludes `scripts/`.
- Locked deps via `pip-compile`: edit `requirements/base.in` / `requirements/dev.in`, then run `pip-compile` to regenerate `requirements/base.txt` / `requirements/dev.txt`.
- Docker: single container, `entrypoint.sh` runs `alembic upgrade head` then `uvicorn`. Healthcheck at `/healthz`.
- Port **7000** default for dev and Docker.