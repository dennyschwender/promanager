# Team / Season / Player Membership Refactor — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple teams from seasons and move season context into `PlayerTeam`, so a player's membership is always a `(player, team, season)` triple.

**Architecture:** Remove `season_id` from `Team`; add `season_id` (NOT NULL) to `PlayerTeam` with a new composite PK `(player_id, team_id, season_id)`. All roster queries are season-scoped. A "copy roster" endpoint lets admins duplicate memberships across seasons.

**Tech Stack:** FastAPI, SQLAlchemy 2.x (Mapped/mapped_column style), Alembic + `batch_alter_table` (SQLite), Jinja2 templates, pytest + httpx TestClient.

**Spec:** `docs/superpowers/specs/2026-03-16-team-season-player-refactor-design.md`

---

## Chunk 1: Models

### Task 1: Update `PlayerTeam` model

**Files:**
- Modify: `models/player_team.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_players.py`:

```python
def test_player_team_has_season_id(db):
    from models.season import Season
    from models.team import Team
    from models.player import Player
    from models.player_team import PlayerTeam

    season = Season(name="2025/26", is_active=True)
    team = Team(name="U21")
    player = Player(first_name="Anna", last_name="Test", is_active=True)
    db.add_all([season, team, player])
    db.flush()

    pt = PlayerTeam(player_id=player.id, team_id=team.id, season_id=season.id, priority=1)
    db.add(pt)
    db.commit()
    db.refresh(pt)

    assert pt.season_id == season.id
    assert pt.season is not None
    assert pt.season.name == "2025/26"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_players.py::test_player_team_has_season_id -v
```
Expected: FAIL — `PlayerTeam` has no `season_id` attribute.

- [ ] **Step 3: Update `models/player_team.py`**

Replace the entire file with:

```python
"""models/player_team.py — Player ↔ Team many-to-many association with priority,
role, position, shirt number, membership status, and season scope."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PlayerTeam(Base):
    __tablename__ = "player_teams"
    # No separate UniqueConstraint needed — composite PK already enforces uniqueness.

    player_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("players.id", ondelete="CASCADE"), primary_key=True
    )
    team_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True
    )
    season_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("seasons.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    # 1 = highest priority; higher numbers = lower priority
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ── Per-team role & position ──────────────────────────────────────
    # "player" | "coach" | "assistant" | "team_leader"
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="player")
    # "goalie" | "defender" | "center" | "forward" | None
    position: Mapped[str | None] = mapped_column(String(32), nullable=True)
    shirt_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Membership status ──────────────────────────────────────────
    # "active" | "inactive" | "injured"
    membership_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active"
    )
    injured_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    # When True the player is absent by default for this team's events in this season.
    absent_by_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # ── Relationships ──────────────────────────────────────────────────────
    player: Mapped[Player] = relationship("Player", back_populates="team_memberships")
    team: Mapped[Team] = relationship("Team", back_populates="player_memberships")
    season: Mapped[Season] = relationship("Season", back_populates="player_memberships")

    def __repr__(self) -> str:
        return (
            f"<PlayerTeam player_id={self.player_id} "
            f"team_id={self.team_id} season_id={self.season_id} priority={self.priority}>"
        )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_players.py::test_player_team_has_season_id -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add models/player_team.py tests/test_players.py
git commit -m "feat: add season_id to PlayerTeam model (composite PK)"
```

---

### Task 2: Update `Team` model — remove `season_id`

**Files:**
- Modify: `models/team.py`
- Modify: `tests/test_teams.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_teams.py`:

```python
def test_team_has_no_season_id(db):
    from models.team import Team
    team = Team(name="U21")
    db.add(team)
    db.commit()
    db.refresh(team)
    assert not hasattr(team, "season_id") or team.__class__.__table__.columns.get("season_id") is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_teams.py::test_team_has_no_season_id -v
```
Expected: FAIL — `season_id` column still exists.

- [ ] **Step 3: Update `models/team.py`**

Replace the entire file with:

```python
"""models/team.py — Team model (season-independent)."""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # ── Relationships ──────────────────────────────────────────────────────
    player_memberships: Mapped[list[PlayerTeam]] = relationship(
        "PlayerTeam",
        back_populates="team",
        cascade="all, delete-orphan",
        lazy="select",
    )
    events: Mapped[list[Event]] = relationship(
        "Event", back_populates="team", lazy="select"
    )
    recurring_schedules: Mapped[list["TeamRecurringSchedule"]] = relationship(  # type: ignore[name-defined]
        "TeamRecurringSchedule",
        back_populates="team",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Team id={self.id} name={self.name!r}>"
```

