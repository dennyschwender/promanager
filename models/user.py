"""models/user.py — User account model."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)

    # "admin" | "coach" | "member"
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Optional hashed API token for machine-to-machine auth
    api_token_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Real name — synced to linked player record when present
    first_name: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    last_name: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)

    # Phone number — used for Telegram bot matching when no player record is linked
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)

    # Telegram chat ID — set when the user authenticates via the bot
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, default=None)

    # Telegram message ID for pinned notification summary (edited in-place for coach alerts)
    telegram_notification_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)

    # Tracks which view the persistent Telegram message is currently showing ("home", "el", "e:42", etc.)
    telegram_current_view: Mapped[str] = mapped_column(String(20), nullable=False, default="home")

    # Preferred UI locale — one of: en, it, fr, de
    locale: Mapped[str] = mapped_column(String(5), nullable=False, default="en")

    # Force password change on next login (set after account creation or password reset)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Set to now() to invalidate all sessions issued before this timestamp
    logout_all_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)

    # Updated on each authenticated request (throttled) — shows last activity
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)

    # Unique token for public iCal calendar feed access
    calendar_token: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True, default=None)

    # ── Relationships ──────────────────────────────────────────────────────
    players: Mapped[list[Player]] = relationship("Player", back_populates="user", lazy="select")
    managed_teams: Mapped[list["UserTeam"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # noqa: F821
    telegram_notifications: Mapped[list["TelegramNotification"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # noqa: F821

    # ── Helpers ────────────────────────────────────────────────────────────
    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_coach(self) -> bool:
        return self.role == "coach"

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"
