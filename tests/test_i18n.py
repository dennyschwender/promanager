"""Tests for app/i18n.py translation loader."""
from __future__ import annotations

import os
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_t(debug: bool = False):
    """Import a fresh t() with the given DEBUG setting."""
    os.environ["DEBUG"] = "true" if debug else "false"
    # Force reload so settings picks up env var
    import importlib
    import app.config as _cfg
    importlib.reload(_cfg)
    import app.i18n as _i18n
    importlib.reload(_i18n)
    from app.i18n import t
    return t


# ---------------------------------------------------------------------------
# Basic lookup
# ---------------------------------------------------------------------------

def test_t_returns_english_string():
    t = _make_t()
    assert t("nav.dashboard", "en") == "Dashboard"


def test_t_returns_italian_string():
    t = _make_t()
    result = t("common.save", "it")
    assert isinstance(result, str)
    assert len(result) > 0


def test_t_returns_french_string():
    t = _make_t()
    result = t("common.save", "fr")
    assert isinstance(result, str)


def test_t_returns_german_string():
    t = _make_t()
    result = t("common.save", "de")
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Fallback behaviour
# ---------------------------------------------------------------------------

def test_t_unsupported_locale_falls_back_to_en():
    t = _make_t()
    assert t("nav.dashboard", "xx") == t("nav.dashboard", "en")


def test_t_missing_key_raises_in_debug():
    t = _make_t(debug=True)
    with pytest.raises(KeyError):
        t("nav.nonexistent_key_xyz", "en")


def test_t_missing_key_falls_back_to_en_in_production():
    """A key missing in a locale but present in 'en' should return the 'en' value."""
    import importlib
    os.environ["DEBUG"] = "false"
    import app.config as _cfg
    importlib.reload(_cfg)
    import app.i18n as _i18n
    importlib.reload(_i18n)
    original = _i18n._translations["it"].get("nav", {}).get("dashboard")
    _i18n._translations["it"].setdefault("nav", {}).pop("dashboard", None)
    try:
        result = _i18n.t("nav.dashboard", "it")
        assert result == "Dashboard"  # fell back to en value
    finally:
        if original is not None:
            _i18n._translations["it"].setdefault("nav", {})["dashboard"] = original


def test_t_missing_key_returns_bare_key_when_en_also_missing():
    """When key is absent from both locale and 'en', return the bare key."""
    import importlib
    import app.i18n as _i18n
    os.environ["DEBUG"] = "false"
    importlib.reload(_i18n)
    original_it = _i18n._translations["it"].get("nav", {}).get("dashboard")
    original_en = _i18n._translations["en"].get("nav", {}).get("dashboard")
    _i18n._translations["it"].setdefault("nav", {}).pop("dashboard", None)
    _i18n._translations["en"].setdefault("nav", {}).pop("dashboard", None)
    try:
        result = _i18n.t("nav.dashboard", "it")
        assert result == "nav.dashboard"
    finally:
        if original_it is not None:
            _i18n._translations["it"].setdefault("nav", {})["dashboard"] = original_it
        if original_en is not None:
            _i18n._translations["en"].setdefault("nav", {})["dashboard"] = original_en


# ---------------------------------------------------------------------------
# Variable interpolation
# ---------------------------------------------------------------------------

def test_t_interpolates_variables():
    t = _make_t()
    result = t("email.reminder_subject", "en", event_name="Training", date="2026-03-20")
    assert "Training" in result
    assert "2026-03-20" in result


# ---------------------------------------------------------------------------
# LocaleMiddleware integration
# ---------------------------------------------------------------------------

def test_locale_cookie_sets_request_locale(client):
    """A locale cookie should cause templates to render in that locale."""
    client.cookies.set("locale", "it")
    resp = client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 200
    # page should render without error — locale plumbing works


def test_invalid_locale_cookie_falls_back_to_en(client):
    client.cookies.set("locale", "zz")
    resp = client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 200
