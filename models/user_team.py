"""models/user_team.py — Coach-to-team assignment."""

from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UserTeam(Base):
    """Links a coach User to a Team they manage, optionally scoped to a Season."""

    __tablename__ = "user_team"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), nullable=False)
    season_id: Mapped[int | None] = mapped_column(ForeignKey("seasons.id"), nullable=True)

    user: Mapped["User"] = relationship(back_populates="managed_teams")  # type: ignore[name-defined]  # noqa: F821
    team: Mapped["Team"] = relationship(back_populates="coaches")  # type: ignore[name-defined]  # noqa: F821
    season: Mapped["Season | None"] = relationship()  # type: ignore[name-defined]  # noqa: F821
