# Users Management Page — Design Spec

## Goal

Add an admin-only Users management section with two pages: a user list and a bulk-create-from-players page.

## Architecture

Two new routes in `routes/users.py`, both requiring `require_admin`. Two new templates. The bulk-create flow creates User records from selected Player records, links them via `player.user_id`, and emails credentials to each player's email address.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, existing `email_service`, existing `auth_service.hash_password`.

---

## Page 1: User List (`GET /auth/users`)

### Route
- `GET /auth/users` — admin only

### Data
- All User rows, each joined with their linked Player (via `Player.user_id`)
- Sorted by `created_at` descending

### Template: `templates/auth/users_list.html`

**Page header:** "Users" h2 + "Create from players" button linking to `/auth/users/bulk-create`

**Table columns:**
| Column | Source |
|---|---|
| Username | `user.username` |
| Email | `user.email` |
| Role | `user.role` as a badge (admin/coach/member) |
| Linked Player | `player.full_name` linked to `/players/{id}`, or "—" |
| Created | `user.created_at` formatted as date |
| Actions | `⋯` dropdown |

**Actions dropdown (per row):**
- **Deactivate / Reactivate** — toggles `user.is_active`
- **Delete** — POST with confirm, removes user record (player link set to NULL via ondelete=SET NULL)

**No filters** — user list is short enough to not need them.

---

## Page 2: Bulk Create (`GET /auth/users/bulk-create`, `POST /auth/users/bulk-create`)

### Routes
- `GET /auth/users/bulk-create` — render form
- `POST /auth/users/bulk-create` — process creation, show results

### GET: Filter + Player Checklist

**Filter row** (same pattern as events/players list):
- Team dropdown (all teams)
- Season dropdown (all seasons)
- Both trigger form resubmit on change

**Eligibility criteria for shown players:**
- `player.is_active = True`
- `player.email` is not null/empty
- `player.user_id` is null (no linked account yet)

**Players without email:** excluded silently from checklist; count shown as a note above the table: "N player(s) not shown — no email address on file."

**Checklist table columns:** checkbox, Full name, Email, Team(s)

**"Select all" checkbox** in thead.

**Role selector** below the list: dropdown (member / coach), default member — applied to all created accounts.

**Submit button:** "Create accounts & send emails"

### POST: Create & Email

For each selected `player_id`:
1. Skip if player already has `user_id` set (guard against double-submit)
2. Skip if player has no email
3. Generate a random 12-char secure password (`secrets.token_urlsafe(9)`)
4. Create `User(username=player.email, email=player.email, role=selected_role, hashed_password=hash_password(pw))`
5. Set `player.user_id = user.id`
6. Send welcome email with username + temporary password via `email_service`
7. Track result: created / skipped / email-failed

**Results page** (re-render same template or dedicated section):
- "X accounts created"
- "X skipped (already linked or no email)"
- "X email delivery failures" (with player names listed)
- "Back to users" link

### Email content
Subject: "Your ProManager account"
Body: username, temporary password, login URL hint. Plain text is sufficient.

---

## Navigation

Add "Users" link inside the admin dropdown in `templates/base.html` (next to "Register user"), pointing to `/auth/users`.

---

## Files

| Action | File |
|---|---|
| Create | `routes/users.py` |
| Create | `templates/auth/users_list.html` |
| Create | `templates/auth/bulk_create_users.html` |
| Modify | `app/main.py` — register `/auth/users` router |
| Modify | `templates/base.html` — add nav link in admin dropdown |
| Modify | `locales/en.json` (+ it, fr, de) — new i18n keys |

---

## i18n Keys

```
users.title             → "Users"
users.create_from_players → "Create from players"
users.linked_player     → "Linked Player"
users.deactivate        → "Deactivate"
users.reactivate        → "Reactivate"
users.delete            → "Delete"
users.bulk_create_title → "Create Accounts from Players"
users.no_email_note     → "{count} player(s) not shown — no email address on file."
users.role_label        → "Assign role"
users.submit_bulk       → "Create accounts & send emails"
users.created_count     → "{count} account(s) created"
users.skipped_count     → "{count} skipped (already linked or no email)"
users.email_failed_count → "{count} email delivery failure(s)"
```

---

## Testing

- `GET /auth/users` returns 200 for admin, 403 for non-admin
- `GET /auth/users/bulk-create` returns 200 for admin
- POST bulk-create creates User records and links player.user_id
- POST skips players that already have user_id
- POST skips players with no email
- Deactivate toggles is_active
- Delete removes user, player.user_id becomes NULL
