"""Tests for app/config.py settings defaults."""


def test_app_url_default():
    from app.config import settings
    assert settings.APP_URL == "http://localhost:7000"


def test_app_timezone_default():
    from app.config import Settings
    s = Settings()
    assert s.APP_TIMEZONE == "UTC"
