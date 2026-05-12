"""History-aware overrides for Fetch ask routing (export follow-ups).

Pure classification stays in ``local_routing.classify_fetch_intent``; this module
applies only when recent broker-backed context should carry the route forward.
"""

from __future__ import annotations

import re
from typing import Any, Final, Optional, Sequence

from app.db.repositories.fetch import FetchMessageRecord

_BROKER_SUCCESS_STATES: Final[frozenset[str]] = frozenset({"booneops", "ready"})

_ALLOWED_PRIOR_METADATA_KEYS: Final[frozenset[str]] = frozenset(
    ("reportContext", "report_context", "sessionContext", "session_context")
)

_EXPORT_ACTION_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(export|download|save|make)\b",
    re.IGNORECASE,
)

_FORMAT_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(pdf|excel|spreadsheet|\bxlsx\b|\bxls\b|\bcsv\b)\b",
    re.IGNORECASE,
)

_HTML_EXPORT_RE: Final[re.Pattern[str]] = re.compile(
    r"\bhtml\b|\.html\b",
    re.IGNORECASE,
)

# Route inheritance for file exports requires the user to point at prior content
# (deictic or explicit "result/answer/report/..."), not a bare format request.
_PRIOR_REFERENT_RE: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"that|this|previous|last|above|same|"
    r"result|answer|report|table|chart"
    r")\b",
    re.IGNORECASE,
)

_NO_OVERRIDE_ROUTES: Final[frozenset[str]] = frozenset(
    {"help", "sources", "health", "blocked_write", "email_cleanup"}
)


def _has_export_action(low: str) -> bool:
    return _EXPORT_ACTION_RE.search(low) is not None


def _mentions_export_format(low: str) -> bool:
    return _FORMAT_RE.search(low) is not None


def _has_prior_referent_cue(low: str) -> bool:
    return _PRIOR_REFERENT_RE.search(low) is not None


def is_export_download_followup_text(text: str) -> bool:
    """Whether ``text`` looks like a PDF/Excel/CSV export of *prior* assistant content."""
    low = text.strip().lower()
    if not low:
        return False
    if not _mentions_export_format(low):
        return False
    if not _has_export_action(low):
        return False
    return _has_prior_referent_cue(low)


def _mentions_html_export_format(low: str) -> bool:
    return _HTML_EXPORT_RE.search(low) is not None


def is_html_export_followup_text(text: str) -> bool:
    """Whether ``text`` asks to export/download/save *prior* content as HTML."""
    low = text.strip().lower()
    if not low:
        return False
    if not _mentions_html_export_format(low):
        return False
    if not _has_export_action(low):
        return False
    return _has_prior_referent_cue(low)


def _assistant_inheritable_route(rec: FetchMessageRecord) -> Optional[str]:
    if rec.role != "assistant":
        return None
    key = (rec.route_key or "").strip()
    if key not in ("printsmith_candidate", "docs_candidate"):
        return None
    state = (rec.context_state or "").strip().lower()
    if state in ("stub", "booneops_error", "error"):
        return None
    if state not in _BROKER_SUCCESS_STATES:
        return None
    return key


def inheritable_session_metadata_from_assistant(
    rec: Optional[FetchMessageRecord],
) -> dict[str, Any]:
    """Subset of prior assistant metadata safe to forward in broker ``sessionMetadata``."""
    if rec is None:
        return {}
    meta = rec.metadata
    if not isinstance(meta, dict):
        return {}
    out: dict[str, Any] = {}
    for k in _ALLOWED_PRIOR_METADATA_KEYS:
        if k in meta and meta[k] is not None:
            out[k] = meta[k]
    return out


def latest_inheritable_assistant_record(
    prior_records: Sequence[FetchMessageRecord],
) -> Optional[FetchMessageRecord]:
    for rec in reversed(prior_records):
        if _assistant_inheritable_route(rec) is not None:
            return rec
    return None


def html_export_prior_assistant(
    prior_records: Sequence[FetchMessageRecord],
    cleaned: str,
) -> Optional[FetchMessageRecord]:
    """Assistant message HTML export could snapshot, if the user asked for HTML and context allows."""
    if not is_html_export_followup_text(cleaned):
        return None
    return latest_inheritable_assistant_record(prior_records)


def resolve_fetch_ask_route(
    cleaned: str,
    base_route: str,
    prior_records: Sequence[FetchMessageRecord],
) -> tuple[str, dict[str, Any]]:
    """Return effective route and optional broker session metadata from the prior turn.

    Does not change ``base_route`` unless this message is an export follow-up and a
    recent successful PrintSmith/docs broker answer exists.
    """
    if base_route in _NO_OVERRIDE_ROUTES:
        return base_route, {}
    if not is_export_download_followup_text(cleaned):
        return base_route, {}
    prior_assistant = latest_inheritable_assistant_record(prior_records)
    inherited = _assistant_inheritable_route(prior_assistant) if prior_assistant else None
    if inherited is None:
        return base_route, {}
    extra = inheritable_session_metadata_from_assistant(prior_assistant)
    return inherited, extra
