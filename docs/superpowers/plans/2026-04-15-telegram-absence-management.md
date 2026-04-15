# Telegram Absence Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add period absence management (create / list / delete) to the Telegram bot, accessible from a new "⚙️ Other" menu on the events list, for players (own absences) and coaches/admins (any player on their team).

**Architecture:** Two new bot modules — `bot/absence_keyboards.py` (pure keyboard builders, easily unit-tested) and `bot/absence_handlers.py` (async handler functions called from the existing `handle_callback` and `handle_text` dispatch in `bot/handlers.py`). All bot-facing absence callbacks start with `abs` prefixes; `other:` drives the new "Other" menu entry point. Absence creation calls the existing `apply_absence_to_future_events` service.

**Tech Stack:** python-telegram-bot, SQLAlchemy, `app.i18n.t()`, existing `services/absence_service.py`.

---

## File Map

| File | Action |
|------|--------|
| `bot/absence_keyboards.py` | **Create** — keyboard builders for Other menu, player list, absence list, delete confirm |
| `bot/absence_handlers.py` | **Create** — async handlers for all absence screens and multi-step add flow |
| `tests/test_absence_keyboards.py` | **Create** — unit tests for keyboard builders |
| `bot/handlers.py` | **Modify** — add `other:`, `absm:`, `absp:`, `absl:`, `absa:`, `absd:`, `absdc:` dispatch; add `awaiting_absence` cleanup; add `/cancel` support; add `handle_absence_text` call in `handle_text` |
| `bot/keyboards.py` | **Modify** — add "⚙️ Other" row to `events_keyboard` |
| `locales/en.json` | **Modify** — add 15 new `telegram.*` keys |
| `locales/it.json` | **Modify** — same keys in Italian |
| `locales/fr.json` | **Modify** — same keys in French |
| `locales/de.json` | **Modify** — same keys in German |

### Callback prefix table

