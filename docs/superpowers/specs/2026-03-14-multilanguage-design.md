# Multilanguage Support (EN, IT, FR, DE) — Design Spec

**Date:** 2026-03-14
**Status:** Approved

---

## Overview

Add full multilanguage support to ProManager covering all UI templates, navigation, forms, error pages, and outgoing emails. Supported locales: English (`en`), Italian (`it`), French (`fr`), German (`de`). English is the default and fallback.

---

## 1. Architecture & Data Flow

### Locale Resolution Order (per request)
1. Logged-in user → `users.locale` DB column
2. Guest or no DB preference → `locale` cookie
3. Neither → `"en"` (hardcoded default)

### LocaleMiddleware (`app/middleware/locale.py`)
Must run **after** `AuthMiddleware` so that `request.state.user` is already set. In FastAPI/Starlette, `app.add_middleware()` wraps in LIFO order — the **last** middleware added is the **outermost** (runs first). Therefore `LocaleMiddleware` must be added **before** `AuthMiddleware` in `app/main.py` so it executes after it:

```python
app.add_middleware(LocaleMiddleware)   # added first → runs second (inner)
app.add_middleware(AuthMiddleware)     # added second → runs first (outer)
```

`LocaleMiddleware` reads `request.state.user.locale` (if set) or the `locale` cookie, validates against `SUPPORTED_LOCALES = ["en", "it", "fr", "de"]`, and sets `request.state.locale`. Falls back to `"en"` for unknown values.

### Translation Loader (`app/i18n.py`)
- At startup, loads all four `locales/{lang}.json` files into memory as a nested dict.
- Exposes a `t(key: str, locale: str, **kwargs) -> str` function:
  - Looks up dot-separated `key` (e.g. `"nav.dashboard"`) in the loaded translations for `locale`.
  - Substitutes `%{var}` placeholders with `kwargs`.
  - **Dev mode** (`settings.DEBUG=True`): missing key raises `KeyError`.
  - **Production** (`settings.DEBUG=False`): missing key logs a `WARNING` and returns the `en` value (or the bare key if `en` is also missing).
- `python-i18n` is used as the underlying engine; `t()` is a thin wrapper that pre-binds the locale and delegates to `i18n.t()`.

### Jinja2 Integration
Jinja2 globals are set at startup and cannot hold per-request state. Instead, a **locale-bound partial** is injected into the template context at render time. The `AuthMiddleware` (or a shared context helper) injects into every `TemplateResponse`:

```python
"t": lambda key, **kw: i18n_t(key, request.state.locale, **kw),
"current_locale": request.state.locale,
```

To avoid duplicating this in every route, `app/templates.py` exposes a helper `render(request, template_name, context)` that merges the i18n context automatically. All routes use this helper instead of calling `templates.TemplateResponse` directly.

Usage in templates:
```jinja2
{{ t('nav.dashboard') }}
{{ t('auth.welcome', name=user.username) }}
```

---

## 2. Locale Files & Key Structure

### File Layout
```
locales/
  en.json
  it.json
  fr.json
  de.json
```

### JSON Structure (nested by feature area)
The keys below are the required minimum. All four locale files must contain every key; `en.json` is the authoritative reference.

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
    "register_user": "Register User"
  },
  "auth": {
    "login_title": "Sign In",
    "username": "Username",
    "password": "Password",
    "submit": "Sign In",
    "register_title": "Register User"
  },
  "events": {
    "title": "Events",
    "new": "New Event",
    "date": "Date",
    "location": "Location",
    "attend": "I'll attend",
    "absent": "I'll be absent"
  },
  "common": {
    "save": "Save",
    "cancel": "Cancel",
    "delete": "Delete",
    "confirm": "Are you sure?",
    "yes": "Yes",
    "no": "No",
    "loading": "Loading…"
  },
  "errors": {
    "404_title": "Page Not Found",
    "500_title": "Server Error",
    "403_title": "Access Denied"
  },
  "email": {
    "reminder_subject": "Reminder: %{event_name} on %{date}",
    "reminder_body": "Hi %{name},\n\nThis is a reminder that %{event_name} is scheduled for %{date} at %{location}.\n\nProManager",
    "attendance_subject": "Attendance request: %{event_name}",
    "attendance_body": "Hi %{name},\n\nPlease confirm your attendance for %{event_name} on %{date}.\n\nProManager"
  }
}
```

### Variable Interpolation
Uses `python-i18n`'s `%{var}` syntax:
```json
{ "welcome": "Welcome, %{name}!" }
```
Called as `{{ t('welcome', name=user.username) }}`.

### Pluralisation
Uses `python-i18n`'s built-in `one`/`other` keys:
```json
{ "player_count": { "one": "1 player", "other": "%{count} players" } }
```

---

## 3. Database & User Preference

### Schema Change
Add `locale` column to `users` table:
```python
locale: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
```
Alembic migration: `add_user_locale`.

### Language Switcher — Two Surfaces

**Navbar (compact):** A `<select>` with short codes (`EN / IT / FR / DE`) always visible in the navbar, next to the username dropdown. Available to guests (cookie only) and logged-in users.

**Profile page (full):** A labelled language selector with full language names ("English", "Italiano", "Français", "Deutsch").

Both submit a `POST /set-locale` request.

### `/set-locale` Endpoint
Lives in a new `routes/locale.py` module (not `routes/auth.py`).

```
POST /set-locale
Body: locale=it&next=/events
```
- Validates locale is in `SUPPORTED_LOCALES`; returns 400 if not
- Sets `locale` cookie (`path=/`, `max_age=31536000`, `httponly=False`)
- If user is authenticated, updates `user.locale` in DB
- Redirects to `next` param (default: `/dashboard`); `next` is validated to be a relative path (must start with `/` and not contain `://`) to prevent open redirect attacks

