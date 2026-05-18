from __future__ import annotations

import json
from pathlib import Path
import re
import uuid

import httpx
from fastapi.testclient import TestClient

import app.auth.sessions as session_module
import app.routes.admin as admin_routes
import app.routes.fetch as fetch_routes
from app.config import AppSettings
from app.dependencies import settings_dependency
from app.db.repositories.fetch import FetchRepository
from app.fetch.booneops_broker import BooneOpsBrokerTurnResult, build_broker_message_presentation
from app.fetch.safe_links import safe_fetch_download_href
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


def make_fetch_broker_proxy_test_settings(email: str = "state@boonegraphics.net") -> AppSettings:
    """Broker + Fetch without MySQL so tests use scaffold identity (seed admin bypasses DB)."""
    return make_fetch_broker_enabled_settings(email=email, with_db=False)


def make_client(settings: AppSettings) -> TestClient:
    app = create_app()
    app.dependency_overrides[settings_dependency] = lambda: settings
    return TestClient(app, follow_redirects=False)


def test_pending_user_page_for_non_admin_local_identity() -> None:
    client = make_client(make_settings(email="new@boonegraphics.net"))

    response = client.get("/")

    assert response.status_code == 200
    assert "Retriever access pending" in response.text
    assert "waiting for an operator" in response.text.lower()
    assert "/health/ready" not in response.text
    assert "nav-label\">Version" not in response.text


def test_seeded_admin_can_load_app_shell() -> None:
    client = make_client(make_settings())

    response = client.get("/")

    assert response.status_code == 200
    assert "Retriever auth shell" in response.text
    assert "/health/ready" in response.text


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


def test_health_and_version_links_render_friendly_html_for_browsers() -> None:
    client = make_client(make_settings())

    health = client.get("/health/ready", headers={"accept": "text/html"})
    version = client.get("/version", headers={"accept": "text/html"})

    assert health.status_code == 200
    assert "Readiness checks" in health.text
    assert "status-grid" not in health.text
    assert version.status_code == 200
    assert "Git SHA" in version.text
    assert "retriever-rebuild" in version.text


def test_health_and_version_still_return_json_for_api_clients() -> None:
    client = make_client(make_settings())

    health = client.get("/health/ready", headers={"accept": "application/json"})
    version = client.get("/version", headers={"accept": "application/json"})

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert version.status_code == 200
    assert version.json()["app"] == "retriever-rebuild"


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
    assert 'data-fetch-suggestion="/docs"' in response.text
    assert 'data-fetch-suggestion="/printsmith"' in response.text


def test_wiki_renders_for_active_seed_admin() -> None:
    client = make_client(make_settings())

    response = client.get("/wiki/")

    assert response.status_code == 200
    assert "Boone Wiki" in response.text
    assert "SweetProcess Procedures" in response.text
    assert "Processing Cal Poly DSF" in response.text
    assert "https://www.sweetprocess.com/procedures/132kYCJ9J0/processing-cal-poly-dsf-am/" in response.text
    assert "Work Instructions" in response.text
    assert "WI-022" in response.text
    assert "/wiki/doc/wi-022-secure-mailing" in response.text
    assert "Document cards" in response.text
    assert "Quality &amp; ISO" in response.text
    assert "Security Posture" in response.text
    assert "General Knowledge" in response.text
    assert "known audit questions" in response.text
    assert "Level 1 Quality Manual" in response.text
    assert 'href="/wiki/" title="Wiki"' in response.text
    assert 'nav-abbrev">W<' in response.text


def test_wiki_requires_active_user() -> None:
    client = make_client(make_settings(email="pending@boonegraphics.net"))

    response = client.get("/wiki/")

    assert response.status_code == 403


def test_wiki_document_detail_stays_inside_retriever() -> None:
    client = make_client(make_settings())

    response = client.get("/wiki/doc/wi-022-secure-mailing")

    assert response.status_code == 200
    assert "WI-022" in response.text
    assert "Secure Mailing" in response.text
    assert "Controlled Wiki view" in response.text
    assert "Raw source documents stay behind" in response.text
    assert "Detailed summaries will be populated" in response.text
    assert "Current internal wiki collection" in response.text


def test_unknown_wiki_document_returns_404() -> None:
    client = make_client(make_settings())

    response = client.get("/wiki/doc/not-a-real-doc")

    assert response.status_code == 404


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
    assert "100vh" in grid_inner
    assert "100dvh" in grid_inner
    assert "overflow: hidden" in grid_inner
    assert "min-height: 0" in grid_inner

    body_fetch = re.search(r"body:has\(\.fetch-shell\)\s*\{([^}]*)\}", css, re.DOTALL)
    assert body_fetch is not None, "expected body:has(.fetch-shell) block for viewport lock"
    body_inner = body_fetch.group(1)
    assert "overflow: hidden" in body_inner
    assert "100vh" in body_inner
    assert "100dvh" in body_inner

    main_block = re.search(
        r"\.main-column:has\(\.fetch-shell\)\s*\{([^}]*)\}",
        css,
        re.DOTALL,
    )
    assert main_block is not None
    main_inner = main_block.group(1)
    assert "min-height: 0" in main_inner
    assert "height: 100%" in main_inner
    assert "overflow: hidden" in main_inner

    content_block = re.search(
        r"\.content:has\(\.fetch-shell\)\s*\{([^}]*)\}",
        css,
        re.DOTALL,
    )
    assert content_block is not None
    content_inner = content_block.group(1)
    assert "flex: 1" in content_inner
    assert "min-height: 0" in content_inner
    assert "overflow: hidden" in content_inner

    topbar_fetch = re.search(
        r"\.main-column:has\(\.fetch-shell\) \.topbar\s*\{([^}]*)\}",
        css,
        re.DOTALL,
    )
    assert topbar_fetch is not None
    assert "flex-shrink: 0" in topbar_fetch.group(1)

    sidebar_fetch = re.search(
        r"\.app-shell:has\(\.fetch-shell\) > \.sidebar\s*\{([^}]*)\}",
        css,
        re.DOTALL,
    )
    assert sidebar_fetch is not None
    sb_inner = sidebar_fetch.group(1)
    assert "min-height: 0" in sb_inner
    assert "overflow-y: auto" in sb_inner or "overflow: auto" in sb_inner

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
    assert "data-fetch-suggestion" in template_text
    assert 'querySelectorAll("[data-fetch-suggestion]")' in template_text


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


