"""Unit tests for services/auth_service magic link helpers."""

from __future__ import annotations

import importlib

import pytest


def _reload_settings(monkeypatch, app_url: str):
    """Helper to reload settings with a specific APP_URL.

    This function modifies global state and should only be used within tests
    that are isolated via fixtures or autouse cleanup.
    """
    monkeypatch.setenv("APP_URL", app_url)
    import app.config as cfg_mod
    importlib.reload(cfg_mod)
    from app.config import Settings
    cfg_mod.settings = Settings()
    import services.auth_service as svc
    importlib.reload(svc)
    return svc


@pytest.fixture(autouse=True)
def _restore_app_config(monkeypatch):
    """Auto-restore app.config after each test to avoid affecting other tests."""
    yield
    # Reload config back to defaults after test
    monkeypatch.delenv("APP_URL", raising=False)
    import app.config as cfg_mod
    importlib.reload(cfg_mod)
    from app.config import Settings
    cfg_mod.settings = Settings()
    import services.auth_service as svc
    importlib.reload(svc)


def test_create_magic_link_returns_none_for_localhost(monkeypatch):
    """When APP_URL is the default localhost value, return None."""
    svc = _reload_settings(monkeypatch, "http://localhost:7000")
    assert svc.create_magic_link(1, "/dashboard") is None


def test_create_magic_link_returns_url(monkeypatch):
    """When APP_URL is a real URL, return a full /auth/magic URL."""
    svc = _reload_settings(monkeypatch, "https://example.com")
    url = svc.create_magic_link(42, "/events/7")
    assert url is not None
    assert url.startswith("https://example.com/auth/magic?token=")


def test_verify_magic_link_round_trip(monkeypatch):
    """create then verify returns original user_id and path."""
    svc = _reload_settings(monkeypatch, "https://example.com")
    url = svc.create_magic_link(5, "/events/3")
    assert url is not None
    token = url.split("token=", 1)[1]
    user_id, path = svc.verify_magic_link(token)
    assert user_id == 5
    assert path == "/events/3"


def test_verify_magic_link_invalid_raises():
    """A tampered token raises an exception."""
    from services.auth_service import verify_magic_link
    with pytest.raises(Exception):
        verify_magic_link("this.is.not.a.valid.token")
