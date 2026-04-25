# CLAUDE.md

Guidance for Claude Code (claude.ai/code) working in this repo.

## Project overview

ProManager = self-hosted player presence/absence tracker for sports teams, built with FastAPI. Coaches/managers handle seasons, teams, players, events, attendance in single Docker container.

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

1. **`AuthMiddleware`** (in `app/main.py`) runs first: resolves signed session cookie → `request.state.user`, generates CSRF token → `request.state.csrf_token`, fetches unread notification count.
2. **`LocaleMiddleware`** (`app/middleware/locale.py`) runs next: resolves locale from user DB preference → locale cookie → `"en"` default → `request.state.locale`.
3. Route handlers use FastAPI `Depends()` for auth guards (`require_login`, `require_admin` from `routes/_auth_helpers.py`) and `get_db` for DB sessions.

### Authentication & authorization

- Session cookie `session_user_id` signed with `itsdangerous.TimestampSigner` (7-day expiry).
- `require_login` / `require_admin` are `Depends()` guards. Raising `NotAuthenticated` → redirect to `/auth/login`; `NotAuthorized` → 403 page.
- Roles: `"admin"` (full CRUD, user management) vs `"member"` (view + own attendance only).
- CSRF: stateless HMAC-SHA256 token (key = `SECRET_KEY`, message = session cookie value). Applied to all mutating endpoints via `require_csrf` dependency. Tests override with no-op.

### Database

- SQLAlchemy 2.x with `Mapped[]` / `mapped_column()` style. All models inherit from `Base` in `app/database.py`.
- `models/__init__.py` imports all models so `Base.metadata` fully populated before `create_all()` / Alembic.
- `get_db()` in `app/database.py` = FastAPI dependency yielding `SessionLocal` session.
- **Python 3.14 compat**: SQLAlchemy pinned to `>=2.0.48` — earlier versions break on 3.14 due to `Union` type handling.

### Routes

Registered dynamically in `app/main.py` via `importlib.import_module`. Each `routes/*.py` exports `router = APIRouter()`. To add router: create file, add entry to `_routers` list in `app/main.py`.

### Templating & i18n

- `app/templates.py` provides `render()` helper injecting `t(key)` (translation) and `current_locale` into every template context.
- Translation YAML files in `locales/` (en, it, fr, de). Keys dot-namespaced: `"players.form.name_label"`.
- `DEBUG=true` raises `KeyError` on missing translation keys.

### Services layer

Business logic in `services/`, called from routes. Key services: `auth_service` (bcrypt hashing, session cookies), `attendance_service` (auto-create `unknown` records when event added), `email_service` (SMTP), `notification_service` (multi-channel dispatch via `services/channels/`).

### Telegram bot

Single persistent inline-keyboard message per user (`User.telegram_notification_message_id`). Navigation = `edit_message_text` on that message — no new messages during navigation. `User.telegram_current_view VARCHAR(20)` tracks the active view so notification injection works regardless of where the user is.

- `bot/views/` — renderers returning `ViewResult = (str, InlineKeyboardMarkup)`: `home.py`, `events.py`, `notifications.py`, `other.py`
- `bot/navigation.py` — `navigate()` edits the persistent message + updates `telegram_current_view`; `inject_notification()` / `inject_chat_notification()` prepend a 🔔/💬 row to current view without navigating
- Callback scheme: `home`, `nl`, `nl:N`, `n:ID`, `el`, `el:N`, `e:ID`, `ec:ID`, `ab`, `other:0`

### Testing conventions

- Tests use in-memory SQLite (`StaticPool`); all tables truncated between tests.
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
| `TELEGRAM_BOT_TOKEN` | `""` | Bot token from @BotFather — leave empty to disable |
| `TELEGRAM_WEBHOOK_URL` | `""` | Public HTTPS base URL of the app (required for webhook mode) |
| `TELEGRAM_WEBHOOK_SECRET` | `""` | Secret to validate incoming Telegram webhook requests |

## Claude Code autonomy

- **Code changes & refactoring**: Work autonomously on features, bug fixes, refactoring without per-step approval. Commit with descriptive messages, run tests before claiming done.
- **Ask for approval on**: destructive ops (force push, branch deletion), PRs/publishing, significant architecture changes, unclear requirements.
- **Testing expectations**: Tests must pass before commit. Use `pytest -v` and `ruff check` locally.

## Claude Code status line

Context-bar status line configured in `~/.claude/settings.json`:

```
Haiku 4.5 | 📁promanager | 🔀master (2 files uncommitted, synced 12m ago) | ██████░░░░ 65% of 200k tokens
💬 example user message preview
```

**Setup requirement**: Install `jq` for JSON parsing:
```bash
brew install jq          # macOS
sudo apt-get install jq  # Ubuntu/Debian
apk add jq              # Alpine
```

Script at `~/.claude/scripts/context-bar.sh` with 10 color themes. See `~/.claude/scripts/README.md` for details.

## Notes

- Port **7000** default for local dev and Docker.
- Attendance records auto-created with status `unknown` for all players when event added.
- `ruff` line length 120; `models/*.py` suppresses `F821` (SQLAlchemy forward refs).