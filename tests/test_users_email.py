"""Tests that users routes call new send functions (not raw send_email)."""
import pytest
from unittest.mock import patch
from tests.conftest import *  # noqa: F401,F403


def test_register_calls_send_welcome_email(admin_client, db):
    """POST /auth/users/register calls send_welcome_email, not raw send_email."""
    with patch("routes.users.send_welcome_email") as mock_welcome:
        response = admin_client.post(
            "/auth/users/register",
            data={
                "username": "newuser",
                "email": "new@example.com",
                "password": "password123",
                "role": "member",
                "locale": "en",
            },
        )
        # Either redirect (302) or success page (200)
        assert response.status_code in (200, 302)
        mock_welcome.assert_called_once()


def test_reset_calls_send_reset_email(admin_client, db, member_user):
    """POST /auth/users/{id}/reset-password calls send_reset_email, not raw send_email."""
    with patch("routes.users.send_reset_email") as mock_reset:
        response = admin_client.post(
            f"/auth/users/{member_user.id}/reset-password",
        )
        assert response.status_code in (200, 302)
        mock_reset.assert_called_once()
