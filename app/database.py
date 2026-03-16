"""app/database.py — SQLAlchemy 2.x synchronous engine & session setup."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
# check_same_thread=False is required for SQLite when used with FastAPI
# because SQLite connections are not thread-safe by default, but SQLAlchemy
# handles concurrency correctly at the ORM level.
_connect_args: dict = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=_connect_args,
    echo=False,  # set True for SQL query logging during development
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# ---------------------------------------------------------------------------
# Declarative base — all models inherit from this
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Dependency for FastAPI routes
# ---------------------------------------------------------------------------


def get_db():
    """Yield a database session and ensure it is closed after use."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Startup helper
# ---------------------------------------------------------------------------


def init_db() -> None:
    """Create all tables that are registered on Base.metadata.

    Alembic manages schema migrations for existing databases.
    This call is retained so the test suite (which uses an in-memory SQLite
    database) can create tables without running Alembic migrations.
    """
    import models  # noqa: F401  (side-effect import — registers all models)

    Base.metadata.create_all(bind=engine)
