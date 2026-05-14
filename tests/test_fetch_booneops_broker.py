"""BooneOps broker client: signing, formatting, and mocked HTTP."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import hmac
import json
import logging

import httpx
import pytest

from app.auth.permissions import CurrentUser
from app.config import AppSettings
from app.db.repositories.fetch import FetchMessageRecord
from app.fetch.booneops_broker import (
    augment_broker_user_message_for_route,
    augment_fetch_broker_user_message_for_turn,
    broker_message_url,
    build_broker_message_presentation,
    call_booneops_broker,
    format_assistant_text_from_broker_json,
    map_user_to_broker_principal,
    normalize_and_validate_booneops_artifact_id,
    sanitized_broker_error_summary,
    sign_body_hmac_sha256,
    strip_redundant_markdown_sources_section,
)
from app.fetch.followup_routing import resolve_fetch_ask_route
from app.fetch.local_routing import should_delegate_ask_to_booneops_broker
from app.fetch.safe_links import safe_fetch_download_href


def _make_settings() -> AppSettings:
    return AppSettings(
        retriever_env="local",
        fetch_enabled=True,
        model_provider="anthropic",
        anthropic_api_key="test-key",
        model_default="claude-test",
        booneops_broker_enabled=True,
        booneops_broker_url="http://broker.example:3487",
        booneops_broker_bearer_token="unit-test-bearer",
        booneops_broker_hmac_secret="unit-test-hmac",
    )


def _make_user(**kwargs: object) -> CurrentUser:
    base = CurrentUser(
        id=42,
        email="worker@boonegraphics.net",
        display_name="Worker",
        status="active",
        capabilities=frozenset({"fetch.ask_internal"}),
        modules=frozenset({"fetch"}),
        is_admin=False,
        booneops_level="light",
    )
    if not kwargs:
        return base
    fields = {k: v for k, v in kwargs.items() if k in CurrentUser.__dataclass_fields__}
    return replace(base, **fields)


def test_sign_body_hmac_sha256_matches_raw_bytes() -> None:
    secret = "signing-secret"
    body = b'{"botId":"booneops.production","message":"ping"}'
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    assert sign_body_hmac_sha256(body, secret) == expected


def test_broker_message_url_joins_path() -> None:
    s = _make_settings()
    assert broker_message_url(s) == "http://broker.example:3487/v1/booneops/message"


def test_map_user_to_broker_principal() -> None:
    assert map_user_to_broker_principal(_make_user()) == ("booneops.production", "production")
    assert map_user_to_broker_principal(_make_user(booneops_level="medium")) == (
        "booneops.super",
        "super",
    )
    assert map_user_to_broker_principal(_make_user(is_admin=True)) == ("booneops.admin", "admin")


def test_should_delegate_printsmith_and_docs_only_by_default() -> None:
    s = _make_settings()
    assert should_delegate_ask_to_booneops_broker("printsmith_candidate", s) is True
    assert should_delegate_ask_to_booneops_broker("docs_candidate", s) is True
    assert should_delegate_ask_to_booneops_broker("general_candidate", s) is False
    assert should_delegate_ask_to_booneops_broker("local", s) is False


def test_should_delegate_general_when_admin_toggle_on() -> None:
    s = _make_settings()
    s = s.model_copy(update={"fetch_general_questions_enabled": True})
    assert should_delegate_ask_to_booneops_broker("general_candidate", s) is True


def test_should_delegate_off_when_broker_disabled() -> None:
    s = _make_settings()
    s = s.model_copy(update={"booneops_broker_enabled": False})
    assert should_delegate_ask_to_booneops_broker("printsmith_candidate", s) is False


@pytest.mark.parametrize(
    ("payload", "expect_substr"),
    [
        (
            {"ok": False, "errors": [{"code": "x", "message": "Export needs context"}]},
            "Export needs context",
        ),
        (
            {
                "ok": True,
                "message": "Here is the answer.",
                "errors": [],
                "artifacts": [
                    {"filename": "out.csv", "artifactId": "art-1"},
                ],
            },
            "Attachments:",
        ),
    ],
)
def test_format_assistant_only_uses_safe_fields(payload: dict, expect_substr: str) -> None:
    payload["booneops_broker_bearer_token"] = "evil-leak"
    text = format_assistant_text_from_broker_json(payload)
    assert expect_substr in text
    assert "evil-leak" not in text
    assert "Bearer" not in text


def test_strip_redundant_markdown_sources_section_noop_without_cards() -> None:
    body = "### Sources\n\n- x\n"
    assert strip_redundant_markdown_sources_section(body, []) == body


def test_strip_redundant_markdown_sources_section_removes_sources_block() -> None:
    body = "Answer line.\n\n### Sources\n\n- [One](https://a.example)\n"
    cards = [{"title": "One", "url": "https://a.example"}]
    out = strip_redundant_markdown_sources_section(body, cards)
    assert "Answer line" in out
    assert "### Sources" not in out


def test_strip_redundant_markdown_sources_section_stops_at_next_heading() -> None:
    body = "Intro\n\n## Sources\n\n- a\n\n## See also\n\nMore text\n"
    cards = [{"title": "Doc", "url": "https://d"}]
    out = strip_redundant_markdown_sources_section(body, cards)
    assert "Intro" in out
    assert "## See also" in out
    assert "More text" in out
    assert "## Sources" not in out


def test_build_broker_message_presentation_strips_inline_sources_when_cards_present() -> None:
    raw = (
        "First paragraph is the intro with enough length to trigger shaping heuristics. " * 8
        + "\n\n1. One step\n2. Two steps\n\n"
        + "### Sources\n\n- [Guide](https://docs/switch)\n"
    )
    text, metadata = build_broker_message_presentation(
        {
            "ok": True,
            "message": raw,
            "sources": [
                {"kind": "docs", "title": "Guide", "url": "https://docs/switch"},
            ],
        },
        "docs_candidate",
    )
    assert metadata.get("source_cards")
    assert "### Sources" not in text
    assert "https://docs/switch" not in text


def test_build_broker_message_presentation_adds_docs_summary_steps_and_source_cards() -> None:
    raw = (
        "Switch flow elements process jobs from left to right.\n\n"
        "1. Open Switch Designer.\n"
        "2. Connect flow elements left to right.\n"
        "3. Use private data keys when scripts need state.\n\n" + ("Detailed paragraph " * 40)
    )
    text, metadata = build_broker_message_presentation(
        {
            "ok": True,
            "message": raw,
            "requestId": "req-docs",
            "sources": [
                {
                    "kind": "docs",
                    "title": "Switch Scripting Guide",
                    "description": "Script element reference",
                    "url": "/docs/switch-script-guide",
                }
            ],
        },
        "docs_candidate",
    )

    assert text.startswith("Summary\n")
    assert "\nSteps\n" in text
    assert "\nDetails\n" in text
    assert metadata["request_id"] == "req-docs"
    assert metadata["source_cards"][0]["title"] == "Switch Scripting Guide"
    assert metadata["source_cards"][0]["url"] == "/docs/switch-script-guide"
    assert "detail" not in metadata["source_cards"][0]


def test_build_broker_message_presentation_keeps_mcp_markdown_headings_for_fetch_docs() -> None:
    """MCP employee docs ship **## Summary** / **### Sources**; avoid re-splitting into Summary/Details."""
    raw = (
        "## Summary\n\n"
        "In **uCreate Print**, table ADOR maps to **Table Content Object**.\n\n"
        "| You say | Help |\n| --- | --- |\n| Table ADOR | Table Content Object |\n\n"
        "### Practical steps\n\n"
        "1. Tag the frame\n2. Bind columns\n\n"
        "### Sources\n\n"
        "- **[Doc](https://help.xmpie.com/uCreatePrint/Latest/Help/en/Tagging/"
        "Tagging_a_Design_Object_with_a_Table_Content_Object.htm)**"
    )
    text, metadata = build_broker_message_presentation({"ok": True, "message": raw}, "docs_candidate")
    assert text.startswith("## Summary")
    assert "\nDetails\n" not in text
    assert "Summary\n## Summary" not in text
    assert "### Sources" in text
    assert metadata.get("source_cards") is None


