# Notifications System — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-channel (email, in-app, web push) notifications to ProManager, triggered manually by admins from event pages, with per-player channel preferences and a real-time in-app inbox.

**Architecture:** Three SQLAlchemy models (`Notification`, `NotificationPreference`, `WebPushSubscription`) back a `NotificationService` that dispatches through pluggable channel classes (`EmailChannel`, `InAppChannel`, `WebPushChannel`). Real-time delivery uses Server-Sent Events with a module-level asyncio queue registry. Notification templates are centralised in `services/notification_templates.py` in an i18n-ready structure (extracted strings, keyed by template ID) so the i18n sub-project can swap them for translated catalogs without touching route or service code.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Jinja2, SQLite, Alembic, pywebpush~=2.0, pytest + httpx TestClient.

**Spec:** `docs/superpowers/specs/2026-03-13-notifications-design.md`

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Modify | `app/config.py` | Add VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT settings |
| Modify | `app/main.py` | Extract `_get_user_from_cookie` → `app/session.py`; update AuthMiddleware to set `request.state.unread_count` |
| Create | `app/session.py` | Shared session/cookie helper (moved from main.py) |
| Create | `models/notification.py` | Notification ORM model |
| Create | `models/notification_preference.py` | Per-player channel opt-in |
| Create | `models/web_push_subscription.py` | Browser push subscriptions |
| Modify | `models/player.py` | Add `notifications`, `notification_preferences`, `web_push_subscriptions` relationships |
| Modify | `models/event.py` | Add `notifications` relationship |
| Modify | `models/__init__.py` | Export three new models |
| Create | `alembic/versions/notif_add_notifications.py` | Migration for all three tables |
| Create | `services/notification_templates.py` | Fixed system templates (i18n-ready structure) |
| Create | `services/channels/__init__.py` | Channel package |
| Create | `services/channels/email_channel.py` | Email channel |
| Create | `services/channels/inapp_channel.py` | In-app channel + SSE connection registry |
| Create | `services/channels/webpush_channel.py` | Web Push channel |
| Create | `services/notification_service.py` | Dispatch orchestration + preference creation |
| Create | `routes/notifications.py` | Inbox, SSE stream, mark-read, webpush subscribe/unsubscribe, VAPID key |
| Modify | `routes/events.py` | Add GET/POST `/events/{id}/notify` |
| Modify | `app/main.py` | Register notifications router |
| Create | `templates/notifications/inbox.html` | Notification inbox page |
| Create | `templates/events/notify.html` | Admin send form |
| Modify | `templates/base.html` | Notification bell in nav |
| Modify | `templates/players/profile.html` | Notification preferences section |
| Create | `static/js/sw.js` | Service worker for Web Push |
| Create | `scripts/generate_vapid.py` | One-time VAPID key generation |
| Create | `tests/test_notifications.py` | Service + route tests |

---

## Chunk 1: Foundation — Config, Session Helper, Models, Migration

### Task 1: Add VAPID settings to `app/config.py`

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: Add VAPID fields to `Settings`**

In `app/config.py`, add after the `COOKIE_SECURE` field:

```python
# ── Web Push (VAPID) ──────────────────────────────────────────────────────
# Generate with: python scripts/generate_vapid.py
VAPID_PUBLIC_KEY: str = ""
VAPID_PRIVATE_KEY: str = ""
# Must be a mailto: or https: URI — required by the Web Push protocol
VAPID_SUBJECT: str = "mailto:admin@promanager.local"
```

- [ ] **Step 2: Add VAPID keys to `.env.example`**

Append to `.env.example`:

```
# Web Push (VAPID) — generate with: python scripts/generate_vapid.py
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
VAPID_SUBJECT=mailto:admin@example.com
```

- [ ] **Step 3: Commit**

```bash
git add app/config.py .env.example
git commit -m "feat: add VAPID config fields for Web Push"
```

---

### Task 2: Extract session helper to `app/session.py`

**Files:**
- Create: `app/session.py`
- Modify: `app/main.py`

`_get_user_from_cookie` is currently a private function in `app/main.py`. Moving it to `app/session.py` lets `routes/notifications.py` (SSE route) import it without a circular dependency.

- [ ] **Step 1: Create `app/session.py`**

```python
"""app/session.py — Session cookie helpers shared across the app."""
from __future__ import annotations

from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

import app.database as _db_mod
from app.config import settings

COOKIE_NAME = "session_user_id"
_signer = TimestampSigner(settings.SECRET_KEY)


def get_user_from_cookie(request: Request):
    """Return the User ORM object for the signed session cookie, or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        raw: bytes = _signer.unsign(token, max_age=60 * 60 * 24 * 7)  # 7 days
        user_id = int(raw.decode())
    except (BadSignature, SignatureExpired, ValueError):
        return None

    from models.user import User  # noqa: PLC0415

    db = _db_mod.SessionLocal()
    try:
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            return None
        return user
    finally:
        db.close()
```

- [ ] **Step 2: Update `app/main.py` to use `app/session.py`**

Replace the private `COOKIE_NAME`, `_signer`, and `_get_user_from_cookie` definitions in `app/main.py` with an import:

```python
from app.session import COOKIE_NAME, get_user_from_cookie as _get_user_from_cookie
```

Remove the old `COOKIE_NAME = "session_user_id"`, `_signer = ...` and `def _get_user_from_cookie(...)` from `app/main.py`.

- [ ] **Step 3: Run tests to confirm nothing broke**

```bash
.venv/bin/pytest -x -q
```

Expected: all 96 tests pass.

- [ ] **Step 4: Commit**

```bash
git add app/session.py app/main.py
git commit -m "refactor: extract session helper to app/session.py"
```

---

### Task 3: Create the three new models

**Files:**
- Create: `models/notification.py`
- Create: `models/notification_preference.py`
- Create: `models/web_push_subscription.py`
- Modify: `models/player.py`
- Modify: `models/event.py`
- Modify: `models/__init__.py`

- [ ] **Step 1: Create `models/notification.py`**

```python
"""models/notification.py — Per-player notification record."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # "direct" | "announcement"
    tag: Mapped[str] = mapped_column(String(32), nullable=False, default="direct")
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    # ── Relationships ──────────────────────────────────────────────────────
    # Use string references — SQLAlchemy resolves them lazily.
    # from __future__ import annotations means the Mapped[] annotations are
    # also strings at runtime, so no circular import occurs.
    player: Mapped[Player] = relationship("Player", back_populates="notifications")
    event: Mapped[Event | None] = relationship("Event", back_populates="notifications")
```

- [ ] **Step 2: Create `models/notification_preference.py`**

```python
"""models/notification_preference.py — Per-player, per-channel opt-in."""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

CHANNELS = ("email", "inapp", "webpush")


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (UniqueConstraint("player_id", "channel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "email" | "inapp" | "webpush"
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    player: Mapped[Player] = relationship(
        "Player", back_populates="notification_preferences"
    )
```

- [ ] **Step 3: Create `models/web_push_subscription.py`**

```python
"""models/web_push_subscription.py — Browser push subscription per device."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WebPushSubscription(Base):
    __tablename__ = "web_push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    p256dh_key: Mapped[str] = mapped_column(String(256), nullable=False)
    auth_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    player: Mapped[Player] = relationship(
        "Player", back_populates="web_push_subscriptions"
    )
```

- [ ] **Step 4: Add relationships to `models/player.py`**

At the end of the `Player` class's relationship section (after `contact`), add:

```python
    notifications: Mapped[list[Notification]] = relationship(
        "Notification",
        back_populates="player",
        cascade="all, delete-orphan",
        lazy="select",
    )
    notification_preferences: Mapped[list[NotificationPreference]] = relationship(
        "NotificationPreference",
        back_populates="player",
        cascade="all, delete-orphan",
        lazy="select",
    )
    web_push_subscriptions: Mapped[list[WebPushSubscription]] = relationship(
        "WebPushSubscription",
        back_populates="player",
        cascade="all, delete-orphan",
        lazy="select",
    )
```

**Do NOT add bottom-of-file imports for Notification/NotificationPreference/WebPushSubscription.**
The string arguments in `relationship("Notification", ...)` are resolved lazily by SQLAlchemy.
The `Mapped[list[Notification]]` type annotations are deferred strings at runtime because of
`from __future__ import annotations` at the top of the file. No runtime import is needed.

- [ ] **Step 5: Add `notifications` relationship to `models/event.py`**

At the end of `Event`'s relationships, add:

```python
    notifications: Mapped[list[Notification]] = relationship(
        "Notification",
        back_populates="event",
        cascade="save-update, merge",  # NOT delete-orphan — DB uses ondelete="SET NULL"
        lazy="select",
    )
```

**Do NOT add a bottom-of-file import for Notification.** Same reasoning as player.py above —
string relationship references + `from __future__ import annotations` handles this without
any runtime cross-model import.

- [ ] **Step 6: Export new models from `models/__init__.py`**

Add to `models/__init__.py`:

```python
from models.notification import Notification as Notification  # noqa: F401
from models.notification_preference import NotificationPreference as NotificationPreference  # noqa: F401
from models.web_push_subscription import WebPushSubscription as WebPushSubscription  # noqa: F401
```