> Note: `players` (direct `Player` relationship via legacy `team_id`) is removed. `season` relationship is removed.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_teams.py::test_team_has_no_season_id -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add models/team.py tests/test_teams.py
git commit -m "feat: remove season_id from Team model"
```

---

### Task 3: Update `Season` model and `Player` model

**Files:**
- Modify: `models/season.py`
- Modify: `models/player.py`

- [ ] **Step 1: Update `models/season.py`**

Replace the entire file with:

```python
"""models/season.py — Season model."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Season(Base):
    __tablename__ = "seasons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── Relationships ──────────────────────────────────────────────────────
    player_memberships: Mapped[list[PlayerTeam]] = relationship(
        "PlayerTeam", back_populates="season", lazy="select"
    )
    events: Mapped[list[Event]] = relationship(
        "Event", back_populates="season", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Season id={self.id} name={self.name!r} active={self.is_active}>"
```

> Note: `teams` relationship (via `Team.season_id`) is replaced by `player_memberships` (via `PlayerTeam.season_id`).

- [ ] **Step 2: Update `models/player.py`** — remove the `teams` property (it returns cross-season data without filtering)

In `models/player.py`, remove lines 92–95:
```python
    @property
    def teams(self) -> list:
        """Ordered list of Team objects (by priority ascending)."""
        return [m.team for m in self.team_memberships if m.team is not None]
```

Remove **only** these three lines (lines 43–45 in the original file) — leave all other relationships untouched:
```python
    team: Mapped[Team | None] = relationship(
        "Team", back_populates="players", lazy="select"
    )
```

> `team_id` column stays. `full_name` property stays. `teams` property is removed (lines 92–95). All other relationships (`team_memberships`, `phones`, `contact`, `user`, `attendances`, `notifications`, `notification_preferences`, `web_push_subscriptions`) are unchanged.

- [ ] **Step 3: Run the full test suite**

```bash
pytest -v
```
Expected: All existing tests pass. (Tests that reference `player.teams` or `team.season` will fail — fix those in the test files now.)

Fix `tests/test_players.py`: the `test_players_filter_by_team` test creates a `PlayerTeam` without `season_id` — it needs a season. Update it:

```python
def test_players_filter_by_team(admin_client, db):
    from models.season import Season
    season = Season(name="2025/26", is_active=True)
    team = Team(name="FilterTeam")
    db.add_all([season, team])
    db.commit()
    db.refresh(season)
    db.refresh(team)

    p1 = Player(first_name="Eve", last_name="InTeam", is_active=True)
    p2 = Player(first_name="Frank", last_name="NoTeam", is_active=True)
    db.add_all([p1, p2])
    db.flush()
    db.add(PlayerTeam(player_id=p1.id, team_id=team.id, season_id=season.id, priority=1))
    db.commit()

    resp = admin_client.get(f"/players?team_id={team.id}", follow_redirects=False)
    assert resp.status_code == 200
    assert b"Eve" in resp.content
    assert b"Frank" not in resp.content
```

Also remove `season_id` from `test_create_team` and `test_create_team_blank_name` form data in `tests/test_teams.py`.

```bash
pytest -v
```
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add models/season.py models/player.py tests/test_players.py tests/test_teams.py
git commit -m "feat: update Season and Player models for season-scoped memberships"
```

---

## Chunk 2: Alembic Migration

### Task 4: Write the Alembic migration

**Files:**
- Create: `alembic/versions/<timestamp>_season_scoped_player_teams.py`

- [ ] **Step 1: Generate the migration file**

```bash
source .venv/bin/activate
alembic revision --autogenerate -m "season_scoped_player_teams"
```

This creates a file in `alembic/versions/`. Open it — autogenerate will be wrong for SQLite (it can't handle PK changes). Replace its contents entirely with the manual migration below.

- [ ] **Step 2: Write the migration manually**

Replace the generated file's `upgrade()` and `downgrade()` with:

```python
"""season_scoped_player_teams

Revision ID: <keep the autogenerated ID>
Revises: a1b2c3d4e5f6
Create Date: <keep autogenerated date>
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '<keep autogenerated>'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def _get_active_season_id(conn) -> int:
    """Return the id of the single active season. Raises RuntimeError if 0 or 2+."""
    result = conn.execute(
        sa.text("SELECT id FROM seasons WHERE is_active = 1")
    ).fetchall()
    if len(result) == 0:
        raise RuntimeError(
            "Migration aborted: no active season found. "
            "Activate exactly one season before running this migration."
        )
    if len(result) > 1:
        raise RuntimeError(
            f"Migration aborted: {len(result)} active seasons found. "
            "Exactly one season must be active before running this migration."
        )
    return result[0][0]


