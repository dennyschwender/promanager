# tests/test_telegram_notifications.py
from __future__ import annotations
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_notify_coaches_sends_to_coaches_with_telegram():
    mock_coach_user = MagicMock()
    mock_coach_user.telegram_chat_id = "coach_chat_id"
    mock_ut = MagicMock()
    mock_ut.user = mock_coach_user
    mock_ut.user_id = 10

    mock_event = MagicMock()
    mock_event.id = 1
    mock_event.title = "Training"
    mock_event.event_date = MagicMock()
    mock_event.event_date.strftime.return_value = "29 Apr"
    mock_event.team_id = 10

    mock_player = MagicMock()
    mock_player.first_name = "John"
    mock_player.last_name = "Doe"

    mock_db = MagicMock()
    mock_db.get.side_effect = lambda model, pk: mock_event if pk == 1 else mock_player
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_ut]

    import bot as _bot
    import app.database as _db_mod
    with (
        patch.object(_bot, "telegram_app") as mock_app,
        patch.object(_db_mod, "SessionLocal", return_value=mock_db),
    ):
        mock_app.bot.send_message = AsyncMock()
        from services.telegram_notifications import notify_coaches_via_telegram
        await notify_coaches_via_telegram(event_id=1, player_id=5, new_status="absent")
        mock_app.bot.send_message.assert_called_once()
        call_kwargs = mock_app.bot.send_message.call_args.kwargs
        assert call_kwargs["chat_id"] == "coach_chat_id"
        assert "John" in call_kwargs["text"]
        assert "absent" in call_kwargs["text"]


@pytest.mark.asyncio
async def test_notify_coaches_skips_when_bot_not_initialized():
    import bot as _bot
    with patch.object(_bot, "telegram_app", None):
        from services.telegram_notifications import notify_coaches_via_telegram
        # Should complete without error
        await notify_coaches_via_telegram(event_id=1, player_id=5, new_status="absent")


@pytest.mark.asyncio
async def test_notify_coaches_deduplicates_chat_ids():
    """Two coaches sharing the same Telegram account → only one message sent."""
    shared_chat_id = "shared_id"
    mock_ut1 = MagicMock()
    mock_ut1.user = MagicMock()
    mock_ut1.user.telegram_chat_id = shared_chat_id
    mock_ut1.user_id = 10
    mock_ut2 = MagicMock()
    mock_ut2.user = MagicMock()
    mock_ut2.user.telegram_chat_id = shared_chat_id
    mock_ut2.user_id = 11

    mock_event = MagicMock()
    mock_event.id = 1
    mock_event.title = "Match"
    mock_event.event_date = MagicMock()
    mock_event.event_date.strftime.return_value = "29 Apr"
    mock_event.team_id = 5

    mock_player = MagicMock()
    mock_player.first_name = "Jane"
    mock_player.last_name = "Smith"

    mock_db = MagicMock()
    mock_db.get.side_effect = lambda model, pk: mock_event if pk == 1 else mock_player
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_ut1, mock_ut2]

    import bot as _bot
    import app.database as _db_mod
    with (
        patch.object(_bot, "telegram_app") as mock_app,
        patch.object(_db_mod, "SessionLocal", return_value=mock_db),
    ):
        mock_app.bot.send_message = AsyncMock()
        from services.telegram_notifications import notify_coaches_via_telegram
        await notify_coaches_via_telegram(event_id=1, player_id=5, new_status="present")
        # Only 1 message despite 2 coaches with same chat_id
        assert mock_app.bot.send_message.call_count == 1
