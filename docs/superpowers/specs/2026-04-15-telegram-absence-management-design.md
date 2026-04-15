# Telegram Absence Management Design

**Date:** 2026-04-15

## Context

Players and coaches currently manage absences only through the ProManager web interface. This spec adds absence management (period absences only — date range + optional reason) to the Telegram bot, accessible via a new "⚙️ Other" section from the events list. Players can manage their own absences; coaches and admins can manage absences for any player on their team(s). Recurring absences remain web-only due to the complexity of weekday selection.

## Scope

- **Operations:** create (period absence) + list + delete
- **Absence types:** period only (start_date, end_date, optional reason); recurring stays web-only
- **Users:** players (own absences), coaches/admins (any player on their team)
- **Entry point:** new "⚙️ Other" button on the events list keyboard

## Navigation Flow

```
Events list
  └─ [⚙️ Other]  →  other:{events_page}
        └─ [📅 Absences]  →  absm:{events_page}
              ├─ Member path: own absence list  →  absl:{player_id}:0:{events_page}
              └─ Coach/Admin path: paginated player list
                    └─ select player  →  absl:{player_id}:0:{events_page}

absl:{player_id}:{page}:{back_page}
  ├─ [🗑 {absence}] per row  →  absd:{absence_id}:{player_id}:{page}:{back_page}
  │     └─ confirm delete  →  absdc:{absence_id}:{player_id}:{page}:{back_page}
  ├─ [+ Add absence]  →  absa:{player_id}:{back_page}
  │     └─ multi-step text input (start_date → end_date → reason)
  │           └─ create + apply_absence_to_future_events → back to absl
  └─ [← Back]  →  absm:{back_page}  (coach/admin — returns to player list)
                  other:{back_page}  (member — returns to Other menu, since absm skips player list)
```

## Callback Data Prefixes

| Prefix | Format | Meaning |
|--------|--------|---------|
| `other:` | `other:{page}` | Show "Other" menu |
| `absm:` | `absm:{back_page}` | Absence root (player list or own list) |
| `absl:` | `absl:{player_id}:{page}:{back_page}` | Absence list for a player |
| `absa:` | `absa:{player_id}:{back_page}` | Start add absence flow |
| `absd:` | `absd:{absence_id}:{player_id}:{page}:{back_page}` | Delete confirmation |
| `absdc:` | `absdc:{absence_id}:{player_id}:{page}:{back_page}` | Confirm delete |

## Multi-Step Add Absence Flow

State stored in `context.user_data["awaiting_absence"]`:

```python
{
    "player_id": int,
    "back_page": int,         # events list page for final Back button
    "step": "start" | "end" | "reason",
    "start_date": date | None,  # populated after step 1
    "end_date": date | None,    # populated after step 2
    "prompt_message_id": int,
    "chat_id": str | int,
}
```

**Steps:**
1. `absa:` callback → set `step="start"` → send prompt: `"Enter start date (YYYY-MM-DD):"` (or `/cancel`)
2. Text received (`step="start"`) → validate date (must be today or future, format YYYY-MM-DD) → on error re-prompt with error message → on success: save `start_date`, set `step="end"`, send prompt: `"Enter end date (YYYY-MM-DD):"`
3. Text received (`step="end"`) → validate (format YYYY-MM-DD, must be ≥ start_date) → on success: save `end_date`, set `step="reason"`, send prompt: `"Enter reason (optional, or /skip):"`
4. Text received (`step="reason"`) or `/skip` → create `PlayerAbsence(absence_type="period", ...)` → call `apply_absence_to_future_events` → clear state → send 2-sec confirmation → navigate to `absl:{player_id}:0:{back_page}`

**Date validation rules:**
- Format must be parseable as `YYYY-MM-DD`; any other input re-prompts with a format error
- Start date must be today or in the future
- End date must be ≥ start date

## Display Format

**Absence list screen text:**
```
📅 Absences — {Player Full Name}

• 2026-04-20 → 2026-04-25  (Injury)
• 2026-05-01 → 2026-05-03

[🗑 2026-04-20 → 2026-04-25]
[🗑 2026-05-01 → 2026-05-03]
[+ Add absence]
[← Back]
```

When the list is empty:
```
📅 Absences — {Player Full Name}

No absences registered.

[+ Add absence]
[← Back]
```

**Keyboard pagination for absence list:** up to 8 absences per page, with Prev/Next if needed.

**Player list screen (coach/admin):** reuses the same paged-list UX as event admin keyboard — one button per player showing full name. Page size: 10. Prev/Next nav + Back.

## Architecture

### New files