- [ ] **Step 7: Run tests to confirm models load correctly**

```bash
.venv/bin/pytest -x -q
```

Expected: all 96 tests pass.

- [ ] **Step 8: Commit**

```bash
git add models/notification.py models/notification_preference.py \
        models/web_push_subscription.py models/player.py models/event.py \
        models/__init__.py
git commit -m "feat: add Notification, NotificationPreference, WebPushSubscription models"
```

---

### Task 4: Alembic migration

**Files:**
- Create: `alembic/versions/notif_add_notifications.py`

- [ ] **Step 1: Generate migration**

```bash
.venv/bin/alembic revision --autogenerate -m "add_notifications"
```

This generates a file in `alembic/versions/`. Rename it to `notif_add_notifications.py` for clarity if desired. Inspect it — confirm it creates `notifications`, `notification_preferences`, and `web_push_subscriptions` tables. Verify `ondelete` clauses and the `UniqueConstraint` on `notification_preferences` appear correctly.

- [ ] **Step 2: Apply migration**

```bash
.venv/bin/alembic upgrade head
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add alembic/versions/
git commit -m "feat: migration — add notifications, notification_preferences, web_push_subscriptions tables"
```

---

## Chunk 2: Service Layer — Channels, Templates, NotificationService

### Task 5: Notification templates (i18n-ready)

**Files:**
- Create: `services/notification_templates.py`

Templates are stored as a list of structured dicts. Each entry has a `key` (machine ID), `name` (display name), `tag`, `title_tpl`, and `body_tpl`. Placeholders use `{event}`, `{date}`, `{time}`, `{location}`, `{new_location}`, `{new_time}`. When the i18n sub-project runs, `title_tpl` and `body_tpl` values become translation keys, and this module becomes the single place to replace them.

- [ ] **Step 1: Create `services/notification_templates.py`**

```python
"""services/notification_templates.py — Fixed system notification templates.

Templates are i18n-ready: title_tpl and body_tpl are plain strings today.
When the i18n sub-project is implemented, replace them with translation-key
lookups (e.g. gettext / fluent) without changing callers.

Placeholders: {event}, {date}, {time}, {location}, {new_location}, {new_time}
"""
from __future__ import annotations

from typing import TypedDict


class NotificationTemplate(TypedDict):
    key: str          # machine identifier
    name: str         # human-readable name shown in the dropdown
    tag: str          # "direct" | "announcement"
    tag_locked: bool  # if True, admin cannot change the tag
    title_tpl: str    # title template with {placeholder} syntax
    body_tpl: str     # body template with {placeholder} syntax


TEMPLATES: list[NotificationTemplate] = [
    {
        "key": "event_reminder",
        "name": "Event Reminder",
        "tag": "direct",
        "tag_locked": True,
        "title_tpl": "Reminder: {event} on {date}",
        "body_tpl": (
            "Don't forget: {event} is on {date} at {time} at {location}. "
            "Please confirm your attendance."
        ),
    },
    {
        "key": "cancellation",
        "name": "Cancellation",
        "tag": "announcement",
        "tag_locked": True,
        "title_tpl": "{event} cancelled",
        "body_tpl": "{event} scheduled for {date} has been cancelled.",
    },
    {
        "key": "venue_change",
        "name": "Venue Change",
        "tag": "announcement",
        "tag_locked": True,
        "title_tpl": "Venue change: {event}",
        "body_tpl": "{event} on {date} has moved to {new_location}.",
    },
    {
        "key": "time_change",
        "name": "Time Change",
        "tag": "announcement",
        "tag_locked": True,
        "title_tpl": "Time change: {event}",
        "body_tpl": "{event} on {date} has been rescheduled to {new_time}.",
    },
    {
        "key": "attendance_request",
        "name": "Attendance Request",
        "tag": "direct",
        "tag_locked": True,
        "title_tpl": "Please confirm: {event}",
        "body_tpl": "Please confirm your attendance for {event} on {date}.",
    },
    {
        "key": "general_announcement",
        "name": "General Announcement",
        "tag": "announcement",
        "tag_locked": False,  # admin can switch to direct
        "title_tpl": "",      # free text — admin fills in
        "body_tpl": "",
    },
    {
        "key": "training_cancelled",
        "name": "Training Cancelled",
        "tag": "announcement",
        "tag_locked": True,
        "title_tpl": "Training cancelled: {date}",
        "body_tpl": "Training on {date} is cancelled.",
    },
    {
        "key": "match_result",
        "name": "Match Result",
        "tag": "announcement",
        "tag_locked": True,
        "title_tpl": "Result: {event}",
        "body_tpl": "",  # admin adds score/summary
    },
]

# Lookup by key for O(1) access
TEMPLATES_BY_KEY: dict[str, NotificationTemplate] = {t["key"]: t for t in TEMPLATES}


def render_template(key: str, context: dict[str, str]) -> tuple[str, str]:
    """Return (title, body) with placeholders substituted from *context*.

    Unknown placeholders are left as-is.
    """
    tpl = TEMPLATES_BY_KEY.get(key)
    if tpl is None:
        return "", ""
    title = tpl["title_tpl"].format_map(_SafeDict(context))
    body = tpl["body_tpl"].format_map(_SafeDict(context))
    return title, body


class _SafeDict(dict):
    """Return the key wrapped in braces for missing keys."""
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
```

- [ ] **Step 2: Write tests**

Create `tests/test_notification_templates.py`:

```python
"""Tests for services/notification_templates.py."""
from services.notification_templates import TEMPLATES, TEMPLATES_BY_KEY, render_template


def test_all_templates_have_required_keys():
    for t in TEMPLATES:
        assert "key" in t
        assert "name" in t
        assert "tag" in t and t["tag"] in ("direct", "announcement")
        assert "tag_locked" in t
        assert "title_tpl" in t
        assert "body_tpl" in t


def test_templates_by_key_covers_all():
    assert len(TEMPLATES_BY_KEY) == len(TEMPLATES)


def test_render_event_reminder():
    title, body = render_template(
        "event_reminder",
        {"event": "Match", "date": "2026-03-20", "time": "18:00", "location": "Gym"},
    )
    assert "Match" in title
    assert "2026-03-20" in title
    assert "Match" in body
    assert "18:00" in body
    assert "Gym" in body


def test_render_unknown_key_returns_empty():
    title, body = render_template("nonexistent", {})
    assert title == ""
    assert body == ""


def test_render_missing_placeholder_left_in_place():
    title, body = render_template("event_reminder", {})
    assert "{event}" in title


def test_general_announcement_tag_not_locked():
    tpl = TEMPLATES_BY_KEY["general_announcement"]
    assert tpl["tag_locked"] is False
```

- [ ] **Step 3: Run tests**

```bash
.venv/bin/pytest tests/test_notification_templates.py -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add services/notification_templates.py tests/test_notification_templates.py
git commit -m "feat: add i18n-ready notification templates service"
```

---

### Task 6: Channel implementations

**Files:**
- Create: `services/channels/__init__.py`
- Create: `services/channels/email_channel.py`
- Create: `services/channels/inapp_channel.py`
- Create: `services/channels/webpush_channel.py`

- [ ] **Step 1: Create `services/channels/__init__.py`**

```python
"""services/channels — pluggable notification channel implementations."""
```

- [ ] **Step 2: Create `services/channels/email_channel.py`**

```python
"""services/channels/email_channel.py — Email notification channel."""
from __future__ import annotations

import logging

from models.notification import Notification
from models.player import Player
from services.email_service import send_email

logger = logging.getLogger(__name__)


class EmailChannel:
    """Sends a notification via email using the existing email_service."""

    def send(self, player: Player, notification: Notification) -> bool:
        if not player.email:
            logger.debug("EmailChannel: player %s has no email, skipping", player.id)
            return False
        subject = notification.title
        body_text = notification.body
        body_html = (
            f"<p>{notification.body.replace(chr(10), '<br>')}</p>"
            f"<p><small>Tag: {notification.tag}</small></p>"
        )
        ok = send_email(player.email, subject, body_html, body_text)
        if not ok:
            logger.warning(
                "EmailChannel: failed to send to player %s (%s)", player.id, player.email
            )
        return ok
```

- [ ] **Step 3: Create `services/channels/inapp_channel.py`**

