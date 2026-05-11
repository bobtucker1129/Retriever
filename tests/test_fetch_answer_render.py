from __future__ import annotations

from app.config import AppSettings
from app.db.repositories.fetch import FetchMessageRecord
from app.fetch.answer_render import (
    assistant_body_html,
    build_assistant_status_line,
    human_model_label,
)


def _settings(**kwargs: object) -> AppSettings:
    base = {
        "retriever_env": "local",
        "local_dev_identity_enabled": True,
        "mysql_host": "h",
        "mysql_user": "u",
        "mysql_password": "p",
    }
    base.update(kwargs)
    return AppSettings(**base)


def test_human_model_label_maps_opus_four_family() -> None:
    s = _settings(model_default="other")
    assert human_model_label("claude-opus-4-20250514", s) == "Opus 4.7"
    assert human_model_label("anthropic/claude-opus-4-foo", s) == "Opus 4.7"
    assert human_model_label("claude-stub", s) == "Claude Stub"


def test_assistant_body_html_allows_markdown_strips_scripts() -> None:
    html = assistant_body_html(
        "**Hi**\n\n- one\n- two\n\n<script>alert(1)</script>"
    )
    text = str(html)
    assert "<strong>Hi</strong>" in text
    assert "<ul>" in text and "<li>" in text
    assert "<script>" not in text.lower()


def test_assistant_body_html_renders_numbered_lists_as_sanitized_ordered_lists() -> None:
    html = assistant_body_html("Steps:\n\n1. First\n2. Second\n")
    text = str(html)
    assert "<ol>" in text and "</ol>" in text
    assert text.count("<li>") >= 2
    assert "First" in text and "Second" in text


def test_build_assistant_status_line_respects_flags_and_context() -> None:
    s = _settings(fetch_general_questions_enabled=False, model_default="claude-stub")
    m = FetchMessageRecord(
        message_id="m1",
        conversation_id="c1",
        user_id=1,
        role="assistant",
        content="x",
        route_key="local",
        model_label="claude-stub",
        context_percent=0,
        context_state="stub",
        metadata=None,
    )
    line = build_assistant_status_line(m, s)
    assert "General Question: Off" in line
    assert "Claude Stub" in line
    assert "Context: 0% stub" in line

    m_err = FetchMessageRecord(
        message_id="m2",
        conversation_id="c1",
        user_id=1,
        role="assistant",
        content="x",
        route_key="local",
        model_label=None,
        context_percent=0,
        context_state="booneops_error",
        metadata=None,
    )
    assert "Context: 0% error" in build_assistant_status_line(m_err, s)
