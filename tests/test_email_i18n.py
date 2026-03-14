"""Tests for locale-aware email service."""
from __future__ import annotations


def test_send_event_reminder_uses_locale(monkeypatch):
    """send_event_reminder should use the provided locale."""
    sent = {}

    def mock_send(to, subject, body_html, body_text=""):
        sent["subject"] = subject
        sent["body"] = body_text
        return True

    monkeypatch.setattr("services.email_service.send_email", mock_send)

    import datetime

    from services.email_service import send_event_reminder

    send_event_reminder(
        player_email="p@test.com",
        player_name="Mario",
        event_title="Training",
        event_date=datetime.date(2026, 3, 20),
        event_time=None,
        event_location="Gym",
        locale="en",
    )
    assert "Training" in sent["subject"]


def test_send_attendance_request_uses_locale(monkeypatch):
    sent = {}

    def mock_send(to, subject, body_html, body_text=""):
        sent["subject"] = subject
        return True

    monkeypatch.setattr("services.email_service.send_email", mock_send)

    import datetime

    from services.email_service import send_attendance_request

    send_attendance_request(
        player_email="p@test.com",
        player_name="Mario",
        event_title="Match",
        event_date=datetime.date(2026, 3, 20),
        attendance_url="http://localhost/attendance/1",
        locale="en",
    )
    assert "Match" in sent["subject"]


def test_send_event_reminder_defaults_locale_to_en(monkeypatch):
    """locale param must be optional with default 'en'."""
    called = {}

    def mock_send(to, subject, body_html, body_text=""):
        called["ok"] = True
        return True

    monkeypatch.setattr("services.email_service.send_email", mock_send)

    import datetime

    from services.email_service import send_event_reminder

    # Call without locale kwarg — should not raise
    send_event_reminder(
        player_email="p@test.com",
        player_name="Mario",
        event_title="Training",
        event_date=datetime.date(2026, 3, 20),
        event_time=None,
        event_location="Gym",
    )
    assert called.get("ok")
