# Telegram Bot Redesign — Single Persistent Message Navigation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace the Telegram bot's reply keyboard with a single persistent inline-keyboard message per user that edits in-place as a mini-app, with new notification delivery injecting a 🔔 button without interrupting navigation.

**Architecture:** One message per user (stored in `User.telegram_notification_message_id`) is edited in-place for all navigation. New package `bot/views/` holds renderers that return `(str, InlineKeyboardMarkup)`. `bot/navigation.py` routes new callbacks, edits the persistent message, and tracks `User.telegram_current_view`. `services/telegram_notifications.py` injects a 🔔 button by re-rendering the current view instead of deleting and re-sending.

**Tech Stack:** python-telegram-bot 20.x, SQLAlchemy 2.x, FastAPI, Alembic, pytest

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `models/user.py` | Add `telegram_current_view` column |
| Create | `alembic/versions/s7t8u9v0w1x2_add_telegram_current_view.py` | DB migration |
| Create | `bot/views/__init__.py` | `ViewResult` type alias |
| Create | `bot/views/home.py` | `render_home(user, db)` |
| Create | `bot/views/events.py` | `render_events_list`, `render_event_detail`, `render_event_chat` |
| Create | `bot/views/notifications.py` | `render_notifications_list`, `render_notification_detail` |
| Create | `bot/views/other.py` | `render_other` (wraps absence root entry) |
| Create | `bot/navigation.py` | `navigate()`, `inject_notification()`, `rerender_current_view()` |
| Modify | `bot/keyboards.py` | Add `home_keyboard()`; update `events_keyboard` to use `e:ID` and `el:N` |
| Modify | `bot/absence_keyboards.py` | Update `other_menu_keyboard` back button → `home` |
| Modify | `bot/handlers.py` | Replace `_send_events_list` with homepage send; add new callback routing; remove nav dispatch |
| Modify | `bot/__init__.py` | Remove `handle_nav_dispatch` / `handle_menu` registrations |
| Modify | `services/telegram_notifications.py` | Replace delete+resend with `inject_notification()` |

### Callback scheme

| New callback | Old equivalent | View |
|---|---|---|
| `home` | — | Homepage |
| `nl` | `notif:0` | Notifications list p0 |
| `nl:N` | `notif:N` | Notifications list page N |
| `n:ID` | — | Notification detail (new) |
| `el` | `evts:0` | Events list p0 |
| `el:N` | `evts:N` | Events list page N |
| `e:ID` | `evt:ID` | Event detail |
| `ec:ID` | — | Event chat read-only (new) |
| `ab` | `absm:0` | Absence root |
| `other:0` | `other:0` | Other mini-menu (kept, back→`home`) |

Old sub-action callbacks (`evte:`, `evtp:`, `evtn:`, `evtx:`, `sta:`, `note:`, `ext*:`, `abs*:`) are **unchanged** — they still call `query.edit_message_text()` which edits the persistent message correctly since all buttons live on that message.

---

## Task 1: Add `telegram_current_view` to User model

**Files:**
- Modify: `models/user.py`
- Create: `alembic/versions/s7t8u9v0w1x2_add_telegram_current_view.py`

- [x] **Step 1.1: Add column to User model**

  In `models/user.py`, after the `telegram_notification_message_id` line, add:

  ```python
  # Tracks which view the persistent Telegram message is currently showing ("home", "el", "e:42", etc.)
  telegram_current_view: Mapped[str] = mapped_column(String(20), nullable=False, default="home")
  ```

- [x] **Step 1.2: Create alembic migration**

  ```bash
  cd /home/denny/Development/promanager && source .venv/bin/activate
  alembic revision -m "add_telegram_current_view"
  ```

  Edit the generated file in `alembic/versions/` — replace `upgrade` and `downgrade`:

  ```python
  def upgrade() -> None:
      op.add_column(
          "users",
          sa.Column("telegram_current_view", sa.String(20), nullable=False, server_default="home"),
      )

  def downgrade() -> None:
      op.drop_column("users", "telegram_current_view")
  ```

- [x] **Step 1.3: Apply migration**

  ```bash
  alembic upgrade head
  ```

  Expected: migration applies cleanly, no errors.

- [x] **Step 1.4: Verify column exists**

  ```bash
  python3 -c "
  from app.database import SessionLocal
  from models.user import User
  with SessionLocal() as db:
      u = db.query(User).first()
      if u:
          print('telegram_current_view:', u.telegram_current_view)
      else:
          print('no users yet — column exists if no error')
  "
  ```

- [x] **Step 1.5: Commit**

  ```bash
  git add models/user.py alembic/versions/
  git commit -m "feat: add telegram_current_view column to users"
  ```

---

## Task 2: Create `bot/views/` package

**Files:**
- Create: `bot/views/__init__.py`
- Create: `bot/views/home.py`

- [x] **Step 2.1: Create package init**

  Create `bot/views/__init__.py`:

  ```python
  """bot/views/ — Pure view renderers returning (text, InlineKeyboardMarkup)."""
  from __future__ import annotations

  from telegram import InlineKeyboardMarkup

  ViewResult = tuple[str, InlineKeyboardMarkup]
  ```

