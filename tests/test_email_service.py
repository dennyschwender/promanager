"""Tests for services/email_service template rendering and send functions."""

from __future__ import annotations

import datetime


def test_render_email_template_reminder_contains_name():
    """reminder.html renders with player name in output."""
    from services.email_service import render_email_template
    html = render_email_template("reminder", {
        "name": "Alice",
        "event_title": "Training",
        "when": "2026-04-20 19:30",
        "location": "Gym",
        "magic_link": None,
    })
    assert "Alice" in html
    assert "Training" in html
    assert "Gym" in html


def test_render_email_template_button_shown_with_magic_link():
    """base.html renders the login button only when magic_link is set."""
    from services.email_service import render_email_template
    html = render_email_template("welcome", {
        "username": "bob",
        "password": "secret",
        "magic_link": "https://example.com/auth/magic?token=abc",
    })
    assert "https://example.com/auth/magic?token=abc" in html


def test_render_email_template_no_button_when_no_magic_link():
    """base.html omits the login button when magic_link is None."""
    from services.email_service import render_email_template
    html = render_email_template("welcome", {
        "username": "bob",
        "password": "secret",
        "magic_link": None,
    })
    assert "/auth/magic" not in html


def test_strip_html_removes_tags():
    from services.email_service import _strip_html
    result = _strip_html("<p>Hello <strong>World</strong></p>")
    assert result == "Hello World"


def test_strip_html_br_becomes_newline():
    from services.email_service import _strip_html
    result = _strip_html("Line1<br>Line2<br/>Line3")
    assert "Line1" in result
    assert "Line2" in result
    assert "\n" in result


def test_send_event_reminder_uses_template(monkeypatch):
    """send_event_reminder sends HTML from template, not from locale body string."""
    sent = {}

    def mock_send(to, subject, body_html, body_text=""):
        sent["html"] = body_html
        sent["text"] = body_text
        return True

    monkeypatch.setattr("services.email_service.send_email", mock_send)

    from services.email_service import send_event_reminder
    send_event_reminder(
        player_email="p@test.com",
        player_name="Mario",
        event_title="NLB Final",
        event_date=datetime.date(2026, 4, 20),
        event_time=datetime.time(19, 30),
        event_location="Arena",
        locale="en",
    )
    assert "Mario" in sent["html"]
    assert "NLB Final" in sent["html"]
    assert "<!DOCTYPE html" in sent["html"]
    assert "Mario" in sent["text"]
    assert "<" not in sent["text"]  # plain text has no HTML tags


def test_send_welcome_email_sends_credentials(monkeypatch):
    sent = {}

    def mock_send(to, subject, body_html, body_text=""):
        sent["html"] = body_html
        sent["to"] = to
        return True

    monkeypatch.setattr("services.email_service.send_email", mock_send)

    from services.email_service import send_welcome_email
    send_welcome_email(
        to="user@test.com",
        username="testuser",
        password="Abc123!",
        locale="en",
        magic_link=None,
    )
    assert sent["to"] == "user@test.com"
    assert "testuser" in sent["html"]
    assert "Abc123!" in sent["html"]


def test_send_reset_email_sends_credentials(monkeypatch):
    sent = {}

    def mock_send(to, subject, body_html, body_text=""):
        sent["html"] = body_html
        return True

    monkeypatch.setattr("services.email_service.send_email", mock_send)

    from services.email_service import send_reset_email
    send_reset_email(
        to="user@test.com",
        username="testuser",
        password="NewPass99!",
        locale="en",
        magic_link=None,
    )
    assert "testuser" in sent["html"]
    assert "NewPass99!" in sent["html"]


def test_send_notification_email_sends_content(monkeypatch):
    sent = {}

    def mock_send(to, subject, body_html, body_text=""):
        sent["subject"] = subject
        sent["html"] = body_html
        return True

    monkeypatch.setattr("services.email_service.send_email", mock_send)

    from services.email_service import send_notification_email
    send_notification_email(
        to="user@test.com",
        title="Match cancelled",
        body="The match on Friday has been cancelled.",
        locale="en",
        magic_link=None,
    )
    assert "Match cancelled" in sent["html"]
    assert "Friday" in sent["html"]
