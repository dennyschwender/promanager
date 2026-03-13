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
One row per player per message. Stored as `String` columns for enum-like values, consistent with project conventions (`Attendance.status`, `Event.event_type`).

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `player_id` | FK → Player, `ondelete="CASCADE"` | deleting a player removes their notifications |
| `event_id` | FK → Event, nullable, `ondelete="SET NULL"` | event deleted → field becomes NULL, notification kept |
| `title` | String | short subject |
| `body` | Text | full message |
| `tag` | String, values: `direct` / `announcement` | direct = targeted; announcement = team broadcast |
| `is_read` | Boolean, default False | |
| `created_at` | DateTime, default utcnow | |

**Relationships:**
- `Notification.player` → `Player` (`back_populates="notifications"`)
- `Notification.event` → `Event` (`back_populates="notifications"`)
- Add `Player.notifications` and `Event.notifications` back-references in their respective models.

### `NotificationPreference`
Per-player, per-channel opt-in. Rows are created for all three channels when a player is first created (via `after_player_create` helper in `services/notification_service.py`), defaulting all to enabled. If rows are missing (e.g. existing players before migration), the service uses a get-or-create pattern defaulting to enabled.

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `player_id` | FK → Player, `ondelete="CASCADE"` | |
| `channel` | String, values: `email` / `inapp` / `webpush` | |
| `enabled` | Boolean, default True | |

Unique constraint: `(player_id, channel)`.

### `WebPushSubscription`
Stores browser push subscriptions. A player can have multiple (different devices/browsers).

| Column | Type | Notes |
|---|---|---|
| `id` | integer PK | |
| `player_id` | FK → Player, `ondelete="CASCADE"` | |
| `endpoint` | String | browser-provided push endpoint |
| `p256dh_key` | String | encryption key |
| `auth_key` | String | auth secret |
| `created_at` | DateTime, default utcnow | |

Expired/invalid subscriptions (`410 Gone` response) are silently removed on next send attempt.

---

## 3. Service Architecture

### `services/notification_service.py`
Single entry point. On `send(event, title, body, tag, recipient_filter, admin_channels, db)`:

1. **Resolves target players** from the event's team, filtered by attendance status if specified. If `event.team_id` is `None`, falls back to all active players in the system.
2. **Creates `Notification` DB rows** for each resolved player.
3. **Dispatches to channels** — the effective channel set per player is the **intersection** of `admin_channels` (the channels the admin checked on the send form) and the player's enabled `NotificationPreference` channels. A player who has disabled email will not receive email even if the admin checked it.
4. **Dispatches via `BackgroundTasks`** — the `POST /events/{id}/notify` handler passes a `BackgroundTasks` instance; actual sending (SMTP, Web Push HTTP) is offloaded so the HTTP response returns immediately.
5. Returns a summary `{queued: N}` synchronously (channel-level failures are logged in the background task, not surfaced to the admin on the flash message).

Failures in one channel do not block others.

### `services/channels/`

**`EmailChannel`**
Wraps existing `email_service.send_email()`. Adapts notification `title` → subject, `body` → HTML/text body.

**`InAppChannel`**
Notification row is already written by `NotificationService`. This channel signals any active SSE connection for the player by putting a message into their queue in the **SSE connection registry** (see Section 7).

**`WebPushChannel`**
Uses `pywebpush` library. Iterates each player's `WebPushSubscription` rows and calls `webpush(subscription_info, data, vapid_private_key, vapid_claims)` for each. The `vapid_claims` dict includes `{"sub": settings.VAPID_SUBJECT}`. Removes expired subscriptions on `410 Gone` response.

Each channel implements `send(player, notification, db) -> bool`.

### VAPID Keys
Generated once via `scripts/generate_vapid.py`. Three env vars required:

| Variable | Description |
|---|---|
| `VAPID_PUBLIC_KEY` | Base64url-encoded public key, served to browsers |
| `VAPID_PRIVATE_KEY` | Base64url-encoded private key, used to sign push requests |
| `VAPID_SUBJECT` | Contact URI, e.g. `mailto:admin@example.com` — required by the Web Push protocol |

Public key exposed at `GET /notifications/vapid-public-key` for the browser subscription flow.

**Dependency:** `pywebpush~=2.0` (pinned to major version; tested against 2.0.x).

---

## 4. Notification Templates