def test_fetch_shell_creates_first_conversation_when_enabled(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    client = make_client(settings)
    response = client.get("/fetch")

    assert response.status_code == 200
    assert len(db.fetch_conversations) == 1
    assert "New Fetch conversation" in response.text
    textarea = re.search(r'<textarea[^>]*id="fetch-question"[^>]*>', response.text, re.DOTALL)
    assert textarea is not None
    assert "disabled" not in textarea.group(0)


def test_fetch_shell_adopts_same_email_legacy_history(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    db.add_user("legacy-row", "Legacy User", "active")
    current_id = db.users["fetcher@boonegraphics.net"]["id"]
    legacy_id = db.users["legacy-row"]["id"]
    db.modules_by_user.setdefault(current_id, set()).add("fetch")
    db.users["legacy-row"]["cloudflare_email"] = "fetcher@boonegraphics.net"
    db.users["legacy-row"]["email"] = "fetcher@boonegraphics.net"
    db.users["legacy-row"]["username"] = "fetcher@boonegraphics.net"

    repo = FetchRepository(db.connection)
    conversation = repo.create_conversation(user_id=legacy_id, title="Recovered thread")
    repo.append_message(
        user_id=legacy_id,
        conversation_id=conversation.conversation_id,
        role="user",
        content="Find order 12345",
    )

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    client = make_client(settings)
    response = client.get("/fetch")

    assert response.status_code == 200
    assert "Recovered thread" in response.text
    assert "Find order 12345" in response.text
    assert db.fetch_conversations[conversation.conversation_id]["user_id"] == current_id
    assert db.fetch_messages[0]["user_id"] == current_id


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


def test_fetch_post_ask_slash_docs_and_printsmith(monkeypatch) -> None:
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

    r_docs = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "/docs Switch checkpoint"},
    )
    assert r_docs.status_code == 303
    assert db.fetch_messages[-1]["route_key"] == "docs_candidate"
    assert "stub" in db.fetch_messages[-1]["content"].lower()

    r_ps = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "/printsmith"},
    )
    assert r_ps.status_code == 303
    assert db.fetch_messages[-1]["route_key"] == "printsmith_candidate"
    assert "stub" in db.fetch_messages[-1]["content"].lower()


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
    assert "Model: not recorded" in page.text
    assert "Thread load:" in page.text
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
    assert 'title="Script element reference"' not in page.text
    assert "Script element reference</p>" not in page.text


def test_fetch_post_ask_renders_safe_artifact_download_link(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Artifact lane")

    settings = make_fetch_broker_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def fake_broker(*_a: object, **_kw: object) -> BooneOpsBrokerTurnResult:
        return BooneOpsBrokerTurnResult(
            "Report is ready.",
            "booneops",
            {
                "artifacts": [
                    {
                        "filename": "Quarterly.xlsx",
                        "description": "Q1 export",
                        "downloadPath": "/fetch/artifacts/q1.xlsx",
                    }
                ]
            },
        )

    monkeypatch.setattr(fetch_routes, "call_booneops_broker", fake_broker)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "PrintSmith DSF job status"},
    )

    assert response.status_code == 303
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert 'class="fetch-artifact-dl"' in page.text
    assert 'href="/fetch/artifacts/q1.xlsx"' in page.text
    assert "Quarterly.xlsx" in page.text


def test_fetch_post_ask_rewrites_broker_artifact_id_to_canonical_proxy_path(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Artifacts")

    settings = make_fetch_broker_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    aid = "550e8400-e29b-41d4-a716-446655440000"

    def fake_broker(*_a: object, **_kw: object) -> BooneOpsBrokerTurnResult:
        text, md = build_broker_message_presentation(
            {
                "ok": True,
                "message": "Report is ready.",
                "artifacts": [
                    {
                        "filename": "Quarterly.pdf",
                        "description": "Q1 PDF",
                        "artifactId": aid,
                        "downloadPath": f"/v1/booneops/artifacts/{aid}",
                    }
                ],
            },
            "printsmith_candidate",
        )
        return BooneOpsBrokerTurnResult(text, "booneops", md)

    monkeypatch.setattr(fetch_routes, "call_booneops_broker", fake_broker)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "PrintSmith DSF PDF export"},
    )

    assert response.status_code == 303
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    canonical = f"/fetch/artifacts/broker/{aid}"
    assert f'href="{canonical}"' in page.text
    assert "/v1/booneops/artifacts/" not in page.text


