# Users Management Page — Design Spec

## Goal

Add an admin-only Users management section with two pages: a user list and a bulk-create-from-players page.

## Architecture

New route file `routes/users.py`. All endpoints require `require_admin`. Two new templates. The bulk-create flow creates User records from selected Player records, links them via `player.user_id`, and emails credentials to each player's email address.

**Tech Stack:** FastAPI, SQLAlchemy, Jinja2, existing `email_service`, existing `auth_service.hash_password`.

**Router registration** — add to `_routers` list in `app/main.py`:
```python
("routes.users", "/auth/users", "users"),
```

**`is_active` at login:** `auth_service.py` already rejects login for `is_active=False` users (`if user is None or not user.is_active`). No changes needed.

---

## Page 1: User List (`GET /auth/users`)

### Routes

All POST routes registered **after** all GET routes in `routes/users.py`. The `/bulk-create` routes must be registered **before** `/{user_id}/...` routes to prevent FastAPI matching `"bulk-create"` as an integer `user_id`.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/auth/users` | require_admin | List all users |
| GET | `/auth/users/bulk-create` | require_admin | Show filter + player checklist |
| POST | `/auth/users/bulk-create` | require_admin + require_csrf | Process creation, show results |
| POST | `/auth/users/{user_id}/toggle-active` | require_admin + require_csrf | Deactivate / reactivate |
| POST | `/auth/users/{user_id}/delete` | require_admin + require_csrf | Delete user |

All POST forms include `<input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">`.

### Data
- All User rows, each joined with their linked Player (via `Player.user_id = User.id`)
- Sorted by `created_at` descending
- `User.role` values: `"admin"`, `"coach"`, `"member"`

### Template: `templates/auth/users_list.html`

**Page header:** h2 + "Create from players" button linking to `/auth/users/bulk-create`

**Table columns:**
| Column | i18n key | Source |
|---|---|---|
| Username | `users.username` | `user.username` |
| Email | `users.email` | `user.email` |
| Role | `users.role` | `user.role` as badge (admin/coach/member) |
| Linked Player | `users.linked_player` | `player.full_name` linked to `/players/{id}`, or "—" |
| Created | `users.created_at` | `user.created_at` formatted as date |
| Actions | `users.actions` | `⋯` dropdown |

No status column — active/inactive state is implied by the action label (Deactivate vs Reactivate).

**Actions dropdown (per row):**
- **Deactivate / Reactivate** — `POST /auth/users/{id}/toggle-active` with CSRF. Label: `users.deactivate` or `users.reactivate` based on `user.is_active`.
- **Delete** — `POST /auth/users/{id}/delete` with CSRF + JS `confirm()`.

**Safety guards (apply to both toggle-active and delete):**
- Cannot act on the currently logged-in user (`user.id == request.state.user.id`) — show greyed-out `⋯` with label `users.cannot_edit_self`, no POST form rendered.
- Cannot deactivate or delete the only remaining active admin:
  ```python
  active_admin_count = db.query(User).filter(User.role == "admin", User.is_active == True).count()
  ```
  If `active_admin_count <= 1` and the target user is that admin → raise `NotAuthorized` / return 400.

---

## Page 2: Bulk Create (`GET /auth/users/bulk-create`, `POST /auth/users/bulk-create`)

### GET: Filter + Player Checklist

**Filter row** (same pattern as events/players list — GET form, `onchange="this.form.submit()"`):
- Team dropdown — all teams, "All teams" default
- Season dropdown — all seasons, "All seasons" default

**Eligibility criteria for shown players:**
- `player.is_active = True`
- `player.email` is not null/empty
- `player.user_id` is null (no linked account yet)
- No existing `User` with `username = player.email` OR `email = player.email`

**Players without email:** excluded from checklist; count shown above table: `users.no_email_note`.

**Checklist table columns:** checkbox (`name="player_ids"`, `value="{{ player.id }}"`), Full name, Email

**"Select all" checkbox** in thead — JS toggles all checkboxes.

**Role selector** below the list: dropdown (`member` / `coach`), default `member`. Label: `users.role_label`.

**Submit button:** `users.submit_bulk`

### POST: Create & Email

Each player processed independently — one failure does not abort the rest.

For each selected `player_id`:
1. Re-fetch player; skip if `player.user_id` is already set
2. Skip if `player.email` is null/empty
3. Skip if `User` already exists with `User.username == player.email` or `User.email == player.email` — track as skipped
4. Generate temporary password: `secrets.token_urlsafe(12)` (~16 chars, ~96 bits entropy)
5. Create `User(username=player.email, email=player.email, role=selected_role, hashed_password=hash_password(pw))`
6. Set `player.user_id = new_user.id`; `db.commit()`
7. Send welcome email:
   ```python
   email_service.send_email(
       to=player.email,
       subject="Your ProManager account",
       body_html=f"<p>Username: {player.email}<br>Password: {pw}</p>",
       body_text=f"Username: {player.email}\nPassword: {pw}",
   )
   ```
8. Track result: `created` / `skipped` / `email_failed`

**Results:** Re-render `bulk_create_users.html` with `results` context dict (no redirect). Template shows results block when `results` is present:
- `users.results_title`
- `users.created_count`
- `users.skipped_count`
- `users.email_failed_count` (list player names below)
- `users.back_to_users` link → `/auth/users`

Filter dropdowns reset; checklist not shown in results view.

---

## Navigation

Add "Users" link in admin dropdown in `templates/base.html`, after "Register user":
```html
<li><a href="/auth/users">{{ t('users.title') }}</a></li>
```

---

## Files

| Action | File |
|---|---|
| Create | `routes/users.py` |
| Create | `templates/auth/users_list.html` |
| Create | `templates/auth/bulk_create_users.html` |
| Modify | `app/main.py` — add `("routes.users", "/auth/users", "users")` to `_routers` |
| Modify | `templates/base.html` — add nav link in admin dropdown |
| Modify | `locales/en.json` (+ it, fr, de) — new i18n keys |

---

## i18n Keys

```
users.title               → "Users"
users.username            → "Username"
users.email               → "Email"
users.role                → "Role"
users.linked_player       → "Linked Player"
users.created_at          → "Created"
users.actions             → "Actions"
users.create_from_players → "Create from players"
users.deactivate          → "Deactivate"
users.reactivate          → "Reactivate"
users.delete              → "Delete"
users.cannot_edit_self    → "Cannot edit your own account"
users.bulk_create_title   → "Create Accounts from Players"
users.no_email_note       → "{count} player(s) not shown — no email address on file."
users.role_label          → "Assign role"
users.select_all          → "Select all"
users.submit_bulk         → "Create accounts & send emails"
users.results_title       → "Results"
users.created_count       → "{count} account(s) created"
users.skipped_count       → "{count} skipped (already linked or email already in use)"
users.email_failed_count  → "{count} email delivery failure(s)"
users.back_to_users       → "Back to users"
```

---

## Testing

- `GET /auth/users` returns 200 for admin, 403 for member/coach
- `GET /auth/users/bulk-create` returns 200 for admin, 403 for non-admin
- POST bulk-create creates User records, sets `player.user_id`, sends email
- POST skips players that already have `user_id` set
- POST skips players with no email
- POST skips players whose email matches an existing User username or email
- Toggle-active deactivates then reactivates a user
- Delete removes user; `player.user_id` becomes NULL
- Cannot toggle-active or delete the currently logged-in admin (returns 400/403)
- Cannot deactivate the only remaining active admin (returns 400/403)
- Cannot delete the only remaining active admin (returns 400/403)