def test_build_broker_message_presentation_suppresses_help_chrome_in_details() -> None:
    raw = (
        "First paragraph is the intro with enough length to trigger shaping heuristics. " * 8
        + "\n\n"
        + "1. One step here\n2. Two steps here\n\n"
        + "You are here: Home / Docs\n\nMore body."
    )
    text, _metadata = build_broker_message_presentation({"ok": True, "message": raw}, "docs_candidate")
    assert "You are here:" not in text
    assert "\nDetails\n" not in text


@pytest.mark.parametrize(
    "dirty_tail",
    (
        "Chrome link uses javascript:history.back(0) in the scraped footer.",
        "Portal nav: My Account | Sign out | Help",
        "Forgot your password? Reset it from the login page.",
    ),
)
def test_build_broker_message_presentation_suppresses_details_for_js_and_auth_chrome(
    dirty_tail: str,
) -> None:
    """Details that still look like help-site chrome (JS URLs, account/sign-in boilerplate) are dropped."""
    raw = (
        "First paragraph is the intro with enough length to trigger shaping heuristics. " * 8
        + "\n\n"
        + "1. One step here\n2. Two steps here\n\n"
        + dirty_tail
    )
    text, _metadata = build_broker_message_presentation({"ok": True, "message": raw}, "docs_candidate")
    assert "\nDetails\n" not in text


