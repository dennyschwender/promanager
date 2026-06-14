# Notification System Fixes Implementation Plan

> **For agentic workers:** Use dispatching-parallel-agents to implement this plan task-by-task.

**Goal:** Fix 9 identified issues in the notification system: bugs (magic link, ephemeral Notification, coach chat), robustness (enum channels, reminder retry, cleanup), and UX (Telegram in web UI, SSE→polling, opt-in).

**Architecture:** Each fix is self-contained touching 1-4 files. Tasks grouped into 3 blocks: bugs first, then robustness, then UX. No shared state between tasks except that SSE→polling requires the `/unread-count` endpoint.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, Python 3.12+

---

### Task 1: Add magic link to manual send-reminders

**Files:**
- Modify: `routes/events.py:1257`

**Problem:** Auto-reminder (`scheduler.py:93`) passes `magic_link` to `send_event_reminder()`, but manual reminder (`routes/events.py:1257`) does not.

**Change:** Add `create_magic_link()` call before `send_event_reminder()`.

- [ ] **Edit `routes/events.py` — pass magic_link to manual send_event_reminder**

```python
# Find imports at top of file — add auth_service import if needed
from services.auth_service import create_magic_link

# Inside send_reminders(), replace line 1257:
for att in attendances:
    player = att.player
    if player and player.email:
        magic = (
            create_magic_link(player.user.id, f"/events/{event_id}", player.user.email)
            if player.user_id
            else None
        )
        ok = send_event_reminder(
            player_email=player.email,
            player_name=player.full_name,
            event_title=event.title,
            event_date=event.event_date,
            event_time=event.event_time,
            event_location=event.location or "",
            magic_link=magic,
        )
```

- [ ] **Run tests to verify**

```bash
pytest tests/test_events.py tests/test_event_notify.py -v
```

- [ ] **Commit**

```bash
git add routes/events.py
git commit -m "fix: add magic link to manual send-reminders"
```

---

### Task 2: Remove ephemeral Notification from manual send-reminders

**Files:**
- Modify: `routes/events.py:1268-1300`

**Problem:** Manual reminders create `Notification(...)` without persisting to DB just to pass data to `TelegramChannel.send()`. Instead, pass data directly.

- [ ] **Edit `routes/events.py` — pass dict directly instead of fake Notification**

Replace the telegram block (lines 1268-1300):

```python
    # Telegram reminders to present/maybe/unknown players
    import os

    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        from services.channels.telegram_channel import TelegramChannel

        tg = TelegramChannel()
        tg_attendances = (
            db.query(Attendance)
            .filter(
                Attendance.event_id == event_id,
                Attendance.status.in_(["present", "maybe", "unknown"]),
            )
            .all()
        )
        date_str = event.event_date.strftime("%Y-%m-%d") if event.event_date else ""
        notif_body = date_str
        if event.event_time:
            notif_body += f" {event.event_time.strftime('%H:%M')}"
        if event.location:
            notif_body += f" · {event.location}"
        for att in tg_attendances:
            player = att.player
            if player:
                tg.send_raw(
                    player=player,
                    title=event.title,
                    body=f"{notif_body} · Your status: {att.status}",
                    tag="reminder",
                    event_id=event_id,
                )
```

- [ ] **Add `send_raw()` method to `TelegramChannel`**

```python
# In services/channels/telegram_channel.py, add method:
def send_raw(self, player: Player, title: str, body: str, tag: str, event_id: int | None = None) -> bool:
    if not player.user or not player.user.telegram_chat_id:
        return False
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return False
    emoji = _EMOJI.get(tag, "📬")
    text = f"{emoji} {title}\n{body}"
    payload: dict = {"chat_id": player.user.telegram_chat_id, "text": text}
    if event_id:
        payload["reply_markup"] = {
            "inline_keyboard": [
                [
                    {"text": "📅 This event", "callback_data": f"evt:{event_id}"},
                    {"text": "📋 All events", "callback_data": "evts:0"},
                ]
            ]
        }
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json=payload,
            timeout=10,
        )
        if not resp.ok:
            logger.warning("TelegramChannel: API error %s for player %s: %s", resp.status_code, player.id, resp.text)
        return resp.ok
    except Exception as exc:
        logger.warning("TelegramChannel: request failed for player %s: %s", player.id, exc, exc_info=True)
        return False
```

- [ ] **Update `send()` to delegate to `send_raw()`** (optional but DRY)

```python
def send(self, player: Player, notification: Notification) -> bool:
    return self.send_raw(
        player=player,
        title=notification.title,
        body=notification.body,
        tag=notification.tag,
        event_id=notification.event_id,
    )
```

