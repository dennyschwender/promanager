"""Tests that email_channel uses send_notification_email."""
import pytest
from unittest.mock import patch, MagicMock


def test_email_channel_calls_send_notification_email():
    """EmailChannel.send() calls send_notification_email, not raw send_email."""
    from services.channels.email_channel import EmailChannel
    channel = EmailChannel()

    mock_user = MagicMock()
    mock_user.email = "alice@example.com"
    mock_user.locale = "en"
    mock_user.id = 42

    mock_notification = MagicMock()
    mock_notification.title = "Training cancelled"
    mock_notification.body = "No training on Friday."

    with patch("services.channels.email_channel.send_notification_email") as mock_fn:
        channel.send(mock_user, mock_notification)
        mock_fn.assert_called_once()
        call_kwargs = mock_fn.call_args[1] if mock_fn.call_args[1] else {}
        call_args = mock_fn.call_args[0] if mock_fn.call_args[0] else ()
        # Check the recipient email is passed
        all_args = list(call_args) + list(call_kwargs.values())
        assert "alice@example.com" in all_args or call_kwargs.get("to") == "alice@example.com"