def test_build_broker_message_presentation_docs_route_has_no_synthetic_source_cards() -> None:
    text, metadata = build_broker_message_presentation(
        {"ok": True, "message": "Short docs answer."},
        "docs_candidate",
    )

    assert text == "Short docs answer."
    assert "source_cards" not in metadata


def test_build_broker_message_presentation_preserves_report_context() -> None:
    ctx = {
        "reportSpec": {"title": "Sales", "chartType": "bar"},
        "exportColumns": ["rep", "total"],
        "exportRows": [{"rep": "A", "total": 10}],
    }
    _, metadata = build_broker_message_presentation(
        {"ok": True, "message": "Here is your export.", "reportContext": ctx},
        "printsmith_candidate",
    )
    assert metadata["reportContext"] == ctx


def test_build_broker_message_presentation_normalizes_snake_case_report_context() -> None:
    ctx = {"exportRows": [{"x": 1}]}
    _, metadata = build_broker_message_presentation(
        {"ok": True, "message": "Done.", "report_context": ctx},
        "printsmith_candidate",
    )
    assert metadata["reportContext"] == ctx
    assert "report_context" not in metadata


def test_build_broker_message_presentation_does_not_persist_huge_report_context(caplog) -> None:
    huge = {"blob": "x" * 900_000}
    _, metadata = build_broker_message_presentation(
        {"ok": True, "message": "Totals attached.", "reportContext": huge},
        "printsmith_candidate",
    )
    assert "reportContext" not in metadata
    assert any("exceeds" in r.message for r in caplog.records)


