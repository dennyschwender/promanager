"""services/notification_templates.py — Fixed system notification templates.

Templates are i18n-ready: title_tpl and body_tpl are plain strings today.
When the i18n sub-project is implemented, replace them with translation-key
lookups (e.g. gettext / fluent) without changing callers.

Placeholders: {event}, {date}, {time}, {location}, {new_location}, {new_time}
"""

from __future__ import annotations

from typing import TypedDict


class NotificationTemplate(TypedDict):
    key: str  # machine identifier
    name: str  # human-readable name shown in the dropdown
    tag: str  # "direct" | "announcement"
    tag_locked: bool  # if True, admin cannot change the tag
    title_tpl: str  # title template with {placeholder} syntax
    body_tpl: str  # body template with {placeholder} syntax


TEMPLATES: list[NotificationTemplate] = [
    {
        "key": "event_reminder",
        "name": "Event Reminder",
        "tag": "direct",
        "tag_locked": True,
        "title_tpl": "Reminder: {event} on {date}",
        "body_tpl": ("Don't forget: {event} is on {date} at {time} at {location}. Please confirm your attendance."),
    },
    {
        "key": "cancellation",
        "name": "Cancellation",
        "tag": "announcement",
        "tag_locked": True,
        "title_tpl": "{event} cancelled",
        "body_tpl": "{event} scheduled for {date} has been cancelled.",
    },
    {
        "key": "venue_change",
        "name": "Venue Change",
        "tag": "announcement",
        "tag_locked": True,
        "title_tpl": "Venue change: {event}",
        "body_tpl": "{event} on {date} has moved to {new_location}.",
    },
    {
        "key": "time_change",
        "name": "Time Change",
        "tag": "announcement",
        "tag_locked": True,
        "title_tpl": "Time change: {event}",
        "body_tpl": "{event} on {date} has been rescheduled to {new_time}.",
    },
    {
        "key": "attendance_request",
        "name": "Attendance Request",
        "tag": "direct",
        "tag_locked": True,
        "title_tpl": "Please confirm: {event}",
        "body_tpl": "Please confirm your attendance for {event} on {date}.",
    },
    {
        "key": "general_announcement",
        "name": "General Announcement",
        "tag": "announcement",
        "tag_locked": False,  # admin can switch to direct
        "title_tpl": "",  # free text — admin fills in
        "body_tpl": "",
    },
    {
        "key": "training_cancelled",
        "name": "Training Cancelled",
        "tag": "announcement",
        "tag_locked": True,
        "title_tpl": "Training cancelled: {date}",
        "body_tpl": "Training on {date} is cancelled.",
    },
    {
        "key": "match_result",
        "name": "Match Result",
        "tag": "announcement",
        "tag_locked": True,
        "title_tpl": "Result: {event}",
        "body_tpl": "",  # admin adds score/summary
    },
]

# Lookup by key for O(1) access
TEMPLATES_BY_KEY: dict[str, NotificationTemplate] = {t["key"]: t for t in TEMPLATES}


def render_template(key: str, context: dict[str, str]) -> tuple[str, str]:
    """Return (title, body) with placeholders substituted from *context*.

    Unknown placeholders are left as-is.
    """
    tpl = TEMPLATES_BY_KEY.get(key)
    if tpl is None:
        return "", ""
    title = tpl["title_tpl"].format_map(_SafeDict(context))
    body = tpl["body_tpl"].format_map(_SafeDict(context))
    return title, body


class _SafeDict(dict):
    """Return the key wrapped in braces for missing keys."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"
