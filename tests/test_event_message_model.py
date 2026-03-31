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
