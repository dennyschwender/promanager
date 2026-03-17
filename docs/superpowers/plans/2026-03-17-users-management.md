# Users Management Page — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-only `/auth/users` list page and `/auth/users/bulk-create` page that lets admins view all users, deactivate/delete them, and mass-create accounts from players with automatic email delivery.

**Architecture:** New `routes/users.py` with 5 endpoints, two new templates following existing Pico CSS + action-dropdown patterns, i18n keys in all 4 locales. All routes are admin-only. Bulk-create uses `email_service.send_email()` per player. Safety guards prevent self-deletion and last-admin deletion/deactivation.

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Jinja2, bcrypt (via auth_service), smtplib (via email_service), pytest.

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| Create | `routes/users.py` | All 5 user management endpoints |
| Create | `templates/auth/users_list.html` | User list table with action dropdowns |
| Create | `templates/auth/bulk_create_users.html` | Filter + checklist + results |
| Modify | `app/main.py` | Register users router in `_routers` list |
| Modify | `templates/base.html` | Add "Users" link in admin nav dropdown |
| Modify | `locales/en.json` | New `users.*` keys |
| Modify | `locales/it.json` | New `users.*` keys (Italian) |
| Modify | `locales/fr.json` | New `users.*` keys (French) |
| Modify | `locales/de.json` | New `users.*` keys (German) |
| Create | `tests/test_users.py` | Tests for all routes |

---

## Task 1: i18n Keys

**Files:**
- Modify: `locales/en.json`
- Modify: `locales/it.json`
- Modify: `locales/fr.json`
- Modify: `locales/de.json`

No tests for i18n — verified visually when templates render.

- [ ] **Step 1: Add keys to `locales/en.json`**

Open the file and add a new `"users"` block. The file uses nested JSON objects. Add after the existing `"auth"` block:

```json
"users": {
  "title": "Users",
  "username": "Username",
  "email": "Email",
  "role": "Role",
  "linked_player": "Linked Player",
  "created_at": "Created",
  "actions": "Actions",
  "create_from_players": "Create from players",
  "deactivate": "Deactivate",
  "reactivate": "Reactivate",
  "delete": "Delete",
  "cannot_edit_self": "Cannot edit your own account",
  "bulk_create_title": "Create Accounts from Players",
  "no_email_note": "{count} player(s) not shown — no email address on file.",
  "role_label": "Assign role",
  "select_all": "Select all",
  "submit_bulk": "Create accounts & send emails",
  "results_title": "Results",
  "created_count": "{count} account(s) created",
  "skipped_count": "{count} skipped (already linked or email already in use)",
  "email_failed_count": "{count} email delivery failure(s)",
  "back_to_users": "Back to users"
}
```

- [ ] **Step 2: Add keys to `locales/it.json`**

```json
"users": {
  "title": "Utenti",
  "username": "Nome utente",
  "email": "Email",
  "role": "Ruolo",
  "linked_player": "Giocatore collegato",
  "created_at": "Creato",
  "actions": "Azioni",
  "create_from_players": "Crea da giocatori",
  "deactivate": "Disattiva",
  "reactivate": "Riattiva",
  "delete": "Elimina",
  "cannot_edit_self": "Non puoi modificare il tuo account",
  "bulk_create_title": "Crea account dai giocatori",
  "no_email_note": "{count} giocatore/i non mostrato/i — nessun indirizzo email.",
  "role_label": "Assegna ruolo",
  "select_all": "Seleziona tutti",
  "submit_bulk": "Crea account e invia email",
  "results_title": "Risultati",
  "created_count": "{count} account creato/i",
  "skipped_count": "{count} saltato/i (già collegato o email in uso)",
  "email_failed_count": "{count} errore/i di consegna email",
  "back_to_users": "Torna agli utenti"
}
```

- [ ] **Step 3: Add keys to `locales/fr.json`**

