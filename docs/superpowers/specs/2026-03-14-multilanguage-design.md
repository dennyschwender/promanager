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
Runs after `AuthMiddleware`. Reads `request.state.user.locale` (if set) or the `locale` cookie, validates against `SUPPORTED_LOCALES = ["en", "it", "fr", "de"]`, and sets `request.state.locale`. Falls back to `"en"` for unknown values.

### Translation Loader (`app/i18n.py`)
- At startup, loads all four `locales/{lang}.json` files into memory as a nested dict.
- Exposes `t(key, locale, **kwargs)` for string lookup with variable interpolation.
- **Dev mode** (`DEBUG=True`): missing key raises `KeyError`.
- **Production**: missing key logs a warning and returns the `en` value (or the bare key if `en` is also missing).

### Jinja2 Integration
`t()` and `current_locale` are injected into the global Jinja2 template context in `app/templates.py`. No per-route boilerplate required. Usage in templates:
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
    "login": "Login"
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
    "reminder_body": "Hi %{name},\n\nThis is a reminder that %{event_name} is scheduled for %{date} at %{location}.\n\nProManager"
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
```
POST /set-locale
Body: locale=it&next=/events
```
- Validates locale is in `SUPPORTED_LOCALES`; returns 400 if not
- Sets `locale` cookie (`path=/`, `max_age=31536000`)
- If user is authenticated, updates `user.locale` in DB
- Redirects to `next` param (default: `/dashboard`); `next` is validated to be a relative path to prevent open redirect attacks

---

## 4. Email Notifications

Outgoing emails use the recipient's locale. The email service resolves `user.locale` (falling back to `"en"`) and passes it to `t()` when building subject lines and body text.

Email strings live in `locales/{lang}.json` under the `email` namespace — no separate per-language HTML templates. This keeps all translations in one place.

---

## 5. Testing

### Unit Tests (`tests/test_i18n.py`)
- `t()` returns correct string for each supported locale
- Missing key raises `KeyError` in dev mode
- Missing key falls back to `en` in production mode with a logged warning
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

## 6. Dependencies

Add to `requirements.txt`:
```
python-i18n[yaml]>=0.3.9
```
(JSON support is built-in; the `[yaml]` extra is optional but included for flexibility.)

---

## 7. Files to Create / Modify

| Action | Path |
|--------|------|
| Create | `app/i18n.py` |
| Create | `app/middleware/locale.py` |
| Create | `locales/en.json` |
| Create | `locales/it.json` |
| Create | `locales/fr.json` |
| Create | `locales/de.json` |
| Modify | `app/main.py` — register `LocaleMiddleware` |
| Modify | `app/templates.py` — inject `t()` and `current_locale` globals |
| Modify | `app/config.py` — add `DEBUG` flag |
| Modify | `models/user.py` — add `locale` column |
| Modify | `templates/base.html` — replace hardcoded strings, add navbar switcher |
| Modify | All other templates — replace hardcoded strings with `t()` calls |
| Modify | `services/email_service.py` — pass locale to `t()` |
| Modify | `routes/auth.py` — add `/set-locale` endpoint |
| Create | `alembic/versions/xxxx_add_user_locale.py` |
| Modify | `requirements.txt` — add `python-i18n` |
| Create | `tests/test_i18n.py` |
