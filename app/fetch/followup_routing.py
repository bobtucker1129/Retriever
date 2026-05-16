"""History-aware overrides for Fetch ask routing.

Pure classification stays in ``local_routing.classify_fetch_intent``; this module
routes follow-ups when recent broker-backed context should carry forward the
prior lane — export refinement, downloadable formats, or sticky continuation
after ``general_candidate`` / ``unknown`` classification.
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

# PDF export follow-ups routed to BooneOps when the target sounds like broker output.
_BROKER_PDF_OBJECT_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(report|chart|table|spreadsheet|excel|xlsx|xls|csv|workbook)\b",
    re.IGNORECASE,
)

_ANSWER_PDF_REPLY_NOUN_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(answer|reply|response)\b",
    re.IGNORECASE,
)

_HTML_EXPORT_RE: Final[re.Pattern[str]] = re.compile(
    r"\bhtml\b|\.html\b",
    re.IGNORECASE,
)

# Follow-up refinement of a recent report/export (styling, cleanup, layout) without
# requiring deictic ``that/this`` when the user names the artifact naturally.
_ARTIFACT_REFINEMENT_TOPIC_RE: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"excel|xlsx|xls|spreadsheet|workbook|csv|"
    r"\bpdf\b|report|table|chart"
    r")\b",
    re.IGNORECASE,
)

_ARTIFACT_REFINEMENT_STYLE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"fancy|prett(y|ier|ify)|nic(er|e)|beautiful|polish|spruce|"
    r"clean\s*up|cleaner|tidy|tidier|"
    r"styl(e|es|ing|ed)|bold(ing)?|italic|underline|"
    r"color|colour|colorful|colourful|"
    r"header(s)?|border(s)?|gridline|highlight|zebra|stripe|"
    r"formatted|formatting|reformat|layout|widths?|alignment"
    r")\b",
    re.IGNORECASE,
)

# Avoid treating definitional trivia as artifact refinement after a report/export turn.
_REFINEMENT_DEFINITIONAL_QUESTION_RE: Final[re.Pattern[str]] = re.compile(
    r"^\s*(what|why|who|when|where|which)\s+(is|are|was|were)\s+",
    re.IGNORECASE,
)

_ALLOWED_REPORT_STYLE_HINTS: Final[frozenset[str]] = frozenset({"basic_styled_excel"})

# Route inheritance for file exports requires the user to point at prior content
# (deictic or explicit "result/answer/report/..."), not a bare format request.
_PRIOR_REFERENT_RE: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"that|this|previous|last|above|same|"
    r"result|answer|report|table|chart"
    r")\b",
    re.IGNORECASE,
)
_TEMPORAL_THIS_RE: Final[re.Pattern[str]] = re.compile(
    r"\bthis\s+(year|month|week|quarter|morning|afternoon|evening|season)\b",
    re.IGNORECASE,
)

_NO_OVERRIDE_ROUTES: Final[frozenset[str]] = frozenset(
    {"help", "sources", "health", "blocked_write", "email_cleanup"}
)

# ``classify_fetch_intent`` lands here for many natural follow-ups (``?``, "can you…", etc.);
# inherit prior successful docs/PrintSmith broker turn instead of the general stub.
_STICKY_BASE_ROUTES: Final[frozenset[str]] = frozenset({"general_candidate", "unknown"})

_STICKY_CONTINUATION_RE: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"are\s+you\s+sure|look\s+again|double[-\s]?check|check\s+again|try\s+again|"
    r"rerun|re-run|same\s+(thing|query|report|search)|"
    r"explain\s+(that|this)|break\s+(that|this)\s+down|"
    r"tell\s+me\s+more\s+about\s+(that|this)"
    r")\b",
    re.IGNORECASE,
)


def _has_export_action(low: str) -> bool:
    return _EXPORT_ACTION_RE.search(low) is not None


def _mentions_export_format(low: str) -> bool:
    return _FORMAT_RE.search(low) is not None


def _has_prior_referent_cue(low: str) -> bool:
    without_temporal_this = _TEMPORAL_THIS_RE.sub("", low)
    return _PRIOR_REFERENT_RE.search(without_temporal_this) is not None


def _is_sticky_continuation_text(text: str) -> bool:
    low = text.strip().lower()
    if not low:
        return False
    if _has_prior_referent_cue(low) or _STICKY_CONTINUATION_RE.search(low) is not None:
        return True
    return _has_export_action(low) and _mentions_export_format(low)


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


_SPREADSHEET_FOR_STYLE_HINT_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(excel|xlsx|xls|spreadsheet|workbook|csv|report|table)\b",
    re.IGNORECASE,
)


def is_artifact_refinement_followup_text(text: str) -> bool:
    """Whether ``text`` continues recent report/export work via styling or cleanup language."""
    low = text.strip().lower()
    if not low:
        return False
    if _REFINEMENT_DEFINITIONAL_QUESTION_RE.search(low) is not None:
        return False
    if _ARTIFACT_REFINEMENT_TOPIC_RE.search(low) is None:
        return False
    if _ARTIFACT_REFINEMENT_STYLE_RE.search(low) is None:
        return False
    return True


def _pdf_only_style_target(low: str) -> bool:
    """True when the user names PDF but not a spreadsheet/tabular export format."""
    if re.search(r"\bpdf\b", low) is None:
        return False
    return (
        re.search(r"\b(excel|xlsx|xls|spreadsheet|workbook|csv)\b", low) is None
    )


def styled_spreadsheet_hint_for_refinement(text: str) -> Optional[str]:
    """Allowlisted ``reportStyle`` session hint for spreadsheet-focused refinement."""
    if not is_artifact_refinement_followup_text(text):
        return None
    low = text.strip().lower()
    if _SPREADSHEET_FOR_STYLE_HINT_RE.search(low) is None:
        return None
    if _pdf_only_style_target(low):
        return None
    return "basic_styled_excel"


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


def is_answer_snapshot_pdf_followup_text(text: str) -> bool:
    """Phrase points at PDF of the Fetch *answer*, not broker report/chart/tabular artifacts."""
    low = text.strip().lower()
    if not low:
        return False
    if re.search(r"\bpdf\b", low) is None:
        return False
    if not _has_export_action(low):
        return False
    if not _has_prior_referent_cue(low):
        return False
    if _BROKER_PDF_OBJECT_RE.search(low) is not None:
        return False
    if _ANSWER_PDF_REPLY_NOUN_RE.search(low) is None:
        return False
    return True


def pdf_export_prior_assistant(
    prior_records: Sequence[FetchMessageRecord],
    cleaned: str,
) -> Optional[FetchMessageRecord]:
    """Same inheritable-assistant gates as HTML when the turn asks for an answer snapshot PDF."""
    if not is_answer_snapshot_pdf_followup_text(cleaned):
        return None
    return latest_inheritable_assistant_record(prior_records)


def resolve_fetch_ask_route(
    cleaned: str,
    base_route: str,
    prior_records: Sequence[FetchMessageRecord],
) -> tuple[str, dict[str, Any]]:
    """Return effective route and optional broker metadata when conversation context pins the lane.

    Handles explicit PDF/Excel/CSV export follow-ups, artifact refinement (styling, cleanup),
    and sticky continuation when classification is ``general_candidate`` or ``unknown`` but a
    recent successful docs/PrintSmith broker turn exists.
    """
    if base_route in _NO_OVERRIDE_ROUTES:
        return base_route, {}
    export_followup = is_export_download_followup_text(cleaned)
    refinement_followup = is_artifact_refinement_followup_text(cleaned)
    if export_followup or refinement_followup:
        prior_assistant = latest_inheritable_assistant_record(prior_records)
        inherited = _assistant_inheritable_route(prior_assistant) if prior_assistant else None
        if inherited is None:
            return base_route, {}
        extra = inheritable_session_metadata_from_assistant(prior_assistant)
        style_hint = styled_spreadsheet_hint_for_refinement(cleaned)
        if style_hint is not None and style_hint in _ALLOWED_REPORT_STYLE_HINTS:
            extra = {**extra, "reportStyle": style_hint}
        return inherited, extra

    if base_route not in _STICKY_BASE_ROUTES:
        return base_route, {}

    prior_assistant = latest_inheritable_assistant_record(prior_records)
    sticky = _assistant_inheritable_route(prior_assistant) if prior_assistant else None
    if sticky is None:
        return base_route, {}
    if not _is_sticky_continuation_text(cleaned):
        return base_route, {}

    return sticky, inheritable_session_metadata_from_assistant(prior_assistant)