- [ ] **Remove unused `Notification` import from routes/events.py** if it's only used in the telegram block

- [ ] **Run tests**

```bash
pytest tests/test_telegram_channel.py tests/test_events.py -v
```

- [ ] **Commit**

```bash
git add routes/events.py services/channels/telegram_channel.py
git commit -m "fix: replace ephemeral Notification with send_raw in manual reminders"
```

---

### Task 3: Notify coaches (non-player) in chat notifications

**Files:**
- Modify: `services/chat_service.py:notify_members_of_chat` (~lines 150-220)

**Problem:** `notify_members_of_chat()` only queries `Attendance` records (non-absent players). Coaches/managers without attendance records don't get web/in-app/push chat notifications, though they DO get Telegram chat buttons.

- [ ] **Edit `notify_members_of_chat` to also include coaches**

Add UserTeam query alongside the Attendance query:

```python
async def notify_members_of_chat(
    event_id: int,
    author_name: str,
    body_text: str,
    exclude_user_id: int | None,
) -> None:
    import app.database as _db_mod
    from models.attendance import Attendance
    from models.notification import Notification
    from models.user_team import UserTeam
    from services.channels.inapp_channel import push_unread_count, push_unread_count_to_user
    from services.channels.webpush_channel import WebPushChannel

    _webpush = WebPushChannel()
    db = _db_mod.SessionLocal()
    try:
        event = db.get(Event, event_id)
        if event is None:
            return

        preview = body_text[:50] + ("\u2026" if len(body_text) > 50 else "")
        notif_title = f"\U0001f4ac {author_name}: {preview}"
        notif_body = event.title

        seen_player_ids: set[int] = set()
        seen_user_ids: set[int] = set()

        # Existing: non-absent attendees
        att_rows = (
            db.query(Attendance)
            .filter(
                Attendance.event_id == event_id,
                Attendance.status.in_(["present", "maybe", "unknown"]),
            )
            .all()
        )
        for att in att_rows:
            player = db.get(Player, att.player_id)
            if not player or not player.user_id or player.user_id == exclude_user_id:
                continue
            if player.id in seen_player_ids:
                continue
            seen_player_ids.add(player.id)

            notif = Notification(
                player_id=player.id,
                event_id=event_id,
                title=notif_title,
                body=notif_body,
                tag="chat",
            )
            db.add(notif)
            db.flush()

            unread = (
                db.query(Notification)
                .filter(Notification.player_id == player.id, Notification.is_read.is_(False))
                .count()
            )
            push_unread_count(player.id, unread)
            _webpush.send(player, notif, db)
            if player.user_id:
                seen_user_ids.add(player.user_id)

        # New: coaches/admins via UserTeam (skip if already notified via attendance)
        if event.team_id is not None:
            for ut in db.query(UserTeam).filter(UserTeam.team_id == event.team_id).all():
                if ut.user_id == exclude_user_id or ut.user_id in seen_user_ids:
                    continue
                if not ut.user:
                    continue
                seen_user_ids.add(ut.user_id)
                coach_player = ut.user.players[0] if ut.user.players else None

                notif = Notification(
                    player_id=coach_player.id if coach_player else None,
                    user_id=ut.user_id if not coach_player else None,
                    event_id=event_id,
                    title=notif_title,
                    body=notif_body,
                    tag="chat",
                )
                db.add(notif)
                db.flush()

                if coach_player:
                    unread = (
                        db.query(Notification)
                        .filter(Notification.player_id == coach_player.id, Notification.is_read.is_(False))
                        .count()
                    )
                    push_unread_count(coach_player.id, unread)
                    _webpush.send(coach_player, notif, db)
                else:
                    unread = (
                        db.query(Notification)
                        .filter(Notification.user_id == ut.user_id, Notification.is_read.is_(False))
                        .count()
                    )
                    push_unread_count_to_user(ut.user_id, unread)
                    _webpush.send_to_user(ut.user_id, notif, db)

        db.commit()
    except Exception:
        logger.exception("notify_members_of_chat failed for event %d", event_id)
        db.rollback()
    finally:
        db.close()
```

- [ ] **Run tests**

```bash
pytest tests/test_chat_service.py tests/test_event_messages.py -v
```

- [ ] **Commit**

```bash
git add services/chat_service.py
git commit -m "fix: notify coaches via UserTeam in chat notifications"
```

---

### Task 4: Replace raw channel strings with StrEnum

**Files:**
- Modify: `models/notification_preference.py`
- Modify: `services/notification_service.py`
- Modify: `routes/notifications.py`
- Modify: `routes/events.py`
- Modify: `services/telegram_notifications.py`
- Modify: `services/scheduler.py`
- Modify: `tests/test_notification_service.py`
- Modify: `tests/test_notification_routes.py`

