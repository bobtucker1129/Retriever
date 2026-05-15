"""Render stored plain-text assistant answers as safe HTML (markdown subset + sanitize)."""

from __future__ import annotations

import re
from typing import Optional, Sequence

import markdown
import nh3
from markupsafe import Markup

from app.config import AppSettings
from app.db.repositories.fetch import FetchMessageRecord

# Anthropic Opus 4 family slugs / labels → pilot display name
_OPUS_4_PATTERNS = re.compile(
    r"(?:claude[-_]?)?opus[-_]?4|opus[-_]?4\.?\d*|claude[-_]opus[-_]4",
    re.IGNORECASE,
)
_SONNET_4_6 = re.compile(
    r"claude[-_]?sonnet[-_]?4[-_]?6|sonnet[-_]?4[-_]?6",
    re.IGNORECASE,
)


def human_model_label(model_label: Optional[str], settings: AppSettings) -> str:
    """Map stored model slug to a short human label (friendly name for common gateway slugs)."""
    raw = (model_label or settings.model_default or "").strip()
    if not raw:
        return "unknown"
    if _OPUS_4_PATTERNS.search(raw):
        return "Opus 4.7"
    low = raw.lower()
    if "opus" in low and "4" in raw:
        return "Opus 4.7"
    if _SONNET_4_6.search(raw) or ("sonnet" in low and "4" in raw and "6" in raw):
        return "Claude Sonnet 4.6"
    return _humanize_slug(raw)


def _humanize_slug(raw: str) -> str:
    parts = [p for p in re.split(r"[\s_\/\-]+", raw.strip()) if p]
    if not parts:
        return "unknown"
    out: list[str] = []
    for p in parts:
        if len(p) <= 2 and p.isalpha():
            out.append(p.upper())
        else:
            out.append(p.capitalize())
    return " ".join(out)


def fetch_thread_load_metadata_for_turn(
    prior_records: Sequence[FetchMessageRecord],
    user_message: str,
    assistant_text: str,
) -> dict[str, Any]:
    """Heuristic thread size hint for operators (not a provider token meter)."""
    total = sum(len(rec.content or "") for rec in prior_records)
    total += len(user_message) + len(assistant_text)
    n = len(prior_records) + 2
    if total < 12_000 and n < 10:
        bucket = "light"
    elif total < 35_000 and n < 18:
        bucket = "moderate"
    else:
        bucket = "heavy"
    suggest = total >= 50_000 or n >= 22
    return {
        "fetch_thread_char_estimate": total,
        "fetch_thread_load_bucket": bucket,
        "fetch_new_chat_suggested": suggest,
    }


def _model_display_parts(m: FetchMessageRecord, settings: AppSettings) -> str:
    meta = m.metadata if isinstance(m.metadata, dict) else {}
    slug = (meta.get("gateway_model_id") or m.model_label or "").strip()
    state = (m.context_state or "").strip().lower()

    if state == "booneops" and not slug:
        return "Model: not recorded"

    if state == "booneops" and slug:
        friendly = human_model_label(slug, settings)
        return f"Model: {friendly} ({slug})"

    friendly = human_model_label(m.model_label, settings)
    return f"Model: {friendly}"


def _thread_load_phrase(m: FetchMessageRecord) -> str:
    meta = m.metadata if isinstance(m.metadata, dict) else {}
    state = (m.context_state or "").strip().lower()

    if "fetch_thread_load_bucket" not in meta:
        if state == "booneops":
            return "Thread load: not tracked on this older reply (not a model context %)."
        return ""

    bucket = str(meta.get("fetch_thread_load_bucket") or "unknown").strip()
    chars = meta.get("fetch_thread_char_estimate")
    suggest = bool(meta.get("fetch_new_chat_suggested"))

    if isinstance(chars, int) and chars >= 0:
        core = f"Thread load: {bucket} (~{chars} chars; not a model context %)"
    else:
        core = f"Thread load: {bucket} (not a model context %)"

    if suggest:
        return f"{core} Consider a new chat if answers drift or you keep growing this thread."
    return core


def context_line_for_assistant(m: FetchMessageRecord) -> tuple[int, str]:
    """Return (percent, state word) for legacy stub/error lines using the old percent slot."""
    pct = m.context_percent
    if pct is None:
        pct = 0
    state_raw = (m.context_state or "").strip().lower()
    if state_raw in ("booneops_error", "error"):
        return pct, "error"
    if state_raw in ("stub",):
        return pct, "stub"
    if state_raw in ("booneops", "ready", "") or not state_raw:
        return pct, "ready"
    return pct, state_raw.replace("_", " ")


def build_assistant_status_line(m: FetchMessageRecord, settings: AppSettings) -> str:
    model_fragment = _model_display_parts(m, settings)
    gq = "On" if settings.fetch_general_questions_enabled else "Off"
    load_fragment = _thread_load_phrase(m)
    state = (m.context_state or "").strip().lower()

    if state == "booneops" and load_fragment:
        return f"{model_fragment} | General Question: {gq} | {load_fragment}"

    pct, state_word = context_line_for_assistant(m)
    return f"{model_fragment} | General Question: {gq} | Context: {pct}% {state_word}"


# GFM-style pipe tables need the "tables" extension; nh3 then keeps structure via explicit allowlists.
_MD_EXTENSIONS = ["nl2br", "sane_lists", "tables"]


def assistant_body_html(plain_text: str) -> Markup:
    """Convert stored plain text to sanitized HTML for assistant bubbles."""
    if not plain_text:
        return Markup("")
    # Markdown preserves readable structure; nh3 strips scripts, event handlers, iframes, inline styles, etc.
    md = markdown.Markdown(extensions=_MD_EXTENSIONS)
    raw_html = md.convert(plain_text)
    clean = nh3.clean(
        raw_html,
        tags=nh3.ALLOWED_TAGS,
        attributes=nh3.ALLOWED_ATTRIBUTES,
    )
    return Markup(clean)


def fetch_assistant_body_display(m: FetchMessageRecord, _settings: AppSettings) -> Markup:
    """Assistant bubble HTML: strip duplicate Markdown Sources when metadata cards exist (docs route)."""
    from app.fetch.booneops_broker import (
        scrub_gateway_host_file_paths_from_employee_fetch_text,
        strip_redundant_markdown_sources_section,
    )

    text = m.content or ""
    if m.role == "assistant":
        text = scrub_gateway_host_file_paths_from_employee_fetch_text(text)
        route = (m.route_key or "").strip()
        meta = m.metadata if isinstance(m.metadata, dict) else {}
        cards = meta.get("source_cards")
        if route == "docs_candidate" and isinstance(cards, list) and len(cards) > 0:
            text = strip_redundant_markdown_sources_section(text, cards)
    return assistant_body_html(text)
