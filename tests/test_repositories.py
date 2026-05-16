from __future__ import annotations

from app.db.repositories.audit import AuditEvent, AuditRepository
from app.db.repositories.sessions import SessionRepository, hash_optional
from app.db.repositories.settings import SettingsRepository
from app.db.repositories.users import UserRepository
from tests.fakes import FakeDb


def test_settings_repository_reads_boolean_setting() -> None:
    db = FakeDb()
    db.settings["fetch.enabled"] = {"setting_value": "true"}
    repo = SettingsRepository(db.connection)

    assert repo.is_enabled("fetch.enabled") is True
    assert repo.is_enabled("missing", default=False) is False


def test_audit_repository_writes_event_without_secret_payload() -> None:
    db = FakeDb()
    repo = AuditRepository(db.connection)

    repo.write_event(
        AuditEvent(
            actor_type="user",
            actor_id="state@boonegraphics.net",
            action_key="pending_user.created",
            result="succeeded",
        )
    )

    assert any("INSERT INTO audit_events" in statement for statement, _ in db.statements)


def test_session_repository_creates_session_with_hashed_metadata() -> None:
    db = FakeDb()
    repo = SessionRepository(db.connection)

    session_id = repo.create_session(
        user_id=1,
        cloudflare_email="state@boonegraphics.net",
        ttl_seconds=60,
        user_agent="Browser",
        source_ip="127.0.0.1",
    )

    assert len(session_id) == 64
    assert hash_optional("Browser") != "Browser"
    assert any("INSERT INTO sessions" in statement for statement, _ in db.statements)


def test_session_repository_revokes_user_sessions() -> None:
    db = FakeDb()
    repo = SessionRepository(db.connection)

    repo.revoke_user_sessions(42)

    assert ("user", 42) in db.revoked_sessions


def test_session_repository_reuses_and_touches_active_session() -> None:
    db = FakeDb()
    repo = SessionRepository(db.connection)
    session_id = repo.create_session(
        user_id=1,
        cloudflare_email="state@boonegraphics.net",
        ttl_seconds=60,
    )

    session = repo.get_active_session(session_id, user_id=1)
    repo.touch_session(session_id)

    assert session.session_id == session_id
    assert session.user_id == 1
    assert session_id in db.touched_sessions


def test_session_repository_revokes_single_session() -> None:
    db = FakeDb()
    repo = SessionRepository(db.connection)
    session_id = repo.create_session(
        user_id=1,
        cloudflare_email="state@boonegraphics.net",
        ttl_seconds=60,
    )

    repo.revoke_session(session_id)

    assert repo.get_active_session(session_id, user_id=1) is None


def test_user_repository_uses_email_for_legacy_rows_without_cloudflare_email() -> None:
    db = FakeDb()
    db.add_user(
        email="state@boonegraphics.net",
        display_name="State",
        status="active",
    )
    db.users["state@boonegraphics.net"]["cloudflare_email"] = None

    user = UserRepository(db.connection).get_by_email("state@boonegraphics.net")

    assert user is not None
    assert user.email == "state@boonegraphics.net"
    assert user.display_name == "State"


def test_user_repository_handles_legacy_rows_without_any_email() -> None:
    db = FakeDb()
    db.add_user(
        email="blank@boonegraphics.net",
        display_name="",
        status="active",
    )
    row = db.users["blank@boonegraphics.net"]
    row["cloudflare_email"] = None
    row["email"] = None
    row["username"] = None

    user = UserRepository(db.connection).get_by_id(row["id"])

    assert user is not None
    assert user.email == f"user-{row['id']}@unknown.local"
