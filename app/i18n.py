"""app/i18n.py — Translation loader and t() helper.

Loads all locale JSON files at import time. Exposes t(key, locale, **kwargs)
for string lookup with %{var} interpolation.

Dev mode (settings.DEBUG=True): missing key raises KeyError.
Production (settings.DEBUG=False): missing key logs a warning and returns
the 'en' value, or the bare key if 'en' also lacks it.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_LOCALES: list[str] = ["en", "it", "fr", "de"]
DEFAULT_LOCALE: str = "it"
_LOCALES_DIR = Path(__file__).parent.parent / "locales"

# ---------------------------------------------------------------------------
# Load all locale files at startup
# ---------------------------------------------------------------------------


def _load_locales() -> dict[str, dict]:
    data: dict[str, dict] = {}
    for lang in SUPPORTED_LOCALES:
        path = _LOCALES_DIR / f"{lang}.json"
        if path.exists():
            with path.open(encoding="utf-8") as fh:
                data[lang] = json.load(fh)
        else:
            logger.warning("Locale file not found: %s", path)
            data[lang] = {}
    return data


_translations: dict[str, dict] = _load_locales()


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def _get(data: dict, key: str):
    """Traverse dot-separated key into nested dict. Returns None if missing."""
    parts = key.split(".")
    node = data
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _interpolate(template: str, **kwargs) -> str:
    """Replace %{var} placeholders with kwargs values."""

    def replacer(m: re.Match) -> str:
        return str(kwargs.get(m.group(1), m.group(0)))

    return re.sub(r"%\{(\w+)\}", replacer, template)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def t(key: str, locale: str, **kwargs) -> str:
    """Look up a translation key for the given locale.

    Falls back to 'en' if locale is unsupported or key is missing.
    In DEBUG mode, raises KeyError for missing keys instead of falling back.
    """
    if locale not in SUPPORTED_LOCALES:
        locale = DEFAULT_LOCALE

    value = _get(_translations.get(locale, {}), key)

    if value is None:
        if settings.DEBUG:
            raise KeyError(f"Missing translation key {key!r} for locale {locale!r}")
        logger.warning("Missing translation key %r for locale %r — falling back to 'en'", key, locale)
        value = _get(_translations.get("en", {}), key)

    if value is None:
        return key  # Last resort: return the bare key

    if isinstance(value, str):
        return _interpolate(value, **kwargs) if kwargs else value

    return str(value)
