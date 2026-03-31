# Event Chat — Design Spec
**Date:** 2026-03-31

## Context

Each event needs a lightweight discussion space so coaches can post announcements and players can chat. The feature must integrate with the existing Telegram bot (push notifications with a reply-back action) and the existing SSE infrastructure for real-time updates in the web UI.

---

## Summary of decisions

| Question | Decision |
|---|---|
| Who can post | Two lanes: announcements (coach/admin only), discussion (everyone) |
| Web UI placement | Collapsible panel at bottom of event detail page |
| Real-time | SSE push via existing per-player queue |
| Telegram | Push notification on new message; users can reply via bot |
| Notification recipients | Present, maybe, unknown — not absent |
| Edit messages | No |
| Delete messages | Yes — own messages for all; all messages for admin/coach |

---

## Data model

**New table: `event_messages`**

```python
class EventMessage(Base):
    __tablename__ = "event_messages"

    id         : int          # PK
    event_id   : int          # FK → events.id CASCADE
    user_id    : int | None   # FK → users.id SET NULL
    lane       : str          # "announcement" | "discussion"
    body       : str          # Text
    created_at : datetime     # timezone=True
```

- Author is `user_id` (not `player_id`) — coaches/admins don't always have a player record.
- Display name: `user.first_name + last_name`, fallback to `user.username`.
- No `edited_at` — edit is out of scope.
- Alembic migration required.

---

## Backend

### New files
- `models/event_message.py` — model definition
- `routes/event_messages.py` — router mounted at `/events/{event_id}/messages`

### Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/events/{id}/messages` | `require_login` | All messages both lanes, ordered by `created_at`. Returns author display name. |
| `POST` | `/events/{id}/messages` | `require_login` | Post a message. `announcement` lane: 403 if not coach/admin. Fires SSE push + Telegram. |
| `DELETE` | `/events/{id}/messages/{msg_id}` | `require_login` | Author, or admin/coach for any message. Fires SSE delete push. |

### SSE integration

Push directly to the per-player SSE queue (via `inapp_channel.register_connection`) with two new event types — bypassing the `Notification` table (chat is not an inbox item):

```json
{"type": "chat_message", "event_id": 42, "message": { "id": 1, "lane": "announcement", "body": "...", "author": "Coach Name", "created_at": "..." }}
{"type": "chat_delete",  "event_id": 42, "message_id": 1}
```

Push targets all users (players AND coaches/admin) who have an active SSE connection and are associated with the event's team. Note: `_resolve_players` only returns `Player` records — coaches/admins without a player record must be resolved separately via `UserTeam` for SSE delivery. For Telegram notifications, the existing `send_notifications` path only covers players; a separate direct-send is needed for coaches/admins who have `telegram_chat_id` set.

### Telegram notifications

Reuse `send_notifications` with:
- `recipient_statuses=["present", "maybe", "unknown"]`
- `tag="chat_message"`

Bot message format:
```
💬 [Announcement | Discussion] — EventTitle
AuthorName: message body
→ /events/{id}
```

**Reply-back flow:**
1. Bot message includes a "Reply" inline button (`callback_data="chatreply:{event_id}:{lane}"`)
2. Pressing it prompts the user for text (same `awaiting_*` pattern as note input)
3. On text received: POST to `/events/{id}/messages` as `discussion` lane (replies always go to discussion, regardless of which lane triggered the notification)
4. Bot confirms: _"Your message was posted."_ and deletes the prompt

New bot callback prefix: `chatreply:` and new `awaiting_chat_reply` context key.

---

## Web UI

### Panel structure

Collapsible `<details>` element at the bottom of `templates/events/detail.html`, below the attendance columns.

```
▼ Chat
  [Announcements] [Discussion]   ← tab pills
  ─────────────────────────────
  📢 Coach Name  10:32
  Game starts at 14:00, be there at 13:30.  [🗑]
  ─────────────────────────────
  ┌──────────────────────────┐
  │ Write an announcement... │  [Send]
  └──────────────────────────┘
```

- Announcement tab: post box hidden for members (read-only)
- Discussion tab: post box visible for all
- Own messages show 🗑 delete button; admin/coach see it on all messages
- Announcements have a distinct background + 📢 label

### Real-time

On panel open:
1. `GET /events/{id}/messages` loads history
2. JS attaches a listener to the existing SSE connection (`/notifications/stream`) for `chat_message` and `chat_delete` events, filtered by `event_id`
3. New messages append to bottom of the correct lane tab
4. Deleted messages are removed by `id`

The SSE connection is already open for the notification badge — no second connection needed.

### Template variables needed

`event_detail` route must pass:
- `chat_messages`: list of all messages for the event (both lanes), with author display name pre-resolved
- `user_is_privileged`: already available as `user.is_admin or user.is_coach`

---

## Alembic migration

One `create_table` migration for `event_messages`. No changes to existing tables.

---

## Files to create / modify

| File | Action |
|---|---|
| `models/event_message.py` | Create |
| `models/__init__.py` | Add import |
| `routes/event_messages.py` | Create |
| `app/main.py` | Register new router |
| `routes/events.py` — `event_detail` | Pass `chat_messages` to template |
| `templates/events/detail.html` | Add chat panel + JS |
| `bot/handlers.py` | Add `chatreply:` callback + `awaiting_chat_reply` flow |
| `bot/keyboards.py` | Add Reply inline button helper |
| `alembic/versions/xxxx_add_event_messages.py` | Create migration |
| `locales/en.json` (+ it/fr/de) | Add `chat.*` translation keys |

---

## Verification

1. **Post an announcement** as coach → appears in panel, SSE pushes to connected members, Telegram notification sent to present/maybe/unknown players
2. **Post a discussion message** as member → appears in panel, SSE pushes to all, Telegram sent
3. **Member tries to post announcement** → 403
4. **Delete own message** → removed from UI live via SSE
5. **Admin deletes any message** → removed from UI live
6. **Reply via Telegram bot** → message appears in web discussion lane
7. **Absent player** → receives no Telegram notification
8. **Open panel on page load** → history loads correctly for both lanes
