# tests/test_telegram_notifications.py
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_coach(user_id: int, chat_id: str | None, players: list = None):
    user = MagicMock()
    user.telegram_chat_id = chat_id
    user.players = players or []
    ut = MagicMock()
    ut.user = user
    ut.user_id = user_id
    return ut


def _make_mock_db(event, player_or_ext, coaches, *, model_map: dict | None = None):
    """Build a mock DB session. model_map: {ModelClass: object} for db.get overrides."""
    from models.event import Event
    from models.player import Player

    defaults = {Event: event, Player: player_or_ext}
    if model_map:
        defaults.update(model_map)

    mock_db = MagicMock()
    mock_db.get.side_effect = lambda model, pk: defaults.get(model, MagicMock())
    mock_db.query.return_value.filter.return_value.all.return_value = coaches
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.query.return_value.filter.return_value.count.return_value = 1
    return mock_db


def _make_bot_app():
    """Create a mock telegram Application with AsyncMock for send_message."""
    app = MagicMock()
    app.bot.send_message = AsyncMock()
    return app


def _make_event(team_id=10, title="Training"):
    e = MagicMock()
    e.id = 1
    e.title = title
    e.team_id = team_id
    return e


def _make_player(first="John", last="Doe"):
    p = MagicMock()
    p.first_name = first
    p.last_name = last
    p.full_name = f"{first} {last}"
    return p


@pytest.mark.asyncio
async def test_notify_coaches_sends_telegram_to_coach_with_chat_id():
    """Coach with telegram_chat_id receives a Telegram push message."""
    coach = _make_coach(user_id=10, chat_id="chat123")
    mock_db = _make_mock_db(_make_event(), _make_player(), [coach])
    mock_app = _make_bot_app()

    import bot as _bot
    import app.database as _db_mod
    with (
        patch.object(_bot, "telegram_app", mock_app),
        patch.object(_db_mod, "SessionLocal", return_value=mock_db),
        patch("bot.navigation.inject_notification", new_callable=AsyncMock),
        patch("services.channels.inapp_channel.push_unread_count_to_user"),
        patch("services.channels.webpush_channel.WebPushChannel.send_to_user"),
    ):
        from services.telegram_notifications import notify_coaches_via_telegram
        await notify_coaches_via_telegram(event_id=1, player_id=5, new_status="absent")

    mock_app.bot.send_message.assert_called_once()
    kwargs = mock_app.bot.send_message.call_args.kwargs
    assert kwargs["chat_id"] == "chat123"
    assert "✗" in kwargs["text"]


@pytest.mark.asyncio
async def test_notify_coaches_creates_notification_for_coach_without_telegram():
    """Coach without Telegram still gets a Notification record (web/in-app channel)."""
    coach = _make_coach(user_id=10, chat_id=None)
    mock_db = _make_mock_db(_make_event(), _make_player(), [coach])
    mock_app = _make_bot_app()

    import bot as _bot
    import app.database as _db_mod
    with (
        patch.object(_bot, "telegram_app", mock_app),
        patch.object(_db_mod, "SessionLocal", return_value=mock_db),
        patch("services.channels.inapp_channel.push_unread_count_to_user"),
        patch("services.channels.webpush_channel.WebPushChannel.send_to_user"),
    ):
        from services.telegram_notifications import notify_coaches_via_telegram
        await notify_coaches_via_telegram(event_id=1, player_id=5, new_status="absent")

    mock_app.bot.send_message.assert_not_called()
    from models.notification import Notification
    added = [c.args[0] for c in mock_db.add.call_args_list]
    assert any(isinstance(obj, Notification) for obj in added)


@pytest.mark.asyncio
async def test_notify_coaches_skips_telegram_when_bot_not_initialized():
    """When telegram_app is None, no Telegram messages but Notification still created."""
    coach = _make_coach(user_id=10, chat_id="chat123")
    mock_db = _make_mock_db(_make_event(), _make_player(), [coach])

    import bot as _bot
    import app.database as _db_mod
    with (
        patch.object(_bot, "telegram_app", None),
        patch.object(_db_mod, "SessionLocal", return_value=mock_db),
        patch("services.channels.inapp_channel.push_unread_count_to_user"),
        patch("services.channels.webpush_channel.WebPushChannel.send_to_user"),
    ):
        from services.telegram_notifications import notify_coaches_via_telegram
        await notify_coaches_via_telegram(event_id=1, player_id=5, new_status="absent")

    from models.notification import Notification
    added = [c.args[0] for c in mock_db.add.call_args_list]
    assert any(isinstance(obj, Notification) for obj in added)


