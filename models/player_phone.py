"""models/player_phone.py — One-or-more phone numbers per player."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PlayerPhone(Base):
    __tablename__ = "player_phones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    # e.g. "mobile", "home", "work"
    label: Mapped[str | None] = mapped_column(String(32), nullable=True)

    player: Mapped[Player] = relationship("Player", back_populates="phones")

    def __repr__(self) -> str:
        return f"<PlayerPhone player_id={self.player_id} phone={self.phone!r} label={self.label!r}>"