def test_fetch_broker_artifact_proxy_streams_pdf(monkeypatch) -> None:
    settings = make_fetch_broker_proxy_test_settings()
    client = make_client(settings)
    aid = "550e8400-e29b-41d4-a716-446655440000"

    def fake_get(url: str, *, bearer_token: str, timeout: float) -> httpx.Response:
        assert str(aid) in url
        assert "/v1/booneops/artifacts/" in url
        assert bearer_token == settings.booneops_broker_bearer_token
        return httpx.Response(
            200,
            content=b"%PDF-1.4 artifact-bytes-here\n",
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": 'attachment; filename="Quarterly-report.pdf"',
            },
        )

    monkeypatch.setattr("app.fetch.booneops_broker.default_broker_artifact_http_get", fake_get)

    resp = client.get(f"/fetch/artifacts/broker/{aid}")
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")
    assert resp.headers["content-type"].startswith("application/pdf")
    cd = resp.headers.get("content-disposition", "").lower()
    assert "attachment" in cd
    assert "quarterly-report.pdf" in cd
    assert resp.headers.get("cache-control") == "no-store"
    assert resp.headers.get("pragma") == "no-cache"


def test_fetch_broker_artifact_proxy_forbidden_without_fetch_shell_access(monkeypatch) -> None:
    """Active non-admin without Fetch module must not reach broker artifact upstream."""
    db = FakeDb()
    db.add_user("plain@boonegraphics.net", "Plain User", "active")
    settings = make_fetch_broker_enabled_settings(email="plain@boonegraphics.net", with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def boom_get(*_a: object, **_k: object) -> None:
        raise AssertionError("broker artifact upstream must not be called without fetch shell access")

    monkeypatch.setattr("app.fetch.booneops_broker.default_broker_artifact_http_get", boom_get)

    client = make_client(settings)
    aid = "550e8400-e29b-41d4-a716-446655440000"
    resp = client.get(f"/fetch/artifacts/broker/{aid}")
    assert resp.status_code == 403


def test_fetch_broker_artifact_compat_route_streams(monkeypatch) -> None:
    settings = make_fetch_broker_proxy_test_settings()
    client = make_client(settings)
    aid = "550e8400-e29b-41d4-a716-446655440000"

    def fake_get(url: str, *, bearer_token: str, timeout: float) -> httpx.Response:
        assert bearer_token == settings.booneops_broker_bearer_token
        return httpx.Response(
            200,
            content=b"fake-xlsx-binary",
            headers={
                "Content-Type": (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ),
                "Content-Disposition": 'attachment; filename="Workbook.xlsx"',
            },
        )

    monkeypatch.setattr("app.fetch.booneops_broker.default_broker_artifact_http_get", fake_get)

    resp = client.get(f"/v1/booneops/artifacts/{aid}")
    assert resp.status_code == 200
    assert resp.content == b"fake-xlsx-binary"
    ct = resp.headers["content-type"]
    assert "spreadsheetml" in ct
    cd = resp.headers.get("content-disposition", "").lower()
    assert "attachment" in cd
    assert "workbook.xlsx" in cd
    assert resp.headers.get("pragma") == "no-cache"


def test_fetch_broker_artifact_proxy_rejects_bad_artifact_tokens() -> None:
    settings = make_fetch_broker_proxy_test_settings()
    client = make_client(settings)
    assert client.get("/fetch/artifacts/broker/ab").status_code == 400


def test_fetch_broker_artifact_proxy_json_body_returns_error_not_download(monkeypatch) -> None:
    settings = make_fetch_broker_proxy_test_settings()
    client = make_client(settings)
    aid = "550e8400-e29b-41d4-a716-446655440000"

    def fake_get(_url: str, *, bearer_token: str, timeout: float) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'{"ok":false,"errors":[{"message":"gone"}]}',
            headers={"Content-Type": "application/json"},
        )

    monkeypatch.setattr("app.fetch.booneops_broker.default_broker_artifact_http_get", fake_get)
    resp = client.get(f"/fetch/artifacts/broker/{aid}")
    assert resp.status_code == 503
    assert "detail" in resp.json()
    assert not resp.content.startswith(b"%PDF")
    cd = resp.headers.get("content-disposition") or ""
    assert "attachment" not in cd.lower()


def test_fetch_broker_artifact_proxy_octet_sniff_detects_small_json(monkeypatch) -> None:
    settings = make_fetch_broker_proxy_test_settings()
    client = make_client(settings)
    aid = "550e8400-e29b-41d4-a716-446655440000"

    def fake_get(_url: str, *, bearer_token: str, timeout: float) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'{"artifact":"gone"} ',
            headers={"Content-Type": "application/octet-stream"},
        )

    monkeypatch.setattr("app.fetch.booneops_broker.default_broker_artifact_http_get", fake_get)
    assert client.get(f"/fetch/artifacts/broker/{aid}").status_code == 503


def test_fetch_broker_artifact_proxy_503_without_broker_config() -> None:
    settings = make_fetch_enabled_settings(email="state@boonegraphics.net", with_db=False)
    client = make_client(settings)
    aid = "550e8400-e29b-41d4-a716-446655440000"
    r = client.get(f"/fetch/artifacts/broker/{aid}")
    assert r.status_code == 503


