from __future__ import annotations

from pathlib import Path
import re

import httpx
from fastapi.testclient import TestClient

import app.auth.sessions as session_module
import app.routes.admin as admin_routes
import app.routes.fetch as fetch_routes
from app.config import AppSettings
from app.dependencies import settings_dependency
from app.db.repositories.fetch import FetchRepository
from app.fetch.booneops_broker import BooneOpsBrokerTurnResult
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


def make_fetch_enabled_settings(
    email: str = "asker@boonegraphics.net",
    with_db: bool = True,
) -> AppSettings:
    kwargs = {
        "retriever_env": "local",
        "local_dev_identity_enabled": True,
        "local_dev_email": email,
        "local_dev_display_name": "Ask Tester",
        "retriever_seed_admin_email": "state@boonegraphics.net",
        "fetch_enabled": True,
        "model_provider": "anthropic",
        "anthropic_api_key": "test-key-not-used",
        "model_default": "claude-stub",
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


def make_fetch_broker_enabled_settings(
    email: str = "asker@boonegraphics.net",
    with_db: bool = True,
) -> AppSettings:
    base = make_fetch_enabled_settings(email=email, with_db=with_db)
    return base.model_copy(
        update={
            "booneops_broker_enabled": True,
            "booneops_broker_url": "http://broker.test.invalid:3487",
            "booneops_broker_bearer_token": "test-bearer-token",
            "booneops_broker_hmac_secret": "test-hmac-secret-value",
        }
    )


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


def test_layout_stylesheet_includes_git_sha_cache_buster() -> None:
    sha = "eb386f9deadbeef"
    settings = make_settings().model_copy(update={"git_sha": sha})
    client = make_client(settings)
    response = client.get("/")
    assert response.status_code == 200
    assert f'/static/app.css?v={sha}' in response.text


def test_layout_stylesheet_default_git_sha_is_dev() -> None:
    client = make_client(make_settings())
    response = client.get("/")
    assert response.status_code == 200
    assert '/static/app.css?v=dev' in response.text


def test_pending_layout_stylesheet_includes_git_sha_cache_buster() -> None:
    sha = "pendingcache1"
    settings = make_settings(email="new@boonegraphics.net").model_copy(update={"git_sha": sha})
    client = make_client(settings)
    response = client.get("/")
    assert response.status_code == 200
    assert f'/static/app.css?v={sha}' in response.text


def test_static_app_css_route_matches_resilient_layout_file() -> None:
    """Served /static/app.css must match package static (cwd-independent mount)."""
    client = make_client(make_settings())
    response = client.get("/static/app.css")
    assert response.status_code == 200
    body = response.text
    assert "7.35rem" not in body
    assert "34rem" not in body
    assert "calc(100vh -" not in body


def test_fetch_shell_renders_for_seed_admin_without_db() -> None:
    client = make_client(make_settings())

    response = client.get("/fetch")

    assert response.status_code == 200
    assert "Fetch is not enabled yet" in response.text
    assert "Connect MySQL to save conversations" in response.text
    assert "+ New Chat" in response.text
    assert "Preview trust states" not in response.text


_FETCH_SHELL_REMOVED_PHRASES = (
    "Thread Reports",
    "What runs depends on how this server is configured",
)

_FETCH_SHELL_TEMPLATE = (
    Path(__file__).resolve().parent.parent / "app" / "templates" / "fetch" / "shell.html"
)

_APP_CSS = Path(__file__).resolve().parent.parent / "app" / "static" / "app.css"


def test_fetch_shell_css_no_brittle_viewport_height() -> None:
    """Fetch shell must not use fixed viewport subtraction or tall min-heights that trap laptops."""
    css = _APP_CSS.read_text(encoding="utf-8")
    assert "7.35rem" not in css
    assert "34rem" not in css
    assert "calc(100vh -" not in css


def test_fetch_shell_css_viewport_fill_chain() -> None:
    """Grid/flex fills available height under topbar; chains min-height: 0 for nested scrollers."""
    css = _APP_CSS.read_text(encoding="utf-8")

    grid_block = re.search(
        r"\.app-shell:has\(\.fetch-shell\)\s*\{([^}]*)\}",
        css,
        re.DOTALL,
    )
    assert grid_block is not None, "expected .app-shell:has(.fetch-shell) block in app.css"
    grid_inner = grid_block.group(1)
    assert "minmax(0, 1fr)" in grid_inner
    assert "100dvh" in grid_inner

    main_block = re.search(
        r"\.main-column:has\(\.fetch-shell\)\s*\{([^}]*)\}",
        css,
        re.DOTALL,
    )
    assert main_block is not None
    assert "min-height: 0" in main_block.group(1)

    content_block = re.search(
        r"\.content:has\(\.fetch-shell\)\s*\{([^}]*)\}",
        css,
        re.DOTALL,
    )
    assert content_block is not None
    content_inner = content_block.group(1)
    assert "flex: 1" in content_inner
    assert "min-height: 0" in content_inner

    shell_blocks = list(re.finditer(r"\.fetch-shell\s*\{([^}]*)\}", css, re.DOTALL))
    assert shell_blocks, "expected at least one .fetch-shell { ... } block in app.css"
    for sb in shell_blocks:
        inner = sb.group(1)
        assert "34rem" not in inner
        assert "7.35rem" not in inner
        assert "calc(100vh -" not in inner
    shell_inner = shell_blocks[0].group(1)
    assert re.search(r"flex:\s*1\s+1\s+0%", shell_inner)
    assert "min-height: 0" in shell_inner
    shell_declarations = [
        part.strip() for part in shell_inner.replace("\n", " ").split(";") if part.strip()
    ]
    assert not any(decl.startswith("height:") for decl in shell_declarations)

    for sb in shell_blocks[1:]:
        normalized = " ".join(sb.group(1).split())
        assert normalized == "flex-direction: column;"
    if len(shell_blocks) > 1:
        media_idx = css.find("@media (max-width: 760px)")
        base_idx = css.find(".fetch-shell {")
        assert media_idx != -1 and base_idx != -1
        assert base_idx < media_idx, "base .fetch-shell must precede @media so mobile only adds direction"

    chat_panel = re.search(r"\.fetch-chat-panel\s*\{([^}]*)\}", css, re.DOTALL)
    assert chat_panel is not None
    panel_inner = chat_panel.group(1)
    assert "flex-direction: column" in panel_inner
    assert "flex: 1" in panel_inner
    assert "min-height: 0" in panel_inner


def test_fetch_shell_css_conversation_list_scroll_contract() -> None:
    """Conversation rail scrolls internally when many threads; does not rely on page scroll."""
    css = _APP_CSS.read_text(encoding="utf-8")
    cl = re.search(r"\.fetch-conversation-list\s*\{([^}]*)\}", css, re.DOTALL)
    assert cl is not None, "expected .fetch-conversation-list block in app.css"
    inner = cl.group(1)
    assert "flex: 1" in inner
    assert "min-height: 0" in inner
    assert "overflow-y: auto" in inner or "overflow: auto" in inner


def test_fetch_shell_css_scroll_root_on_message_list() -> None:
    """`.fetch-message-list` scrolls transcript; `.fetch-thread` is a non-scrolling flex shell."""
    css = _APP_CSS.read_text(encoding="utf-8")
    ml = re.search(r"\.fetch-message-list\s*\{([^}]*)\}", css, re.DOTALL)
    assert ml is not None, "expected .fetch-message-list block in app.css"
    ml_block = ml.group(1)
    assert "overflow: auto" in ml_block or "overflow-y: auto" in ml_block
    assert "min-height: 0" in ml_block
    assert "flex: 1" in ml_block

    th = re.search(r"\.fetch-thread\s*\{([^}]*)\}", css, re.DOTALL)
    assert th is not None
    thread_block = th.group(1)
    assert "overflow: hidden" in thread_block
    assert re.search(r"overflow:\s*auto", thread_block) is None


def test_fetch_shell_css_message_list_scroll_smooth_disabled() -> None:
    """Programmatic scroll anchors use scrollTop jumps; scroll root avoids smooth CSS."""
    css = _APP_CSS.read_text(encoding="utf-8")
    scroll_block = re.search(
        r"\.fetch-message-list--scroll\s*\{([^}]*)\}",
        css,
        re.DOTALL,
    )
    assert scroll_block is not None, "expected .fetch-message-list--scroll block in app.css"
    inner = scroll_block.group(1)
    assert "scroll-behavior:" in inner
    assert "smooth" not in inner


def test_fetch_shell_template_scroll_root_matches_message_list() -> None:
    """`data-fetch-scroll-root` sits on `.fetch-message-list` with message rows."""
    html = _FETCH_SHELL_TEMPLATE.read_text(encoding="utf-8")
    assert (
        re.search(
            r'<div[^>]+class="[^"]*\bfetch-message-list\b[^"]*"[^>]*\bdata-fetch-message-list\b[^>]*'
            r"\bdata-fetch-scroll-root\b",
            html,
            re.DOTALL,
        )
        or re.search(
            r'<div[^>]+class="[^"]*\bfetch-message-list\b[^"]*"[^>]*\bdata-fetch-scroll-root\b[^>]*'
            r"\bdata-fetch-message-list\b",
            html,
            re.DOTALL,
        )
    )


def test_fetch_shell_template_script_and_scroll_hooks() -> None:
    """Static contract for Fetch JS: optimistic ask, single scroller, focus=latest."""
    template_text = _FETCH_SHELL_TEMPLATE.read_text(encoding="utf-8")
    assert "<footer" not in template_text.lower()
    assert 'data-fetch-scroll-root' in template_text
    assert 'fetch-message-list--scroll' in template_text
    assert 'data-fetch-scroll-more' in template_text
    assert 'data-fetch-focus-latest' in template_text
    assert "preventDefault" in template_text
    assert "fetch(" in template_text
    assert "location.assign" in template_text
    assert "clampFetchScrollTop" in template_text
    assert "scrollFetchBottomFallback" in template_text
    assert "scrollFetchRowBottomBreathing" in template_text
    assert "scrollFetchFocusLatestPair" in template_text
    assert "runFetchScrollAfterLayout" in template_text
    assert "getBoundingClientRect" in template_text
    assert "scrollHeight" in template_text
    assert "URLSearchParams" in template_text
    assert "scrollRestoration" in template_text


def test_fetch_get_after_ask_sets_focus_latest_attributes(monkeypatch) -> None:
    """After ask redirect (no focus query needed), anchor flags show last-user id + focus-latest."""
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Stub lane")

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def _no_http(*_a: object, **_k: object) -> None:
        raise AssertionError("fetch ask must not perform HTTP calls")

    monkeypatch.setattr(httpx, "get", _no_http)
    monkeypatch.setattr(httpx, "post", _no_http)
    monkeypatch.setattr(httpx, "request", _no_http)

    client = make_client(settings)

    post = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "What is DSF?"},
    )
    assert post.status_code == 303
    assert post.headers["location"] == f"/fetch?c={conv.conversation_id}"

    page = client.get(post.headers["location"])
    assert page.status_code == 200
    body = page.text
    assert 'data-fetch-focus-latest="true"' in body
    assert "data-fetch-scroll-root" in body
    assert "data-fetch-scroll-more" in body
    assert "fetch-msg-" in body
    assert 'data-fetch-last-user-id=""' not in body
    assert "What is DSF?" in body