**`bot/absence_handlers.py`**
Async functions called from `handle_callback` and `handle_text` in `bot/handlers.py`:
- `show_other_menu(query, user, locale)` — renders the "Other" mini-menu
- `show_absence_root(query, user, db, back_page)` — branches on role: member → own list, coach/admin → player list
- `show_absence_player_list(query, user, db, page, back_page)` — paginated player list for coaches
- `show_absence_list(query, user, db, player_id, page, back_page)` — renders absence list for one player
- `start_add_absence(query, user, context, player_id, back_page)` — begins multi-step flow
- `handle_absence_text(update, context, db, user)` — processes text input for all 3 steps; called from `handle_text`
- `confirm_delete_absence(query, user, db, absence_id, player_id, page, back_page)` — shows confirmation
- `delete_absence(query, user, db, absence_id, player_id, page, back_page)` — deletes + refreshes list

**`bot/absence_keyboards.py`**
Keyboard builders:
- `other_menu_keyboard(back_page, locale)` — "Other" menu with Absences + Back
- `absence_player_list_keyboard(players, page, total_pages, back_page, locale)` — paginated player buttons
- `absence_list_keyboard(absences, player_id, page, total_pages, back_page, locale)` — one delete button per absence + Add + Back
- `absence_delete_confirm_keyboard(absence_id, player_id, page, back_page, locale)` — Yes/No confirm

### Modified files

**`bot/handlers.py`**
- `handle_callback`: add dispatch blocks for `other:`, `absm:`, `absl:`, `absa:`, `absd:`, `absdc:` — delegate to `bot/absence_handlers.py` functions
- `handle_callback` cleanup block: add `"awaiting_absence"` to the keys cleared on navigation (alongside `"awaiting_note"` etc.)
- `handle_text`: add check for `context.user_data.get("awaiting_absence")` → call `handle_absence_text`

**`bot/keyboards.py`** (`events_keyboard`)
- Add a new bottom row with `⚙️ [t("telegram.other_button")]` → `other:{page}`

**`locales/en.json`, `it.json`, `fr.json`, `de.json`** — new keys in the `"telegram"` section:
```
telegram.other_button          ⚙️ Other
telegram.absences_button       📅 Absences
telegram.absences_header       📅 Absences — {name}
telegram.absences_empty        No absences registered.
telegram.absence_add_button    + Add absence
telegram.absence_del_button    🗑 {dates}
telegram.absence_start_prompt  Enter start date (YYYY-MM-DD), or /cancel:
telegram.absence_end_prompt    Enter end date (YYYY-MM-DD), or /cancel:
telegram.absence_reason_prompt Enter reason (optional), or /skip:
telegram.absence_added         Absence added. %{count} event(s) updated.
telegram.absence_deleted       Absence deleted.
telegram.absence_date_error    Invalid date format. Please use YYYY-MM-DD:
telegram.absence_past_error    Start date must be today or in the future:
telegram.absence_range_error   End date must be on or after start date:
telegram.absence_confirm_del   Delete this absence?
telegram.absence_confirm_yes   ✅ Yes, delete
telegram.absence_confirm_no    ❌ No, keep
telegram.select_player         Select a player:
```

### Authorization

- Players: can only manage their own player's absences. `show_absence_root` finds the player linked to `user.id` (via `Player.user_id`). If no player found, show an error message.
- Coaches: can manage any player in their visible teams (`_visible_team_ids`). Player list is filtered to `PlayerTeam.team_id IN visible_team_ids`.
- Admins: see all non-archived players.
- Guard in `show_absence_list` and `delete_absence`: verify the target player belongs to the requesting user's scope (player owns it, or coach/admin has team access).

## Files to Change

| File | Change |
|------|--------|
| `bot/absence_handlers.py` | **New** — all absence async handlers |
| `bot/absence_keyboards.py` | **New** — keyboard builders |
| `bot/handlers.py` | Add dispatch + cleanup + text handler delegation |
| `bot/keyboards.py` | Add "⚙️ Other" row to `events_keyboard` |
| `locales/en.json`, `it.json`, `fr.json`, `de.json` | Add telegram absence keys |

## Verification

1. **Events list**: "⚙️ Other" button appears below Refresh/View More.
2. **Other menu**: Shows "📅 Absences" + Back. Back returns to events list.
3. **Member flow**: Absence root shows own absence list (or empty state). Add creates period absence, confirmation shows number of events updated. Delete shows confirmation, then removes the record.
4. **Coach flow**: Absence root shows paginated player list. Selecting a player shows their absences. Coach can add/delete for any team player.
5. **Date validation**: Non-date input re-prompts. Past start date rejected. End before start rejected.
6. **`/cancel` mid-flow**: Aborts, clears state, shows "Cancelled."
7. **Navigation away**: Clicking any other button mid-flow cleans up the pending prompt message.
8. **Attendance sync**: After adding an absence, future event attendance is correctly updated (check `apply_absence_to_future_events` is called).
