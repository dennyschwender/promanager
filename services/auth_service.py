"""services/auth_service.py — Authentication helpers."""

from __future__ import annotations

import secrets

import bcrypt
from itsdangerous import TimestampSigner
from sqlalchemy.orm import Session

from app.config import settings
from models.user import User

# ---------------------------------------------------------------------------
# Password helpers (using bcrypt directly — passlib 1.7.4 is incompatible
# with bcrypt >= 4.x / Python 3.12+)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# User lookups
# ---------------------------------------------------------------------------


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = get_user_by_username(db, username)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# ---------------------------------------------------------------------------
# Session cookie
# ---------------------------------------------------------------------------


def create_session_cookie(user_id: int) -> str:
    """Return a signed cookie value for the given user_id."""
    signer = TimestampSigner(settings.SECRET_KEY)
    return signer.sign(str(user_id).encode()).decode()


# ---------------------------------------------------------------------------
# User creation
# ---------------------------------------------------------------------------


def create_user(
    db: Session,
    username: str,
    email: str,
    password: str,
    role: str = "member",
    phone: str | None = None,
    locale: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
) -> User:
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
        role=role,
        is_active=True,
        phone=phone,
        locale=locale,
        first_name=first_name,
        last_name=last_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# API token helpers
# ---------------------------------------------------------------------------


def set_api_token(db: Session, user: User, raw_token: str) -> None:
    """Hash and store the raw API token on the user record."""
    user.api_token_hash = bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode()
    db.add(user)
    db.commit()


def verify_api_token(user: User, raw_token: str) -> bool:
    if not user.api_token_hash:
        return False
    try:
        return bcrypt.checkpw(raw_token.encode(), user.api_token_hash.encode())
    except Exception:
        return False


def generate_api_token() -> str:
    """Generate a cryptographically secure random API token."""
    return secrets.token_urlsafe(32)
