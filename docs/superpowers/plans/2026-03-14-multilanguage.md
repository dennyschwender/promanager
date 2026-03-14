# Multilanguage Support (EN, IT, FR, DE) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add full EN/IT/FR/DE multilanguage support to ProManager covering all UI templates, navigation, forms, error pages, and outgoing emails.

**Architecture:** A custom loader (`app/i18n.py`) reads four JSON locale files at startup into memory using `json.load`; a `t(key, locale, **kwargs)` function handles lookup, `%{var}` interpolation, and EN fallback. `python-i18n` is listed as a dependency per the spec but the loader is implemented directly without calling the `i18n` API — this keeps the implementation simple and avoids indirect behaviour. A `LocaleMiddleware` resolves the active locale per request (DB → cookie → `"en"`) and stores it on `request.state.locale`. A `render()` helper in `app/templates.py` injects a locale-bound `t()` partial and `current_locale` into every template context automatically.

**Tech Stack:** FastAPI, Jinja2, SQLAlchemy 2.x, python-i18n>=0.3.9, Alembic, pytest

**Spec:** `docs/superpowers/specs/2026-03-14-multilanguage-design.md`

---

## Chunk 1: Foundation — i18n loader, config, middleware, templates helper, wiring

### Task 1: Add dependency and create English locale file

**Files:**
- Modify: `requirements.txt`
- Create: `locales/en.json`

- [ ] **Step 1: Add python-i18n to requirements.txt**

Add after `slowapi==0.1.9`:
```
python-i18n>=0.3.9
```

- [ ] **Step 2: Create `locales/en.json` with the full key set**

```json
{
  "nav": {
    "dashboard": "Dashboard",
    "events": "Events",
    "players": "Players",
    "teams": "Teams",
    "seasons": "Seasons",
    "reports": "Reports",
    "notifications": "Notifications",
    "profile": "Profile",
    "sign_out": "Sign Out",
    "login": "Login",
    "register_user": "Register User",
    "language": "Language"
  },
  "auth": {
    "login_title": "Sign In",
    "username": "Username",
    "password": "Password",
    "submit": "Sign In",
    "register_title": "Register User",
    "logout": "Sign Out",
    "profile_title": "My Profile",
    "role": "Role",
    "email": "Email",
    "save_preferences": "Save preferences",
    "notification_preferences": "Notification Preferences",
    "language_preference": "Language",
    "register_submit": "Register"
  },
  "dashboard": {
    "title": "Dashboard",
    "upcoming_events": "Upcoming Events",
    "next_30_days": "next 30 days",
    "pending_responses": "Pending Responses",
    "upcoming_events_label": "upcoming events",
    "next_5_events": "Next 5 Events",
    "no_upcoming": "No upcoming events.",
    "create_one": "Create one",
    "quick_actions": "Quick Actions",
    "season_reports": "Season Reports",
    "no_active_season": "No active season.",
    "manage_seasons": "Manage seasons"
  },
  "events": {
    "title": "Events",
    "new": "+ New Event",
    "upcoming": "Upcoming",
    "past": "Past Events",
    "date": "Date",
    "time": "Time",
    "title_col": "Title",
    "type": "Type",
    "location": "Location",
    "actions": "Actions",
    "no_upcoming": "No upcoming events.",
    "no_past": "No past events.",
    "attendance": "Attendance",
    "edit": "Edit",
    "view": "View",
    "recurring": "Recurring",
    "all_seasons": "All Seasons",
    "all_teams": "All Teams",
    "season": "Season",
    "team": "Team",
    "detail_title": "Event",
    "back_to_events": "Back to Events",
    "notify_players": "Notify Players",
    "delete": "Delete Event",
    "confirm_delete": "Delete this event?",
    "new_title": "New Event",
    "edit_title": "Edit Event",
    "save": "Save Event"
  },
  "attendance": {
    "title": "Mark Attendance",
    "status_attend": "Attending",
    "status_absent": "Absent",
    "status_unknown": "Unknown",
    "save": "Save",
    "player": "Player",
    "status": "Status",
    "notes": "Notes",
    "back": "Back to Event"
  },
  "players": {
    "title": "Players",
    "new": "+ New Player",
    "import": "Import",
    "name": "Name",
    "email": "Email",
    "phone": "Phone",
    "team": "Team",
    "active": "Active",
    "actions": "Actions",
    "edit": "Edit",
    "view": "View",
    "no_players": "No players found.",
    "detail_title": "Player",
    "back": "Back to Players",
    "new_title": "New Player",
    "edit_title": "Edit Player",
    "save": "Save Player",
    "import_title": "Import Players",
    "import_submit": "Import"
  },
  "teams": {
    "title": "Teams",
    "new": "+ New Team",
    "name": "Name",
    "season": "Season",
    "players": "Players",
    "actions": "Actions",
    "edit": "Edit",
    "no_teams": "No teams found.",
    "new_title": "New Team",
    "edit_title": "Edit Team",
    "save": "Save Team",
    "back": "Back to Teams"
  },
  "seasons": {
    "title": "Seasons",
    "new": "+ New Season",
    "name": "Name",
    "active": "Active",
    "actions": "Actions",
    "edit": "Edit",
    "no_seasons": "No seasons found.",
    "new_title": "New Season",
    "edit_title": "Edit Season",
    "save": "Save Season",
    "back": "Back to Seasons"
  },
  "reports": {
    "season_title": "Season Report",
    "player_title": "Player Report",
    "back": "Back to Reports",
    "player": "Player",
    "attended": "Attended",
    "absent": "Absent",
    "unknown": "Unknown",
    "total": "Total",
    "attendance_rate": "Attendance Rate"
  },
  "notifications": {
    "title": "Notifications",
    "no_notifications": "No notifications.",
    "mark_read": "Mark all as read",
    "inbox": "Inbox"
  },
  "common": {
    "save": "Save",
    "cancel": "Cancel",
    "delete": "Delete",
    "confirm": "Are you sure?",
    "yes": "Yes",
    "no": "No",
    "loading": "Loading\u2026",
    "back": "Back",
    "edit": "Edit",
    "new_season": "+ New Season",
    "new_team": "+ New Team",
    "new_player": "+ New Player",
    "new_event": "+ New Event"
  },
  "errors": {
    "404_title": "Page Not Found",
    "404_body": "The page you requested could not be found.",
    "500_title": "Server Error",
    "500_body": "Something went wrong. Please try again.",
    "403_title": "Access Denied",
    "403_body": "You do not have permission to view this page.",
    "back_home": "Back to Dashboard"
  },
  "notify": {
    "title": "Notify Players",
    "send": "Send Notification",
    "back": "Back to Event"
  },
  "email": {
    "reminder_subject": "Reminder: %{event_name} on %{date}",
    "reminder_body": "Hi %{name},\n\nThis is a reminder for the upcoming event:\n\n  Event:    %{event_name}\n  When:     %{when}\n  Location: %{location}\n\nPlease make sure to update your attendance status.\n\nBest regards,\n%{app_name}",
    "reminder_body_html": "<p>Hi <strong>%{name}</strong>,</p><p>This is a reminder for the upcoming event:</p><table><tr><td><strong>Event</strong></td><td>%{event_name}</td></tr><tr><td><strong>When</strong></td><td>%{when}</td></tr><tr><td><strong>Location</strong></td><td>%{location}</td></tr></table><p>Please update your attendance status.</p><p>Best regards,<br>%{app_name}</p>",
    "attendance_subject": "Please confirm attendance: %{event_name} on %{date}",
    "attendance_body": "Hi %{name},\n\nPlease confirm your attendance for:\n\n  Event: %{event_name}\n  Date:  %{date}\n\nUpdate your status here: %{url}\n\nBest regards,\n%{app_name}",
    "attendance_body_html": "<p>Hi <strong>%{name}</strong>,</p><p>Please confirm your attendance for <strong>%{event_name}</strong> on %{date}.</p><p><a href=\"%{url}\">Click here to update your attendance status</a></p><p>Best regards,<br>%{app_name}</p>"
  }
}
```

