from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _player(chat_id: str | None = "123456"):
    p = MagicMock()
    p.id = 1
    p.user = MagicMock()
    p.user.telegram_chat_id = chat_id
    return p


def _notif(event_id: int | None = 42, tag: str = "event_new"):
    n = MagicMock()
    n.title = "Training"
    n.body = "Tue 29 Apr 18:00 · Sports Center"
    n.tag = tag
    n.event_id = event_id
    return n


def test_returns_false_when_no_chat_id():
    from services.channels.telegram_channel import TelegramChannel
    assert TelegramChannel().send(_player(chat_id=None), _notif()) is False


def test_returns_false_when_no_user():
    from services.channels.telegram_channel import TelegramChannel
    p = MagicMock()
    p.user = None
    assert TelegramChannel().send(p, _notif()) is False


def test_returns_false_when_no_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    from services.channels.telegram_channel import TelegramChannel
    assert TelegramChannel().send(_player(), _notif()) is False


def test_posts_to_telegram_api(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    resp = MagicMock()
    resp.ok = True
    from services.channels.telegram_channel import TelegramChannel
    with patch("services.channels.telegram_channel.requests.post", return_value=resp) as mock_post:
        result = TelegramChannel().send(_player("999"), _notif(event_id=42, tag="event_new"))
    assert result is True
    payload = mock_post.call_args.kwargs["json"]
    assert payload["chat_id"] == "999"
    assert "📅" in payload["text"]
    assert "Training" in payload["text"]
    buttons = payload["reply_markup"]["inline_keyboard"][0]
    assert any(b["callback_data"] == "evt:42" for b in buttons)
    assert any(b["callback_data"] == "evts:0" for b in buttons)


def test_no_buttons_when_no_event_id(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    resp = MagicMock()
    resp.ok = True
    from services.channels.telegram_channel import TelegramChannel
    with patch("services.channels.telegram_channel.requests.post", return_value=resp) as mock_post:
        TelegramChannel().send(_player(), _notif(event_id=None))
    assert "reply_markup" not in mock_post.call_args.kwargs["json"]


def test_returns_false_on_api_error(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    resp = MagicMock()
    resp.ok = False
    resp.status_code = 400
    resp.text = "Bad Request"
    from services.channels.telegram_channel import TelegramChannel
    with patch("services.channels.telegram_channel.requests.post", return_value=resp):
        assert TelegramChannel().send(_player(), _notif()) is False


def test_returns_false_on_request_exception(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    from services.channels.telegram_channel import TelegramChannel
    with patch("services.channels.telegram_channel.requests.post", side_effect=Exception("timeout")):
        assert TelegramChannel().send(_player(), _notif()) is False


@pytest.mark.parametrize("tag,emoji", [
    ("event_new", "📅"),
    ("event_update", "✏️"),
    ("reminder", "⏰"),
    ("announcement", "📅"),
    ("direct", "📬"),
    ("unknown_tag", "📬"),
])
def test_emoji_mapping(monkeypatch, tag, emoji):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    resp = MagicMock()
    resp.ok = True
    from services.channels.telegram_channel import TelegramChannel
    with patch("services.channels.telegram_channel.requests.post", return_value=resp) as mock_post:
        TelegramChannel().send(_player(), _notif(tag=tag))
    assert emoji in mock_post.call_args.kwargs["json"]["text"]
