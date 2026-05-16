from __future__ import annotations

import httpx

from app.config import AppSettings
from app.db.repositories.fetch import FetchMessageRecord
from app.fetch.general_llm import (
    ANTHROPIC_MESSAGES_URL,
    call_general_conversation_llm,
    resolve_anthropic_model_id,
    should_use_general_llm,
)


def _settings(**updates) -> AppSettings:
    base = {
        "fetch_enabled": True,
        "model_provider": "Anthropic",
        "anthropic_api_key": "test-key",
        "model_default": "Opus 4.7",
    }
    base.update(updates)
    return AppSettings(**base)


def test_resolve_anthropic_model_id_accepts_friendly_opus_label() -> None:
    assert resolve_anthropic_model_id("Opus 4.7") == "claude-opus-4-7"
    assert resolve_anthropic_model_id("claude-sonnet-4-6") == "claude-sonnet-4-6"


def test_should_use_general_llm_only_for_normal_conversation_routes() -> None:
    settings = _settings()
    assert should_use_general_llm("general_candidate", settings) is True
    assert should_use_general_llm("local", settings) is True
    assert should_use_general_llm("unknown", settings) is True
    assert should_use_general_llm("printsmith_candidate", settings) is False
    assert should_use_general_llm("docs_candidate", settings) is False


def test_call_general_conversation_llm_posts_anthropic_messages_payload() -> None:
    seen = {}

    def fake_post(url: str, **kwargs):
        seen["url"] = url
        seen["headers"] = kwargs["headers"]
        seen["json"] = kwargs["json"]
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "The Kings question needs live data."}],
                "usage": {
                    "input_tokens": 12,
                    "output_tokens": 8,
                    "server_tool_use": {"web_search_requests": 1},
                },
            },
            request=httpx.Request("POST", url),
        )

    result = call_general_conversation_llm(
        _settings(),
        user_message="How are the LA Kings doing?",
        prior_records=[
            FetchMessageRecord(
                message_id="m1",
                conversation_id="c1",
                user_id=1,
                role="user",
                content="hello",
                route_key="local",
            ),
            FetchMessageRecord(
                message_id="m2",
                conversation_id="c1",
                user_id=1,
                role="assistant",
                content="Hi there.",
                route_key="local",
                context_state="llm",
            ),
            FetchMessageRecord(
                message_id="m3",
                conversation_id="c1",
                user_id=1,
                role="assistant",
                content="Sports are outside my lane.",
                route_key="general_candidate",
                context_state="booneops",
            ),
        ],
        http_post=fake_post,
    )

    assert seen["url"] == ANTHROPIC_MESSAGES_URL
    assert seen["headers"]["x-api-key"] == "test-key"
    assert seen["json"]["model"] == "claude-opus-4-7"
    assert seen["json"]["tools"] == [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "user_location": {
                "type": "approximate",
                "country": "US",
                "timezone": "America/New_York",
            },
        }
    ]
    assert "Sports are outside my lane." not in str(seen["json"]["messages"])
    assert seen["json"]["messages"][-1] == {
        "role": "user",
        "content": "How are the LA Kings doing?",
    }
    assert result.assistant_text == "The Kings question needs live data."
    assert result.context_state == "llm"
    assert result.model_label == "claude-opus-4-7"
    assert result.metadata == {
        "general_llm_provider": "anthropic",
        "general_llm_model_id": "claude-opus-4-7",
        "general_llm_input_tokens": 12,
        "general_llm_output_tokens": 8,
        "general_llm_web_search_requests": 1,
    }


def test_call_general_conversation_llm_handles_timeout() -> None:
    def fake_post(*_args, **_kwargs):
        raise httpx.TimeoutException("slow")

    result = call_general_conversation_llm(
        _settings(),
        user_message="hi",
        prior_records=[],
        http_post=fake_post,
    )

    assert result.context_state == "error"
    assert "too long" in result.assistant_text
    assert result.model_label == "claude-opus-4-7"
