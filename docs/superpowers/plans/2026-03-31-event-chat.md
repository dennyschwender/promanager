# Event Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a two-lane per-event chat (announcements + discussion) with SSE real-time updates and Telegram push notifications with reply-back.

**Architecture:** New `EventMessage` model + `chat_service` + JSON API routes under `/events/{id}/messages`. SSE reuses the existing per-player asyncio queue registry by adding a generic `push_payload` function. Telegram notifications are sent as async background tasks using the existing `bot.telegram_app`.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, python-telegram-bot, existing SSE + `inapp_channel` infrastructure.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `models/event_message.py` | Create | EventMessage ORM model |
| `models/event.py` | Modify | Add `messages` relationship |
| `models/__init__.py` | Modify | Import EventMessage |
| `alembic/versions/j5k6l7m8n9o0_add_event_messages.py` | Create | DB migration |
| `services/channels/inapp_channel.py` | Modify | Add `push_payload` generic SSE helper |
| `services/chat_service.py` | Create | All chat business logic (author name, SSE push, Telegram) |
| `routes/event_messages.py` | Create | GET / POST / DELETE endpoints |
| `app/main.py` | Modify | Register event_messages router |
| `routes/events.py` | Modify | Pass `chat_messages` to event detail template |
| `locales/en.json` `it.json` `fr.json` `de.json` | Modify | Add `chat.*` and `telegram.chat_*` keys |
| `templates/base.html` | Modify | Expose `window._pmSSE` for chat panel |
| `templates/events/detail.html` | Modify | Add chat panel + JS |
| `bot/handlers.py` | Modify | `chatreply:` callback + `awaiting_chat_reply` text flow |
| `tests/test_event_message_model.py` | Create | Model + migration smoke tests |
| `tests/test_chat_service.py` | Create | Service unit tests |
| `tests/test_event_messages.py` | Create | Route integration tests |

---

### Task 1: EventMessage model and migration

**Files:**
- Create: `models/event_message.py`
- Modify: `models/event.py`
- Modify: `models/__init__.py`
- Create: `alembic/versions/j5k6l7m8n9o0_add_event_messages.py`
- Test: `tests/test_event_message_model.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_event_message_model.py`:

```python
"""Tests for EventMessage model."""
from datetime import date

from models.event import Event
from models.event_message import EventMessage
from models.user import User


def test_event_message_saves_and_retrieves(db):
    user = User(username="u1", email="u@t.com", hashed_password="x", role="admin")
    db.add(user)
    event = Event(title="Test", event_type="training", event_date=date(2026, 4, 1))
    db.add(event)
    db.commit()
    db.refresh(user)
    db.refresh(event)

    msg = EventMessage(event_id=event.id, user_id=user.id, lane="discussion", body="Hello team")
    db.add(msg)
    db.commit()
    db.refresh(msg)

    retrieved = db.get(EventMessage, msg.id)
    assert retrieved is not None
    assert retrieved.body == "Hello team"
    assert retrieved.lane == "discussion"
    assert retrieved.event_id == event.id
    assert retrieved.user_id == user.id
    assert retrieved.created_at is not None


def test_event_message_cascade_deletes_with_event(db):
    event = Event(title="ToDelete", event_type="training", event_date=date(2026, 4, 1))
    db.add(event)
    db.commit()
    db.refresh(event)

    msg = EventMessage(event_id=event.id, user_id=None, lane="discussion", body="Bye")
    db.add(msg)
    db.commit()
    msg_id = msg.id

    db.delete(event)
    db.commit()

    assert db.get(EventMessage, msg_id) is None


def test_event_message_user_id_nullable(db):
    event = Event(title="T", event_type="training", event_date=date(2026, 4, 1))
    db.add(event)
    db.commit()
    db.refresh(event)

    msg = EventMessage(event_id=event.id, user_id=None, lane="announcement", body="No author")
    db.add(msg)
    db.commit()
    db.refresh(msg)
    assert db.get(EventMessage, msg.id).user_id is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_event_message_model.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` — `models.event_message` does not exist yet.

- [ ] **Step 3: Create `models/event_message.py`**

```python
"""models/event_message.py — Per-event chat message."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventMessage(Base):
    __tablename__ = "event_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # "announcement" | "discussion"
    lane: Mapped[str] = mapped_column(String(16), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    user: Mapped["User"] = relationship("User", lazy="select")  # noqa: F821
    event: Mapped["Event"] = relationship(  # noqa: F821
        "Event", back_populates="messages", lazy="select"
    )
```

- [ ] **Step 4: Add `messages` relationship to `models/event.py`**

In `models/event.py`, after the `externals` relationship (around line 72), add:

```python
    messages: Mapped[list["EventMessage"]] = relationship(  # noqa: F821
        "EventMessage", back_populates="event", lazy="select", cascade="all, delete-orphan"
    )
```

- [ ] **Step 5: Update `models/__init__.py`**

Add after the `EventExternal` import line:

```python
from .event_message import EventMessage
```

Add `"EventMessage"` to the `__all__` list.

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_event_message_model.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 7: Create the Alembic migration**

Create `alembic/versions/j5k6l7m8n9o0_add_event_messages.py`:

```python
"""add event_messages table

Revision ID: j5k6l7m8n9o0
Revises: i4j5k6l7m8n9
Create Date: 2026-03-31 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j5k6l7m8n9o0"
down_revision: Union[str, None] = "i4j5k6l7m8n9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "event_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("lane", sa.String(16), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_event_messages_id", "event_messages", ["id"])
    op.create_index("ix_event_messages_event_id", "event_messages", ["event_id"])
    op.create_index("ix_event_messages_user_id", "event_messages", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_event_messages_user_id", table_name="event_messages")
    op.drop_index("ix_event_messages_event_id", table_name="event_messages")
    op.drop_index("ix_event_messages_id", table_name="event_messages")
    op.drop_table("event_messages")
```

- [ ] **Step 8: Apply migration to dev database**

```bash
source .venv/bin/activate
alembic upgrade head
```

Expected: `Running upgrade i4j5k6l7m8n9 -> j5k6l7m8n9o0, add event_messages table`

- [ ] **Step 9: Commit**

```bash
git add models/event_message.py models/event.py models/__init__.py \
    alembic/versions/j5k6l7m8n9o0_add_event_messages.py \
    tests/test_event_message_model.py
git commit -m "feat: add EventMessage model and migration"
```

---

### Task 2: SSE push helper and chat service

**Files:**
- Modify: `services/channels/inapp_channel.py`
- Create: `services/chat_service.py`
- Test: `tests/test_chat_service.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_chat_service.py`:

```python
"""Tests for services/chat_service.py."""

from datetime import date

import pytest

from models.event import Event
from models.event_message import EventMessage
from models.player import Player
from models.player_team import PlayerTeam
from models.season import Season
from models.team import Team
from models.user import User
from services.chat_service import (
    author_display_name,
    message_to_dict,
    resolve_event_player_ids,
)


@pytest.fixture()
def team_event(db):
    season = Season(name="2026", is_active=True)
    db.add(season)
    team = Team(name="Lions")
    db.add(team)
    db.commit()
    db.refresh(season)
    db.refresh(team)
    event = Event(
        title="Practice",
        event_type="training",
        event_date=date(2026, 4, 10),
        team_id=team.id,
        season_id=season.id,
    )
    db.add(event)
    player = Player(first_name="Sam", last_name="Jones", is_active=True)
    db.add(player)
    db.commit()
    db.refresh(event)
    db.refresh(player)
    db.add(
        PlayerTeam(
            player_id=player.id,
            team_id=team.id,
            season_id=season.id,
            priority=1,
            role="player",
            membership_status="active",
            absent_by_default=False,
        )
    )
    db.commit()
    return event, team, player


def test_author_display_name_full_name():
    user = User(
        username="jdoe",
        email="j@t.com",
        hashed_password="x",
        role="member",
        first_name="John",
        last_name="Doe",
    )
    assert author_display_name(user) == "John Doe"


def test_author_display_name_first_only():
    user = User(
        username="jdoe", email="j@t.com", hashed_password="x", role="member", first_name="John"
    )
    assert author_display_name(user) == "John"


def test_author_display_name_username_fallback():
    user = User(username="jdoe", email="j@t.com", hashed_password="x", role="member")
    assert author_display_name(user) == "jdoe"


def test_author_display_name_none():
    assert author_display_name(None) == "Deleted user"


def test_message_to_dict(db):
    user = User(username="u1", email="u@t.com", hashed_password="x", role="admin")
    db.add(user)
    event = Event(title="T", event_type="training", event_date=date(2026, 4, 1))
    db.add(event)
    db.commit()
    db.refresh(user)
    db.refresh(event)
    msg = EventMessage(event_id=event.id, user_id=user.id, lane="discussion", body="Hi")
    db.add(msg)
    db.commit()
    db.refresh(msg)

    d = message_to_dict(msg, "User One")
    assert d["id"] == msg.id
    assert d["lane"] == "discussion"
    assert d["body"] == "Hi"
    assert d["author"] == "User One"
    assert d["user_id"] == user.id
    assert d["created_at"] is not None


def test_resolve_event_player_ids_returns_team_players(db, team_event):
    event, team, player = team_event
    ids = resolve_event_player_ids(event.id, db)
    assert player.id in ids


def test_resolve_event_player_ids_no_team(db):
    event = Event(title="NoTeam", event_type="training", event_date=date(2026, 4, 1))
    db.add(event)
    db.commit()
    db.refresh(event)
    assert resolve_event_player_ids(event.id, db) == []


def test_resolve_event_player_ids_excludes_inactive(db, team_event):
    event, team, _ = team_event
    season = db.query(Season).first()
    inactive_player = Player(first_name="Out", last_name="Player", is_active=False)
    db.add(inactive_player)
    db.commit()
    db.refresh(inactive_player)
    db.add(
        PlayerTeam(
            player_id=inactive_player.id,
            team_id=team.id,
            season_id=season.id,
            priority=2,
            role="player",
            membership_status="active",
            absent_by_default=False,
        )
    )
    db.commit()
    ids = resolve_event_player_ids(event.id, db)
    assert inactive_player.id not in ids
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_chat_service.py -v
```

Expected: `ImportError` — `services.chat_service` does not exist yet.

- [ ] **Step 3: Add `push_payload` to `services/channels/inapp_channel.py`**

After the `push_unread_count` function, add:

```python
def push_payload(player_id: int, payload: dict) -> None:
    """Push an arbitrary JSON payload to all connected tabs for *player_id*.

    Used for chat events (chat_message, chat_delete) that bypass the
    Notification table.
    """
    queues = _connections.get(player_id, [])
    data = json.dumps(payload)
    for q in queues:
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            logger.warning("SSE queue full for player %s — dropping chat event", player_id)
```

- [ ] **Step 4: Create `services/chat_service.py`**

```python
"""services/chat_service.py — Event chat business logic."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from models.event import Event
from models.event_message import EventMessage
from models.player import Player
from models.player_team import PlayerTeam
from models.user import User
from services.channels.inapp_channel import push_payload

logger = logging.getLogger(__name__)


def author_display_name(user: User | None) -> str:
    """Return 'First Last', first name only, username, or 'Deleted user'."""
    if user is None:
        return "Deleted user"
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    if user.first_name:
        return user.first_name
    return user.username


def message_to_dict(msg: EventMessage, author_name: str) -> dict:
    """Serialise an EventMessage to a JSON-safe dict."""
    return {
        "id": msg.id,
        "event_id": msg.event_id,
        "lane": msg.lane,
        "body": msg.body,
        "author": author_name,
        "user_id": msg.user_id,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


def resolve_event_player_ids(event_id: int, db: Session) -> list[int]:
    """Return all active player_ids for the event's team (no attendance filter).

    Returns empty list if the event has no team_id.
    """
    event = db.get(Event, event_id)
    if event is None or event.team_id is None:
        return []
    rows = (
        db.query(PlayerTeam.player_id)
        .join(Player, Player.id == PlayerTeam.player_id)
        .filter(
            PlayerTeam.team_id == event.team_id,
            PlayerTeam.membership_status == "active",
            Player.is_active.is_(True),
            Player.archived_at.is_(None),
        )
        .all()
    )
    return [r[0] for r in rows]


def push_chat_message_sse(event_id: int, msg_dict: dict, db: Session) -> None:
    """Push a chat_message SSE event to all connected players for the event."""
    player_ids = resolve_event_player_ids(event_id, db)
    payload = {"type": "chat_message", "event_id": event_id, "message": msg_dict}
    for pid in player_ids:
        push_payload(pid, payload)


def push_chat_delete_sse(event_id: int, message_id: int, db: Session) -> None:
    """Push a chat_delete SSE event to all connected players for the event."""
    player_ids = resolve_event_player_ids(event_id, db)
    payload = {"type": "chat_delete", "event_id": event_id, "message_id": message_id}
    for pid in player_ids:
        push_payload(pid, payload)


async def send_telegram_notifications(
    event_id: int,
    author_name: str,
    lane: str,
    body: str,
    exclude_user_id: int | None,
) -> None:
    """Send Telegram push notifications for a new chat message.

    Targets: players with present/maybe/unknown attendance + coaches/admins
    linked to the event's team. Excludes the message author.
    Opens its own DB session — safe to call as a BackgroundTask.
    """
    try:
        import bot as _bot  # noqa: PLC0415

        if _bot.telegram_app is None:
            return
    except Exception:
        return

    import app.database as _db_mod  # noqa: PLC0415
    from models.attendance import Attendance  # noqa: PLC0415
    from models.user_team import UserTeam  # noqa: PLC0415
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup  # noqa: PLC0415

    db = _db_mod.SessionLocal()
    try:
        event = db.get(Event, event_id)
        if event is None:
            return

        lane_label = "📢 Announcement" if lane == "announcement" else "💬 Discussion"
        text = f"{lane_label} — {event.title}\n{author_name}: {body}"

        chat_ids: set[str] = set()

        if event.team_id is not None:
            # Players with non-absent attendance
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
                if player and player.user_id and player.user_id != exclude_user_id:
                    u = db.get(User, player.user_id)
                    if u and u.telegram_chat_id:
                        chat_ids.add(u.telegram_chat_id)

            # Coaches/admins linked to the event's team via UserTeam
            coach_rows = (
                db.query(UserTeam).filter(UserTeam.team_id == event.team_id).all()
            )
            for row in coach_rows:
                if row.user_id != exclude_user_id:
                    u = db.get(User, row.user_id)
                    if u and u.telegram_chat_id:
                        chat_ids.add(u.telegram_chat_id)

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💬 Reply",
                        callback_data=f"chatreply:{event_id}:discussion",
                    )
                ]
            ]
        )

        for chat_id in chat_ids:
            try:
                await _bot.telegram_app.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=keyboard,
                )
            except Exception:
                logger.warning(
                    "Failed to send Telegram chat notification to %s", chat_id
                )
    finally:
        db.close()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_chat_service.py -v
```

Expected: All 8 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add services/channels/inapp_channel.py services/chat_service.py \
    tests/test_chat_service.py
git commit -m "feat: add push_payload SSE helper and chat service"
```

---

### Task 3: Event messages routes

**Files:**
- Create: `routes/event_messages.py`
- Test: `tests/test_event_messages.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_event_messages.py`:

```python
"""Tests for /events/{id}/messages routes."""

from datetime import date

import pytest

from models.event import Event
from models.event_message import EventMessage


@pytest.fixture()
def event(db):
    e = Event(title="Chat Test", event_type="training", event_date=date(2026, 4, 10))
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def test_list_messages_requires_login(client, db, event):
    r = client.get(f"/events/{event.id}/messages")
    assert r.status_code in (302, 401)


