"""models/player.py — Player model."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    first_name: Mapped[str] = mapped_column(String(64), nullable=False)
    last_name: Mapped[str] = mapped_column(String(64), nullable=False)
    email: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    # Legacy single phone kept for backward-compat; use phones for multi-number
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ── Personal info ───────────────────────────────────────────────────
    # "male" | "female" | "other"
    sex: Mapped[str | None] = mapped_column(String(16), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    street: Mapped[str | None] = mapped_column(String(256), nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(16), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)

    team_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # ── Relationships ──────────────────────────────────────────────────────
    team_memberships: Mapped[list[PlayerTeam]] = relationship(
        "PlayerTeam",
        back_populates="player",
        cascade="all, delete-orphan",
        order_by="PlayerTeam.priority",
        lazy="select",
    )
    phones: Mapped[list[PlayerPhone]] = relationship(
        "PlayerPhone",
        back_populates="player",
        cascade="all, delete-orphan",
        lazy="select",
    )
    contact: Mapped[PlayerContact | None] = relationship(
        "PlayerContact",
        back_populates="player",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="select",
    )
    user: Mapped[User | None] = relationship(
        "User", back_populates="players", lazy="select"
    )
    attendances: Mapped[list[Attendance]] = relationship(
        "Attendance", back_populates="player", lazy="select"
    )
    notifications: Mapped[list[Notification]] = relationship(
        "Notification",
        back_populates="player",
        cascade="all, delete-orphan",
        lazy="select",
    )
    notification_preferences: Mapped[list[NotificationPreference]] = relationship(
        "NotificationPreference",
        back_populates="player",
        cascade="all, delete-orphan",
        lazy="select",
    )
    web_push_subscriptions: Mapped[list[WebPushSubscription]] = relationship(
        "WebPushSubscription",
        back_populates="player",
        cascade="all, delete-orphan",
        lazy="select",
    )

    # ── Helpers ────────────────────────────────────────────────────────────
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    def __repr__(self) -> str:
        return f"<Player id={self.id} name={self.full_name!r}>"
