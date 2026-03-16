"""Tests for services/notification_templates.py."""

from services.notification_templates import TEMPLATES, TEMPLATES_BY_KEY, render_template


def test_all_templates_have_required_keys():
    for t in TEMPLATES:
        assert "key" in t
        assert "name" in t
        assert "tag" in t and t["tag"] in ("direct", "announcement")
        assert "tag_locked" in t
        assert "title_tpl" in t
        assert "body_tpl" in t


def test_templates_by_key_covers_all():
    assert len(TEMPLATES_BY_KEY) == len(TEMPLATES)


def test_render_event_reminder():
    title, body = render_template(
        "event_reminder",
        {"event": "Match", "date": "2026-03-20", "time": "18:00", "location": "Gym"},
    )
    assert "Match" in title
    assert "2026-03-20" in title
    assert "Match" in body
    assert "18:00" in body
    assert "Gym" in body


def test_render_unknown_key_returns_empty():
    title, body = render_template("nonexistent", {})
    assert title == ""
    assert body == ""


def test_render_missing_placeholder_left_in_place():
    title, body = render_template("event_reminder", {})
    assert "{event}" in title


def test_general_announcement_tag_not_locked():
    tpl = TEMPLATES_BY_KEY["general_announcement"]
    assert tpl["tag_locked"] is False