- [x] **Step 2.2: Create `bot/views/home.py`**

  ```python
  """bot/views/home.py — Homepage view renderer."""
  from __future__ import annotations

  from telegram import InlineKeyboardButton, InlineKeyboardMarkup

  from app.i18n import t
  from bot.views import ViewResult


  def render_home(user, db) -> ViewResult:
      from models.notification import Notification  # noqa: PLC0415
      from models.player import Player  # noqa: PLC0415
      from models.telegram_notification import TelegramNotification  # noqa: PLC0415

      locale = user.locale or "en"
      is_admin_or_coach = user.is_admin or user.is_coach

      last_notif_text: str | None = None
      last_notif_ts: str | None = None

      if is_admin_or_coach:
          notif = (
              db.query(TelegramNotification)
              .filter(TelegramNotification.user_id == user.id)
              .order_by(TelegramNotification.created_at.desc())
              .first()
          )
          if notif:
              player = notif.player
              player_name = player.full_name if player else f"Player {notif.player_id}"
              event = notif.event
              event_title = event.title if event else "Event"
              icon = {"present": "✓", "absent": "✗", "unknown": "?"}.get(notif.status, "?")
              last_notif_text = f"{icon} {player_name} → {notif.status}\n{event_title}"
              if notif.created_at:
                  last_notif_ts = notif.created_at.strftime("%d %b %H:%M")
      else:
          linked_player = db.query(Player).filter(
              Player.user_id == user.id, Player.archived_at.is_(None)
          ).first()
          if linked_player:
              notif = (
                  db.query(Notification)
                  .filter(Notification.player_id == linked_player.id)
                  .order_by(Notification.created_at.desc())
                  .first()
              )
              if notif:
                  body = notif.body[:200] + "…" if len(notif.body) > 200 else notif.body
                  last_notif_text = f"*{notif.title}*\n{body}"
                  if notif.created_at:
                      last_notif_ts = notif.created_at.strftime("%d %b %H:%M")

      parts = ["🏠 *ProManager*\n"]
      if last_notif_text:
          parts.append("📣 Last notification:")
          parts.append(last_notif_text)
          if last_notif_ts:
              parts.append(f"_{last_notif_ts}_")
      else:
          parts.append("_No notifications yet_")

      text = "\n".join(parts)
      keyboard = _home_keyboard(locale)
      return text, keyboard


  def _home_keyboard(locale: str = "en") -> InlineKeyboardMarkup:
      return InlineKeyboardMarkup([
          [
              InlineKeyboardButton(t("telegram.notifications_button", locale), callback_data="nl"),
              InlineKeyboardButton(t("telegram.events_button", locale), callback_data="el"),
          ],
          [
              InlineKeyboardButton(t("telegram.absences_button", locale), callback_data="ab"),
              InlineKeyboardButton(t("telegram.other_button", locale), callback_data="other:0"),
          ],
      ])
  ```

  > **Note on i18n:** `t()` raises `KeyError` in DEBUG mode for missing keys. `notifications_button` and `events_button` do NOT exist yet — they must be added in Task 7, Step 7.7 before this view is called.

- [x] **Step 2.3: Verify import works**

  ```bash
  python3 -c "from bot.views.home import render_home; print('OK')"
  ```

- [x] **Step 2.4: Commit**

  ```bash
  git add bot/views/
  git commit -m "feat: add bot/views package and home renderer"
  ```

---

## Task 3: Create `bot/views/events.py`

**Files:**
- Create: `bot/views/events.py`

This is adapted from `_show_events` (lines 735–761), `_show_event_detail` (lines 762–890), and new `render_event_chat`.