def test_fancy_excel_followup_broker_payload_includes_saved_report_context(monkeypatch) -> None:
    """After a broker turn stored reportContext, styling language merges it into sessionMetadata."""
    prior_ctx = {
        "reportSpec": {"title": "Q1"},
        "exportColumns": ["invoice"],
        "exportRows": [{"invoice": "104446"}],
    }
    prior = [
        FetchMessageRecord(
            message_id="m1",
            conversation_id="c",
            user_id=1,
            role="assistant",
            content="Excel attached.",
            route_key="printsmith_candidate",
            context_state="booneops",
            metadata={"reportContext": prior_ctx, "artifacts": []},
        ),
    ]
    phrase = (
        "Can you fancy up the excel file and maybe add some bolding and colorful headers?"
    )
    _route, extra = resolve_fetch_ask_route(phrase, "general_candidate", prior)
    assert extra.get("reportStyle") == "basic_styled_excel"
    assert extra.get("reportContext") == prior_ctx

    settings = _make_settings()
    user = _make_user()
    captured: dict = {}

    def fake_post(url: str, *, content: bytes, headers: dict[str, str], timeout: float):
        captured["content"] = content

        class Resp:
            status_code = 200
            content = b'{"ok":true,"message":"ok","errors":[]}'

            def json(self):
                return json.loads(self.content.decode())

        return Resp()

    monkeypatch.setattr("app.fetch.booneops_broker.default_http_post", fake_post)
    call_booneops_broker(
        settings,
        user=user,
        conversation_id="conv-1",
        user_message=phrase,
        route_label=_route,
        request_id="req-style",
        prior_messages=[],
        session_metadata_extra=extra,
        http_post=None,
    )
    payload = json.loads(captured["content"].decode())
    sm = payload["sessionMetadata"]
    assert sm["reportStyle"] == "basic_styled_excel"
    assert sm["reportContext"] == prior_ctx


def test_augment_fetch_broker_user_message_wraps_basic_styled_excel_followups() -> None:
    raw = "bold headers please"
    wrapped = augment_fetch_broker_user_message_for_turn(
        raw,
        "printsmith_candidate",
        {"reportStyle": "basic_styled_excel"},
    )
    assert "[Retriever follow-up: basic styled Excel]" in wrapped
    assert "User wording: bold headers please" in wrapped
    docs = augment_fetch_broker_user_message_for_turn(
        raw,
        "docs_candidate",
        {"reportStyle": "basic_styled_excel"},
    )
    assert "[Retriever follow-up: basic styled Excel]" in docs
    assert "[Retriever docs route]" not in docs
    assert "sourceCards" not in docs
    assert "Lead with a short Summary" not in docs


def test_augment_broker_user_message_leaves_user_text_untouched_by_route() -> None:
    q = "How does uPlan proofing work?"
    assert augment_broker_user_message_for_route(q, "printsmith_candidate") == q
    assert augment_broker_user_message_for_route(q, "docs_candidate") == q


def test_build_broker_message_presentation_truncates_long_source_title_only() -> None:
    long_title = "T" * 200
    _, metadata = build_broker_message_presentation(
        {
            "ok": True,
            "message": "Answer.",
            "sources": [
                {
                    "title": long_title,
                    "description": "should not appear in metadata",
                    "url": "/docs/x",
                }
            ],
        },
        "docs_candidate",
    )
    card = metadata["source_cards"][0]
    assert len(card["title"]) == 140
    assert "detail" not in card


def test_call_booneops_broker_sends_signature_headers(monkeypatch) -> None:
    settings = _make_settings()
    user = _make_user()
    captured: dict = {}

    def fake_post(url: str, *, content: bytes, headers: dict[str, str], timeout: float):
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        captured["timeout"] = timeout

        class Resp:
            status_code = 200
            content = (
                b'{"ok":true,"message":"Broker ok","errors":[],'
                b'"actionsTaken":[{"type":"execution.forwarded","status":"executed"}]}'
            )

            def json(self):
                return json.loads(self.content.decode())

        return Resp()

    monkeypatch.setattr(
        "app.fetch.booneops_broker.default_http_post",
        fake_post,
    )
    result = call_booneops_broker(
        settings,
        user=user,
        conversation_id="conv-1",
        user_message="What is DSF?",
        route_label="printsmith_candidate",
        request_id="req-fixed",
        prior_messages=[],
        http_post=None,
    )

    assert result.assistant_text == "Broker ok"
    assert result.context_state == "booneops"
    assert result.metadata.get("booneops_actions") == ["execution.forwarded"]
    headers = captured["headers"]
    assert headers["Authorization"] == "Bearer unit-test-bearer"
    sig = headers["X-BooneOps-Signature"]
    assert sig.startswith("sha256=")
    body = captured["content"]
    assert sign_body_hmac_sha256(body, "unit-test-hmac") == sig
    assert headers["X-Correlation-Id"] == "req-fixed"
    payload = json.loads(body.decode())
    assert payload["requestId"] == "req-fixed"
    assert payload["sessionMetadata"]["routeLabel"] == "printsmith_candidate"
    assert payload["sessionMetadata"].get("retrieverDiscordAnswerParity") is True
    assert "unit-test-bearer" not in result.assistant_text
    assert "unit-test-hmac" not in result.assistant_text


