"""Tests for /seasons routes."""
import pytest
from models.season import Season


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_seasons_list(admin_client):
    resp = admin_client.get("/seasons", follow_redirects=False)
    assert resp.status_code == 200


def test_seasons_requires_login(client):
    resp = client.get("/seasons", follow_redirects=False)
    assert resp.status_code == 302
    assert "/auth/login" in resp.headers["location"]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_season(admin_client, db):
    resp = admin_client.post(
        "/seasons/new",
        data={"name": "2025/26", "start_date": "2025-09-01", "end_date": "2026-05-31"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert db.query(Season).filter(Season.name == "2025/26").first() is not None


def test_create_season_blank_name(admin_client):
    resp = admin_client.post(
        "/seasons/new",
        data={"name": "   ", "start_date": "", "end_date": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Edit
# ---------------------------------------------------------------------------


def test_edit_season(admin_client, db):
    season = Season(name="OldName")
    db.add(season)
    db.commit()
    db.refresh(season)

    resp = admin_client.post(
        f"/seasons/{season.id}/edit",
        data={"name": "NewName", "start_date": "", "end_date": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db.refresh(season)
    assert season.name == "NewName"


# ---------------------------------------------------------------------------
# Activate
# ---------------------------------------------------------------------------


def test_activate_season(admin_client, db):
    s1 = Season(name="Season A", is_active=True)
    s2 = Season(name="Season B", is_active=False)
    db.add_all([s1, s2])
    db.commit()
    db.refresh(s1)
    db.refresh(s2)

    resp = admin_client.post(f"/seasons/{s2.id}/activate", follow_redirects=False)
    assert resp.status_code == 302

    db.refresh(s1)
    db.refresh(s2)
    assert s2.is_active is True
    assert s1.is_active is False


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_season(admin_client, db):
    season = Season(name="ToDelete")
    db.add(season)
    db.commit()
    db.refresh(season)
    sid = season.id

    resp = admin_client.post(f"/seasons/{sid}/delete", follow_redirects=False)
    assert resp.status_code == 302
    assert db.get(Season, sid) is None