- [ ] **Add ChannelType StrEnum to `models/notification_preference.py`**

```python
from enum import StrEnum

class ChannelType(StrEnum):
    EMAIL = "email"
    INAPP = "inapp"
    WEBPUSH = "webpush"
    TELEGRAM = "telegram"

CHANNELS = tuple(c.value for c in ChannelType)
```

- [ ] **Update all `"email"` / `"inapp"` / `"webpush"` / `"telegram"` string literals to use `ChannelType` enum**

Search and replace pattern across all files:

**`services/notification_service.py`:**
- `get_preference(player.id, "inapp", db)` → `get_preference(player.id, ChannelType.INAPP, db)`
- `get_preference(player.id, "email", db)` → `get_preference(player.id, ChannelType.EMAIL, db)`
- Same for webpush, telegram
- `if "inapp" in admin_channels` → stays as-is (admin_channels is a list sent by caller)
- `admin_channels=["inapp", "webpush", "telegram"]` → stays string-based (callee decides)

**`routes/events.py`:**
- Channels list from form: stays as strings (form values)
- `admin_channels=channels` stays as-is

**`services/telegram_notifications.py`:**
- `NotificationPreference.channel == "telegram"` → `NotificationPreference.channel == ChannelType.TELEGRAM`
- `get_user_preference(ut.user_id, "telegram", db)` → `get_user_preference(ut.user_id, ChannelType.TELEGRAM, db)`

**`services/scheduler.py`:**
- `get_preference(player.id, "email", db)` → `get_preference(player.id, ChannelType.EMAIL, db)`
- `admin_channels=["inapp", "webpush", "telegram"]` → stays string

**`routes/notifications.py`:**
- `channel in CHANNELS` → stays (CHANNELS is tuple of str values)

**Tests:**
- `get_preference(player.id, "email", db)` → `get_preference(player.id, ChannelType.EMAIL, db)`

- [ ] **Run full test suite**

```bash
pytest -v
```

- [ ] **Commit**

```bash
git add models/notification_preference.py services/notification_service.py services/telegram_notifications.py services/scheduler.py routes/events.py routes/notifications.py tests/
git commit -m "refactor: use ChannelType StrEnum instead of raw strings"
```

---

### Task 5: Add reminder retry with reminder_attempts

**Files:**
- Modify: `models/event.py`
- Create: `alembic/versions/` (auto-generated)
- Modify: `services/scheduler.py:send_due_reminders`

- [ ] **Add `reminder_attempts` field to Event model**

```python
# In models/event.py, add field:
reminder_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

- [ ] **Generate Alembic migration**

```bash
source .venv/bin/activate
alembic revision --autogenerate -m "add reminder_attempts to events"
alembic upgrade head
```

- [ ] **Modify `send_due_reminders` to use reminder_attempts**

Instead of filtering `reminder_sent.is_(False)`, filter `(Event.reminder_sent.is_(False)) | (Event.reminder_attempts < 3)` and check `reminder_sent` per-event:

```python
# In services/scheduler.py:send_due_reminders, change the events query:
events = (
    db.query(Event)
    .filter(
        (Event.reminder_sent.is_(False)) | (Event.reminder_attempts < 3),
        Event.event_date >= today,
        Event.event_date <= cutoff_date,
    )
    .all()
)
```

Then at the end, instead of `event.reminder_sent = True`:

```python
event.reminder_attempts = (event.reminder_attempts or 0) + 1
if event.reminder_attempts >= 3:
    event.reminder_sent = True
db.add(event)
```

- [ ] **Run tests**

```bash
pytest tests/test_scheduler.py -v
```

- [ ] **Commit**

```bash
git add models/event.py services/scheduler.py alembic/
git commit -m "feat: add reminder_attempts retry logic (max 3 attempts)"
```

---

### Task 6: Add notification cleanup

**Files:**
- Modify: `services/scheduler.py`

- [ ] **Add `cleanup_old_notifications()` function**

```python
def cleanup_old_notifications() -> int:
    from datetime import datetime, timezone, timedelta

    from app.database import SessionLocal
    from models.notification import Notification
    from models.telegram_notification import TelegramNotification

    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        n_deleted = (
            db.query(Notification)
            .filter(Notification.created_at < cutoff)
            .delete(synchronize_session="fetch")
        )
        tg_deleted = (
            db.query(TelegramNotification)
            .filter(TelegramNotification.created_at < cutoff)
            .delete(synchronize_session="fetch")
        )
        db.commit()
        total = n_deleted + tg_deleted
        if total:
            logger.info("Cleanup: deleted %d notifications (notif=%d, tg=%d)", total, n_deleted, tg_deleted)
        return total
    except Exception:
        logger.exception("Notification cleanup failed")
        db.rollback()
        return 0
    finally:
        db.close()
