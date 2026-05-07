from __future__ import annotations

from app.auth.cloudflare import CloudflareIdentity
from app.auth.sessions import current_user_from_identity
from app.config import AppSettings
from app.db.repositories.users import UserRepository
from tests.fakes import FakeDb


def test_current_user_flow_uses_repository_for_pending_user() -> None:
    db = FakeDb()
    repo = UserRepository(db.connection)
    settings = AppSettings(retriever_seed_admin_email="state@boonegraphics.net")

    user = current_user_from_identity(
        CloudflareIdentity(email="new@boonegraphics.net", display_name="New User"),
        settings,
        repository=repo,
    )

    assert user.email == "new@boonegraphics.net"
    assert user.status == "pending"
    assert user.is_admin is False


def test_current_user_flow_uses_repository_for_seed_admin() -> None:
    db = FakeDb()
    repo = UserRepository(db.connection)
    settings = AppSettings(retriever_seed_admin_email="state@boonegraphics.net")

    user = current_user_from_identity(
        CloudflareIdentity(email="state@boonegraphics.net", display_name="Master Tate"),
        settings,
        repository=repo,
    )

    assert user.status == "active"
    assert user.is_admin is True
    assert user.has_capability("admin.manage_users")
    assert user.has_module("admin")