- [ ] **Step 3: Install the dependency**

```bash
pip install python-i18n>=0.3.9
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt locales/en.json
git commit -m "feat: add python-i18n dependency and English locale file"
```

---

### Task 2: Add DEBUG flag to config

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: Add `DEBUG` field to Settings class**

In `app/config.py`, after `COOKIE_SECURE: bool = False`, add:
```python
# ── i18n ──────────────────────────────────────────────────────────────────
# Set DEBUG=true in .env to raise KeyError on missing translation keys
DEBUG: bool = False
```

- [ ] **Step 2: Verify settings loads correctly**

```bash
python -c "from app.config import settings; print(settings.DEBUG)"
```
Expected output: `False`

- [ ] **Step 3: Commit**

```bash
git add app/config.py
git commit -m "feat: add DEBUG config flag for i18n dev mode"
```

---

### Task 3: Create the i18n translation loader

**Files:**
- Create: `app/i18n.py`
- Create: `tests/test_i18n.py`

- [ ] **Step 1: Write the failing tests first**

Create `tests/test_i18n.py`:
```python
"""Tests for app/i18n.py translation loader."""
from __future__ import annotations

import os
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_t(debug: bool = False):
    """Import a fresh t() with the given DEBUG setting."""
    os.environ["DEBUG"] = "true" if debug else "false"
    # Force reload so settings picks up env var
    import importlib
    import app.config as _cfg
    importlib.reload(_cfg)
    import app.i18n as _i18n
    importlib.reload(_i18n)
    from app.i18n import t
    return t


# ---------------------------------------------------------------------------
# Basic lookup
# ---------------------------------------------------------------------------

def test_t_returns_english_string():
    t = _make_t()
    assert t("nav.dashboard", "en") == "Dashboard"


def test_t_returns_italian_string():
    t = _make_t()
    result = t("common.save", "it")
    assert isinstance(result, str)
    assert len(result) > 0


def test_t_returns_french_string():
    t = _make_t()
    result = t("common.save", "fr")
    assert isinstance(result, str)


def test_t_returns_german_string():
    t = _make_t()
    result = t("common.save", "de")
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Fallback behaviour
# ---------------------------------------------------------------------------

def test_t_unsupported_locale_falls_back_to_en():
    t = _make_t()
    assert t("nav.dashboard", "xx") == t("nav.dashboard", "en")


def test_t_missing_key_raises_in_debug(tmp_path, monkeypatch):
    t = _make_t(debug=True)
    with pytest.raises(KeyError):
        t("nav.nonexistent_key_xyz", "en")


def test_t_missing_key_falls_back_to_en_in_production():
    """A key missing in a locale but present in 'en' should return the 'en' value."""
    import importlib
    import app.i18n as _i18n
    importlib.reload(_i18n)
    # Mutate the live _translations AFTER reload so reload doesn't undo it
    _i18n._translations["it"].setdefault("nav", {}).pop("dashboard", None)
    result = _i18n.t("nav.dashboard", "it")
    assert result == "Dashboard"  # fell back to en value


# ---------------------------------------------------------------------------
# Variable interpolation
# ---------------------------------------------------------------------------

def test_t_interpolates_variables():
    t = _make_t()
    result = t("email.reminder_subject", "en", event_name="Training", date="2026-03-20")
    assert "Training" in result
    assert "2026-03-20" in result
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_i18n.py -v
```
Expected: `ModuleNotFoundError` or `ImportError` — `app/i18n.py` doesn't exist yet.

- [ ] **Step 3: Create `app/i18n.py`**

```python
"""app/i18n.py — Translation loader and t() helper.

Loads all locale JSON files at import time. Exposes t(key, locale, **kwargs)
for string lookup with %{var} interpolation.

Dev mode (settings.DEBUG=True): missing key raises KeyError.
Production (settings.DEBUG=False): missing key logs a warning and returns
the 'en' value, or the bare key if 'en' also lacks it.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_LOCALES: list[str] = ["en", "it", "fr", "de"]
_LOCALES_DIR = Path(__file__).parent.parent / "locales"

# ---------------------------------------------------------------------------
# Load all locale files at startup
# ---------------------------------------------------------------------------

def _load_locales() -> dict[str, dict]:
    data: dict[str, dict] = {}
    for lang in SUPPORTED_LOCALES:
        path = _LOCALES_DIR / f"{lang}.json"
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                data[lang] = json.load(fh)
        else:
            logger.warning("Locale file not found: %s", path)
            data[lang] = {}
    return data


_translations: dict[str, dict] = _load_locales()


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def _get(data: dict, key: str):
    """Traverse dot-separated key into nested dict. Returns None if missing."""
    parts = key.split(".")
    node = data
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _interpolate(template: str, **kwargs) -> str:
    """Replace %{var} placeholders with kwargs values."""
    def replacer(m: re.Match) -> str:
        return str(kwargs.get(m.group(1), m.group(0)))
    return re.sub(r"%\{(\w+)\}", replacer, template)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def t(key: str, locale: str, **kwargs) -> str:
    """Look up a translation key for the given locale.

    Falls back to 'en' if locale is unsupported or key is missing.
    In DEBUG mode, raises KeyError for missing keys instead of falling back.
    """
    if locale not in SUPPORTED_LOCALES:
        locale = "en"

    value = _get(_translations.get(locale, {}), key)

    if value is None:
        if settings.DEBUG:
            raise KeyError(f"Missing translation key {key!r} for locale {locale!r}")
        logger.warning("Missing translation key %r for locale %r — falling back to 'en'", key, locale)
        value = _get(_translations.get("en", {}), key)

    if value is None:
        return key  # Last resort: return the bare key

    if isinstance(value, str):
        return _interpolate(value, **kwargs) if kwargs else value

    return str(value)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_i18n.py -v
```
Expected: All pass (some locale tests may be `it`/`fr`/`de` stubs until locale files are written — those tests just check `isinstance(result, str)` and will pass since fallback returns a string).

- [ ] **Step 5: Commit**

```bash
git add app/i18n.py tests/test_i18n.py
git commit -m "feat: add i18n translation loader with t() helper and tests"
```

---

### Task 4: Create LocaleMiddleware

**Files:**
- Create: `app/middleware/__init__.py`
- Create: `app/middleware/locale.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_i18n.py`:
```python
# ---------------------------------------------------------------------------
# LocaleMiddleware integration
# ---------------------------------------------------------------------------

def test_locale_cookie_sets_request_locale(client):
    """A locale cookie should cause templates to render in that locale."""
    client.cookies.set("locale", "it")
    resp = client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 200
    # page should render without error — locale plumbing works


def test_invalid_locale_cookie_falls_back_to_en(client):
    client.cookies.set("locale", "zz")
    resp = client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 200
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_i18n.py::test_locale_cookie_sets_request_locale -v
```
Expected: FAIL (middleware not wired yet).

- [ ] **Step 3: Create `app/middleware/__init__.py`** (empty)

```python
```

- [ ] **Step 4: Create `app/middleware/locale.py`**