```python
"""services/channels/inapp_channel.py — In-app channel + SSE connection registry.

The SSE registry is a module-level dict keyed by player_id.
Each connected browser tab has its own asyncio.Queue.

Constraint: in-process only — does not work with multiple Uvicorn workers.
ProManager must run with --workers 1 (enforced by SQLite anyway).
"""
from __future__ import annotations

import asyncio
import json
import logging

from models.notification import Notification
from models.player import Player

logger = logging.getLogger(__name__)

# player_id → list of queues (one per open browser tab/connection)
_connections: dict[int, list[asyncio.Queue]] = {}


def register_connection(player_id: int) -> asyncio.Queue:
    """Create and register a new SSE queue for *player_id*. Call on connect."""
    q: asyncio.Queue = asyncio.Queue()
    _connections.setdefault(player_id, []).append(q)
    logger.debug("SSE: registered connection for player %s (%d total)",
                 player_id, len(_connections[player_id]))
    return q


def unregister_connection(player_id: int, q: asyncio.Queue) -> None:
    """Remove the queue when the SSE connection closes."""
    queues = _connections.get(player_id, [])
    try:
        queues.remove(q)
    except ValueError:
        pass
    if not queues:
        _connections.pop(player_id, None)
    logger.debug("SSE: unregistered connection for player %s", player_id)


def push_unread_count(player_id: int, unread_count: int) -> None:
    """Push an unread-count update to all connected tabs for *player_id*.

    Safe to call from sync context (puts items into thread-safe queues).
    If the player has no open connection the event is silently dropped —
    the badge will update on next page load via the middleware-embedded count.
    """
    queues = _connections.get(player_id, [])
    payload = json.dumps({"unread_count": unread_count})
    for q in queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for player %s — dropping event", player_id)


class InAppChannel:
    """Signals the SSE stream for connected players."""

    def send(self, player: Player, notification: Notification, unread_count: int) -> bool:
        push_unread_count(player.id, unread_count)
        return True
```

- [ ] **Step 4: Create `services/channels/webpush_channel.py`**

```python
"""services/channels/webpush_channel.py — Web Push notification channel."""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.config import settings
from models.notification import Notification
from models.player import Player
from models.web_push_subscription import WebPushSubscription

logger = logging.getLogger(__name__)


def _is_configured() -> bool:
    return bool(settings.VAPID_PRIVATE_KEY and settings.VAPID_PUBLIC_KEY)


class WebPushChannel:
    """Sends browser push notifications via pywebpush."""

    def send(self, player: Player, notification: Notification, db: Session) -> bool:
        if not _is_configured():
            logger.debug("WebPushChannel: VAPID not configured, skipping")
            return False

        try:
            from pywebpush import webpush, WebPushException  # noqa: PLC0415
        except ImportError:
            logger.warning("pywebpush not installed — Web Push unavailable")
            return False

        subscriptions = (
            db.query(WebPushSubscription)
            .filter(WebPushSubscription.player_id == player.id)
            .all()
        )
        if not subscriptions:
            return False

        payload = json.dumps({"title": notification.title, "body": notification.body})
        vapid_claims = {"sub": settings.VAPID_SUBJECT}
        sent = False

        to_delete = []
        for sub in subscriptions:
            subscription_info = {
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh_key, "auth": sub.auth_key},
            }
            try:
                webpush(
                    subscription_info=subscription_info,
                    data=payload,
                    vapid_private_key=settings.VAPID_PRIVATE_KEY,
                    vapid_claims=vapid_claims,
                )
                sent = True
            except Exception as exc:
                # Intentionally broad catch — pywebpush raises WebPushException
                # (subclass of Exception) for push failures. We check for HTTP
                # 410 Gone, which means the subscription is expired/revoked.
                # WebPushException.response is a requests.Response with .status_code.
                # Other exceptions (network errors, etc.) are logged and skipped.
                is_gone = hasattr(exc, "response") and getattr(
                    exc.response, "status_code", None
                ) == 410
                if is_gone:
                    logger.info(
                        "WebPushChannel: removing expired subscription %s", sub.id
                    )
                    to_delete.append(sub)
                else:
                    logger.warning(
                        "WebPushChannel: push failed for sub %s: %s", sub.id, exc
                    )

        for sub in to_delete:
            db.delete(sub)
        if to_delete:
            db.commit()

        return sent
```

- [ ] **Step 5: Commit**

```bash
git add services/channels/
git commit -m "feat: add email, in-app, and web push channel implementations"
```

---

### Task 7: `NotificationService`

**Files:**
- Create: `services/notification_service.py`
- Create: `tests/test_notification_service.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_notification_service.py`:

```python
"""Tests for services/notification_service.py."""
from __future__ import annotations

import pytest
from models.notification import Notification
from models.notification_preference import NotificationPreference, CHANNELS
from models.player import Player
from models.team import Team
from models.event import Event
from models.season import Season
from models.attendance import Attendance
from services.notification_service import (
    create_default_preferences,
    get_preference,
    send_notifications,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def season(db):
    s = Season(name="2026", is_active=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@pytest.fixture()
def team(db, season):
    t = Team(name="Eagles", season_id=season.id)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


@pytest.fixture()
def player(db, team):
    from models.player_team import PlayerTeam
    p = Player(first_name="Alice", last_name="Smith", email="alice@test.com",
               is_active=True)
    db.add(p)
    db.flush()
    # _resolve_players joins via PlayerTeam — must exist for team-scoped queries
    db.add(PlayerTeam(
        player_id=p.id, team_id=team.id, priority=1,
        role="player", membership_status="active", absent_by_default=False,
    ))
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture()
def event(db, season, team):
    e = Event(title="Match", event_type="match", event_date="2026-04-01",
              season_id=season.id, team_id=team.id)
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


# ── create_default_preferences ────────────────────────────────────────────────

def test_create_default_preferences_creates_all_channels(db, player):
    create_default_preferences(player.id, db)
    prefs = db.query(NotificationPreference).filter(
        NotificationPreference.player_id == player.id
    ).all()
    assert {p.channel for p in prefs} == set(CHANNELS)
    assert all(p.enabled for p in prefs)


def test_create_default_preferences_idempotent(db, player):
    create_default_preferences(player.id, db)
    create_default_preferences(player.id, db)  # second call must not raise
    prefs = db.query(NotificationPreference).filter(
        NotificationPreference.player_id == player.id
    ).all()
    assert len(prefs) == len(CHANNELS)


# ── get_preference ─────────────────────────────────────────────────────────────

def test_get_preference_returns_true_when_enabled(db, player):
    create_default_preferences(player.id, db)
    assert get_preference(player.id, "email", db) is True


def test_get_preference_returns_true_when_missing(db, player):
    # No preferences created — defaults to True
    assert get_preference(player.id, "email", db) is True


def test_get_preference_returns_false_when_disabled(db, player):
    create_default_preferences(player.id, db)
    pref = db.query(NotificationPreference).filter(
        NotificationPreference.player_id == player.id,
        NotificationPreference.channel == "email",
    ).one()
    pref.enabled = False
    db.commit()
    assert get_preference(player.id, "email", db) is False


# ── send_notifications ────────────────────────────────────────────────────────

def test_send_creates_notification_rows(db, player, event):
    create_default_preferences(player.id, db)
    result = send_notifications(
        event=event,
        title="Test",
        body="Body",
        tag="direct",
        recipient_statuses=None,  # all
        admin_channels=["inapp"],
        db=db,
        background_tasks=None,
    )
    assert result["queued"] >= 1
    # _dispatch opens its own session — expire the test session to see committed rows
    db.expire_all()
    notifs = db.query(Notification).filter(Notification.player_id == player.id).all()
    assert len(notifs) == 1
    assert notifs[0].title == "Test"
    assert notifs[0].tag == "direct"


def test_send_skips_disabled_channel(db, player, event):
    create_default_preferences(player.id, db)
    # Disable inapp for player
    pref = db.query(NotificationPreference).filter(
        NotificationPreference.player_id == player.id,
        NotificationPreference.channel == "inapp",
    ).one()
    pref.enabled = False
    db.commit()

    result = send_notifications(
        event=event,
        title="Test",
        body="Body",
        tag="direct",
        recipient_statuses=None,
        admin_channels=["inapp"],
        db=db,
        background_tasks=None,
    )
    # Notification row is still created (for inbox persistence) even if channel skipped
    db.expire_all()
    notifs = db.query(Notification).filter(Notification.player_id == player.id).all()
    assert len(notifs) == 1
    assert result["queued"] == 1


def test_send_filters_by_attendance_status(db, player, event):
    create_default_preferences(player.id, db)
    # Give player an "absent" attendance record
    att = Attendance(event_id=event.id, player_id=player.id, status="absent")
    db.add(att)
    db.commit()

    # Only target "present" players — player should be excluded
    result = send_notifications(
        event=event,
        title="Test",
        body="Body",
        tag="direct",
        recipient_statuses=["present"],
        admin_channels=["inapp"],
        db=db,
        background_tasks=None,
    )
    assert result["queued"] == 0
    db.expire_all()
    notifs = db.query(Notification).filter(Notification.player_id == player.id).all()
    assert len(notifs) == 0


def test_send_event_without_team_targets_active_players(db, event, player):
    """When event has no team, all active players receive the notification."""
    event.team_id = None
    db.commit()
    create_default_preferences(player.id, db)

    result = send_notifications(
        event=event,
        title="Test",
        body="Body",
        tag="announcement",
        recipient_statuses=None,
        admin_channels=["inapp"],
        db=db,
        background_tasks=None,
    )
    assert result["queued"] >= 1
```

- [ ] **Step 2: Run to confirm they fail**

```bash
.venv/bin/pytest tests/test_notification_service.py -v 2>&1 | head -20
```

Expected: `ImportError` or `ModuleNotFoundError`.

