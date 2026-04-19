# iCal Calendar Feed — Design Spec

**Date:** 2026-04-19
**Status:** Approved

## Problem

Coaches and players want to see ProManager events in their personal calendar app (Google Calendar, Apple Calendar, etc.) without manual data entry. A subscribed iCal feed is the simplest solution: no OAuth, no third-party API credentials, works with any standards-compliant calendar app.

## Scope

- One-way sync: ProManager → calendar app (read-only feed)
- Per-user feed URL covering all events the user is involved in
- Available to all roles: admin, coach, member
- No new runtime dependencies

## Data Model

### New column on `users` table

```python
calendar_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
```

- Generated on demand via `secrets.token_hex(32)` (first visit to profile/settings)
- Unique index allows fast lookup by token
- Nullable — users who never use the feature have no token
- User can regenerate (old URL immediately stops working)

### New Alembic migration

Add `calendar_token VARCHAR(64) UNIQUE NULLABLE` to `users` table.

### New config setting

```python
APP_TIMEZONE: str = "UTC"  # e.g. "Europe/Rome", "America/New_York"
```

Used for `TZID` param on iCal `DTSTART`/`DTEND`. All events use this single timezone.

## Architecture

### New files

| File | Purpose |
|---|---|
| `services/calendar_service.py` | Token generation, iCal feed construction |
| `routes/calendar.py` | Feed endpoint, token regeneration endpoint |

### Modified files

| File | Change |
|---|---|
| `models/user.py` | Add `calendar_token` column |
| `app/config.py` | Add `APP_TIMEZONE` setting |
| `app/main.py` | Register `calendar` router |
| `routes/users.py` (or profile route) | Show feed URL + regenerate button in user settings |
| `alembic/versions/` | New migration for `calendar_token` column |
| `locales/*.yaml` | i18n keys for calendar section in settings UI |

## Feed Endpoint

```
GET /calendar/{token}/feed.ics
```

**Auth:** Token lookup only — no session required. Returns 404 for unknown token.

**Response:**
- `Content-Type: text/calendar; charset=utf-8`
- `Content-Disposition: attachment; filename="promanager.ics"`
- Body: RFC 5545 iCal string

**Event filtering by role:**
- **admin**: all events in the system
- **coach**: events for teams in `UserTeam` (their assigned teams)
- **member**: events for teams via `PlayerTeam` (active memberships, all statuses of events)

Only future events + events from the past 30 days are included (keeps feed manageable).

## iCal Feed Format

```
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//ProManager//ProManager//EN
X-WR-CALNAME:ProManager
X-WR-CALDESC:ProManager team events
BEGIN:VEVENT
UID:{event_id}@promanager
SUMMARY:{event_title}
DTSTART;TZID={APP_TIMEZONE}:20260422T183000
DTEND;TZID={APP_TIMEZONE}:20260422T200000
LOCATION:{location}
DTSTAMP:{created_at in UTC, format: 20260101T120000Z}
END:VEVENT
END:VCALENDAR
```

**`DTEND` when `event_end_time` is null:** Use `DTSTART + 1 hour` as fallback.

**All-day events** (no `event_time`):
```
DTSTART;VALUE=DATE:20260422
DTEND;VALUE=DATE:20260423
```

**Meeting point** (when `meeting_time` is set): second `VEVENT` with:
- `UID`: `{event_id}-meet@promanager`
- `SUMMARY`: `Meet: {event_title}`
- `DTSTART`: `meeting_time`
- `DTEND`: `event_time` (meeting ends when event starts)
- `LOCATION`: `meeting_location` (if set), else `location`

**iCal line folding:** Lines >75 chars must be folded per RFC 5545 (continuation line starts with a space). The service handles this.

## Token Regeneration

```
POST /calendar/regenerate-token
```

Requires session login. Generates new `calendar_token`, saves to DB, redirects back to profile/settings with new URL displayed. Old URL immediately returns 404.

## Settings UI

In user profile/settings page, new "Calendar" section:

- Feed URL displayed in a readonly input (copyable)
- "Copy link" button (JS clipboard)
- "Regenerate link" button (POST form, with confirmation warning that old URL stops working)
- Brief instructions: "Subscribe to this URL in Google Calendar, Apple Calendar, or any calendar app"

If user has no `calendar_token` yet, a "Generate calendar link" button creates one on first use.

## Verification

1. Generate calendar link in user settings → URL appears
2. `curl -s "http://localhost:7000/calendar/{token}/feed.ics"` → valid iCal output
3. Subscribe URL in Google Calendar → events appear with correct title, time, location
4. If `meeting_time` set on an event → two entries appear in Google Calendar
5. Event with no time → appears as all-day event in Google Calendar
6. Regenerate token → old URL returns 404, new URL works
7. Unknown token → 404
8. `pytest tests/test_calendar.py` — unit tests for feed generation and endpoint