```python
"""app/middleware/locale.py — Resolves the active locale for each request.

Resolution order:
  1. Logged-in user: request.state.user.locale
  2. Guest: 'locale' cookie
  3. Default: 'en'

Sets request.state.locale.

Registration order in app/main.py (LIFO — last added runs first):
  app.add_middleware(LocaleMiddleware)  # added first → runs second
  app.add_middleware(AuthMiddleware)   # added second → runs first
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.i18n import SUPPORTED_LOCALES


class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        locale = "en"

        # 1. Authenticated user preference
        user = getattr(request.state, "user", None)
        if user is not None:
            user_locale = getattr(user, "locale", None)
            if user_locale and user_locale in SUPPORTED_LOCALES:
                locale = user_locale

        # 2. Cookie fallback — only for unauthenticated users.
        # Authenticated users always use their DB locale (even if it is "en").
        # To change locale, authenticated users must POST to /set-locale.
        if locale == "en" and user is None:
            cookie_locale = request.cookies.get("locale", "")
            if cookie_locale in SUPPORTED_LOCALES:
                locale = cookie_locale

        request.state.locale = locale
        return await call_next(request)
```

- [ ] **Step 5: Register middleware in `app/main.py`**

In `app/main.py`, after `from app.session import ...` imports, add:
```python
from app.middleware.locale import LocaleMiddleware
```

In the `create_app()` function, find the line:
```python
app.add_middleware(AuthMiddleware)
```
Replace with:
```python
app.add_middleware(LocaleMiddleware)   # added first → executes second (inner)
app.add_middleware(AuthMiddleware)     # added second → executes first (outer)
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_i18n.py -v
```
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add app/middleware/__init__.py app/middleware/locale.py app/main.py tests/test_i18n.py
git commit -m "feat: add LocaleMiddleware to resolve locale per request"
```

---

### Task 5: Update templates.py with render() helper

**Files:**
- Modify: `app/templates.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_i18n.py`:
```python
def test_template_t_function_available(client):
    """t() must be available in templates — rendered login page should not crash."""
    resp = client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 200
    # Once templates use t(), this confirms the binding works
```

- [ ] **Step 2: Update `app/templates.py`**

Replace the entire file with:
```python
"""app/templates.py — Shared Jinja2Templates instance and render() helper.

Import `templates` from here instead of instantiating Jinja2Templates
in each route module. This ensures globals (now, urlencode) are available
in every rendered template.

Use render() to get t() and current_locale automatically injected.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote_plus

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.i18n import t as _t

templates = Jinja2Templates(directory="templates")
templates.env.globals["now"] = lambda: datetime.now(timezone.utc)
templates.env.filters["urlencode"] = quote_plus


def render(
    request: Request,
    template_name: str,
    context: dict,
    status_code: int = 200,
) -> HTMLResponse:
    """Render a template with i18n context (t, current_locale) auto-injected."""
    locale = getattr(request.state, "locale", "en")
    i18n_ctx = {
        "t": lambda key, **kw: _t(key, locale, **kw),
        "current_locale": locale,
    }
    return templates.TemplateResponse(
        request,
        template_name,
        {**i18n_ctx, **context},
        status_code=status_code,
    )
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_i18n.py -v && pytest -x -q
```
Expected: All pass (existing routes still use `templates.TemplateResponse` directly — that's fine for now, they'll be updated in Task 10).

- [ ] **Step 4: Commit**

```bash
git add app/templates.py tests/test_i18n.py
git commit -m "feat: add render() helper to templates.py with auto i18n context injection"
```

---

## Chunk 2: Database, /set-locale route

### Task 6: Add locale column to User model and migrate

**Files:**
- Modify: `models/user.py`
- Create: `alembic/versions/a1b2_add_user_locale.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_i18n.py`:
```python
def test_user_has_locale_field(db, admin_user):
    """User model must have a locale field defaulting to 'en'."""
    assert hasattr(admin_user, "locale")
    assert admin_user.locale == "en"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_i18n.py::test_user_has_locale_field -v
```
Expected: FAIL — `User` has no `locale` attribute.

- [ ] **Step 3: Add `locale` column to `models/user.py`**

After the `api_token_hash` field, add:
```python
# Preferred UI locale — one of: en, it, fr, de
locale: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
```

- [ ] **Step 4: Run test**

```bash
pytest tests/test_i18n.py::test_user_has_locale_field -v
```
Expected: PASS (conftest.py calls `Base.metadata.create_all` which picks up the new column).

- [ ] **Step 5: Create Alembic migration**

Create `alembic/versions/a1b2_add_user_locale.py`:
```python
"""add_user_locale

Revision ID: a1b2c3d4e5f6
Revises: 17990e6d0210
Create Date: 2026-03-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "17990e6d0210"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("locale", sa.String(5), nullable=False, server_default="en"),
    )


def downgrade() -> None:
    op.drop_column("users", "locale")
```

- [ ] **Step 6: Apply migration to dev DB**

```bash
.venv/bin/alembic upgrade head
```
Expected: `Running upgrade 17990e6d0210 -> a1b2c3d4e5f6, add_user_locale`

- [ ] **Step 7: Run full test suite**

```bash
pytest -x -q
```
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add models/user.py alembic/versions/a1b2_add_user_locale.py
git commit -m "feat: add locale column to users table with migration"
```

---

### Task 7: Create /set-locale endpoint

**Files:**
- Create: `routes/locale.py`
- Modify: `app/main.py`
- Create: `tests/test_locale_route.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_locale_route.py`:
```python
"""Tests for POST /set-locale."""
from __future__ import annotations

from services.auth_service import create_user, create_session_cookie


def test_set_locale_sets_cookie(client):
    resp = client.post(
        "/set-locale",
        data={"locale": "it", "next": "/dashboard"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"
    assert resp.cookies.get("locale") == "it"


def test_set_locale_invalid_locale_returns_400(client):
    resp = client.post(
        "/set-locale",
        data={"locale": "xx"},
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_set_locale_defaults_redirect_to_dashboard(client):
    resp = client.post(
        "/set-locale",
        data={"locale": "fr"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"


def test_set_locale_rejects_external_next(client):
    resp = client.post(
        "/set-locale",
        data={"locale": "de", "next": "https://evil.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"


def test_set_locale_updates_user_db(admin_client, admin_user, db):
    resp = admin_client.post(
        "/set-locale",
        data={"locale": "de", "next": "/dashboard"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db.refresh(admin_user)
    assert admin_user.locale == "de"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_locale_route.py -v
```
Expected: FAIL — route doesn't exist yet.

- [ ] **Step 3: Create `routes/locale.py`**

```python
"""routes/locale.py — Language preference endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from fastapi import Depends

from app.database import get_db
from app.i18n import SUPPORTED_LOCALES

router = APIRouter(tags=["locale"])


def _safe_next(next_url: str) -> str:
    """Return next_url only if it is a safe relative path."""
    if next_url and next_url.startswith("/") and "://" not in next_url:
        return next_url
    return "/dashboard"


@router.post("/set-locale")
async def set_locale(
    request: Request,
    locale: str = Form(...),
    next: str = Form(default="/dashboard"),
    db: Session = Depends(get_db),
):
    if locale not in SUPPORTED_LOCALES:
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "Unsupported locale"}, status_code=400)

    redirect_to = _safe_next(next)
    response = RedirectResponse(url=redirect_to, status_code=302)
    response.set_cookie("locale", locale, max_age=31536000, path="/", httponly=False)

    # Persist to DB if authenticated
    user = getattr(request.state, "user", None)
    if user is not None:
        user.locale = locale
        db.add(user)
        db.commit()

    return response
```

- [ ] **Step 4: Register router in `app/main.py`**

In `create_app()`, after the notifications router block, add:
```python
# ── Locale switcher ───────────────────────────────────────────────────
from routes.locale import router as _locale_router  # noqa: PLC0415
app.include_router(_locale_router)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_locale_route.py -v
```
Expected: All pass.

- [ ] **Step 6: Run full suite**

