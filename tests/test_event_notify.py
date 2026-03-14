"""Tests for GET/POST /events/{id}/notify."""
from __future__ import annotations

import datetime
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
    event = Event(title="Match", event_type="match", event_date=datetime.date(2026, 4, 1),
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
