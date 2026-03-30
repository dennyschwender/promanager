# Telegram Bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Telegram bot to ProManager that lets authenticated users view upcoming events and manage attendance, with the same role-based access rules as the web app.

**Architecture:** Webhook mode — FastAPI receives Telegram updates at `POST /telegram/webhook`, validates a secret header, and dispatches them to a `python-telegram-bot` v20 `Application` instance. The Application is initialised in the FastAPI lifespan and shared via a module-level variable in `bot/__init__.py`. Authentication ties a Telegram `chat_id` to a `User` row by matching the phone number shared via Telegram's native contact button against `Player.phone` / `PlayerPhone`.

**Tech Stack:** `python-telegram-bot>=20.0` (async-native), existing FastAPI/SQLAlchemy stack, existing `app/i18n.py` translation system (JSON locale files).

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `requirements.txt` | Add `python-telegram-bot>=20.0` |
| Modify | `app/config.py` | Add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_URL`, `TELEGRAM_WEBHOOK_SECRET` |
| Modify | `.env.example` | Document new env vars |
| Modify | `models/user.py` | Add `telegram_chat_id` column |
| Create | `alembic/versions/f1a2b3c4d5e6_add_telegram_chat_id.py` | DB migration |
| Modify | `locales/en.json` | Add `telegram.*` keys |
| Modify | `locales/it.json` | Add `telegram.*` keys (Italian) |
| Modify | `locales/fr.json` | Add `telegram.*` keys (French) |
| Modify | `locales/de.json` | Add `telegram.*` keys (German) |
| Create | `services/telegram_service.py` | Phone normalization, user lookup, auth logic |
| Create | `bot/__init__.py` | Build and expose the `Application` instance |
| Create | `bot/keyboards.py` | Inline keyboard builders |
| Create | `bot/handlers.py` | All command and callback query handlers |
| Create | `routes/telegram.py` | `POST /telegram/webhook` FastAPI route |
| Modify | `app/main.py` | Lifespan webhook registration; add telegram router |
| Create | `tests/test_telegram_service.py` | Unit tests for phone normalization and auth |
| Create | `tests/test_telegram_webhook.py` | Integration tests for the webhook route |

---

## Task 1: Dependencies and Config

**Files:**
- Modify: `requirements.txt`
- Modify: `app/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add the dependency**

Open `requirements.txt` and add after `slowapi==0.1.9`:

```
python-telegram-bot>=20.0
```

- [ ] **Step 2: Add config vars to `app/config.py`**

Inside the `Settings` class, add a new section after the `# ── Web Push (VAPID)` block:

```python
    # ── Telegram Bot ──────────────────────────────────────────────────────
    # Get token from @BotFather on Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    # Public base URL of this app (e.g. https://myserver.com) — used to register webhook
    TELEGRAM_WEBHOOK_URL: str = ""
    # Random secret to validate incoming webhook requests from Telegram
    TELEGRAM_WEBHOOK_SECRET: str = ""
```

- [ ] **Step 3: Document in `.env.example`**

Add at the end of `.env.example`:

```
# ── Telegram Bot ─────────────────────────────────────────────────────────────
# Get token from @BotFather. Leave empty to disable the Telegram bot.
TELEGRAM_BOT_TOKEN=
# Public HTTPS base URL of this app (required for webhook mode)
TELEGRAM_WEBHOOK_URL=https://yourserver.com
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
TELEGRAM_WEBHOOK_SECRET=
```

- [ ] **Step 4: Install the new dependency**

```bash
pip install python-telegram-bot>=20.0
```

Expected: installs successfully, `python -c "import telegram; print(telegram.__version__)"` prints `20.x`.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt app/config.py .env.example
git commit -m "feat: add python-telegram-bot dependency and config vars"
```

---

## Task 2: Database — add `telegram_chat_id` to User

**Files:**
- Modify: `models/user.py`
- Create: `alembic/versions/f1a2b3c4d5e6_add_telegram_chat_id.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_telegram_service.py` (just enough to force the model change):

```python
"""tests/test_telegram_service.py"""
from tests.conftest import override_get_db  # noqa: F401
from models.user import User


def test_user_has_telegram_chat_id_field(db_session):
    user = User(
        username="tgtest",
        email="tgtest@example.com",
        hashed_password="x",
        role="member",
    )
    user.telegram_chat_id = "987654321"
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    assert user.telegram_chat_id == "987654321"
```

Run: `pytest tests/test_telegram_service.py::test_user_has_telegram_chat_id_field -v`
Expected: FAIL with `AttributeError: can't set attribute` or column not found.

- [ ] **Step 2: Add column to `models/user.py`**

In `models/user.py`, add the import for `UniqueConstraint` to the SQLAlchemy imports line:

```python
from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
```

Then add the column after `api_token_hash`:

```python
    # Telegram chat ID — set when the user authenticates via the bot
    telegram_chat_id: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, default=None
    )
```

- [ ] **Step 3: Create the Alembic migration**

Create `alembic/versions/f1a2b3c4d5e6_add_telegram_chat_id.py`:

```python
"""add telegram_chat_id to users

Revision ID: f1a2b3c4d5e6
Revises: ce63adc3d835
Create Date: 2026-03-30 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "ce63adc3d835"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("telegram_chat_id", sa.String(64), nullable=True, unique=True),
    )


def downgrade() -> None:
    op.drop_column("users", "telegram_chat_id")
```