def test_call_booneops_broker_payload_strips_forced_slash_prefix(monkeypatch) -> None:
    settings = _make_settings()
    user = _make_user()
    captured: dict = {}

    def fake_post(url: str, *, content: bytes, headers: dict[str, str], timeout: float):
        captured["content"] = content

        class Resp:
            status_code = 200
            content = b'{"ok":true,"message":"ok","errors":[]}'

            def json(self):
                return json.loads(self.content.decode())

        return Resp()

    monkeypatch.setattr("app.fetch.booneops_broker.default_http_post", fake_post)
    call_booneops_broker(
        settings,
        user=user,
        conversation_id="conv-1",
        user_message="/docs  Switch checkpoints",
        route_label="docs_candidate",
        request_id="req-strip",
        prior_messages=[],
        http_post=None,
    )
    payload = json.loads(captured["content"].decode())
    assert payload["message"] == "Switch checkpoints"

    call_booneops_broker(
        settings,
        user=user,
        conversation_id="conv-1",
        user_message="/printsmith",
        route_label="printsmith_candidate",
        request_id="req-strip2",
        prior_messages=[],
        http_post=None,
    )
    payload2 = json.loads(captured["content"].decode())
    assert payload2["message"] == "PrintSmith shop data question."


def test_call_booneops_broker_merges_session_metadata_extra(monkeypatch) -> None:
    settings = _make_settings()
    user = _make_user()
    captured: dict = {}

    def fake_post(url: str, *, content: bytes, headers: dict[str, str], timeout: float):
        captured["content"] = content

        class Resp:
            status_code = 200
            content = b'{"ok":true,"message":"ok","errors":[]}'

            def json(self):
                return json.loads(self.content.decode())

        return Resp()

    monkeypatch.setattr("app.fetch.booneops_broker.default_http_post", fake_post)
    call_booneops_broker(
        settings,
        user=user,
        conversation_id="conv-1",
        user_message="export pdf",
        route_label="printsmith_candidate",
        request_id="req-meta",
        prior_messages=[],
        session_metadata_extra={"reportContext": {"rid": "7"}},
        http_post=None,
    )
    payload = json.loads(captured["content"].decode())
    assert payload["sessionMetadata"]["routeLabel"] == "printsmith_candidate"
    assert payload["sessionMetadata"]["reportContext"] == {"rid": "7"}


def test_call_booneops_broker_docs_route_keeps_user_message_clean_and_sets_guidance_metadata(
    monkeypatch,
) -> None:
    settings = _make_settings()
    user = _make_user()
    captured: dict = {}

    def fake_post(url: str, *, content: bytes, headers: dict[str, str], timeout: float):
        captured["content"] = content

        class Resp:
            status_code = 200
            content = b'{"ok":true,"message":"ok","errors":[]}'

            def json(self):
                return json.loads(self.content.decode())

        return Resp()

    monkeypatch.setattr("app.fetch.booneops_broker.default_http_post", fake_post)
    user_q = "read the Switch manual"
    call_booneops_broker(
        settings,
        user=user,
        conversation_id="conv-1",
        user_message=user_q,
        route_label="docs_candidate",
        request_id="req-docs-augment",
        prior_messages=[],
        http_post=None,
    )
    payload = json.loads(captured["content"].decode())
    assert payload["message"] == user_q
    sm = payload["sessionMetadata"]
    assert sm["retrieverDocsPresentationGuidance"].startswith("Lead with a short Summary")
    assert "sourceCards" in sm["retrieverDocsPresentationGuidance"]
    forbidden_in_message = (
        "[Retriever docs route]",
        "retrieverDocsPresentationGuidance",
        "sourceCards",
        "Lead with a short Summary",
    )
    for fs in forbidden_in_message:
        assert fs not in payload["message"]