| Prefix | Format | Meaning |
|--------|--------|---------|
| `other:` | `other:{page}` | Show "⚙️ Other" mini-menu |
| `absm:` | `absm:{back_page}` | Absence root (page 0 of player list, or member's own list) |
| `absp:` | `absp:{page}:{back_page}` | Player list page N (coaches/admins only) |
| `absl:` | `absl:{player_id}:{page}:{back_page}` | Absence list for one player |
| `absa:` | `absa:{player_id}:{back_page}` | Start add-absence multi-step flow |
| `absd:` | `absd:{absence_id}:{player_id}:{page}:{back_page}` | Delete confirmation screen |
| `absdc:` | `absdc:{absence_id}:{player_id}:{page}:{back_page}` | Confirmed delete |

---

## Task 1: Add locale keys to all four locale files

**Files:**
- Modify: `locales/en.json`
- Modify: `locales/it.json`
- Modify: `locales/fr.json`
- Modify: `locales/de.json`

- [ ] **Step 1: Add keys to `locales/en.json`**

Find the last key in the `"telegram"` section (`"chat_reply_posted": "..."`) and add the following lines before the closing `}` of the `"telegram"` object:

```json
    "other_button": "⚙️ Other",
    "absences_button": "📅 Absences",
    "absences_header": "📅 Absences — %{name}",
    "absences_empty": "No absences registered.",
    "absence_add_button": "+ Add absence",
    "absence_del_button": "🗑 %{dates}",
    "absence_start_prompt": "Enter start date (YYYY-MM-DD), or /cancel:",
    "absence_end_prompt": "Enter end date (YYYY-MM-DD), or /cancel:",
    "absence_reason_prompt": "Enter reason (optional), or /skip:",
    "absence_added": "Absence added. %{count} event(s) updated.",
    "absence_deleted": "Absence deleted.",
    "absence_date_error": "Invalid date format. Please use YYYY-MM-DD:",
    "absence_past_error": "Start date must be today or in the future:",
    "absence_range_error": "End date must be on or after start date:",
    "absence_confirm_del": "Delete this absence?",
    "absence_confirm_yes": "✅ Yes, delete",
    "absence_confirm_no": "❌ No, keep",
    "select_player": "Select a player:"
```

- [ ] **Step 2: Add keys to `locales/it.json`**

Find `"chat_reply_posted"` in the `"telegram"` section and add before the closing `}`:

```json
    "other_button": "⚙️ Altro",
    "absences_button": "📅 Assenze",
    "absences_header": "📅 Assenze — %{name}",
    "absences_empty": "Nessuna assenza registrata.",
    "absence_add_button": "+ Aggiungi assenza",
    "absence_del_button": "🗑 %{dates}",
    "absence_start_prompt": "Inserisci la data di inizio (AAAA-MM-GG), o /cancel:",
    "absence_end_prompt": "Inserisci la data di fine (AAAA-MM-GG), o /cancel:",
    "absence_reason_prompt": "Inserisci il motivo (opzionale), o /skip:",
    "absence_added": "Assenza aggiunta. %{count} evento/i aggiornato/i.",
    "absence_deleted": "Assenza eliminata.",
    "absence_date_error": "Formato data non valido. Usa AAAA-MM-GG:",
    "absence_past_error": "La data di inizio deve essere oggi o nel futuro:",
    "absence_range_error": "La data di fine deve essere uguale o successiva alla data di inizio:",
    "absence_confirm_del": "Eliminare questa assenza?",
    "absence_confirm_yes": "✅ Sì, elimina",
    "absence_confirm_no": "❌ No, mantieni",
    "select_player": "Seleziona un giocatore:"
```

- [ ] **Step 3: Add keys to `locales/fr.json`**

Find `"chat_reply_posted"` in the `"telegram"` section and add before the closing `}`:

```json
    "other_button": "⚙️ Autre",
    "absences_button": "📅 Absences",
    "absences_header": "📅 Absences — %{name}",
    "absences_empty": "Aucune absence enregistrée.",
    "absence_add_button": "+ Ajouter une absence",
    "absence_del_button": "🗑 %{dates}",
    "absence_start_prompt": "Entrez la date de début (AAAA-MM-JJ), ou /cancel :",
    "absence_end_prompt": "Entrez la date de fin (AAAA-MM-JJ), ou /cancel :",
    "absence_reason_prompt": "Entrez le motif (optionnel), ou /skip :",
    "absence_added": "Absence ajoutée. %{count} événement(s) mis à jour.",
    "absence_deleted": "Absence supprimée.",
    "absence_date_error": "Format de date invalide. Utilisez AAAA-MM-JJ :",
    "absence_past_error": "La date de début doit être aujourd'hui ou dans le futur :",
    "absence_range_error": "La date de fin doit être égale ou postérieure à la date de début :",
    "absence_confirm_del": "Supprimer cette absence ?",
    "absence_confirm_yes": "✅ Oui, supprimer",
    "absence_confirm_no": "❌ Non, garder",
    "select_player": "Sélectionnez un joueur :"
```

- [ ] **Step 4: Add keys to `locales/de.json`**

Find `"chat_reply_posted"` in the `"telegram"` section and add before the closing `}`:

```json
    "other_button": "⚙️ Weitere",
    "absences_button": "📅 Abwesenheiten",
    "absences_header": "📅 Abwesenheiten — %{name}",
    "absences_empty": "Keine Abwesenheiten registriert.",
    "absence_add_button": "+ Abwesenheit hinzufügen",
    "absence_del_button": "🗑 %{dates}",
    "absence_start_prompt": "Startdatum eingeben (JJJJ-MM-TT), oder /cancel:",
    "absence_end_prompt": "Enddatum eingeben (JJJJ-MM-TT), oder /cancel:",
    "absence_reason_prompt": "Grund eingeben (optional), oder /skip:",
    "absence_added": "Abwesenheit hinzugefügt. %{count} Ereignis(se) aktualisiert.",
    "absence_deleted": "Abwesenheit gelöscht.",
    "absence_date_error": "Ungültiges Datumsformat. Bitte JJJJ-MM-TT verwenden:",
    "absence_past_error": "Das Startdatum muss heute oder in der Zukunft liegen:",
    "absence_range_error": "Das Enddatum muss gleich oder nach dem Startdatum liegen:",
    "absence_confirm_del": "Diese Abwesenheit löschen?",
    "absence_confirm_yes": "✅ Ja, löschen",
    "absence_confirm_no": "❌ Nein, behalten",
    "select_player": "Spieler auswählen:"
```

- [ ] **Step 5: Verify JSON is valid**

```bash
python -c "import json; [json.load(open(f'locales/{l}.json')) for l in ['en','it','fr','de']]; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add locales/en.json locales/it.json locales/fr.json locales/de.json
git commit -m "feat(i18n): add telegram absence management locale keys"
```

---

## Task 2: Create `bot/absence_keyboards.py` with tests

**Files:**
- Create: `bot/absence_keyboards.py`
- Create: `tests/test_absence_keyboards.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_absence_keyboards.py`:

```python
"""Unit tests for bot/absence_keyboards.py."""

from types import SimpleNamespace

import pytest

from bot.absence_keyboards import (
    absence_delete_confirm_keyboard,
    absence_list_keyboard,
    absence_player_list_keyboard,
    other_menu_keyboard,
)


def _cb_data(keyboard):
    """Flatten all callback_data values from an InlineKeyboardMarkup."""
    return [btn.callback_data for row in keyboard.inline_keyboard for btn in row]


# ---------------------------------------------------------------------------
# other_menu_keyboard
# ---------------------------------------------------------------------------


def test_other_menu_has_absences_and_back():
    kb = other_menu_keyboard(back_page=2, locale="en")
    data = _cb_data(kb)
    assert any(d.startswith("absm:2") for d in data)
    assert any(d == "evts:2" for d in data)


# ---------------------------------------------------------------------------
# absence_player_list_keyboard
# ---------------------------------------------------------------------------


def _make_player(id_, name):
    p = SimpleNamespace(id=id_, full_name=name)
    return p


def test_player_list_keyboard_buttons():
    players = [_make_player(1, "Alice"), _make_player(2, "Bob")]
    kb = absence_player_list_keyboard(players, page=0, total_pages=1, back_page=3, locale="en")
    data = _cb_data(kb)
    assert "absl:1:0:3" in data
    assert "absl:2:0:3" in data
    assert "other:3" in data


def test_player_list_keyboard_pagination():
    players = [_make_player(i, f"P{i}") for i in range(3)]
    kb = absence_player_list_keyboard(players, page=1, total_pages=3, back_page=0, locale="en")
    data = _cb_data(kb)
    assert any(d.startswith("absp:0:") for d in data)  # Prev
    assert any(d.startswith("absp:2:") for d in data)  # Next


def test_player_list_no_prev_on_first_page():
    players = [_make_player(1, "Alice")]
    kb = absence_player_list_keyboard(players, page=0, total_pages=2, back_page=0, locale="en")
    data = _cb_data(kb)
    assert not any(d.startswith("absp:") and ":0:" not in d for d in data if d.startswith("absp:"))
    # More precisely: no prev button (page-1 = -1 is never added)
    assert not any(d == "absp:-1:0" for d in data)


# ---------------------------------------------------------------------------
# absence_list_keyboard
# ---------------------------------------------------------------------------


def _make_absence(id_, start, end):
    return SimpleNamespace(id=id_, start_date=start, end_date=end)


def test_absence_list_has_delete_add_back_member():
    absences = [_make_absence(10, "2026-05-01", "2026-05-05")]
    kb = absence_list_keyboard(
        absences, player_id=7, page=0, total_pages=1,
        back_page=2, is_member=True, locale="en"
    )
    data = _cb_data(kb)
    assert "absd:10:7:0:2" in data          # delete button
    assert "absa:7:2" in data               # add button
    assert "other:2" in data               # back → Other menu for member


def test_absence_list_back_goes_to_player_list_for_coach():
    kb = absence_list_keyboard(
        [], player_id=5, page=0, total_pages=1,
        back_page=1, is_member=False, locale="en"
    )
    data = _cb_data(kb)
    assert "absm:1" in data                # back → player list for coach


def test_absence_list_pagination():
    absences = [_make_absence(i, f"2026-05-{i:02d}", f"2026-05-{i+1:02d}") for i in range(1, 4)]
    kb = absence_list_keyboard(
        absences, player_id=3, page=1, total_pages=3,
        back_page=0, is_member=False, locale="en"
    )
    data = _cb_data(kb)
    assert "absl:3:0:0" in data   # Prev
    assert "absl:3:2:0" in data   # Next


# ---------------------------------------------------------------------------
# absence_delete_confirm_keyboard
# ---------------------------------------------------------------------------


def test_delete_confirm_keyboard():
    kb = absence_delete_confirm_keyboard(
        absence_id=99, player_id=7, page=0, back_page=2, locale="en"
    )
    data = _cb_data(kb)
    assert "absdc:99:7:0:2" in data   # confirm
    assert "absl:7:0:2" in data       # cancel → back to list
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_absence_keyboards.py -v
```

Expected: `ImportError` — `bot.absence_keyboards` does not exist yet.

- [ ] **Step 3: Create `bot/absence_keyboards.py`**

```python
"""bot/absence_keyboards.py — Inline keyboard builders for absence management."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.i18n import t

ABSENCE_PAGE_SIZE = 8
PLAYER_PAGE_SIZE = 10


def other_menu_keyboard(back_page: int, locale: str = "en") -> InlineKeyboardMarkup:
    """'⚙️ Other' mini-menu: Absences entry + Back to events list."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("telegram.absences_button", locale), callback_data=f"absm:{back_page}")],
        [InlineKeyboardButton(t("telegram.back_button", locale), callback_data=f"evts:{back_page}")],
    ])


def absence_player_list_keyboard(
    players: list,
    page: int,
    total_pages: int,
    back_page: int,
    locale: str = "en",
) -> InlineKeyboardMarkup:
    """Paginated player list for coach/admin absence selection.

    Each player button navigates to their absence list (page 0).
    Pagination uses ``absp:{page}:{back_page}`` callbacks.
    Back returns to the Other menu.
    """
    rows = []
    for player in players:
        rows.append([
            InlineKeyboardButton(
                player.full_name,
                callback_data=f"absl:{player.id}:0:{back_page}",
            )
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            t("telegram.prev_button", locale),
            callback_data=f"absp:{page - 1}:{back_page}",
        ))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(
            t("telegram.next_button", locale),
            callback_data=f"absp:{page + 1}:{back_page}",
        ))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(
        t("telegram.back_button", locale),
        callback_data=f"other:{back_page}",
    )])
    return InlineKeyboardMarkup(rows)


def absence_list_keyboard(
    absences: list,
    player_id: int,
    page: int,
    total_pages: int,
    back_page: int,
    is_member: bool,
    locale: str = "en",
) -> InlineKeyboardMarkup:
    """One delete button per absence, Add button, pagination, and Back.

    Back destination differs by role:
    - Member → ``other:{back_page}`` (Other menu, since absm: skips player list)
    - Coach/Admin → ``absm:{back_page}`` (player list)
    """
    rows = []
    for absence in absences:
        dates = f"{absence.start_date} → {absence.end_date}"
        rows.append([InlineKeyboardButton(
            t("telegram.absence_del_button", locale, dates=dates),
            callback_data=f"absd:{absence.id}:{player_id}:{page}:{back_page}",
        )])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(
            t("telegram.prev_button", locale),
            callback_data=f"absl:{player_id}:{page - 1}:{back_page}",
        ))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(
            t("telegram.next_button", locale),
            callback_data=f"absl:{player_id}:{page + 1}:{back_page}",
        ))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(
        t("telegram.absence_add_button", locale),
        callback_data=f"absa:{player_id}:{back_page}",
    )])

    back_dest = f"other:{back_page}" if is_member else f"absm:{back_page}"
    rows.append([InlineKeyboardButton(
        t("telegram.back_button", locale),
        callback_data=back_dest,
    )])
    return InlineKeyboardMarkup(rows)


def absence_delete_confirm_keyboard(
    absence_id: int,
    player_id: int,
    page: int,
    back_page: int,
    locale: str = "en",
) -> InlineKeyboardMarkup:
    """Yes/No confirmation before deleting an absence."""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            t("telegram.absence_confirm_yes", locale),
            callback_data=f"absdc:{absence_id}:{player_id}:{page}:{back_page}",
        ),
        InlineKeyboardButton(
            t("telegram.absence_confirm_no", locale),
            callback_data=f"absl:{player_id}:{page}:{back_page}",
        ),
    ]])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_absence_keyboards.py -v
```

Expected: all 9 tests pass.

- [ ] **Step 5: Commit**

```bash
git add bot/absence_keyboards.py tests/test_absence_keyboards.py
git commit -m "feat(bot): add absence keyboard builders"
```

---

## Task 3: Create `bot/absence_handlers.py`

**Files:**
- Create: `bot/absence_handlers.py`

No unit tests for handler functions (they depend on live Telegram objects and are verified end-to-end). The DB interactions use the same `SessionLocal` pattern as `handlers.py`.

- [ ] **Step 1: Create `bot/absence_handlers.py`**

```python
"""bot/absence_handlers.py — Telegram absence management handler functions.

All public async functions are called from bot/handlers.py dispatch blocks.
They follow the same pattern as the private helpers in handlers.py:
  - accept (query, user, db, ...) for callback-driven screens
  - open their own SessionLocal for text-input handlers
"""

from __future__ import annotations

import asyncio
import math
from datetime import date

from telegram import Update
from telegram.ext import ContextTypes

from app.database import SessionLocal
from app.i18n import t
from bot.absence_keyboards import (
    ABSENCE_PAGE_SIZE,
    PLAYER_PAGE_SIZE,
    absence_delete_confirm_keyboard,
    absence_list_keyboard,
    absence_player_list_keyboard,
    other_menu_keyboard,
)
from models.player import Player
from models.player_absence import PlayerAbsence
from models.player_team import PlayerTeam
from models.user_team import UserTeam
from services.absence_service import apply_absence_to_future_events
from services.telegram_service import get_user_by_chat_id


def _locale(user) -> str:
    return user.locale if user and user.locale else "en"


# ---------------------------------------------------------------------------
# Other menu
# ---------------------------------------------------------------------------


async def show_other_menu(query, user, back_page: int) -> None:
    """Render the '⚙️ Other' mini-menu."""
    locale = _locale(user)
    await query.edit_message_text(
        t("telegram.other_button", locale),
        reply_markup=other_menu_keyboard(back_page, locale),
    )


# ---------------------------------------------------------------------------
# Absence root — branches by role
# ---------------------------------------------------------------------------


async def show_absence_root(query, user, db, back_page: int) -> None:
    """Entry point from the Other menu.

    Members go directly to their own absence list.
    Coaches/admins see the paginated player list.
    """
    if user.is_admin or user.is_coach:
        await show_absence_player_list(query, user, db, page=0, back_page=back_page)
    else:
        player = db.query(Player).filter(
            Player.user_id == user.id,
            Player.archived_at.is_(None),
        ).first()
        if player is None:
            await query.edit_message_text(t("telegram.not_authenticated", _locale(user)))
            return
        await show_absence_list(query, user, db, player_id=player.id, page=0, back_page=back_page, is_member=True)


# ---------------------------------------------------------------------------
# Player list (coach/admin only)
# ---------------------------------------------------------------------------


async def show_absence_player_list(query, user, db, page: int, back_page: int) -> None:
    """Paginated list of players for coach/admin to pick from."""
    locale = _locale(user)

    if user.is_admin:
        players_q = (
            db.query(Player)
            .filter(Player.archived_at.is_(None))
            .order_by(Player.first_name, Player.last_name)
            .all()
        )
    else:
        team_ids = {
            r[0] for r in db.query(UserTeam.team_id).filter(UserTeam.user_id == user.id).all()
        }
        player_ids = {
            r[0] for r in db.query(PlayerTeam.player_id).filter(PlayerTeam.team_id.in_(team_ids)).all()
        }
        players_q = (
            db.query(Player)
            .filter(Player.id.in_(player_ids), Player.archived_at.is_(None))
            .order_by(Player.first_name, Player.last_name)
            .all()
        )

    total_pages = max(1, math.ceil(len(players_q) / PLAYER_PAGE_SIZE))
    page = max(0, min(page, total_pages - 1))
    page_players = players_q[page * PLAYER_PAGE_SIZE : (page + 1) * PLAYER_PAGE_SIZE]

    keyboard = absence_player_list_keyboard(page_players, page, total_pages, back_page, locale)
    await query.edit_message_text(t("telegram.select_player", locale), reply_markup=keyboard)


# ---------------------------------------------------------------------------
# Absence list for one player
# ---------------------------------------------------------------------------


async def show_absence_list(query, user, db, player_id: int, page: int, back_page: int, is_member: bool) -> None:
    """Show all period absences for a player with delete buttons."""
    locale = _locale(user)

    player = db.get(Player, player_id)
    if player is None:
        await query.edit_message_text(t("telegram.unknown_error", locale))
        return

    absences = (
        db.query(PlayerAbsence)
        .filter(PlayerAbsence.player_id == player_id, PlayerAbsence.absence_type == "period")
        .order_by(PlayerAbsence.start_date)
        .all()
    )

    total_pages = max(1, math.ceil(len(absences) / ABSENCE_PAGE_SIZE)) if absences else 1
    page = max(0, min(page, total_pages - 1))
    page_absences = absences[page * ABSENCE_PAGE_SIZE : (page + 1) * ABSENCE_PAGE_SIZE]

    header = t("telegram.absences_header", locale, name=player.full_name)
    if not absences:
        header += f"\n\n{t('telegram.absences_empty', locale)}"

    keyboard = absence_list_keyboard(page_absences, player_id, page, total_pages, back_page, is_member, locale)
    await query.edit_message_text(header, reply_markup=keyboard)


# ---------------------------------------------------------------------------
# Add absence — multi-step text flow
# ---------------------------------------------------------------------------


async def start_add_absence(query, user, context: ContextTypes.DEFAULT_TYPE, player_id: int, back_page: int) -> None:
    """Begin the add-absence multi-step flow (step 1: start date)."""
    locale = _locale(user)
    prompt_msg = await query.message.reply_text(t("telegram.absence_start_prompt", locale))
    context.user_data["awaiting_absence"] = {
        "player_id": player_id,
        "back_page": back_page,
        "step": "start",
        "start_date": None,
        "end_date": None,
        "prompt_message_id": prompt_msg.message_id,
        "chat_id": query.message.chat_id,
    }


async def handle_absence_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Process one step of the add-absence multi-step input flow.

    Returns True if this message was consumed by the absence flow (caller
    should ``return`` immediately). Returns False if no absence flow is active.

    Steps: start date → end date → reason → create absence → show list.
    """
    pending = context.user_data.get("awaiting_absence")
    if not pending:
        return False

    chat_id = str(update.effective_chat.id)
    text = (update.message.text or "").strip()
    step = pending["step"]
    prompt_msg_id = pending.get("prompt_message_id")
    abs_chat_id = pending.get("chat_id")

    # Clean up previous prompt + user message
    if prompt_msg_id and abs_chat_id:
        try:
            await context.bot.delete_message(chat_id=abs_chat_id, message_id=prompt_msg_id)
        except Exception:
            pass
    try:
        await update.message.delete()
    except Exception:
        pass

    with SessionLocal() as db:
        user = get_user_by_chat_id(db, chat_id)
        if user is None:
            context.user_data.pop("awaiting_absence", None)
            return True
        locale = _locale(user)

        if step == "start":
            try:
                parsed = date.fromisoformat(text)
            except ValueError:
                new_prompt = await update.message.reply_text(t("telegram.absence_date_error", locale))
                pending["prompt_message_id"] = new_prompt.message_id
                return True
            if parsed < date.today():
                new_prompt = await update.message.reply_text(t("telegram.absence_past_error", locale))
                pending["prompt_message_id"] = new_prompt.message_id
                return True
            pending["start_date"] = parsed.isoformat()
            pending["step"] = "end"
            new_prompt = await update.message.reply_text(t("telegram.absence_end_prompt", locale))
            pending["prompt_message_id"] = new_prompt.message_id
            return True

        elif step == "end":
            try:
                parsed = date.fromisoformat(text)
            except ValueError:
                new_prompt = await update.message.reply_text(t("telegram.absence_date_error", locale))
                pending["prompt_message_id"] = new_prompt.message_id
                return True
            start = date.fromisoformat(pending["start_date"])
            if parsed < start:
                new_prompt = await update.message.reply_text(t("telegram.absence_range_error", locale))
                pending["prompt_message_id"] = new_prompt.message_id
                return True
            pending["end_date"] = parsed.isoformat()
            pending["step"] = "reason"
            new_prompt = await update.message.reply_text(t("telegram.absence_reason_prompt", locale))
            pending["prompt_message_id"] = new_prompt.message_id
            return True

        elif step == "reason":
            reason = None if text.lower() == "/skip" or not text else text
            player_id = pending["player_id"]
            back_page = pending["back_page"]
            start_date = date.fromisoformat(pending["start_date"])
            end_date = date.fromisoformat(pending["end_date"])

            absence = PlayerAbsence(
                player_id=player_id,
                absence_type="period",
                start_date=start_date,
                end_date=end_date,
                reason=reason,
            )
            db.add(absence)
            db.commit()
            count = apply_absence_to_future_events(player_id, db)

            context.user_data.pop("awaiting_absence", None)

            conf = await update.message.reply_text(
                t("telegram.absence_added", locale, count=count)
            )
            await asyncio.sleep(2)
            try:
                await conf.delete()
            except Exception:
                pass

            # Send a fresh absence list message (can't edit the old bot message from handle_text)
            is_member = not (user.is_admin or user.is_coach)
            player = db.get(Player, player_id)
            absences = (
                db.query(PlayerAbsence)
                .filter(PlayerAbsence.player_id == player_id, PlayerAbsence.absence_type == "period")
                .order_by(PlayerAbsence.start_date)
                .all()
            )
            page = 0
            total_pages = max(1, math.ceil(len(absences) / ABSENCE_PAGE_SIZE)) if absences else 1
            page_absences = absences[page * ABSENCE_PAGE_SIZE : (page + 1) * ABSENCE_PAGE_SIZE]

            header = t("telegram.absences_header", locale, name=player.full_name)
            keyboard = absence_list_keyboard(page_absences, player_id, page, total_pages, back_page, is_member, locale)
            await update.message.reply_text(header, reply_markup=keyboard)
            return True

    return True


# ---------------------------------------------------------------------------
# Delete absence
# ---------------------------------------------------------------------------


async def confirm_delete_absence(query, user, db, absence_id: int, player_id: int, page: int, back_page: int) -> None:
    """Show a Yes/No confirmation screen before deleting."""
    locale = _locale(user)
    absence = db.get(PlayerAbsence, absence_id)
    if absence is None or absence.player_id != player_id:
        await query.edit_message_text(t("telegram.unknown_error", locale))
        return
    dates = f"{absence.start_date} → {absence.end_date}"
    keyboard = absence_delete_confirm_keyboard(absence_id, player_id, page, back_page, locale)
    await query.edit_message_text(
        f"{t('telegram.absence_confirm_del', locale)}\n{dates}",
        reply_markup=keyboard,
    )


async def delete_absence(query, user, db, absence_id: int, player_id: int, page: int, back_page: int) -> None:
    """Delete the absence and refresh the absence list."""
    absence = db.get(PlayerAbsence, absence_id)
    if absence and absence.player_id == player_id:
        db.delete(absence)
        db.commit()
    is_member = not (user.is_admin or user.is_coach)
    await show_absence_list(query, user, db, player_id, page, back_page, is_member)
```

- [ ] **Step 2: Run the full test suite to confirm nothing is broken**

```bash
pytest -v
```

Expected: all existing tests pass (new file has no tests of its own, but shouldn't break anything).

- [ ] **Step 3: Commit**

```bash
git add bot/absence_handlers.py
git commit -m "feat(bot): add absence handler functions"
```

---

## Task 4: Wire everything into `bot/handlers.py` and `bot/keyboards.py`

**Files:**
- Modify: `bot/handlers.py`
- Modify: `bot/keyboards.py`

Four changes in `bot/handlers.py`:
1. Add `awaiting_absence` to the navigation-cleanup block
2. Add `awaiting_absence` to `handle_cancel`
3. Add absence callback dispatch blocks (`other:`, `absm:`, `absp:`, `absl:`, `absa:`, `absd:`, `absdc:`)
4. Add `handle_absence_text` call at the top of `handle_text`

One change in `bot/keyboards.py`:
5. Add "⚙️ Other" button row to `events_keyboard`

- [ ] **Step 1: Add `awaiting_absence` to the cleanup block in `handle_callback`**

In `bot/handlers.py`, find this line (around line 243):

```python
        for _key in ("awaiting_note", "awaiting_chat_reply") + (() if _skip_ext_cleanup else ("awaiting_external",)) + (() if _skip_extn_cleanup else ("awaiting_ext_note",)):
```

Replace with:

```python
        for _key in ("awaiting_note", "awaiting_chat_reply", "awaiting_absence") + (() if _skip_ext_cleanup else ("awaiting_external",)) + (() if _skip_extn_cleanup else ("awaiting_ext_note",)):
```

Note: unlike `extsta:`, the absence flow has no mid-step callback that needs `awaiting_absence` preserved — any button tap should cancel the flow, so no skip flag is needed.

- [ ] **Step 2: Add `awaiting_absence` cleanup to `handle_cancel`**

Find `handle_cancel` (around line 646). It currently pops several keys. Add `"awaiting_absence"` to the list:

```python
async def handle_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    cancelled = (
        context.user_data.pop("awaiting_note", None)
        or context.user_data.pop("awaiting_ext_note", None)
        or context.user_data.pop("awaiting_external", None)
        or context.user_data.pop("awaiting_chat_reply", None)
        or context.user_data.pop("awaiting_absence", None)
    )
    if cancelled:
        with SessionLocal() as db:
            user = get_user_by_chat_id(db, chat_id)
            locale = _locale(user) if user else "en"
        await update.message.reply_text(t("telegram.note_cancelled", locale))
    else:
        await update.message.reply_text("OK.")
```

- [ ] **Step 3: Add the absence callback dispatch blocks to `handle_callback`**

In `handle_callback`, find the last `elif` block (the `chatreply:` handler, ending around line 442). Add the following blocks immediately after it, before the closing of the function:

```python
        elif data.startswith("other:"):
            await query.answer()
            # other:{back_page}
            from bot.absence_handlers import show_other_menu  # noqa: PLC0415
            back_page_o = int(data.split(":")[1])
            await show_other_menu(query, user, back_page=back_page_o)

        elif data.startswith("absm:"):
            await query.answer()
            # absm:{back_page}
            from bot.absence_handlers import show_absence_root  # noqa: PLC0415
            back_page_am = int(data.split(":")[1])
            await show_absence_root(query, user, db, back_page=back_page_am)

        elif data.startswith("absp:"):
            await query.answer()
            # absp:{page}:{back_page}
            from bot.absence_handlers import show_absence_player_list  # noqa: PLC0415
            parts = data.split(":")
            await show_absence_player_list(query, user, db, page=int(parts[1]), back_page=int(parts[2]))

        elif data.startswith("absl:"):
            await query.answer()
            # absl:{player_id}:{page}:{back_page}
            from bot.absence_handlers import show_absence_list  # noqa: PLC0415
            parts = data.split(":")
            player_id_al, page_al, back_page_al = int(parts[1]), int(parts[2]), int(parts[3])
            is_member_al = not (user.is_admin or user.is_coach)
            await show_absence_list(query, user, db, player_id_al, page_al, back_page_al, is_member_al)

        elif data.startswith("absa:"):
            await query.answer()
            # absa:{player_id}:{back_page}
            from bot.absence_handlers import start_add_absence  # noqa: PLC0415
            parts = data.split(":")
            await start_add_absence(query, user, context, int(parts[1]), int(parts[2]))

        elif data.startswith("absd:"):
            await query.answer()
            # absd:{absence_id}:{player_id}:{page}:{back_page}
            from bot.absence_handlers import confirm_delete_absence  # noqa: PLC0415
            parts = data.split(":")
            await confirm_delete_absence(query, user, db, int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]))

        elif data.startswith("absdc:"):
            await query.answer()
            # absdc:{absence_id}:{player_id}:{page}:{back_page}
            from bot.absence_handlers import delete_absence  # noqa: PLC0415
            parts = data.split(":")
            await delete_absence(query, user, db, int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4]))
```

- [ ] **Step 4: Add `handle_absence_text` call to `handle_text`**

In `handle_text` (around line 668), find the very first line of the function body:

```python
    chat_id = str(update.effective_chat.id)

    # Handle external name input
    pending_ext = context.user_data.get("awaiting_external")
```

Insert the absence check before it:

```python
    chat_id = str(update.effective_chat.id)

    # Handle absence multi-step input
    from bot.absence_handlers import handle_absence_text  # noqa: PLC0415
    if await handle_absence_text(update, context):
        return

    # Handle external name input
    pending_ext = context.user_data.get("awaiting_external")
```

- [ ] **Step 5: Add "⚙️ Other" button to `events_keyboard` in `bot/keyboards.py`**

Find the `events_keyboard` function. Its current last line before `return` is:

```python
    rows.append(nav)

    return InlineKeyboardMarkup(rows)
```

Replace with:

```python
    rows.append(nav)
    rows.append([InlineKeyboardButton(t("telegram.other_button", locale), callback_data=f"other:{page}")])

    return InlineKeyboardMarkup(rows)
```

- [ ] **Step 6: Run the full test suite**

```bash
pytest -v && ruff check .
```

Expected: all tests pass, no ruff errors.

- [ ] **Step 7: Commit**

```bash
git add bot/handlers.py bot/keyboards.py
git commit -m "feat(bot): wire absence management into event list and callback dispatcher"
```

---

## Verification Checklist

After all tasks complete, verify end-to-end with the running bot:

1. **Other button visible**: Events list shows "⚙️ Other" / "⚙️ Altro" below Refresh/View More.
2. **Other menu**: Tapping it shows "📅 Absences" + "← Back". Back returns to events list.
3. **Member flow**: Tapping Absences shows own absence list (or empty state). "← Back" returns to Other menu.
4. **Coach flow**: Tapping Absences shows paginated player list. Selecting a player shows their absences. "← Back" returns to player list.
5. **Add absence (happy path)**: Tap "+ Add absence" → enter valid start date → valid end date → reason or /skip → see "Absence added. N event(s) updated." → updated absence list appears.
6. **Add absence — bad date format**: Enter `"tomorrow"` as start date → see format error, re-prompted. Enter valid date → flow continues.
7. **Add absence — past date**: Enter yesterday's date → see "must be today or future" error, re-prompted.
8. **Add absence — end before start**: Enter end date before start → see range error, re-prompted.
9. **Delete absence**: Tap 🗑 button → confirmation screen appears → "Yes, delete" → absence removed, list refreshed. "No, keep" → back to list with no change.
10. **Cancel mid-flow**: Start add flow, then type `/cancel` → "Note entry cancelled." state cleared.
11. **Navigate away mid-flow**: Start add flow, then tap any other button → pending state cleaned up, no ghost prompt message left.
12. **Attendance sync**: Add an absence covering a future event's date → check that event's attendance shows the player as absent with `[Absence]` note.