- [x] **Step 3.1: Create `bot/views/events.py`**

  ```python
  """bot/views/events.py — Events view renderers."""
  from __future__ import annotations

  import math
  from datetime import datetime

  from telegram import InlineKeyboardButton, InlineKeyboardMarkup
  from telegram.constants import ParseMode

  from app.i18n import t
  from bot.keyboards import (
      PLAYER_PAGE_SIZE,
      STATUS_ICON,
      event_admin_keyboard,
      event_view_keyboard,
      event_status_keyboard,
  )
  from bot.views import ViewResult
  from models.attendance import Attendance
  from models.event import Event
  from models.event_external import EventExternal
  from models.player import Player
  from models.player_team import PlayerTeam

  PAGE_SIZE = 5


  def _locale(user) -> str:
      return user.locale or "en"


  def _visible_team_ids(user, db) -> set[int] | None:
      from models.user_team import UserTeam  # noqa: PLC0415

      if user.is_admin:
          return None
      if user.is_coach:
          rows = db.query(UserTeam.team_id).filter(UserTeam.user_id == user.id).all()
          return {r[0] for r in rows}
      player = db.query(Player).filter(Player.user_id == user.id, Player.archived_at.is_(None)).first()
      if player is None:
          return set()
      rows = db.query(PlayerTeam.team_id).filter(PlayerTeam.player_id == player.id).all()
      return {r[0] for r in rows}


  def _upcoming_events(db, user) -> list[Event]:
      today = datetime.today().date()
      q = db.query(Event).filter(Event.event_date >= today)
      team_ids = _visible_team_ids(user, db)
      if team_ids is not None:
          q = q.filter(Event.team_id.in_(team_ids))
      return q.order_by(Event.event_date.asc()).all()


  def render_events_list(user, db, page: int = 0) -> ViewResult:
      locale = _locale(user)
      all_events = _upcoming_events(db, user)
      total_pages = max(1, math.ceil(len(all_events) / PAGE_SIZE))
      page = max(0, min(page, total_pages - 1))
      page_events = all_events[page * PAGE_SIZE : (page + 1) * PAGE_SIZE]

      if not all_events:
          keyboard = InlineKeyboardMarkup([[
              InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home"),
          ]])
          return t("telegram.no_events", locale), keyboard

      header = t("telegram.events_header", locale, page=page + 1)
      rows = []
      for event in page_events:
          time_val = event.meeting_time or event.event_time
          time_str = f" {str(time_val)[:5]}" if time_val else ""
          label = f"{event.event_date}{time_str} — {event.title}"
          rows.append([InlineKeyboardButton(label, callback_data=f"e:{event.id}")])

      nav = []
      if page > 0:
          nav.append(InlineKeyboardButton(t("telegram.prev_button", locale), callback_data=f"el:{page - 1}"))
      if page < total_pages - 1:
          nav.append(InlineKeyboardButton(t("telegram.view_more_button", locale), callback_data=f"el:{page + 1}"))
      rows.append(nav if nav else [InlineKeyboardButton("—", callback_data="noop")])
      rows.append([InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home")])

      return header, InlineKeyboardMarkup(rows)


  def render_event_detail(user, db, event_id: int, back: str = "el") -> ViewResult:
      locale = _locale(user)
      event = db.get(Event, event_id)
      if event is None:
          return t("telegram.no_events", locale), InlineKeyboardMarkup([[
              InlineKeyboardButton(t("telegram.back_button", locale), callback_data=back),
          ]])

      if event.event_type in ("training", "match"):
          event_type_str = t(f"telegram.event_type_{event.event_type}", locale)
      else:
          event_type_str = t("telegram.event_type_other", locale)

      lines = [f"*{event_type_str}: {event.title}*"]
      lines.append(f"{t('telegram.date_label', locale)}: {event.event_date}")

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

      atts = db.query(Attendance).filter(Attendance.event_id == event_id).all()
      att_by_player: dict[int, Attendance] = {a.player_id: a for a in atts}
      ext_rows = (
          db.query(EventExternal)
          .filter(EventExternal.event_id == event_id)
          .order_by(EventExternal.created_at)
          .all()
      )
      counts: dict[str, int] = {"present": 0, "absent": 0, "unknown": 0, "maybe": 0}
      for a in atts:
          counts[a.status] = counts.get(a.status, 0) + 1
      for ext in ext_rows:
          counts[ext.status] = counts.get(ext.status, 0) + 1
      lines.append(
          f"\n{t('telegram.attendance_label', locale)}: ✓ {counts['present']} | ✗ {counts['absent']} | ? {counts['unknown']}"
      )

      # Check for chat messages
      from models.event_message import EventMessage  # noqa: PLC0415
      msg_count = db.query(EventMessage).filter(EventMessage.event_id == event_id).count()

      text = "\n".join(lines)
      is_admin_or_coach = user.is_admin or user.is_coach

      # Use back_page=0 for sub-action keyboards (evte:, evtp:, evtn:, evtx:)
      # These use evts:0 as their back which now routes to el → same destination
      back_page = 0

      if not is_admin_or_coach:
          own_player = db.query(Player).filter(
              Player.user_id == user.id, Player.archived_at.is_(None)
          ).first()
          if own_player:
              own_att = att_by_player.get(own_player.id)
              own_status = own_att.status if own_att else "unknown"
              own_note = own_att.note if own_att else ""
              status_label = t(f"telegram.status_{own_status}", locale)
              text += f"\n\n{t('telegram.your_status_label', locale)}: {status_label}"
              if own_note:
                  text += f"\n_{t('telegram.note_label', locale)}: {own_note}_"
              keyboard = event_status_keyboard(
                  event_id, own_player.id, back_page=back_page, locale=locale, note=own_note or ""
              )
          else:
              keyboard = InlineKeyboardMarkup([[
                  InlineKeyboardButton(t("telegram.back_button", locale), callback_data=back),
              ]])
      else:
          if event.team_id and event.season_id:
              pt_rows = (
                  db.query(PlayerTeam)
                  .filter(
                      PlayerTeam.team_id == event.team_id,
                      PlayerTeam.season_id == event.season_id,
                  )
                  .all()
              )
              player_ids = {pt.player_id: pt.position for pt in pt_rows}
              players = (
                  db.query(Player)
                  .filter(Player.id.in_(player_ids.keys()), Player.archived_at.is_(None))
                  .order_by(Player.first_name, Player.last_name)
                  .all()
              )
              for p in players:
                  p._position = player_ids.get(p.id)  # type: ignore[attr-defined]
          else:
              players = (
                  db.query(Player)
                  .filter(Player.archived_at.is_(None))
                  .order_by(Player.first_name, Player.last_name)
                  .all()
              )
              for p in players:
                  p._position = None  # type: ignore[attr-defined]

          from services.event_text_service import format_attendance_body  # noqa: PLC0415
          text += "\n" + format_attendance_body(
              players, att_by_player, ext_rows, locale, grouped=True, markdown=True
          )

          rows = [
              [InlineKeyboardButton(t("telegram.edit_attendance_button", locale), callback_data=f"evte:{event_id}:0:{back_page}")],
          ]
          rows.append([
              InlineKeyboardButton(t("telegram.notes_button", locale), callback_data=f"evtn:{event_id}:{back_page}"),
              InlineKeyboardButton(t("telegram.externals_button", locale), callback_data=f"evtx:{event_id}:{back_page}"),
          ])
          if msg_count > 0:
              rows.append([InlineKeyboardButton(
                  f"💬 Chat ({msg_count})", callback_data=f"ec:{event_id}",
              )])
          rows.append([InlineKeyboardButton(t("telegram.back_button", locale), callback_data=back)])
          keyboard = InlineKeyboardMarkup(rows)

      return text, keyboard


  def render_event_chat(user, db, event_id: int, back: str = "el") -> ViewResult:
      from models.event_message import EventMessage  # noqa: PLC0415

      locale = _locale(user)
      event = db.get(Event, event_id)
      if event is None:
          return t("telegram.no_events", locale), InlineKeyboardMarkup([[
              InlineKeyboardButton(t("telegram.back_button", locale), callback_data=back),
          ]])

      messages = (
          db.query(EventMessage)
          .filter(EventMessage.event_id == event_id)
          .order_by(EventMessage.created_at.asc())
          .limit(20)
          .all()
      )

      lines = [f"*💬 {event.title}*\n"]
      if not messages:
          lines.append("_No messages yet_")
      else:
          for msg in messages:
              author = msg.user.username if msg.user else "System"
              lane_icon = "📢" if msg.lane == "announcement" else "💬"
              ts = msg.created_at.strftime("%d %b %H:%M") if msg.created_at else ""
              lines.append(f"{lane_icon} *{author}* _{ts}_")
              lines.append(msg.body)
              lines.append("")

      text = "\n".join(lines)
      keyboard = InlineKeyboardMarkup([[
          InlineKeyboardButton(t("telegram.back_button", locale), callback_data=back),
      ]])
      return text, keyboard
  ```

- [x] **Step 3.2: Verify import**

  ```bash
  python3 -c "from bot.views.events import render_events_list, render_event_detail, render_event_chat; print('OK')"
  ```

- [x] **Step 3.3: Commit**

  ```bash
  git add bot/views/events.py
  git commit -m "feat: add events view renderers"
  ```

---

## Task 4: Create `bot/views/notifications.py`

**Files:**
- Create: `bot/views/notifications.py`

Adapted from `_show_notifications` (lines 615–734 in `handlers.py`).