def test_fetch_get_existing_conversation_defaults_focus_latest(monkeypatch) -> None:
    """GET /fetch?c=… with stored turns enables bottom anchor without ?focus."""
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Scroll lane")

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def _no_http(*_a: object, **_k: object) -> None:
        raise AssertionError("fetch ask must not perform HTTP calls")

    monkeypatch.setattr(httpx, "get", _no_http)
    monkeypatch.setattr(httpx, "post", _no_http)
    monkeypatch.setattr(httpx, "request", _no_http)

    client = make_client(settings)

    created = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "What is DSF?"},
    )
    assert created.status_code == 303

    direct = client.get(f"/fetch?c={conv.conversation_id}")
    assert direct.status_code == 200
    assert 'data-fetch-focus-latest="true"' in direct.text
    assert 'data-fetch-last-user-id=""' not in direct.text


def test_fetch_get_focus_history_opt_out(monkeypatch) -> None:
    """focus=history leaves the transcript at default scroll position (no bottom anchor attr)."""
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="History lane")

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def _no_http(*_a: object, **_k: object) -> None:
        raise AssertionError("fetch ask must not perform HTTP calls")

    monkeypatch.setattr(httpx, "get", _no_http)
    monkeypatch.setattr(httpx, "post", _no_http)
    monkeypatch.setattr(httpx, "request", _no_http)

    client = make_client(settings)

    post = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "What is DSF?"},
    )
    assert post.status_code == 303

    page = client.get(f"/fetch?c={conv.conversation_id}&focus=history")
    assert page.status_code == 200
    assert 'data-fetch-focus-latest="false"' in page.text


