"""Tests that required email locale keys exist in all locale files."""
import json
from pathlib import Path

import pytest

LOCALES = ["en", "it", "fr", "de"]
REQUIRED_KEYS = [
    "email.login_button",
    "email.footer",
    "email.welcome_subject",
    "email.reset_subject",
    "email.notification_subject",
    "email.reminder_subject",
    "email.attendance_subject",
]
RETIRED_KEYS = [
    "email.reminder_body",
    "email.reminder_body_html",
    "email.attendance_body",
    "email.attendance_body_html",
    "users.email_subject",
    "users.reset_email_body",
]


def _get(data: dict, dotted_key: str):
    """Navigate dot-separated keys into nested dict."""
    parts = dotted_key.split(".")
    node = data
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("key", REQUIRED_KEYS)
def test_required_key_exists(locale, key):
    path = Path(f"locales/{locale}.json")
    data = json.loads(path.read_text())
    assert _get(data, key) is not None, f"Missing key '{key}' in {locale}.json"


@pytest.mark.parametrize("locale", LOCALES)
@pytest.mark.parametrize("key", RETIRED_KEYS)
def test_retired_key_removed(locale, key):
    path = Path(f"locales/{locale}.json")
    data = json.loads(path.read_text())
    assert _get(data, key) is None, f"Retired key '{key}' still present in {locale}.json"