def test_list_messages_empty(admin_client, db, event):
    r = admin_client.get(f"/events/{event.id}/messages")
    assert r.status_code == 200
    assert r.json() == []


def test_list_messages_returns_both_lanes(admin_client, db, event, admin_user):
    db.add(EventMessage(event_id=event.id, user_id=admin_user.id, lane="announcement", body="Ann 1"))
    db.add(EventMessage(event_id=event.id, user_id=admin_user.id, lane="discussion", body="Disc 1"))
    db.commit()
    r = admin_client.get(f"/events/{event.id}/messages")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    lanes = {m["lane"] for m in data}
    assert lanes == {"announcement", "discussion"}


def test_post_announcement_as_admin(admin_client, db, event):
    r = admin_client.post(
        f"/events/{event.id}/messages",
        json={"lane": "announcement", "body": "Meeting at 10am"},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["lane"] == "announcement"
    assert data["body"] == "Meeting at 10am"
    assert "id" in data
    assert data["created_at"] is not None


def test_post_discussion_as_member(member_client, db, event):
    r = member_client.post(
        f"/events/{event.id}/messages",
        json={"lane": "discussion", "body": "See you there!"},
    )
    assert r.status_code == 201
    assert r.json()["lane"] == "discussion"


def test_post_announcement_as_member_forbidden(member_client, db, event):
    r = member_client.post(
        f"/events/{event.id}/messages",
        json={"lane": "announcement", "body": "Unauthorized"},
    )
    assert r.status_code == 403


def test_post_invalid_lane_rejected(admin_client, db, event):
    r = admin_client.post(
        f"/events/{event.id}/messages",
        json={"lane": "other", "body": "test"},
    )
    assert r.status_code == 400


def test_post_empty_body_rejected(admin_client, db, event):
    r = admin_client.post(
        f"/events/{event.id}/messages",
        json={"lane": "discussion", "body": "   "},
    )
    assert r.status_code == 400


def test_post_nonexistent_event(admin_client, db):
    r = admin_client.post(
        "/events/99999/messages",
        json={"lane": "discussion", "body": "Hello"},
    )
    assert r.status_code == 404


def test_delete_own_message_as_member(member_client, db, event, member_user):
    msg = EventMessage(event_id=event.id, user_id=member_user.id, lane="discussion", body="Mine")
    db.add(msg)
    db.commit()
    db.refresh(msg)

    r = member_client.delete(f"/events/{event.id}/messages/{msg.id}")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert db.get(EventMessage, msg.id) is None


def test_delete_others_message_as_member_forbidden(member_client, db, event, admin_user):
    msg = EventMessage(
        event_id=event.id, user_id=admin_user.id, lane="discussion", body="Admin's"
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    r = member_client.delete(f"/events/{event.id}/messages/{msg.id}")
    assert r.status_code == 403


def test_delete_any_message_as_admin(admin_client, db, event, member_user):
    msg = EventMessage(
        event_id=event.id, user_id=member_user.id, lane="discussion", body="Member's"
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    r = admin_client.delete(f"/events/{event.id}/messages/{msg.id}")
    assert r.status_code == 200
    assert db.get(EventMessage, msg.id) is None


def test_delete_nonexistent_message(admin_client, db, event):
    r = admin_client.delete(f"/events/{event.id}/messages/99999")
    assert r.status_code == 404


def test_messages_ordered_by_created_at(admin_client, db, event, admin_user):
    db.add(EventMessage(event_id=event.id, user_id=admin_user.id, lane="discussion", body="First"))
    db.add(EventMessage(event_id=event.id, user_id=admin_user.id, lane="discussion", body="Second"))
    db.commit()
    r = admin_client.get(f"/events/{event.id}/messages")
    data = r.json()
    assert data[0]["body"] == "First"
    assert data[1]["body"] == "Second"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_event_messages.py -v
```

Expected: Tests fail — route module does not exist yet.

- [ ] **Step 3: Create `routes/event_messages.py`**

```python
"""routes/event_messages.py — Event chat message endpoints."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.csrf import require_csrf_header
from app.database import get_db
from models.event import Event
from models.event_message import EventMessage
from models.user import User
from routes._auth_helpers import require_login
from services.chat_service import (
    author_display_name,
    message_to_dict,
    push_chat_delete_sse,
    push_chat_message_sse,
    send_telegram_notifications,
)

router = APIRouter()


class _PostBody(BaseModel):
    lane: str
    body: str


@router.get("/events/{event_id}/messages")
async def list_messages(
    event_id: int,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
) -> JSONResponse:
    if db.get(Event, event_id) is None:
        raise HTTPException(status_code=404)
    messages = (
        db.query(EventMessage)
        .filter(EventMessage.event_id == event_id)
        .order_by(EventMessage.created_at.asc())
        .all()
    )
    result = []
    for msg in messages:
        author = db.get(User, msg.user_id) if msg.user_id else None
        result.append(message_to_dict(msg, author_display_name(author)))
    return JSONResponse(result)


@router.post("/events/{event_id}/messages")
async def post_message(
    event_id: int,
    body: _PostBody,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_login),
    _csrf: None = Depends(require_csrf_header),
    db: Session = Depends(get_db),
) -> JSONResponse:
    if db.get(Event, event_id) is None:
        raise HTTPException(status_code=404)
    if body.lane not in ("announcement", "discussion"):
        raise HTTPException(status_code=400, detail="Invalid lane")
    if body.lane == "announcement" and not (user.is_admin or user.is_coach):
        raise HTTPException(status_code=403, detail="Only coaches and admins can post announcements")
    if not body.body.strip():
        raise HTTPException(status_code=400, detail="Message body cannot be empty")

    msg = EventMessage(
        event_id=event_id,
        user_id=user.id,
        lane=body.lane,
        body=body.body.strip(),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    author_name = author_display_name(user)
    msg_dict = message_to_dict(msg, author_name)

    push_chat_message_sse(event_id, msg_dict, db)
    background_tasks.add_task(
        send_telegram_notifications,
        event_id,
        author_name,
        body.lane,
        body.body.strip(),
        user.id,
    )

    return JSONResponse(msg_dict, status_code=201)


@router.delete("/events/{event_id}/messages/{msg_id}")
async def delete_message(
    event_id: int,
    msg_id: int,
    _csrf: None = Depends(require_csrf_header),
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
) -> JSONResponse:
    msg = db.get(EventMessage, msg_id)
    if msg is None or msg.event_id != event_id:
        raise HTTPException(status_code=404)
    if msg.user_id != user.id and not (user.is_admin or user.is_coach):
        raise HTTPException(status_code=403)
    db.delete(msg)
    db.commit()
    push_chat_delete_sse(event_id, msg_id, db)
    return JSONResponse({"ok": True})
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_event_messages.py -v
```

Expected: All 14 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add routes/event_messages.py tests/test_event_messages.py
git commit -m "feat: add event messages GET/POST/DELETE routes"
```

---

### Task 4: Wire up router, update event_detail, add i18n keys

**Files:**
- Modify: `app/main.py`
- Modify: `routes/events.py`
- Modify: `locales/en.json`, `locales/it.json`, `locales/fr.json`, `locales/de.json`

- [ ] **Step 1: Register the router in `app/main.py`**

In `app/main.py`, in the `_routers` list (around line 168), add after the `attendance` entry:

```python
        ("routes.event_messages", "", "event_messages"),
```

- [ ] **Step 2: Add `chat_messages` to the `event_detail` route in `routes/events.py`**

Add these imports at the top with the other model imports:

```python
from models.event_message import EventMessage
from services.chat_service import author_display_name, message_to_dict
```

In the `event_detail` function, just before the `return render(...)` call, add:

```python
    chat_msgs_raw = (
        db.query(EventMessage)
        .filter(EventMessage.event_id == event_id)
        .order_by(EventMessage.created_at.asc())
        .all()
    )
    chat_messages = [
        message_to_dict(
            msg,
            author_display_name(db.get(User, msg.user_id) if msg.user_id else None),
        )
        for msg in chat_msgs_raw
    ]
```

Add `"chat_messages": chat_messages` to the dict passed to `render()`.

- [ ] **Step 3: Add i18n keys to `locales/en.json`**

Add a `"chat"` top-level section (before the closing `}`):

```json
  "chat": {
    "title": "Chat",
    "announcements": "Announcements",
    "discussion": "Discussion",
    "post_placeholder_announcement": "Write an announcement...",
    "post_placeholder_discussion": "Write a message...",
    "send": "Send",
    "delete_confirm": "Delete this message?",
    "empty_announcement": "No announcements yet.",
    "empty_discussion": "No messages yet."
  }
```

In the `"telegram"` section, add before its closing `}`:

```json
    "chat_reply_button": "💬 Reply",
    "chat_reply_prompt": "Type your reply (or /cancel to abort):",
    "chat_reply_posted": "Your message was posted to the event discussion."
```

- [ ] **Step 4: Add i18n keys to `locales/it.json`**

`"chat"` section:

```json
  "chat": {
    "title": "Chat",
    "announcements": "Comunicazioni",
    "discussion": "Discussione",
    "post_placeholder_announcement": "Scrivi una comunicazione...",
    "post_placeholder_discussion": "Scrivi un messaggio...",
    "send": "Invia",
    "delete_confirm": "Eliminare questo messaggio?",
    "empty_announcement": "Nessuna comunicazione.",
    "empty_discussion": "Nessun messaggio."
  }
```

Telegram keys:

```json
    "chat_reply_button": "💬 Rispondi",
    "chat_reply_prompt": "Scrivi la tua risposta (o /cancel per annullare):",
    "chat_reply_posted": "Il tuo messaggio è stato pubblicato nella discussione dell'evento."
```

- [ ] **Step 5: Add i18n keys to `locales/fr.json`**

`"chat"` section:

```json
  "chat": {
    "title": "Chat",
    "announcements": "Annonces",
    "discussion": "Discussion",
    "post_placeholder_announcement": "Écrire une annonce...",
    "post_placeholder_discussion": "Écrire un message...",
    "send": "Envoyer",
    "delete_confirm": "Supprimer ce message ?",
    "empty_announcement": "Aucune annonce.",
    "empty_discussion": "Aucun message."
  }
```

Telegram keys:

```json
    "chat_reply_button": "💬 Répondre",
    "chat_reply_prompt": "Tapez votre réponse (ou /cancel pour annuler) :",
    "chat_reply_posted": "Votre message a été publié dans la discussion de l'événement."
```

- [ ] **Step 6: Add i18n keys to `locales/de.json`**

`"chat"` section:

```json
  "chat": {
    "title": "Chat",
    "announcements": "Ankündigungen",
    "discussion": "Diskussion",
    "post_placeholder_announcement": "Ankündigung schreiben...",
    "post_placeholder_discussion": "Nachricht schreiben...",
    "send": "Senden",
    "delete_confirm": "Diese Nachricht löschen?",
    "empty_announcement": "Keine Ankündigungen.",
    "empty_discussion": "Keine Nachrichten."
  }
```

Telegram keys:

```json
    "chat_reply_button": "💬 Antworten",
    "chat_reply_prompt": "Schreibe deine Antwort (oder /cancel zum Abbrechen):",
    "chat_reply_posted": "Deine Nachricht wurde in der Eventdiskussion veröffentlicht."
```

- [ ] **Step 7: Run full test suite**

```bash
pytest -v
```

Expected: All tests PASS.

- [ ] **Step 8: Commit**

```bash
git add app/main.py routes/events.py \
    locales/en.json locales/it.json locales/fr.json locales/de.json
git commit -m "feat: wire event messages router, update event_detail, add i18n chat keys"
```

---

### Task 5: Chat panel template

**Files:**
- Modify: `templates/base.html`
- Modify: `templates/events/detail.html`

- [ ] **Step 1: Expose `window._pmSSE` in `templates/base.html`**

Find this line (around line 126):

```js
  const evtSource = new EventSource("/notifications/stream");
```

Add `window._pmSSE = evtSource;` immediately after:

```js
  const evtSource = new EventSource("/notifications/stream");
  window._pmSSE = evtSource;
```

- [ ] **Step 2: Add the chat panel to `templates/events/detail.html`**

Find the last `{% endblock %}` at the end of `{% block content %}` (after the delete-dialog `{% endif %}`). Insert the entire block **before** it:

```html
{# ── Chat panel ────────────────────────────────────────────────── #}
<details id="chat-panel" class="chat-panel">
  <summary>{{ t('chat.title') }}</summary>
  <div class="chat-tabs">
    <button type="button" class="chat-tab-btn active" data-lane="announcement">{{ t('chat.announcements') }}</button>
    <button type="button" class="chat-tab-btn" data-lane="discussion">{{ t('chat.discussion') }}</button>
  </div>

  <div id="chat-lane-announcement" class="chat-lane">
    <div class="chat-messages" id="chat-messages-announcement"></div>
    {% if user.is_admin or user.is_coach %}
    <div class="chat-input-row">
      <textarea id="chat-input-announcement" class="chat-input" rows="2" placeholder="{{ t('chat.post_placeholder_announcement') }}"></textarea>
      <button type="button" class="btn btn-sm btn-primary chat-send-btn" data-lane="announcement">{{ t('chat.send') }}</button>
    </div>
    {% endif %}
  </div>

  <div id="chat-lane-discussion" class="chat-lane" style="display:none">
    <div class="chat-messages" id="chat-messages-discussion"></div>
    <div class="chat-input-row">
      <textarea id="chat-input-discussion" class="chat-input" rows="2" placeholder="{{ t('chat.post_placeholder_discussion') }}"></textarea>
      <button type="button" class="btn btn-sm btn-primary chat-send-btn" data-lane="discussion">{{ t('chat.send') }}</button>
    </div>
  </div>
</details>

<style>
.chat-panel { margin-top: 2rem; }
.chat-panel > summary { cursor: pointer; font-weight: 600; padding: .5rem 0; user-select: none; }
.chat-tabs { display: flex; gap: .5rem; margin: .75rem 0 .5rem; }
.chat-tab-btn { padding: .25rem .85rem; border-radius: 999px; border: 1px solid var(--tp-border, #ccc); background: none; cursor: pointer; font-size: .9rem; }
.chat-tab-btn.active { background: var(--tp-primary, #3498db); color: #fff; border-color: var(--tp-primary, #3498db); }
.chat-messages { max-height: 320px; overflow-y: auto; display: flex; flex-direction: column; gap: .4rem; margin-bottom: .5rem; padding: .25rem 0; }
.chat-msg { padding: .5rem .75rem; border-radius: 6px; background: var(--tp-surface, #f4f4f4); }
.chat-msg-announcement { background: var(--tp-warning-light, #fff8e1); border-left: 3px solid var(--tp-warning, #f39c12); }
.chat-msg-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: .2rem; }
.chat-msg-meta { display: flex; align-items: center; gap: .4rem; }
.chat-msg-author { font-weight: 600; font-size: .875rem; }
.chat-msg-time { font-size: .75rem; color: var(--tp-muted, #888); }
.chat-msg-body { white-space: pre-wrap; word-break: break-word; font-size: .9rem; }
.chat-msg-del { background: none; border: none; cursor: pointer; color: var(--tp-danger, #c0392b); font-size: .8rem; padding: 0 .2rem; opacity: .6; }
.chat-msg-del:hover { opacity: 1; }
.chat-input-row { display: flex; gap: .5rem; align-items: flex-end; }
.chat-input { flex: 1; resize: vertical; min-height: 2.5rem; }
</style>

<script>
(function () {
  var EVENT_ID = {{ event.id }};
  var USER_ID = {{ user.id }};
  var IS_PRIVILEGED = {{ 'true' if (user.is_admin or user.is_coach) else 'false' }};
  var CSRF = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
  var DELETE_CONFIRM = {{ t('chat.delete_confirm') | tojson }};

  var panel = document.getElementById('chat-panel');
  var loaded = false;
  var _renderedIds = new Set();

  function formatTime(isoStr) {
    if (!isoStr) return '';
    try { return new Date(isoStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); } catch (_) { return ''; }
  }

  function renderMessage(msg) {
    var div = document.createElement('div');
    div.className = 'chat-msg' + (msg.lane === 'announcement' ? ' chat-msg-announcement' : '');
    div.dataset.msgId = msg.id;

    var header = document.createElement('div');
    header.className = 'chat-msg-header';
    var meta = document.createElement('div');
    meta.className = 'chat-msg-meta';

    if (msg.lane === 'announcement') {
      var icon = document.createElement('span');
      icon.textContent = '📢';
      meta.appendChild(icon);
    }
    var author = document.createElement('span');
    author.className = 'chat-msg-author';
    author.textContent = msg.author;
    meta.appendChild(author);
    var time = document.createElement('span');
    time.className = 'chat-msg-time';
    time.textContent = formatTime(msg.created_at);
    meta.appendChild(time);
    header.appendChild(meta);

    if (msg.user_id === USER_ID || IS_PRIVILEGED) {
      var delBtn = document.createElement('button');
      delBtn.type = 'button';
      delBtn.className = 'chat-msg-del';
      delBtn.title = 'Delete';
      delBtn.textContent = '🗑';
      delBtn.addEventListener('click', function () {
        if (!confirm(DELETE_CONFIRM)) return;
        fetch('/events/' + EVENT_ID + '/messages/' + msg.id, {
          method: 'DELETE',
          headers: { 'X-CSRF-Token': CSRF },
        })
          .then(function (r) { return r.json(); })
          .then(function (data) { if (data.ok) { div.remove(); _renderedIds.delete(msg.id); } });
      });
      header.appendChild(delBtn);
    }

    div.appendChild(header);
    var bodyEl = document.createElement('div');
    bodyEl.className = 'chat-msg-body';
    bodyEl.textContent = msg.body;
    div.appendChild(bodyEl);
    return div;
  }

  function appendMessage(msg) {
    if (_renderedIds.has(msg.id)) return;
    _renderedIds.add(msg.id);
    var container = document.getElementById('chat-messages-' + msg.lane);
    if (!container) return;
    container.appendChild(renderMessage(msg));
    container.scrollTop = container.scrollHeight;
  }

  function removeMessage(messageId) {
    var el = document.querySelector('[data-msg-id="' + messageId + '"]');
    if (el) { el.remove(); _renderedIds.delete(messageId); }
  }

  function loadMessages() {
    fetch('/events/' + EVENT_ID + '/messages')
      .then(function (r) { return r.json(); })
      .then(function (messages) {
        _renderedIds.clear();
        var annEl = document.getElementById('chat-messages-announcement');
        var discEl = document.getElementById('chat-messages-discussion');
        while (annEl.firstChild) { annEl.removeChild(annEl.firstChild); }
        while (discEl.firstChild) { discEl.removeChild(discEl.firstChild); }
        messages.forEach(appendMessage);
        loaded = true;
      });
  }

  panel.addEventListener('toggle', function () {
    if (panel.open && !loaded) loadMessages();
  });

  if (window._pmSSE) {
    window._pmSSE.addEventListener('message', function (e) {
      try {
        var data = JSON.parse(e.data);
        if (data.event_id !== EVENT_ID) return;
        if (data.type === 'chat_message' && loaded) { appendMessage(data.message); }
        else if (data.type === 'chat_delete') { removeMessage(data.message_id); }
      } catch (_) {}
    });
  }

  document.querySelectorAll('.chat-tab-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.chat-tab-btn').forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      var lane = btn.dataset.lane;
      document.getElementById('chat-lane-announcement').style.display = lane === 'announcement' ? '' : 'none';
      document.getElementById('chat-lane-discussion').style.display = lane === 'discussion' ? '' : 'none';
    });
  });

  document.querySelectorAll('.chat-send-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var lane = btn.dataset.lane;
      var input = document.getElementById('chat-input-' + lane);
      var bodyText = input.value.trim();
      if (!bodyText) return;
      btn.disabled = true;
      fetch('/events/' + EVENT_ID + '/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-CSRF-Token': CSRF },
        body: JSON.stringify({ lane: lane, body: bodyText }),
      })
        .then(function (r) { return r.json(); })
        .then(function (msg) { if (msg.id) { input.value = ''; appendMessage(msg); } btn.disabled = false; })
        .catch(function () { btn.disabled = false; });
    });
  });

  document.querySelectorAll('.chat-input').forEach(function (input) {
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        var lane = input.id.replace('chat-input-', '');
        var sendBtn = document.querySelector('.chat-send-btn[data-lane="' + lane + '"]');
        if (sendBtn) sendBtn.click();
      }
    });
  });
})();
</script>
```

- [ ] **Step 3: Verify visually**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 7000
```

Open an event detail page. Confirm:
- Chat panel appears collapsed at the bottom
- Clicking expands it; Announcements tab is shown first
- As admin/coach: can send in both tabs
- As member: Announcement tab has no input box; Discussion tab does
- Post a message → appears immediately without page reload
- Delete own message → disappears immediately

- [ ] **Step 4: Commit**

```bash
git add templates/base.html templates/events/detail.html
git commit -m "feat: add event chat panel with SSE real-time updates"
```

---

### Task 6: Telegram bot reply-back

**Files:**
- Modify: `bot/handlers.py`

- [ ] **Step 1: Add `awaiting_chat_reply` to the cleanup loop in `handle_callback`**

Find this line in `handle_callback`:

```python
        for _key in ("awaiting_note",) + (() if _skip_ext_cleanup else ("awaiting_external",)) + (() if _skip_extn_cleanup else ("awaiting_ext_note",)):
```

Replace with:

```python
        for _key in ("awaiting_note", "awaiting_chat_reply") + (() if _skip_ext_cleanup else ("awaiting_external",)) + (() if _skip_extn_cleanup else ("awaiting_ext_note",)):
```

- [ ] **Step 2: Add `chatreply:` callback handler at the end of `handle_callback`**

After the last `elif data.startswith("sta:")` block, add:

```python
        elif data.startswith("chatreply:"):
            await query.answer()
            # chatreply:{event_id}:{lane}
            parts = data.split(":")
            event_id_cr = int(parts[1])
            locale_cr = _locale(user)
            prompt_msg = await query.message.reply_text(
                t("telegram.chat_reply_prompt", locale_cr)
            )
            context.user_data["awaiting_chat_reply"] = {
                "event_id": event_id_cr,
                "prompt_message_id": prompt_msg.message_id,
                "chat_id": query.message.chat_id,
            }
```

- [ ] **Step 3: Handle `awaiting_chat_reply` text in `handle_text`**

In `handle_text`, find:

```python
    pending = context.user_data.get("awaiting_note")
    if not pending:
        return  # ignore unrecognised text
```

Insert the following block **immediately before** those two lines:

```python
    # Handle chat reply input
    pending_chat = context.user_data.get("awaiting_chat_reply")
    if pending_chat:
        body_text = (update.message.text or "").strip()
        prompt_msg_id = pending_chat.get("prompt_message_id")
        reply_chat_id = pending_chat.get("chat_id")
        if prompt_msg_id and reply_chat_id:
            try:
                await context.bot.delete_message(chat_id=reply_chat_id, message_id=prompt_msg_id)
            except Exception:
                pass
        try:
            await update.message.delete()
        except Exception:
            pass
        context.user_data.pop("awaiting_chat_reply", None)
        locale_cr = "en"
        if body_text:
            with SessionLocal() as db:
                user = get_user_by_chat_id(db, chat_id)
                locale_cr = _locale(user) if user else "en"
                if user:
                    from models.event_message import EventMessage as _EventMessage  # noqa: PLC0415
                    from services.chat_service import (  # noqa: PLC0415
                        author_display_name,
                        message_to_dict,
                        push_chat_message_sse,
                    )
                    msg = _EventMessage(
                        event_id=pending_chat["event_id"],
                        user_id=user.id,
                        lane="discussion",
                        body=body_text,
                    )
                    db.add(msg)
                    db.commit()
                    db.refresh(msg)
                    author_name = author_display_name(user)
                    msg_dict = message_to_dict(msg, author_name)
                    push_chat_message_sse(pending_chat["event_id"], msg_dict, db)
        import asyncio as _asyncio  # noqa: PLC0415
        conf = await update.message.reply_text(t("telegram.chat_reply_posted", locale_cr))
        await _asyncio.sleep(2)
        try:
            await conf.delete()
        except Exception:
            pass
        return
```

- [ ] **Step 4: Add `awaiting_chat_reply` to `handle_cancel`**

Find:

```python
    cancelled = context.user_data.pop("awaiting_note", None) or context.user_data.pop("awaiting_ext_note", None) or context.user_data.pop("awaiting_external", None)
```

Replace with:

```python
    cancelled = (
        context.user_data.pop("awaiting_note", None)
        or context.user_data.pop("awaiting_ext_note", None)
        or context.user_data.pop("awaiting_external", None)
        or context.user_data.pop("awaiting_chat_reply", None)
    )
```

- [ ] **Step 5: Run full test suite**

```bash
pytest -v
```

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add bot/handlers.py
git commit -m "feat: add Telegram chat reply-back (chatreply: callback)"
```

---

## End-to-End Verification Checklist

- [ ] Post announcement as coach → appears in panel under Announcements tab
- [ ] SSE delivers it live to a second open browser tab (same player/user)
- [ ] Telegram push received by present/maybe/unknown players (not absent)
- [ ] Post discussion message as member → appears under Discussion tab
- [ ] Member attempts to post announcement → 403
- [ ] Delete own message → removed from UI live via SSE
- [ ] Admin deletes member's message → removed from UI live
- [ ] Reply via Telegram bot → message appears in Discussion lane in web UI
- [ ] Absent player receives no Telegram notification
- [ ] `/cancel` during Telegram reply → prompt cleaned up, no message posted
- [ ] Opening panel loads full message history for both lanes
