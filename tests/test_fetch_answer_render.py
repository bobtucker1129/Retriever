from __future__ import annotations

from app.config import AppSettings
from app.db.repositories.fetch import FetchMessageRecord
from app.fetch.answer_render import (
    assistant_body_html,
    build_assistant_status_line,
    fetch_assistant_body_display,
    fetch_thread_load_metadata_for_turn,
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
    s2 = _settings(model_default="other")
    assert human_model_label("claude-sonnet-4-6", s2) == "Claude Sonnet 4.6"


def test_fetch_thread_load_metadata_for_turn() -> None:
    prior = [
        FetchMessageRecord(
            message_id="a",
            conversation_id="c",
            user_id=1,
            role="user",
            content="x" * 100,
            route_key="docs_candidate",
        ),
        FetchMessageRecord(
            message_id="b",
            conversation_id="c",
            user_id=1,
            role="assistant",
            content="y" * 100,
            route_key="docs_candidate",
        ),
    ]
    meta = fetch_thread_load_metadata_for_turn(prior, "hello", "world")
    assert meta["fetch_thread_load_bucket"] == "light"
    assert meta["fetch_new_chat_suggested"] is False
    assert meta["fetch_thread_char_estimate"] == 100 + 100 + len("hello") + len("world")


def test_build_assistant_status_line_booneops_shows_model_and_load() -> None:
    s = _settings(model_default="claude-stub")
    m = FetchMessageRecord(
        message_id="m1",
        conversation_id="c1",
        user_id=1,
        role="assistant",
        content="x",
        route_key="docs_candidate",
        model_label="claude-sonnet-4-6",
        context_percent=0,
        context_state="booneops",
        metadata={
            "gateway_model_id": "claude-sonnet-4-6",
            "fetch_thread_char_estimate": 5000,
            "fetch_thread_load_bucket": "light",
            "fetch_new_chat_suggested": False,
        },
    )
    line = build_assistant_status_line(m, s)
    assert "Claude Sonnet 4.6 (claude-sonnet-4-6)" in line
    assert "Thread load: light" in line
    assert "not a model context %" in line


def test_build_assistant_status_line_booneops_without_gateway_model() -> None:
    s = _settings(model_default="claude-opus-4-x")
    m = FetchMessageRecord(
        message_id="m1",
        conversation_id="c1",
        user_id=1,
        role="assistant",
        content="x",
        route_key="docs_candidate",
        model_label=None,
        context_percent=0,
        context_state="booneops",
        metadata={
            "fetch_thread_char_estimate": 1000,
            "fetch_thread_load_bucket": "light",
            "fetch_new_chat_suggested": False,
        },
    )
    line = build_assistant_status_line(m, s)
    assert "Model: not recorded" in line


def test_assistant_body_html_allows_markdown_strips_scripts() -> None:
    html = assistant_body_html(
        "**Hi**\n\n- one\n- two\n\n<script>alert(1)</script>"
    )
    text = str(html)
    assert "<strong>Hi</strong>" in text
    assert "<ul>" in text and "<li>" in text
    assert "<script>" not in text.lower()


def test_fetch_assistant_body_display_strips_gateway_media_paths_from_stored_content() -> None:
    s = _settings()
    m = FetchMessageRecord(
        message_id="m1",
        conversation_id="c1",
        user_id=1,
        role="assistant",
        content="See MEDIA:/Users/o/workspace/a.xlsx below.",
        route_key="printsmith_candidate",
        model_label=None,
        context_percent=0,
        context_state="booneops",
        metadata={},
    )
    html = str(fetch_assistant_body_display(m, s))
    assert "MEDIA:" not in html
    assert "/Users/o" not in html
    assert "See" in html


def test_assistant_body_html_renders_pipe_table_with_safe_structure() -> None:
    md = "| Col A | Col B |\n| --- | --- |\n| 1 | 2 |\n"
    text = str(assistant_body_html(md))
    assert "<table>" in text
    assert "<thead>" in text and "<tbody>" in text
    assert "<tr>" in text
    assert "<th" in text and "Col A" in text and "Col B" in text
    assert "<td" in text and "1" in text and "2" in text


def test_assistant_body_html_pipe_table_strips_script_in_cells() -> None:
    md = "| x |\n| --- |\n| pre <script>bad</script> post |\n"
    text = str(assistant_body_html(md))
    assert "<table>" in text and "<td" in text
    assert "<script>" not in text.lower()
    assert "pre" in text and "post" in text


def test_assistant_body_html_pipe_table_strips_iframe_style_and_handlers_in_cells() -> None:
    """nh3 allowlists omit iframe/style tags and strip dangerous attributes from allowed tags."""
    iframe_md = '| c |\n| --- |\n| pre <iframe src="//e"></iframe> post |\n'
    low_iframe = str(assistant_body_html(iframe_md)).lower()
    assert "<table>" in low_iframe and "<td" in low_iframe
    assert "iframe" not in low_iframe
    assert "pre" in low_iframe and "post" in low_iframe

    style_md = "| c |\n| --- |\n| x <style>body{background:red}</style> y |\n"
    low_style = str(assistant_body_html(style_md)).lower()
    assert "<table>" in low_style
    assert "<style" not in low_style
    assert "x" in low_style and "y" in low_style

    handler_md = (
        "| c |\n| --- |\n| <span style=\"color:red\" onclick=\"alert(1)\">safe</span> |\n"
    )
    low_h = str(assistant_body_html(handler_md)).lower()
    assert "<table>" in low_h and "<td" in low_h
    assert "onclick" not in low_h
    assert "style=" not in low_h
    assert "safe" in low_h


def test_assistant_body_html_renders_numbered_lists_as_sanitized_ordered_lists() -> None:
    html = assistant_body_html("Steps:\n\n1. First\n2. Second\n")
    text = str(html)
    assert "<ol>" in text and "</ol>" in text
    assert text.count("<li>") >= 2
    assert "First" in text and "Second" in text


def test_build_assistant_status_line_respects_context() -> None:
    s = _settings(model_default="claude-stub")
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


def test_fetch_assistant_body_display_strips_sources_when_cards_present() -> None:
    s = _settings()
    body = "Summary\n\nSome answer text.\n\n### Sources\n\n- [One](https://a)\n- Two\n"
    m = FetchMessageRecord(
        message_id="m1",
        conversation_id="c1",
        user_id=1,
        role="assistant",
        content=body,
        route_key="docs_candidate",
        model_label=None,
        context_percent=0,
        context_state="ready",
        metadata={"source_cards": [{"title": "One", "url": "https://a"}]},
    )
    html = str(fetch_assistant_body_display(m, s))
    assert "Some answer text" in html
    assert "### Sources" not in html


def test_fetch_assistant_body_display_passes_through_without_cards() -> None:
    s = _settings()
    body = "### Sources\n\n- x\n"
    m = FetchMessageRecord(
        message_id="m1",
        conversation_id="c1",
        user_id=1,
        role="assistant",
        content=body,
        route_key="docs_candidate",
        model_label=None,
        context_percent=0,
        context_state="ready",
        metadata=None,
    )
    html = str(fetch_assistant_body_display(m, s))
    assert "Sources" in html
