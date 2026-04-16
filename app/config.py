"""app/config.py — Application settings loaded from environment / .env file."""

from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY: str = "change-me-in-production"

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite:///./data/proManager.db"

    # ── SMTP ──────────────────────────────────────────────────────────────────
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@promanager.local"

    # ── Application ───────────────────────────────────────────────────────────
    APP_NAME: str = "ProManager"
    # Base URL for magic login links (must include scheme+host, no trailing slash).
    # If left as the default localhost value, magic link buttons are omitted from emails.
    APP_URL: str = "http://localhost:7000"
    REMINDER_HOURS_BEFORE: int = 24
    # Set to true when serving over HTTPS (marks session cookie Secure)
    COOKIE_SECURE: bool = False

    # ── i18n ──────────────────────────────────────────────────────────────────
    # Set DEBUG=true in .env to raise KeyError on missing translation keys
    DEBUG: bool = False

    # ── Web Push (VAPID) ──────────────────────────────────────────────────
    # Generate with: python scripts/generate_vapid.py
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    # Must be a mailto: or https: URI — required by the Web Push protocol
    VAPID_SUBJECT: str = "mailto:admin@promanager.local"

    # ── Backup ────────────────────────────────────────────────────────────
    # Number of daily backup files to keep (older ones are pruned automatically)
    BACKUP_KEEP_DAYS: int = 7

    # ── Telegram Bot ──────────────────────────────────────────────────────
    # Get token from @BotFather on Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    # Public base URL of this app (e.g. https://myserver.com) — used to register webhook
    TELEGRAM_WEBHOOK_URL: str = ""
    # Random secret to validate incoming webhook requests from Telegram
    TELEGRAM_WEBHOOK_SECRET: str = ""

    @field_validator("SMTP_PORT")
    @classmethod
    def smtp_port_range(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError("SMTP_PORT must be between 1 and 65535")
        return v


# Singleton instance — import this everywhere
settings = Settings()
