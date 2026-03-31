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