- [ ] **Step 4: Run the test**

```bash
pytest tests/test_telegram_service.py::test_user_has_telegram_chat_id_field -v
```

Expected: PASS (in-memory SQLite picks up the new column automatically from the model).

- [ ] **Step 5: Run the migration against the real DB (if you have one)**

```bash
alembic upgrade head
```

Expected: `Running upgrade ce63adc3d835 -> f1a2b3c4d5e6, add telegram_chat_id to users`

- [ ] **Step 6: Commit**

```bash
git add models/user.py alembic/versions/f1a2b3c4d5e6_add_telegram_chat_id.py tests/test_telegram_service.py
git commit -m "feat: add telegram_chat_id column to users"
```

---

## Task 3: Translation Keys

**Files:**
- Modify: `locales/en.json`
- Modify: `locales/it.json`
- Modify: `locales/fr.json`
- Modify: `locales/de.json`

- [ ] **Step 1: Add telegram keys to `locales/en.json`**

Add this top-level key alongside the existing keys (e.g. after `"nav"`):

```json
  "telegram": {
    "welcome": "Welcome to ProManager! Please share your phone number to authenticate.",
    "share_phone_button": "Share my phone number",
    "auth_success": "Authenticated as %{username}. Welcome!",
    "auth_already_this": "You are already authenticated as %{username}.",
    "auth_conflict_chat": "This Telegram account is already linked to another ProManager user. Contact your admin.",
    "auth_conflict_user": "This ProManager account is already linked to another Telegram user. Contact your admin.",
    "auth_not_found": "No ProManager account found for this phone number. Contact your admin.",
    "auth_no_user": "This phone is registered to a player with no linked user account. Contact your admin.",
    "not_authenticated": "Please use /start to authenticate first.",
    "logout_success": "You have been logged out.",
    "events_header": "Upcoming events (page %{page}):",
    "no_events": "No upcoming events.",
    "view_button": "View",
    "prev_button": "← Prev",
    "next_button": "Next →",
    "back_button": "← Back",
    "event_type_training": "Training",
    "event_type_match": "Match",
    "event_type_other": "Event",
    "date_label": "Date",
    "time_label": "Time",
    "location_label": "Location",
    "meeting_label": "Meeting",
    "attendance_label": "Attendance",
    "your_status_label": "Your status",
    "status_present": "✓ Present",
    "status_absent": "✗ Absent",
    "status_unknown": "? Unknown",
    "status_maybe": "~ Maybe",
    "status_updated": "Status updated to %{status}.",
    "players_header": "Players:",
    "unknown_error": "An error occurred. Please try again."
  }
```

- [ ] **Step 2: Add telegram keys to `locales/it.json`**

```json
  "telegram": {
    "welcome": "Benvenuto in ProManager! Condividi il tuo numero di telefono per autenticarti.",
    "share_phone_button": "Condividi il mio numero",
    "auth_success": "Autenticato come %{username}. Benvenuto!",
    "auth_already_this": "Sei già autenticato come %{username}.",
    "auth_conflict_chat": "Questo account Telegram è già collegato a un altro utente ProManager. Contatta il tuo admin.",
    "auth_conflict_user": "Questo account ProManager è già collegato a un altro utente Telegram. Contatta il tuo admin.",
    "auth_not_found": "Nessun account ProManager trovato per questo numero. Contatta il tuo admin.",
    "auth_no_user": "Questo telefono è registrato a un giocatore senza account utente. Contatta il tuo admin.",
    "not_authenticated": "Usa /start per autenticarti prima.",
    "logout_success": "Sei stato disconnesso.",
    "events_header": "Prossimi eventi (pagina %{page}):",
    "no_events": "Nessun evento in programma.",
    "view_button": "Vedi",
    "prev_button": "← Prec",
    "next_button": "Succ →",
    "back_button": "← Indietro",
    "event_type_training": "Allenamento",
    "event_type_match": "Partita",
    "event_type_other": "Evento",
    "date_label": "Data",
    "time_label": "Ora",
    "location_label": "Luogo",
    "meeting_label": "Ritrovo",
    "attendance_label": "Presenze",
    "your_status_label": "Il tuo stato",
    "status_present": "✓ Presente",
    "status_absent": "✗ Assente",
    "status_unknown": "? Sconosciuto",
    "status_maybe": "~ Forse",
    "status_updated": "Stato aggiornato a %{status}.",
    "players_header": "Giocatori:",
    "unknown_error": "Si è verificato un errore. Riprova."
  }
```

- [ ] **Step 3: Add telegram keys to `locales/fr.json`**