def test_fetch_post_ask_skips_external_artifact_href(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Artifact lane")

    settings = make_fetch_broker_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def fake_broker(*_a: object, **_kw: object) -> BooneOpsBrokerTurnResult:
        return BooneOpsBrokerTurnResult(
            "Here is a file.",
            "booneops",
            {
                "artifacts": [
                    {
                        "filename": "bad.xlsx",
                        "downloadPath": "https://evil.example/leak",
                    }
                ]
            },
        )

    monkeypatch.setattr(fetch_routes, "call_booneops_broker", fake_broker)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "PrintSmith DSF export please"},
    )

    assert response.status_code == 303
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert "evil.example" not in page.text
    assert 'class="fetch-artifact-dl"' not in page.text
    assert 'class="fetch-artifact-name"' in page.text


def test_fetch_general_question_uses_anthropic_llm_without_broker(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Stub lane")

    settings = make_fetch_broker_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def fake_broker(*_a: object, **_kw: object) -> BooneOpsBrokerTurnResult:
        raise AssertionError("general questions should not call the BooneOps broker")

    monkeypatch.setattr(fetch_routes, "call_booneops_broker", fake_broker)

    def fake_llm(*_a: object, **_kw: object) -> fetch_routes.GeneralLlmTurnResult:
        return fetch_routes.GeneralLlmTurnResult(
            "The Kings are worth checking on, but I do not have live scores here.",
            "llm",
            "claude-opus-4-7",
            {"general_llm_provider": "anthropic"},
        )

    monkeypatch.setattr(fetch_routes, "call_general_conversation_llm", fake_llm)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "How are the LA Kings doing?"},
    )

    assert response.status_code == 303
    assert db.fetch_messages[0]["route_key"] == "general_candidate"
    assert db.fetch_messages[1]["context_state"] == "llm"
    assert db.fetch_messages[1]["content"].startswith("The Kings")
    assert db.fetch_messages[1]["model_label"] == "claude-opus-4-7"
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert "fetch-source-card-list" not in page.text


def test_fetch_cleanup_email_uses_dedicated_llm_and_copy_button(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Email lane")

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    captured: dict[str, object] = {}

    def fake_cleanup(
        _settings: AppSettings,
        *,
        email_draft: str,
    ) -> fetch_routes.GeneralLlmTurnResult:
        captured["email_draft"] = email_draft
        return fetch_routes.GeneralLlmTurnResult(
            "Hi Michael,\n\nThanks for sending this over.",
            "llm",
            "claude-opus-4-7",
            {"email_cleanup": True, "general_llm_provider": "anthropic"},
        )

    monkeypatch.setattr(fetch_routes, "call_email_cleanup_llm", fake_cleanup)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/cleanup-email",
        data={"question": "Hi Micheal,\n\nthank for sending this ovre"},
    )

    assert response.status_code == 303
    assert captured["email_draft"] == "Hi Micheal,\n\nthank for sending this ovre"
    assert db.fetch_messages[0]["route_key"] == "email_cleanup"
    assert db.fetch_messages[0]["content"] == "Hi Micheal,\n\nthank for sending this ovre"
    assert db.fetch_messages[1]["route_key"] == "email_cleanup"
    assert db.fetch_messages[1]["metadata_json"] is not None
    assert json.loads(db.fetch_messages[1]["metadata_json"])["email_cleanup"] is True
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    assert "Cleaned email" in page.text
    assert "data-fetch-copy-target" in page.text
    assert "Thanks for sending this over." in page.text


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


def test_fetch_export_followup_inherits_printsmith_and_calls_broker(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Export lane")
    repo = FetchRepository(db.connection)

    repo.append_message(
        user_id,
        conv.conversation_id,
        role="user",
        content="How many jobs in January?",
        route_key="printsmith_candidate",
    )
    repo.append_message(
        user_id,
        conv.conversation_id,
        role="assistant",
        content="January had 42 jobs.",
        route_key="printsmith_candidate",
        context_state="booneops",
    )

    settings = make_fetch_broker_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def _no_http(*_a: object, **_k: object) -> None:
        raise AssertionError("Fetch ask must use broker client, not raw httpx")

    monkeypatch.setattr(httpx, "get", _no_http)
    monkeypatch.setattr(httpx, "post", _no_http)
    monkeypatch.setattr(httpx, "request", _no_http)

    captured: dict[str, object] = {}

    def fake_broker(
        _settings: AppSettings,
        *,
        route_label: str,
        prior_messages: list,
        session_metadata_extra: object = None,
        **_kw: object,
    ) -> BooneOpsBrokerTurnResult:
        captured["route_label"] = route_label
        captured["prior_messages"] = list(prior_messages)
        captured["session_metadata_extra"] = session_metadata_extra
        return BooneOpsBrokerTurnResult("PDF export reply.", "booneops")

    monkeypatch.setattr(fetch_routes, "call_booneops_broker", fake_broker)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "can you export that as a pdf file?"},
    )

    assert response.status_code == 303
    assert captured.get("route_label") == "printsmith_candidate"
    prior_msgs = captured.get("prior_messages")
    assert isinstance(prior_msgs, list)
    texts = [m.get("text", "") for m in prior_msgs if isinstance(m, dict)]
    assert "How many jobs in January?" in texts
    assert "January had 42 jobs." in texts
    assert db.fetch_messages[-2]["route_key"] == "printsmith_candidate"
    assert db.fetch_messages[-1]["content"] == "PDF export reply."


