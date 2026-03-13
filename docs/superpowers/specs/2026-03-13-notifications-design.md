# Notifications System — Design Spec

**Date:** 2026-03-13
**Status:** Approved
**Scope:** Email + In-App (inbox + real-time toasts) + Web Push notifications for ProManager
**Depends on:** i18n sub-project (template strings will be extracted when i18n is implemented)

---

## 1. Overview

Admins can manually trigger notifications from an event detail page. Notifications are delivered via up to three channels — Email, In-App, and Web Push — respecting each player's per-channel preferences. A persistent in-app inbox and real-time toast alerts give players visibility without requiring a third-party service. Web Push enables app-like browser alerts even when the site is not open.

SMS and WhatsApp are deferred pending provider evaluation.

---

## 2. Data Model

### `Notification`
One row per player per message.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `player_id` | FK → Player | recipient |
| `event_id` | FK → Event, nullable | linked event (if any) |
| `title` | string | short subject |
| `body` | text | full message |
| `tag` | enum: `direct`, `announcement` | direct = targeted; announcement = team broadcast |
| `is_read` | bool, default False | |
| `created_at` | datetime | |

### `NotificationPreference`
Per-player, per-channel opt-in. Defaults to all enabled.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `player_id` | FK → Player | |
| `channel` | enum: `email`, `inapp`, `webpush` | |
| `enabled` | bool, default True | |

Unique constraint: `(player_id, channel)`.

### `WebPushSubscription`
Stores browser push subscriptions. A player can have multiple (different devices/browsers).

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `player_id` | FK → Player | |
| `endpoint` | string | browser-provided push endpoint |
| `p256dh_key` | string | encryption key |
| `auth_key` | string | auth secret |
| `created_at` | datetime | |

Expired/invalid subscriptions are silently removed on next send attempt.

---

## 3. Service Architecture

### `services/notification_service.py`
Single entry point. On `send(event, title, body, tag, recipient_filter, channels)`:

1. Resolves target players from the event's team, filtered by attendance status if specified
2. Creates `Notification` DB rows for each player (in-app record)
3. Dispatches to channel implementations in parallel, respecting each player's `NotificationPreference`
4. Returns a summary `{sent: N, skipped: N, failures: [...]}`

Failures in one channel do not block others.

### `services/channels/`

**`EmailChannel`**
Wraps existing `email_service.send_email()`. Adapts notification `title` → subject, `body` → HTML/text body.

**`InAppChannel`**
Notification row is already written by `NotificationService`. This channel signals the SSE stream for any connected players by pushing `{"unread_count": N}`.

**`WebPushChannel`**
Uses `pywebpush` library with VAPID keys from `.env`. Iterates each player's `WebPushSubscription` rows and sends to each device. Removes expired subscriptions on `410 Gone` response.

Each channel implements a single `send(player, notification) -> bool` method.

### VAPID Keys
Generated once via `scripts/generate_vapid.py`, stored as `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` in `.env`. Public key exposed at `GET /notifications/vapid-public-key` for browser subscription flow.

---

## 4. Notification Templates

Fixed system templates pre-fill the send form with the event's details substituted in. Admins can edit before sending. Template strings will be extracted into translation files when the i18n sub-project is implemented (EN, IT, DE, FR minimum).

| # | Name | Tag | Title | Body |
|---|---|---|---|---|
| 1 | Event Reminder | direct | Reminder: {event} on {date} | Don't forget: {event} is on {date} at {time} at {location}. Please confirm your attendance. |
| 2 | Cancellation | announcement | {event} cancelled | {event} scheduled for {date} has been cancelled. |
| 3 | Venue Change | announcement | Venue change: {event} | {event} on {date} has moved to {new_location}. |
| 4 | Time Change | announcement | Time change: {event} | {event} on {date} has been rescheduled to {new_time}. |
| 5 | Attendance Request | direct | Please confirm: {event} | Please confirm your attendance for {event} on {date}. |
| 6 | General Announcement | announcement | (free text) | (free text) |
| 7 | Training Cancelled | announcement | Training cancelled: {date} | Training on {date} is cancelled. |
| 8 | Match Result | announcement | Result: {event} | (free text score/summary) |

