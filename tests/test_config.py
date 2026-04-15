"""Tests for app/config.py settings defaults."""


def test_app_url_default():
    from app.config import settings
    assert settings.APP_URL == "http://localhost:7000"