def test_fetch_refinement_followup_inherits_printsmith_and_sends_report_style(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Refine lane")
    repo = FetchRepository(db.connection)

    repo.append_message(
        user_id,
        conv.conversation_id,
        role="user",
        content="Open jobs summary",
        route_key="printsmith_candidate",
    )
    repo.append_message(
        user_id,
        conv.conversation_id,
        role="assistant",
        content="January had 42 jobs.",
        route_key="printsmith_candidate",
        context_state="booneops",
    )

    settings = make_fetch_broker_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    captured: dict[str, object] = {}

    def fake_post(url: str, *, content: bytes, headers: dict[str, str], timeout: float):
        captured["payload"] = json.loads(content.decode())

        class Resp:
            status_code = 200
            content = b'{"ok":true,"message":"Styled spreadsheet reply.","errors":[]}'

            def json(self):
                return json.loads(self.content.decode())

        return Resp()

    monkeypatch.setattr("app.fetch.booneops_broker.default_http_post", fake_post)

    phrase = (
        "Can you fancy up the excel file and maybe add some bolding and colorful headers?"
    )
    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": phrase},
    )

    assert response.status_code == 303
    payload = captured.get("payload")
    assert isinstance(payload, dict)
    assert payload.get("sessionMetadata", {}).get("reportStyle") == "basic_styled_excel"
    msg = str(payload.get("message") or "")
    assert "[Retriever follow-up: basic styled Excel]" in msg
    assert phrase in msg
    assert db.fetch_messages[-2]["content"] == phrase
    assert db.fetch_messages[-2]["route_key"] == "printsmith_candidate"
    assert "Styled spreadsheet reply." in db.fetch_messages[-1]["content"]


def test_fetch_export_followup_inherits_docs_and_calls_broker(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Docs export")
    repo = FetchRepository(db.connection)

    repo.append_message(
        user_id,
        conv.conversation_id,
        role="assistant",
        content="Switch scripting overview.",
        route_key="docs_candidate",
        context_state="booneops",
    )

    settings = make_fetch_broker_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def _no_http(*_a: object, **_k: object) -> None:
        raise AssertionError("Fetch ask must use broker client")

    monkeypatch.setattr(httpx, "get", _no_http)
    monkeypatch.setattr(httpx, "post", _no_http)
    monkeypatch.setattr(httpx, "request", _no_http)

    captured: dict[str, object] = {}

    def fake_broker(
        _settings: AppSettings,
        *,
        route_label: str,
        **_kw: object,
    ) -> BooneOpsBrokerTurnResult:
        captured["route_label"] = route_label
        return BooneOpsBrokerTurnResult("CSV attached.", "booneops")

    monkeypatch.setattr(fetch_routes, "call_booneops_broker", fake_broker)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "export that as csv"},
    )

    assert response.status_code == 303
    assert captured.get("route_label") == "docs_candidate"


def test_fetch_html_followup_writes_file_safe_href(monkeypatch, tmp_path: Path) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="HTML lane")
    repo = FetchRepository(db.connection)

    repo.append_message(
        user_id,
        conv.conversation_id,
        role="assistant",
        content="Line **one**\n<script>evil()</script>",
        route_key="printsmith_candidate",
        context_state="booneops",
    )

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net").model_copy(
        update={"retriever_report_dir": tmp_path}
    )
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def boom_broker(*_a: object, **_k: object) -> BooneOpsBrokerTurnResult:
        raise AssertionError("HTML export must not call BooneOps broker")

    monkeypatch.setattr(fetch_routes, "call_booneops_broker", boom_broker)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "can you export that as an html file?"},
    )

    assert response.status_code == 303
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    m = re.search(r'href="(/fetch/artifacts/html/[a-f0-9]{32}\.html)"', page.text)
    assert m is not None
    dl = safe_fetch_download_href(m.group(1))
    assert dl == m.group(1)

    export_dir = tmp_path / "fetch_html_exports"
    assert export_dir.is_dir()
    exported = list(export_dir.glob("*.html"))
    assert len(exported) == 1
    body = exported[0].read_text(encoding="utf-8").lower()
    assert "<script" not in body
    assert "line" in body

    file_response = client.get(m.group(1))
    assert file_response.status_code == 200
    assert "text/html" in file_response.headers.get("content-type", "")

    raw_meta = db.fetch_messages[-1]["metadata_json"]
    assert raw_meta is not None
    stored = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
    art0 = stored["artifacts"][0]
    assert "expiresAtUtc" in art0
    assert "issuedAtUtc" in art0
    assert art0.get("storageScope") == "retriever_local"


def test_fetch_html_followup_cold_start_no_export_no_broker(monkeypatch, tmp_path: Path) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Cold html")

    settings = make_fetch_broker_enabled_settings(email="fetcher@boonegraphics.net").model_copy(
        update={"retriever_report_dir": tmp_path}
    )
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def boom_broker(*_a: object, **_k: object) -> BooneOpsBrokerTurnResult:
        raise AssertionError("broker must not run for HTML cold export")

    monkeypatch.setattr(fetch_routes, "call_booneops_broker", boom_broker)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "please export this as html"},
    )

    assert response.status_code == 303
    assert "need" in db.fetch_messages[-1]["content"].lower()
    assert db.fetch_messages[-1]["route_key"] == "fetch_html_export"
    export_dir = tmp_path / "fetch_html_exports"
    assert not export_dir.exists() or len(list(export_dir.glob("*.html"))) == 0