Placeholders: `{event}`, `{date}`, `{time}`, `{location}`, `{new_location}`, `{new_time}` — substituted from the event record at send time.

---

## 5. Admin Send UI

**Entry point:** "Notify" button on event detail page → `GET /events/{id}/notify`

**Send form fields:**
- **Template** — dropdown of fixed templates; selecting one pre-fills title + body (editable)
- **Title** — text input
- **Body** — textarea (free text)
- **Tag** — radio: `Direct` / `Team Announcement`
- **Recipients** — checkboxes: `All`, `Present`, `Absent`, `Maybe`, `Unknown` (multi-select, default: All)
- **Channels** — checkboxes: `Email`, `In-app`, `Web Push` (all checked by default)
- **Preview** — resolves and shows recipient count before sending

**`POST /events/{id}/notify`** — calls `NotificationService.send(...)`, redirects back to event detail with a flash message showing notification count.

Admin-only routes (`require_admin` dependency).

---

## 6. Player Profile & Preferences

New **Notification Preferences** section on `/profile`:

- Three toggles: **Email**, **In-app**, **Web Push** (all on by default)
- **"Enable browser notifications"** button — triggers browser permission prompt, saves `WebPushSubscription`
- Subscription status: "Active on N device(s)" + "Remove all devices" option

Admins can also view/edit preferences on the player detail page.

---

## 7. In-App Inbox & Real-Time UI

### Notification Bell (`base.html`)
- Shown to all logged-in users
- Displays unread count badge
- Links to `/notifications` inbox

### Inbox (`/notifications`)
- Notifications newest-first
- Each row: tag badge, title, body preview, timestamp, read/unread indicator
- Clicking a notification marks it read and links to the related event (if applicable)
- "Mark all as read" button
- `POST /notifications/{id}/read` and `POST /notifications/read-all`

### Real-Time Flow (SSE)
1. Browser connects to `GET /notifications/stream` on page load (authenticated only)
2. `InAppChannel` pushes `{"unread_count": N}` when a notification is created
3. Browser updates bell badge and shows a **toast** (bottom-right, auto-dismisses after 5s)
4. Toast click opens the inbox
5. No message content over SSE — client fetches full notification from inbox

### Web Push (Service Worker)
- `static/js/sw.js` — registered on profile page when player enables push
- Handles push events: shows browser notification with title + body
- Click on browser notification opens the app

---

## 8. New Files Summary

| Action | File | Purpose |
|---|---|---|
| Create | `models/notification.py` | Notification ORM model |
| Create | `models/notification_preference.py` | Per-player channel preferences |
| Create | `models/web_push_subscription.py` | Browser push subscriptions |
| Modify | `models/__init__.py` | Export new models |
| Create | `alembic/versions/xxx_add_notifications.py` | DB migration |
| Create | `services/notification_service.py` | Dispatch orchestration |
| Create | `services/channels/__init__.py` | Channel package |
| Create | `services/channels/email_channel.py` | Email channel |
| Create | `services/channels/inapp_channel.py` | In-app + SSE channel |
| Create | `services/channels/webpush_channel.py` | Web Push channel |
| Create | `routes/notifications.py` | Inbox, SSE stream, mark-read, preferences |
| Modify | `routes/events.py` | Add "Notify" button + send form routes |
| Modify | `app/main.py` | Register notifications router |
| Create | `templates/notifications/inbox.html` | Notification inbox page |
| Create | `templates/events/notify.html` | Admin send form |
| Modify | `templates/base.html` | Notification bell in nav |
| Modify | `templates/players/profile.html` | Notification preferences section |
| Create | `static/js/sw.js` | Service worker for Web Push |
| Create | `scripts/generate_vapid.py` | One-time VAPID key generation |

---

## 9. Dependencies

- `pywebpush>=2.0.0` — Web Push sending
- No new dependencies for Email, In-App, or SSE (all stdlib or already present)

---

## 10. Out of Scope

- SMS / WhatsApp (deferred — provider TBD)
- i18n of template strings (deferred to i18n sub-project; EN, IT, DE, FR planned)
- Notification delivery receipts / read tracking per channel
- Admin notification history/audit log
