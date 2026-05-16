from __future__ import annotations

from app.auth.cloudflare import CloudflareIdentity
from app.db.repositories.users import UserRepository, normalize_email
from tests.fakes import FakeDb


def test_normalize_email() -> None:
    assert normalize_email(" STATE@BOONEGRAPHICS.NET ") == "state@boonegraphics.net"


def test_unknown_non_admin_identity_creates_pending_user() -> None:
    db = FakeDb()
    repo = UserRepository(db.connection)

    user = repo.ensure_profile(
        CloudflareIdentity(email="chris@boonegraphics.net", display_name="Chris"),
        seed_admin_email="state@boonegraphics.net",
    )

    assert user.email == "chris@boonegraphics.net"
    assert user.display_name == "Chris"
    assert user.status == "pending"
    assert user.is_admin is False


def test_seed_admin_identity_creates_active_admin() -> None:
    db = FakeDb()
    repo = UserRepository(db.connection)

    user = repo.ensure_profile(
        CloudflareIdentity(email="state@boonegraphics.net", display_name="Master Tate"),
        seed_admin_email="state@boonegraphics.net",
    )

    assert user.status == "active"
    assert user.is_admin is True
    assert "admin.manage_users" in user.capabilities
    assert "admin" in user.modules


def test_existing_seed_admin_is_promoted_to_owner_admin() -> None:
    db = FakeDb()
    db.add_user(
        email="state@boonegraphics.net",
        display_name="State",
        status="active",
    )
    db.users["state@boonegraphics.net"]["cloudflare_email"] = None
    repo = UserRepository(db.connection)

    user = repo.ensure_profile(
        CloudflareIdentity(email="state@boonegraphics.net", display_name="Master Tate"),
        seed_admin_email="state@boonegraphics.net",
    )

    assert user.status == "active"
    assert user.is_admin is True
    assert "admin.manage_users" in user.capabilities
    assert "admin" in user.modules


def test_list_pending_returns_only_pending_users() -> None:
    db = FakeDb()
    repo = UserRepository(db.connection)
    repo.ensure_profile(
        CloudflareIdentity(email="state@boonegraphics.net", display_name="Master Tate"),
        seed_admin_email="state@boonegraphics.net",
    )
    repo.ensure_profile(
        CloudflareIdentity(email="pending@boonegraphics.net", display_name="Pending User"),
        seed_admin_email="state@boonegraphics.net",
    )

    pending = repo.list_pending()

    assert [user.email for user in pending] == ["pending@boonegraphics.net"]


def test_admin_directory_skips_legacy_rows_without_identity() -> None:
    db = FakeDb()
    db.add_user(email="blank@boonegraphics.net", display_name="", status="active")
    row = db.users["blank@boonegraphics.net"]
    row["cloudflare_email"] = ""
    row["email"] = None
    row["username"] = "  "
    db.add_user(email="real@boonegraphics.net", display_name="Real User", status="active")
    repo = UserRepository(db.connection)

    users = repo.list_users_for_admin_directory()

    assert [user.email for user in users] == ["real@boonegraphics.net"]


def test_activate_suspend_and_block_user() -> None:
    db = FakeDb()
    repo = UserRepository(db.connection)
    user = repo.ensure_profile(
        CloudflareIdentity(email="pending@boonegraphics.net", display_name="Pending User"),
        seed_admin_email="state@boonegraphics.net",
    )

    repo.activate_user(user.id, approved_by_user_id=99)
    assert repo.get_by_email(user.email).status == "active"

    repo.suspend_user(user.id, actor_user_id=99)
    assert repo.get_by_email(user.email).status == "suspended"

    repo.block_user(user.id, actor_user_id=99)
    assert repo.get_by_email(user.email).status == "blocked"


def test_assignments_change_user_permissions() -> None:
    db = FakeDb()
    repo = UserRepository(db.connection)
    user = repo.ensure_profile(
        CloudflareIdentity(email="user@boonegraphics.net", display_name="User"),
        seed_admin_email="state@boonegraphics.net",
    )

    repo.assign_role(user.id, "viewer")
    repo.set_module_access(user.id, "fetch", True)
    repo.grant_capability(user.id, "fetch.access", granted_by_user_id=99)

    updated = repo.get_by_email(user.email)
    assert updated.role_key == "viewer"
    assert "fetch" in updated.modules
    assert "fetch.access" in updated.capabilities

    repo.revoke_capability(user.id, "fetch.access")
    assert "fetch.access" not in repo.get_by_email(user.email).capabilities