def upgrade() -> None:
    conn = op.get_bind()

    # Pre-flight: exactly one active season must exist
    active_season_id = _get_active_season_id(conn)

    # ── Step 1: Add season_id to player_teams (nullable for now) ──────────────
    with op.batch_alter_table("player_teams") as batch_op:
        batch_op.add_column(sa.Column("season_id", sa.Integer(), nullable=True))

    # ── Step 2: Populate season_id for all existing rows ──────────────────────
    conn.execute(
        sa.text("UPDATE player_teams SET season_id = :sid"),
        {"sid": active_season_id},
    )

    # ── Step 3: Rebuild player_teams with new PK and NOT NULL season_id ───────
    # `recreate="always"` forces Alembic to fully rebuild the table on SQLite,
    # which is required to change the composite primary key.
    with op.batch_alter_table("player_teams", recreate="always") as batch_op:
        # Drop old unique constraint (it will be replaced by the new PK)
        batch_op.drop_constraint("uq_player_team", type_="unique")
        batch_op.alter_column("season_id", nullable=False)
        batch_op.create_foreign_key(
            "fk_player_teams_season_id",
            "seasons",
            ["season_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_player_teams_season_id", ["season_id"])
    # The new composite PK (player_id, team_id, season_id) is picked up from
    # the model metadata during the recreate="always" table rebuild.

    # ── Step 4: Remove season_id from teams ───────────────────────────────────
    # On SQLite, batch_alter_table with recreate="always" handles implicit FK
    # removal — no explicit drop_constraint needed (unnamed FKs are not tracked).
    with op.batch_alter_table("teams", recreate="always") as batch_op:
        batch_op.drop_index("ix_teams_season_id")
        batch_op.drop_column("season_id")


def downgrade() -> None:
    raise NotImplementedError(
        "This migration is intentionally irreversible. "
        "The season_id data on teams has been permanently removed. "
        "Restore from a database backup to revert."
    )
```

> **Important:** The `revision` and `down_revision` values must match your actual generated IDs. The `down_revision` should point to `a1b2c3d4e5f6` (the current head).

- [ ] **Step 3: Verify the migration runs (on a copy first)**

```bash
# On the dev SQLite database (make a backup first)
cp data/proManager.db data/proManager.db.bak
alembic upgrade head
```

Expected: Migration completes without error. Check:
```bash
sqlite3 data/proManager.db ".schema player_teams"
```
Expected output shows `season_id` column and no `season_id` in `.schema teams`.

- [ ] **Step 4: Run the full test suite**

```bash
pytest -v
```

> Note: Tests use an in-memory SQLite DB rebuilt from `Base.metadata` — the migration does not run during tests. The model changes from Tasks 1–3 define the schema for tests.

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "feat: alembic migration — season-scoped player_teams, remove team.season_id"
```

---

## Chunk 3: Routes

### Task 5: Update `routes/teams.py` — remove season_id

**Files:**
- Modify: `routes/teams.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_teams.py`:

```python
def test_create_team_does_not_accept_season_id(admin_client, db):
    """After refactor, teams have no season_id field."""
    from models.team import Team
    resp = admin_client.post(
        "/teams/new",
        data={"name": "NoSeasonTeam", "description": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    team = db.query(Team).filter(Team.name == "NoSeasonTeam").first()
    assert team is not None
    assert not hasattr(team, "season_id")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_teams.py::test_create_team_does_not_accept_season_id -v
```
Expected: FAIL — `season_id` Form param causes a 422 or is stored.

- [ ] **Step 3: Update `routes/teams.py`**

Make these targeted changes:

1. Remove `from models.season import Season` import. After editing, verify no remaining references:
```bash
grep -n "Season" routes/teams.py
```
Expected: zero results.

2. In `team_new_get` — remove `seasons = db.query(Season)...` and remove `"seasons": seasons` from context. Change context to:
```python
return render(request, "teams/form.html", {
    "user": user,
    "team": None,
    "error": None,
    "schedule_rows": [],
    "saved": False,
    "confirm_mode": False,
    "flagged": [],
    "_schedules_json": "",
})
```

3. In `team_new_post` — remove `season_id: str = Form("")` parameter. Remove `sid = int(season_id)...` line. Remove `season_id=sid` from `Team(...)` constructor. Remove `seasons = db.query(Season)...` from error path context. Remove `"seasons": seasons` from error context.

4. In `team_edit_get` — remove `seasons = db.query(Season)...` and `"seasons": seasons` from context.

5. In `team_edit_post` — remove `season_id: str = Form("")` parameter. Remove all references to `season_id`, `old_season_id`, `team.season_id`, `season_changed`. Remove `seasons = db.query(Season)...` and `"seasons": seasons` from `_render` inner function.

- [ ] **Step 4: Run test**

```bash
pytest tests/test_teams.py -v
```
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add routes/teams.py tests/test_teams.py
git commit -m "feat: remove season_id from teams route and forms"
```

---

### Task 6: Update `routes/players.py` — season-scoped memberships

**Files:**
- Modify: `routes/players.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_players.py`:

```python
def test_players_list_filters_by_active_season(admin_client, db):
    """Player list defaults to active season — only shows players in that season."""
    from models.season import Season
    from models.team import Team
    from models.player import Player
    from models.player_team import PlayerTeam

    s1 = Season(name="2024/25", is_active=False)
    s2 = Season(name="2025/26", is_active=True)
    team = Team(name="U21")
    db.add_all([s1, s2, team])
    db.flush()

    p1 = Player(first_name="InActive", last_name="Season", is_active=True)
    p2 = Player(first_name="InCurrent", last_name="Season", is_active=True)
    db.add_all([p1, p2])
    db.flush()

    db.add(PlayerTeam(player_id=p1.id, team_id=team.id, season_id=s1.id, priority=1))
    db.add(PlayerTeam(player_id=p2.id, team_id=team.id, season_id=s2.id, priority=1))
    db.commit()

    # Request with active season filter (default)
    resp = admin_client.get(f"/players?season_id={s2.id}&team_id={team.id}", follow_redirects=False)
    assert resp.status_code == 200
    assert b"InCurrent" in resp.content
    assert b"InActive" not in resp.content


def test_sync_memberships_only_touches_target_season(db):
    """Editing a player in season A must not delete their season B membership."""
    from models.season import Season
    from models.team import Team
    from models.player_team import PlayerTeam
    from routes.players import _sync_memberships

    s1 = Season(name="2024/25", is_active=False)
    s2 = Season(name="2025/26", is_active=True)
    team = Team(name="U21")
    db.add_all([s1, s2, team])
    db.flush()

    player = Player(first_name="Multi", last_name="Season", is_active=True)
    db.add(player)
    db.flush()

    # Player has memberships in both seasons
    db.add(PlayerTeam(player_id=player.id, team_id=team.id, season_id=s1.id, priority=1))
    db.add(PlayerTeam(player_id=player.id, team_id=team.id, season_id=s2.id, priority=1))
    db.commit()

    # Sync memberships for season 2 only (e.g., player removed from team in s2)
    _sync_memberships(db, player, [], season_id=s2.id)
    db.commit()

    remaining = db.query(PlayerTeam).filter(PlayerTeam.player_id == player.id).all()
    assert len(remaining) == 1
    assert remaining[0].season_id == s1.id  # s1 membership untouched
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_players.py::test_players_list_filters_by_active_season tests/test_players.py::test_sync_memberships_only_touches_target_season -v
```
Expected: Both FAIL.

- [ ] **Step 3: Update `routes/players.py`**

**3a. Update `_sync_memberships` signature** — add `season_id: int` parameter and scope the delete:

```python
def _sync_memberships(
    db: Session,
    player: Player,
    memberships: list[tuple[int, int, dict]],
    season_id: int,
) -> None:
    """Replace PlayerTeam rows for *player* in *season* with *memberships*.

    Memberships from other seasons are untouched.
    """
    db.query(PlayerTeam).filter(
        PlayerTeam.player_id == player.id,
        PlayerTeam.season_id == season_id,
    ).delete()
    for team_id, priority, extra in memberships:
        db.add(PlayerTeam(
            player_id=player.id,
            team_id=team_id,
            season_id=season_id,
            priority=priority,
            role=extra.get("role", "player") or "player",
            position=extra.get("position"),
            shirt_number=extra.get("shirt_number"),
            membership_status=extra.get("membership_status", "active") or "active",
            injured_until=extra.get("injured_until"),
            absent_by_default=bool(extra.get("absent_by_default", False)),
        ))
```

**3b. Add `Season` import** at top of file:
```python
from models.season import Season
```

**3c. Add helper to resolve active season id:**
```python
def _active_season_id(db: Session) -> int | None:
    season = db.query(Season).filter(Season.is_active == True).first()  # noqa: E712
    return season.id if season else None
```

**3d. Update `players_list`** — add `season_id` query param, filter memberships:

```python
@router.get("")
@router.get("/")
async def players_list(
    request: Request,
    team_id: int | None = None,
    season_id: int | None = None,
    user: User = Depends(require_login),
    db: Session = Depends(get_db),
):
    seasons = db.query(Season).order_by(Season.name).all()
    selected_season_id = season_id or _active_season_id(db)

    q = db.query(Player)
    if team_id is not None and selected_season_id is not None:
        q = (
            q.join(PlayerTeam, Player.id == PlayerTeam.player_id)
            .filter(PlayerTeam.team_id == team_id, PlayerTeam.season_id == selected_season_id)
        )
    elif team_id is not None:
        q = (
            q.join(PlayerTeam, Player.id == PlayerTeam.player_id)
            .filter(PlayerTeam.team_id == team_id)
        )
    players = q.order_by(Player.last_name, Player.first_name).all()
    teams = db.query(Team).order_by(Team.name).all()

    return render(request, "players/list.html", {
        "user": user,
        "players": players,
        "teams": teams,
        "seasons": seasons,
        "selected_team_id": team_id,
        "selected_season_id": selected_season_id,
    })
```

**3e. Update `player_new_get`** — pass seasons + selected_season_id:

```python
@router.get("/new")
async def player_new_get(
    request: Request,
    season_id: int | None = None,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    teams = db.query(Team).order_by(Team.name).all()
    users = db.query(User).order_by(User.username).all()
    seasons = db.query(Season).order_by(Season.name).all()
    selected_season_id = season_id or _active_season_id(db)
    return render(request, "players/form.html", {
        "user": user,
        "player": None,
        "teams": teams,
        "users": users,
        "seasons": seasons,
        "selected_season_id": selected_season_id,
        "memberships": {},
        "error": None,
    })
```

**3f. Update `player_new_post`** — read `season_id` from form, pass to `_sync_memberships`:

```python
@router.post("/new")
async def player_new_post(
    request: Request,
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    form = await request.form()
    first_name = (form.get("first_name") or "").strip()
    last_name  = (form.get("last_name")  or "").strip()
    email      = (form.get("email")      or "").strip()
    phone      = (form.get("phone")      or "").strip()
    user_id_s  = (form.get("user_id")    or "").strip()
    season_id_s = (form.get("season_id") or "").strip()

    teams = db.query(Team).order_by(Team.name).all()
    users = db.query(User).order_by(User.username).all()
    seasons = db.query(Season).order_by(Season.name).all()
    selected_season_id = int(season_id_s) if season_id_s else _active_season_id(db)

    if not first_name or not last_name:
        return render(request, "players/form.html", {
            "user": user,
            "player": None,
            "teams": teams,
            "users": users,
            "seasons": seasons,
            "selected_season_id": selected_season_id,
            "memberships": {},
            "error": "First name and last name are required.",
        }, status_code=400)

    player = Player(
        first_name=first_name,
        last_name=last_name,
        email=email or None,
        phone=phone or None,
        user_id=int(user_id_s) if user_id_s else None,
        is_active=True,
    )
    _apply_personal_fields(player, form)
    db.add(player)
    db.flush()

    if selected_season_id is not None:
        memberships = _parse_team_memberships(form)
        _sync_memberships(db, player, memberships, season_id=selected_season_id)
    _sync_phones(db, player, form)
    _sync_contact(db, player, form)

    db.commit()
    return RedirectResponse("/players", status_code=302)
```

**3g. Update `player_edit_get`** — pass seasons + selected_season_id + season-scoped memberships:

```python
@router.get("/{player_id}/edit")
async def player_edit_get(
    player_id: int,
    request: Request,
    season_id: int | None = None,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    player = db.get(Player, player_id)
    if player is None:
        return RedirectResponse("/players", status_code=302)

    teams = db.query(Team).order_by(Team.name).all()
    users = db.query(User).order_by(User.username).all()
    seasons = db.query(Season).order_by(Season.name).all()
    selected_season_id = season_id or _active_season_id(db)
    memberships = _memberships_dict(player, selected_season_id)
    return render(request, "players/form.html", {
        "user": user,
        "player": player,
        "teams": teams,
        "users": users,
        "seasons": seasons,
        "selected_season_id": selected_season_id,
        "memberships": memberships,
        "error": None,
    })
```

**3h. Update `_memberships_dict`** — filter by season:

```python
def _memberships_dict(player: Player, season_id: int | None) -> dict:
    """Return {team_id: PlayerTeam} for pre-filling the edit form, scoped to season."""
    if season_id is None:
        return {}
    return {
        m.team_id: m
        for m in player.team_memberships
        if m.season_id == season_id
    }
```

**3i. Update `player_edit_post`** — read `season_id` from form, pass to `_sync_memberships`:

```python
@router.post("/{player_id}/edit")
async def player_edit_post(
    player_id: int,
    request: Request,
    user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    player = db.get(Player, player_id)
    if player is None:
        return RedirectResponse("/players", status_code=302)

    form = await request.form()
    first_name = (form.get("first_name") or "").strip()
    last_name  = (form.get("last_name")  or "").strip()
    email      = (form.get("email")      or "").strip()
    phone      = (form.get("phone")      or "").strip()
    user_id_s  = (form.get("user_id")    or "").strip()
    is_active  = (form.get("is_active")  or "")
    season_id_s = (form.get("season_id") or "").strip()

    teams = db.query(Team).order_by(Team.name).all()
    users = db.query(User).order_by(User.username).all()
    seasons = db.query(Season).order_by(Season.name).all()
    selected_season_id = int(season_id_s) if season_id_s else _active_season_id(db)

    if not first_name or not last_name:
        return render(request, "players/form.html", {
            "user": user,
            "player": player,
            "teams": teams,
            "users": users,
            "seasons": seasons,
            "selected_season_id": selected_season_id,
            "memberships": _memberships_dict(player, selected_season_id),
            "error": "First name and last name are required.",
        }, status_code=400)

    player.first_name = first_name
    player.last_name  = last_name
    player.email      = email or None
    player.phone      = phone or None
    player.user_id    = int(user_id_s) if user_id_s else None
    player.is_active  = is_active in ("on", "true", "1", "yes")
    _apply_personal_fields(player, form)

    if selected_season_id is not None:
        _sync_memberships(db, player, _parse_team_memberships(form), season_id=selected_season_id)
    _sync_phones(db, player, form)
    _sync_contact(db, player, form)

    db.add(player)
    db.commit()
    return RedirectResponse(f"/players/{player_id}", status_code=302)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_players.py -v
```
Expected: All pass including the two new tests.

- [ ] **Step 5: Commit**

```bash
git add routes/players.py tests/test_players.py
git commit -m "feat: season-scope player memberships in players route"
```

---

### Task 7: Add copy-roster endpoint to `routes/seasons.py`

**Files:**
- Modify: `routes/seasons.py`
- Modify: `tests/test_seasons.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_seasons.py`:

```python
def test_copy_roster(admin_client, db):
    """Copy-roster duplicates PlayerTeam rows from source to target season."""
    from models.team import Team
    from models.player import Player
    from models.player_team import PlayerTeam

    s1 = Season(name="2024/25", is_active=False)
    s2 = Season(name="2025/26", is_active=True)
    team = Team(name="U21")
    db.add_all([s1, s2, team])
    db.flush()

    player = Player(first_name="Copy", last_name="Test", is_active=True)
    db.add(player)
    db.flush()

    db.add(PlayerTeam(
        player_id=player.id, team_id=team.id, season_id=s1.id,
        priority=1, role="player", injured_until=None, absent_by_default=False,
    ))
    db.commit()

    resp = admin_client.post(
        f"/seasons/{s2.id}/copy-roster",
        data={"source_season_id": str(s1.id)},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    copied = db.query(PlayerTeam).filter(
        PlayerTeam.player_id == player.id,
        PlayerTeam.season_id == s2.id,
    ).first()
    assert copied is not None
    assert copied.priority == 1
    assert copied.role == "player"


def test_copy_roster_resets_injury_fields(admin_client, db):
    """Copy-roster resets injured_until and absent_by_default on copied rows."""
    from datetime import date
    from models.team import Team
    from models.player import Player
    from models.player_team import PlayerTeam

    s1 = Season(name="2024/25", is_active=False)
    s2 = Season(name="2025/26", is_active=True)
    team = Team(name="U21")
    db.add_all([s1, s2, team])
    db.flush()

    player = Player(first_name="Injured", last_name="Player", is_active=True)
    db.add(player)
    db.flush()

    db.add(PlayerTeam(
        player_id=player.id, team_id=team.id, season_id=s1.id,
        priority=1, injured_until=date(2025, 3, 1), absent_by_default=True,
    ))
    db.commit()

    admin_client.post(
        f"/seasons/{s2.id}/copy-roster",
        data={"source_season_id": str(s1.id)},
        follow_redirects=False,
    )

    copied = db.query(PlayerTeam).filter(
        PlayerTeam.season_id == s2.id
    ).first()
    assert copied.injured_until is None
    assert copied.absent_by_default is False


def test_copy_roster_skips_duplicates(admin_client, db):
    """Copy-roster is idempotent — running twice doesn't duplicate rows."""
    from models.team import Team
    from models.player import Player
    from models.player_team import PlayerTeam

    s1 = Season(name="2024/25", is_active=False)
    s2 = Season(name="2025/26", is_active=True)
    team = Team(name="U21")
    db.add_all([s1, s2, team])
    db.flush()

    player = Player(first_name="Dupe", last_name="Test", is_active=True)
    db.add(player)
    db.flush()
    db.add(PlayerTeam(player_id=player.id, team_id=team.id, season_id=s1.id, priority=1))
    db.commit()

    resp1 = admin_client.post(f"/seasons/{s2.id}/copy-roster", data={"source_season_id": str(s1.id)}, follow_redirects=False)
    resp2 = admin_client.post(f"/seasons/{s2.id}/copy-roster", data={"source_season_id": str(s1.id)}, follow_redirects=False)
    assert resp1.status_code == 302
    assert resp2.status_code == 302

    count = db.query(PlayerTeam).filter(PlayerTeam.season_id == s2.id).count()
    assert count == 1


def test_copy_roster_self_copy_returns_400(admin_client, db):
    """copy-roster with source == target returns 400."""
    season = Season(name="2025/26", is_active=True)
    db.add(season)
    db.commit()
    db.refresh(season)

    resp = admin_client.post(
        f"/seasons/{season.id}/copy-roster",
        data={"source_season_id": str(season.id)},
        follow_redirects=False,
    )
    assert resp.status_code == 400


def test_copy_roster_empty_source_returns_zero(admin_client, db):
    """Copy-roster with an empty source season returns 302 and copies 0 rows."""
    s1 = Season(name="2024/25", is_active=False)
    s2 = Season(name="2025/26", is_active=True)
    db.add_all([s1, s2])
    db.commit()

    resp = admin_client.post(
        f"/seasons/{s2.id}/copy-roster",
        data={"source_season_id": str(s1.id)},
        follow_redirects=False,
    )
    assert resp.status_code == 302


def test_copy_roster_requires_admin(member_client, db):
    """copy-roster returns 403 for non-admin users."""
    season = Season(name="2025/26", is_active=True)
    db.add(season)
    db.commit()
    db.refresh(season)

    resp = member_client.post(
        f"/seasons/{season.id}/copy-roster",
        data={"source_season_id": "1"},
        follow_redirects=False,
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_seasons.py::test_copy_roster tests/test_seasons.py::test_copy_roster_requires_admin -v
```
Expected: FAIL — endpoint doesn't exist.

- [ ] **Step 3: Add the endpoint to `routes/seasons.py`**

Add imports at top (only if not already present):
```python
from fastapi import Form
from models.player_team import PlayerTeam
```

Add after the `season_delete` endpoint:

```python
# ---------------------------------------------------------------------------
# Copy roster
# ---------------------------------------------------------------------------


@router.post("/{season_id}/copy-roster")
async def season_copy_roster(
    season_id: int,
    request: Request,
    source_season_id: int = Form(...),
    _user: User = Depends(require_admin),
    _csrf: None = Depends(require_csrf),
    db: Session = Depends(get_db),
):
    if source_season_id == season_id:
        return render(request, "seasons/list.html", {
            "user": _user,
            "seasons": db.query(Season).order_by(Season.name).all(),
            "error": "Source and target season must be different.",
        }, status_code=400)

    target = db.get(Season, season_id)
    source = db.get(Season, source_season_id)
    if target is None or source is None:
        return RedirectResponse("/seasons", status_code=302)

    # Fetch all memberships from source season
    source_memberships = (
        db.query(PlayerTeam)
        .filter(PlayerTeam.season_id == source_season_id)
        .all()
    )

    # Find existing (player_id, team_id) pairs in target to skip duplicates
    existing = {
        (pt.player_id, pt.team_id)
        for pt in db.query(PlayerTeam).filter(PlayerTeam.season_id == season_id).all()
    }

    copied = 0
    for src in source_memberships:
        if (src.player_id, src.team_id) in existing:
            continue
        db.add(PlayerTeam(
            player_id=src.player_id,
            team_id=src.team_id,
            season_id=season_id,
            priority=src.priority,
            role=src.role,
            position=src.position,
            shirt_number=src.shirt_number,
            membership_status=src.membership_status,
            injured_until=None,        # stale from prior season — reset
            absent_by_default=False,   # stale from prior season — reset
        ))
        copied += 1

    db.commit()
    return RedirectResponse(f"/seasons?copied={copied}", status_code=302)
```

- [ ] **Step 4: Run all season tests**

```bash
pytest tests/test_seasons.py -v
```
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add routes/seasons.py tests/test_seasons.py
git commit -m "feat: add copy-roster endpoint to seasons route"
```

---

## Chunk 4: Attendance Service

### Task 8: Season-scope `ensure_attendance_records` and `_has_higher_prio_conflict`

**Files:**
- Modify: `services/attendance_service.py`
- Modify: `tests/test_attendance.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_attendance.py`:

```python
def test_ensure_attendance_only_includes_season_players(db):
    """ensure_attendance_records only creates rows for players in event's (team, season)."""
    from datetime import date
    from models.season import Season
    from models.team import Team
    from models.player_team import PlayerTeam
    from services.attendance_service import ensure_attendance_records

    s1 = Season(name="2024/25", is_active=False)
    s2 = Season(name="2025/26", is_active=True)
    team = Team(name="U21")
    db.add_all([s1, s2, team])
    db.flush()

    p1 = _make_player(db, "InSeason", "Two")
    p2 = _make_player(db, "InSeason", "One")
    db.add(PlayerTeam(player_id=p1.id, team_id=team.id, season_id=s1.id, priority=1))
    db.add(PlayerTeam(player_id=p2.id, team_id=team.id, season_id=s2.id, priority=1))
    db.commit()

    event = Event(
        title="S2 Match", event_type="match",
        event_date=date(2026, 1, 10),
        team_id=team.id, season_id=s2.id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    ensure_attendance_records(db, event)

    from models.attendance import Attendance
    att_player_ids = {a.player_id for a in db.query(Attendance).filter(Attendance.event_id == event.id).all()}
    assert p2.id in att_player_ids      # in s2 — should be included
    assert p1.id not in att_player_ids  # in s1 — should NOT be included


def test_ensure_attendance_no_season_creates_no_records(db):
    """ensure_attendance_records with event.season_id=None creates no attendance rows."""
    from datetime import date
    from models.team import Team
    from services.attendance_service import ensure_attendance_records

    team = Team(name="NoSeason")
    db.add(team)
    db.flush()

    player = _make_player(db, "NoSeason", "Player")
    db.commit()

    event = Event(
        title="No Season Event", event_type="training",
        event_date=date(2026, 2, 1),
        team_id=team.id, season_id=None,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    ensure_attendance_records(db, event)

    from models.attendance import Attendance
    count = db.query(Attendance).filter(Attendance.event_id == event.id).count()
    assert count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_attendance.py::test_ensure_attendance_only_includes_season_players tests/test_attendance.py::test_ensure_attendance_no_season_creates_no_records -v
```
Expected: Both FAIL.

- [ ] **Step 3: Update `services/attendance_service.py`**

**3a. Update `ensure_attendance_records`** — replace the memberships query:

```python
def ensure_attendance_records(db: Session, event: Event) -> None:
    """Create Attendance rows for every active player in event's (team, season).

    If event.season_id is None, no records are created (season context required).
    """
    if event.team_id is None:
        return
    if event.season_id is None:
        import logging
        logging.getLogger(__name__).warning(
            "ensure_attendance_records called with event.season_id=None "
            "(event_id=%s). No attendance records created.", event.id
        )
        return

    # Fetch players via (team_id, season_id) — season-scoped
    memberships = (
        db.query(PlayerTeam)
        .filter(
            PlayerTeam.team_id == event.team_id,
            PlayerTeam.season_id == event.season_id,
        )
        .all()
    )
    players = [
        m.player for m in memberships
        if m.player is not None and m.player.is_active
    ]

    existing_player_ids = {
        att.player_id
        for att in db.query(Attendance)
        .filter(Attendance.event_id == event.id)
        .all()
    }

    default = _default_status(event)
    new_records = []
    for player in players:
        if player.id not in existing_player_ids:
            status = default
            mem = next(
                (m for m in memberships if m.player_id == player.id), None
            )
            if status != "absent" and mem is not None and mem.absent_by_default:
                status = "absent"
            if status != "absent" and _has_higher_prio_conflict(db, player, event):
                status = "absent"
            new_records.append(
                Attendance(event_id=event.id, player_id=player.id, status=status)
            )

    if new_records:
        db.add_all(new_records)
        db.commit()
```

**3b. Update `_has_higher_prio_conflict`** — add `season_id` filter to both queries:

```python
def _has_higher_prio_conflict(db: Session, player: Player, event: Event) -> bool:
    """True if player has a higher-priority team with a conflicting event on the same date/time.

    Both PlayerTeam queries are scoped to event.season_id.
    If event.season_id is None, returns False (no conflict assumed).
    """
    if event.team_id is None:
        return False
    if event.season_id is None:
        return False

    # Query 1: player's own membership in this team for this season
    my_pt = (
        db.query(PlayerTeam)
        .filter_by(player_id=player.id, team_id=event.team_id, season_id=event.season_id)
        .first()
    )
    if my_pt is None:
        return False

    # Query 2: find all higher-priority teams for the player in this season
    higher_team_ids = [
        pt.team_id
        for pt in db.query(PlayerTeam)
        .filter(
            PlayerTeam.player_id == player.id,
            PlayerTeam.season_id == event.season_id,
            PlayerTeam.priority < my_pt.priority,
        )
        .all()
    ]
    if not higher_team_ids:
        return False

    competing = (
        db.query(Event)
        .filter(
            Event.event_date == event.event_date,
            Event.team_id.in_(higher_team_ids),
            Event.id != event.id,
        )
        .all()
    )
    for ce in competing:
        if event.event_time is None or ce.event_time is None:
            return True
        if event.event_time == ce.event_time:
            return True
    return False
```

- [ ] **Step 4: Run all tests**

```bash
pytest -v
```
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add services/attendance_service.py tests/test_attendance.py
git commit -m "feat: season-scope ensure_attendance_records and _has_higher_prio_conflict"
```

---

## Chunk 5: Templates

### Task 9: Update team templates — remove season field

**Files:**
- Modify: `templates/teams/form.html`
- Modify: `templates/teams/list.html`

- [ ] **Step 1: Update `templates/teams/form.html`**

Find and remove the `<select>` or `<input>` block for `season_id`. This is typically a `<label>` + `<select name="season_id">` block with options rendered from `seasons`. Remove the entire block.

Also remove any JavaScript that references `season_id` or the seasons dropdown.

- [ ] **Step 2: Update `templates/teams/list.html`**

Find and remove the table column that shows `t.season.name` or `t.season`. This includes:
- The `<th>` header for the season column
- The `<td>` cell with `{{ t.season.name if t.season else "-" }}` or similar

- [ ] **Step 3: Run a smoke test**

```bash
pytest tests/test_teams.py -v
```
Expected: All pass (templates render without errors in tests via `resp.content`).

- [ ] **Step 4: Commit**

```bash
git add templates/teams/
git commit -m "feat: remove season field from team templates"
```

---

### Task 10: Update player templates — add season selector

**Files:**
- Modify: `templates/players/list.html`
- Modify: `templates/players/form.html`

- [ ] **Step 1: Update `templates/players/list.html`**

Add a season selector form above the player table. The form submits GET to `/players` with `season_id` and optionally `team_id`:

```html
<form method="get" action="/players">
  <label for="season_filter">{{ t("players.season_label") }}</label>
  <select id="season_filter" name="season_id" onchange="this.form.submit()">
    {% for s in seasons %}
      <option value="{{ s.id }}" {% if s.id == selected_season_id %}selected{% endif %}>
        {{ s.name }}{% if s.is_active %} ✓{% endif %}
      </option>
    {% endfor %}
  </select>
  {% if selected_team_id %}
    <input type="hidden" name="team_id" value="{{ selected_team_id }}">
  {% endif %}
  {% if not seasons %}
    <span class="text-muted">{{ t("players.no_seasons") }}</span>
  {% endif %}
</form>
```

- [ ] **Step 2: Update `templates/players/form.html`**

Add a season selector at the top of the form (hidden input if only one option, dropdown if multiple). Add a `<select name="season_id">` element and pass it the current `selected_season_id`.

Add a banner if `selected_season_id is None`:

```html
{% if selected_season_id is none %}
  <div class="notice">{{ t("players.no_active_season") }}</div>
{% endif %}
```

Make the team assignment table only editable when `selected_season_id` is set. Add `{% if selected_season_id %}` guard around the team checkboxes section.

- [ ] **Step 3: Run smoke tests**

```bash
pytest tests/test_players.py -v
```
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add templates/players/
git commit -m "feat: add season selector to player list and form templates"
```

---

### Task 11: Update season template — add copy-roster UI

**Files:**
- Modify: `templates/seasons/list.html`

- [ ] **Step 1: Update `templates/seasons/list.html`**

For each season row (admin only), add a "Copy roster from" form:

```html
{% if user.is_admin %}
  <form method="post" action="/seasons/{{ s.id }}/copy-roster" style="display:inline">
    <input type="hidden" name="csrf_token" value="{{ request.state.csrf_token }}">
    <select name="source_season_id">
      {% for other in seasons %}
        {% if other.id != s.id %}
          <option value="{{ other.id }}">{{ other.name }}</option>
        {% endif %}
      {% endfor %}
    </select>
    <button type="submit">{{ t("seasons.copy_roster") }}</button>
  </form>
{% endif %}
```

- [ ] **Step 2: Run smoke tests**

```bash
pytest tests/test_seasons.py -v
```
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add templates/seasons/
git commit -m "feat: add copy-roster UI to seasons list template"
```

---

## Chunk 6: Final Verification

### Task 12: Full test run + push

- [ ] **Step 1: Run the full test suite**

```bash
pytest -v --tb=short
```
Expected: All tests pass. No warnings about missing columns.

- [ ] **Step 2: Lint check**

```bash
ruff check .
ruff format --check .
```
Fix any issues, then re-run.

- [ ] **Step 3: Run alembic migration on dev database**

```bash
# Backup first
cp data/proManager.db data/proManager.db.bak.$(date +%Y%m%d)
alembic upgrade head
```

Verify schema:
```bash
sqlite3 data/proManager.db ".schema player_teams"
sqlite3 data/proManager.db ".schema teams"
```

Expected: `player_teams` has `season_id`. `teams` has no `season_id`.

- [ ] **Step 4: Final commit and push**

```bash
git push
```

---

## Deployment to pi4desk

After all tests pass and the branch is pushed:

```bash
ssh pi4desk "cd ~/dockerimages/proManager && git pull && docker compose up -d --build"
```

> **Important:** The migration will run automatically on startup (the app's lifespan calls `init_db`). However `init_db` uses `create_all` — it does **not** run Alembic migrations. Run Alembic manually before restarting:

```bash
ssh pi4desk "cd ~/dockerimages/proManager && docker compose exec web alembic upgrade head"
ssh pi4desk "cd ~/dockerimages/proManager && docker compose up -d --build"
```
