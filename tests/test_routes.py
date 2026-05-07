from __future__ import annotations

from fastapi.testclient import TestClient

import app.auth.sessions as session_module
import app.routes.admin as admin_routes
from app.config import AppSettings
from app.dependencies import settings_dependency
from app.main import create_app
from tests.fakes import FakeDb


def make_settings(email: str = "state@boonegraphics.net", with_db: bool = False) -> AppSettings:
    kwargs = {
        "retriever_env": "local",
        "local_dev_identity_enabled": True,
        "local_dev_email": email,
        "local_dev_display_name": "Route Tester",
        "retriever_seed_admin_email": "state@boonegraphics.net",
    }
    if with_db:
        kwargs.update(
            {
                "mysql_host": "mysql.internal",
                "mysql_user": "retriever_app",
                "mysql_password": "redacted",
            }
        )
    return AppSettings(**kwargs)


def make_client(settings: AppSettings) -> TestClient:
    app = create_app()
    app.dependency_overrides[settings_dependency] = lambda: settings
    return TestClient(app, follow_redirects=False)


def test_pending_user_page_for_non_admin_local_identity() -> None:
    client = make_client(make_settings(email="new@boonegraphics.net"))

    response = client.get("/")

    assert response.status_code == 200
    assert "Retriever access pending" in response.text


def test_seeded_admin_can_load_app_shell() -> None:
    client = make_client(make_settings())

    response = client.get("/")

    assert response.status_code == 200
    assert "Retriever auth shell" in response.text


def test_fetch_route_renders_disabled_skeleton() -> None:
    client = make_client(make_settings())

    response = client.get("/fetch")

    assert response.status_code == 200
    assert "Fetch is not enabled yet" in response.text
    assert "Fetch skeleton review" in response.text
    assert "Context: 0% ready" in response.text
    assert "Model: not connected" in response.text


def test_non_admin_is_forbidden_from_admin_users() -> None:
    client = make_client(make_settings(email="new@boonegraphics.net"))

    response = client.get("/admin/users")

    assert response.status_code == 403


def test_admin_users_page_lists_pending_users(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("pending@boonegraphics.net", "Pending User", "pending")
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(admin_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.get("/admin/users")

    assert response.status_code == 200
    assert "Pending User" in response.text
    assert "Approve" in response.text
    assert "Grant Fetch access" in response.text


def test_admin_activate_post_updates_user_and_redirects(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("pending@boonegraphics.net", "Pending User", "pending")
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(admin_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post("/admin/users/1/activate")

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/users"
    assert db.user_by_id(1)["status"] == "active"
    assert len(db.audit_events) == 1


def test_active_db_user_gets_session_cookie(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("state@boonegraphics.net", "Master Tate", "active", is_seed_admin=True)
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(admin_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.get("/")

    assert response.status_code == 200
    assert "retriever_session=" in response.headers.get("set-cookie", "")
    assert len(db.sessions) == 1


def test_active_db_user_reuses_existing_session_cookie(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("state@boonegraphics.net", "Master Tate", "active", is_seed_admin=True)
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    first = client.get("/")
    cookie = first.cookies.get("retriever_session")
    client.cookies.set("retriever_session", cookie)
    second = client.get("/")

    assert second.status_code == 200
    assert cookie in db.touched_sessions
    assert len(db.sessions) == 1


def test_logout_revokes_session_cookie(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("state@boonegraphics.net", "Master Tate", "active", is_seed_admin=True)
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    client = make_client(settings)
    first = client.get("/")
    cookie = first.cookies.get("retriever_session")
    client.cookies.set("retriever_session", cookie)

    response = client.post("/logout")

    assert response.status_code == 303
    assert cookie in db.revoked_sessions


def test_suspended_user_is_denied_admin_route(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("state@boonegraphics.net", "Master Tate", "suspended", is_seed_admin=True)
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(admin_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.get("/admin/users")

    assert response.status_code == 403


def test_blocked_user_is_denied_admin_route(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("state@boonegraphics.net", "Master Tate", "blocked", is_seed_admin=True)
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(admin_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.get("/admin/users")

    assert response.status_code == 403