- [x] **Step 4.1: Create `bot/views/notifications.py`**

  ```python
  """bot/views/notifications.py — Notification view renderers."""
  from __future__ import annotations

  import math

  from telegram import InlineKeyboardButton, InlineKeyboardMarkup
  from telegram.constants import ParseMode

  from app.i18n import t
  from bot.views import ViewResult
  from models.player import Player

  NOTIF_PAGE_SIZE = 5


  def render_notifications_list(user, db, page: int = 0) -> ViewResult:
      from models.notification import Notification  # noqa: PLC0415
      from models.telegram_notification import TelegramNotification  # noqa: PLC0415

      locale = user.locale or "en"
      is_admin_or_coach = user.is_admin or user.is_coach

      if is_admin_or_coach:
          notifs = (
              db.query(TelegramNotification)
              .filter(TelegramNotification.user_id == user.id)
              .order_by(TelegramNotification.created_at.desc())
              .all()
          )
          if not notifs:
              keyboard = InlineKeyboardMarkup([[
                  InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home"),
              ]])
              return t("telegram.no_events", locale), keyboard

          total_pages = max(1, math.ceil(len(notifs) / NOTIF_PAGE_SIZE))
          page = max(0, min(page, total_pages - 1))
          page_notifs = notifs[page * NOTIF_PAGE_SIZE : (page + 1) * NOTIF_PAGE_SIZE]

          text_lines = ["🔔 Recent Notifications:"]
          rows = []
          for notif in page_notifs:
              player_name = notif.player.full_name if notif.player else f"Player {notif.player_id}"
              event_title = notif.event.title if notif.event else "Event"
              icon = {"present": "✓", "absent": "✗", "unknown": "?"}.get(notif.status, "?")
              text_lines.append(f"{icon} {player_name} → {notif.status}")
              rows.append([InlineKeyboardButton(
                  f"👁 {event_title}",
                  callback_data=f"n:{notif.id}",
              )])
      else:
          linked_player = db.query(Player).filter(
              Player.user_id == user.id, Player.archived_at.is_(None)
          ).first()
          if linked_player is None:
              keyboard = InlineKeyboardMarkup([[
                  InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home"),
              ]])
              return t("telegram.no_events", locale), keyboard

          notifs = (
              db.query(Notification)
              .filter(Notification.player_id == linked_player.id)
              .order_by(Notification.created_at.desc())
              .all()
          )
          if not notifs:
              keyboard = InlineKeyboardMarkup([[
                  InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home"),
              ]])
              return t("telegram.no_events", locale), keyboard

          # Mark all as read
          db.query(Notification).filter(
              Notification.player_id == linked_player.id,
              Notification.is_read.is_(False),
          ).update({"is_read": True})
          db.commit()

          total_pages = max(1, math.ceil(len(notifs) / NOTIF_PAGE_SIZE))
          page = max(0, min(page, total_pages - 1))
          page_notifs = notifs[page * NOTIF_PAGE_SIZE : (page + 1) * NOTIF_PAGE_SIZE]

          text_lines = ["🔔 Notifications:"]
          rows = []
          for notif in page_notifs:
              event = notif.event
              event_date = str(event.event_date) if event else ""
              header = f"*{notif.title}*"
              if event_date:
                  header += f" ({event_date})"
              text_lines.append(header)
              text_lines.append(notif.body)
              if event:
                  rows.append([InlineKeyboardButton(
                      f"👁 {event.title}",
                      callback_data=f"e:{notif.event_id}",
                  )])

      nav = []
      if page > 0:
          nav.append(InlineKeyboardButton("← Prev", callback_data=f"nl:{page - 1}"))
      if page < total_pages - 1:
          nav.append(InlineKeyboardButton("Next →", callback_data=f"nl:{page + 1}"))
      if nav:
          rows.append(nav)
      rows.append([InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home")])

      return "\n".join(text_lines), InlineKeyboardMarkup(rows)


  def render_notification_detail(user, db, notif_id: int) -> ViewResult:
      """Show a single TelegramNotification with link to its event."""
      from models.telegram_notification import TelegramNotification  # noqa: PLC0415

      locale = user.locale or "en"
      notif = db.get(TelegramNotification, notif_id)
      if notif is None or notif.user_id != user.id:
          keyboard = InlineKeyboardMarkup([[
              InlineKeyboardButton(t("telegram.back_button", locale), callback_data="nl"),
          ]])
          return "Notification not found.", keyboard

      player_name = notif.player.full_name if notif.player else f"Player {notif.player_id}"
      event = notif.event
      event_title = event.title if event else "Event"
      event_date = str(event.event_date) if event else ""
      icon = {"present": "✓", "absent": "✗", "unknown": "?"}.get(notif.status, "?")
      ts = notif.created_at.strftime("%d %b %H:%M") if notif.created_at else ""

      text = f"📬 *{player_name}* {icon} → {notif.status}\n*{event_title}*"
      if event_date:
          text += f"\n{event_date}"
      if ts:
          text += f"\n_{ts}_"

      rows = []
      if event:
          rows.append([InlineKeyboardButton(f"📅 {event_title}", callback_data=f"e:{notif.event_id}")])
      rows.append([InlineKeyboardButton(t("telegram.back_button", locale), callback_data="nl")])

      return text, InlineKeyboardMarkup(rows)
  ```

- [x] **Step 4.2: Verify import**

  ```bash
  python3 -c "from bot.views.notifications import render_notifications_list, render_notification_detail; print('OK')"
  ```

- [x] **Step 4.3: Commit**

  ```bash
  git add bot/views/notifications.py
  git commit -m "feat: add notifications view renderers"
  ```

---

## Task 5: Create `bot/views/other.py`

**Files:**
- Create: `bot/views/other.py`

- [x] **Step 5.1: Create `bot/views/other.py`**

  ```python
  """bot/views/other.py — 'Other' menu view renderer."""
  from __future__ import annotations

  from telegram import InlineKeyboardButton, InlineKeyboardMarkup

  from app.i18n import t
  from bot.views import ViewResult


  def render_other(user, locale: str = "en") -> ViewResult:
      """Other mini-menu: entry point to absences + back home."""
      text = t("telegram.other_button", locale)
      keyboard = InlineKeyboardMarkup([
          [InlineKeyboardButton(t("telegram.absences_button", locale), callback_data="ab")],
          [InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home")],
      ])
      return text, keyboard
  ```