@pytest.mark.parametrize("route_label", ("printsmith_candidate", "general_candidate"))
def test_call_booneops_broker_non_docs_route_has_no_presentation_guidance_metadata(
    monkeypatch, route_label: str
) -> None:
    settings = _make_settings()
    captured: dict = {}

    def fake_post(url: str, *, content: bytes, headers: dict[str, str], timeout: float):
        captured["content"] = content

        class Resp:
            status_code = 200
            content = b'{"ok":true,"message":"ok","errors":[]}'

            def json(self):
                return json.loads(self.content.decode())

        return Resp()

    monkeypatch.setattr("app.fetch.booneops_broker.default_http_post", fake_post)
    call_booneops_broker(
        settings,
        user=_make_user(),
        conversation_id="conv-1",
        user_message="hello",
        route_label=route_label,
        request_id="req-x",
        prior_messages=[],
        http_post=None,
    )
    payload = json.loads(captured["content"].decode())
    assert "retrieverDocsPresentationGuidance" not in payload.get("sessionMetadata", {})


def test_sanitized_broker_error_summary_prefers_errors0_over_error() -> None:
    code, msg, keys = sanitized_broker_error_summary(
        {
            "ok": False,
            "error": {"code": "from_error", "message": "e"},
            "errors": [{"code": "from_list", "message": "first"}],
        }
    )
    assert code == "from_list"
    assert msg == "first"
    assert keys == []


def test_sanitized_broker_error_summary_reads_error_object_and_detail_keys_only() -> None:
    secret = "must_not_appear_in_keys_or_msg"
    code, msg, keys = sanitized_broker_error_summary(
        {
            "ok": False,
            "error": {
                "code": "upstream_bad_gateway",
                "message": "line1\nline2",
                "details": {"z_key": secret, "a_key": 1},
            },
        }
    )
    assert code == "upstream_bad_gateway"
    assert msg == "line1 line2"
    assert keys == ["a_key", "z_key"]
    assert secret not in msg
    assert secret not in ",".join(keys)


def test_sanitized_broker_error_summary_truncates_long_message() -> None:
    long = "word " * 80
    _, msg, _ = sanitized_broker_error_summary(
        {"ok": False, "errors": [{"code": "x", "message": long}]}
    )
    assert msg is not None
    assert len(msg) == 200


def test_call_booneops_broker_retries_once_on_500_then_succeeds(monkeypatch) -> None:
    """Second POST succeeds after one 5xx; same correlation headers on both attempts."""
    monkeypatch.setattr("app.fetch.booneops_broker.time.sleep", lambda _s: None)
    settings = _make_settings()
    user = _make_user()
    calls: list[dict[str, object]] = []

    ok_body = b'{"ok":true,"message":"Recovered","errors":[]}'

    def fake_post(url: str, *, content: bytes, headers: dict[str, str], timeout: float):
        calls.append({"headers": dict(headers)})
        n = len(calls)

        class Resp:
            def __init__(self, status_code: int, content: bytes) -> None:
                self.status_code = status_code
                self.content = content

            def json(self):
                return json.loads(self.content.decode())

        if n == 1:
            return Resp(500, b'{"ok":false,"error":{"code":"tmp","message":"busy"}}')
        return Resp(200, ok_body)

    result = call_booneops_broker(
        settings,
        user=user,
        conversation_id="c",
        user_message="hi",
        route_label="printsmith_candidate",
        request_id="req-retry-ok",
        prior_messages=[],
        http_post=fake_post,
    )
    assert result.assistant_text == "Recovered"
    assert result.context_state == "booneops"
    assert len(calls) == 2
    assert calls[0]["headers"]["X-Correlation-Id"] == "req-retry-ok"
    assert calls[1]["headers"]["X-Correlation-Id"] == "req-retry-ok"
    assert calls[0]["headers"]["X-Retriever-Request-Id"] == "req-retry-ok"
    assert calls[1]["headers"]["X-Retriever-Request-Id"] == "req-retry-ok"


