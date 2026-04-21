# Telegram Notifications Expansion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand Telegram notifications to fire on new event (opt-in), event update (opt-in), attendance reminder, and attendance status change (coaches only).

**Architecture:** Add `TelegramChannel` to `services/channels/` using `requests` against the Telegram HTTP API (sync, compatible with notification_service's sync `_dispatch()`). Wire it into `_dispatch()` and add `"telegram"` to `CHANNELS`. Attendance-change-to-coaches uses a separate async helper `notify_coaches_via_telegram()` in `services/telegram_notifications.py` (same pattern as `chat_service.py`). No new bot handlers needed — `evt:{id}` and `evts:0` callbacks already exist in `bot/handlers.py`.

**Tech Stack:** requests (already in requirements), python-telegram-bot, SQLAlchemy 2.x, FastAPI BackgroundTasks, Alembic

---

## File Map

| File | Action |
|------|--------|
| `services/channels/telegram_channel.py` | **Create** — TelegramChannel.send() via HTTP API |
| `services/telegram_notifications.py` | **Create** — async notify_coaches_via_telegram() |
| `models/notification_preference.py` | **Modify** — add "telegram" to CHANNELS tuple |
| `services/notification_service.py` | **Modify** — import + instantiate TelegramChannel, add to _dispatch() |
| `routes/events.py` | **Modify** — tag="event_new" on create, add notify_on_update + tag="event_update" + BackgroundTasks to edit handler, add Telegram to send_reminders |
| `routes/attendance.py` | **Modify** — add BackgroundTask call after status change |
| `alembic/versions/q5r6s7t8u9v0_add_telegram_notification_pref.py` | **Create** — insert telegram preference rows for existing players |
| `templates/events/event_form.html` | **Modify** — telegram checkbox in notify_channels section + notify_on_update checkbox |
| `tests/test_telegram_channel.py` | **Create** |
| `tests/test_telegram_notifications.py` | **Create** |

---

## Task 1: TelegramChannel

**Files:**
- Create: `services/channels/telegram_channel.py`
- Create: `tests/test_telegram_channel.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_telegram_channel.py
from __future__ import annotations
from unittest.mock import MagicMock, patch

import pytest


def _player(chat_id: str | None = "123456"):
    p = MagicMock()
    p.id = 1
    p.user = MagicMock()
    p.user.telegram_chat_id = chat_id
    return p


def _notif(event_id: int | None = 42, tag: str = "event_new"):
    n = MagicMock()
    n.title = "Training"
    n.body = "Tue 29 Apr 18:00 · Sports Center"
    n.tag = tag
    n.event_id = event_id
    return n


def test_returns_false_when_no_chat_id():
    from services.channels.telegram_channel import TelegramChannel
    assert TelegramChannel().send(_player(chat_id=None), _notif()) is False


def test_returns_false_when_no_user():
    from services.channels.telegram_channel import TelegramChannel
    p = MagicMock()
    p.user = None
    assert TelegramChannel().send(p, _notif()) is False


def test_returns_false_when_no_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    from services.channels.telegram_channel import TelegramChannel
    assert TelegramChannel().send(_player(), _notif()) is False


def test_posts_to_telegram_api(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    resp = MagicMock()
    resp.ok = True
    from services.channels.telegram_channel import TelegramChannel
    with patch("services.channels.telegram_channel.requests.post", return_value=resp) as mock_post:
        result = TelegramChannel().send(_player("999"), _notif(event_id=42, tag="event_new"))
    assert result is True
    payload = mock_post.call_args.kwargs["json"]
    assert payload["chat_id"] == "999"
    assert "📅" in payload["text"]
    assert "Training" in payload["text"]
    buttons = payload["reply_markup"]["inline_keyboard"][0]
    assert any(b["callback_data"] == "evt:42" for b in buttons)
    assert any(b["callback_data"] == "evts:0" for b in buttons)


def test_no_buttons_when_no_event_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    resp = MagicMock()
    resp.ok = True
    from services.channels.telegram_channel import TelegramChannel
    with patch("services.channels.telegram_channel.requests.post", return_value=resp) as mock_post:
        TelegramChannel().send(_player(), _notif(event_id=None))
    assert "reply_markup" not in mock_post.call_args.kwargs["json"]


def test_returns_false_on_api_error(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    resp = MagicMock()
    resp.ok = False
    resp.status_code = 400
    resp.text = "Bad Request"
    from services.channels.telegram_channel import TelegramChannel
    with patch("services.channels.telegram_channel.requests.post", return_value=resp):
        assert TelegramChannel().send(_player(), _notif()) is False


def test_returns_false_on_request_exception(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    from services.channels.telegram_channel import TelegramChannel
    with patch("services.channels.telegram_channel.requests.post", side_effect=Exception("timeout")):
        assert TelegramChannel().send(_player(), _notif()) is False


@pytest.mark.parametrize("tag,emoji", [
    ("event_new", "📅"),
    ("event_update", "✏️"),
    ("reminder", "⏰"),
    ("announcement", "📅"),
    ("direct", "📬"),
    ("unknown_tag", "📬"),
])
def test_emoji_mapping(monkeypatch, tag, emoji):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    resp = MagicMock()
    resp.ok = True
    from services.channels.telegram_channel import TelegramChannel
    with patch("services.channels.telegram_channel.requests.post", return_value=resp) as mock_post:
        TelegramChannel().send(_player(), _notif(tag=tag))
    assert emoji in mock_post.call_args.kwargs["json"]["text"]
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
pytest tests/test_telegram_channel.py -v
```
Expected: `ModuleNotFoundError: No module named 'services.channels.telegram_channel'`

- [ ] **Step 3: Implement TelegramChannel**

```python
# services/channels/telegram_channel.py
"""services/channels/telegram_channel.py — Telegram notification channel."""
from __future__ import annotations

import logging
import os

import requests

from models.notification import Notification
from models.player import Player

logger = logging.getLogger(__name__)

_EMOJI: dict[str, str] = {
    "event_new": "📅",
    "event_update": "✏️",
    "reminder": "⏰",
    "announcement": "📅",
}


class TelegramChannel:
    """Sends a notification to a player's linked Telegram chat via the Bot HTTP API."""

    def send(self, player: Player, notification: Notification) -> bool:
        if not player.user or not player.user.telegram_chat_id:
            return False
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not token:
            return False

        emoji = _EMOJI.get(notification.tag, "📬")
        text = f"{emoji} {notification.title}\n{notification.body}"
        payload: dict = {"chat_id": player.user.telegram_chat_id, "text": text}

        if notification.event_id:
            payload["reply_markup"] = {
                "inline_keyboard": [[
                    {"text": "📅 This event", "callback_data": f"evt:{notification.event_id}"},
                    {"text": "📋 All events", "callback_data": "evts:0"},
                ]]
            }

        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
                timeout=10,
            )
            if not resp.ok:
                logger.warning(
                    "TelegramChannel: API error %s for player %s: %s",
                    resp.status_code, player.id, resp.text,
                )
            return resp.ok
        except Exception as exc:
            logger.warning("TelegramChannel: request failed for player %s: %s", player.id, exc)
            return False
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
pytest tests/test_telegram_channel.py -v
```
Expected: all 13 tests PASS

- [ ] **Step 5: Commit**

```bash
git add services/channels/telegram_channel.py tests/test_telegram_channel.py
git commit -m "feat: add TelegramChannel for notification dispatch"
```

---

## Task 2: Wire TelegramChannel into notification_service

**Files:**
- Modify: `models/notification_preference.py`
- Modify: `services/notification_service.py`

- [ ] **Step 1: Update CHANNELS in `models/notification_preference.py`**

Change line:
```python
CHANNELS = ("email", "inapp", "webpush")
```
To:
```python
CHANNELS = ("email", "inapp", "webpush", "telegram")
```

- [ ] **Step 2: Add TelegramChannel to `services/notification_service.py`**

After the existing imports at the top of the file (around line 14–20), add:
```python
from services.channels.telegram_channel import TelegramChannel
```

After line 20 where `_inapp_channel` is instantiated, add:
```python
_telegram_channel = TelegramChannel()
```

Inside `_dispatch()`, after the `webpush` block (around line 156), add:
```python
            if "telegram" in admin_channels and get_preference(player.id, "telegram", db):
                _telegram_channel.send(player, notif)
```

- [ ] **Step 3: Run existing tests to confirm nothing broke**

```bash
pytest tests/ -v -x -q
```
Expected: all existing tests PASS (TelegramChannel.send is a no-op when TELEGRAM_BOT_TOKEN not set)

- [ ] **Step 4: Commit**

```bash
git add models/notification_preference.py services/notification_service.py
git commit -m "feat: wire TelegramChannel into notification_service dispatch"
```

---

## Task 3: Alembic migration — telegram notification preferences

**Files:**
- Create: `alembic/versions/q5r6s7t8u9v0_add_telegram_notification_pref.py`

- [ ] **Step 1: Create migration file**

```python
# alembic/versions/q5r6s7t8u9v0_add_telegram_notification_pref.py
"""add telegram notification preference for all players

Revision ID: q5r6s7t8u9v0
Revises: p4q5r6s7t8u9
Create Date: 2026-04-20
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "q5r6s7t8u9v0"
down_revision: Union[str, Sequence[str], None] = "p4q5r6s7t8u9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Insert telegram preference (enabled=True) for every player that doesn't
    # already have one — uses INSERT OR IGNORE for idempotency.
    op.execute("""
        INSERT OR IGNORE INTO notification_preferences (player_id, channel, enabled)
        SELECT id, 'telegram', 1
        FROM players
    """)


def downgrade() -> None:
    op.execute("DELETE FROM notification_preferences WHERE channel = 'telegram'")
```

- [ ] **Step 2: Run migration**

```bash
.venv/bin/alembic upgrade head
```
Expected: `Running upgrade p4q5r6s7t8u9 -> q5r6s7t8u9v0`

- [ ] **Step 3: Verify rows inserted**

```bash
python3 -c "
from app.database import SessionLocal
from models.notification_preference import NotificationPreference
db = SessionLocal()
count = db.query(NotificationPreference).filter_by(channel='telegram').count()
print(f'telegram prefs: {count}')
db.close()
"
```
Expected: count > 0 (one per player)

- [ ] **Step 4: Commit**

```bash
git add alembic/versions/q5r6s7t8u9v0_add_telegram_notification_pref.py
git commit -m "feat: migrate telegram notification preferences for all players"
```

---

## Task 4: Event create — use tag="event_new" and include telegram in default channels

**Files:**
- Modify: `routes/events.py` (event_new_post function, notify block ~line 380)

- [ ] **Step 1: Update notify block in `event_new_post`**

Find the notify block in `event_new_post` that reads:
```python
    if notify_on_create.strip() and first_event is not None:
        form_data = await request.form()
        channels = list(form_data.getlist("notify_channels")) or ["email", "inapp", "webpush"]
        ...
        send_notifications(
            ...
            tag="announcement",
            ...
        )
```

Change to:
```python
    if notify_on_create.strip() and first_event is not None:
        form_data = await request.form()
        channels = list(form_data.getlist("notify_channels")) or ["email", "inapp", "webpush", "telegram"]
        ...
        send_notifications(
            ...
            tag="event_new",
            ...
        )
```

(Two changes: default channels list adds `"telegram"`, tag changes from `"announcement"` to `"event_new"`.)

- [ ] **Step 2: Add telegram checkbox to event form template**

In `templates/events/event_form.html`, find the `notify_channels` checkbox group (where email, inapp, webpush checkboxes are rendered). Add a Telegram checkbox alongside them:

```html
<label>
  <input type="checkbox" name="notify_channels" value="telegram" checked>
  Telegram
</label>
```

Place it after the existing webpush checkbox, matching the existing checkbox style in the template.

- [ ] **Step 3: Run tests**

```bash
pytest tests/ -v -x -q
```
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add routes/events.py templates/events/event_form.html
git commit -m "feat: include telegram in event create notification channels"
```

---

## Task 5: Event update — notify_on_update with Telegram

**Files:**
- Modify: `routes/events.py` (event_edit_post function)
- Modify: `templates/events/event_form.html`

- [ ] **Step 1: Add `BackgroundTasks` and `notify_on_update` param to `event_edit_post`**

Current signature (around line 809):
```python
async def event_edit_post(
    event_id: int,
    request: Request,
    title: str = Form(...),
    ...
    edit_scope: str = Form("single"),
    user: User = Depends(require_coach_or_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
```

Add two parameters:
```python
async def event_edit_post(
    event_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    ...
    edit_scope: str = Form("single"),
    notify_on_update: str = Form(""),
    user: User = Depends(require_coach_or_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
```

Make sure `BackgroundTasks` is imported at the top of `routes/events.py` (it's likely already imported since `event_new_post` uses it — verify with `grep "BackgroundTasks" routes/events.py`).

- [ ] **Step 2: Add notify block before the return in `event_edit_post`**

Just before `return RedirectResponse(f"/events/{event_id}", status_code=302)` at the end of `event_edit_post`, add:

```python
    if notify_on_update.strip() and event is not None:
        form_data = await request.form()
        channels = list(form_data.getlist("notify_channels")) or ["email", "inapp", "webpush", "telegram"]
        date_str = event.event_date.strftime("%Y-%m-%d") if event.event_date else ""
        notif_body = date_str
        if event.event_time:
            notif_body += f" {event.event_time.strftime('%H:%M')}"
        if event.location:
            notif_body += f" · {event.location}"
        from services.notification_service import send_notifications  # noqa: PLC0415
        send_notifications(
            event=event,
            title=event.title,
            body=notif_body.strip(),
            tag="event_update",
            recipient_statuses=None,
            admin_channels=channels,
            db=db,
            background_tasks=background_tasks,
        )
```

Note: `send_notifications` is likely already imported at the top of `routes/events.py` (used by `event_new_post`). Remove the inline import if so.

- [ ] **Step 3: Add notify_on_update checkbox to event form template**

In `templates/events/event_form.html`, find the edit form section (the part shown when editing an existing event, not creating). Add the checkbox in the notify section. If there's no notify section on the edit form, add one above the submit button:

```html
<div class="notify-section">
  <label>
    <input type="checkbox" name="notify_on_update" value="1">
    Notify team about this update
  </label>
  <div class="channel-options">
    <label><input type="checkbox" name="notify_channels" value="email" checked> Email</label>
    <label><input type="checkbox" name="notify_channels" value="inapp" checked> In-app</label>
    <label><input type="checkbox" name="notify_channels" value="webpush" checked> Push</label>
    <label><input type="checkbox" name="notify_channels" value="telegram" checked> Telegram</label>
  </div>
</div>
```

Match the exact CSS classes and structure already used for the `notify_on_create` section in the same template.

- [ ] **Step 4: Run tests**

```bash
pytest tests/ -v -x -q
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add routes/events.py templates/events/event_form.html
git commit -m "feat: notify team via Telegram on event update (opt-in)"
```

---

## Task 6: Attendance reminder — add Telegram sends

**Files:**
- Modify: `routes/events.py` (send_reminders handler, lines 915–950)

- [ ] **Step 1: Extend `send_reminders` to also send Telegram**

Current handler iterates attendances with `status == "unknown"` and sends email. Add a second loop after the email loop to send Telegram to players with `status IN ("present", "maybe", "unknown")`.

Replace the `send_reminders` handler body with:

```python
    event = db.get(Event, event_id)
    if event is None:
        return RedirectResponse("/events", status_code=302)
    check_team_access(_user, event.team_id, db, season_id=event.season_id)

    # Email reminders to players with unknown status (existing behaviour)
    unknown_attendances = db.query(Attendance).filter(
        Attendance.event_id == event_id, Attendance.status == "unknown"
    ).all()
    sent = 0
    for att in unknown_attendances:
        player = att.player
        if player and player.email:
            ok = send_event_reminder(
                player_email=player.email,
                player_name=player.full_name,
                event_title=event.title,
                event_date=event.event_date,
                event_time=event.event_time,
                event_location=event.location or "",
            )
            if ok:
                sent += 1

    # Telegram reminders to present/maybe/unknown players
    from services.channels.telegram_channel import TelegramChannel  # noqa: PLC0415
    import os  # noqa: PLC0415
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        tg = TelegramChannel()
        tg_attendances = db.query(Attendance).filter(
            Attendance.event_id == event_id,
            Attendance.status.in_(["present", "maybe", "unknown"]),
        ).all()
        date_str = event.event_date.strftime("%Y-%m-%d") if event.event_date else ""
        notif_body = date_str
        if event.event_time:
            notif_body += f" {event.event_time.strftime('%H:%M')}"
        if event.location:
            notif_body += f" · {event.location}"
        for att in tg_attendances:
            player = att.player
            if player:
                from models.notification import Notification  # noqa: PLC0415
                fake_notif = Notification(
                    player_id=player.id,
                    event_id=event_id,
                    title=event.title,
                    body=f"{notif_body} · Your status: {att.status}",
                    tag="reminder",
                )
                tg.send(player, fake_notif)

    event.reminder_sent = True
    db.add(event)
    db.commit()

    return RedirectResponse(f"/events/{event_id}?reminders_sent={sent}", status_code=302)
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/ -v -x -q
```
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add routes/events.py
git commit -m "feat: send Telegram reminders alongside email in send-reminders"
```

---

## Task 7: Attendance change — notify coaches via Telegram

**Files:**
- Create: `services/telegram_notifications.py`
- Modify: `routes/attendance.py`
- Create: `tests/test_telegram_notifications.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_telegram_notifications.py
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


@pytest.mark.asyncio
async def test_notify_coaches_sends_to_coaches_with_telegram():
    """notify_coaches_via_telegram sends to coaches/admins with telegram_chat_id linked."""
    from services.telegram_notifications import notify_coaches_via_telegram

    mock_coach_user = MagicMock()
    mock_coach_user.telegram_chat_id = "coach_chat_id"

    mock_ut = MagicMock()
    mock_ut.user = mock_coach_user

    mock_event = MagicMock()
    mock_event.id = 1
    mock_event.title = "Training"
    mock_event.event_date = MagicMock()
    mock_event.event_date.strftime.return_value = "2026-04-29"
    mock_event.team_id = 10

    mock_player = MagicMock()
    mock_player.first_name = "John"
    mock_player.last_name = "Doe"

    import bot as _bot
    with patch.object(_bot, "telegram_app") as mock_app:
        mock_app.bot.send_message = AsyncMock()

        mock_db = MagicMock()
        mock_db.get.side_effect = lambda model, pk: {
            (type(mock_event), 1): mock_event,
            (type(mock_player), 5): mock_player,
        }.get((model, pk))

        from models.user_team import UserTeam
        mock_db.query.return_value.filter.return_value.all.return_value = [mock_ut]

        await notify_coaches_via_telegram(
            event_id=1, player_id=5, new_status="absent", db=mock_db
        )

        mock_app.bot.send_message.assert_called_once()
        call_kwargs = mock_app.bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == "coach_chat_id"
        assert "John" in call_kwargs["text"] or "Doe" in call_kwargs["text"]
        assert "absent" in call_kwargs["text"]


@pytest.mark.asyncio
async def test_notify_coaches_skips_when_bot_not_initialized():
    from services.telegram_notifications import notify_coaches_via_telegram
    import bot as _bot
    with patch.object(_bot, "telegram_app", None):
        # Should return without error
        await notify_coaches_via_telegram(event_id=1, player_id=5, new_status="absent", db=MagicMock())
```

- [ ] **Step 2: Run test — verify it fails**

```bash
pytest tests/test_telegram_notifications.py -v
```
Expected: `ModuleNotFoundError: No module named 'services.telegram_notifications'`

- [ ] **Step 3: Implement `services/telegram_notifications.py`**

```python
# services/telegram_notifications.py
"""services/telegram_notifications.py — Telegram notifications for attendance changes."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


async def notify_coaches_via_telegram(
    event_id: int,
    player_id: int,
    new_status: str,
    db: Session,
) -> None:
    """Send Telegram message to all coaches/admins of the event's team when a player changes status."""
    import bot as _bot  # noqa: PLC0415

    if _bot.telegram_app is None:
        return

    from models.event import Event  # noqa: PLC0415
    from models.player import Player  # noqa: PLC0415
    from models.user_team import UserTeam  # noqa: PLC0415

    event = db.get(Event, event_id)
    if event is None:
        return
    player = db.get(Player, player_id)
    if player is None:
        return

    player_name = f"{player.first_name} {player.last_name}".strip() or f"Player {player_id}"
    date_str = event.event_date.strftime("%d %b") if event.event_date else ""
    text = f"📋 {player_name} → {new_status}\n{event.title} · {date_str}"

    coaches = (
        db.query(UserTeam)
        .filter(UserTeam.team_id == event.team_id)
        .all()
    )
    sent_chat_ids: set[str] = set()
    for ut in coaches:
        if ut.user and ut.user.telegram_chat_id and ut.user.telegram_chat_id not in sent_chat_ids:
            try:
                await _bot.telegram_app.bot.send_message(
                    chat_id=ut.user.telegram_chat_id,
                    text=text,
                )
                sent_chat_ids.add(ut.user.telegram_chat_id)
            except Exception as exc:
                logger.warning(
                    "notify_coaches_via_telegram: failed for user %s: %s",
                    ut.user_id, exc,
                )
```

- [ ] **Step 4: Wire into `routes/attendance.py`**

In `update_attendance()`, the handler already captures `old_status` and has a block that runs `if old_status != status:`. After the existing `log_action(...)` call in that block, add:

```python
        # Notify coaches via Telegram when a player changes their attendance
        from services.telegram_notifications import notify_coaches_via_telegram  # noqa: PLC0415
        background_tasks.add_task(notify_coaches_via_telegram, event_id, player_id, status, db)
```

This requires adding `background_tasks: BackgroundTasks` to the `update_attendance` function signature. Add it after `request: Request`:

```python
async def update_attendance(
    event_id: int,
    player_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    status: str = Form(...),
    note: str = Form(""),
    user: User = Depends(require_login),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
```

Verify `BackgroundTasks` is imported in `routes/attendance.py`. If not, add:
```python
from fastapi import BackgroundTasks
```

**Important:** The `notify_coaches_via_telegram` function is `async` and needs an open DB session. However, since `db` (the request-scoped session) will be closed before the background task runs, pass `db` directly only works here because FastAPI keeps the session open until the response is sent. For safety, change the call to open a fresh session inside the background task by creating a sync wrapper:

Replace the background task call with a direct call passing IDs only. Update `services/telegram_notifications.py` to open its own session:

```python
# Replace the signature to not take db:
async def notify_coaches_via_telegram(
    event_id: int,
    player_id: int,
    new_status: str,
) -> None:
    import bot as _bot  # noqa: PLC0415
    if _bot.telegram_app is None:
        return

    import app.database as _db_mod  # noqa: PLC0415
    from models.event import Event  # noqa: PLC0415
    from models.player import Player  # noqa: PLC0415
    from models.user_team import UserTeam  # noqa: PLC0415

    db = _db_mod.SessionLocal()
    try:
        event = db.get(Event, event_id)
        if event is None:
            return
        player = db.get(Player, player_id)
        if player is None:
            return

        player_name = f"{player.first_name} {player.last_name}".strip() or f"Player {player_id}"
        date_str = event.event_date.strftime("%d %b") if event.event_date else ""
        text = f"📋 {player_name} → {new_status}\n{event.title} · {date_str}"

        coaches = db.query(UserTeam).filter(UserTeam.team_id == event.team_id).all()
        sent_chat_ids: set[str] = set()
        for ut in coaches:
            if ut.user and ut.user.telegram_chat_id and ut.user.telegram_chat_id not in sent_chat_ids:
                try:
                    await _bot.telegram_app.bot.send_message(
                        chat_id=ut.user.telegram_chat_id,
                        text=text,
                    )
                    sent_chat_ids.add(ut.user.telegram_chat_id)
                except Exception as exc:
                    logger.warning(
                        "notify_coaches_via_telegram: failed for user %s: %s",
                        ut.user_id, exc,
                    )
    finally:
        db.close()
```

And in `routes/attendance.py`:
```python
background_tasks.add_task(notify_coaches_via_telegram, event_id, player_id, status)
```

Update the test in `tests/test_telegram_notifications.py` to match the new signature (no `db` param — opens own session). Patch `app.database.SessionLocal` instead:

```python
@pytest.mark.asyncio
async def test_notify_coaches_sends_to_coaches_with_telegram():
    from services.telegram_notifications import notify_coaches_via_telegram

    mock_coach_user = MagicMock()
    mock_coach_user.telegram_chat_id = "coach_chat_id"
    mock_ut = MagicMock()
    mock_ut.user = mock_coach_user

    mock_event = MagicMock()
    mock_event.id = 1
    mock_event.title = "Training"
    mock_event.event_date = MagicMock()
    mock_event.event_date.strftime.return_value = "29 Apr"
    mock_event.team_id = 10

    mock_player = MagicMock()
    mock_player.first_name = "John"
    mock_player.last_name = "Doe"

    mock_db = MagicMock()
    mock_db.__enter__ = MagicMock(return_value=mock_db)
    mock_db.__exit__ = MagicMock(return_value=False)
    mock_db.get.side_effect = lambda model, pk: mock_event if pk == 1 else mock_player
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_ut]

    import bot as _bot
    import app.database as _db_mod
    with (
        patch.object(_bot, "telegram_app") as mock_app,
        patch.object(_db_mod, "SessionLocal", return_value=mock_db),
    ):
        mock_app.bot.send_message = AsyncMock()
        await notify_coaches_via_telegram(event_id=1, player_id=5, new_status="absent")
        mock_app.bot.send_message.assert_called_once()
        call_kwargs = mock_app.bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == "coach_chat_id"
        assert "John" in call_kwargs["text"]
        assert "absent" in call_kwargs["text"]


@pytest.mark.asyncio
async def test_notify_coaches_skips_when_bot_not_initialized():
    from services.telegram_notifications import notify_coaches_via_telegram
    import bot as _bot
    with patch.object(_bot, "telegram_app", None):
        await notify_coaches_via_telegram(event_id=1, player_id=5, new_status="absent")
        # no error raised
```

- [ ] **Step 5: Run all tests**

```bash
pytest tests/ -v -x -q
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add services/telegram_notifications.py routes/attendance.py tests/test_telegram_notifications.py
git commit -m "feat: notify coaches via Telegram when player changes attendance status"
```

---

## Verification (end-to-end)

After all tasks complete:

1. `pytest -v` — all tests pass
2. `ruff check .` — no lint errors
3. Configure `TELEGRAM_BOT_TOKEN` in `.env`, link a test user via bot `/start`
4. Create event with "Notify team" checked → Telegram message received with `evt:` and `evts:0` buttons
5. Tap "📅 This event" → event detail opens in bot
6. Tap "📋 All events" → upcoming events list shown
7. Edit event with "Notify team about this update" checked → Telegram message with ✏️ prefix
8. Trigger send-reminders → Telegram reminder received with player's attendance status
9. Update attendance as player → coach receives `📋 Player → absent` Telegram message
10. Disable telegram in notification preferences → no Telegram sent for triggers 1–3 (coaches-only trigger 4 bypasses preferences by design)
11. Player with no Telegram linked → silently skipped, no errors in logs
