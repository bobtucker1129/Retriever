"""Deterministic Fetch local routing (no HTTP)."""

from __future__ import annotations

import pytest

from app.fetch.local_routing import (
    FETCH_ROUTE_LABELS,
    build_fetch_stub_reply,
    classify_fetch_intent,
    normalize_user_text,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/help", "help"),
        ("/HELP", "help"),
        ("  /sources  ", "sources"),
        ("/health", "health"),
        ("/help more", "help"),
        ("delete my account records please", "blocked_write"),
        ("Please send email to vendor@example.com", "blocked_write"),
        ("clean my inbox today", "email_cleanup"),
        ("What is DSF?", "printsmith_candidate"),
        ("PrintSmith job status question", "printsmith_candidate"),
        ("read the xmpie manual for uproduce", "docs_candidate"),
        ("documentation for Switch", "docs_candidate"),
        ("What is the meaning of life?", "general_candidate"),
        ("Could you summarize the policy?", "general_candidate"),
        ("hi", "local"),
        ("Thanks", "local"),
        ("random musings without keywords", "unknown"),
        ("", "unknown"),
    ],
)
def test_classify_fetch_intent(text: str, expected: str) -> None:
    assert classify_fetch_intent(text) == expected


def test_all_routes_have_stub_copy() -> None:
    for route in FETCH_ROUTE_LABELS:
        text = build_fetch_stub_reply(route)
        assert len(text) > 40
        assert "stub" in text.lower() or "offline" in text.lower() or "not connected" in text.lower()


def test_stub_copy_always_warns_offline_for_route_like_prompts() -> None:
    for route in (
        "printsmith_candidate",
        "docs_candidate",
        "general_candidate",
        "email_cleanup",
    ):
        body = build_fetch_stub_reply(route)
        assert "stub" in body.lower() or "not connected" in body.lower()


def test_normalize_user_text() -> None:
    assert normalize_user_text("  a  b  ") == "a b"
