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

    # Phone number — used for Telegram bot matching when no player record is linked
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)

    # Telegram chat ID — set when the user authenticates via the bot
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, default=None)

    # Preferred UI locale — one of: en, it, fr, de
    locale: Mapped[str] = mapped_column(String(5), nullable=False, default="en")

    # ── Relationships ──────────────────────────────────────────────────────
    players: Mapped[list[Player]] = relationship("Player", back_populates="user", lazy="select")
    managed_teams: Mapped[list["UserTeam"]] = relationship(back_populates="user", cascade="all, delete-orphan")  # noqa: F821

    # ── Helpers ────────────────────────────────────────────────────────────
    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_coach(self) -> bool:
        return self.role == "coach"

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role!r}>"
