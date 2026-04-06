# Player Absences Feature Design

**Date:** 2026-04-06  
**Status:** Draft  
**Approach:** Eager Application (Approach 1)

---

## Overview

ProManager needs a player absence management system to track when players are unavailable. Absences can be:
- **Period-based:** A specific date range (e.g., April 10-20)
- **Recurring:** A repeating pattern (e.g., every Friday) scoped to a season

When an absence is active, players are automatically marked "absent" for all future events on those dates, with a dedicated note. Players can self-manage their own absences; coaches can view and manage absences for their team's players (by season).

---

## Requirements

### Functional

**Players:**
- Create/view/delete their own absences
- Specify period (start_date to end_date, inclusive) or recurring (rrule) absences
- Optionally provide a reason for the absence

**Coaches:**
- View absences for players in their managed team (per season)
- Create/delete absences on behalf of team players
- See which upcoming events are affected by an absence

**Admins:**
- Full CRUD access to any player's absences

**System:**
- Auto-set attendance to "absent" for future events falling within an absence period
- Override event defaults: if event.presence_type="all" (auto-present), absence still sets player to "absent"
- Preserve explicit coach overrides: if coach manually set a player to "present", don't override unless event defaults to "present"
- Do not retroactively change past event attendance

### Non-Functional

- Account-wide absences: one absence applies to all teams a player is in
- Delete-and-recreate model for modifications (no in-place edits)
- Season context required for recurring absences; period absences can span seasons
- Consistent audit trail via note field on Attendance records

---

## Data Model

### New: `PlayerAbsence` Model

```python
class PlayerAbsence(Base):
    __tablename__ = "player_absences"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # "period" | "recurring"
    absence_type: Mapped[str] = mapped_column(String(16), nullable=False)
    
    # Period absence: start_date (inclusive) to end_date (inclusive, full day)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    # Recurring absence: rrule string (RFC 5545, e.g., "FREQ=WEEKLY;BYDAY=FR")
    rrule: Mapped[str | None] = mapped_column(String(256), nullable=True)
    
    # Optional end date for recurring rule (auto-populated to season.end_date if not provided)
    rrule_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    
    # Season ID for context (required for recurring, optional for period)
    season_id: Mapped[int | None] = mapped_column(ForeignKey("seasons.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Reason (e.g., "Injury recovery", "Family vacation")
    reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    
    # Relationships
    player: Mapped[Player] = relationship("Player", back_populates="absences")
    season: Mapped["Season | None"] = relationship("Season", lazy="select")
```

### Modified: `Attendance` Model

No schema changes. The note field (already existing) is used to track absence origin:
- Note format: `"[Absence] {reason}"` or `"[Absence] On leave"` if reason is not provided

---

## Business Logic

### Service: `absence_service.py`

#### Function 1: `is_date_in_absence(player_id: int, check_date: date, db: Session) -> bool`

Check if a date falls within any active absence for a player.

**Logic:**
- Query all `PlayerAbsence` records for the player
- For `absence_type == "period"`: check `start_date <= check_date <= end_date`
- For `absence_type == "recurring"`: parse rrule, generate occurrences up to `check_date`, check membership
- Return `True` if any absence matches

**Edge cases:**
- Ignore recurring absences where `rrule_until` is in the past
- Handle invalid rrule strings gracefully (log warning, skip)

---

#### Function 2: `apply_absence_to_future_events(player_id: int, db: Session) -> int`

Apply an absence to all matching future event attendance records.

**Logic:**
1. Query all `Attendance` records where:
   - `player_id` matches
   - `event.event_date >= today()`
2. For each Attendance:
   - If `is_date_in_absence(player_id, event.event_date)`:
     - If status is "unknown" → set to "absent"
     - If status is "present" AND event.presence_type == "all" → set to "absent" (override the default)
     - Otherwise (coach override or explicit choice) → leave as-is
   - Update note to `"[Absence] {reason}"` or `"[Absence] On leave"`
3. Commit all updates in a single transaction
4. Return count of updated records

**Rationale for "present + all" override:**
- When `presence_type="all"`, "present" is auto-assigned to everyone by default
- An absence should override that default, not be subordinate to it
- A coach's explicit "present" on a non-"all" event is preserved (assumed intentional)

---

#### Function 3: `clear_absence_from_events(player_id: int, reason: str | None, db: Session) -> int`

Clear auto-set absence records from attendance (called when deleting an absence).

**Logic:**
1. Query all `Attendance` records where:
   - `player_id` matches
   - `note` matches the pattern `"[Absence] {reason or 'On leave'}"`
   - `status == "absent"` (only clear absences, not explicit coach decisions)
2. Set status back to "unknown" and clear note field for matching records
3. Return count of cleared records

**Rationale:** Deleting Attendance records entirely is destructive and makes recovery harder. Resetting to "unknown" preserves the record and allows coaches to see what was previously auto-set.

**Note:** This function is optional. Per requirements, past events stay unchanged. This is only for cleaning up future events if a coach corrects a mistake (created wrong absence).

---

### Validation Rules

**Period absences:**
- `start_date <= end_date`
- Both dates are in the future (today or later; no retroactive entries)
- At least one future event must fall within the range (or allow empty ranges)