```bash
pytest -x -q
```
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add routes/locale.py app/main.py tests/test_locale_route.py
git commit -m "feat: add /set-locale endpoint with cookie + DB persistence"
```

---

## Chunk 3: Email service i18n

### Task 8: Add locale support to email service

**Files:**
- Modify: `services/email_service.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_email_i18n.py`:
```python
"""Tests for locale-aware email service."""
from __future__ import annotations

from unittest.mock import patch


def test_send_event_reminder_uses_locale(monkeypatch):
    """send_event_reminder should use the provided locale."""
    sent = {}

    def mock_send(to, subject, body_html, body_text=""):
        sent["subject"] = subject
        sent["body"] = body_text
        return True

    monkeypatch.setattr("services.email_service.send_email", mock_send)

    from services.email_service import send_event_reminder
    import datetime

    send_event_reminder(
        player_email="p@test.com",
        player_name="Mario",
        event_title="Training",
        event_date=datetime.date(2026, 3, 20),
        event_time=None,
        event_location="Gym",
        locale="en",
    )
    assert "Training" in sent["subject"]


def test_send_attendance_request_uses_locale(monkeypatch):
    sent = {}

    def mock_send(to, subject, body_html, body_text=""):
        sent["subject"] = subject
        return True

    monkeypatch.setattr("services.email_service.send_email", mock_send)

    from services.email_service import send_attendance_request
    import datetime

    send_attendance_request(
        player_email="p@test.com",
        player_name="Mario",
        event_title="Match",
        event_date=datetime.date(2026, 3, 20),
        attendance_url="http://localhost/attendance/1",
        locale="en",
    )
    assert "Match" in sent["subject"]


def test_send_event_reminder_defaults_locale_to_en(monkeypatch):
    """locale param must be optional with default 'en'."""
    called = {}

    def mock_send(to, subject, body_html, body_text=""):
        called["ok"] = True
        return True

    monkeypatch.setattr("services.email_service.send_email", mock_send)

    from services.email_service import send_event_reminder
    import datetime

    # Call without locale kwarg — should not raise
    send_event_reminder(
        player_email="p@test.com",
        player_name="Mario",
        event_title="Training",
        event_date=datetime.date(2026, 3, 20),
        event_time=None,
        event_location="Gym",
    )
    assert called.get("ok")
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_email_i18n.py -v
```
Expected: FAIL — `locale` param not accepted yet.

- [ ] **Step 3: Update `services/email_service.py`**

Replace `send_event_reminder` and `send_attendance_request` with locale-aware versions:

```python
from app.i18n import t as _t  # add at top of file, after existing imports


def send_event_reminder(
    player_email: str,
    player_name: str,
    event_title: str,
    event_date,
    event_time,
    event_location: str,
    locale: str = "en",
) -> bool:
    """Send an event reminder to a player."""
    time_str = event_time.strftime("%H:%M") if event_time else ""
    date_str = event_date.strftime("%Y-%m-%d") if event_date else str(event_date)
    when = f"{date_str} {time_str}".strip()
    location = event_location or "TBD"

    subject = _t("email.reminder_subject", locale, event_name=event_title, date=date_str)
    body_text = _t(
        "email.reminder_body", locale,
        name=player_name, event_name=event_title,
        when=when, location=location, app_name=settings.APP_NAME,
    )
    body_html = _t(
        "email.reminder_body_html", locale,
        name=player_name, event_name=event_title,
        when=when, location=location, app_name=settings.APP_NAME,
    )
    return send_email(player_email, subject, body_html, body_text)


def send_attendance_request(
    player_email: str,
    player_name: str,
    event_title: str,
    event_date,
    attendance_url: str,
    locale: str = "en",
) -> bool:
    """Send an attendance request (RSVP) to a player."""
    date_str = event_date.strftime("%Y-%m-%d") if event_date else str(event_date)

    subject = _t("email.attendance_subject", locale, event_name=event_title, date=date_str)
    body_text = _t(
        "email.attendance_body", locale,
        name=player_name, event_name=event_title,
        date=date_str, url=attendance_url, app_name=settings.APP_NAME,
    )
    body_html = _t(
        "email.attendance_body_html", locale,
        name=player_name, event_name=event_title,
        date=date_str, url=attendance_url, app_name=settings.APP_NAME,
    )
    return send_email(player_email, subject, body_html, body_text)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_email_i18n.py -v && pytest -x -q
```
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add services/email_service.py tests/test_email_i18n.py
git commit -m "feat: add locale param to email service helpers"
```

---

## Chunk 4: Template updates

### Task 9: Update base.html (navbar language switcher + all nav strings)

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Replace hardcoded strings in `templates/base.html`**

Replace the entire file with the i18n version below. Key changes:
- All nav link labels use `{{ t('nav.xxx') }}`
- Add a compact language `<select>` in the nav after the username dropdown
- `<html lang="{{ current_locale }}">`

