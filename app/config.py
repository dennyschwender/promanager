"""app/config.py — Application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY: str = field(
        default_factory=lambda: os.environ.get(
            "SECRET_KEY", "change-me-in-production"
        )
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL", "sqlite:///./data/teamPresence.db"
        )
    )

    # ── SMTP ──────────────────────────────────────────────────────────────────
    SMTP_HOST: str = field(
        default_factory=lambda: os.environ.get("SMTP_HOST", "localhost")
    )
    SMTP_PORT: int = field(
        default_factory=lambda: int(os.environ.get("SMTP_PORT", "587"))
    )
    SMTP_USER: str = field(
        default_factory=lambda: os.environ.get("SMTP_USER", "")
    )
    SMTP_PASSWORD: str = field(
        default_factory=lambda: os.environ.get("SMTP_PASSWORD", "")
    )
    SMTP_FROM: str = field(
        default_factory=lambda: os.environ.get(
            "SMTP_FROM", "noreply@teampresence.local"
        )
    )

    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str = field(
        default_factory=lambda: os.environ.get("APP_NAME", "TeamPresence")
    )
    REMINDER_HOURS_BEFORE: int = field(
        default_factory=lambda: int(
            os.environ.get("REMINDER_HOURS_BEFORE", "24")
        )
    )
    # Set to true in production (requires HTTPS)
    COOKIE_SECURE: bool = field(
        default_factory=lambda: os.environ.get("COOKIE_SECURE", "false").lower()
        in ("true", "1", "yes")
    )


# Singleton instance — import this everywhere
settings = Settings()
