"""Tests for /teams routes."""
from models.team import Team

# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_teams_list(admin_client):
    resp = admin_client.get("/teams", follow_redirects=False)
    assert resp.status_code == 200


def test_teams_requires_login(client):
    resp = client.get("/teams", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_team(admin_client, db):
    resp = admin_client.post(
        "/teams/new",
        data={"name": "Falcons", "description": "The best team", "season_id": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert db.query(Team).filter(Team.name == "Falcons").first() is not None


def test_create_team_blank_name(admin_client):
    resp = admin_client.post(
        "/teams/new",
        data={"name": "", "description": "", "season_id": ""},
        follow_redirects=False,
    )
    assert resp.status_code in (400, 422)


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


def test_edit_team(admin_client, db):
    team = Team(name="OldTeam")
    db.add(team)
    db.commit()
    db.refresh(team)

    resp = admin_client.post(
        f"/teams/{team.id}/edit",
        data={"name": "NewTeam", "description": "", "season_id": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db.refresh(team)
    assert team.name == "NewTeam"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_team(admin_client, db):
    team = Team(name="ToDelete")
    db.add(team)
    db.commit()
    db.refresh(team)
    tid = team.id

    resp = admin_client.post(f"/teams/{tid}/delete", follow_redirects=False)
    assert resp.status_code == 302
    assert db.get(Team, tid) is None


# ---------------------------------------------------------------------------
# Recurring schedules
# ---------------------------------------------------------------------------

from datetime import date
from unittest.mock import patch


def _make_team_for_sched(db, name="Eagles"):
    from models.team import Team
    team = Team(name=name)
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


def _sched_form_data(i=0, title="Eagles - Training Tuesday", event_type="training",
                     rule="weekly", start="2026-03-03", end="2026-03-24",
                     sched_id=""):
    return {
        f"sched_id_{i}": sched_id,
        f"sched_title_{i}": title,
        f"sched_event_type_{i}": event_type,
        f"sched_rule_{i}": rule,
        f"sched_start_{i}": start,
        f"sched_end_{i}": end,
        f"sched_time_{i}": "18:00",
        f"sched_end_time_{i}": "",
        f"sched_location_{i}": "Gym A",
        f"sched_meeting_time_{i}": "",
        f"sched_meeting_location_{i}": "",
        f"sched_presence_{i}": "normal",
        f"sched_desc_{i}": "",
        "sched_count": "1",
    }


def test_new_schedule_creates_events(admin_client, db):
    team = _make_team_for_sched(db)
    data = {"name": team.name, "description": "", "season_id": ""}
    data.update(_sched_form_data(start="2026-03-03", end="2026-03-24"))

    with patch("services.schedule_service.ensure_attendance_records"):
        resp = admin_client.post(f"/teams/{team.id}/edit", data=data,
                                 follow_redirects=False)

    assert resp.status_code == 302

    from models.event import Event
    from models.team_recurring_schedule import TeamRecurringSchedule
    db.expire_all()

    scheds = db.query(TeamRecurringSchedule).filter_by(team_id=team.id).all()
    assert len(scheds) == 1

    events = (db.query(Event).filter_by(team_id=team.id)
              .order_by(Event.event_date).all())
    assert len(events) == 4  # Mar 3, 10, 17, 24
    assert events[0].event_date == date(2026, 3, 3)
    assert all(e.recurrence_group_id == scheds[0].recurrence_group_id for e in events)


def test_changed_schedule_triggers_confirmation(admin_client, db):
    from models.team_recurring_schedule import TeamRecurringSchedule
    from services.schedule_service import new_group_id

    team = _make_team_for_sched(db)
    sched = TeamRecurringSchedule(
        team_id=team.id, title="Eagles - Training Tuesday",
        event_type="training", recurrence_rule="weekly",
        start_date=date(2026, 3, 3), end_date=date(2026, 3, 24),
        presence_type="normal", recurrence_group_id=new_group_id(),
    )
    db.add(sched)
    db.commit()
    db.refresh(sched)

    # Change the start_date — should trigger confirmation step
    data = {"name": team.name, "description": "", "season_id": ""}
    data.update(_sched_form_data(sched_id=str(sched.id), start="2026-03-10"))

    resp = admin_client.post(f"/teams/{team.id}/edit", data=data,
                             follow_redirects=False)

    assert resp.status_code == 200
    assert b"confirm" in resp.content.lower()


def test_confirmed_schedule_regenerates_events(admin_client, db):
    from models.event import Event
    from models.team_recurring_schedule import TeamRecurringSchedule
    from services.schedule_service import new_group_id, sign_payload

    team = _make_team_for_sched(db)
    group_id = new_group_id()
    sched = TeamRecurringSchedule(
        team_id=team.id, title="Eagles - Training Tuesday",
        event_type="training", recurrence_rule="weekly",
        start_date=date(2026, 3, 3), end_date=date(2026, 3, 24),
        presence_type="normal", recurrence_group_id=group_id,
    )
    db.add(sched)
    future_ev = Event(
        title="Eagles - Training Tuesday", event_type="training",
        event_date=date(2099, 3, 10), recurrence_group_id=group_id,
        team_id=team.id,
    )
    db.add(future_ev)
    db.commit()
    db.refresh(sched)
    old_ev_id = future_ev.id

    payload = sign_payload({"team_id": team.id, "rows": [{
        "id": str(sched.id),
        "recurrence_group_id": group_id,
        "title": "Eagles - Training Tuesday",
        "event_type": "training",
        "recurrence_rule": "weekly",
        "start_date": "2026-03-10",  # changed
        "end_date": "2026-03-24",
        "event_time": "",
        "event_end_time": "",
        "location": "",
        "meeting_time": "",
        "meeting_location": "",
        "presence_type": "normal",
        "description": "",
    }]})

    data = {
        "name": team.name, "description": "", "season_id": "",
        "_confirm_step": "1",
        "_schedules_json": payload,
        f"confirm_schedule_{sched.id}": "on",
    }

    with patch("services.schedule_service.ensure_attendance_records"):
        resp = admin_client.post(f"/teams/{team.id}/edit", data=data,
                                 follow_redirects=False)

    assert resp.status_code == 302

    db.expire_all()
    # Old future event was deleted (verify by date since SQLite may reuse the auto-inc ID)
    assert db.query(Event).filter_by(team_id=team.id, event_date=date(2099, 3, 10)).first() is None
    # New events start from new start_date
    events = (db.query(Event).filter_by(team_id=team.id)
              .order_by(Event.event_date).all())
    assert len(events) > 0
    assert events[0].event_date == date(2026, 3, 10)
    # New events must have a different recurrence_group_id (regeneration assigns new UUID)
    assert events[0].recurrence_group_id != group_id


def test_removed_schedule_without_confirm_keeps_events(admin_client, db):
    from models.event import Event
    from models.team_recurring_schedule import TeamRecurringSchedule
    from services.schedule_service import new_group_id, sign_payload

    team = _make_team_for_sched(db)
    group_id = new_group_id()
    sched = TeamRecurringSchedule(
        team_id=team.id, title="T", event_type="training",
        recurrence_rule="weekly", start_date=date(2026, 3, 3),
        end_date=date(2026, 3, 24), presence_type="normal",
        recurrence_group_id=group_id,
    )
    db.add(sched)
    future_ev = Event(
        title="T", event_type="training", event_date=date(2099, 1, 1),
        recurrence_group_id=group_id, team_id=team.id,
    )
    db.add(future_ev)
    db.commit()
    db.refresh(sched)
    ev_id = future_ev.id
    sched_id = sched.id

    # Confirmation step: schedule removed, checkbox NOT checked
    payload = sign_payload({"team_id": team.id, "rows": []})
    data = {
        "name": team.name, "description": "", "season_id": "",
        "_confirm_step": "1",
        "_schedules_json": payload,
        # confirm_schedule_{id} absent = unchecked
    }

    resp = admin_client.post(f"/teams/{team.id}/edit", data=data,
                             follow_redirects=False)

    assert resp.status_code == 302
    db.expire_all()
    assert db.query(TeamRecurringSchedule).filter_by(id=sched_id).first() is not None
    assert db.query(Event).filter_by(id=ev_id).first() is not None


def test_removed_schedule_with_confirm_deletes_events(admin_client, db):
    from models.event import Event
    from models.team_recurring_schedule import TeamRecurringSchedule
    from services.schedule_service import new_group_id, sign_payload

    team = _make_team_for_sched(db)
    group_id = new_group_id()
    sched = TeamRecurringSchedule(
        team_id=team.id, title="T", event_type="training",
        recurrence_rule="weekly", start_date=date(2026, 3, 3),
        end_date=date(2026, 3, 24), presence_type="normal",
        recurrence_group_id=group_id,
    )
    db.add(sched)
    future_ev = Event(
        title="T", event_type="training", event_date=date(2099, 1, 1),
        recurrence_group_id=group_id, team_id=team.id,
    )
    db.add(future_ev)
    db.commit()
    db.refresh(sched)
    ev_id = future_ev.id
    sched_id = sched.id

    # Confirmation step: schedule removed, checkbox IS checked
    payload = sign_payload({"team_id": team.id, "rows": []})
    data = {
        "name": team.name, "description": "", "season_id": "",
        "_confirm_step": "1",
        "_schedules_json": payload,
        f"confirm_schedule_{sched_id}": "on",  # checked
    }

    resp = admin_client.post(f"/teams/{team.id}/edit", data=data,
                             follow_redirects=False)

    assert resp.status_code == 302
    db.expire_all()
    # Schedule is deleted
    assert db.query(TeamRecurringSchedule).filter_by(id=sched_id).first() is None
    # Future event is deleted
    assert db.query(Event).filter_by(id=ev_id).first() is None


def test_changed_schedule_unconfirmed_saves_fields_keeps_events(admin_client, db):
    """Changed schedule with checkbox unchecked: fields updated, events untouched."""
    from models.event import Event
    from models.team_recurring_schedule import TeamRecurringSchedule
    from services.schedule_service import new_group_id, sign_payload

    team = _make_team_for_sched(db)
    group_id = new_group_id()
    sched = TeamRecurringSchedule(
        team_id=team.id, title="Eagles - Training Tuesday",
        event_type="training", recurrence_rule="weekly",
        start_date=date(2026, 3, 3), end_date=date(2026, 3, 24),
        event_time=None, presence_type="normal",
        recurrence_group_id=group_id,
    )
    db.add(sched)
    future_ev = Event(
        title="Eagles - Training Tuesday", event_type="training",
        event_date=date(2099, 3, 10), recurrence_group_id=group_id,
        team_id=team.id,
    )
    db.add(future_ev)
    db.commit()
    db.refresh(sched)
    ev_id = future_ev.id
    sched_id = sched.id
    original_ev_date = future_ev.event_date

    # Confirmation step: start_date changed, checkbox NOT checked
    payload = sign_payload({"team_id": team.id, "rows": [{
        "id": str(sched.id),
        "recurrence_group_id": group_id,
        "title": "Eagles - Training Tuesday",
        "event_type": "training",
        "recurrence_rule": "weekly",
        "start_date": "2026-03-10",  # key field changed
        "end_date": "2026-03-24",
        "event_time": "",
        "event_end_time": "",
        "location": "",
        "meeting_time": "",
        "meeting_location": "",
        "presence_type": "normal",
        "description": "",
    }]})
    data = {
        "name": team.name, "description": "", "season_id": "",
        "_confirm_step": "1",
        "_schedules_json": payload,
        # confirm_schedule_{id} absent = unchecked
    }

    resp = admin_client.post(f"/teams/{team.id}/edit", data=data,
                             follow_redirects=False)

    assert resp.status_code == 302
    db.expire_all()
    # Schedule fields were updated
    updated = db.query(TeamRecurringSchedule).filter_by(id=sched_id).first()
    assert updated is not None
    assert updated.start_date == date(2026, 3, 10)
    # Future event was NOT touched (same id, same date, same recurrence_group_id)
    ev = db.query(Event).filter_by(id=ev_id).first()
    assert ev is not None
    assert ev.event_date == original_ev_date
    assert ev.recurrence_group_id == group_id