```html
<!DOCTYPE html>
<html lang="{{ current_locale }}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}ProManager{% endblock %}</title>
  <link rel="stylesheet" href="/static/css/pico.min.css">
  <link rel="stylesheet" href="/static/css/flatpickr.min.css">
  <link rel="stylesheet" href="/static/css/main.css">
  {% block head_extra %}{% endblock %}
  <style>
  .notif-bell { position: relative; text-decoration: none; font-size: 1.1rem; }
  .notif-badge {
    position: absolute; top: -6px; right: -8px;
    background: #ef4444; color: #fff;
    font-size: .65rem; font-weight: 700; line-height: 1;
    padding: 2px 4px; border-radius: 10px; white-space: nowrap;
  }
  </style>
</head>
<body>

<nav class="container-fluid">
  <ul>
    <li><a href="/dashboard" style="font-weight:700;text-decoration:none;">⬡ ProManager</a></li>
  </ul>
  <ul>
    {% if user %}
      {% set path = request.url.path %}
      <li><a href="/dashboard" class="{% if path == '/dashboard' %}nav-active{% endif %}">{{ t('nav.dashboard') }}</a></li>
      <li><a href="/events"    class="{% if path.startswith('/events') %}nav-active{% endif %}">{{ t('nav.events') }}</a></li>
      <li><a href="/players"   class="{% if path.startswith('/players') %}nav-active{% endif %}">{{ t('nav.players') }}</a></li>
      <li><a href="/teams"     class="{% if path.startswith('/teams') %}nav-active{% endif %}">{{ t('nav.teams') }}</a></li>
      {% if user.is_admin %}
        <li><a href="/seasons"  class="{% if path.startswith('/seasons') %}nav-active{% endif %}">{{ t('nav.seasons') }}</a></li>
        <li><a href="/reports"  class="{% if path.startswith('/reports') %}nav-active{% endif %}">{{ t('nav.reports') }}</a></li>
      {% endif %}
      <li>
        <a href="/notifications" class="notif-bell" title="{{ t('nav.notifications') }}" aria-label="{{ t('nav.notifications') }}">
          🔔
          {% if request.state.unread_count > 0 %}
            <span class="notif-badge">{{ request.state.unread_count }}</span>
          {% endif %}
        </a>
      </li>
      <li>
        <details role="list" style="list-style:none;">
          <summary aria-haspopup="listbox" role="link">{{ user.username }}</summary>
          <ul role="listbox">
            {% if user.is_admin %}
              <li><a href="/auth/register">{{ t('nav.register_user') }}</a></li>
              <li><hr style="margin:.25rem 0;"></li>
            {% endif %}
            <li><a href="/profile">{{ t('nav.profile') }}</a></li>
            <li><a href="/auth/logout">{{ t('nav.sign_out') }}</a></li>
          </ul>
        </details>
      </li>
    {% else %}
      <li><a href="/auth/login" role="button" class="outline">{{ t('nav.login') }}</a></li>
    {% endif %}
    <li>
      <form method="post" action="/set-locale" style="display:inline;margin:0;">
        <input type="hidden" name="next" value="{{ request.url.path }}">
        <select name="locale" onchange="this.form.submit()" style="margin:0;padding:.2rem .4rem;font-size:.85rem;width:auto;">
          <option value="en" {% if current_locale == 'en' %}selected{% endif %}>EN</option>
          <option value="it" {% if current_locale == 'it' %}selected{% endif %}>IT</option>
          <option value="fr" {% if current_locale == 'fr' %}selected{% endif %}>FR</option>
          <option value="de" {% if current_locale == 'de' %}selected{% endif %}>DE</option>
        </select>
      </form>
    </li>
  </ul>
</nav>

<main class="container" style="padding-top:1.5rem;">
  {% block breadcrumb %}{% endblock %}
  {% block content %}{% endblock %}
</main>

<footer class="container site-footer">
  <div class="footer-inner">
    <span>⬡ ProManager</span>
    {% if user %}
    <span>
      <a href="/dashboard">{{ t('nav.dashboard') }}</a> ·
      <a href="/events">{{ t('nav.events') }}</a> ·
      <a href="/players">{{ t('nav.players') }}</a>
      {% if user.is_admin %} · <a href="/seasons">{{ t('nav.seasons') }}</a>{% endif %}
    </span>
    {% endif %}
    <span>© {{ now().year if now is defined else '2026' }}</span>
  </div>
</footer>

{% block scripts %}{% endblock %}
{% if user %}
<script>
(function () {
  const evtSource = new EventSource("/notifications/stream");
  evtSource.onmessage = function (e) {
    try {
      const data = JSON.parse(e.data);
      const badge = document.querySelector(".notif-badge");
      const bell = document.querySelector(".notif-bell");
      if (data.unread_count > 0) {
        if (!badge) {
          const span = document.createElement("span");
          span.className = "notif-badge";
          bell.appendChild(span);
        }
        document.querySelector(".notif-badge").textContent = data.unread_count;
        showToast("You have a new notification");
      } else if (badge) {
        badge.remove();
      }
    } catch (_) {}
  };

  function showToast(msg) {
    const toast = document.createElement("div");
    toast.className = "notif-toast";
    toast.textContent = msg;
    toast.onclick = () => window.location.href = "/notifications";
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
  }
})();
</script>
<style>
.notif-toast {
  position: fixed; bottom: 1.5rem; right: 1.5rem; z-index: 9999;
  background: #1e293b; color: #fff; padding: .75rem 1.25rem;
  border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,.25);
  cursor: pointer; font-size: .92rem; max-width: 320px;
  animation: slideIn .3s ease;
}
@keyframes slideIn { from { transform: translateY(2rem); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
</style>
{% endif %}
<script src="/static/js/flatpickr.min.js"></script>
<script>
  flatpickr("input[type=date]", {
    dateFormat: "Y-m-d",
    altInput: true,
    altFormat: "d/m/Y",
    allowInput: true
  });
</script>
</body>
</html>
```

- [ ] **Step 2: Update all routes to use render() instead of templates.TemplateResponse**

For every route that calls `templates.TemplateResponse(request, ...)`, replace with `render(request, ...)`. Import `render` instead of `templates`:

```python
# Change this import in each route file:
from app.templates import templates
# To:
from app.templates import render
```

And change calls from:
```python
return templates.TemplateResponse(request, "some/template.html", {"key": val})
```
To:
```python
return render(request, "some/template.html", {"key": val})
```

Do this for all files in `routes/` and `app/main.py` (the profile page and error handlers).

- [ ] **Step 3: Verify app starts and base template renders**

```bash
pytest tests/test_auth.py::test_login_page_renders -v
```
Expected: PASS.

- [ ] **Step 4: Run full suite**

```bash
pytest -x -q
```
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add templates/base.html routes/ app/main.py
git commit -m "feat: update base.html and all routes to use i18n t() and render() helper"
```

---

### Task 10: Update all remaining templates with t() calls

**Files:**
- Modify: All 23 remaining templates

> **Note:** Work through templates systematically. For each template: replace hardcoded UI strings with `t('section.key')` calls using keys from `locales/en.json`. Dynamic content (player names, event titles, dates) is **not** translated — only static labels, headings, button text, and column headers.

- [ ] **Step 1: Update `templates/dashboard/index.html`**

Replace hardcoded strings with `t()` calls. Example:
```html
<h2>{{ t('dashboard.title') }}</h2>
<div class="stat-label">{{ t('dashboard.upcoming_events') }}<br><small>({{ t('dashboard.next_30_days') }})</small></div>
<h3>{{ t('dashboard.next_5_events') }}</h3>
<th>{{ t('events.date') }}</th><th>{{ t('events.title_col') }}</th>
<a href="/attendance/{{ event.id }}" class="btn btn-sm btn-primary">{{ t('events.attendance') }}</a>
```

- [ ] **Step 2: Update `templates/events/list.html`**, `detail.html`, `form.html`, `notify.html`

- [ ] **Step 3: Update `templates/players/list.html`**, `detail.html`, `form.html`, `import.html`

- [ ] **Step 4: Update `templates/teams/list.html`**, `form.html`

- [ ] **Step 5: Update `templates/seasons/list.html`**, `form.html`

- [ ] **Step 6: Update `templates/attendance/mark.html`**

- [ ] **Step 7: Update `templates/reports/season.html`**, `player.html`

- [ ] **Step 8: Update `templates/notifications/inbox.html`**

- [ ] **Step 9: Update `templates/auth/login.html`**, `register.html`, `profile.html`

For `profile.html`, also add the full language selector section:
```html
<section style="margin-top:2rem;">
  <h3>{{ t('auth.language_preference') }}</h3>
  <form method="post" action="/set-locale">
    <input type="hidden" name="next" value="/profile">
    <select name="locale">
      <option value="en" {% if current_locale == 'en' %}selected{% endif %}>English</option>
      <option value="it" {% if current_locale == 'it' %}selected{% endif %}>Italiano</option>
      <option value="fr" {% if current_locale == 'fr' %}selected{% endif %}>Français</option>
      <option value="de" {% if current_locale == 'de' %}selected{% endif %}>Deutsch</option>
    </select>
    <button type="submit" class="btn btn-sm btn-outline" style="margin-left:.5rem;">{{ t('common.save') }}</button>
  </form>