```

- [ ] **Add `notification_cleanup_loop` scheduler loop**

```python
async def notification_cleanup_loop(interval_seconds: int = 86400) -> None:
    logger.info("Notification cleanup scheduler started (interval=%ds)", interval_seconds)
    await asyncio.sleep(3600)  # first run after 1h
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            count = await asyncio.get_event_loop().run_in_executor(None, cleanup_old_notifications)
            if count:
                logger.info("Notification cleanup: removed %d old record(s)", count)
        except asyncio.CancelledError:
            logger.info("Notification cleanup scheduler stopped.")
            break
        except Exception:
            logger.exception("Unexpected error in notification cleanup loop — continuing")
```

- [ ] **Register the new loop in `app/main.py` lifespan**

```python
# In app/main.py lifespan, add:
from services.scheduler import backup_loop, cleanup_loop, notification_cleanup_loop, reminder_loop

_notif_cleanup_task = asyncio.create_task(notification_cleanup_loop())
# Add to shutdown:
for _task in (_reminder_task, _cleanup_task, _backup_task, _notif_cleanup_task):
    _task.cancel()
```

- [ ] **Run tests**

```bash
pytest tests/test_scheduler.py -v
```

- [ ] **Commit**

```bash
git add services/scheduler.py app/main.py
git commit -m "feat: add notification cleanup (90-day TTL)"
```

---

### Task 7: Add Telegram toggle in web UI profile

**Files:**
- Modify: `templates/auth/profile.html`
- Modify: `app/main.py` (profile_page route)

- [ ] **Edit profile.html — add Telegram to channel list**

Change the channel loop from:

```jinja2
{% for channel, label in [("email", t('auth.channel_email')), ("inapp", t('auth.channel_inbox')), ("webpush", t('auth.channel_push'))] %}
```

To:

```jinja2
{% set channels = [("email", t('auth.channel_email')), ("inapp", t('auth.channel_inbox')), ("webpush", t('auth.channel_push'))] %}
{% if current_player.user.telegram_chat_id or user.telegram_chat_id %}
  {% set channels = channels + [("telegram", t('auth.channel_telegram'))] %}
{% endif %}
{% for channel, label in channels %}
```

Wait — the profile template doesn't have direct access to `user.telegram_chat_id`. Let me check... Actually `user` is the logged-in user object which does have `telegram_chat_id`. So:

```jinja2
{% for channel, label in [("email", t('auth.channel_email')), ("inapp", t('auth.channel_inbox')), ("webpush", t('auth.channel_push'))] %}
```

Replace with:

```jinja2
{% for channel, label in [("email", t('auth.channel_email')), ("inapp", t('auth.channel_inbox')), ("webpush", t('auth.channel_push')), ("telegram", t('auth.channel_telegram'))] %}
```

Always show the Telegram toggle (since the channel is only effective when chat_id is set — the code already handles that via `TelegramChannel.send` guard).

- [ ] **Run tests**

```bash
pytest tests/test_notification_routes.py -v
```

- [ ] **Commit**

```bash
git add templates/auth/profile.html
git commit -m "feat: add Telegram notification toggle to web UI profile"
```

---

### Task 8: Replace SSE with polling

**Files:**
- Modify: `templates/base.html` (remove EventSource, add polling)
- Modify: `routes/notifications.py` (keep or remove /stream endpoint)
- Modify: `services/channels/inapp_channel.py` (keep for backward compat or remove)
- Create: `routes/notifications.py` → add `/unread-count` endpoint

- [ ] **Add `/notifications/unread-count` endpoint**

```python
# In routes/notifications.py:
@router.get("/unread-count")
async def unread_count(
    request: Request,
    user=Depends(require_login),
    db: Session = Depends(get_db),
):
    player_ids = _player_ids_for_user(user, db)
    count = (
        db.query(Notification)
        .filter(
            or_(
                Notification.player_id.in_(player_ids) if player_ids else False,
                Notification.user_id == user.id,
            ),
            Notification.is_read.is_(False),
        )
        .count()
    )
    return JSONResponse({"unread_count": count})