def test_fetch_pdf_answer_snapshot_followup_writes_pdf_safe_href(monkeypatch, tmp_path: Path) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="PDF lane")

    FetchRepository(db.connection).append_message(
        user_id,
        conv.conversation_id,
        role="assistant",
        content="Totals **bold**.",
        route_key="printsmith_candidate",
        context_state="booneops",
    )

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net").model_copy(
        update={"retriever_report_dir": tmp_path}
    )
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(
        fetch_routes,
        "convert_html_export_document_to_pdf",
        lambda _html, **_kwargs: (b"%PDF-1.4 mocked\n", None),
    )

    def boom_broker(*_a: object, **_k: object) -> BooneOpsBrokerTurnResult:
        raise AssertionError("answer-snapshot PDF must not call BooneOps broker")

    monkeypatch.setattr(fetch_routes, "call_booneops_broker", boom_broker)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "please save this answer as a PDF"},
    )
    assert response.status_code == 303
    page = client.get(response.headers["location"])
    assert page.status_code == 200
    m = re.search(r'href="(/fetch/artifacts/pdf/[a-f0-9]{32}\.pdf)"', page.text)
    assert m is not None
    assert safe_fetch_download_href(m.group(1)) == m.group(1)

    export_dir = tmp_path / "fetch_html_exports"
    pdfs = list(export_dir.glob("*.pdf"))
    assert len(pdfs) == 1

    file_response = client.get(m.group(1))
    assert file_response.status_code == 200
    ctype = file_response.headers.get("content-type", "").lower()
    assert "pdf" in ctype or "octet-stream" in ctype

    raw_meta = db.fetch_messages[-1]["metadata_json"]
    assert raw_meta is not None
    stored = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
    art0 = stored["artifacts"][0]
    assert "expiresAtUtc" in art0
    assert "issuedAtUtc" in art0
    assert art0.get("storageScope") == "retriever_local"
    assert db.fetch_messages[-1]["route_key"] == "fetch_pdf_export"


def test_fetch_export_that_as_pdf_still_invokes_broker_route(monkeypatch, tmp_path: Path) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Broker PDF")

    FetchRepository(db.connection).append_message(
        user_id,
        conv.conversation_id,
        role="assistant",
        content="Here is your report.",
        route_key="printsmith_candidate",
        context_state="booneops",
    )

    settings = make_fetch_broker_enabled_settings(email="fetcher@boonegraphics.net").model_copy(
        update={"retriever_report_dir": tmp_path}
    )
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    captured: dict[str, object] = {}

    def fake_broker(
        _settings: AppSettings,
        *,
        route_label: str,
        **_kw: object,
    ) -> BooneOpsBrokerTurnResult:
        captured["route_label"] = route_label
        return BooneOpsBrokerTurnResult("PDF attached.", "booneops")

    monkeypatch.setattr(fetch_routes, "call_booneops_broker", fake_broker)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "can you export that as a pdf file?"},
    )
    assert response.status_code == 303
    assert captured.get("route_label") == "printsmith_candidate"
    assert db.fetch_messages[-2]["route_key"] == "printsmith_candidate"


def test_fetch_pdf_export_route_returns_404_when_file_missing(monkeypatch, tmp_path: Path) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net").model_copy(
        update={"retriever_report_dir": tmp_path}
    )
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    client = make_client(settings)
    ghost = uuid.uuid4().hex
    assert client.get(f"/fetch/artifacts/pdf/{ghost}.pdf").status_code == 404


def test_fetch_shell_hides_missing_local_pdf_artifact(monkeypatch, tmp_path: Path) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Ghost pdf")
    stem = uuid.uuid4().hex
    path = f"/fetch/artifacts/pdf/{stem}.pdf"
    FetchRepository(db.connection).append_message(
        user_id,
        conv.conversation_id,
        role="assistant",
        content="Saved PDF snapshot.",
        route_key="fetch_pdf_export",
        context_state="ready",
        metadata={
            "artifacts": [
                {
                    "filename": "fetch-answer-export.pdf",
                    "description": "local",
                    "downloadPath": path,
                    "expiresAtUtc": "2099-01-01T00:00:00Z",
                }
            ]
        },
    )

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net").model_copy(
        update={"retriever_report_dir": tmp_path}
    )
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    client = make_client(settings)
    page = client.get(f"/fetch?c={conv.conversation_id}")
    assert page.status_code == 200
    assert "fetch-answer-export.pdf" not in page.text
    assert 'class="fetch-artifact-dl"' not in page.text


def test_fetch_shell_hides_missing_local_html_artifact_card(monkeypatch, tmp_path: Path) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Ghost html")
    repo = FetchRepository(db.connection)
    stem = uuid.uuid4().hex
    path = f"/fetch/artifacts/html/{stem}.html"
    repo.append_message(
        user_id,
        conv.conversation_id,
        role="assistant",
        content="I saved an HTML snapshot of your previous Fetch answer.",
        route_key="fetch_html_export",
        context_state="ready",
        metadata={
            "artifacts": [
                {
                    "filename": "fetch-answer-export.html",
                    "description": "Sanitized standalone HTML snapshot of the prior answer.",
                    "downloadPath": path,
                    "expiresAtUtc": "2099-01-01T00:00:00Z",
                }
            ]
        },
    )

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net").model_copy(
        update={"retriever_report_dir": tmp_path}
    )
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    client = make_client(settings)
    page = client.get(f"/fetch?c={conv.conversation_id}")
    assert page.status_code == 200
    assert "fetch-answer-export.html" not in page.text
    assert 'class="fetch-artifact-dl"' not in page.text
    assert "expired" not in page.text.lower()


