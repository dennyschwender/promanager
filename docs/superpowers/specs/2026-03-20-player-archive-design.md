# Player Archive Design

**Date:** 2026-03-20
**Status:** Approved

## Overview

Replace the hard-delete player action with a soft-delete (archive) mechanism. Archived players are hidden from day-to-day views but their data (attendance history, team memberships) is preserved. Add bulk archive, unarchive, activate, and deactivate actions to the players list bulk toolbar.

---

## Data Model

Add one column to `models/player.py`:

```python
archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, default=None)
```

- `archived_at IS NULL` → normal player (active or inactive)
- `archived_at IS NOT NULL` → archived, hidden from default views

The existing `is_active` field is untouched — it retains its meaning of "temporarily benched / inactive".

Use `datetime.now(timezone.utc)` (not the deprecated `datetime.utcnow()`) when setting `archived_at`, consistent with all other timestamp columns in the project.

**Migration:** `alembic revision --autogenerate -m "add_archived_at_to_player"`. No change needed to `models/__init__.py` — `Player` is already imported there, so Alembic's autogenerate will pick up the new column automatically.

---

## Backend

### Filter changes

`GET /players` default query adds `WHERE archived_at IS NULL`.

New `archived` query param controls visibility:

| `?archived=` | Behaviour |
|---|---|
| omitted (default) | `WHERE archived_at IS NULL` |
| `only` | `WHERE archived_at IS NOT NULL` |
| `all` | no filter on `archived_at` |

Invalid values for `?archived=` (anything other than omitted, `only`, or `all`) are treated as the default (active only), silently — consistent with how `team_id` and `season_id` handle bad values.

### Archive filter scope across the codebase

Only `GET /players` gains the `archived` filter. Other query sites have deliberate policies:

- **`services/notification_service.py`** — must exclude archived players. Sending reminders to archived players is a data-quality bug. Add `WHERE archived_at IS NULL` here.
- **`routes/attendance.py`** — must exclude archived players from attendance auto-creation and queries.
- **`services/import_service.py`** (email deduplication check) — must **include** archived players in the duplicate check to avoid creating a new record for someone who was archived.
- **`routes/users.py`** (bulk-create user flow) — exclude archived players; they should not receive user account creation emails.
- **`routes/notifications.py`** — exclude archived players from notification dispatch.

### Single-player endpoints

- `POST /players/{id}/delete` → **renamed** `POST /players/{id}/archive`
  - Sets `archived_at = datetime.now(timezone.utc)`, redirects to `/players`
- New `POST /players/{id}/unarchive`
  - Sets `archived_at = None`, redirects to `/players` (the default active view, so the restored player is immediately visible)

Both are admin-only with CSRF.

### Bulk endpoints (all admin-only, require CSRF header)

**`POST /players/bulk-activate`**
```
Body:    { player_ids: [int] }
Returns: { activated: int, skipped: int, errors: [...] }
```
Sets `is_active = True`. Skips already-active players and players with `archived_at IS NOT NULL` (archived players cannot be activated via this endpoint).

**`POST /players/bulk-deactivate`**
```
Body:    { player_ids: [int] }
Returns: { deactivated: int, skipped: int, errors: [...] }
```
Sets `is_active = False`. Skips already-inactive players and players with `archived_at IS NOT NULL`.

**`POST /players/bulk-archive`**
```
Body:    { player_ids: [int] }
Returns: { archived: int, skipped: int, errors: [...] }
```
Sets `archived_at = datetime.now(timezone.utc)`. Skips already-archived players.

**`POST /players/bulk-unarchive`**
```
Body:    { player_ids: [int] }
Returns: { unarchived: int, skipped: int, errors: [...] }
```
Sets `archived_at = None`. Skips non-archived players.

All four follow the savepoint pattern of existing bulk endpoints (`bulk-assign`, `bulk-remove`).

---

## UI

### Filter bar

Add an **Archived** select alongside the existing Season and Team filters:

```
[ Season ▾ ]  [ Team ▾ ]  [ Archived: Active only ▾ ]  [ Columns ▾ ] [ Filter ▾ ] [ Edit ]
```

Options: **Active only** (default) / **Archived only** / **All**.

### Bulk toolbar

Context-aware — buttons shown/hidden based on the state of selected players. Each `<tr>` carries `data-is-active` and `data-archived-at` attributes read by JS.

| Button | Shown when |
|---|---|
| Assign to team | always |
| Remove from team | always |
| Activate | ≥1 selected player has `is_active=false` and `archived_at=null` |
| Deactivate | ≥1 selected player has `is_active=true` and `archived_at=null` |
| Archive | ≥1 selected player has `archived_at=null` |
| Unarchive | ≥1 selected player has `archived_at` set |

Archive and Unarchive are danger-styled (red border/text), matching the existing "Remove from team" style.

**Confirmation dialog** (Archive bulk action): lists each selected player's full name and date of birth before confirming.

### Per-row Actions dropdown

Replace the current "Delete" entry with:
- **Activate** / **Deactivate** — toggled based on `is_active` state
- **Archive** — shown when `archived_at` is null; opens a confirmation dialog with the player's name and DOB
- **Unarchive** — shown when `archived_at` is set

---

## Testing

New file: `tests/test_players_bulk_archive.py`

- `test_bulk_archive_sets_archived_at`
- `test_bulk_unarchive_clears_archived_at`
- `test_bulk_activate`
- `test_bulk_deactivate`
- `test_bulk_archive_skips_already_archived`
- `test_bulk_activate_skips_archived_players`
- `test_bulk_deactivate_skips_archived_players`
- `test_archived_filter_hides_archived_by_default`
- `test_archived_filter_only`
- `test_archived_filter_all`
- `test_single_player_archive`
- `test_single_player_unarchive`
- `test_member_cannot_archive`
- `test_member_cannot_unarchive`

**Update existing tests:** any test referencing `POST /players/{id}/delete` → update to `POST /players/{id}/archive`.
