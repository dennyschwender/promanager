# ProManager — AGENTS.md

Compact reference for agents working in this repo. Supersedes information in CLAUDE.md where they differ. Trust executable sources over prose.

## Commands (from pyproject.toml, CI, entrypoint)

```bash
source .venv/bin/activate
pip install -r requirements-dev.txt  # or: pip install -r requirements/dev.txt
cp .env.example .env                 # set SECRET_KEY
alembic upgrade head                 # entrypoint.sh does this too
uvicorn app.main:app --reload --host 0.0.0.0 --port 7000

# Test categories (pytest markers)
pytest -m core            # Auth, config, infra
pytest -m events          # Event CRUD, calendar, attendance
pytest -m players         # Players, absences, teams
pytest -m notifications   # Emails, telegram channels, inbox
pytest -m integration     # Users, dashboard, seasons, full flows
pytest -m telegram        # Telegram bot
pytest -m i18n            # Locale/translation
pytest -m "not slow"      # All except slow (scheduler, import)
pytest --cov              # Full suite with coverage

ruff check . && ruff format . && mypy .        # CI order: ruff → mypy → pytest
```

## Architecture

- **Entrypoint**: `app/main.py` — `create_app()` factory, top-level `app = create_app()` for uvicorn. Routes registered dynamically via `_routers` list (add new route modules there).
- **Settings**: `app/config.py` — pydantic-settings, loaded from `.env`. Singleton `settings`.
- **Database**: SQLite with `NullPool` in production (avoids QueuePool exhaustion). Tests use in-memory SQLite with `StaticPool`.
- **Alembic**: `render_as_batch=True` in `alembic/env.py` (required for SQLite ALTER TABLE).
- **Template rendering**: `app/templates.py` — `render()` auto-injects `t(key)` (i18n), `current_locale`, `current_theme`, `enums` lookup dicts. Default locale is `"it"`.
- **Auth**: Signed session cookie (`session_user_id`, itsdangerous TimestampSigner, 7-day expiry). `AuthMiddleware` runs first on every request. `logout_all_at` field invalidates all sessions.
- **CSRF**: Stateless HMAC-SHA256. Applied via `require_csrf` (form) / `require_csrf_header` (JSON) dependencies.
- **Background tasks**: `reminder_loop()` + `backup_loop()` in `services/scheduler.py` — created in `create_app()` lifespan.
- **Telegram bot**: `bot/__init__.py` has `init_application()` / `shutdown_application()`. Module-level `bot.telegram_app`.

## Models (all 22)

All imported in `models/__init__.py` so `Base.metadata` is fully populated. SQLAlchemy 2.x `Mapped[]` / `mapped_column()` style.

## Testing quirks

- `DATABASE_URL=sqlite:///:memory:` must be set **before** any app imports (`conftest.py:14`)
- Tables truncated between every test (function scope fixture)
- `client` fixture overrides CSRF to no-op; `csrf_client` keeps enforcement
- TestClient uses `raise_server_exceptions=False, follow_redirects=False`
- `admin_user` / `member_user` fixtures use `create_user(db, username, email, password, role=...)`
- `admin_client` / `member_client` pre-authenticate by setting session cookie
- Override pattern: `app.dependency_overrides[get_db] = override_get_db`

## Toolchain config (don't guess these)

- **ruff**: line-length 120, `models/*.py` suppresses F821 (SQLAlchemy forward refs), `alembic/*` suppresses E501/W291/I001
- **mypy**: `ignore_missing_imports=true`, `disable_error_code=["misc", "valid-type", "import-untyped"]`, excludes `scripts/`
- **CI** (`.github/workflows/ci.yml`): ruff 0.4.4 pinned, mypy uses `requirements/dev.txt`, pytest with `--cov=. --cov-report=term-missing`
- **Python 3.14 compat**: SQLAlchemy pinned `>=2.0.48` in requirements

## Route registration (gotcha)

New route modules must be:
1. Created in `routes/` with `router = APIRouter()`
2. Added to the `_routers` list in `app/main.py` as `(module_path, prefix, tag)`
3. Import statement in `app/main.py` is NOT needed (dynamic via `importlib.import_module`)

## Key conventions

- `render()` is the only way to return HTML responses — always use it
- Attendance auto-created with status `unknown` when event added
- Port 7000 default everywhere
- Three roles: `"admin"` (full CRUD), `"coach"` (own teams), `"member"` (own attendance)
- Notification preferences now opt-in (default disabled) since 8767c54
- Locked deps via `pip-compile`: edit `requirements/base.in` / `requirements/dev.in`, regenerate `requirements/base.txt` / `requirements/dev.txt`
- Docker: single container, `entrypoint.sh` runs `alembic upgrade head` then `uvicorn`. Healthcheck at `/healthz`.

## Deploy

```bash
ssh pi5
cd ~/dockerimages
./updateDocker proManager
```

Pushes to GitHub master, then SSH into the Pi5 and run the update script.

## Existing instruction files

- `CLAUDE.md` — detailed, includes full Telegram callback table. Keep in sync with codebase.
- `.claudeignore` / `.claudignore` — skip `node_modules/`, `.venv/`, `.git/`, build outputs, media files

## Learnings

- **Calendar i18n conflict**: `locales/*.json` already had a `"calendar"` section for calendar sync (profile page). Adding a second `"calendar"` key creates a JSON duplicate — Python json.load keeps the last one, overwriting the first. Always merge new keys into the existing section at the end of the file (~line 1064).
- **Template blocks**: `base.html` uses `{% block scripts %}` not `{% block scripts_extra %}` — check existing blocks before creating new ones.
- **Route order**: `/events/calendar` must be registered BEFORE `routes.events` in `_routers` list in `app/main.py` — otherwise the events router's `/{event_id}` matches "calendar" as an int path param first (returning 422).