def test_call_booneops_broker_two_500_responses_single_user_error(monkeypatch) -> None:
    monkeypatch.setattr("app.fetch.booneops_broker.time.sleep", lambda _s: None)
    settings = _make_settings()
    body = b'{"ok":false,"error":{"code":"upstream_bad_gateway","message":"still down"}}'

    call_count = {"n": 0}

    def fake_post(_url: str, **_kw: object):
        call_count["n"] += 1

        class Resp:
            status_code = 502
            content = body

            def json(self):
                return json.loads(body.decode())

        return Resp()

    result = call_booneops_broker(
        settings,
        user=_make_user(),
        conversation_id="c",
        user_message="hi",
        route_label="printsmith_candidate",
        request_id="req-two-500",
        prior_messages=[],
        http_post=fake_post,
    )
    assert call_count["n"] == 2
    assert "server problem" in result.assistant_text.lower()
    assert "retried" in result.assistant_text.lower()
    assert result.metadata.get("request_id") == "req-two-500"
    assert result.metadata["status_cards"][0].get("request_id") == "req-two-500"


def test_call_booneops_broker_retries_network_error_once_then_timeout_user_message(monkeypatch) -> None:
    monkeypatch.setattr("app.fetch.booneops_broker.time.sleep", lambda _s: None)
    settings = _make_settings()
    n = {"c": 0}

    def fake_post(_url: str, **_kw: object):
        n["c"] += 1
        raise httpx.ReadTimeout("timed out", request=None)

    result = call_booneops_broker(
        settings,
        user=_make_user(),
        conversation_id="c",
        user_message="hi",
        route_label="printsmith_candidate",
        request_id="req-2-timeout",
        prior_messages=[],
        http_post=fake_post,
    )
    assert n["c"] == 2
    lowered = result.assistant_text.lower()
    assert "time" in lowered or "timeout" in lowered
    assert result.metadata.get("request_id") == "req-2-timeout"


def test_call_booneops_broker_502_logs_sanitized_fields_not_secret_details(caplog, monkeypatch) -> None:
    monkeypatch.setattr("app.fetch.booneops_broker.time.sleep", lambda _s: None)
    caplog.set_level(logging.WARNING, logger="app.fetch.booneops_broker")
    secret_in_details = "sk_live_dummy_never_log_this"
    body = json.dumps(
        {
            "ok": False,
            "error": {
                "code": "upstream_bad_gateway",
                "message": "Broker upstream\nfailed",
                "details": {"internalToken": secret_in_details, "route": "bots"},
            },
        }
    ).encode()

    def fake_post(_url: str, **_kw: object):
        class Resp:
            status_code = 502
            content = body

            def json(self):
                return json.loads(body.decode())

        return Resp()

    monkeypatch.setattr("app.fetch.booneops_broker.default_http_post", fake_post)
    result = call_booneops_broker(
        _make_settings(),
        user=_make_user(),
        conversation_id="c",
        user_message="hi",
        route_label="printsmith_candidate",
        request_id="req-502-test",
        prior_messages=[],
        http_post=None,
    )
    assert "temporary server problem" in result.assistant_text.lower()
    assert "retried" in result.assistant_text.lower()
    assert result.metadata.get("request_id") == "req-502-test"

    joined = " ".join(r.message for r in caplog.records)
    assert "req-502-test" in joined
    assert "502" in joined
    assert "retrying once" in joined.lower()
    assert "upstream_bad_gateway" in joined
    assert "Broker upstream failed" in joined
    assert "internalToken,route" in joined
    assert secret_in_details not in joined
    assert "unit-test-bearer" not in joined
    assert "unit-test-hmac" not in joined