</section>
```

- [ ] **Step 10: Update `templates/errors/403.html`**, `404.html`, `500.html`

- [ ] **Step 11: Run full test suite**

```bash
pytest -x -q
```
Expected: All pass.

- [ ] **Step 12: Commit**

```bash
git add templates/
git commit -m "feat: replace hardcoded strings in all templates with t() calls"
```

---

## Chunk 5: Non-English locale files

### Task 11: Create IT, FR, DE locale files

**Files:**
- Create: `locales/it.json`
- Create: `locales/fr.json`
- Create: `locales/de.json`

> Each file must contain every key present in `en.json`. Missing keys fall back to English at runtime but all keys should be translated.

- [ ] **Step 1: Create `locales/it.json`** (Italian translations)

```json
{
  "nav": {
    "dashboard": "Pannello",
    "events": "Eventi",
    "players": "Giocatori",
    "teams": "Squadre",
    "seasons": "Stagioni",
    "reports": "Report",
    "notifications": "Notifiche",
    "profile": "Profilo",
    "sign_out": "Esci",
    "login": "Accedi",
    "register_user": "Registra Utente",
    "language": "Lingua"
  },
  "auth": {
    "login_title": "Accedi",
    "username": "Nome utente",
    "password": "Password",
    "submit": "Accedi",
    "register_title": "Registra Utente",
    "logout": "Esci",
    "profile_title": "Il mio profilo",
    "role": "Ruolo",
    "email": "Email",
    "save_preferences": "Salva preferenze",
    "notification_preferences": "Preferenze notifiche",
    "language_preference": "Lingua",
    "register_submit": "Registra"
  },
  "dashboard": {
    "title": "Pannello",
    "upcoming_events": "Prossimi eventi",
    "next_30_days": "prossimi 30 giorni",
    "pending_responses": "Risposte in attesa",
    "upcoming_events_label": "eventi in programma",
    "next_5_events": "Prossimi 5 eventi",
    "no_upcoming": "Nessun evento in programma.",
    "create_one": "Creane uno",
    "quick_actions": "Azioni rapide",
    "season_reports": "Report stagione",
    "no_active_season": "Nessuna stagione attiva.",
    "manage_seasons": "Gestisci stagioni"
  },
  "events": {
    "title": "Eventi",
    "new": "+ Nuovo Evento",
    "upcoming": "In programma",
    "past": "Eventi passati",
    "date": "Data",
    "time": "Ora",
    "title_col": "Titolo",
    "type": "Tipo",
    "location": "Luogo",
    "actions": "Azioni",
    "no_upcoming": "Nessun evento in programma.",
    "no_past": "Nessun evento passato.",
    "attendance": "Presenze",
    "edit": "Modifica",
    "view": "Visualizza",
    "recurring": "Ricorrente",
    "all_seasons": "Tutte le stagioni",
    "all_teams": "Tutte le squadre",
    "season": "Stagione",
    "team": "Squadra",
    "detail_title": "Evento",
    "back_to_events": "Torna agli eventi",
    "notify_players": "Notifica giocatori",
    "delete": "Elimina evento",
    "confirm_delete": "Eliminare questo evento?",
    "new_title": "Nuovo Evento",
    "edit_title": "Modifica Evento",
    "save": "Salva Evento"
  },
  "attendance": {
    "title": "Registra Presenze",
    "status_attend": "Presente",
    "status_absent": "Assente",
    "status_unknown": "Sconosciuto",
    "save": "Salva",
    "player": "Giocatore",
    "status": "Stato",
    "notes": "Note",
    "back": "Torna all'evento"
  },
  "players": {
    "title": "Giocatori",
    "new": "+ Nuovo Giocatore",
    "import": "Importa",
    "name": "Nome",
    "email": "Email",
    "phone": "Telefono",
    "team": "Squadra",
    "active": "Attivo",
    "actions": "Azioni",
    "edit": "Modifica",
    "view": "Visualizza",
    "no_players": "Nessun giocatore trovato.",
    "detail_title": "Giocatore",
    "back": "Torna ai giocatori",
    "new_title": "Nuovo Giocatore",
    "edit_title": "Modifica Giocatore",
    "save": "Salva Giocatore",
    "import_title": "Importa Giocatori",
    "import_submit": "Importa"
  },
  "teams": {
    "title": "Squadre",
    "new": "+ Nuova Squadra",
    "name": "Nome",
    "season": "Stagione",
    "players": "Giocatori",
    "actions": "Azioni",
    "edit": "Modifica",
    "no_teams": "Nessuna squadra trovata.",
    "new_title": "Nuova Squadra",
    "edit_title": "Modifica Squadra",
    "save": "Salva Squadra",
    "back": "Torna alle squadre"
  },
  "seasons": {
    "title": "Stagioni",
    "new": "+ Nuova Stagione",
    "name": "Nome",
    "active": "Attiva",
    "actions": "Azioni",
    "edit": "Modifica",
    "no_seasons": "Nessuna stagione trovata.",
    "new_title": "Nuova Stagione",
    "edit_title": "Modifica Stagione",
    "save": "Salva Stagione",
    "back": "Torna alle stagioni"
  },
  "reports": {
    "season_title": "Report Stagione",
    "player_title": "Report Giocatore",
    "back": "Torna ai report",
    "player": "Giocatore",
    "attended": "Presenti",
    "absent": "Assenti",
    "unknown": "Sconosciuti",
    "total": "Totale",
    "attendance_rate": "Tasso di presenza"
  },
  "notifications": {
    "title": "Notifiche",
    "no_notifications": "Nessuna notifica.",
    "mark_read": "Segna tutto come letto",
    "inbox": "Posta in arrivo"
  },
  "common": {
    "save": "Salva",
    "cancel": "Annulla",
    "delete": "Elimina",
    "confirm": "Sei sicuro?",
    "yes": "Sì",
    "no": "No",
    "loading": "Caricamento\u2026",
    "back": "Indietro",
    "edit": "Modifica",
    "new_season": "+ Nuova Stagione",
    "new_team": "+ Nuova Squadra",
    "new_player": "+ Nuovo Giocatore",
    "new_event": "+ Nuovo Evento"
  },
  "errors": {
    "404_title": "Pagina Non Trovata",
    "404_body": "La pagina richiesta non è stata trovata.",
    "500_title": "Errore del Server",
    "500_body": "Si è verificato un errore. Riprova.",
    "403_title": "Accesso Negato",
    "403_body": "Non hai il permesso di visualizzare questa pagina.",
    "back_home": "Torna al pannello"
  },
  "notify": {
    "title": "Notifica Giocatori",
    "send": "Invia Notifica",
    "back": "Torna all'evento"
  },
  "email": {
    "reminder_subject": "Promemoria: %{event_name} il %{date}",
    "reminder_body": "Ciao %{name},\n\nEcco un promemoria per il prossimo evento:\n\n  Evento:  %{event_name}\n  Quando:  %{when}\n  Luogo:   %{location}\n\nRicordati di aggiornare la tua presenza.\n\nCordiali saluti,\n%{app_name}",
    "reminder_body_html": "<p>Ciao <strong>%{name}</strong>,</p><p>Ecco un promemoria per il prossimo evento:</p><table><tr><td><strong>Evento</strong></td><td>%{event_name}</td></tr><tr><td><strong>Quando</strong></td><td>%{when}</td></tr><tr><td><strong>Luogo</strong></td><td>%{location}</td></tr></table><p>Aggiorna la tua presenza.</p><p>Cordiali saluti,<br>%{app_name}</p>",
    "attendance_subject": "Conferma presenza: %{event_name} il %{date}",
    "attendance_body": "Ciao %{name},\n\nConferma la tua presenza per:\n\n  Evento: %{event_name}\n  Data:   %{date}\n\nAggiorna il tuo stato qui: %{url}\n\nCordiali saluti,\n%{app_name}",
    "attendance_body_html": "<p>Ciao <strong>%{name}</strong>,</p><p>Conferma la tua presenza per <strong>%{event_name}</strong> il %{date}.</p><p><a href=\"%{url}\">Clicca qui per aggiornare la tua presenza</a></p><p>Cordiali saluti,<br>%{app_name}</p>"
  }
}
```

- [ ] **Step 2: Create `locales/fr.json`** (French translations)

```json
{
  "nav": {
    "dashboard": "Tableau de bord",
    "events": "Événements",
    "players": "Joueurs",
    "teams": "Équipes",
    "seasons": "Saisons",
    "reports": "Rapports",
    "notifications": "Notifications",
    "profile": "Profil",
    "sign_out": "Déconnexion",
    "login": "Connexion",
    "register_user": "Enregistrer un utilisateur",
    "language": "Langue"
  },
  "auth": {
    "login_title": "Connexion",
    "username": "Nom d'utilisateur",
    "password": "Mot de passe",
    "submit": "Se connecter",
    "register_title": "Enregistrer un utilisateur",
    "logout": "Déconnexion",
    "profile_title": "Mon profil",
    "role": "Rôle",
    "email": "E-mail",
    "save_preferences": "Enregistrer les préférences",
    "notification_preferences": "Préférences de notification",
    "language_preference": "Langue",
    "register_submit": "Enregistrer"
  },
  "dashboard": {
    "title": "Tableau de bord",
    "upcoming_events": "Événements à venir",
    "next_30_days": "30 prochains jours",
    "pending_responses": "Réponses en attente",
    "upcoming_events_label": "événements à venir",
    "next_5_events": "5 prochains événements",
    "no_upcoming": "Aucun événement à venir.",
    "create_one": "Créer un",
    "quick_actions": "Actions rapides",
    "season_reports": "Rapports de saison",
    "no_active_season": "Aucune saison active.",
    "manage_seasons": "Gérer les saisons"
  },
  "events": {
    "title": "Événements",
    "new": "+ Nouvel événement",
    "upcoming": "À venir",
    "past": "Événements passés",
    "date": "Date",
    "time": "Heure",
    "title_col": "Titre",
    "type": "Type",
    "location": "Lieu",
    "actions": "Actions",
    "no_upcoming": "Aucun événement à venir.",
    "no_past": "Aucun événement passé.",
    "attendance": "Présences",
    "edit": "Modifier",
    "view": "Voir",
    "recurring": "Récurrent",
    "all_seasons": "Toutes les saisons",
    "all_teams": "Toutes les équipes",
    "season": "Saison",
    "team": "Équipe",
    "detail_title": "Événement",
    "back_to_events": "Retour aux événements",
    "notify_players": "Notifier les joueurs",
    "delete": "Supprimer l'événement",
    "confirm_delete": "Supprimer cet événement ?",
    "new_title": "Nouvel événement",
    "edit_title": "Modifier l'événement",
    "save": "Enregistrer"
  },
  "attendance": {
    "title": "Marquer les présences",
    "status_attend": "Présent",
    "status_absent": "Absent",
    "status_unknown": "Inconnu",
    "save": "Enregistrer",
    "player": "Joueur",
    "status": "Statut",
    "notes": "Notes",
    "back": "Retour à l'événement"
  },
  "players": {
    "title": "Joueurs",
    "new": "+ Nouveau joueur",
    "import": "Importer",
    "name": "Nom",
    "email": "E-mail",
    "phone": "Téléphone",
    "team": "Équipe",
    "active": "Actif",
    "actions": "Actions",
    "edit": "Modifier",
    "view": "Voir",
    "no_players": "Aucun joueur trouvé.",
    "detail_title": "Joueur",
    "back": "Retour aux joueurs",
    "new_title": "Nouveau joueur",
    "edit_title": "Modifier le joueur",
    "save": "Enregistrer",
    "import_title": "Importer des joueurs",
    "import_submit": "Importer"
  },
  "teams": {
    "title": "Équipes",
    "new": "+ Nouvelle équipe",
    "name": "Nom",
    "season": "Saison",
    "players": "Joueurs",
    "actions": "Actions",
    "edit": "Modifier",
    "no_teams": "Aucune équipe trouvée.",
    "new_title": "Nouvelle équipe",
    "edit_title": "Modifier l'équipe",
    "save": "Enregistrer",
    "back": "Retour aux équipes"
  },
  "seasons": {
    "title": "Saisons",
    "new": "+ Nouvelle saison",
    "name": "Nom",
    "active": "Active",
    "actions": "Actions",
    "edit": "Modifier",
    "no_seasons": "Aucune saison trouvée.",
    "new_title": "Nouvelle saison",
    "edit_title": "Modifier la saison",
    "save": "Enregistrer",
    "back": "Retour aux saisons"
  },
  "reports": {
    "season_title": "Rapport de saison",
    "player_title": "Rapport du joueur",
    "back": "Retour aux rapports",
    "player": "Joueur",
    "attended": "Présent",
    "absent": "Absent",
    "unknown": "Inconnu",
    "total": "Total",
    "attendance_rate": "Taux de présence"
  },
  "notifications": {
    "title": "Notifications",
    "no_notifications": "Aucune notification.",
    "mark_read": "Tout marquer comme lu",
    "inbox": "Boîte de réception"
  },
  "common": {
    "save": "Enregistrer",
    "cancel": "Annuler",
    "delete": "Supprimer",
    "confirm": "Êtes-vous sûr ?",
    "yes": "Oui",
    "no": "Non",
    "loading": "Chargement\u2026",
    "back": "Retour",
    "edit": "Modifier",
    "new_season": "+ Nouvelle saison",
    "new_team": "+ Nouvelle équipe",
    "new_player": "+ Nouveau joueur",
    "new_event": "+ Nouvel événement"
  },
  "errors": {
    "404_title": "Page introuvable",
    "404_body": "La page que vous avez demandée est introuvable.",
    "500_title": "Erreur serveur",
    "500_body": "Une erreur s'est produite. Veuillez réessayer.",
    "403_title": "Accès refusé",
    "403_body": "Vous n'avez pas l'autorisation d'afficher cette page.",
    "back_home": "Retour au tableau de bord"
  },
  "notify": {
    "title": "Notifier les joueurs",
    "send": "Envoyer la notification",
    "back": "Retour à l'événement"
  },
  "email": {
    "reminder_subject": "Rappel : %{event_name} le %{date}",
    "reminder_body": "Bonjour %{name},\n\nCeci est un rappel pour l'événement à venir :\n\n  Événement : %{event_name}\n  Quand :     %{when}\n  Lieu :      %{location}\n\nPensez à mettre à jour votre statut de présence.\n\nCordialement,\n%{app_name}",
    "reminder_body_html": "<p>Bonjour <strong>%{name}</strong>,</p><p>Ceci est un rappel pour l'événement à venir :</p><table><tr><td><strong>Événement</strong></td><td>%{event_name}</td></tr><tr><td><strong>Quand</strong></td><td>%{when}</td></tr><tr><td><strong>Lieu</strong></td><td>%{location}</td></tr></table><p>Mettez à jour votre statut de présence.</p><p>Cordialement,<br>%{app_name}</p>",
    "attendance_subject": "Confirmation de présence : %{event_name} le %{date}",
    "attendance_body": "Bonjour %{name},\n\nConfirmez votre présence pour :\n\n  Événement : %{event_name}\n  Date :      %{date}\n\nMettez à jour votre statut ici : %{url}\n\nCordialement,\n%{app_name}",
    "attendance_body_html": "<p>Bonjour <strong>%{name}</strong>,</p><p>Confirmez votre présence pour <strong>%{event_name}</strong> le %{date}.</p><p><a href=\"%{url}\">Cliquez ici pour mettre à jour votre statut</a></p><p>Cordialement,<br>%{app_name}</p>"
  }
}
```

- [ ] **Step 3: Create `locales/de.json`** (German translations)

```json
{
  "nav": {
    "dashboard": "Dashboard",
    "events": "Termine",
    "players": "Spieler",
    "teams": "Teams",
    "seasons": "Saisons",
    "reports": "Berichte",
    "notifications": "Benachrichtigungen",
    "profile": "Profil",
    "sign_out": "Abmelden",
    "login": "Anmelden",
    "register_user": "Benutzer registrieren",
    "language": "Sprache"
  },
  "auth": {
    "login_title": "Anmelden",
    "username": "Benutzername",
    "password": "Passwort",
    "submit": "Anmelden",
    "register_title": "Benutzer registrieren",
    "logout": "Abmelden",
    "profile_title": "Mein Profil",
    "role": "Rolle",
    "email": "E-Mail",
    "save_preferences": "Einstellungen speichern",
    "notification_preferences": "Benachrichtigungseinstellungen",
    "language_preference": "Sprache",
    "register_submit": "Registrieren"
  },
  "dashboard": {
    "title": "Dashboard",
    "upcoming_events": "Bevorstehende Termine",
    "next_30_days": "nächste 30 Tage",
    "pending_responses": "Ausstehende Antworten",
    "upcoming_events_label": "bevorstehende Termine",
    "next_5_events": "Nächste 5 Termine",
    "no_upcoming": "Keine bevorstehenden Termine.",
    "create_one": "Einen erstellen",
    "quick_actions": "Schnellaktionen",
    "season_reports": "Saisonberichte",
    "no_active_season": "Keine aktive Saison.",
    "manage_seasons": "Saisons verwalten"
  },
  "events": {
    "title": "Termine",
    "new": "+ Neuer Termin",
    "upcoming": "Bevorstehend",
    "past": "Vergangene Termine",
    "date": "Datum",
    "time": "Uhrzeit",
    "title_col": "Titel",
    "type": "Typ",
    "location": "Ort",
    "actions": "Aktionen",
    "no_upcoming": "Keine bevorstehenden Termine.",
    "no_past": "Keine vergangenen Termine.",
    "attendance": "Anwesenheit",
    "edit": "Bearbeiten",
    "view": "Ansehen",
    "recurring": "Wiederkehrend",
    "all_seasons": "Alle Saisons",
    "all_teams": "Alle Teams",
    "season": "Saison",
    "team": "Team",
    "detail_title": "Termin",
    "back_to_events": "Zurück zu Terminen",
    "notify_players": "Spieler benachrichtigen",
    "delete": "Termin löschen",
    "confirm_delete": "Diesen Termin löschen?",
    "new_title": "Neuer Termin",
    "edit_title": "Termin bearbeiten",
    "save": "Termin speichern"
  },
  "attendance": {
    "title": "Anwesenheit erfassen",
    "status_attend": "Anwesend",
    "status_absent": "Abwesend",
    "status_unknown": "Unbekannt",
    "save": "Speichern",
    "player": "Spieler",
    "status": "Status",
    "notes": "Notizen",
    "back": "Zurück zum Termin"
  },
  "players": {
    "title": "Spieler",
    "new": "+ Neuer Spieler",
    "import": "Importieren",
    "name": "Name",
    "email": "E-Mail",
    "phone": "Telefon",
    "team": "Team",
    "active": "Aktiv",
    "actions": "Aktionen",
    "edit": "Bearbeiten",
    "view": "Ansehen",
    "no_players": "Keine Spieler gefunden.",
    "detail_title": "Spieler",
    "back": "Zurück zu Spielern",
    "new_title": "Neuer Spieler",
    "edit_title": "Spieler bearbeiten",
    "save": "Spieler speichern",
    "import_title": "Spieler importieren",
    "import_submit": "Importieren"
  },
  "teams": {
    "title": "Teams",
    "new": "+ Neues Team",
    "name": "Name",
    "season": "Saison",
    "players": "Spieler",
    "actions": "Aktionen",
    "edit": "Bearbeiten",
    "no_teams": "Keine Teams gefunden.",
    "new_title": "Neues Team",
    "edit_title": "Team bearbeiten",
    "save": "Team speichern",
    "back": "Zurück zu Teams"
  },
  "seasons": {
    "title": "Saisons",
    "new": "+ Neue Saison",
    "name": "Name",
    "active": "Aktiv",
    "actions": "Aktionen",
    "edit": "Bearbeiten",
    "no_seasons": "Keine Saisons gefunden.",
    "new_title": "Neue Saison",
    "edit_title": "Saison bearbeiten",
    "save": "Saison speichern",
    "back": "Zurück zu Saisons"
  },
  "reports": {
    "season_title": "Saisonbericht",
    "player_title": "Spielerbericht",
    "back": "Zurück zu Berichten",
    "player": "Spieler",
    "attended": "Anwesend",
    "absent": "Abwesend",
    "unknown": "Unbekannt",
    "total": "Gesamt",
    "attendance_rate": "Anwesenheitsquote"
  },
  "notifications": {
    "title": "Benachrichtigungen",
    "no_notifications": "Keine Benachrichtigungen.",
    "mark_read": "Alle als gelesen markieren",
    "inbox": "Posteingang"
  },
  "common": {
    "save": "Speichern",
    "cancel": "Abbrechen",
    "delete": "Löschen",
    "confirm": "Sind Sie sicher?",
    "yes": "Ja",
    "no": "Nein",
    "loading": "Laden\u2026",
    "back": "Zurück",
    "edit": "Bearbeiten",
    "new_season": "+ Neue Saison",
    "new_team": "+ Neues Team",
    "new_player": "+ Neuer Spieler",
    "new_event": "+ Neuer Termin"
  },
  "errors": {
    "404_title": "Seite nicht gefunden",
    "404_body": "Die angeforderte Seite wurde nicht gefunden.",
    "500_title": "Serverfehler",
    "500_body": "Es ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut.",
    "403_title": "Zugriff verweigert",
    "403_body": "Sie haben keine Berechtigung, diese Seite anzuzeigen.",
    "back_home": "Zurück zum Dashboard"
  },
  "notify": {
    "title": "Spieler benachrichtigen",
    "send": "Benachrichtigung senden",
    "back": "Zurück zum Termin"
  },
  "email": {
    "reminder_subject": "Erinnerung: %{event_name} am %{date}",
    "reminder_body": "Hallo %{name},\n\nErinnerung an den bevorstehenden Termin:\n\n  Termin: %{event_name}\n  Wann:   %{when}\n  Ort:    %{location}\n\nBitte aktualisieren Sie Ihren Anwesenheitsstatus.\n\nMit freundlichen Grüßen,\n%{app_name}",
    "reminder_body_html": "<p>Hallo <strong>%{name}</strong>,</p><p>Erinnerung an den bevorstehenden Termin:</p><table><tr><td><strong>Termin</strong></td><td>%{event_name}</td></tr><tr><td><strong>Wann</strong></td><td>%{when}</td></tr><tr><td><strong>Ort</strong></td><td>%{location}</td></tr></table><p>Bitte aktualisieren Sie Ihren Anwesenheitsstatus.</p><p>Mit freundlichen Grüßen,<br>%{app_name}</p>",
    "attendance_subject": "Anwesenheit bestätigen: %{event_name} am %{date}",
    "attendance_body": "Hallo %{name},\n\nBitte bestätigen Sie Ihre Anwesenheit für:\n\n  Termin: %{event_name}\n  Datum:  %{date}\n\nStatus hier aktualisieren: %{url}\n\nMit freundlichen Grüßen,\n%{app_name}",
    "attendance_body_html": "<p>Hallo <strong>%{name}</strong>,</p><p>Bitte bestätigen Sie Ihre Anwesenheit für <strong>%{event_name}</strong> am %{date}.</p><p><a href=\"%{url}\">Hier klicken, um den Status zu aktualisieren</a></p><p>Mit freundlichen Grüßen,<br>%{app_name}</p>"
  }
}
```

- [ ] **Step 4: Run full test suite**

```bash
pytest -x -q
```
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add locales/
git commit -m "feat: add Italian, French, German locale files"
```

---

## Final verification

- [ ] **Step 1: Run complete test suite**

```bash
pytest -v
```
Expected: All tests pass.

- [ ] **Step 2: Start dev server and manually verify**

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 7000
```

Manual checks:
- Navigate to http://localhost:7000 — navbar renders in EN
- Switch language to IT via navbar dropdown — page reloads in Italian
- Log in — language persists across pages
- Visit `/profile` — full language selector visible
- Switch to DE from profile — stays in German after redirect

- [ ] **Step 3: Final commit**

```bash
git add .
git commit -m "feat: complete multilanguage support (EN/IT/FR/DE)"
```