```json
"users": {
  "title": "Utilisateurs",
  "username": "Nom d'utilisateur",
  "email": "Email",
  "role": "Rôle",
  "linked_player": "Joueur lié",
  "created_at": "Créé le",
  "actions": "Actions",
  "create_from_players": "Créer depuis les joueurs",
  "deactivate": "Désactiver",
  "reactivate": "Réactiver",
  "delete": "Supprimer",
  "cannot_edit_self": "Impossible de modifier votre propre compte",
  "bulk_create_title": "Créer des comptes depuis les joueurs",
  "no_email_note": "{count} joueur(s) non affiché(s) — pas d'adresse email.",
  "role_label": "Attribuer un rôle",
  "select_all": "Tout sélectionner",
  "submit_bulk": "Créer les comptes et envoyer les emails",
  "results_title": "Résultats",
  "created_count": "{count} compte(s) créé(s)",
  "skipped_count": "{count} ignoré(s) (déjà lié ou email déjà utilisé)",
  "email_failed_count": "{count} échec(s) d'envoi d'email",
  "back_to_users": "Retour aux utilisateurs"
}
```

- [ ] **Step 4: Add keys to `locales/de.json`**

```json
"users": {
  "title": "Benutzer",
  "username": "Benutzername",
  "email": "E-Mail",
  "role": "Rolle",
  "linked_player": "Verknüpfter Spieler",
  "created_at": "Erstellt",
  "actions": "Aktionen",
  "create_from_players": "Aus Spielern erstellen",
  "deactivate": "Deaktivieren",
  "reactivate": "Reaktivieren",
  "delete": "Löschen",
  "cannot_edit_self": "Eigenes Konto kann nicht bearbeitet werden",
  "bulk_create_title": "Konten aus Spielern erstellen",
  "no_email_note": "{count} Spieler nicht angezeigt — keine E-Mail-Adresse.",
  "role_label": "Rolle zuweisen",
  "select_all": "Alle auswählen",
  "submit_bulk": "Konten erstellen und E-Mails senden",
  "results_title": "Ergebnisse",
  "created_count": "{count} Konto/Konten erstellt",
  "skipped_count": "{count} übersprungen (bereits verknüpft oder E-Mail in Verwendung)",
  "email_failed_count": "{count} E-Mail-Zustellungsfehler",
  "back_to_users": "Zurück zu Benutzern"
}
```

- [ ] **Step 5: Commit**

```bash
git add locales/
git commit -m "feat: add users.* i18n keys to all locales"
```

---

## Task 2: User List Route + Tests

**Files:**
- Create: `routes/users.py`
- Create: `tests/test_users.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_users.py`:

```python
"""Tests for /auth/users routes."""
import pytest
from models.user import User
from services.auth_service import hash_password


def _make_user(db, username, email, role="member"):
    u = User(username=username, email=email,
             hashed_password=hash_password("Pass1234!"), role=role)
    db.add(u)
    db.flush()
    return u


# ---------------------------------------------------------------------------
# User list
# ---------------------------------------------------------------------------

def test_users_list_admin_200(admin_client):
    resp = admin_client.get("/auth/users", follow_redirects=False)
    assert resp.status_code == 200


def test_users_list_member_403(member_client):
    resp = member_client.get("/auth/users", follow_redirects=False)
    assert resp.status_code in (302, 403)


def test_users_list_shows_users(admin_client, db):
    _make_user(db, "alice", "alice@test.com", role="member")
    db.commit()
    resp = admin_client.get("/auth/users")
    assert b"alice" in resp.content
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_users.py -v
```

Expected: `ModuleNotFoundError` or `404` — routes don't exist yet.

- [ ] **Step 3: Create `routes/users.py` with list route**

```python
"""routes/users.py — Admin user management."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.templates import render
from models.player import Player
from models.user import User
from routes._auth_helpers import require_admin

router = APIRouter()


@router.get("", dependencies=[Depends(require_admin)])
async def users_list(request: Request, db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    # Build player lookup: user_id -> Player
    players = db.query(Player).filter(Player.user_id.isnot(None)).all()
    player_by_user: dict[int, Player] = {p.user_id: p for p in players}
    return render(
        request,
        "auth/users_list.html",
        {
            "user": request.state.user,
            "users": users,
            "player_by_user": player_by_user,
        },
    )
```

- [ ] **Step 4: Register router in `app/main.py`**

Open `app/main.py`, find the `_routers` list, and add:

```python
("routes.users", "/auth/users", "users"),
```

Add it after the `("routes.reports", ...)` entry.

- [ ] **Step 5: Run tests — expect pass**