- [x] **Step 5.2: Verify import**

  ```bash
  python3 -c "from bot.views.other import render_other; print('OK')"
  ```

- [x] **Step 5.3: Commit**

  ```bash
  git add bot/views/other.py
  git commit -m "feat: add other view renderer"
  ```

---

## Task 6: Create `bot/navigation.py`

**Files:**
- Create: `bot/navigation.py`

- [x] **Step 6.1: Create `bot/navigation.py`**

  ```python
  """bot/navigation.py — Persistent message navigation and notification injection."""
  from __future__ import annotations

  import logging

  from telegram import InlineKeyboardButton, InlineKeyboardMarkup
  from telegram.constants import ParseMode

  logger = logging.getLogger(__name__)


  async def navigate(query, user, db, view_key: str, text: str, keyboard: InlineKeyboardMarkup) -> None:
      """Edit the persistent message to show a new view and update the view state."""
      try:
          await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
      except Exception:
          await query.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
      user.telegram_current_view = view_key
      db.commit()


  async def inject_notification(user, notif_id: int, bot, db) -> None:
      """Inject a 🔔 button into the current view when a new notification arrives.

      If user has no persistent message yet, sends the homepage as the first message.
      """
      if not user.telegram_chat_id:
          return

      if user.telegram_notification_message_id is None:
          # No persistent message yet — send homepage first
          from bot.views.home import render_home  # noqa: PLC0415
          text, keyboard = render_home(user, db)
          try:
              msg = await bot.send_message(
                  chat_id=user.telegram_chat_id,
                  text=text,
                  reply_markup=keyboard,
                  parse_mode=ParseMode.MARKDOWN,
              )
              user.telegram_notification_message_id = msg.message_id
              user.telegram_current_view = "home"
              db.commit()
          except Exception as exc:
              logger.warning("inject_notification: failed to send homepage for user %s: %s", user.id, exc)
              return

      # Re-render current view with 🔔 button injected
      text, keyboard = _rerender_current_view(user, db, notif_id)
      try:
          await bot.edit_message_text(
              chat_id=user.telegram_chat_id,
              message_id=user.telegram_notification_message_id,
              text=text,
              reply_markup=keyboard,
              parse_mode=ParseMode.MARKDOWN,
          )
      except Exception as exc:
          logger.warning("inject_notification: failed to edit message for user %s: %s", user.id, exc)


  def _rerender_current_view(user, db, notif_id: int) -> tuple[str, InlineKeyboardMarkup]:
      """Re-render the current view and prepend a 🔔 notification button."""
      view_key = user.telegram_current_view or "home"
      text, keyboard = _render_view(user, db, view_key)

      # Build preview for notification button
      preview = _notif_preview(user, db, notif_id)
      notif_row = [InlineKeyboardButton(f"🔔 {preview}", callback_data=f"n:{notif_id}")]

      new_rows = [notif_row] + list(keyboard.inline_keyboard)
      new_keyboard = InlineKeyboardMarkup(new_rows)
      return text, new_keyboard


  def _render_view(user, db, view_key: str) -> tuple[str, InlineKeyboardMarkup]:
      """Dispatch view key string to the appropriate renderer."""
      from bot.views.home import render_home  # noqa: PLC0415
      from bot.views.events import render_events_list, render_event_detail, render_event_chat  # noqa: PLC0415
      from bot.views.notifications import render_notifications_list, render_notification_detail  # noqa: PLC0415
      from bot.views.other import render_other  # noqa: PLC0415

      locale = user.locale or "en"

      if view_key == "home":
          return render_home(user, db)
      if view_key == "nl":
          return render_notifications_list(user, db, 0)
      if view_key.startswith("nl:"):
          page = int(view_key.split(":")[1])
          return render_notifications_list(user, db, page)
      if view_key.startswith("n:"):
          return render_notification_detail(user, db, int(view_key.split(":")[1]))
      if view_key == "el":
          return render_events_list(user, db, 0)
      if view_key.startswith("el:"):
          page = int(view_key.split(":")[1])
          return render_events_list(user, db, page)
      if view_key.startswith("e:"):
          return render_event_detail(user, db, int(view_key.split(":")[1]))
      if view_key.startswith("ec:"):
          return render_event_chat(user, db, int(view_key.split(":")[1]))
      if view_key in ("ab", "other"):
          return render_other(user, locale)
      # Fallback
      return render_home(user, db)


  def _notif_preview(user, db, notif_id: int) -> str:
      """Short text for the 🔔 button label (max ~30 chars)."""
      from models.telegram_notification import TelegramNotification  # noqa: PLC0415

      notif = db.get(TelegramNotification, notif_id)
      if notif is None:
          return "New notification"
      player_name = notif.player.full_name if notif.player else "Player"
      icon = {"present": "✓", "absent": "✗", "unknown": "?"}.get(notif.status, "?")
      preview = f"{player_name} {icon}"
      return preview[:30]
  ```

- [x] **Step 6.2: Verify import**

  ```bash
  python3 -c "from bot.navigation import navigate, inject_notification; print('OK')"
  ```

- [x] **Step 6.3: Commit**

  ```bash
  git add bot/navigation.py
  git commit -m "feat: add navigation module with inject_notification"
  ```

---

## Task 7: Update `bot/keyboards.py` and `bot/absence_keyboards.py`

**Files:**
- Modify: `bot/keyboards.py`
- Modify: `bot/absence_keyboards.py`