@pytest.mark.asyncio
async def test_notify_coaches_deduplicates_by_user_id():
    """Two UserTeam entries for same user_id → only one notification created."""
    coach1 = _make_coach(user_id=10, chat_id="chat123")
    coach2 = _make_coach(user_id=10, chat_id="chat123")  # duplicate user_id
    mock_db = _make_mock_db(_make_event(), _make_player(), [coach1, coach2])
    mock_app = _make_bot_app()

    import bot as _bot
    import app.database as _db_mod
    with (
        patch.object(_bot, "telegram_app", mock_app),
        patch.object(_db_mod, "SessionLocal", return_value=mock_db),
        patch("bot.navigation.inject_notification", new_callable=AsyncMock),
        patch("services.channels.inapp_channel.push_unread_count_to_user"),
        patch("services.channels.webpush_channel.WebPushChannel.send_to_user"),
    ):
        from services.telegram_notifications import notify_coaches_via_telegram
        await notify_coaches_via_telegram(event_id=1, player_id=5, new_status="present")

    mock_app.bot.send_message.assert_called_once()
    from models.notification import Notification
    notif_adds = [c for c in mock_db.add.call_args_list if isinstance(c.args[0], Notification)]
    assert len(notif_adds) == 1


@pytest.mark.asyncio
async def test_notify_coaches_deduplicates_shared_telegram_chat_id():
    """Two different users sharing same Telegram chat_id → one Telegram msg, two Notifications."""
    chat_id = "shared_id"
    coach1 = _make_coach(user_id=10, chat_id=chat_id)
    coach2 = _make_coach(user_id=11, chat_id=chat_id)
    mock_db = _make_mock_db(_make_event(), _make_player(), [coach1, coach2])
    mock_app = _make_bot_app()

    import bot as _bot
    import app.database as _db_mod
    with (
        patch.object(_bot, "telegram_app", mock_app),
        patch.object(_db_mod, "SessionLocal", return_value=mock_db),
        patch("bot.navigation.inject_notification", new_callable=AsyncMock),
        patch("services.channels.inapp_channel.push_unread_count_to_user"),
        patch("services.channels.webpush_channel.WebPushChannel.send_to_user"),
    ):
        from services.telegram_notifications import notify_coaches_via_telegram
        await notify_coaches_via_telegram(event_id=1, player_id=5, new_status="present")

    mock_app.bot.send_message.assert_called_once()
    from models.notification import Notification
    notif_adds = [c for c in mock_db.add.call_args_list if isinstance(c.args[0], Notification)]
    assert len(notif_adds) == 2  # one per distinct user_id


@pytest.mark.asyncio
async def test_notify_about_external_change_sends_telegram_and_notification():
    """External player status change notifies coaches via Telegram + Notification record."""
    coach = _make_coach(user_id=10, chat_id="chat123")
    mock_event = _make_event()
    mock_ext = MagicMock()
    mock_ext.full_name = "Guest Player"

    from models.event import Event
    from models.event_external import EventExternal

    mock_db = _make_mock_db(
        mock_event,
        mock_ext,
        [coach],
        model_map={Event: mock_event, EventExternal: mock_ext},
    )
    mock_app = _make_bot_app()

    import bot as _bot
    import app.database as _db_mod
    with (
        patch.object(_bot, "telegram_app", mock_app),
        patch.object(_db_mod, "SessionLocal", return_value=mock_db),
        patch("services.channels.inapp_channel.push_unread_count_to_user"),
        patch("services.channels.webpush_channel.WebPushChannel.send_to_user"),
    ):
        from services.telegram_notifications import notify_coaches_about_external_change
        await notify_coaches_about_external_change(event_id=1, ext_id=99, new_status="absent")

    mock_app.bot.send_message.assert_called_once()
    text = mock_app.bot.send_message.call_args.kwargs["text"]
    assert "ext" in text
    assert "✗" in text
    from models.notification import Notification
    notif_adds = [c for c in mock_db.add.call_args_list if isinstance(c.args[0], Notification)]
    assert len(notif_adds) == 1
