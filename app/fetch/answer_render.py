"""Render stored plain-text assistant answers as safe HTML (markdown subset + sanitize)."""

from __future__ import annotations

import re
from typing import Optional

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


def human_model_label(model_label: Optional[str], settings: AppSettings) -> str:
    """Map stored model slug to a short human label (Opus 4.7 for current Opus, else cleaned slug)."""
    raw = (model_label or settings.model_default or "").strip()
    if not raw:
        return "unknown"
    if _OPUS_4_PATTERNS.search(raw):
        return "Opus 4.7"
    low = raw.lower()
    if "opus" in low and "4" in raw:
        return "Opus 4.7"
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


def context_line_for_assistant(m: FetchMessageRecord) -> tuple[int, str]:
    """Return (percent, state word) for the compact status line."""
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
    model = human_model_label(m.model_label, settings)
    gq = "On" if settings.fetch_general_questions_enabled else "Off"
    pct, state_word = context_line_for_assistant(m)
    return f"Model: {model} | General Question: {gq} | Context: {pct}% {state_word}"


# GFM-style pipe tables need the "tables" extension; nh3 then keeps structure via explicit allowlists.
_MD_EXTENSIONS = ["nl2br", "sane_lists", "tables"]


def assistant_body_html(plain_text: str) -> Markup:
    """Convert stored plain text to sanitized HTML for assistant bubbles."""
    if not plain_text:
        return Markup("")
    # Markdown preserves readable structure; nh3 strips scripts, event handlers, iframes, inline styles, etc.
    md = markdown.Markdown(extensions=_MD_EXTENSIONS)
    html = md.convert(plain_text)
    clean = nh3.clean(
        html,
        tags=nh3.ALLOWED_TAGS,
        attributes=nh3.ALLOWED_ATTRIBUTES,
    )
    return Markup(clean)