```json
  "telegram": {
    "welcome": "Bienvenue sur ProManager! Partagez votre numéro de téléphone pour vous authentifier.",
    "share_phone_button": "Partager mon numéro",
    "auth_success": "Authentifié en tant que %{username}. Bienvenue!",
    "auth_already_this": "Vous êtes déjà authentifié en tant que %{username}.",
    "auth_conflict_chat": "Ce compte Telegram est déjà lié à un autre utilisateur ProManager. Contactez votre admin.",
    "auth_conflict_user": "Ce compte ProManager est déjà lié à un autre utilisateur Telegram. Contactez votre admin.",
    "auth_not_found": "Aucun compte ProManager trouvé pour ce numéro. Contactez votre admin.",
    "auth_no_user": "Ce téléphone est enregistré pour un joueur sans compte utilisateur. Contactez votre admin.",
    "not_authenticated": "Utilisez /start pour vous authentifier.",
    "logout_success": "Vous avez été déconnecté.",
    "events_header": "Prochains événements (page %{page}):",
    "no_events": "Aucun événement à venir.",
    "view_button": "Voir",
    "prev_button": "← Préc",
    "next_button": "Suiv →",
    "back_button": "← Retour",
    "event_type_training": "Entraînement",
    "event_type_match": "Match",
    "event_type_other": "Événement",
    "date_label": "Date",
    "time_label": "Heure",
    "location_label": "Lieu",
    "meeting_label": "Rendez-vous",
    "attendance_label": "Présences",
    "your_status_label": "Votre statut",
    "status_present": "✓ Présent",
    "status_absent": "✗ Absent",
    "status_unknown": "? Inconnu",
    "status_maybe": "~ Peut-être",
    "status_updated": "Statut mis à jour: %{status}.",
    "players_header": "Joueurs:",
    "unknown_error": "Une erreur s'est produite. Veuillez réessayer."
  }
```

- [ ] **Step 4: Add telegram keys to `locales/de.json`**

```json
  "telegram": {
    "welcome": "Willkommen bei ProManager! Teile deine Telefonnummer zur Authentifizierung.",
    "share_phone_button": "Meine Nummer teilen",
    "auth_success": "Angemeldet als %{username}. Willkommen!",
    "auth_already_this": "Du bist bereits als %{username} angemeldet.",
    "auth_conflict_chat": "Dieses Telegram-Konto ist bereits mit einem anderen ProManager-Benutzer verknüpft. Kontaktiere deinen Admin.",
    "auth_conflict_user": "Dieses ProManager-Konto ist bereits mit einem anderen Telegram-Benutzer verknüpft. Kontaktiere deinen Admin.",
    "auth_not_found": "Kein ProManager-Konto für diese Telefonnummer gefunden. Kontaktiere deinen Admin.",
    "auth_no_user": "Dieses Telefon gehört einem Spieler ohne Benutzerkonto. Kontaktiere deinen Admin.",
    "not_authenticated": "Bitte /start verwenden um dich anzumelden.",
    "logout_success": "Du wurdest abgemeldet.",
    "events_header": "Bevorstehende Ereignisse (Seite %{page}):",
    "no_events": "Keine bevorstehenden Ereignisse.",
    "view_button": "Ansehen",
    "prev_button": "← Zurück",
    "next_button": "Weiter →",
    "back_button": "← Zurück",
    "event_type_training": "Training",
    "event_type_match": "Spiel",
    "event_type_other": "Ereignis",
    "date_label": "Datum",
    "time_label": "Zeit",
    "location_label": "Ort",
    "meeting_label": "Treffpunkt",
    "attendance_label": "Anwesenheit",
    "your_status_label": "Dein Status",
    "status_present": "✓ Anwesend",
    "status_absent": "✗ Abwesend",
    "status_unknown": "? Unbekannt",
    "status_maybe": "~ Vielleicht",
    "status_updated": "Status aktualisiert: %{status}.",
    "players_header": "Spieler:",
    "unknown_error": "Ein Fehler ist aufgetreten. Bitte erneut versuchen."
  }
```

- [ ] **Step 5: Commit**

```bash
git add locales/en.json locales/it.json locales/fr.json locales/de.json
git commit -m "feat: add telegram bot translation keys to all locales"
```

---

## Task 4: `services/telegram_service.py` — Phone Auth Logic

**Files:**
- Create: `services/telegram_service.py`
- Modify: `tests/test_telegram_service.py`

- [ ] **Step 1: Write failing tests**

Replace the contents of `tests/test_telegram_service.py` with:

```python
"""tests/test_telegram_service.py"""
import pytest
from sqlalchemy.orm import Session

from models.player import Player
from models.player_phone import PlayerPhone
from models.user import User
from services.telegram_service import (
    AuthResult,
    find_user_by_phone,
    link_telegram,
    normalize_phone,
    unlink_telegram,
)


# ── normalize_phone ───────────────────────────────────────────────────────────

def test_normalize_strips_spaces_and_dashes():
    assert normalize_phone("+39 123-456-7890") == "391234567890"


def test_normalize_strips_plus():
    assert normalize_phone("+391234567890") == "391234567890"


def test_normalize_strips_parens():
    assert normalize_phone("(039) 123 4567") == "0391234567"


def test_normalize_digits_only_unchanged():
    assert normalize_phone("391234567890") == "391234567890"


# ── find_user_by_phone ────────────────────────────────────────────────────────

def test_find_user_by_legacy_phone(db_session: Session):
    user = User(username="u1", email="u1@x.com", hashed_password="x", role="member")
    db_session.add(user)
    db_session.flush()
    player = Player(first_name="A", last_name="B", phone="+39 123 456 7890", user_id=user.id)
    db_session.add(player)
    db_session.commit()

    found = find_user_by_phone(db_session, "391234567890")
    assert found is not None
    assert found.id == user.id


def test_find_user_by_player_phone_table(db_session: Session):
    user = User(username="u2", email="u2@x.com", hashed_password="x", role="member")
    db_session.add(user)
    db_session.flush()
    player = Player(first_name="C", last_name="D", user_id=user.id)
    db_session.add(player)
    db_session.flush()
    pp = PlayerPhone(player_id=player.id, phone="+39 987 654 3210", label="mobile")
    db_session.add(pp)
    db_session.commit()

    found = find_user_by_phone(db_session, "39987654321 0".replace(" ", ""))
    # normalize: "39987654321 0" -> "399876543210"
    found2 = find_user_by_phone(db_session, "399876543210")
    assert found2 is not None
    assert found2.id == user.id


def test_find_user_returns_none_when_no_match(db_session: Session):
    assert find_user_by_phone(db_session, "0000000000") is None


def test_find_user_returns_none_when_player_has_no_user(db_session: Session):
    player = Player(first_name="E", last_name="F", phone="111222333")
    db_session.add(player)
    db_session.commit()
    assert find_user_by_phone(db_session, "111222333") is None


# ── link_telegram ─────────────────────────────────────────────────────────────

def test_link_telegram_success(db_session: Session):
    user = User(username="u3", email="u3@x.com", hashed_password="x", role="member")
    db_session.add(user)
    db_session.commit()

    result = link_telegram(db_session, user, chat_id="111")
    assert result == AuthResult.SUCCESS
    db_session.refresh(user)
    assert user.telegram_chat_id == "111"


def test_link_telegram_already_this_chat(db_session: Session):
    user = User(username="u4", email="u4@x.com", hashed_password="x", role="member", telegram_chat_id="222")
    db_session.add(user)
    db_session.commit()

    result = link_telegram(db_session, user, chat_id="222")
    assert result == AuthResult.ALREADY_THIS


def test_link_telegram_conflict_chat_id(db_session: Session):
    """chat_id already linked to a different user."""
    other = User(username="u5", email="u5@x.com", hashed_password="x", role="member", telegram_chat_id="333")
    user = User(username="u6", email="u6@x.com", hashed_password="x", role="member")
    db_session.add_all([other, user])
    db_session.commit()

    result = link_telegram(db_session, user, chat_id="333")
    assert result == AuthResult.CONFLICT_CHAT


def test_link_telegram_conflict_user_already_linked(db_session: Session):
    """The target user already has a different chat_id."""
    user = User(username="u7", email="u7@x.com", hashed_password="x", role="member", telegram_chat_id="444")
    db_session.add(user)
    db_session.commit()

    result = link_telegram(db_session, user, chat_id="555")
    assert result == AuthResult.CONFLICT_USER


# ── unlink_telegram ───────────────────────────────────────────────────────────

def test_unlink_telegram(db_session: Session):
    user = User(username="u8", email="u8@x.com", hashed_password="x", role="member", telegram_chat_id="666")
    db_session.add(user)
    db_session.commit()

    unlink_telegram(db_session, user)
    db_session.refresh(user)
    assert user.telegram_chat_id is None
```

Run: `pytest tests/test_telegram_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.telegram_service'`

- [ ] **Step 2: Create `services/telegram_service.py`**

```python
"""services/telegram_service.py — Telegram bot authentication helpers."""

from __future__ import annotations

import re
from enum import Enum, auto

from sqlalchemy.orm import Session

from models.player import Player
from models.player_phone import PlayerPhone
from models.user import User


class AuthResult(Enum):
    SUCCESS = auto()
    ALREADY_THIS = auto()   # same chat_id already linked to this user
    CONFLICT_CHAT = auto()  # chat_id linked to a different user
    CONFLICT_USER = auto()  # user already linked to a different chat_id


def normalize_phone(phone: str) -> str:
    """Strip all non-digit characters (including leading +) for comparison."""
    return re.sub(r"\D", "", phone)


def find_user_by_phone(db: Session, telegram_phone: str) -> User | None:
    """Return the User whose linked player has a matching phone number.

    `telegram_phone` is already normalized (digits only, no +).
    Searches both Player.phone (legacy) and PlayerPhone rows.
    Returns None if no match or if the matched player has no linked user.
    """
    norm = normalize_phone(telegram_phone)

    # Search legacy Player.phone
    players = db.query(Player).filter(Player.phone.isnot(None)).all()
    for player in players:
        if normalize_phone(player.phone) == norm and player.user_id is not None:
            return db.get(User, player.user_id)

    # Search PlayerPhone table
    phone_rows = db.query(PlayerPhone).all()
    for row in phone_rows:
        if normalize_phone(row.phone) == norm:
            player = db.get(Player, row.player_id)
            if player and player.user_id is not None:
                return db.get(User, player.user_id)

    return None


def link_telegram(db: Session, user: User, chat_id: str) -> AuthResult:
    """Try to link `chat_id` to `user`. Returns an AuthResult indicating outcome.

    Does NOT commit — caller must commit on SUCCESS.
    """
    # Already linked to this same chat
    if user.telegram_chat_id == chat_id:
        return AuthResult.ALREADY_THIS

    # User already linked to a different chat
    if user.telegram_chat_id is not None and user.telegram_chat_id != chat_id:
        return AuthResult.CONFLICT_USER

    # chat_id already linked to a different user
    existing = db.query(User).filter(User.telegram_chat_id == chat_id).first()
    if existing is not None and existing.id != user.id:
        return AuthResult.CONFLICT_CHAT

    user.telegram_chat_id = chat_id
    db.add(user)
    db.commit()
    return AuthResult.SUCCESS


def unlink_telegram(db: Session, user: User) -> None:
    """Remove the Telegram link from a user."""
    user.telegram_chat_id = None
    db.add(user)
    db.commit()


def get_user_by_chat_id(db: Session, chat_id: str) -> User | None:
    """Return the User linked to this Telegram chat ID, or None."""
    return db.query(User).filter(User.telegram_chat_id == str(chat_id)).first()
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_telegram_service.py -v
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add services/telegram_service.py tests/test_telegram_service.py
git commit -m "feat: add telegram_service with phone auth logic"
```