- [ ] **Step 3: Create `services/notification_service.py`**

```python
"""services/notification_service.py — Notification dispatch orchestration."""
from __future__ import annotations

import logging
from typing import Sequence

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from models.attendance import Attendance
from models.notification import Notification
from models.notification_preference import CHANNELS, NotificationPreference
from models.player import Player
from services.channels.email_channel import EmailChannel
from services.channels.inapp_channel import InAppChannel

logger = logging.getLogger(__name__)

_email_channel = EmailChannel()
_inapp_channel = InAppChannel()


# ── Preference helpers ────────────────────────────────────────────────────────

def create_default_preferences(player_id: int, db: Session) -> None:
    """Create enabled preferences for all channels if they don't exist."""
    for channel in CHANNELS:
        existing = (
            db.query(NotificationPreference)
            .filter(
                NotificationPreference.player_id == player_id,
                NotificationPreference.channel == channel,
            )
            .first()
        )
        if existing is None:
            db.add(NotificationPreference(player_id=player_id, channel=channel, enabled=True))
    db.commit()


def get_preference(player_id: int, channel: str, db: Session) -> bool:
    """Return True if the player has the channel enabled (defaults to True if missing)."""
    pref = (
        db.query(NotificationPreference)
        .filter(
            NotificationPreference.player_id == player_id,
            NotificationPreference.channel == channel,
        )
        .first()
    )
    return pref.enabled if pref is not None else True


# ── Recipient resolution ──────────────────────────────────────────────────────

def _resolve_players(event, recipient_statuses: list[str] | None, db: Session) -> list[Player]:
    """Return the list of players to notify."""
    if event.team_id is not None:
        from models.player_team import PlayerTeam  # noqa: PLC0415
        base_q = (
            db.query(Player)
            .join(PlayerTeam, PlayerTeam.player_id == Player.id)
            .filter(
                PlayerTeam.team_id == event.team_id,
                PlayerTeam.membership_status == "active",
                Player.is_active.is_(True),
            )
        )
    else:
        base_q = db.query(Player).filter(Player.is_active.is_(True))

    if not recipient_statuses:
        return base_q.all()

    # Filter by attendance status
    player_ids_with_status = (
        db.query(Attendance.player_id)
        .filter(
            Attendance.event_id == event.id,
            Attendance.status.in_(recipient_statuses),
        )
        .subquery()
    )
    return base_q.filter(Player.id.in_(player_ids_with_status)).all()


# ── Core dispatch ─────────────────────────────────────────────────────────────

def _dispatch(
    player_ids: list[int],
    event_id: int | None,
    title: str,
    body: str,
    tag: str,
    admin_channels: list[str],
) -> int:
    """Create notification rows and dispatch to channels. Opens its own DB session.

    Called either synchronously (tests) or as a FastAPI BackgroundTask.
    Never receives a request-scoped session — those are closed before
    background tasks run.
    """
    from services.channels.webpush_channel import WebPushChannel  # noqa: PLC0415
    import app.database as _db_mod  # noqa: PLC0415
    _webpush_channel = WebPushChannel()

    db = _db_mod.SessionLocal()
    try:
        queued = 0
        for player_id in player_ids:
            player = db.get(Player, player_id)
            if player is None:
                continue

            notif = Notification(
                player_id=player.id,
                event_id=event_id,
                title=title,
                body=body,
                tag=tag,
            )
            db.add(notif)
            db.flush()

            # Count unread for SSE badge
            unread = (
                db.query(Notification)
                .filter(
                    Notification.player_id == player.id,
                    Notification.is_read.is_(False),
                )
                .count()
            )

            if "inapp" in admin_channels and get_preference(player.id, "inapp", db):
                _inapp_channel.send(player, notif, unread_count=unread)

            if "email" in admin_channels and get_preference(player.id, "email", db):
                _email_channel.send(player, notif)

            if "webpush" in admin_channels and get_preference(player.id, "webpush", db):
                _webpush_channel.send(player, notif, db=db)

            queued += 1

        db.commit()
        return queued
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def send_notifications(
    *,
    event,
    title: str,
    body: str,
    tag: str,
    recipient_statuses: list[str] | None,
    admin_channels: list[str],
    db: Session,
    background_tasks: BackgroundTasks | None,
) -> dict:
    """Resolve players, then dispatch channels.

    Player IDs are resolved synchronously (within the request session).
    Actual dispatch (_dispatch) always opens its own session — safe whether
    called synchronously (tests, background_tasks=None) or as a BackgroundTask
    (where the request session is already closed).
    """
    players = _resolve_players(event, recipient_statuses, db)
    if not players:
        return {"queued": 0}

    player_ids = [p.id for p in players]
    event_id = event.id if event else None

    if background_tasks is not None:
        background_tasks.add_task(
            _dispatch, player_ids, event_id, title, body, tag, admin_channels
        )
        return {"queued": len(player_ids)}
    else:
        count = _dispatch(player_ids, event_id, title, body, tag, admin_channels)
        return {"queued": count}
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_notification_service.py -v
```

Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/pytest -x -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add services/notification_service.py tests/test_notification_service.py
git commit -m "feat: add NotificationService with channel dispatch and preference management"
```

---

## Chunk 3: Routes — Notifications Router, Events Notify, Middleware

### Task 8: Update `AuthMiddleware` to embed unread count

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Update `AuthMiddleware.dispatch`**

In `app/main.py`, update the `dispatch` method of `AuthMiddleware`:

```python
async def dispatch(self, request: Request, call_next) -> Response:
    user = _get_user_from_cookie(request)
    request.state.user = user
    request.state.csrf_token = generate_csrf_token(
        request.cookies.get(COOKIE_NAME, "")
    )
    # Embed unread notification count for the bell badge
    request.state.unread_count = 0
    if user is not None:
        from models.notification import Notification  # noqa: PLC0415
        from models.player import Player  # noqa: PLC0415
        db = _db_mod.SessionLocal()
        try:
            # Find player(s) linked to this user
            player_ids = [
                pid for (pid,) in db.query(Player.id).filter(
                    Player.user_id == user.id,
                    Player.is_active.is_(True),
                ).all()
            ]
            if player_ids:
                request.state.unread_count = (
                    db.query(Notification)
                    .filter(
                        Notification.player_id.in_(player_ids),
                        Notification.is_read.is_(False),
                    )
                    .count()
                )
        finally:
            db.close()
    response = await call_next(request)
    return response
```

- [ ] **Step 2: Run tests**

```bash
.venv/bin/pytest -x -q
```

Expected: all pass (middleware change is backwards-compatible — `unread_count` defaults to 0).

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: embed unread notification count in request.state via AuthMiddleware"
```

---

### Task 9: Create `routes/notifications.py`

**Files:**
- Create: `routes/notifications.py`
- Create: `tests/test_notification_routes.py`

- [ ] **Step 1: Write failing route tests**

Create `tests/test_notification_routes.py`:

```python
"""Tests for routes/notifications.py."""
from __future__ import annotations

import pytest
from models.notification import Notification
from models.notification_preference import NotificationPreference, CHANNELS
from models.player import Player
from services.auth_service import create_session_cookie, create_user
from services.notification_service import create_default_preferences


@pytest.fixture()
def player_with_user(db):
    user = create_user(db, "puser", "p@test.com", "pass", role="member")
    player = Player(
        first_name="Test", last_name="Player", email="p@test.com",
        user_id=user.id, is_active=True,
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    create_default_preferences(player.id, db)
    return user, player


@pytest.fixture()
def player_client(client, player_with_user):
    user, player = player_with_user
    cookie_val = create_session_cookie(user.id)
    client.cookies.set("session_user_id", cookie_val)
    return client, player


def test_inbox_requires_login(client):
    r = client.get("/notifications")
    assert r.status_code in (302, 401)


def test_inbox_empty(player_client):
    c, player = player_client
    r = c.get("/notifications")
    assert r.status_code == 200
    assert b"notifications" in r.content.lower()


def test_inbox_shows_notification(db, player_client):
    c, player = player_client
    notif = Notification(player_id=player.id, title="Hi", body="Body", tag="direct")
    db.add(notif)
    db.commit()

    r = c.get("/notifications")
    assert r.status_code == 200
    assert b"Hi" in r.content


def test_mark_read(db, player_client):
    c, player = player_client
    notif = Notification(player_id=player.id, title="Hi", body="Body", tag="direct")
    db.add(notif)
    db.commit()

    r = c.post(f"/notifications/{notif.id}/read")
    assert r.status_code in (200, 302)
    db.refresh(notif)
    assert notif.is_read is True


def test_mark_read_all(db, player_client):
    c, player = player_client
    for i in range(3):
        db.add(Notification(player_id=player.id, title=f"N{i}", body="B", tag="direct"))
    db.commit()

    r = c.post("/notifications/read-all")
    assert r.status_code in (200, 302)
    unread = db.query(Notification).filter(
        Notification.player_id == player.id, Notification.is_read.is_(False)
    ).count()
    assert unread == 0


def test_cannot_mark_other_players_notification(db, player_client, admin_user):
    c, player = player_client
    # Create a notification for admin_user (different player — no player linked in this test)
    other_player = Player(first_name="Other", last_name="P", is_active=True)
    db.add(other_player)
    db.commit()
    notif = Notification(player_id=other_player.id, title="Secret", body="B", tag="direct")
    db.add(notif)
    db.commit()

    r = c.post(f"/notifications/{notif.id}/read")
    assert r.status_code in (403, 404, 302)
    db.refresh(notif)
    assert notif.is_read is False


def test_vapid_public_key_endpoint(client):
    r = client.get("/notifications/vapid-public-key")
    assert r.status_code == 200
    data = r.json()
    assert "publicKey" in data


def test_notification_preferences_update(db, player_client):
    c, player = player_client
    r = c.post(
        "/notifications/preferences",
        data={"email": "off", "inapp": "on", "webpush": "off"},
    )
    assert r.status_code in (200, 302)
    email_pref = db.query(NotificationPreference).filter(
        NotificationPreference.player_id == player.id,
        NotificationPreference.channel == "email",
    ).one()
    assert email_pref.enabled is False
```