- [x] **Step 7.1: Update `events_keyboard` to use new callback scheme**

  In `bot/keyboards.py`, find `events_keyboard()` and make these changes:

  1. Change `callback_data=f"evt:{event.id}"` → `callback_data=f"e:{event.id}"`
  2. Change `callback_data=f"evts:{page - 1}"` → `callback_data=f"el:{page - 1}"`
  3. Change `callback_data=f"ref:{page}"` → `callback_data=f"el:{page}"` (refresh = reload current page)
  4. Change `callback_data=f"evts:{page + 1}"` → `callback_data=f"el:{page + 1}"`
  5. Change `callback_data=f"other:{page}"` → `callback_data="other:0"` (keep other menu working)

  Full updated function:

  ```python
  def events_keyboard(events: list[Event], page: int, total_pages: int, locale: str = "en") -> InlineKeyboardMarkup:
      """One row per event with a View button, plus Prev/Next/Refresh navigation."""
      rows = []
      for event in events:
          time_val = event.meeting_time or event.event_time
          time_str = f" {str(time_val)[:5]}" if time_val else ""
          label = f"{event.event_date}{time_str} — {event.title}"
          rows.append([InlineKeyboardButton(label, callback_data=f"e:{event.id}")])

      nav = []
      if page > 0:
          nav.append(InlineKeyboardButton(t("telegram.prev_button", locale), callback_data=f"el:{page - 1}"))
      nav.append(InlineKeyboardButton(t("telegram.refresh_button", locale), callback_data=f"el:{page}"))
      if page < total_pages - 1:
          nav.append(InlineKeyboardButton(t("telegram.view_more_button", locale), callback_data=f"el:{page + 1}"))
      rows.append(nav)
      rows.append([InlineKeyboardButton(t("telegram.other_button", locale), callback_data="other:0")])

      return InlineKeyboardMarkup(rows)
  ```

- [x] **Step 7.2: Update `event_view_keyboard` back button**

  Change `callback_data=f"evts:{back_page}"` → `callback_data=f"el:{back_page}"` in `event_view_keyboard`. This ensures the back button from event detail always routes to the events list renderer.

  ```python
  def event_view_keyboard(event_id: int, back_page: int = 0, locale: str = "en", is_privileged: bool = False) -> InlineKeyboardMarkup:
      rows = [
          [InlineKeyboardButton(t("telegram.edit_attendance_button", locale), callback_data=f"evte:{event_id}:0:{back_page}")],
      ]
      if is_privileged:
          rows.append([
              InlineKeyboardButton(t("telegram.notes_button", locale), callback_data=f"evtn:{event_id}:{back_page}"),
              InlineKeyboardButton(t("telegram.externals_button", locale), callback_data=f"evtx:{event_id}:{back_page}"),
          ])
      rows.append([InlineKeyboardButton(t("telegram.back_button", locale), callback_data=f"el:{back_page}")])
      return InlineKeyboardMarkup(rows)
  ```

- [x] **Step 7.3: Update `event_status_keyboard` back button**

  Change `callback_data=f"evts:{back_page}"` → `callback_data=f"el:{back_page}"` in `event_status_keyboard`:

  ```python
  rows = [
      [...],
      [InlineKeyboardButton(note_label, callback_data=f"note:{event_id}:{player_id}:{back_page}")],
      [InlineKeyboardButton(t("telegram.back_button", locale), callback_data=f"el:{back_page}")],
  ]
  ```

- [x] **Step 7.4: Update `other_menu_keyboard` back button**

  In `bot/absence_keyboards.py`, change:

  ```python
  def other_menu_keyboard(back_page: int, locale: str = "en") -> InlineKeyboardMarkup:
      return InlineKeyboardMarkup([
          [InlineKeyboardButton(t("telegram.absences_button", locale), callback_data=f"absm:{back_page}")],
          [InlineKeyboardButton(t("telegram.back_button", locale), callback_data="home")],
      ])
  ```

- [x] **Step 7.5: Update `absence_player_list_keyboard` back button**

  In `bot/absence_keyboards.py`, find `absence_player_list_keyboard` and change:

  `callback_data=f"other:{back_page}"` → `callback_data="other:0"`

- [x] **Step 7.6: Update `absence_list_keyboard` back buttons**

  In `bot/absence_keyboards.py`, find `absence_list_keyboard` and change:

  `callback_data=f"other:{back_page}"` → `callback_data="other:0"` (for member back)
  `callback_data=f"absm:{back_page}"` → `callback_data=f"absm:{back_page}"` (keep for coach back — already correct)

- [x] **Step 7.7: Check i18n keys exist**

  ```bash
  python3 -c "
  import yaml
  en = yaml.safe_load(open('locales/en.yaml'))
  tg = en.get('telegram', {})
  needed = ['notifications_button', 'events_button', 'absences_button']
  for k in needed:
      print(k, ':', tg.get(k, 'MISSING'))
  "
  ```

  If any key is `MISSING`, add it to all 4 locale JSON files (`locales/en.json`, `locales/it.json`, `locales/fr.json`, `locales/de.json`). Under the `"telegram"` key, add:

  ```json
  "notifications_button": "🔔 Notifications",
  "events_button": "📅 Events"
  ```

  Translate for `it` (Notifiche / Allenamenti), `fr` (Notifications / Événements), `de` (Benachrichtigungen / Termine).

  After adding keys, verify home.py imports cleanly: `python3 -c "from bot.views.home import render_home; print('OK')"`

- [x] **Step 7.8: Verify keyboards import cleanly**

  ```bash
  python3 -c "from bot.keyboards import events_keyboard, event_view_keyboard; print('OK')"
  python3 -c "from bot.absence_keyboards import other_menu_keyboard; print('OK')"
  ```

- [x] **Step 7.9: Commit**

  ```bash
  git add bot/keyboards.py bot/absence_keyboards.py locales/
  git commit -m "feat: update keyboard callbacks to new navigation scheme"
  ```

---

## Task 8: Update `bot/handlers.py`

**Files:**
- Modify: `bot/handlers.py`

This is the largest change. Key goals:
1. Replace `_send_events_list` with `_send_homepage` (sends or edits persistent message)
2. Add routing for new callbacks: `home`, `el`, `el:N`, `e:ID`, `ec:ID`, `nl`, `nl:N`, `n:ID`, `ab`
3. Remove `handle_nav_dispatch` and `handle_menu`
4. Update auth handlers to use homepage

- [x] **Step 8.1: Add `_send_homepage` helper, remove `_send_events_list`**

  At the top of `handlers.py`, remove the entire `_send_events_list` async function (lines 93–167).

  Replace with:

  ```python
  async def _send_homepage(message_or_bot, user, db, *, bot=None) -> None:
      """Send or replace the persistent message with the homepage view."""
      from bot.views.home import render_home  # noqa: PLC0415

      text, keyboard = render_home(user, db)

      # Delete old persistent message if exists
      if user.telegram_notification_message_id:
          try:
              _bot = bot or message_or_bot.get_bot()
              await _bot.delete_message(
                  chat_id=user.telegram_chat_id,
                  message_id=user.telegram_notification_message_id,
              )
          except Exception:
              pass
          user.telegram_notification_message_id = None

      # Send new persistent message
      msg = await message_or_bot.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
      user.telegram_notification_message_id = msg.message_id
      user.telegram_current_view = "home"
      db.commit()
  ```