---

## Task 5: `bot/__init__.py` and `bot/keyboards.py`

**Files:**
- Create: `bot/__init__.py`
- Create: `bot/keyboards.py`

- [ ] **Step 1: Create `bot/__init__.py`**

```python
"""bot/__init__.py — Telegram Application factory.

`telegram_app` is None when TELEGRAM_BOT_TOKEN is not configured.
Call `get_application()` to get the initialised instance.
"""

from __future__ import annotations

import logging

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

logger = logging.getLogger(__name__)

telegram_app: Application | None = None


def build_application(token: str) -> Application:
    """Build and wire the Application with all handlers."""
    from bot.handlers import (  # noqa: PLC0415
        handle_callback,
        handle_contact,
        handle_logout,
        handle_start,
    )

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", handle_start))
    app.add_handler(CommandHandler("logout", handle_logout))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(CallbackQueryHandler(handle_callback))
    return app


async def init_application(token: str) -> Application:
    """Build and initialise the Application. Stores it in `telegram_app`."""
    global telegram_app
    telegram_app = build_application(token)
    await telegram_app.initialize()
    logger.info("Telegram Application initialised.")
    return telegram_app


async def shutdown_application() -> None:
    """Shut down the Application cleanly."""
    global telegram_app
    if telegram_app is not None:
        await telegram_app.shutdown()
        telegram_app = None
        logger.info("Telegram Application shut down.")
```

- [ ] **Step 2: Create `bot/keyboards.py`**

```python
"""bot/keyboards.py — Inline keyboard builders for the Telegram bot."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from models.attendance import Attendance
from models.event import Event
from models.player import Player

PAGE_SIZE = 5
PLAYER_PAGE_SIZE = 10


def events_keyboard(events: list[Event], page: int, total_pages: int) -> InlineKeyboardMarkup:
    """One row per event with a View button, plus Prev/Next navigation."""
    rows = []
    for event in events:
        label = f"{event.event_date} — {event.title}"
        rows.append([InlineKeyboardButton(label, callback_data=f"evt:{event.id}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("← Prev", callback_data=f"evts:{page - 1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next →", callback_data=f"evts:{page + 1}"))
    if nav:
        rows.append(nav)

    return InlineKeyboardMarkup(rows)


def event_status_keyboard(event_id: int, player_id: int, back_page: int = 0) -> InlineKeyboardMarkup:
    """Status buttons for a single player (member self-service)."""
    rows = [
        [
            InlineKeyboardButton("✓ Present", callback_data=f"sta:{event_id}:{player_id}:p"),
            InlineKeyboardButton("✗ Absent", callback_data=f"sta:{event_id}:{player_id}:a"),
            InlineKeyboardButton("? Unknown", callback_data=f"sta:{event_id}:{player_id}:u"),
        ],
        [InlineKeyboardButton("← Back", callback_data=f"evts:{back_page}")],
    ]
    return InlineKeyboardMarkup(rows)


def event_admin_keyboard(
    event_id: int,
    players: list[Player],
    attendances: dict[int, Attendance],
    page: int,
    total_pages: int,
    back_page: int = 0,
) -> InlineKeyboardMarkup:
    """Player list with per-player status buttons for coaches/admins."""
    STATUS_ICON = {"present": "✓", "absent": "✗", "unknown": "?", "maybe": "~"}
    rows = []
    for player in players:
        att = attendances.get(player.id)
        current = att.status if att else "unknown"
        icon = STATUS_ICON.get(current, "?")
        name_btn = InlineKeyboardButton(
            f"{icon} {player.full_name}",
            callback_data=f"noop",
        )
        rows.append([
            name_btn,
            InlineKeyboardButton("✓", callback_data=f"sta:{event_id}:{player.id}:p"),
            InlineKeyboardButton("✗", callback_data=f"sta:{event_id}:{player.id}:a"),
            InlineKeyboardButton("?", callback_data=f"sta:{event_id}:{player.id}:u"),
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("← Players prev", callback_data=f"evtp:{event_id}:{page - 1}:{back_page}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Players next →", callback_data=f"evtp:{event_id}:{page + 1}:{back_page}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton("← Back to Events", callback_data=f"evts:{back_page}")])
    return InlineKeyboardMarkup(rows)
```

- [ ] **Step 3: Commit**

```bash
git add bot/__init__.py bot/keyboards.py
git commit -m "feat: add bot package with Application factory and keyboard builders"
```

---

## Task 6: `bot/handlers.py` — Auth and Events List

**Files:**
- Create: `bot/handlers.py`

- [ ] **Step 1: Create `bot/handlers.py` with auth handlers**