- [ ] **Step 2: Run to confirm they fail**

```bash
.venv/bin/pytest tests/test_notification_routes.py -v 2>&1 | head -20
```

Expected: `404` or `ImportError`.

- [ ] **Step 3: Create `routes/notifications.py`**

```python
"""routes/notifications.py — In-app inbox, SSE stream, Web Push management."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.csrf import require_csrf
from app.database import get_db
from app.session import get_user_from_cookie
from app.templates import templates
from models.notification import Notification
from models.notification_preference import CHANNELS, NotificationPreference
from models.player import Player
from models.web_push_subscription import WebPushSubscription
from routes._auth_helpers import require_login
from services.channels.inapp_channel import register_connection, unregister_connection
from services.notification_service import create_default_preferences, get_preference

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["notifications"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_linked_players(user, db: Session) -> list[Player]:
    """Return all active Player rows linked to *user*."""
    return (
        db.query(Player)
        .filter(Player.user_id == user.id, Player.is_active.is_(True))
        .all()
    )


def _player_ids_for_user(user, db: Session) -> list[int]:
    return [p.id for p in _get_linked_players(user, db)]


# ── VAPID public key ──────────────────────────────────────────────────────────

@router.get("/vapid-public-key")
async def vapid_public_key():
    """Return the VAPID public key for the browser push subscription flow."""
    return JSONResponse({"publicKey": settings.VAPID_PUBLIC_KEY})


# ── SSE stream ────────────────────────────────────────────────────────────────

@router.get("/stream")
async def notification_stream(request: Request, db: Session = Depends(get_db)):
    """Server-Sent Events stream for real-time notification badge updates.

    Auth is handled inline (not via AuthMiddleware) to avoid BaseHTTPMiddleware
    buffering issues with streaming responses.
    """
    user = get_user_from_cookie(request)
    if user is None:
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    player_ids = _player_ids_for_user(user, db)
    if not player_ids:
        # No linked player — stream keepalives only
        async def keepalive() -> AsyncGenerator[str, None]:
            while True:
                if await request.is_disconnected():
                    break
                yield ": keepalive\n\n"
                await asyncio.sleep(30)
        return StreamingResponse(keepalive(), media_type="text/event-stream")

    # Register SSE for the primary linked player only.
    # If a user has multiple linked players, notifications for non-primary
    # players will not trigger real-time badge updates — they will be visible
    # on next page load via the middleware-embedded unread count.
    # Multi-player SSE registration is deferred as a future improvement.
    player_id = player_ids[0]
    q = register_connection(player_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            unregister_connection(player_id, q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Inbox ─────────────────────────────────────────────────────────────────────

@router.get("")
async def inbox(
    request: Request,
    user=Depends(require_login),
    db: Session = Depends(get_db),
):
    player_ids = _player_ids_for_user(user, db)
    notifications = []
    if player_ids:
        notifications = (
            db.query(Notification)
            .filter(Notification.player_id.in_(player_ids))
            .order_by(Notification.created_at.desc())
            .all()
        )
    return templates.TemplateResponse(
        request,
        "notifications/inbox.html",
        {"user": user, "notifications": notifications},
    )


# ── Mark read ─────────────────────────────────────────────────────────────────

@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int,
    request: Request,
    user=Depends(require_login),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    player_ids = _player_ids_for_user(user, db)
    notif = db.get(Notification, notification_id)
    if notif is None or notif.player_id not in player_ids:
        raise HTTPException(status_code=404)
    notif.is_read = True
    db.commit()
    redirect_url = str(request.headers.get("referer", "/notifications"))
    return RedirectResponse(redirect_url, status_code=302)


@router.post("/read-all")
async def mark_read_all(
    request: Request,
    user=Depends(require_login),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    player_ids = _player_ids_for_user(user, db)
    if player_ids:
        db.query(Notification).filter(
            Notification.player_id.in_(player_ids),
            Notification.is_read.is_(False),
        ).update({"is_read": True}, synchronize_session="fetch")
        db.commit()
    return RedirectResponse("/notifications", status_code=302)


# ── Notification preferences ──────────────────────────────────────────────────

@router.post("/preferences")
async def update_preferences(
    request: Request,
    user=Depends(require_login),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    # require_csrf calls request.form() internally. FastAPI caches the parsed
    # form body on request._form after the first call, so this second call is
    # safe and returns the cached result. Do NOT switch to Form(...) params here
    # because the channel names are dynamic and cannot be declared statically.
    form = await request.form()
    player_ids = _player_ids_for_user(user, db)
    for player_id in player_ids:
        create_default_preferences(player_id, db)
        for channel in CHANNELS:
            enabled = form.get(channel) == "on"
            pref = (
                db.query(NotificationPreference)
                .filter(
                    NotificationPreference.player_id == player_id,
                    NotificationPreference.channel == channel,
                )
                .first()
            )
            if pref:
                pref.enabled = enabled
    db.commit()
    return RedirectResponse("/profile", status_code=302)


# ── Web Push subscribe / unsubscribe ──────────────────────────────────────────

@router.post("/webpush/subscribe")
async def webpush_subscribe(
    request: Request,
    endpoint: str = Form(...),
    p256dh: str = Form(...),
    auth: str = Form(...),
    user=Depends(require_login),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    """Store a new browser push subscription for the current user's player.

    The CSRF token is sent as a form field by the JS handler (read from the
    <meta name="csrf-token"> tag). require_csrf validates it via the cached
    form body. Do NOT also declare csrf_token as a Form(...) parameter —
    require_csrf already handles it.
    """
    player_ids = _player_ids_for_user(user, db)
    if not player_ids:
        return JSONResponse({"detail": "No linked player"}, status_code=400)

    for player_id in player_ids:
        # Avoid duplicate endpoint
        existing = (
            db.query(WebPushSubscription)
            .filter(
                WebPushSubscription.player_id == player_id,
                WebPushSubscription.endpoint == endpoint,
            )
            .first()
        )
        if existing is None:
            db.add(WebPushSubscription(
                player_id=player_id,
                endpoint=endpoint,
                p256dh_key=p256dh,
                auth_key=auth,
            ))
    db.commit()
    return JSONResponse({"status": "ok"})


@router.post("/webpush/unsubscribe-all")
async def webpush_unsubscribe_all(
    request: Request,
    user=Depends(require_login),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    player_ids = _player_ids_for_user(user, db)
    if player_ids:
        db.query(WebPushSubscription).filter(
            WebPushSubscription.player_id.in_(player_ids)
        ).delete(synchronize_session="fetch")
        db.commit()
    return RedirectResponse("/profile", status_code=302)


@router.post("/webpush/resubscribe")
async def webpush_resubscribe(
    request: Request,
    endpoint: str = Form(...),
    p256dh: str = Form(...),
    auth: str = Form(...),
    user=Depends(require_login),
    db: Session = Depends(get_db),
):
    """CSRF-exempt endpoint for service worker pushsubscriptionchange renewal.

    Service workers cannot access the page DOM so cannot read the csrf meta tag.
    This route is protected by authentication (require_login) and the session
    cookie's SameSite=Lax attribute, which prevents cross-site POST from
    third-party origins. No CSRF dependency is applied here intentionally.
    """
    player_ids = _player_ids_for_user(user, db)
    if not player_ids:
        return JSONResponse({"detail": "No linked player"}, status_code=400)
    for player_id in player_ids:
        existing = (
            db.query(WebPushSubscription)
            .filter(
                WebPushSubscription.player_id == player_id,
                WebPushSubscription.endpoint == endpoint,
            )
            .first()
        )
        if existing is None:
            db.add(WebPushSubscription(
                player_id=player_id,
                endpoint=endpoint,
                p256dh_key=p256dh,
                auth_key=auth,
            ))
    db.commit()
    return JSONResponse({"status": "ok"})
```

- [ ] **Step 4: Register router in `app/main.py`**

In `app/main.py`, add alongside the other route imports:

```python
from routes import notifications as _notifications_mod
```