```bash
pytest tests/test_users.py::test_users_list_admin_200 tests/test_users.py::test_users_list_member_403 tests/test_users.py::test_users_list_shows_users -v
```

Expected: all PASS (template doesn't exist yet — may get 500, adjust test to check for non-404 first if needed — create minimal template in next task).

- [ ] **Step 6: Commit**

```bash
git add routes/users.py app/main.py tests/test_users.py
git commit -m "feat: add /auth/users list route (admin only)"
```

---

## Task 3: User List Template

**Files:**
- Create: `templates/auth/users_list.html`
- Modify: `templates/base.html`

- [ ] **Step 1: Create `templates/auth/users_list.html`**

```html
{% extends "base.html" %}
{% block title %}{{ t('users.title') }} — ProManager{% endblock %}
{% block breadcrumb %}
<nav class="breadcrumb">
  <a href="/dashboard">Home</a><span class="breadcrumb-sep"></span>
  <span>{{ t('users.title') }}</span>
</nav>
{% endblock %}
{% block content %}
<div class="page-header">
  <h2>{{ t('users.title') }}</h2>
  <a href="/auth/users/bulk-create" class="btn btn-primary">{{ t('users.create_from_players') }}</a>
</div>

<div class="table-responsive">
<table>
  <thead><tr>
    <th>{{ t('users.username') }}</th>
    <th>{{ t('users.email') }}</th>
    <th>{{ t('users.role') }}</th>
    <th>{{ t('users.linked_player') }}</th>
    <th>{{ t('users.created_at') }}</th>
    <th>{{ t('users.actions') }}</th>
  </tr></thead>
  <tbody>
  {% for u in users %}
  <tr>
    <td>{{ u.username }}</td>
    <td>{{ u.email }}</td>
    <td><span class="badge badge-{{ u.role }}">{{ u.role|capitalize }}</span></td>
    <td>
      {% set p = player_by_user.get(u.id) %}
      {% if p %}<a href="/players/{{ p.id }}">{{ p.full_name }}</a>{% else %}—{% endif %}
    </td>
    <td>{{ u.created_at.strftime('%Y-%m-%d') if u.created_at else '—' }}</td>
    <td>
      {% if u.id == user.id %}
        <span class="text-muted" style="font-size:.82rem;">{{ t('users.cannot_edit_self') }}</span>
      {% else %}
      <div class="action-dropdown">
        <button type="button" class="btn btn-sm btn-outline action-dropdown-toggle" aria-haspopup="true">⋯</button>
        <div class="action-dropdown-menu">
          <form method="post" action="/auth/users/{{ u.id }}/toggle-active">
            <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
            <button type="submit" class="{% if not u.is_active %}reactivate{% endif %}">
              {% if u.is_active %}{{ t('users.deactivate') }}{% else %}{{ t('users.reactivate') }}{% endif %}
            </button>
          </form>
          <form method="post" action="/auth/users/{{ u.id }}/delete"
                onsubmit="return confirm('Delete user {{ u.username }}?')">
            <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
            <button type="submit" class="danger">{{ t('users.delete') }}</button>
          </form>
        </div>
      </div>
      {% endif %}
    </td>
  </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% endblock %}
{% block scripts %}
<script>
document.addEventListener('click', function (e) {
  var toggle = e.target.closest('.action-dropdown-toggle');
  if (toggle) {
    e.stopPropagation();
    var menu = toggle.nextElementSibling;
    var isOpen = menu.classList.contains('open');
    document.querySelectorAll('.action-dropdown-menu.open').forEach(function (m) { m.classList.remove('open'); m.classList.remove('open-up'); });
    document.querySelectorAll('.table-responsive.dropdown-open').forEach(function (w) { w.classList.remove('dropdown-open'); });
    if (!isOpen) {
      var rect = toggle.getBoundingClientRect();
      menu.classList.add('open');
      if (window.innerHeight - rect.bottom < 120) menu.classList.add('open-up');
      var wrapper = toggle.closest('.table-responsive');
      if (wrapper) wrapper.classList.add('dropdown-open');
    }
    return;
  }
  document.querySelectorAll('.action-dropdown-menu.open').forEach(function (m) { m.classList.remove('open'); m.classList.remove('open-up'); });
  document.querySelectorAll('.table-responsive.dropdown-open').forEach(function (w) { w.classList.remove('dropdown-open'); });
});
</script>
{% endblock %}
```

- [ ] **Step 2: Add "Users" link to admin nav dropdown in `templates/base.html`**

Find this block:
```html
{% if user.is_admin %}
  <li><a href="/auth/register">{{ t('nav.register_user') }}</a></li>
  <li><hr style="margin:.25rem 0;"></li>
{% endif %}
```

Change it to:
```html
{% if user.is_admin %}
  <li><a href="/auth/register">{{ t('nav.register_user') }}</a></li>
  <li><a href="/auth/users">{{ t('users.title') }}</a></li>
  <li><hr style="margin:.25rem 0;"></li>
{% endif %}
```

- [ ] **Step 3: Run the list tests**

```bash
pytest tests/test_users.py::test_users_list_admin_200 tests/test_users.py::test_users_list_shows_users -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add templates/auth/users_list.html templates/base.html
git commit -m "feat: users list template and nav link"
```

---

## Task 4: Toggle-Active and Delete Routes + Tests

**Files:**
- Modify: `routes/users.py`
- Modify: `tests/test_users.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_users.py`:

```python
# ---------------------------------------------------------------------------
# Toggle active
# ---------------------------------------------------------------------------

def test_toggle_active_deactivates_user(admin_client, db, admin_user):
    target = _make_user(db, "bob", "bob@test.com")
    db.commit()
    resp = admin_client.post(
        f"/auth/users/{target.id}/toggle-active",
        data={"csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db.refresh(target)
    assert target.is_active is False


def test_toggle_active_reactivates_user(admin_client, db):
    target = _make_user(db, "carol", "carol@test.com")
    target.is_active = False
    db.commit()
    resp = admin_client.post(
        f"/auth/users/{target.id}/toggle-active",
        data={"csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    db.refresh(target)
    assert target.is_active is True


def test_cannot_deactivate_self(admin_client, db, admin_user):
    resp = admin_client.post(
        f"/auth/users/{admin_user.id}/toggle-active",
        data={"csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code in (400, 403)


def test_cannot_deactivate_last_admin(admin_client, db, admin_user):
    # admin_user is the only admin — deactivating should be blocked
    resp = admin_client.post(
        f"/auth/users/{admin_user.id}/toggle-active",
        data={"csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code in (400, 403)


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------

def test_delete_user(admin_client, db):
    target = _make_user(db, "dave", "dave@test.com")
    db.commit()
    uid = target.id
    resp = admin_client.post(
        f"/auth/users/{uid}/delete",
        data={"csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert db.get(User, uid) is None


def test_delete_user_unlinks_player(admin_client, db):
    from models.player import Player
    target = _make_user(db, "eve", "eve@test.com")
    player = Player(first_name="Eve", last_name="Test", is_active=True, user_id=target.id)
    db.add(player)
    db.commit()
    pid = player.id
    admin_client.post(f"/auth/users/{target.id}/delete", data={"csrf_token": "test"})
    db.expire_all()
    p = db.get(Player, pid)
    assert p.user_id is None


def test_cannot_delete_self(admin_client, db, admin_user):
    resp = admin_client.post(
        f"/auth/users/{admin_user.id}/delete",
        data={"csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code in (400, 403)


def test_cannot_delete_last_admin(admin_client, db, admin_user):
    resp = admin_client.post(
        f"/auth/users/{admin_user.id}/delete",
        data={"csrf_token": "test"},
        follow_redirects=False,
    )
    assert resp.status_code in (400, 403)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_users.py -k "toggle or delete" -v
```

Expected: 404 or attribute errors — routes not yet implemented.

- [ ] **Step 3: Add toggle-active and delete routes to `routes/users.py`**

Add these imports at the top of `routes/users.py`:
```python
from fastapi import Form
from fastapi.responses import RedirectResponse, HTMLResponse
from routes._auth_helpers import NotAuthorized
from app.csrf import require_csrf
```

Then append these routes (IMPORTANT: register these **after** the bulk-create routes you'll add in Task 5 — but since bulk-create is at `/bulk-create` which is not an int path, it's safe to add these now):

```python
@router.post("/{user_id}/toggle-active", dependencies=[Depends(require_admin), Depends(require_csrf)])
async def toggle_active(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    current_user = request.state.user
    target = db.get(User, user_id)
    if target is None:
        return RedirectResponse("/auth/users", status_code=302)

    # Cannot act on yourself
    if target.id == current_user.id:
        raise NotAuthorized

    # Cannot deactivate the last active admin
    if target.role == "admin" and target.is_active:
        active_admin_count = db.query(User).filter(
            User.role == "admin", User.is_active == True  # noqa: E712
        ).count()
        if active_admin_count <= 1:
            raise NotAuthorized

    target.is_active = not target.is_active
    db.commit()
    return RedirectResponse("/auth/users", status_code=302)


@router.post("/{user_id}/delete", dependencies=[Depends(require_admin), Depends(require_csrf)])
async def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    current_user = request.state.user
    target = db.get(User, user_id)
    if target is None:
        return RedirectResponse("/auth/users", status_code=302)

    # Cannot delete yourself
    if target.id == current_user.id:
        raise NotAuthorized

    # Cannot delete the last active admin
    if target.role == "admin":
        active_admin_count = db.query(User).filter(
            User.role == "admin", User.is_active == True  # noqa: E712
        ).count()
        if active_admin_count <= 1:
            raise NotAuthorized

    db.delete(target)
    db.commit()
    return RedirectResponse("/auth/users", status_code=302)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_users.py -k "toggle or delete" -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add routes/users.py tests/test_users.py
git commit -m "feat: toggle-active and delete user routes with safety guards"
```

---

## Task 5: Bulk-Create GET Route + Template

**Files:**
- Modify: `routes/users.py`
- Create: `templates/auth/bulk_create_users.html`

- [ ] **Step 1: Write failing test**

Append to `tests/test_users.py`:

```python
# ---------------------------------------------------------------------------
# Bulk create — GET
# ---------------------------------------------------------------------------

def test_bulk_create_get_admin_200(admin_client):
    resp = admin_client.get("/auth/users/bulk-create", follow_redirects=False)
    assert resp.status_code == 200


def test_bulk_create_get_member_403(member_client):
    resp = member_client.get("/auth/users/bulk-create", follow_redirects=False)
    assert resp.status_code in (302, 403)


def test_bulk_create_shows_eligible_players(admin_client, db):
    from models.player import Player
    # Eligible: active, has email, no user_id
    p = Player(first_name="Frank", last_name="Test", is_active=True, email="frank@test.com")
    db.add(p)
    # Ineligible: no email
    p2 = Player(first_name="Grace", last_name="Test", is_active=True)
    db.add(p2)
    db.commit()
    resp = admin_client.get("/auth/users/bulk-create")
    assert b"frank@test.com" in resp.content
    assert b"Grace" not in resp.content


def test_bulk_create_excludes_linked_players(admin_client, db):
    from models.player import Player
    u = _make_user(db, "henry", "henry@test.com")
    p = Player(first_name="Henry", last_name="Test", is_active=True,
               email="henry@test.com", user_id=u.id)
    db.add(p)
    db.commit()
    resp = admin_client.get("/auth/users/bulk-create")
    assert b"henry@test.com" not in resp.content
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_users.py -k "bulk_create_get" -v
```

Expected: 404.

- [ ] **Step 3: Add bulk-create GET route to `routes/users.py`**

Add these imports at the top if not already present:
```python
from models.season import Season
from models.team import Team
from models.player_team import PlayerTeam
```

Add the route **before** the `/{user_id}/toggle-active` route (order matters for FastAPI — literal paths before parameterised paths):

```python
@router.get("/bulk-create", dependencies=[Depends(require_admin)])
async def bulk_create_get(
    request: Request,
    team_id: str | None = None,
    season_id: str | None = None,
    db: Session = Depends(get_db),
):
    selected_team_id = int(team_id) if team_id and team_id.strip() else None
    selected_season_id = int(season_id) if season_id and season_id.strip() else None

    teams = db.query(Team).order_by(Team.name).all()
    seasons = db.query(Season).order_by(Season.name).all()

    # Find existing user emails/usernames to exclude
    existing_emails = {u.email for u in db.query(User.email).all()}
    existing_usernames = {u.username for u in db.query(User.username).all()}
    taken = existing_emails | existing_usernames

    # Base query: active players with email, no user_id
    q = (
        db.query(Player)
        .filter(
            Player.is_active == True,  # noqa: E712
            Player.email.isnot(None),
            Player.email != "",
            Player.user_id.is_(None),
        )
    )

    # Apply team/season filter via PlayerTeam join
    if selected_team_id:
        player_ids_in_team = [
            row.player_id
            for row in db.query(PlayerTeam.player_id)
            .filter(PlayerTeam.team_id == selected_team_id)
            .all()
        ]
        if selected_season_id:
            player_ids_in_team = [
                row.player_id
                for row in db.query(PlayerTeam.player_id)
                .filter(
                    PlayerTeam.team_id == selected_team_id,
                    PlayerTeam.season_id == selected_season_id,
                )
                .all()
            ]
        q = q.filter(Player.id.in_(player_ids_in_team))

    all_eligible_with_email = q.all()
    # Separate already-taken emails
    eligible = [p for p in all_eligible_with_email if p.email not in taken]
    already_taken_count = len(all_eligible_with_email) - len(eligible)

    # Count players without email (for note)
    no_email_q = db.query(Player).filter(
        Player.is_active == True,  # noqa: E712
        (Player.email.is_(None)) | (Player.email == ""),
        Player.user_id.is_(None),
    )
    if selected_team_id:
        no_email_q = no_email_q.filter(Player.id.in_(
            [row.player_id for row in db.query(PlayerTeam.player_id)
             .filter(PlayerTeam.team_id == selected_team_id).all()]
        ))
    no_email_count = no_email_q.count()

    return render(
        request,
        "auth/bulk_create_users.html",
        {
            "user": request.state.user,
            "teams": teams,
            "seasons": seasons,
            "selected_team_id": selected_team_id,
            "selected_season_id": selected_season_id,
            "eligible": eligible,
            "no_email_count": no_email_count,
            "already_taken_count": already_taken_count,
            "results": None,
        },
    )
```

- [ ] **Step 4: Create `templates/auth/bulk_create_users.html`**

```html
{% extends "base.html" %}
{% block title %}{{ t('users.bulk_create_title') }} — ProManager{% endblock %}
{% block breadcrumb %}
<nav class="breadcrumb">
  <a href="/dashboard">Home</a><span class="breadcrumb-sep"></span>
  <a href="/auth/users">{{ t('users.title') }}</a><span class="breadcrumb-sep"></span>
  <span>{{ t('users.bulk_create_title') }}</span>
</nav>
{% endblock %}
{% block content %}
<div style="max-width:800px;">
<div class="page-header">
  <h2>{{ t('users.bulk_create_title') }}</h2>
</div>

{% if results %}
<!-- Results view -->
<div class="alert alert-info" style="margin-bottom:1.5rem;">
  <h3>{{ t('users.results_title') }}</h3>
  <p>✅ {{ t('users.created_count').replace('{count}', results.created|string) }}</p>
  <p>⏭ {{ t('users.skipped_count').replace('{count}', results.skipped|string) }}</p>
  {% if results.email_failed %}
    <p>⚠️ {{ t('users.email_failed_count').replace('{count}', results.email_failed|length|string) }}</p>
    <ul>{% for name in results.email_failed %}<li>{{ name }}</li>{% endfor %}</ul>
  {% endif %}
</div>
<a href="/auth/users" class="btn btn-outline">{{ t('users.back_to_users') }}</a>

{% else %}
<!-- Filter row -->
<form method="get" action="/auth/users/bulk-create" class="filter-row">
  <label>{{ t('events.team') }}
    <select name="team_id" onchange="this.form.submit()">
      <option value="">{{ t('events.all_teams') }}</option>
      {% for tm in teams %}
        <option value="{{ tm.id }}" {% if selected_team_id == tm.id %}selected{% endif %}>{{ tm.name }}</option>
      {% endfor %}
    </select>
  </label>
  <label>{{ t('events.season') }}
    <select name="season_id" onchange="this.form.submit()">
      <option value="">{{ t('events.all_seasons') }}</option>
      {% for s in seasons %}
        <option value="{{ s.id }}" {% if selected_season_id == s.id %}selected{% endif %}>{{ s.name }}</option>
      {% endfor %}
    </select>
  </label>
</form>

{% if no_email_count > 0 %}
<p class="text-muted" style="font-size:.88rem;">
  ⚠️ {{ t('users.no_email_note').replace('{count}', no_email_count|string) }}
</p>
{% endif %}

{% if eligible %}
<form method="post" action="/auth/users/bulk-create">
  <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
  {% if selected_team_id %}<input type="hidden" name="team_id" value="{{ selected_team_id }}">{% endif %}
  {% if selected_season_id %}<input type="hidden" name="season_id" value="{{ selected_season_id }}">{% endif %}

  <div class="table-responsive" style="margin-bottom:1rem;">
  <table>
    <thead><tr>
      <th style="width:2.5rem;"><input type="checkbox" id="select-all" title="{{ t('users.select_all') }}"></th>
      <th>{{ t('players.name') }}</th>
      <th>{{ t('users.email') }}</th>
    </tr></thead>
    <tbody>
    {% for p in eligible %}
    <tr>
      <td><input type="checkbox" name="player_ids" value="{{ p.id }}" class="player-cb" checked></td>
      <td>{{ p.full_name }}</td>
      <td>{{ p.email }}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>

  <label style="display:flex;align-items:center;gap:.75rem;margin-bottom:1rem;">
    {{ t('users.role_label') }}
    <select name="role" style="width:auto;margin:0;">
      <option value="member">Member</option>
      <option value="coach">Coach</option>
    </select>
  </label>

  <button type="submit" class="btn btn-primary">{{ t('users.submit_bulk') }}</button>
  <a href="/auth/users" class="btn btn-outline" style="margin-left:.5rem;">{{ t('common.cancel') }}</a>
</form>

{% else %}
<p>{{ t('players.no_players') }}</p>
<a href="/auth/users" class="btn btn-outline">{{ t('users.back_to_users') }}</a>
{% endif %}
{% endif %}
</div>
{% endblock %}
{% block scripts %}
<script>
var selectAll = document.getElementById('select-all');
if (selectAll) {
  selectAll.addEventListener('change', function () {
    document.querySelectorAll('.player-cb').forEach(function (cb) {
      cb.checked = selectAll.checked;
    });
  });
}
</script>
{% endblock %}
```

- [ ] **Step 5: Run GET tests**

```bash
pytest tests/test_users.py -k "bulk_create_get" -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add routes/users.py templates/auth/bulk_create_users.html
git commit -m "feat: bulk-create GET route and template"
```

---

## Task 6: Bulk-Create POST Route + Tests

**Files:**
- Modify: `routes/users.py`
- Modify: `tests/test_users.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_users.py`:

```python
# ---------------------------------------------------------------------------
# Bulk create — POST
# ---------------------------------------------------------------------------

def test_bulk_create_post_creates_users(admin_client, db):
    from models.player import Player
    from unittest.mock import patch
    p = Player(first_name="Ivy", last_name="Test", is_active=True, email="ivy@test.com")
    db.add(p)
    db.commit()

    with patch("services.email_service.send_email", return_value=True):
        resp = admin_client.post(
            "/auth/users/bulk-create",
            data={"player_ids": str(p.id), "role": "member", "csrf_token": "test"},
            follow_redirects=False,
        )
    assert resp.status_code == 200  # re-render with results
    assert b"1" in resp.content  # created count

    db.expire_all()
    p_fresh = db.get(Player, p.id)
    assert p_fresh.user_id is not None
    u = db.get(User, p_fresh.user_id)
    assert u.email == "ivy@test.com"
    assert u.role == "member"


def test_bulk_create_post_skips_already_linked(admin_client, db):
    from models.player import Player
    from unittest.mock import patch
    existing_user = _make_user(db, "jack@test.com", "jack@test.com")
    p = Player(first_name="Jack", last_name="Test", is_active=True,
               email="jack@test.com", user_id=existing_user.id)
    db.add(p)
    db.commit()

    with patch("services.email_service.send_email", return_value=True):
        resp = admin_client.post(
            "/auth/users/bulk-create",
            data={"player_ids": str(p.id), "role": "member", "csrf_token": "test"},
        )
    assert resp.status_code == 200
    # No new user created — count stays same
    assert db.query(User).count() == 2  # admin + existing_user


def test_bulk_create_post_skips_existing_email(admin_client, db):
    from models.player import Player
    from unittest.mock import patch
    # User with same email already exists but player not linked
    _make_user(db, "kate@test.com", "kate@test.com")
    p = Player(first_name="Kate", last_name="Test", is_active=True, email="kate@test.com")
    db.add(p)
    db.commit()

    with patch("services.email_service.send_email", return_value=True):
        resp = admin_client.post(
            "/auth/users/bulk-create",
            data={"player_ids": str(p.id), "role": "member", "csrf_token": "test"},
        )
    assert resp.status_code == 200
    db.expire_all()
    assert db.get(Player, p.id).user_id is None  # not linked
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_users.py -k "bulk_create_post" -v
```

Expected: 404 or 405 — POST route doesn't exist.

- [ ] **Step 3: Add bulk-create POST route to `routes/users.py`**

Add these imports at the top:
```python
import secrets
from fastapi import Form
from services.auth_service import hash_password
from services import email_service
```

Add the POST route (place it immediately after the GET `/bulk-create` route, still before `/{user_id}/...` routes):

```python
@router.post("/bulk-create", dependencies=[Depends(require_admin), Depends(require_csrf)])
async def bulk_create_post(
    request: Request,
    db: Session = Depends(get_db),
    player_ids: list[int] = Form(default=[]),
    role: str = Form(default="member"),
):
    if role not in ("admin", "coach", "member"):
        role = "member"

    created = 0
    skipped = 0
    email_failed: list[str] = []

    for pid in player_ids:
        player = db.get(Player, pid)
        if player is None:
            skipped += 1
            continue
        # Skip if already linked
        if player.user_id is not None:
            skipped += 1
            continue
        # Skip if no email
        if not player.email:
            skipped += 1
            continue
        # Skip if email already used as username or email on another User
        existing = db.query(User).filter(
            (User.username == player.email) | (User.email == player.email)
        ).first()
        if existing:
            skipped += 1
            continue

        # Create user
        pw = secrets.token_urlsafe(12)
        new_user = User(
            username=player.email,
            email=player.email,
            hashed_password=hash_password(pw),
            role=role,
        )
        db.add(new_user)
        db.flush()  # get new_user.id
        player.user_id = new_user.id
        db.commit()

        # Send welcome email
        sent = email_service.send_email(
            to=player.email,
            subject="Your ProManager account",
            body_html=f"<p>Your account has been created.<br>Username: <strong>{player.email}</strong><br>Password: <strong>{pw}</strong></p>",
            body_text=f"Your account has been created.\nUsername: {player.email}\nPassword: {pw}",
        )
        if sent:
            created += 1
        else:
            email_failed.append(player.full_name)
            created += 1  # account created even if email failed

    teams = db.query(Team).order_by(Team.name).all()
    seasons = db.query(Season).order_by(Season.name).all()

    return render(
        request,
        "auth/bulk_create_users.html",
        {
            "user": request.state.user,
            "teams": teams,
            "seasons": seasons,
            "selected_team_id": None,
            "selected_season_id": None,
            "eligible": [],
            "no_email_count": 0,
            "already_taken_count": 0,
            "results": {
                "created": created,
                "skipped": skipped,
                "email_failed": email_failed,
            },
        },
    )
```

- [ ] **Step 4: Run all bulk-create tests**

```bash
pytest tests/test_users.py -k "bulk_create" -v
```

Expected: all PASS.

- [ ] **Step 5: Run full test suite**

```bash
pytest -v --tb=short
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add routes/users.py tests/test_users.py
git commit -m "feat: bulk-create POST route — creates users from players and sends email"
```

---

## Task 7: Final wiring + push

**Files:**
- No new files — verify everything is wired

- [ ] **Step 1: Verify router is registered**

Open `app/main.py` and confirm the `_routers` list contains:
```python
("routes.users", "/auth/users", "users"),
```

If missing, add it after `("routes.reports", "/reports", "reports")`.

- [ ] **Step 2: Run full test suite**

```bash
pytest -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 3: Commit and push**

```bash
git add -u
git push
```