Fixed system templates pre-fill the send form with the event's details substituted in. Selecting a template auto-sets the `tag` field (locking the radio to the template's default); the admin can override. Admins can edit title and body freely before sending. Template strings will be extracted into translation files when the i18n sub-project is implemented (EN, IT, DE, FR minimum).

| # | Name | Tag (pre-set) | Title | Body |
|---|---|---|---|---|
| 1 | Event Reminder | direct | Reminder: {event} on {date} | Don't forget: {event} is on {date} at {time} at {location}. Please confirm your attendance. |
| 2 | Cancellation | announcement | {event} cancelled | {event} scheduled for {date} has been cancelled. |
| 3 | Venue Change | announcement | Venue change: {event} | {event} on {date} has moved to {new_location}. |
| 4 | Time Change | announcement | Time change: {event} | {event} on {date} has been rescheduled to {new_time}. |
| 5 | Attendance Request | direct | Please confirm: {event} | Please confirm your attendance for {event} on {date}. |
| 6 | General Announcement | announcement | (free text) | (free text) — tag radio remains editable |
| 7 | Training Cancelled | announcement | Training cancelled: {date} | Training on {date} is cancelled. |
| 8 | Match Result | announcement | Result: {event} | (free text score/summary) |

Placeholders: `{event}`, `{date}`, `{time}`, `{location}`, `{new_location}`, `{new_time}` — substituted from the event record at send time.

---

## 5. Admin Send UI

**Entry point:** "Notify" button on event detail page → `GET /events/{id}/notify`

**Send form fields:**
- **Template** — dropdown of fixed templates; selecting one pre-fills title + body (editable) and auto-sets tag
- **Title** — text input
- **Body** — textarea (free text)
- **Tag** — radio: `Direct` / `Team Announcement` (auto-set by template, always editable)
- **Recipients** — checkboxes: `All`, `Present`, `Absent`, `Maybe`, `Unknown` (multi-select, default: All)
- **Channels** — checkboxes: `Email`, `In-app`, `Web Push` (all checked by default)
- **Preview** — the GET form handler embeds the total team player count per attendance status in the template as a JS data object; the client updates a "N players will be notified" label in real-time as the recipient checkboxes change, without any AJAX round-trip