```python
"""bot/handlers.py — Telegram bot command and callback handlers."""

from __future__ import annotations

import logging
import math
from datetime import datetime

from telegram import KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from app.database import SessionLocal
from app.i18n import t
from bot.keyboards import (
    PAGE_SIZE,
    PLAYER_PAGE_SIZE,
    event_admin_keyboard,
    event_status_keyboard,
    events_keyboard,
)
from models.attendance import Attendance
from models.event import Event
from models.player import Player
from models.player_team import PlayerTeam
from services.attendance_service import set_attendance
from services.telegram_service import (
    AuthResult,
    find_user_by_phone,
    get_user_by_chat_id,
    link_telegram,
    normalize_phone,
    unlink_telegram,
)

logger = logging.getLogger(__name__)

# Status char → full status string
_STATUS_MAP = {"p": "present", "a": "absent", "u": "unknown"}


def _locale(user) -> str:
    return user.locale if user and user.locale else "en"


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------


async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    with SessionLocal() as db:
        user = get_user_by_chat_id(db, chat_id)
        if user is not None:
            locale = _locale(user)
            await update.message.reply_text(
                t("telegram.auth_already_this", locale, username=user.username),
                reply_markup=ReplyKeyboardRemove(),
            )
            return

    # Not authenticated — ask for phone
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("Share my phone number", request_contact=True)]],
        one_time_keyboard=True,
        resize_keyboard=True,
    )
    await update.message.reply_text(
        t("telegram.welcome", "en"),
        reply_markup=keyboard,
    )


# ---------------------------------------------------------------------------
# /logout
# ---------------------------------------------------------------------------


async def handle_logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    with SessionLocal() as db:
        user = get_user_by_chat_id(db, chat_id)
        if user is None:
            await update.message.reply_text(t("telegram.not_authenticated", "en"))
            return
        locale = _locale(user)
        unlink_telegram(db, user)
    await update.message.reply_text(t("telegram.logout_success", locale))


# ---------------------------------------------------------------------------
# Contact share — authentication
# ---------------------------------------------------------------------------


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    contact = update.message.contact
    chat_id = str(update.effective_chat.id)
    telegram_phone = normalize_phone(contact.phone_number)

    with SessionLocal() as db:
        user = find_user_by_phone(db, telegram_phone)

        if user is None:
            await update.message.reply_text(
                t("telegram.auth_not_found", "en"),
                reply_markup=ReplyKeyboardRemove(),
            )
            return

        locale = _locale(user)
        result = link_telegram(db, user, chat_id)

    reply_markup = ReplyKeyboardRemove()
    if result == AuthResult.SUCCESS:
        msg = t("telegram.auth_success", locale, username=user.username)
    elif result == AuthResult.ALREADY_THIS:
        msg = t("telegram.auth_already_this", locale, username=user.username)
    elif result == AuthResult.CONFLICT_CHAT:
        msg = t("telegram.auth_conflict_chat", locale)
    else:  # CONFLICT_USER
        msg = t("telegram.auth_conflict_user", locale)

    await update.message.reply_text(msg, reply_markup=reply_markup)


# ---------------------------------------------------------------------------
# Callback query dispatcher
# ---------------------------------------------------------------------------


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    chat_id = str(update.effective_chat.id)

    with SessionLocal() as db:
        user = get_user_by_chat_id(db, chat_id)
        if user is None:
            await query.edit_message_text(t("telegram.not_authenticated", "en"))
            return

        data = query.data or ""

        if data == "noop":
            return

        if data.startswith("evts:"):
            page = int(data.split(":")[1])
            await _show_events(query, user, db, page)

        elif data.startswith("evt:"):
            event_id = int(data.split(":")[1])
            await _show_event_detail(query, user, db, event_id, back_page=0)

        elif data.startswith("evtp:"):
            # evtp:{event_id}:{player_page}:{back_page}
            _, event_id_s, ppage_s, bpage_s = data.split(":")
            await _show_event_detail(
                query, user, db, int(event_id_s), back_page=int(bpage_s), player_page=int(ppage_s)
            )

        elif data.startswith("sta:"):
            # sta:{event_id}:{player_id}:{status_char}
            _, event_id_s, player_id_s, status_char = data.split(":")
            await _set_status(query, user, db, int(event_id_s), int(player_id_s), status_char)


# ---------------------------------------------------------------------------
# Events list
# ---------------------------------------------------------------------------


async def _show_events(query, user, db, page: int) -> None:
    locale = _locale(user)
    today = datetime.today().date()
    all_upcoming = (
        db.query(Event)
        .filter(Event.event_date >= today)
        .order_by(Event.event_date.asc())
        .all()
    )
    total_pages = max(1, math.ceil(len(all_upcoming) / PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    page_events = all_upcoming[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

    if not all_upcoming:
        await query.edit_message_text(t("telegram.no_events", locale))
        return

    header = t("telegram.events_header", locale, page=page + 1)
    keyboard = events_keyboard(page_events, page, total_pages)
    await query.edit_message_text(header, reply_markup=keyboard)


# ---------------------------------------------------------------------------
# Event detail
# ---------------------------------------------------------------------------


async def _show_event_detail(query, user, db, event_id: int, back_page: int = 0, player_page: int = 0) -> None:
    locale = _locale(user)
    event = db.get(Event, event_id)
    if event is None:
        await query.edit_message_text(t("telegram.no_events", locale))
        return

    # Build event info text
    type_key = f"telegram.event_type_{event.event_type}" if event.event_type in ("training", "match") else "telegram.event_type_other"
    event_type_str = t(type_key, locale)

    lines = [f"*{event_type_str}: {event.title}*"]
    lines.append(f"{t('telegram.date_label', locale)}: {event.event_date}")

    time_str = ""
    if event.event_time:
        time_str = str(event.event_time)[:5]
        if event.event_end_time:
            time_str += f" - {str(event.event_end_time)[:5]}"
        lines.append(f"{t('telegram.time_label', locale)}: {time_str}")

    if event.location:
        lines.append(f"{t('telegram.location_label', locale)}: {event.location}")

    if event.meeting_time:
        meet = str(event.meeting_time)[:5]
        if event.meeting_location:
            meet += f" @ {event.meeting_location}"
        lines.append(f"{t('telegram.meeting_label', locale)}: {meet}")

    if event.description:
        lines.append(f"\n{event.description}")

    # Attendance summary
    atts = db.query(Attendance).filter(Attendance.event_id == event_id).all()
    att_by_player: dict[int, Attendance] = {a.player_id: a for a in atts}
    counts = {"present": 0, "absent": 0, "unknown": 0, "maybe": 0}
    for a in atts:
        counts[a.status] = counts.get(a.status, 0) + 1
    lines.append(
        f"\n{t('telegram.attendance_label', locale)}: ✓ {counts['present']} | ✗ {counts['absent']} | ? {counts['unknown']}"
    )

    text = "\n".join(lines)

    is_admin_or_coach = user.is_admin or user.is_coach

    if not is_admin_or_coach:
        # Member: show own status + status buttons
        own_player = db.query(Player).filter(Player.user_id == user.id, Player.archived_at.is_(None)).first()
        if own_player:
            own_att = att_by_player.get(own_player.id)
            own_status = own_att.status if own_att else "unknown"
            status_label = t(f"telegram.status_{own_status}", locale)
            text += f"\n\n{t('telegram.your_status_label', locale)}: {status_label}"
            keyboard = event_status_keyboard(event_id, own_player.id, back_page=back_page)
        else:
            keyboard = event_status_keyboard.__module__  # fallback — no player linked
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup  # noqa: PLC0415
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("← Back", callback_data=f"evts:{back_page}")]])
    else:
        # Coach/Admin: show full player list with status buttons
        players = (
            db.query(Player)
            .filter(Player.archived_at.is_(None))
            .order_by(Player.last_name, Player.first_name)
            .all()
        )
        total_player_pages = max(1, math.ceil(len(players) / PLAYER_PAGE_SIZE))
        player_page = max(0, min(player_page, total_player_pages - 1))
        page_players = players[player_page * PLAYER_PAGE_SIZE : (player_page + 1) * PLAYER_PAGE_SIZE]

        text += f"\n\n{t('telegram.players_header', locale)}"
        keyboard = event_admin_keyboard(
            event_id, page_players, att_by_player, player_page, total_player_pages, back_page=back_page
        )

    await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------------------------
# Set attendance status
# ---------------------------------------------------------------------------


async def _set_status(query, user, db, event_id: int, player_id: int, status_char: str) -> None:
    locale = _locale(user)
    status = _STATUS_MAP.get(status_char, "unknown")

    # Authorization: member can only update their own player
    if not (user.is_admin or user.is_coach):
        own_player = db.query(Player).filter(Player.user_id == user.id, Player.archived_at.is_(None)).first()
        if own_player is None or own_player.id != player_id:
            await query.answer("Not authorized.", show_alert=True)
            return

    set_attendance(db, event_id, player_id, status)

    status_label = t(f"telegram.status_{status}", locale)
    await query.answer(t("telegram.status_updated", locale, status=status_label), show_alert=False)

    # Re-render the event detail in place
    await _show_event_detail(query, user, db, event_id, back_page=0)
```