def test_fetch_shell_excludes_thread_reports_and_configuration_disclaimer(
    monkeypatch,
) -> None:
    """Regression: removed sidebar strip / long composer copy must stay out of shell template and GET /fetch HTML."""
    template_text = _FETCH_SHELL_TEMPLATE.read_text(encoding="utf-8")
    for phrase in _FETCH_SHELL_REMOVED_PHRASES:
        assert phrase not in template_text

    client = make_client(make_settings())
    r_minimal = client.get("/fetch")
    assert r_minimal.status_code == 200
    for phrase in _FETCH_SHELL_REMOVED_PHRASES:
        assert phrase not in r_minimal.text

    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    repo = FetchRepository(db.connection)
    repo.create_conversation(user_id=user_id, title="Listed thread")

    settings = make_settings(email="fetcher@boonegraphics.net", with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())
    client_db = make_client(settings)
    r_db = client_db.get("/fetch")
    assert r_db.status_code == 200
    for phrase in _FETCH_SHELL_REMOVED_PHRASES:
        assert phrase not in r_db.text

    db2 = FakeDb()
    db2.add_user("fetcher2@boonegraphics.net", "Fetcher Two", "active")
    user_id2 = db2.users["fetcher2@boonegraphics.net"]["id"]
    db2.modules_by_user.setdefault(user_id2, set()).add("fetch")
    FetchRepository(db2.connection).create_conversation(user_id=user_id2, title="Lane")

    settings_enabled = make_fetch_enabled_settings(email="fetcher2@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db2.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db2.connection())
    client_enabled = make_client(settings_enabled)
    r_enabled = client_enabled.get("/fetch")
    assert r_enabled.status_code == 200
    for phrase in _FETCH_SHELL_REMOVED_PHRASES:
        assert phrase not in r_enabled.text


def test_pending_user_forbidden_from_fetch() -> None:
    client = make_client(make_settings(email="new@boonegraphics.net"))

    response = client.get("/fetch")

    assert response.status_code == 403
    assert "approved" in response.text.lower() or "active" in response.text.lower()


def test_fetch_shell_forbidden_without_fetch_access(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("plain@boonegraphics.net", "Plain User", "active")
    settings = make_settings(email="plain@boonegraphics.net", with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.get("/fetch")

    assert response.status_code == 403


def test_fetch_shell_via_fetch_access_capability_only(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("cap@boonegraphics.net", "Capability User", "active")
    user_id = db.users["cap@boonegraphics.net"]["id"]
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.access")
    FetchRepository(db.connection).create_conversation(user_id=user_id, title="Cap thread")

    settings = make_settings(email="cap@boonegraphics.net", with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.get("/fetch")

    assert response.status_code == 200
    assert "Cap thread" in response.text


def test_fetch_shell_lists_conversations_from_db(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    repo = FetchRepository(db.connection)
    repo.create_conversation(user_id=user_id, title="DSF nightly check")

    settings = make_settings(email="fetcher@boonegraphics.net", with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    client = make_client(settings)
    response = client.get("/fetch")

    assert response.status_code == 200
    assert "DSF nightly check" in response.text


def test_fetch_post_new_conversation_requires_access(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("plain@boonegraphics.net", "Plain User", "active")
    settings = make_settings(email="plain@boonegraphics.net", with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post("/fetch/conversations/new")

    assert response.status_code == 403


def test_fetch_post_new_conversation_redirects_when_allowed(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")

    settings = make_settings(email="fetcher@boonegraphics.net", with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post("/fetch/conversations/new", data={"title": "  Priority queue  "})

    assert response.status_code == 303
    assert response.headers["location"].startswith("/fetch?c=")
    slug = client.get(response.headers["location"])
    assert slug.status_code == 200
    assert "Priority queue" in slug.text


def test_fetch_post_ask_redirects_without_message_when_fetch_disabled(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Ask lane")

    settings = make_settings(email="fetcher@boonegraphics.net", with_db=True)
    assert settings.fetch_enabled is False
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "Hello from disabled gate"},
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/fetch?c={conv.conversation_id}"
    assert len(db.fetch_messages) == 0


def test_fetch_post_ask_allows_fetch_module_without_extra_ask_capability(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Fetch module")

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "What is DSF?"},
    )

    assert response.status_code == 303
    assert len(db.fetch_messages) == 2
    assert db.fetch_messages[0]["content"] == "What is DSF?"


def test_fetch_post_ask_stub_reply_persists_without_external_calls(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Stub lane")

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def _no_http(*_a: object, **_k: object) -> None:
        raise AssertionError("fetch ask must not perform HTTP calls")

    monkeypatch.setattr(httpx, "get", _no_http)
    monkeypatch.setattr(httpx, "post", _no_http)
    monkeypatch.setattr(httpx, "request", _no_http)

    client = make_client(settings)

    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "  What is DSF?  "},
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/fetch?c={conv.conversation_id}"
    assert len(db.fetch_messages) == 2
    assert db.fetch_messages[0]["role"] == "user"
    assert db.fetch_messages[0]["content"] == "What is DSF?"
    assert db.fetch_messages[1]["role"] == "assistant"
    assert "stub" in db.fetch_messages[1]["content"].lower()
    assert "printsmith" in db.fetch_messages[1]["content"].lower()
    assert db.fetch_messages[1]["route_key"] == "printsmith_candidate"

    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert "What is DSF?" in page.text
    assert "stub" in page.text.lower()
    assert "General Question: Off" in page.text
    assert "Context: 0% stub" in page.text


def test_fetch_post_ask_slash_help_returns_static_guidance(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Cmd lane")

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "/help"},
    )

    assert response.status_code == 303
    assert db.fetch_messages[1]["route_key"] == "help"
    assert "/help" in db.fetch_messages[1]["content"]
    assert "offline stub" in db.fetch_messages[1]["content"].lower()
    assert "slash" in db.fetch_messages[1]["content"].lower()


def test_fetch_post_ask_slash_sources_and_health(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Cmd lane")

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    r1 = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "/sources"},
    )
    assert r1.status_code == 303
    assert db.fetch_messages[-1]["route_key"] == "sources"
    assert "printsmith" in db.fetch_messages[-1]["content"].lower()

    r2 = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "/health"},
    )
    assert r2.status_code == 303
    assert db.fetch_messages[-1]["route_key"] == "health"
    assert "integration" in db.fetch_messages[-1]["content"].lower()


def test_fetch_post_ask_route_like_prompt_no_http(monkeypatch) -> None:
    """Docs-shaped prompts must not trigger outbound HTTP from the ask handler."""
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Doc lane")

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def _no_http(*_a: object, **_k: object) -> None:
        raise AssertionError("unexpected outbound HTTP from fetch ask")

    monkeypatch.setattr(httpx, "get", _no_http)
    monkeypatch.setattr(httpx, "post", _no_http)
    monkeypatch.setattr(httpx, "request", _no_http)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "Where is the xmpie uproduce documentation?"},
    )
    assert response.status_code == 303
    assert db.fetch_messages[-1]["route_key"] == "docs_candidate"
    assert "vendor" in db.fetch_messages[-1]["content"].lower() or "documentation" in db.fetch_messages[-1]["content"].lower()
    assert "stub" in db.fetch_messages[-1]["content"].lower()


def test_fetch_shell_has_no_global_routing_footer_when_fetch_enabled(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    FetchRepository(db.connection).create_conversation(user_id=user_id, title="Lane")

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.get("/fetch")

    assert response.status_code == 200
    assert "Routing: not connected" not in response.text
    assert "Path: local" not in response.text


def test_fetch_shell_has_no_global_broker_footer_when_broker_enabled(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    FetchRepository(db.connection).create_conversation(user_id=user_id, title="Lane")

    settings = make_fetch_broker_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.get("/fetch")

    assert response.status_code == 200
    assert "Routing: BooneOps broker" not in response.text
    assert "Path: booneops" not in response.text


def test_fetch_post_ask_printsmith_calls_broker_when_enabled(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Broker lane")

    settings = make_fetch_broker_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def _no_http(*_a: object, **_k: object) -> None:
        raise AssertionError("Fetch ask must use broker client, not raw httpx")

    monkeypatch.setattr(httpx, "get", _no_http)
    monkeypatch.setattr(httpx, "post", _no_http)
    monkeypatch.setattr(httpx, "request", _no_http)

    def fake_broker(*_a: object, **_kw: object) -> BooneOpsBrokerTurnResult:
        return BooneOpsBrokerTurnResult("Anchored BooneOps reply text.", "booneops")

    monkeypatch.setattr(fetch_routes, "call_booneops_broker", fake_broker)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "What is PrintSmith DSF?"},
    )

    assert response.status_code == 303
    assert len(db.fetch_messages) == 2
    assert db.fetch_messages[1]["role"] == "assistant"
    assert db.fetch_messages[1]["content"] == "Anchored BooneOps reply text."
    assert db.fetch_messages[1]["context_state"] == "booneops"
    assert "stub" not in db.fetch_messages[1]["content"].lower()

    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert "Context: 0% ready" in page.text
    assert "Anchored BooneOps reply text." in page.text


def test_fetch_post_ask_docs_renders_broker_source_cards(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Docs lane")

    settings = make_fetch_broker_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def fake_broker(*_a: object, **_kw: object) -> BooneOpsBrokerTurnResult:
        return BooneOpsBrokerTurnResult(
            "Summary\nUse the Switch scripting guide.\n\nDetails\nLong answer.",
            "booneops",
            {
                "source_cards": [
                    {
                        "kind": "docs",
                        "title": "Switch Scripting Guide",
                        "detail": "Script element reference",
                    }
                ]
            },
        )

    monkeypatch.setattr(fetch_routes, "call_booneops_broker", fake_broker)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "Where is the Switch manual?"},
    )

    assert response.status_code == 303
    assert db.fetch_messages[1]["metadata_json"] is not None
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert "Sources" in page.text
    assert "Switch Scripting Guide" in page.text
    assert "Script element reference" in page.text


def test_fetch_post_ask_broker_failure_keeps_conversation_usable(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Broker lane")

    settings = make_fetch_broker_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def fake_broker(*_a: object, **_kw: object) -> BooneOpsBrokerTurnResult:
        return BooneOpsBrokerTurnResult(
            "Fetch could not reach the BooneOps broker (network error).\n\n"
            "Your message was saved.",
            "booneops_error",
        )

    monkeypatch.setattr(fetch_routes, "call_booneops_broker", fake_broker)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "PrintSmith question"},
    )

    assert response.status_code == 303
    assert db.fetch_messages[0]["role"] == "user"
    assert db.fetch_messages[1]["role"] == "assistant"
    assert "saved" in db.fetch_messages[1]["content"].lower()
    assert db.fetch_messages[1]["context_state"] == "booneops_error"

def test_home_hides_fetch_nav_without_access(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("plain@boonegraphics.net", "Plain User", "active")
    settings = make_settings(email="plain@boonegraphics.net", with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.get("/")

    assert response.status_code == 200
    assert "Fetch disabled" not in response.text


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

