"""tests/test_telegram_webhook.py — Webhook route tests."""
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def test_webhook_rejects_missing_secret(client: TestClient):
    resp = client.post("/telegram/webhook", json={"update_id": 1})
    assert resp.status_code == 403


def test_webhook_rejects_wrong_secret(client: TestClient):
    resp = client.post(
        "/telegram/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
    )
    assert resp.status_code == 403


def test_webhook_accepts_correct_secret(client: TestClient):
    mock_settings = MagicMock()
    mock_settings.TELEGRAM_WEBHOOK_SECRET = "test-secret"

    with patch("routes.telegram.settings", mock_settings):
        with patch("routes.telegram._get_app", return_value=None):
            resp = client.post(
                "/telegram/webhook",
                json={"update_id": 1},
                headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
            )
    assert resp.status_code == 200


def test_webhook_returns_200_when_bot_disabled(client: TestClient):
    mock_settings = MagicMock()
    mock_settings.TELEGRAM_WEBHOOK_SECRET = "test-secret"

    with patch("routes.telegram.settings", mock_settings):
        with patch("routes.telegram._get_app", return_value=None):
            resp = client.post(
                "/telegram/webhook",
                json={"update_id": 1},
                headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
            )
    assert resp.status_code == 200