def test_fetch_shell_hides_expired_local_html_artifact_card(monkeypatch, tmp_path: Path) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Stale html")
    repo = FetchRepository(db.connection)
    stem = uuid.uuid4().hex
    export_dir = tmp_path / "fetch_html_exports"
    export_dir.mkdir(parents=True)
    (export_dir / f"{stem}.html").write_text("<html><body>x</body></html>", encoding="utf-8")
    path = f"/fetch/artifacts/html/{stem}.html"
    repo.append_message(
        user_id,
        conv.conversation_id,
        role="assistant",
        content="I saved an HTML snapshot of your previous Fetch answer.",
        route_key="fetch_html_export",
        context_state="ready",
        metadata={
            "artifacts": [
                {
                    "filename": "fetch-answer-export.html",
                    "downloadPath": path,
                    "expiresAtUtc": "2000-01-01T00:00:00Z",
                }
            ]
        },
    )

    settings = make_fetch_enabled_settings(email="fetcher@boonegraphics.net").model_copy(
        update={"retriever_report_dir": tmp_path}
    )
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    client = make_client(settings)
    page = client.get(f"/fetch?c={conv.conversation_id}")
    assert page.status_code == 200
    assert "fetch-answer-export.html" not in page.text
    assert 'class="fetch-artifact-dl"' not in page.text
    assert "expired" not in page.text.lower()


def test_fetch_export_followup_after_general_stub_does_not_call_broker(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="General lane")
    repo = FetchRepository(db.connection)

    repo.append_message(
        user_id,
        conv.conversation_id,
        role="user",
        content="What is the meaning of life?",
        route_key="general_candidate",
    )
    repo.append_message(
        user_id,
        conv.conversation_id,
        role="assistant",
        content="stub body",
        route_key="general_candidate",
        context_state="stub",
    )

    settings = make_fetch_broker_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def _no_http(*_a: object, **_k: object) -> None:
        raise AssertionError("Fetch ask must use broker client")

    monkeypatch.setattr(httpx, "get", _no_http)
    monkeypatch.setattr(httpx, "post", _no_http)
    monkeypatch.setattr(httpx, "request", _no_http)

    def boom_broker(*_a: object, **_k: object) -> BooneOpsBrokerTurnResult:
        raise AssertionError("broker must not run for uninheritable export follow-ups")

    monkeypatch.setattr(fetch_routes, "call_booneops_broker", boom_broker)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "download that as excel"},
    )

    assert response.status_code == 303
    assert db.fetch_messages[-1]["context_state"] == "stub"