- [x] **Step 8.2: Update `handle_start` to use `_send_homepage`**

  Replace the `await _send_events_list(...)` call in `handle_start`:

  ```python
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
              await _send_homepage(update.message, user, db)
              return

      await update.message.reply_text(
          t("telegram.welcome", "en"),
          reply_markup=_phone_request_keyboard(),
      )
  ```

- [x] **Step 8.3: Update `handle_refresh` to use `_send_homepage`**

  ```python
  async def handle_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
      chat_id = str(update.effective_chat.id)
      with SessionLocal() as db:
          user = get_user_by_chat_id(db, chat_id)
          if user is None:
              await update.message.reply_text(t("telegram.not_authenticated", "en"))
              return
          await _send_homepage(update.message, user, db)
  ```

- [x] **Step 8.4: Update `handle_contact` auth success to use `_send_homepage` and remove reply keyboard**

  In `handle_contact`, find the auth success block (around line 315):

  ```python
  if result in (AuthResult.SUCCESS, AuthResult.ALREADY_THIS):
      with SessionLocal() as db:
          await _send_homepage(update.message, user, db)
  ```

  Remove the `await update.message.reply_text("✓", reply_markup=main_menu_keyboard())` line.

- [x] **Step 8.5: Add new callback routing to `handle_callback`**

  In `handle_callback`, after the `"noop"` and `"restart:"` blocks, add new routing blocks before the existing `notif:` block:

  ```python
  if data == "home":
      await query.answer()
      from bot.views.home import render_home  # noqa: PLC0415
      from bot.navigation import navigate  # noqa: PLC0415
      text, keyboard = render_home(user, db)
      await navigate(query, user, db, "home", text, keyboard)
      return

  if data == "nl" or data.startswith("nl:"):
      await query.answer()
      from bot.views.notifications import render_notifications_list  # noqa: PLC0415
      from bot.navigation import navigate  # noqa: PLC0415
      page = int(data.split(":")[1]) if ":" in data else 0
      text, keyboard = render_notifications_list(user, db, page)
      view_key = f"nl:{page}" if page > 0 else "nl"
      await navigate(query, user, db, view_key, text, keyboard)
      return

  if data.startswith("n:"):
      await query.answer()
      from bot.views.notifications import render_notification_detail  # noqa: PLC0415
      from bot.navigation import navigate  # noqa: PLC0415
      notif_id = int(data.split(":")[1])
      text, keyboard = render_notification_detail(user, db, notif_id)
      await navigate(query, user, db, f"n:{notif_id}", text, keyboard)
      return

  if data == "el" or data.startswith("el:"):
      await query.answer()
      from bot.views.events import render_events_list  # noqa: PLC0415
      from bot.navigation import navigate  # noqa: PLC0415
      page = int(data.split(":")[1]) if ":" in data else 0
      text, keyboard = render_events_list(user, db, page)
      view_key = f"el:{page}" if page > 0 else "el"
      await navigate(query, user, db, view_key, text, keyboard)
      return

  if data.startswith("e:"):
      await query.answer()
      from bot.views.events import render_event_detail  # noqa: PLC0415
      from bot.navigation import navigate  # noqa: PLC0415
      event_id = int(data.split(":")[1])
      text, keyboard = render_event_detail(user, db, event_id)
      await navigate(query, user, db, f"e:{event_id}", text, keyboard)
      return

  if data.startswith("ec:"):
      await query.answer()
      from bot.views.events import render_event_chat  # noqa: PLC0415
      from bot.navigation import navigate  # noqa: PLC0415
      event_id = int(data.split(":")[1])
      text, keyboard = render_event_chat(user, db, event_id, back=f"e:{event_id}")
      await navigate(query, user, db, f"ec:{event_id}", text, keyboard)
      return

  if data == "ab":
      await query.answer()
      from bot.absence_handlers import show_absence_root  # noqa: PLC0415
      await show_absence_root(query, user, db, back_page=0)
      user.telegram_current_view = "ab"
      db.commit()
      return
  ```

  > **Important:** `data.startswith("e:")` does NOT match `"evts:"`, `"evt:"`, `"evte:"`, `"ext:"` etc. — the second character differs (`e:v...` vs `e:`). Place the new `e:` block AFTER all `evts:`, `evt:`, `evte:`, `evtp:`, `evtn:`, `evtx:`, `ext*:` blocks to avoid any ambiguity.

- [x] **Step 8.6: Keep existing `notif:` routing as alias**

  The existing `notif:` block can stay as-is — it routes to `_show_notifications` which still works fine on the persistent message. Or replace it to use the new renderer:

  ```python
  if data.startswith("notif:"):
      await query.answer()
      from bot.views.notifications import render_notifications_list  # noqa: PLC0415
      from bot.navigation import navigate  # noqa: PLC0415
      page = max(0, int(data.split(":")[1]))
      text, keyboard = render_notifications_list(user, db, page)
      await navigate(query, user, db, f"nl:{page}" if page > 0 else "nl", text, keyboard)
      return
  ```

- [x] **Step 8.7: Remove `handle_nav_dispatch` and `handle_menu` functions**

  Delete the entire `handle_nav_dispatch` function (lines 247–270) and `handle_menu` function (lines 239–245). These are no longer used.

- [x] **Step 8.8: Remove unused imports**

  Remove from top of `handlers.py`:
  - `KeyboardButton`
  - `ReplyKeyboardMarkup` (if no longer used elsewhere)
  - `NAV_ABSENCES`, `NAV_EVENTS`, `NAV_REFRESH` from keyboards import
  - `main_menu_keyboard` from keyboards import

  Keep `ReplyKeyboardRemove` — still used in auth flow.