Then add **directly** to the `app` — do NOT add it to `_routers` or any
prefix-applying loop. The router already declares `prefix="/notifications"`,
so applying a prefix a second time would yield `/notifications/notifications/...`.

```python
app.include_router(_notifications_mod.router)
```

Add this line after the `_routers` loop, at the same level as any other
directly-included routers.

- [ ] **Step 5: Run tests**

```bash
.venv/bin/pytest tests/test_notification_routes.py -v
```

Expected: all pass.

- [ ] **Step 6: Run full suite**

```bash
.venv/bin/pytest -x -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add routes/notifications.py tests/test_notification_routes.py app/main.py
git commit -m "feat: add notifications router (inbox, SSE, mark-read, webpush, preferences)"
```

---

### Task 10: Add notify routes to `routes/events.py`

**Files:**
- Modify: `routes/events.py`
- Create: `tests/test_event_notify.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_event_notify.py`:

```python
"""Tests for GET/POST /events/{id}/notify."""
from __future__ import annotations

import pytest
from models.event import Event
from models.notification import Notification
from models.player import Player
from models.player_team import PlayerTeam
from models.season import Season
from models.team import Team
from services.notification_service import create_default_preferences


@pytest.fixture()
def setup(db):
    season = Season(name="2026", is_active=True)
    db.add(season)
    db.flush()
    team = Team(name="Eagles", season_id=season.id)
    db.add(team)
    db.flush()
    player = Player(first_name="Alice", last_name="Smith",
                    email="alice@test.com", is_active=True)
    db.add(player)
    db.flush()
    db.add(PlayerTeam(player_id=player.id, team_id=team.id,
                      priority=1, role="player",
                      membership_status="active", absent_by_default=False))
    event = Event(title="Match", event_type="match", event_date="2026-04-01",
                  season_id=season.id, team_id=team.id)
    db.add(event)
    db.commit()
    create_default_preferences(player.id, db)
    return {"season": season, "team": team, "player": player, "event": event}


def test_notify_get_requires_admin(client, setup):
    r = client.get(f"/events/{setup['event'].id}/notify")
    assert r.status_code in (302, 401, 403)


def test_notify_get_renders_form(admin_client, setup):
    r = admin_client.get(f"/events/{setup['event'].id}/notify")
    assert r.status_code == 200
    assert b"notify" in r.content.lower()


def test_notify_post_creates_notification(db, admin_client, setup):
    r = admin_client.post(
        f"/events/{setup['event'].id}/notify",
        data={
            "title": "Test Notification",
            "body": "Hello team",
            "tag": "direct",
            "recipients": ["all"],
            "channels": ["inapp"],
        },
    )
    assert r.status_code in (200, 302)
    notifs = db.query(Notification).filter(
        Notification.player_id == setup["player"].id
    ).all()
    assert len(notifs) == 1
    assert notifs[0].title == "Test Notification"


def test_notify_post_member_forbidden(member_client, setup):
    r = member_client.post(
        f"/events/{setup['event'].id}/notify",
        data={"title": "X", "body": "Y", "tag": "direct",
              "recipients": ["all"], "channels": ["inapp"]},
    )
    assert r.status_code in (302, 403)
```

- [ ] **Step 2: Run to confirm they fail**

```bash
.venv/bin/pytest tests/test_event_notify.py -v 2>&1 | head -20
```

Expected: 404.

- [ ] **Step 3: Add notify routes to `routes/events.py`**

Add these imports at the top of `routes/events.py`:

```python
from fastapi import BackgroundTasks
from services.notification_service import send_notifications
from services.notification_templates import TEMPLATES, render_template
```

Add these two route handlers before the final `/{event_id}` catch-all route:

```python
# ── Notify ────────────────────────────────────────────────────────────────────

@router.get("/{event_id}/notify")
async def notify_get(
    event_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        return RedirectResponse("/events", status_code=302)

    # Attendance counts per status for the client-side preview calculation
    from models.attendance import Attendance  # noqa: PLC0415
    counts_q = (
        db.query(Attendance.status, func.count(Attendance.id))
        .filter(Attendance.event_id == event_id)
        .group_by(Attendance.status)
        .all()
    )
    status_counts = dict(counts_q)

    return templates.TemplateResponse(
        request,
        "events/notify.html",
        {
            "user": user,
            "event": event,
            "templates": TEMPLATES,
            "status_counts": status_counts,
        },
    )


@router.post("/{event_id}/notify")
async def notify_post(
    event_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    event = db.get(Event, event_id)
    if event is None:
        return RedirectResponse("/events", status_code=302)

    form = await request.form()
    title = (form.get("title") or "").strip()
    body = (form.get("body") or "").strip()
    tag = (form.get("tag") or "direct").strip()
    recipients_raw = form.getlist("recipients")
    channels_raw = form.getlist("channels")

    # "all" means no status filter
    recipient_statuses = None if "all" in recipients_raw else recipients_raw or None
    admin_channels = channels_raw if channels_raw else ["inapp"]

    if not title or not body:
        return RedirectResponse(f"/events/{event_id}/notify", status_code=302)

    result = send_notifications(
        event=event,
        title=title,
        body=body,
        tag=tag,
        recipient_statuses=recipient_statuses,
        admin_channels=admin_channels,
        db=db,
        background_tasks=background_tasks,
    )

    # Flash message via query param (picked up by the event detail template)
    return RedirectResponse(
        f"/events/{event_id}?notified={result['queued']}",
        status_code=302,
    )
```

Also add `from sqlalchemy import func` to the imports if not already present.

- [ ] **Step 4: Run tests**

```bash
.venv/bin/pytest tests/test_event_notify.py -v
```

Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
.venv/bin/pytest -x -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add routes/events.py tests/test_event_notify.py
git commit -m "feat: add GET/POST /events/{id}/notify route handlers"
```

---

## Chunk 4: Templates & UI

### Task 11: Create `templates/notifications/inbox.html`

**Files:**
- Create: `templates/notifications/inbox.html`

- [ ] **Step 1: Create the directory and template**

```bash
mkdir -p templates/notifications
```

Create `templates/notifications/inbox.html`:

```html
{% extends "base.html" %}
{% block title %}Notifications — {{ settings.APP_NAME }}{% endblock %}

{% block breadcrumb %}
<nav class="breadcrumb">
  <a href="/dashboard">Home</a><span class="breadcrumb-sep"></span>
  <span>Notifications</span>
</nav>
{% endblock %}

{% block content %}
<div class="page-header" style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem;">
  <h2>Notifications</h2>
  {% set unread_count = notifications | selectattr("is_read", "equalto", false) | list | length %}
  {% if unread_count > 0 %}
    <form method="post" action="/notifications/read-all">
      <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
      <button type="submit" class="btn btn-sm btn-outline">Mark all as read</button>
    </form>
  {% endif %}
</div>

{% if not notifications %}
  <p class="text-muted">No notifications yet.</p>
{% else %}
  <ul class="notification-list">
    {% for n in notifications %}
      <li class="notification-item{% if not n.is_read %} unread{% endif %}">
        <form method="post" action="/notifications/{{ n.id }}/read" style="display:none;" id="read-form-{{ n.id }}">
          <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
        </form>
        <a href="{% if n.event_id %}/events/{{ n.event_id }}{% else %}/notifications{% endif %}"
           onclick="document.getElementById('read-form-{{ n.id }}').submit(); return true;"
           class="notification-link">
          <span class="notif-tag notif-tag--{{ n.tag }}">{{ n.tag | title }}</span>
          <span class="notif-title">{{ n.title }}</span>
          <span class="notif-body">{{ n.body | truncate(100) }}</span>
          <span class="notif-time">{{ n.created_at.strftime("%d %b %Y %H:%M") }}</span>
        </a>
      </li>
    {% endfor %}
  </ul>
{% endif %}