def test_fetch_export_followup_new_thread_does_not_call_broker(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("fetcher@boonegraphics.net", "Fetcher User", "active")
    user_id = db.users["fetcher@boonegraphics.net"]["id"]
    db.modules_by_user.setdefault(user_id, set()).add("fetch")
    db.capabilities_by_user.setdefault(user_id, set()).add("fetch.ask_internal")
    conv = FetchRepository(db.connection).create_conversation(user_id=user_id, title="Cold export")

    settings = make_fetch_broker_enabled_settings(email="fetcher@boonegraphics.net")
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(fetch_routes, "create_connection", lambda _: db.connection())

    def _no_http(*_a: object, **_k: object) -> None:
        raise AssertionError("unexpected outbound HTTP from fetch ask")

    monkeypatch.setattr(httpx, "get", _no_http)
    monkeypatch.setattr(httpx, "post", _no_http)
    monkeypatch.setattr(httpx, "request", _no_http)

    def boom_broker(*_a: object, **_k: object) -> BooneOpsBrokerTurnResult:
        raise AssertionError("broker must not run without inheritable broker context")

    monkeypatch.setattr(fetch_routes, "call_booneops_broker", boom_broker)

    client = make_client(settings)
    response = client.post(
        f"/fetch/conversations/{conv.conversation_id}/ask",
        data={"question": "export as pdf"},
    )

    assert response.status_code == 303
    assert db.fetch_messages[-1]["route_key"] == "unknown"


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
    assert "pending@boonegraphics.net" in response.text
    assert "Cloudflare Email Auth" in response.text
    assert "Last Login" in response.text
    assert "Pending" in response.text
    assert "Inventory" in response.text
    assert "Proofs" in response.text
    assert "00/Scott - Working" in response.text
    assert ">Save<" in response.text
    assert ">Block<" not in response.text


def test_seed_admin_can_load_prepress_shell_without_db() -> None:
    client = make_client(make_settings())

    response = client.get("/prepress/")

    assert response.status_code == 200
    assert "PrePress WIP" in response.text
    assert "hx-get=\"/prepress/partials/wip-table\"" in response.text
    assert "ppToast(j.message || (j.ok ? \"Saved.\" : \"Save failed.\")" in response.text
    assert "Save failed on the server." in response.text
    assert "target: \"#parts-\" + invoiceNumber" in response.text


def test_active_user_without_prepress_is_forbidden(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("plain@boonegraphics.net", "Plain User", "active")
    db.add_user("state@boonegraphics.net", "Master Tate", "active", is_seed_admin=True)
    settings = make_settings(email="plain@boonegraphics.net", with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.get("/prepress/")

    assert response.status_code == 403


def test_admin_suspend_self_returns_400(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("state@boonegraphics.net", "Master Tate", "active", is_seed_admin=True)
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(admin_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post("/admin/users/1/suspend")

    assert response.status_code == 400


def test_admin_block_self_returns_400(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("state@boonegraphics.net", "Master Tate", "active", is_seed_admin=True)
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(admin_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post("/admin/users/1/block")

    assert response.status_code == 400


def test_admin_delete_self_returns_400(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("state@boonegraphics.net", "Master Tate", "active", is_seed_admin=True)
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(admin_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post("/admin/users/1/delete")

    assert response.status_code == 400


def test_admin_delete_user_removes_profile(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("active@boonegraphics.net", "Active User", "active", full_name="Active User")
    db.add_user("state@boonegraphics.net", "Master Tate", "active", is_seed_admin=True)
    db.modules_by_user[1] = {"fetch"}
    db.capabilities_by_user[1] = {"fetch.access"}
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(admin_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post("/admin/users/1/delete")

    assert response.status_code == 303
    assert "active@boonegraphics.net" not in db.users
    assert db.modules_by_user.get(1) is None
    assert db.capabilities_by_user.get(1) is None
    assert ("user", 1) in db.revoked_sessions


def test_admin_matrix_update_applies_entitlements(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("active@boonegraphics.net", "Active User", "active")
    db.add_user("state@boonegraphics.net", "Master Tate", "active", is_seed_admin=True)
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(admin_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post(
        "/admin/users/1/matrix-update",
        data={
            "full_name": "Web Orders",
            "production_location_choice": "1|00/Scott - Working",
            "admin_module": "false",
            "fetch_module": "true",
            "fetch_access": "true",
            "prepress_module": "true",
            "dsf_module": "false",
            "inventory_level": "viewer",
            "proofs_level": "manager",
        },
    )

    assert response.status_code == 303
    assert db.user_by_id(1)["full_name"] == "Web Orders"
    assert db.user_by_id(1)["production_location_id"] == 1
    assert db.user_by_id(1)["production_location_name"] == "00/Scott - Working"
    assert "fetch" in db.modules_by_user.get(1, set())
    assert "prepress" in db.modules_by_user.get(1, set())
    assert "fetch.access" in db.capabilities_by_user.get(1, set())
    assert "prepress.access" in db.capabilities_by_user.get(1, set())
    assert db.user_by_id(1)["inventory_level"] == "viewer"
    assert db.user_by_id(1)["proofs_level"] == "manager"
    assert "inventory" in db.modules_by_user.get(1, set())
    assert "proofs" in db.modules_by_user.get(1, set())


def test_admin_matrix_update_can_grant_admin(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("active@boonegraphics.net", "Active User", "active")
    db.add_user("state@boonegraphics.net", "Master Tate", "active", is_seed_admin=True)
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(admin_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post(
        "/admin/users/1/matrix-update",
        data={
            "full_name": "Active Admin",
            "production_location_choice": "",
            "admin_module": "true",
            "fetch_module": "false",
            "fetch_access": "false",
            "prepress_module": "false",
            "dsf_module": "false",
            "inventory_level": "no",
            "proofs_level": "no",
        },
    )

    assert response.status_code == 303
    assert db.user_by_id(1)["role_key"] == "owner_admin"
    assert "admin" in db.modules_by_user.get(1, set())
    assert "admin.manage_users" in db.capabilities_by_user.get(1, set())
    assert "booneops.admin" in db.capabilities_by_user.get(1, set())


def test_admin_matrix_update_allows_seed_location_but_preserves_admin(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("state@boonegraphics.net", "Master Tate", "active", is_seed_admin=True)
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(admin_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post(
        "/admin/users/1/matrix-update",
        data={
            "full_name": "Scott Tate",
            "production_location_choice": "1|100/Scott Working",
            "admin_module": "false",
            "fetch_module": "false",
            "fetch_access": "false",
            "prepress_module": "false",
            "dsf_module": "false",
            "inventory_level": "no",
            "proofs_level": "no",
        },
    )

    assert response.status_code == 303
    assert db.user_by_id(1)["full_name"] == "Scott Tate"
    assert db.user_by_id(1)["production_location_id"] == 1
    assert db.user_by_id(1)["production_location_name"] == "100/Scott Working"
    assert db.user_by_id(1)["role_key"] == "owner_admin"
    assert "admin" in db.modules_by_user.get(1, set())
    assert "admin.manage_users" in db.capabilities_by_user.get(1, set())


def test_admin_activate_post_updates_user_and_redirects(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("pending@boonegraphics.net", "Pending User", "pending", full_name="Pending User")
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(admin_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post("/admin/users/1/activate")

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/users"
    assert db.user_by_id(1)["status"] == "active"
    assert len(db.audit_events) == 1


def test_admin_activate_requires_full_name(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("pending@boonegraphics.net", "Pending User", "pending")
    settings = make_settings(with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(admin_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post("/admin/users/1/activate")

    assert response.status_code == 400
    assert db.user_by_id(1)["status"] == "pending"


def test_admin_direct_entitlement_endpoint_rejects_seed_row(monkeypatch) -> None:
    db = FakeDb()
    db.add_user("state@boonegraphics.net", "Master Tate", "active", is_seed_admin=True)
    db.add_user("admin@boonegraphics.net", "Admin User", "active", is_seed_admin=True)
    settings = make_settings(email="admin@boonegraphics.net", with_db=True)
    monkeypatch.setattr(session_module, "create_connection", lambda _: db.connection())
    monkeypatch.setattr(admin_routes, "create_connection", lambda _: db.connection())
    client = make_client(settings)

    response = client.post("/admin/users/1/role", data={"role_key": "viewer"})

    assert response.status_code == 400
    assert db.user_by_id(1)["role_key"] == "owner_admin"


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
    assert db.user_by_id(1)["last_seen_at"] is not None


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
    assert db.user_by_id(1)["last_seen_at"] is not None


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
