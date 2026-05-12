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
        ("How many Estimates did Jim and steve enter into prinsmith in Feb 26?", "printsmith_candidate"),
        ("print smith down jobs last week", "printsmith_candidate"),
        ("printsmit export help", "printsmith_candidate"),
        ("printsmth invoice search", "printsmith_candidate"),
        ("prinsmit ticket 12", "printsmith_candidate"),
        ("How many estimates did we log in January?", "printsmith_candidate"),
        (
            "Who opened more invoices in the month of Dec 2025, Ellie or Shelley?",
            "printsmith_candidate",
        ),
        ("How many invoices were posted during FY2024?", "printsmith_candidate"),
        ("Were more invoices entered in Sep 2026 or Nov 2026?", "printsmith_candidate"),
        (
            "Can you give me a list of job that were digital Color in the month of Jan, 2026",
            "printsmith_candidate",
        ),
        ("List all jobs in digital color for February 2026.", "printsmith_candidate"),
        ("How many jobs did we run in January 2026?", "printsmith_candidate"),
        ("Who invented jobs?", "general_candidate"),
        ("read the xmpie manual for uproduce", "docs_candidate"),
        ("documentation for Switch", "docs_candidate"),
        (
            # Invoice wording but no verb/volume/time — keep out of PrintSmith lane.
            "Who invented invoices?",
            "general_candidate",
        ),
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


def test_general_stub_explains_downloads_need_broker_or_routed_paths() -> None:
    body = build_fetch_stub_reply("general_candidate")
    lowered = body.lower()
    assert "download" in lowered
    assert "artifact" in lowered
    assert "docs" in lowered
    assert "printsmith" in lowered


def test_normalize_user_text() -> None:
    assert normalize_user_text("  a  b  ") == "a b"