- [ ] **Step 2: Commit**

```bash
git add bot/handlers.py
git commit -m "feat: add telegram bot handlers (auth, events list, event detail, status update)"
```

---

## Task 7: `routes/telegram.py` — Webhook Endpoint

**Files:**
- Create: `routes/telegram.py`
- Create: `tests/test_telegram_webhook.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_telegram_webhook.py`:

```python
"""tests/test_telegram_webhook.py — Webhook route tests."""
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings


def test_webhook_rejects_missing_secret(client: TestClient):
    resp = client.post("/telegram/webhook", json={"update_id": 1})
    assert resp.status_code == 403


def test_webhook_rejects_wrong_secret(client: TestClient):
    resp = client.post(
        "/telegram/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
    )
    assert resp.status_code == 403


def test_webhook_accepts_correct_secret(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "test-secret")

    # Patch the bot application so it doesn't actually process
    with patch("routes.telegram._get_app", return_value=None):
        resp = client.post(
            "/telegram/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
    assert resp.status_code == 200


def test_webhook_returns_200_when_bot_disabled(client: TestClient, monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "test-secret")
    with patch("routes.telegram._get_app", return_value=None):
        resp = client.post(
            "/telegram/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        )
    assert resp.status_code == 200
```

Run: `pytest tests/test_telegram_webhook.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'routes.telegram'`