**Recurring absences:**
- rrule string must parse correctly using `dateutil.rrule.rrulestr()`
- Must generate at least one occurrence within rrule_until (if set)
- `rrule_until` must be in the future
- `season_id` is required

**Both types:**
- `player_id` must exist and be active
- Reason (if provided) is max 512 chars

---

## API Routes

### Player Endpoints

**GET `/api/players/{player_id}/absences`**
- View own absences (or coach/admin viewing their team's player)
- Returns: list of PlayerAbsence objects
- Guard: `require_login` + ownership check

**POST `/api/players/{player_id}/absences`**
- Create absence (period or recurring)
- Body: `{ absence_type, start_date?, end_date?, rrule?, rrule_until?, season_id?, reason? }`
- Triggers: `apply_absence_to_future_events()`
- Guard: `require_login` + ownership check

**DELETE `/api/players/{player_id}/absences/{absence_id}`**
- Delete absence
- Triggers: `clear_absence_from_events()` (optional cleanup)
- Guard: `require_login` + ownership check

---

### Coach Endpoints

**GET `/api/teams/{team_id}/season/{season_id}/absences`**
- List all absences for players in a team (for that season)
- Returns: list of PlayerAbsence + player details
- Guard: `require_login` + team coach check

**GET `/api/players/{player_id}/absences`** (same as player endpoint)
- Coach views a specific player's absences
- Guard: team coach check

**POST/DELETE** (same POST/DELETE endpoints as player, with team coach guard)

---

### Admin Endpoints

All endpoints with `require_admin` guard.

---

## Access Control

**Player:**
- `GET /api/players/{player_id}/absences` — only own absences
- `POST /api/players/{player_id}/absences` — only own absences
- `DELETE /api/players/{player_id}/absences/{absence_id}` — only own absences

**Coach:**
- Access restricted to players in their managed team + season
- Per CLAUDE.md: coaches are scoped by team and optionally by season
- Query: `UserTeam.filter(user_id=current_user, team_id=team_id, season_id=season_id)`

**Admin:**
- Full access, no restrictions

---

## UI

### Player Page: `/players/{player_id}/absences`

**List section:**
- Table: Absence Type | Dates/Pattern | Reason | Actions (Edit, Delete)
- For period absences: show "April 10 – April 20"
- For recurring: show "Every Friday until Dec 31, 2026"
- Empty state: "No absences scheduled"

**Create/Edit Form:**
- Radio group: "Period" vs "Recurring"
- Conditional fields:
  - Period: date picker (start, end)
  - Recurring: rrule builder (weekday checkboxes, frequency dropdown, optional until date)
    - If no until date, auto-populate to season.end_date
  - Both: text field for reason (optional)
- Submit button, validation on client + server
- On success: redirect to list, show toast "Absence created"

---

### Coach Page: Team Absences View

**List of team players + their absences:**
- Table: Player Name | Absence Type | Dates/Pattern | Reason | Actions (Delete, or "View Detail")
- Filter by player name (optional)
- Upcoming events affected badge: "3 events affected"

**Create/Edit absence on behalf of player:**
- Same form as player page, but with player selector dropdown
- Pre-populate reason field with hint like "Enter reason (e.g., injury, vacation)"

---

### Event Detail View (All Roles)

When viewing an event, if a player's attendance is "absent" due to an absence:
- Show tag next to player name: `"[Absence: On leave]"` or `"[Absence: {reason}]"`
- Coaches can still manually override by clicking to edit attendance

---

## Testing Strategy

**Unit tests:**
- `is_date_in_absence()` with period and recurring patterns
- rrule parsing and occurrence generation
- Validation rules (dates, rrule format)

**Integration tests:**
- Create period absence → verify Attendance records updated
- Create recurring absence → verify correct events matched
- Override "present" when event.presence_type="all"
- Preserve coach overrides on "present" for non-"all" events
- Access control: player can't view other player absences, coach restricted to team

**E2E:**
- Player creates period absence → appears in list → auto-sets attendance
- Coach creates recurring absence for player → affects multiple future events
- Delete absence → clears auto-set records, preserves coach overrides

---

## Edge Cases & Future Considerations

**Out of scope for v1:**
- Bulk absence import (CSV upload)
- Absence approval workflow (admin/coach approve before applying)
- Absence conflict detection (warn if multiple absences overlap)
- Absence history/audit trail (who deleted, when)

**Future v2 features:**
- Add `absence_id` FK to `Attendance` for tracking and in-place edits
- Rrule modification (currently delete/recreate)
- Absence templates (coach-defined recurring patterns)
- Multi-year recurring patterns (every Friday indefinitely, or until explicitly ended)

---

## Success Criteria

✓ Players can create, view, and delete their own absences  
✓ Coaches can view and manage team player absences (per season)  
✓ Future events fall into absence patterns automatically  
✓ Attendance records show absence reason in note field  
✓ Coach overrides preserved (explicit decisions not overridden)  
✓ Event defaults respected (presence_type="all" still overridden by absence)  
✓ Access control: players see own, coaches see team, admins see all  
✓ Full rrule support (no time component; dates only)  
✓ Recurring absences auto-default to season end  
✓ Period absences can span multiple seasons  

---

## Questions for Review

None at this time. Design is complete and validated.