---

## 4. Email Notifications

All outgoing email functions in `services/email_service.py` accept a `locale: str = "en"` parameter. This applies to both:
- `send_event_reminder(...)` — uses `email.reminder_subject` / `email.reminder_body`
- `send_attendance_request(...)` — uses `email.attendance_subject` / `email.attendance_body`

The email service resolves the recipient's locale from `user.locale` (falling back to `"en"`) and passes it to the `locale` parameter.

Email strings live in `locales/{lang}.json` under the `email` namespace — no separate per-language HTML templates. This keeps all translations in one place.

---

## 5. Config

Add to `app/config.py`:
```python
DEBUG: bool = False  # Set DEBUG=true in .env for development mode
```
When `DEBUG=True`, missing translation keys raise `KeyError`. When `False`, they log a warning and fall back to `en`.

---

## 6. Testing

### Unit Tests (`tests/test_i18n.py`)
- `t()` returns correct string for each supported locale
- Missing key raises `KeyError` in dev mode (`DEBUG=True`)
- Missing key falls back to `en` in production mode (`DEBUG=False`) with a logged warning
- Variable interpolation works correctly
- Unsupported locale falls back to `"en"`

### Integration Tests
- `POST /set-locale` sets cookie and redirects correctly
- `POST /set-locale` with authenticated user updates `user.locale` in DB
- `POST /set-locale` with invalid locale returns 400
- `POST /set-locale` with external `next` URL is rejected
- Templates render translated strings when locale cookie is set (spot-check per feature area)

### Existing Tests
Tests that assert on specific UI strings need updating to assert against `en` locale output. Tests that don't assert on translated strings are unaffected.

---

## 7. Dependencies

Add to `requirements.txt`:
```
python-i18n[yaml]>=0.3.9
```
(JSON support is built-in; the `[yaml]` extra is optional but included for flexibility.)

---

## 8. Files to Create / Modify

| Action | Path | Notes |
|--------|------|-------|
| Create | `app/i18n.py` | Translation loader + `t()` wrapper |
| Create | `app/middleware/locale.py` | `LocaleMiddleware` |
| Create | `locales/en.json` | Authoritative key reference |
| Create | `locales/it.json` | |
| Create | `locales/fr.json` | |
| Create | `locales/de.json` | |
| Modify | `app/main.py` | Register `LocaleMiddleware` before `AuthMiddleware` |
| Modify | `app/templates.py` | Add `render()` helper that injects `t()` partial + `current_locale` |
| Modify | `app/config.py` | Add `DEBUG: bool = False` |
| Modify | `models/user.py` | Add `locale` column |
| Modify | `templates/base.html` | Replace hardcoded strings, add navbar switcher |
| Modify | All other templates | Replace hardcoded strings with `t()` calls |
| Modify | `services/email_service.py` | Add `locale` param to both email functions |
| Create | `routes/locale.py` | `/set-locale` endpoint |
| Modify | `app/main.py` | Register `routes/locale.py` router |
| Create | `alembic/versions/xxxx_add_user_locale.py` | Migration |
| Modify | `requirements.txt` | Add `python-i18n` |
| Create | `tests/test_i18n.py` | |
