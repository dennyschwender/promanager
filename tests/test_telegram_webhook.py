"""tests/test_telegram_webhook.py — Webhook route tests."""
from unittest.mock import AsyncMock, MagicMock, patch

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


def test_webhook_returns_200_when_bot_disabled(client: TestClient, monkeypatch):
    """When the bot app is None (not configured), the route still returns 200."""
    from app.config import settings
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "test-secret")

    with patch("routes.telegram._get_app", return_value=None):
        resp = client.post(
            "/telegram/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_webhook_dispatches_update_when_bot_enabled(client: TestClient, monkeypatch):
    """When the bot app is present, process_update is called and returns 200."""
    from app.config import settings
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "test-secret")

    mock_bot = MagicMock()
    mock_bot.de_json.return_value = MagicMock()

    mock_app = MagicMock()
    mock_app.bot = mock_bot
    mock_app.process_update = AsyncMock(return_value=None)

    with patch("routes.telegram._get_app", return_value=mock_app), \
         patch("routes.telegram.Update.de_json", return_value=MagicMock()):
        resp = client.post(
            "/telegram/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    mock_app.process_update.assert_called_once()
