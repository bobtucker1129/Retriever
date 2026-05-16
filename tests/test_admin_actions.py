from __future__ import annotations

from app.auth.permissions import CurrentUser
from app.db.repositories.audit import AuditRepository
from app.db.repositories.sessions import SessionRepository
from app.db.repositories.users import UserRepository
from app.services.admin_actions import AdminActionService, AdminRepositories
from tests.fakes import FakeDb


def make_actor() -> CurrentUser:
    return CurrentUser(
        id=1,
        email="state@boonegraphics.net",
        display_name="Master Tate",
        status="active",
        capabilities=frozenset({"admin.manage_users"}),
        modules=frozenset({"admin"}),
        is_admin=True,
    )


def make_service(db: FakeDb) -> AdminActionService:
    return AdminActionService(
        AdminRepositories(
            users=UserRepository(db.connection),
            audit=AuditRepository(db.connection),
            sessions=SessionRepository(db.connection),
        )
    )


def test_admin_activate_writes_audit_event() -> None:
    db = FakeDb()
    db.add_user("pending@boonegraphics.net", "Pending User", "pending", full_name="Pending User")
    service = make_service(db)

    service.activate_user(1, make_actor())

    assert db.user_by_id(1)["status"] == "active"
    assert len(db.audit_events) == 1


def test_admin_suspend_revokes_sessions_and_audits() -> None:
    db = FakeDb()
    db.add_user("active@boonegraphics.net", "Active User", "active")
    service = make_service(db)

    service.suspend_user(1, make_actor())

    assert db.user_by_id(1)["status"] == "suspended"
    assert ("user", 1) in db.revoked_sessions
    assert len(db.audit_events) == 1


def test_admin_delete_user_removes_access_revokes_sessions_and_audits() -> None:
    db = FakeDb()
    db.add_user("active@boonegraphics.net", "Active User", "active", full_name="Active User")
    db.capabilities_by_user[1] = {"fetch.access"}
    db.modules_by_user[1] = {"fetch"}
    service = make_service(db)

    service.delete_user(1, make_actor())

    assert db.users == {}
    assert db.capabilities_by_user.get(1) is None
    assert db.modules_by_user.get(1) is None
    assert ("user", 1) in db.revoked_sessions
    assert len(db.audit_events) == 1


def test_admin_delete_rejects_seed_user() -> None:
    db = FakeDb()
    db.add_user("state@boonegraphics.net", "Master Tate", "active", is_seed_admin=True)
    service = make_service(db)

    try:
        service.delete_user(1, make_actor())
    except ValueError as exc:
        assert "seed operator" in str(exc)
    else:
        raise AssertionError("Expected seed delete to fail")

    assert db.user_by_id(1)["status"] == "active"


def test_admin_block_revokes_sessions_and_audits() -> None:
    db = FakeDb()
    db.add_user("active@boonegraphics.net", "Active User", "active")
    service = make_service(db)

    service.block_user(1, make_actor())

    assert db.user_by_id(1)["status"] == "blocked"
    assert ("user", 1) in db.revoked_sessions
    assert len(db.audit_events) == 1


def test_admin_assignment_actions_write_audit_events() -> None:
    db = FakeDb()
    db.add_user("user@boonegraphics.net", "User", "active")
    service = make_service(db)
    actor = make_actor()

    service.set_module_access(1, "fetch", True, actor)
    service.grant_capability(1, "fetch.access", actor)
    service.revoke_capability(1, "fetch.access", actor)

    assert len(db.audit_events) == 3
