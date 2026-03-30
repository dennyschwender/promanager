# Telegram Bot Design

**Date:** 2026-03-30
**Status:** Approved

## Overview

A Telegram bot integrated into the existing ProManager FastAPI app. Users can authenticate via their phone number (matched against `Player.phone` / `PlayerPhone`), view upcoming events, see event details, and update attendance status — with the same role-based access as the web app.

---

## Authentication

### Flow

1. User sends `/start` or any message while unauthenticated
2. Bot replies asking for phone via Telegram's native `request_contact` keyboard button (verified phone, not typed)
3. Bot normalizes the received phone number and searches `player_phones` (and `player.phone` fallback) for a match
4. If match found, resolve `player.user_id` to a `User`
5. **Double-auth check 1:** If this `telegram_chat_id` is already linked to a different user → "This Telegram account is already authenticated as [username]"
6. **Double-auth check 2:** If the matched user already has a different `telegram_chat_id` → "This ProManager account is already linked to another Telegram user — contact your admin"
7. If clean → save `telegram_chat_id` on the `User` row, confirm success
8. `/logout` clears `telegram_chat_id` (sets to NULL)

### Session Persistence

Once `telegram_chat_id` is stored on `User`, all subsequent messages from that chat ID are auto-identified — no re-auth per session.

### Database Change

Add `telegram_chat_id: Mapped[str | None]` (`String(64), unique=True, nullable=True`) to `models/user.py` + Alembic migration.

---

## Bot Interaction Model

All navigation is via **inline keyboard buttons** — no typed commands beyond `/start` and `/logout`.

### `/events`

- Returns a paginated list of upcoming events (~5 per page)
- Each event row has a **[View]** inline button
- Pagination via **[← Prev]** / **[Next →]** inline buttons

### Event Detail (on [View])

Shown for all roles:
- Title, type, date, time (and end time if set), location, meeting time/location, description
- Attendance summary counts (present / absent / unknown)
- User's own current attendance status

**Member:** inline buttons **[✓ Present] [✗ Absent] [? Unknown]** to update own status only

**Coach / Admin:** full player list with per-player status inline buttons **[✓] [✗] [?]** to update any player's attendance

Tapping a status button edits the same message in-place (no chat clutter). A **[← Back to Events]** button returns to the list.

---

## Role-Based Access

| Feature | Member | Coach | Admin |
|---|---|---|---|
| List events | ✓ | ✓ | ✓ |
| View event detail | ✓ | ✓ | ✓ |
| Update own attendance | ✓ | ✓ | ✓ |
| View full player attendance list | — | ✓ | ✓ |
| Update any player's attendance | — | ✓ | ✓ |

Coaches follow the same team-scoping rules as the web app (`check_team_access`).

---

## Localisation

All bot messages are rendered in the user's `locale` preference (en/it/fr/de), reusing the existing `locales/*.yaml` translation files. Falls back to `en` if the user's locale has no bot-specific key.

New translation keys will be added under a `telegram.*` namespace in each locale file.

---

## Architecture

### New Config Variables (`app/config.py` + `.env.example`)

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `TELEGRAM_WEBHOOK_URL` | Public base URL (e.g. `https://myserver.com`) |
| `TELEGRAM_WEBHOOK_SECRET` | Random secret to validate incoming webhook requests |

### New Files

| File | Purpose |
|---|---|
| `bot/__init__.py` | Package init, exposes `application` instance |
| `bot/handlers.py` | All command and callback query handlers |
| `bot/keyboards.py` | Inline keyboard builders |
| `bot/i18n.py` | Thin wrapper reusing `app/i18n.py` translation loader |
| `routes/telegram.py` | `POST /telegram/webhook` FastAPI route |
| `services/telegram_service.py` | Phone normalisation, user lookup, auth logic |
| `alembic/versions/<hash>_add_telegram_chat_id.py` | Migration |

### Modified Files

| File | Change |
|---|---|
| `models/user.py` | Add `telegram_chat_id` column |
| `app/main.py` | Register webhook on startup, deregister on shutdown; add `telegram` router |
| `app/config.py` | Add three new env vars |
| `.env.example` | Document new vars |
| `locales/*.yaml` | Add `telegram.*` keys |
| `requirements.txt` | Add `python-telegram-bot>=20` |

### Startup / Shutdown (`app/main.py`)

- `lifespan` startup: call Telegram API to register webhook URL with secret header
- `lifespan` shutdown: deregister webhook

### Webhook Route (`routes/telegram.py`)

- `POST /telegram/webhook`
- Validates `X-Telegram-Bot-Api-Secret-Token` header against `TELEGRAM_WEBHOOK_SECRET`
- Passes update to `python-telegram-bot` `Application.process_update()`

### Dependency

`python-telegram-bot>=20.0` (async-native, no threading)

---

## Testing

- Unit tests for `telegram_service.py`: phone normalization, user lookup, double-auth checks
- Integration tests for the webhook route: valid/invalid secret, update dispatch
- Handler tests using `python-telegram-bot`'s test utilities or mocked `Update` objects