<style>
.notification-list { list-style: none; padding: 0; margin: 0; }
.notification-item { border-bottom: 1px solid var(--pico-muted-border-color, #e0e0e0); }
.notification-item.unread { background: var(--pico-primary-background, #eef4ff); }
.notification-link { display: grid; grid-template-columns: auto 1fr; grid-template-rows: auto auto; gap: .15rem .5rem; padding: .75rem .5rem; text-decoration: none; color: inherit; }
.notif-tag { grid-row: 1; grid-column: 1; font-size: .72rem; font-weight: 700; padding: .1rem .4rem; border-radius: 3px; background: var(--pico-secondary-background, #eee); align-self: center; white-space: nowrap; }
.notif-tag--announcement { background: #dbeafe; color: #1e40af; }
.notif-tag--direct { background: #dcfce7; color: #166534; }
.notif-title { grid-row: 1; grid-column: 2; font-weight: 600; }
.notif-body { grid-row: 2; grid-column: 2; font-size: .88rem; color: var(--pico-muted-color, #666); }
.notif-time { grid-row: 2; grid-column: 1; font-size: .75rem; color: var(--pico-muted-color, #999); white-space: nowrap; }
</style>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/notifications/inbox.html
git commit -m "feat: add notification inbox template"
```

---

### Task 12: Create `templates/events/notify.html`

**Files:**
- Create: `templates/events/notify.html`

- [ ] **Step 1: Create `templates/events/notify.html`**

```html
{% extends "base.html" %}
{% block title %}Notify Players — {{ event.title }} — {{ settings.APP_NAME }}{% endblock %}

{% block breadcrumb %}
<nav class="breadcrumb">
  <a href="/dashboard">Home</a><span class="breadcrumb-sep"></span>
  <a href="/events">Events</a><span class="breadcrumb-sep"></span>
  <a href="/events/{{ event.id }}">{{ event.title }}</a><span class="breadcrumb-sep"></span>
  <span>Notify</span>
</nav>
{% endblock %}

{% block content %}
<div class="page-header">
  <h2>Notify Players — {{ event.title }}</h2>
  <p class="text-muted">{{ event.event_date }} {% if event.event_time %}at {{ event.event_time }}{% endif %}{% if event.location %} · {{ event.location }}{% endif %}</p>
</div>

<form method="post" action="/events/{{ event.id }}/notify" id="notify-form">
  <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">

  <!-- Template picker -->
  <label>
    Template
    <select id="template-select" name="template_key">
      <option value="">— Start from template —</option>
      {% for tpl in templates %}
        <option value="{{ tpl.key }}"
          data-title="{{ tpl.title_tpl }}"
          data-body="{{ tpl.body_tpl }}"
          data-tag="{{ tpl.tag }}"
          data-tag-locked="{{ tpl.tag_locked | lower }}">
          {{ tpl.name }}
        </option>
      {% endfor %}
    </select>
  </label>

  <!-- Title -->
  <label>
    Title <span style="color:red">*</span>
    <input type="text" name="title" id="notify-title" required maxlength="256">
  </label>

  <!-- Body -->
  <label>
    Message <span style="color:red">*</span>
    <textarea name="body" id="notify-body" rows="5" required></textarea>
  </label>

  <!-- Tag -->
  <fieldset>
    <legend>Type</legend>
    <label><input type="radio" name="tag" value="direct" checked id="tag-direct"> Direct (targeted)</label>
    <label><input type="radio" name="tag" value="announcement" id="tag-announcement"> Team Announcement</label>
  </fieldset>

  <!-- Recipients -->
  <fieldset>
    <legend>Recipients <span id="recipient-preview" class="text-muted" style="font-size:.88rem;font-weight:normal;"></span></legend>
    <label><input type="checkbox" name="recipients" value="all" id="chk-all" checked> All players</label>
    <label><input type="checkbox" name="recipients" value="present"> Present</label>
    <label><input type="checkbox" name="recipients" value="absent"> Absent</label>
    <label><input type="checkbox" name="recipients" value="maybe"> Maybe</label>
    <label><input type="checkbox" name="recipients" value="unknown"> Unknown</label>
  </fieldset>

  <!-- Channels -->
  <fieldset>
    <legend>Channels</legend>
    <label><input type="checkbox" name="channels" value="email" checked> Email</label>
    <label><input type="checkbox" name="channels" value="inapp" checked> In-app</label>
    <label><input type="checkbox" name="channels" value="webpush" checked> Web Push</label>
  </fieldset>

  <div class="form-footer">
    <button type="submit" class="btn btn-primary">Send Notification</button>
    <a href="/events/{{ event.id }}" class="btn btn-outline">Cancel</a>
  </div>
</form>

<script>
(function () {
  // Status counts from server for live recipient preview
  const STATUS_COUNTS = {{ status_counts | tojson }};
  const TOTAL = Object.values(STATUS_COUNTS).reduce((a, b) => a + b, 0);

  // ── Template pre-fill ─────────────────────────────────────────────────────
  const eventCtx = {
    event: {{ event.title | tojson }},
    date:  {{ event.event_date | string | tojson }},
    time:  {{ (event.event_time | string if event.event_time else "") | tojson }},
    location: {{ (event.location or "") | tojson }},
  };

  function fillPlaceholders(tpl) {
    return tpl.replace(/\{(\w+)\}/g, (_, k) => eventCtx[k] || "{" + k + "}");
  }

  document.getElementById("template-select").addEventListener("change", function () {
    const opt = this.selectedOptions[0];
    if (!opt.value) return;
    document.getElementById("notify-title").value = fillPlaceholders(opt.dataset.title || "");
    document.getElementById("notify-body").value  = fillPlaceholders(opt.dataset.body  || "");
    const locked = opt.dataset.tagLocked === "true";
    document.getElementById("tag-direct").disabled = locked;
    document.getElementById("tag-announcement").disabled = locked;
    const tagVal = opt.dataset.tag || "direct";
    document.querySelector(`input[name="tag"][value="${tagVal}"]`).checked = true;
  });

  // ── Recipient preview ─────────────────────────────────────────────────────
  const allChk = document.getElementById("chk-all");
  const recipientChks = document.querySelectorAll("input[name='recipients']");
  const preview = document.getElementById("recipient-preview");

  function updatePreview() {
    if (allChk.checked) {
      preview.textContent = `— ${TOTAL} player(s)`;
      return;
    }
    let count = 0;
    recipientChks.forEach(chk => {
      if (chk !== allChk && chk.checked) count += STATUS_COUNTS[chk.value] || 0;
    });
    preview.textContent = `— ${count} player(s)`;
  }

  allChk.addEventListener("change", function () {
    if (this.checked) {
      recipientChks.forEach(chk => { if (chk !== allChk) chk.checked = false; });
    }
    updatePreview();
  });
  recipientChks.forEach(chk => {
    if (chk !== allChk) chk.addEventListener("change", function () {
      if (this.checked) allChk.checked = false;
      updatePreview();
    });
  });
  updatePreview();
})();
</script>
{% endblock %}
```

- [ ] **Step 2: Commit**

```bash
git add templates/events/notify.html
git commit -m "feat: add event notify template with template picker and recipient preview"
```

---

### Task 13: Update `templates/base.html` — notification bell

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Add bell to nav**

In `templates/base.html`, inside the `<nav>` element (visible to logged-in users), add the notification bell after the existing nav links and before the logout link:

```html
{% if user %}
  <a href="/notifications" class="notif-bell" title="Notifications" aria-label="Notifications">
    🔔
    {% if request.state.unread_count > 0 %}
      <span class="notif-badge">{{ request.state.unread_count }}</span>
    {% endif %}
  </a>
{% endif %}
```

Add to the `<style>` block or `static/css/main.css`:

```css
.notif-bell { position: relative; text-decoration: none; font-size: 1.1rem; }
.notif-badge {
  position: absolute; top: -6px; right: -8px;
  background: #ef4444; color: #fff;
  font-size: .65rem; font-weight: 700; line-height: 1;
  padding: 2px 4px; border-radius: 10px; white-space: nowrap;
}
```

- [ ] **Step 2: Add SSE client script to base.html**

Just before `</body>` in `base.html`, add (only for logged-in users):

```html
{% if user %}
<script>
(function () {
  const evtSource = new EventSource("/notifications/stream");
  evtSource.onmessage = function (e) {
    try {
      const data = JSON.parse(e.data);
      const badge = document.querySelector(".notif-badge");
      const bell = document.querySelector(".notif-bell");
      if (data.unread_count > 0) {
        if (!badge) {
          const span = document.createElement("span");
          span.className = "notif-badge";
          bell.appendChild(span);
        }
        document.querySelector(".notif-badge").textContent = data.unread_count;
        showToast("You have a new notification");
      } else if (badge) {
        badge.remove();
      }
    } catch (_) {}
  };

  function showToast(msg) {
    const toast = document.createElement("div");
    toast.className = "notif-toast";
    toast.textContent = msg;
    toast.onclick = () => window.location.href = "/notifications";
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
  }
})();
</script>
<style>
.notif-toast {
  position: fixed; bottom: 1.5rem; right: 1.5rem; z-index: 9999;
  background: #1e293b; color: #fff; padding: .75rem 1.25rem;
  border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,.25);
  cursor: pointer; font-size: .92rem; max-width: 320px;
  animation: slideIn .3s ease;
}
@keyframes slideIn { from { transform: translateY(2rem); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
</style>
{% endif %}
```

- [ ] **Step 3: Run tests**

```bash
.venv/bin/pytest -x -q
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add templates/base.html
git commit -m "feat: add notification bell and SSE toast to base template"
```

---

### Task 14: Add notification preferences to profile template

**Files:**
- Modify: `templates/players/profile.html` (or equivalent profile page)

- [ ] **Step 1: Check the profile template path**

```bash
ls templates/players/
```

If no `profile.html` exists, check `templates/auth/` or `templates/dashboard/`. Adapt the path accordingly.

- [ ] **Step 2: Add notification preferences section**

Add this section to the profile template (inside the `{% block content %}`, after existing sections):

```html
<!-- ── Notification Preferences ─────────────────────────────────────────── -->
{% if current_player %}
<section style="margin-top:2rem;">
  <h3>Notification Preferences</h3>
  <form method="post" action="/notifications/preferences">
    <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
    {% for channel, label in [("email","Email"), ("inapp","In-app inbox"), ("webpush","Browser push")] %}
      {% set pref_enabled = player_prefs.get(channel, true) %}
      <label style="display:flex;align-items:center;gap:.5rem;">
        <input type="checkbox" name="{{ channel }}" value="on" {% if pref_enabled %}checked{% endif %}>
        {{ label }}
      </label>
    {% endfor %}
    <button type="submit" class="btn btn-sm btn-outline" style="margin-top:.5rem;">Save preferences</button>
  </form>

  <!-- Web Push subscription -->
  <div style="margin-top:1.5rem;">
    <h4 style="font-size:1rem;">Browser Notifications (Web Push)</h4>
    {% if vapid_public_key %}
      <p id="push-status" class="text-muted" style="font-size:.88rem;">
        {% if push_device_count > 0 %}Active on {{ push_device_count }} device(s).{% else %}Not enabled on this device.{% endif %}
      </p>
      <meta name="csrf-token" content="{{ request.state.csrf_token }}">
      <button type="button" class="btn btn-sm btn-outline" id="enable-push-btn">
        Enable on this device
      </button>
      {% if push_device_count > 0 %}
        <form method="post" action="/notifications/webpush/unsubscribe-all" style="display:inline;">
          <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
          <button type="submit" class="btn btn-sm btn-danger">Remove all devices</button>
        </form>
      {% endif %}
      <script>
      (function () {
        const VAPID_PUBLIC_KEY = {{ vapid_public_key | tojson }};
        const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]').content;

        function urlBase64ToUint8Array(base64String) {
          const padding = '='.repeat((4 - base64String.length % 4) % 4);
          const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
          const rawData = atob(base64);
          return Uint8Array.from([...rawData].map(c => c.charCodeAt(0)));
        }

        document.getElementById("enable-push-btn").addEventListener("click", async () => {
          if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
            alert("Web Push is not supported in this browser.");
            return;
          }
          const perm = await Notification.requestPermission();
          if (perm !== "granted") {
            alert("Permission denied.");
            return;
          }
          const reg = await navigator.serviceWorker.register("/static/js/sw.js");
          const sub = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
          });
          const key = sub.getKey("p256dh");
          const auth = sub.getKey("auth");
          const body = new FormData();
          body.append("csrf_token", CSRF_TOKEN);
          body.append("endpoint", sub.endpoint);
          body.append("p256dh", btoa(String.fromCharCode(...new Uint8Array(key))));
          body.append("auth", btoa(String.fromCharCode(...new Uint8Array(auth))));
          const resp = await fetch("/notifications/webpush/subscribe", {
            method: "POST", body,
          });
          if (resp.ok) {
            document.getElementById("push-status").textContent = "Enabled on this device.";
          } else {
            alert("Failed to subscribe. Please try again.");
          }
        });
      })();
      </script>
    {% else %}
      <p class="text-muted" style="font-size:.88rem;">Web Push is not configured on this server.</p>
    {% endif %}
  </div>
</section>
{% endif %}
```

- [ ] **Step 3: Update the profile route to pass `player_prefs`, `vapid_public_key`, `push_device_count`**

Find the profile route in `routes/` (likely `routes/auth.py` or `routes/players.py`). Add these to its template context:

```python
from models.notification_preference import NotificationPreference
from models.web_push_subscription import WebPushSubscription
from app.config import settings

# Inside the route handler, after identifying current_player:
player_prefs = {}
push_device_count = 0
if current_player:
    prefs = db.query(NotificationPreference).filter(
        NotificationPreference.player_id == current_player.id
    ).all()
    player_prefs = {p.channel: p.enabled for p in prefs}
    push_device_count = db.query(WebPushSubscription).filter(
        WebPushSubscription.player_id == current_player.id
    ).count()

# Add to template context:
{
    ...,
    "player_prefs": player_prefs,
    "push_device_count": push_device_count,
    "vapid_public_key": settings.VAPID_PUBLIC_KEY or None,
    "current_player": current_player,
}
```

- [ ] **Step 4: Add Notify button to event detail template**

In `templates/events/detail.html`, inside the admin action buttons area, add:

```html
{% if user.is_admin %}
  <a href="/events/{{ event.id }}/notify" class="btn btn-sm btn-outline">Notify Players</a>
{% endif %}
```

Also add a flash message display for the `?notified=N` query parameter:

```html
{% if request.query_params.get("notified") %}
  <div class="alert alert-success">
    Notification queued for {{ request.query_params.get("notified") }} player(s).
  </div>
{% endif %}
```

- [ ] **Step 5: Run full test suite**

```bash
.venv/bin/pytest -x -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add templates/ routes/
git commit -m "feat: add notification preferences and web push UI to profile; notify button on event detail"
```

---

## Chunk 5: Web Push & VAPID Setup

### Task 15: VAPID key generator script

**Files:**
- Create: `scripts/generate_vapid.py`

- [ ] **Step 1: Install pywebpush**

```bash
.venv/bin/pip install "pywebpush~=2.0"
```

- [ ] **Step 2: Add to `requirements.txt`**

Add after `itsdangerous==2.2.0`:

```
pywebpush~=2.0
```

- [ ] **Step 3: Create `scripts/generate_vapid.py`**

```python
#!/usr/bin/env python
"""scripts/generate_vapid.py — Generate VAPID key pair for Web Push.

Run once and add the output to your .env file:

    python scripts/generate_vapid.py
"""
from py_vapid import Vapid

vapid = Vapid()
vapid.generate_keys()
public_key = vapid.public_key_urlsafe
private_key = vapid.private_key_urlsafe

print("Add these to your .env file:")
print()
print(f"VAPID_PUBLIC_KEY={public_key}")
print(f"VAPID_PRIVATE_KEY={private_key}")
print(f"VAPID_SUBJECT=mailto:admin@example.com")
print()
print("The public key is also needed in the browser (already served at /notifications/vapid-public-key).")
```

- [ ] **Step 4: Test the script**

```bash
.venv/bin/python scripts/generate_vapid.py
```

Expected: prints two non-empty base64url strings and the VAPID_SUBJECT line.

If you get an `AttributeError` on `public_key_urlsafe` or `private_key_urlsafe`, the
installed `py_vapid` version uses different attribute names. Run:
```bash
.venv/bin/python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print(dir(v))"
```
and adapt the script to use the correct attribute names shown.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt scripts/generate_vapid.py
git commit -m "feat: add VAPID key generator script and pywebpush dependency"
```

---

### Task 16: Service worker `static/js/sw.js`

**Files:**
- Create: `static/js/sw.js`

- [ ] **Step 1: Create `static/js/sw.js`**

```javascript
// static/js/sw.js — Service Worker for Web Push notifications

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

self.addEventListener("push", function (event) {
  let data = { title: "ProManager", body: "You have a new notification." };
  if (event.data) {
    try { data = event.data.json(); } catch (_) {}
  }
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: "/static/img/icon-192.png",  // optional — replace with your icon path
      badge: "/static/img/icon-192.png",
    })
  );
});

self.addEventListener("notificationclick", function (event) {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
      if (list.length > 0) return list[0].focus();
      return clients.openWindow("/notifications");
    })
  );
});

// Re-subscribe when push subscription expires
// Uses a separate CSRF-exempt endpoint (/notifications/webpush/resubscribe)
// because service workers cannot access the page DOM or meta tags.
// SameSite=Lax cookie provides the cross-site protection instead.
self.addEventListener("pushsubscriptionchange", function (event) {
  event.waitUntil(
    self.registration.pushManager.subscribe(event.oldSubscription.options)
      .then(sub => {
        const key = sub.getKey("p256dh");
        const auth = sub.getKey("auth");
        const body = new FormData();
        body.append("endpoint", sub.endpoint);
        body.append("p256dh", btoa(String.fromCharCode(...new Uint8Array(key))));
        body.append("auth", btoa(String.fromCharCode(...new Uint8Array(auth))));
        return fetch("/notifications/webpush/resubscribe", { method: "POST", body });
      })
  );
});
```


- [ ] **Step 2: Commit**

```bash
git add static/js/sw.js
git commit -m "feat: add service worker for Web Push (push, notificationclick, pushsubscriptionchange)"
```

---

### Task 17: Final smoke-test checklist

- [ ] Generate VAPID keys and add to `.env`
- [ ] Run `alembic upgrade head` on dev DB
- [ ] Start dev server: `uvicorn app.main:app --reload --port 7000`
- [ ] Log in as admin → go to an event → "Notify Players" button appears
- [ ] Fill notify form, pick a template → title/body pre-fill correctly
- [ ] Send notification → flash message "Notification queued for N player(s)"
- [ ] Log in as a player with a linked user → notification bell appears in nav
- [ ] Bell shows badge count; clicking opens inbox
- [ ] Toast appears in real-time (open two tabs to test)
- [ ] Profile page shows notification preferences toggles
- [ ] "Enable on this device" triggers browser permission prompt → subscription saved
- [ ] Web push notification appears in browser after admin sends one
- [ ] Run full test suite: `.venv/bin/pytest -v` — all pass

- [ ] **Final commit — push to remote**

```bash
git push
```