- [x] **Step 8.9: Run tests**

  ```bash
  cd /home/denny/Development/promanager && source .venv/bin/activate && pytest -v 2>&1 | tail -40
  ```

  Fix any import errors or test failures before committing.

- [x] **Step 8.10: Commit**

  ```bash
  git add bot/handlers.py
  git commit -m "feat: replace _send_events_list with homepage, add new callback routing"
  ```

---

## Task 9: Update `bot/__init__.py`

**Files:**
- Modify: `bot/__init__.py`

- [x] **Step 9.1: Remove `handle_nav_dispatch` and `handle_menu` registrations**

  In `bot/__init__.py`, update `build_application`:

  ```python
  def build_application(token: str) -> Application:
      from bot.handlers import (  # noqa: PLC0415
          handle_callback,
          handle_cancel,
          handle_contact,
          handle_logout,
          handle_refresh,
          handle_start,
          handle_text,
      )

      app = Application.builder().token(token).build()
      app.add_handler(CommandHandler("start", handle_start))
      app.add_handler(CommandHandler("logout", handle_logout))
      app.add_handler(CommandHandler("refresh", handle_refresh))
      app.add_handler(CommandHandler("cancel", handle_cancel))
      app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
      app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
      app.add_handler(CallbackQueryHandler(handle_callback))
      return app
  ```

  Remove the `handle_menu`, `handle_nav_dispatch` imports, the `NAV_*` imports, and the nav regex handler.

- [x] **Step 9.2: Remove unused imports from `bot/__init__.py`**

  Remove: `KeyboardButton`, `ReplyKeyboardMarkup` if they were imported. Remove: `filters.Regex` MessageHandler block.

- [x] **Step 9.3: Verify**

  ```bash
  python3 -c "from bot import build_application; print('OK')"
  ```

- [x] **Step 9.4: Commit**

  ```bash
  git add bot/__init__.py
  git commit -m "feat: remove reply keyboard handlers from bot registration"
  ```

---

## Task 10: Update `services/telegram_notifications.py`

**Files:**
- Modify: `services/telegram_notifications.py`

Replace the delete-and-resend pattern with `inject_notification`.

- [x] **Step 10.1: Rewrite `notify_coaches_via_telegram`**

  Replace the entire function body with:

  ```python
  async def notify_coaches_via_telegram(
      event_id: int,
      player_id: int,
      new_status: str,
  ) -> None:
      """Send Telegram alert to coaches/admins about attendance change."""
      import bot as _bot  # noqa: PLC0415

      if _bot.telegram_app is None:
          return

      import app.database as _db_mod  # noqa: PLC0415
      from bot.navigation import inject_notification  # noqa: PLC0415
      from models.event import Event  # noqa: PLC0415
      from models.notification_preference import NotificationPreference  # noqa: PLC0415
      from models.player import Player  # noqa: PLC0415
      from models.telegram_notification import TelegramNotification  # noqa: PLC0415
      from models.user_team import UserTeam  # noqa: PLC0415

      db = _db_mod.SessionLocal()
      try:
          event = db.get(Event, event_id)
          if event is None:
              return
          player = db.get(Player, player_id)
          if player is None:
              return

          coaches = db.query(UserTeam).filter(UserTeam.team_id == event.team_id).all()
          seen_chat_ids: set[str] = set()

          for ut in coaches:
              if not (ut.user and ut.user.telegram_chat_id):
                  continue
              if ut.user.telegram_chat_id in seen_chat_ids:
                  continue
              seen_chat_ids.add(ut.user.telegram_chat_id)

              # Respect notification preference
              coach_player = ut.user.players[0] if ut.user.players else None
              if coach_player is not None:
                  pref = (
                      db.query(NotificationPreference)
                      .filter(
                          NotificationPreference.player_id == coach_player.id,
                          NotificationPreference.channel == "telegram",
                      )
                      .first()
                  )
                  if pref is not None and not pref.enabled:
                      continue

              try:
                  # Create notification record
                  notif = TelegramNotification(
                      user_id=ut.user_id,
                      event_id=event_id,
                      player_id=player_id,
                      status=new_status,
                  )
                  db.add(notif)
                  db.flush()  # get notif.id before inject_notification

                  # Inject 🔔 button into persistent message (or send homepage if first time)
                  await inject_notification(ut.user, notif.id, _bot.telegram_app.bot, db)

              except Exception as exc:
                  logger.warning(
                      "notify_coaches_via_telegram: failed for user %s: %s",
                      ut.user_id, exc, exc_info=True,
                  )

          db.commit()
      finally:
          db.close()
  ```

- [x] **Step 10.2: Run tests**

  ```bash
  pytest -v 2>&1 | tail -40
  ```

- [x] **Step 10.3: Commit**

  ```bash
  git add services/telegram_notifications.py
  git commit -m "feat: replace delete+resend with inject_notification for coach alerts"
  ```

---

## Task 11: Push and deploy

- [x] **Step 11.1: Run full test suite**

  ```bash
  cd /home/denny/Development/promanager && source .venv/bin/activate
  pytest -v 2>&1 | tail -60
  ruff check .
  ```

  All tests must pass before deploying.

- [x] **Step 11.2: Push to GitHub**

  ```bash
  git push
  ```

- [x] **Step 11.3: Deploy to Docker**

  ```bash
  cd ~/dockerimages && ./updateDocker.sh proManager
  ```

- [x] **Step 11.4: Verify logs clean**

  ```bash
  cd ~/dockerimages/proManager && docker compose logs --tail=30
  ```

  Expected: no import errors, bot initialises cleanly.

---

## Verification

1. `/start` → homepage renders with last notification + 4 buttons (Notifications, Events, Absences, Other)
2. Tap Events → message edits to events list; back button returns to homepage
3. Tap an event → event detail; coaches see Edit Attendance + Notes + Externals + Chat button (if messages exist)
4. Tap Chat → read-only messages shown; back returns to event detail
5. Tap Notifications → notifications list; tap a notification → notification detail; tap event link → event detail
6. Tap Absences → absence flow; back returns home
7. Trigger attendance change → coach's persistent message gets 🔔 button injected (does not navigate away from current view)
8. Tap 🔔 button → notification detail
9. `/refresh` → sends fresh homepage (replaces persistent message)
10. `pytest -v` passes