**`POST /events/{id}/notify`** — includes `csrf_token` (follows project's `require_csrf` pattern), dispatches to `BackgroundTasks`, redirects back to event detail with a flash message showing how many players were queued.

Admin-only routes (`require_admin` dependency).

---

## 6. Player Profile & Preferences

New **Notification Preferences** section on `/profile`:

- Three toggles: **Email**, **In-app**, **Web Push** (all on by default)
- **"Enable browser notifications"** button — triggers browser permission prompt, POSTs subscription to `POST /notifications/webpush/subscribe`
- Subscription status: "Active on N device(s)"
- **"Remove all devices"** button → `POST /notifications/webpush/unsubscribe-all` (with CSRF token)

Admins can also view/edit preferences on the player detail page.

---

## 7. In-App Inbox & Real-Time UI

### Notification Bell (`base.html`)
- Shown to all logged-in users
- Initial unread count is **embedded in the base template context** by `AuthMiddleware` alongside `request.state.user`. The middleware opens its own short-lived `SessionLocal()` session (matching the existing pattern for user lookup). It finds the `Player` row(s) linked to the authenticated `User` via `Player.user_id`, sums unread `Notification` rows across all linked players, and sets `request.state.unread_count`. For admin users with no linked `Player` row, `request.state.unread_count = 0`. Unauthenticated requests set it to 0.
- Displays unread count badge
- Links to `/notifications` inbox

### Inbox (`/notifications`)
- Notifications newest-first
- Each row: tag badge, title, body preview, timestamp, read/unread indicator
- Clicking a notification marks it read and links to the related event (if applicable)
- "Mark all as read" button
- `POST /notifications/{id}/read` and `POST /notifications/read-all` — both include CSRF token, follow `require_csrf` pattern

### Real-Time Flow (SSE)

**Connection registry:** `services/channels/inapp_channel.py` maintains a module-level dict `_connections: dict[int, list[asyncio.Queue]]` keyed by `player_id`. Multiple concurrent connections for the same player (different tabs/devices) are supported — each gets its own `Queue`. When the SSE connection closes, the queue is removed from the list.

**Constraint:** The registry is in-process memory only. It does not work correctly behind multiple Uvicorn workers. ProManager must be run with a single worker (`--workers 1`), which is already the case for SQLite deployments. This constraint is noted in the README.

**Flow:**
1. Browser connects to `GET /notifications/stream` on every page load (authenticated only). Connection is added to the registry.
2. When `InAppChannel.send()` is called, it puts `{"unread_count": N}` into all queues for that player.
3. Browser updates the bell badge and shows a **toast** (bottom-right, auto-dismisses after 5s).
4. Toast click opens the inbox.
5. No message content over SSE — the client re-fetches the badge count from the embedded template state on next navigation.

### Real-Time Flow — Middleware Compatibility
`AuthMiddleware` uses Starlette's `BaseHTTPMiddleware`, which buffers the full response body and breaks streaming responses. The SSE route `GET /notifications/stream` must bypass this. The chosen approach: **auth is handled within the SSE route itself** (not via middleware). The route reads the session cookie directly using the same `_get_user_from_cookie` helper extracted from `AuthMiddleware`, and returns a 401 redirect if unauthenticated. The route is still registered on the main app and passes through the middleware, but `BaseHTTPMiddleware` is only called for the SSE endpoint's initial response headers — the streaming body is not buffered because `StreamingResponse` with an async generator is used, which Starlette handles correctly even with `BaseHTTPMiddleware` as long as the generator yields promptly. To be safe, the SSE route should be tested explicitly.

### Web Push (Service Worker)
- `static/js/sw.js` — registered on profile page when player enables push
- Handles `push` events: shows browser notification with title + body
- Handles `pushsubscriptionchange` event: re-subscribes and POSTs new subscription to `POST /notifications/webpush/subscribe`
- Click on browser notification opens the app

### Web Push Subscribe — CSRF Handling
`POST /notifications/webpush/subscribe` is triggered by JavaScript (not a traditional form POST) after the browser permission prompt. To carry the CSRF token, the profile page embeds the token in a `<meta name="csrf-token">` tag. The JavaScript subscribe handler reads this value and sends it as a form field in the POST body. The route uses the existing `require_csrf` dependency, which reads the token from the form body. This avoids a CSRF exemption.

---

## 8. New Files Summary

| Action | File | Purpose |
|---|---|---|
| Create | `models/notification.py` | Notification ORM model |
| Create | `models/notification_preference.py` | Per-player channel preferences |
| Create | `models/web_push_subscription.py` | Browser push subscriptions |
| Modify | `models/player.py` | Add `notifications` + `notification_preferences` + `web_push_subscriptions` relationships |
| Modify | `models/event.py` | Add `notifications` relationship |
| Modify | `models/__init__.py` | Export new models |
| Create | `alembic/versions/xxx_add_notifications.py` | DB migration (all three tables) |
| Create | `services/notification_service.py` | Dispatch orchestration + player preference creation |
| Create | `services/channels/__init__.py` | Channel package |
| Create | `services/channels/email_channel.py` | Email channel |
| Create | `services/channels/inapp_channel.py` | In-app + SSE registry + channel |
| Create | `services/channels/webpush_channel.py` | Web Push channel |
| Create | `routes/notifications.py` | Inbox, SSE stream, mark-read, webpush subscribe/unsubscribe, vapid public key |
| Modify | `routes/events.py` | Add GET/POST `/events/{id}/notify` handlers |
| Modify | `app/main.py` | Register notifications router; embed unread count in base context |
| Create | `templates/notifications/inbox.html` | Notification inbox page |
| Create | `templates/events/notify.html` | Admin send form |
| Modify | `templates/base.html` | Notification bell in nav |
| Modify | `templates/players/profile.html` | Notification preferences section |
| Create | `static/js/sw.js` | Service worker for Web Push |
| Create | `scripts/generate_vapid.py` | One-time VAPID key generation |

---

## 9. Dependencies

- `pywebpush~=2.0` — Web Push sending (pure Python, no C extensions, Python 3.12 compatible)
- No new dependencies for Email, In-App, or SSE (all stdlib or already present)

New env vars: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`

---

## 10. Out of Scope

- SMS / WhatsApp (deferred — provider TBD)
- i18n of template strings (deferred to i18n sub-project; EN, IT, DE, FR planned)
- Notification delivery receipts / read tracking per channel
- Admin notification history/audit log
- Multi-worker deployment (SSE registry is single-process; SQLite enforces single-worker anyway)