```

- [ ] **Replace SSE in `templates/base.html` with polling**

Remove the EventSource block (lines 175-207) and replace with:

```html
{% if user %}
<script>
(function () {
  let lastUnread = {{ request.state.unread_count }};
  function pollUnread() {
    fetch("/notifications/unread-count")
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var count = data.unread_count;
        var badge = document.querySelector(".notif-badge");
        var bell = document.querySelector(".notif-bell");
        if (count > 0 && count !== lastUnread) {
          if (!badge) {
            var span = document.createElement("span");
            span.className = "notif-badge";
            bell.appendChild(span);
            badge = span;
          }
          badge.textContent = count;
          showToast({{ t('notifications.new_notification')|tojson }});
        } else if (count === 0 && badge) {
          badge.remove();
        }
        lastUnread = count;
      })
      .catch(function () {});
  }
  setInterval(pollUnread, 20000);

  function showToast(msg) {
    var toast = document.createElement("div");
    toast.className = "notif-toast";
    toast.textContent = msg;
    toast.onclick = function () { window.location.href = "/notifications"; };
    document.body.appendChild(toast);
    setTimeout(function () { toast.remove(); }, 5000);
  }
})();
</script>
<style>
.notif-toast {
  position: fixed; bottom: 1.5rem; right: 1.5rem; z-index: 9999;
  background: var(--contrast); color: var(--contrast-inverse); padding: .75rem 1.25rem;
  border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,.25);
  cursor: pointer; font-size: .92rem; max-width: 320px;
  animation: slideIn .3s ease;
}
@keyframes slideIn { from { transform: translateY(2rem); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
</style>
{% endif %}
```

- [ ] **Remove SSE endpoint** (keep old endpoint for backward compat with existing tabs, but unused by new code)

- [ ] **Run tests**

```bash
pytest tests/test_notification_routes.py -v
python -c "from app.main import app; print('imports OK')"
```

- [ ] **Commit**

```bash
git add templates/base.html routes/notifications.py
git commit -m "refactor: replace SSE with polling for notification badge"
```

---

### Task 9: Switch notification preferences from opt-out to opt-in

**Files:**
- Modify: `services/notification_service.py`
- Modify: `routes/notifications.py`

- [ ] **Change `get_preference` default from True to False**

```python
def get_preference(player_id: int, channel: ChannelType, db: Session) -> bool:
    pref = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.player_id == player_id,
            NotificationPreference.channel == channel,
        )
        .first()
    )
    return pref.enabled if pref is not None else False
```

- [ ] **Change `get_user_preference` default from True to False**

```python
def get_user_preference(user_id: int, channel: ChannelType, db: Session) -> bool:
    pref = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.user_id == user_id,
            NotificationPreference.channel == channel,
        )
        .first()
    )
    return pref.enabled if pref is not None else False
```

- [ ] **Change `create_default_preferences` to set `enabled=False`**

Wait — actually if we default to False, we need to create preferences with enabled=True so the user CAN enable them. The current flow is:
1. User visits profile page first time
2. `create_default_preferences()` creates all channels with `enabled=True`

With opt-in, we should either:
- Keep `create_default_preferences()` creating with `enabled=False` (user must toggle them on)
- Or not create defaults at all and let `get_preference` return False

Better: don't change `create_default_preferences` — instead just change the default in `get_preference`/`get_user_preference`. When preferences are missing, they're disabled. But when created (via profile page), they start enabled.

Actually, let me think about this more carefully. The `get_preference` default of `True` means: "if there's no preference row for this player+channel, assume enabled". Changing to `False` means: "if there's no preference row, assume disabled". This is the opt-in vs opt-out change.

The `create_default_preferences` creates rows with `enabled=True` — that's called when the user first visits the preferences page. So existing users who haven't visited the page will go from "assumed enabled" to "assumed disabled" — this is correct for opt-in.

For new users created via the admin panel, `create_default_preferences` is NOT called automatically. So they'll start with everything disabled — correct opt-in behavior.

No changes needed to `create_default_preferences`.

- [ ] **Update tests that rely on the old default**

In `test_notification_service.py`:

```python
# test_get_preference_returns_true_when_missing: now returns False
def test_get_preference_returns_false_when_missing(db, player):
    assert get_preference(player.id, "email", db) is False
```

And `test_send_skips_disabled_channel` should still work (it creates defaults first, then disables one).

But `test_send_creates_notification_rows` — it calls `create_default_preferences(player.id, db)` first, so it works (prefs exist with enabled=True).

However, without `create_default_preferences`, sending a notification would now be a no-op since all channels are disabled. This is correct behavior.

- [ ] **Run full test suite**

```bash
pytest -v
```

- [ ] **Commit**

```bash
git add services/notification_service.py tests/test_notification_service.py
git commit -m "refactor: switch notification preferences to opt-in (default disabled)"
```