- [ ] **Step 2: Create `routes/telegram.py`**

```python
"""routes/telegram.py — Telegram webhook endpoint."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from telegram import Update

from app.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_app():
    """Return the telegram Application instance (or None if not initialised)."""
    try:
        import bot as _bot  # noqa: PLC0415
        return _bot.telegram_app
    except Exception:
        return None


@router.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> JSONResponse:
    secret = settings.TELEGRAM_WEBHOOK_SECRET
    if not secret or x_telegram_bot_api_secret_token != secret:
        raise HTTPException(status_code=403, detail="Forbidden")

    app = _get_app()
    if app is None:
        return JSONResponse({"ok": True})

    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.process_update(update)
    return JSONResponse({"ok": True})
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_telegram_webhook.py -v
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add routes/telegram.py tests/test_telegram_webhook.py
git commit -m "feat: add telegram webhook route"
```

---

## Task 8: Wire Up in `app/main.py`

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add webhook registration to the lifespan**

In `app/main.py`, update the `lifespan` function. Replace:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _weak_keys = {
        "change-me-in-production",
        "change-me-to-a-long-random-string-before-production",
    }
    if settings.SECRET_KEY in _weak_keys:
        logger.warning(
            "SECRET_KEY is set to the default insecure value. "
            'Generate a new one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    logger.info("Starting up — initialising database …")
    init_db()
    logger.info("Database ready.")
    yield
    logger.info("Shutting down.")
    shutdown_event.set()
```

With:

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _weak_keys = {
        "change-me-in-production",
        "change-me-to-a-long-random-string-before-production",
    }
    if settings.SECRET_KEY in _weak_keys:
        logger.warning(
            "SECRET_KEY is set to the default insecure value. "
            'Generate a new one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    logger.info("Starting up — initialising database …")
    init_db()
    logger.info("Database ready.")

    # ── Telegram Bot ──────────────────────────────────────────────────────
    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_WEBHOOK_URL and settings.TELEGRAM_WEBHOOK_SECRET:
        try:
            import bot as _bot  # noqa: PLC0415

            tg_app = await _bot.init_application(settings.TELEGRAM_BOT_TOKEN)
            webhook_url = f"{settings.TELEGRAM_WEBHOOK_URL.rstrip('/')}/telegram/webhook"
            await tg_app.bot.set_webhook(
                url=webhook_url,
                secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
            )
            logger.info("Telegram webhook registered at %s", webhook_url)
        except Exception:
            logger.exception("Failed to initialise Telegram bot — continuing without it.")
    else:
        logger.info("Telegram bot not configured (TELEGRAM_BOT_TOKEN/TELEGRAM_WEBHOOK_URL/TELEGRAM_WEBHOOK_SECRET not set).")

    yield

    logger.info("Shutting down.")
    shutdown_event.set()

    # ── Telegram Bot shutdown ─────────────────────────────────────────────
    try:
        import bot as _bot  # noqa: PLC0415

        if _bot.telegram_app is not None:
            await _bot.telegram_app.bot.delete_webhook()
            await _bot.shutdown_application()
            logger.info("Telegram webhook deregistered.")
    except Exception:
        logger.debug("Telegram bot not active on shutdown.")
```

- [ ] **Step 2: Add telegram router to `_routers` list**

In `create_app()`, add to the `_routers` list:

```python
        ("routes.telegram", "", "telegram"),
```

Note: the prefix is `""` because the route already has the full path `/telegram/webhook`.

- [ ] **Step 3: Smoke test — start the app**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 7000
```

Expected: app starts, logs `"Telegram bot not configured"` (since `.env` has empty token), no errors.

- [ ] **Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat: wire telegram bot into FastAPI lifespan and router"
```

---

## Task 9: Full Test Suite Pass

**Files:**
- None (verification only)

- [ ] **Step 1: Run all tests**

```bash
pytest -v
```

Expected: all existing tests pass, new telegram tests pass.

- [ ] **Step 2: Run linter**

```bash
ruff check .
ruff format .
```

Fix any reported issues.

- [ ] **Step 3: Final commit if any lint fixes were needed**

```bash
git add -u
git commit -m "fix: ruff lint fixes for telegram bot"
```

---

## Spec Coverage Check

| Spec requirement | Covered by |
|---|---|
| Auth via player phone | Task 4 (`telegram_service.py`) |
| Double-auth prevention | Task 4 (`link_telegram` checks) |
| `/start` + contact share | Task 6 (`handle_start`, `handle_contact`) |
| `/logout` | Task 6 (`handle_logout`) |
| Events list with [View] buttons | Task 6 (`_show_events`, `events_keyboard`) |
| Event detail (all fields) | Task 6 (`_show_event_detail`) |
| Member: own status + update | Task 6 (`event_status_keyboard`, `_set_status`) |
| Coach/Admin: full player list + update | Task 6 (`event_admin_keyboard`, `_set_status`) |
| Role-based access enforced | Task 6 (`_set_status` auth check) |
| Locale-aware messages | Task 3 + Task 6 (`_locale()`, `t()`) |
| Webhook mode, FastAPI integrated | Task 7 + Task 8 |
| `telegram_chat_id` on User | Task 2 |
| Alembic migration | Task 2 |
| Config vars + `.env.example` | Task 1 |
| Graceful no-op when token not set | Task 8 (lifespan guard) |
