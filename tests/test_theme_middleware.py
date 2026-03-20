"""Tests for theme resolution in LocaleMiddleware."""

from __future__ import annotations


def test_theme_defaults_to_light(client):
    """No cookie → data-theme="light" in rendered HTML."""
    resp = client.get("/auth/login")
    assert resp.status_code == 200
    assert 'data-theme="light"' in resp.text


def test_theme_cookie_dark(client):
    """theme=dark cookie → data-theme="dark"."""
    client.cookies.set("theme", "dark")
    resp = client.get("/auth/login")
    assert 'data-theme="dark"' in resp.text


def test_theme_cookie_invalid_defaults_to_light(client):
    """Invalid theme cookie value falls back to light."""
    client.cookies.set("theme", "purple")
    resp = client.get("/auth/login")
    assert 'data-theme="light"' in resp.text
