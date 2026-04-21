# Telegram Notifications — Design Spec

**Date:** 2026-04-20  
**Status:** Approved

## Context

ProManager already sends Telegram messages when coach/admin posts in event chat (`services/chat_service.py → send_telegram_notifications()`). This spec expands Telegram to 4 new triggers: new event, event updated, attendance reminder, attendance change. Approach: add `"telegram"` as a formal channel in the existing notification system.

---

## Triggers

| # | Trigger | Recipients | Opt-in? |
|---|---------|-----------|---------|
| 1 | New event created | All team players | Checkbox on create form (already exists: `notify_on_create`) |
| 2 | Event updated | All team players | New checkbox on edit form: `notify_on_update` |
| 3 | Attendance reminder | Players with status present/maybe/unknown | Manual via existing send-reminders route |
| 4 | Player changes attendance | Coaches/admins of event's team only | Auto (no opt-in) |

---

## Architecture

```
notification_service._dispatch()
  ├── InAppChannel       (existing)
  ├── EmailChannel       (existing)
  ├── WebPushChannel     (existing)
  └── TelegramChannel    (NEW)

Attendance change (trigger 4):
  routes/attendance.py → BackgroundTask → notify_coaches_via_telegram()
  (separate path: recipients are coaches, not players)
```

`TelegramChannel` follows the same interface as existing channels:
- `send(notification: Notification, player: Player, db: Session) → bool`
- Gets `chat_id` from `player.user.telegram_chat_id`
- Returns `False` (skip silently) if player has no linked Telegram

---

## Message Format

All messages share the same inline keyboard:

```
[📅 This event]   [📋 All events]
```

- **This event** → callback `event_view:{event_id}` — opens event detail in bot
- **All events** → callback `events_list` — shows upcoming events list (existing bot behavior)

Message text per trigger:

**New event (trigger 1):**
```
📅 New event: {title}
{date} {time} @ {location}
{description if present}
```

**Event updated (trigger 2):**
```
✏️ Updated: {title}
{date} {time} @ {location}
```

**Attendance reminder (trigger 3):**
```
⏰ Reminder: {title}
{date} {time} @ {location}
Your status: {player_status}
```

**Attendance changed — to coaches (trigger 4):**
```
📋 {player_name} → {new_status}
{event_title} · {event_date}
```
(No event buttons on trigger 4 — coaches-only operational message.)

Chat messages keep existing format + "💬 Reply" button (unchanged).

---

## Data Model Changes

### `models/notification_preference.py`
```python
CHANNELS = ("email", "inapp", "webpush", "telegram")  # add "telegram"
```

### Alembic migration
Insert `notification_preferences` rows: `telegram` channel, `enabled=True`, for all existing players. Consistent with how other channels default.

---

## Files to Create / Modify

| File | Change |
|------|--------|
| `services/channels/telegram_channel.py` | **NEW** — `TelegramChannel` class |
| `services/notification_service.py` | Wire `TelegramChannel` into `_dispatch()` |
| `models/notification_preference.py` | Add `"telegram"` to `CHANNELS` |
| `routes/events.py` | Add `notify_on_update: str = Form("")` to edit handler; pass telegram to channels |
| `templates/events/event_form.html` | Add `notify_on_update` checkbox to edit form section |
| `routes/attendance.py` | Add BackgroundTask call for trigger 4 |
| `services/chat_service.py` | Add `notify_coaches_via_telegram()` helper for trigger 4 |
| `bot/handlers.py` | Add `event_view:{event_id}` callback handler; add `events_list` callback if missing |
| `alembic/versions/` | Migration: insert telegram preference rows for all players |

---

## `TelegramChannel` — Key Logic

```python
class TelegramChannel:
    def send(self, notification: Notification, player: Player, db: Session) -> bool:
        if not player.user or not player.user.telegram_chat_id:
            return False
        # build text from notification.title + notification.body
        # build inline keyboard: [This event, All events] if notification.event_id
        # call bot.telegram_app.bot.send_message(chat_id=..., text=..., reply_markup=...)
        # return True on success, False on failure (log warning, don't raise)
```

Format mapping: `notification.tag` drives the emoji prefix:
- `"event_new"` → 📅
- `"event_update"` → ✏️  
- `"reminder"` → ⏰
- anything else → 📬

---

## Bot Handler Additions

### `event_view:{event_id}` callback
Show event detail: title, date/time, location, player's current attendance status, inline buttons to mark status (reuse existing attendance-marking keyboard pattern).

### `events_list` callback  
Trigger same response as `/refresh` command — show upcoming events list with per-event inline buttons.

---

## Notification Preference UI

Existing `templates/notifications/preferences.html` shows channel toggles per notification type. Add Telegram row alongside email/inapp/webpush. No backend route changes needed — preferences route already handles arbitrary channel names from `CHANNELS`.

---

## Attendance Change Notification (Trigger 4)

`notify_coaches_via_telegram(event_id, player_id, new_status, db)`:
1. Fetch event's team coaches/admins via `UserTeam` where `role in ("admin", "coach")`
2. Collect `user.telegram_chat_id` for each
3. Send message (no inline buttons — coaches-only operational alert)
4. Called as `BackgroundTasks.add_task()` from `update_attendance()` handler

Only fires when status actually changes (already tracked in `update_attendance` via old status comparison).

---

## Verification

1. `pytest -v` — all tests pass (new channel must not break existing tests)
2. Configure `TELEGRAM_BOT_TOKEN` in `.env`, link a test user via `/start`
3. Create event with `notify_on_create` checked → Telegram message received with 2 buttons
4. Edit event with `notify_on_update` checked → Telegram message received
5. Trigger reminder via send-reminders route → Telegram message received
6. Update attendance as player → coach receives Telegram alert
7. Tap "📅 This event" button → event detail shown in bot
8. Tap "📋 All events" button → upcoming events list shown
9. Toggle Telegram off in notification preferences → no Telegram sent
10. Player with no Telegram linked → skipped silently, no error