def test_call_booneops_broker_network_error_is_user_safe(monkeypatch) -> None:
    monkeypatch.setattr("app.fetch.booneops_broker.time.sleep", lambda _s: None)
    settings = _make_settings()
    n = {"c": 0}

    def boom(_url: str, **_kw: object):
        n["c"] += 1
        raise httpx.ConnectError("nope", request=None)

    monkeypatch.setattr("app.fetch.booneops_broker.default_http_post", boom)

    result = call_booneops_broker(
        settings,
        user=_make_user(),
        conversation_id="c",
        user_message="hi",
        route_label="printsmith_candidate",
        request_id="r1",
        prior_messages=[],
        http_post=None,
    )
    assert n["c"] == 2
    lowered = result.assistant_text.lower()
    assert "broker" in lowered
    assert "network" in lowered or "connectivity" in lowered
    assert result.context_state == "booneops_error"
    assert result.metadata.get("request_id") == "r1"


def test_safe_fetch_download_href_accepts_root_paths_only() -> None:
    assert safe_fetch_download_href("/reports/abc/file.pdf") == "/reports/abc/file.pdf"
    assert safe_fetch_download_href("  /ok  ") == "/ok"
    assert safe_fetch_download_href(None) is None
    assert safe_fetch_download_href("") is None
    assert safe_fetch_download_href("//evil.example/path") is None
    assert safe_fetch_download_href("https://x.example/a") is None
    assert safe_fetch_download_href("/../admin") is None
    assert safe_fetch_download_href("/ok\\windows") is None
    assert safe_fetch_download_href("/ok\tbad") is None
    assert safe_fetch_download_href("/ok\x0bbad") is None


def test_normalize_and_validate_booneops_artifact_id() -> None:
    uid = "550e8400-e29b-41d4-a716-446655440000"
    assert normalize_and_validate_booneops_artifact_id(uid) == uid
    assert normalize_and_validate_booneops_artifact_id("art-12345") == "art-12345"
    assert normalize_and_validate_booneops_artifact_id("ab") is None
    assert normalize_and_validate_booneops_artifact_id("x/y") is None
    assert normalize_and_validate_booneops_artifact_id("../x") is None


def test_build_broker_message_presentation_docs_caps_source_cards_at_two() -> None:
    srcs = [{"title": f"Doc {i}", "url": f"/docs/{i}"} for i in range(5)]
    _, metadata = build_broker_message_presentation(
        {"ok": True, "message": "x" * 600, "sources": srcs},
        "docs_candidate",
    )
    assert len(metadata["source_cards"]) == 2
    assert metadata["source_cards"][0]["title"] == "Doc 0"
    assert metadata["source_cards"][1]["title"] == "Doc 1"


def test_build_broker_message_presentation_docs_low_confidence_returns_clarify_not_dump() -> None:
    wall = "Switch manual content " * 80
    text, metadata = build_broker_message_presentation(
        {
            "ok": True,
            "message": wall,
            "answerConfidence": "low",
            "sources": [{"title": "Switch Guide", "url": "/docs/s"}],
        },
        "docs_candidate",
    )
    assert "Switch manual content" not in text
    assert "Which product" in text or "doc entry" in text.lower()
    assert "source_cards" not in metadata


def test_build_broker_message_presentation_docs_weak_text_without_sources_clarifies() -> None:
    text, metadata = build_broker_message_presentation(
        {
            "ok": True,
            "message": "I could not find relevant documentation for that product variant.",
        },
        "docs_candidate",
    )
    assert "could not find relevant documentation" not in text.lower()
    assert "source_cards" not in metadata


def test_build_broker_message_presentation_canonical_download_path_for_artifacts() -> None:
    uid = "550e8400-e29b-41d4-a716-446655440000"
    _text, metadata = build_broker_message_presentation(
        {
            "ok": True,
            "message": "Attached.",
            "artifacts": [{"filename": "q.pdf", "artifactId": uid, "downloadPath": f"/v1/booneops/artifacts/{uid}"}],
        },
        "printsmith_candidate",
    )
    expect = f"/fetch/artifacts/broker/{uid}"
    assert metadata["artifacts"][0]["downloadPath"] == expect
