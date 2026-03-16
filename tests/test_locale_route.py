"""Tests for POST /set-locale."""

from __future__ import annotations


def test_set_locale_sets_cookie(client):
    resp = client.post(
        "/set-locale",
        data={"locale": "it", "next": "/dashboard"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"
    assert resp.cookies.get("locale") == "it"


def test_set_locale_invalid_locale_returns_400(client):
    resp = client.post(
        "/set-locale",
        data={"locale": "xx"},
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_set_locale_defaults_redirect_to_dashboard(client):
    resp = client.post(
        "/set-locale",
        data={"locale": "fr"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"


def test_set_locale_rejects_external_next(client):
    resp = client.post(
        "/set-locale",
        data={"locale": "de", "next": "https://evil.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"


def test_set_locale_rejects_protocol_relative_next(client):
    resp = client.post(
        "/set-locale",
        data={"locale": "it", "next": "//evil.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert resp.headers["location"] == "/dashboard"


def test_set_locale_updates_user_db(admin_client, admin_user, db):
    resp = admin_client.post(
        "/set-locale",
        data={"locale": "de", "next": "/dashboard"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db.refresh(admin_user)
    assert admin_user.locale == "de"
