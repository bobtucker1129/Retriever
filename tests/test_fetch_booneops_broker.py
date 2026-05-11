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
from app.fetch.booneops_broker import (
    broker_message_url,
    call_booneops_broker,
    format_assistant_text_from_broker_json,
    map_user_to_broker_principal,
    sanitized_broker_error_summary,
    sign_body_hmac_sha256,
)
from app.fetch.local_routing import should_delegate_ask_to_booneops_broker


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
            content = b'{"ok":true,"message":"Broker ok","errors":[]}'

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
    assert "unit-test-bearer" not in result.assistant_text
    assert "unit-test-hmac" not in result.assistant_text


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


def test_call_booneops_broker_502_logs_sanitized_fields_not_secret_details(caplog, monkeypatch) -> None:
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
    expected_user = (
        "BooneOps encountered a server error.\n\n"
        "Your message was saved; try again later."
    )
    assert result.assistant_text == expected_user

    joined = " ".join(r.message for r in caplog.records)
    assert "req-502-test" in joined
    assert "502" in joined
    assert "upstream_bad_gateway" in joined
    assert "Broker upstream failed" in joined
    assert "internalToken,route" in joined
    assert secret_in_details not in joined
    assert "unit-test-bearer" not in joined
    assert "unit-test-hmac" not in joined


def test_call_booneops_broker_network_error_is_user_safe(monkeypatch) -> None:
    settings = _make_settings()

    def boom(_url: str, **_kw: object):
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
    lowered = result.assistant_text.lower()
    assert "broker" in lowered
    assert result.context_state == "booneops_error"
