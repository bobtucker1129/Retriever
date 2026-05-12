"""Deterministic local-only Fetch intent classification and stub replies.

No network calls. Labels are stable for tests and future provider/tool routing.
"""

from __future__ import annotations

import re
from typing import Final

from app.config import AppSettings

# Stable public set used by classification and tests.
FETCH_ROUTE_LABELS: Final[tuple[str, ...]] = (
    "local",
    "help",
    "sources",
    "health",
    "email_cleanup",
    "printsmith_candidate",
    "docs_candidate",
    "general_candidate",
    "blocked_write",
    "unknown",
)

_SLASH_COMMANDS: Final[frozenset[str]] = frozenset({"/help", "/sources", "/health"})

_PRINTSMITH_HINTS: Final[tuple[str, ...]] = (
    "printsmith",
    "printsmit",
    "dsf",
    "job ticket",
    "work ticket",
    "estimate number",
)

# Spaced or punctuated typos collapse to these letter runs (see _collapsed_printsmith_hint).
_COLLAPSED_PRINTSMITH_FRAGMENTS: Final[tuple[str, ...]] = (
    "printsmith",
    "prinsmith",
    "printsmit",
    "printsmth",
    "prinsmit",
)

# Natural-language estimate volume / entry questions (shop data lane).
_ESTIMATE_ENTRY_HINTS: Final[tuple[str, ...]] = (
    "how many estimates",
    "estimates did",
    "estimates were",
    "number of estimates",
    "entered estimates",
    "estimates entered",
    "estimate entry",
)

_DOCS_HINTS: Final[tuple[str, ...]] = (
    "documentation",
    "vendor doc",
    "xmpie",
    "uplan",
    "ucreate",
    "uproduce",
    "switch manual",
    "the manual",
    "qlingo",
)

_EMAIL_CLEANUP_HINTS: Final[tuple[str, ...]] = (
    "email cleanup",
    "clean my inbox",
    "inbox cleanup",
    "mailbox cleanup",
    "inbox hygiene",
)

_BLOCKED_WRITE_HINTS: Final[tuple[str, ...]] = (
    "send email to",
    "send an email to",
    "delete my ",
    "erase my ",
    "remove my ",
    "drop table",
    "truncate ",
    "update all records",
    "wire transfer",
)

_GREETING_RE: Final[re.Pattern[str]] = re.compile(
    r"^(hi|hello|hey|thanks|thank you|ok|okay|ping)\.?$",
    re.IGNORECASE,
)

_GENERAL_START_RE: Final[re.Pattern[str]] = re.compile(
    r"^(what|how|why|when|where|who|can you|could you|would you|please explain|explain|tell me)\b",
    re.IGNORECASE,
)

_NON_ALNUM_PRINTSMITH_COLLAPSE: Final[re.Pattern[str]] = re.compile(r"[^a-z0-9]+", re.IGNORECASE)

_INVOICE_NOUN_RE: Final[re.Pattern[str]] = re.compile(r"\binvoices?\b", re.IGNORECASE)
_INVOICE_VERB_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(opened|opens|opening|closed|closes|closing|entered|enters|entering"
    r"|posted|posts|posting)\b",
    re.IGNORECASE,
)
_INVOICE_VOLUME_OR_COMPARE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b("
    r"how\s+many\s+invoices?"
    r"|(?:more|fewer|most)\s+invoices?"
    r"|invoice\s+count"
    r"|number\s+of\s+invoices?"
    r")\b",
    re.IGNORECASE,
)

# Month names, numeric years, and coarse calendar buckets for shop-report questions.
_PRINTSMITH_OPS_TIME_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(month|months|year|years|quarter|quarters|fiscal\b|weekly|daily)"
    r"|\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may\b|jun(?:e)?"
    r"|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b"
    r"|\bfy[-\s]?\d{2,4}\b"
    r"|\b(?:19|20)\d{2}\b",
    re.IGNORECASE,
)

# Shop job / work-order wording + calendar window — before general_candidate ("Can you…").
_PRINTSMITH_JOB_CONTEXT_RE: Final[re.Pattern[str]] = re.compile(
    r"\bjobs?\b"
    r"|work\s+orders?"
    r"|job\s+tickets?"
    r"|work\s+tickets?",
    re.IGNORECASE,
)


def _looks_printsmith_dated_job_shop_query(low: str) -> bool:
    """Operational job/work-order list or counts with a recognized time window."""
    if _PRINTSMITH_JOB_CONTEXT_RE.search(low) is None:
        return False
    return _PRINTSMITH_OPS_TIME_RE.search(low) is not None


def _looks_printsmith_invoice_shop_query(low: str) -> bool:
    """Operational invoice activity + calendar window — Boone PrintSmith-shaped; before general_candidate."""
    has_invoice_story = (
        _INVOICE_VOLUME_OR_COMPARE_RE.search(low) is not None
        or (
            _INVOICE_NOUN_RE.search(low) is not None and _INVOICE_VERB_RE.search(low) is not None
        )
    )
    if not has_invoice_story:
        return False
    return _PRINTSMITH_OPS_TIME_RE.search(low) is not None


def _collapsed_printsmith_hint(low: str) -> bool:
    """Match PrintSmith mentions with spaces, hyphens, or common misspellings."""
    collapsed = _NON_ALNUM_PRINTSMITH_COLLAPSE.sub("", low)
    return any(fragment in collapsed for fragment in _COLLAPSED_PRINTSMITH_FRAGMENTS)


def normalize_user_text(text: str) -> str:
    """Collapse whitespace; preserves leading slash commands."""
    return " ".join(text.split()).strip()


def classify_fetch_intent(text: str) -> str:
    """Assign a single route label. First matching rule wins (deterministic order)."""
    cleaned = normalize_user_text(text)
    if not cleaned:
        return "unknown"

    low = cleaned.lower()
    slash_key = low.split()[0] if low else ""
    if slash_key in _SLASH_COMMANDS:
        return slash_key[1:]  # help | sources | health

    for hint in _BLOCKED_WRITE_HINTS:
        if hint in low:
            return "blocked_write"

    for hint in _EMAIL_CLEANUP_HINTS:
        if hint in low:
            return "email_cleanup"

    if _collapsed_printsmith_hint(low):
        return "printsmith_candidate"

    for hint in _ESTIMATE_ENTRY_HINTS:
        if hint in low:
            return "printsmith_candidate"

    for hint in _PRINTSMITH_HINTS:
        if hint in low:
            return "printsmith_candidate"

    for hint in _DOCS_HINTS:
        if hint in low:
            return "docs_candidate"

    if _looks_printsmith_invoice_shop_query(low):
        return "printsmith_candidate"

    if _looks_printsmith_dated_job_shop_query(low):
        return "printsmith_candidate"

    if "?" in cleaned or _GENERAL_START_RE.match(cleaned):
        return "general_candidate"

    if _GREETING_RE.match(cleaned):
        return "local"

    return "unknown"


def should_delegate_ask_to_booneops_broker(route: str, settings: AppSettings) -> bool:
    """Whether this route may call the BooneOps broker (still gated by ``BOONEOPS_BROKER_ENABLED``)."""
    if not settings.booneops_broker_enabled:
        return False
    if route in ("printsmith_candidate", "docs_candidate"):
        return True
    if route == "general_candidate" and settings.fetch_general_questions_enabled:
        return True
    return False


_STATUS_OFFLINE: Final[str] = (
    "Fetch is in local stub mode: the live model, PrintSmith, vendor documentation, "
    "BooneOps, uploads, delayed reports, and web search are not connected. "
    "Nothing ran beyond saving this turn."
)

_FUTURE_ROUTES: Final[str] = (
    "When routing is turned on, planned labels include: local, help, sources, health, "
    "email_cleanup, printsmith_candidate, docs_candidate, general_candidate; "
    "blocked_write stays safety-screened."
)


def build_fetch_stub_reply(route: str) -> str:
    """Deterministic assistant text for the gated ask path (no external tools)."""
    if route not in FETCH_ROUTE_LABELS:
        route = "unknown"

    if route == "help":
        return (
            "/help — Fetch shell (offline stub)\n\n"
            f"{_STATUS_OFFLINE}\n\n"
            "Slash commands available in the stub: /help, /sources, /health. "
            "They only return this static guidance; there is no live assistant behind them yet.\n\n"
            f"{_FUTURE_ROUTES}"
        )

    if route == "sources":
        return (
            "/sources — what will be wired later\n\n"
            f"{_STATUS_OFFLINE}\n\n"
            "Future source lanes (not active): Boone PrintSmith reads, curated vendor or "
            "internal documentation, and BooneOps-backed internal context when those "
            "integrations are enabled and you have the right capability.\n\n"
            "Right now: no retrieval, no connectors, no uploads."
        )

    if route == "health":
        return (
            "/health — routing and integrations\n\n"
            f"{_STATUS_OFFLINE}\n\n"
            "Integration health checks and live dependency status are not implemented on "
            "this path yet. The HTTP /health endpoints for the app may still be used by "
            "operators; this command only describes Fetch routing state.\n\n"
            f"{_FUTURE_ROUTES}"
        )

    if route == "blocked_write":
        return (
            "That request looks like a write or outbound action (email send, destructive "
            "data change, etc.). In stub mode nothing was executed.\n\n"
            f"{_STATUS_OFFLINE}\n\n"
            "Future routing will keep high-risk writes off automatic tool paths until "
            "explicit approval and capability gates exist."
        )

    if route == "email_cleanup":
        return (
            "Email cleanup / mailbox hygiene is classified as a future assisted workflow.\n\n"
            f"{_STATUS_OFFLINE}\n\n"
            "When enabled, this lane would run only under explicit internal policy and "
            "would not touch mail in stub mode."
        )

    if route == "printsmith_candidate":
        return (
            "This message looks PrintSmith- or shop-estimate-related (e.g. DSF, tickets, "
            "or PrintSmith wording).\n\n"
            f"{_STATUS_OFFLINE}\n\n"
            "When PrintSmith routing is enabled, this path would use approved read-only "
            "or scoped operations—none of that ran here."
        )

    if route == "docs_candidate":
        return (
            "This message looks vendor- or documentation-related (tools, manuals, XMPie, "
            "Switch, etc.).\n\n"
            f"{_STATUS_OFFLINE}\n\n"
            "When documentation retrieval is enabled, answers would come from approved "
            "sources only—no web search or ad-hoc uploads in this stub."
        )

    if route == "general_candidate":
        return (
            "This message looks like a general question.\n\n"
            "Downloadable charts or files need a live BooneOps reply with artifact metadata, "
            "or a docs / PrintSmith / report-style route—not this offline stub while general "
            "routing is off.\n\n"
            f"{_STATUS_OFFLINE}\n\n"
            "When general or model routing is enabled for your account, this label would "
            "feed the appropriate provider path; here you only get this placeholder."
        )

    if route == "local":
        return (
            "Local / conversational acknowledgment (stub).\n\n"
            f"{_STATUS_OFFLINE}"
        )

    if route == "unknown":
        return (
            "Could not map this message to a specific future route yet.\n\n"
            f"{_STATUS_OFFLINE}\n\n"
            f"{_FUTURE_ROUTES}"
        )

    # Defensive — should be unreachable if FETCH_ROUTE_LABELS stays aligned.
    return (
        f"{_STATUS_OFFLINE}\n\n"
        f"{_FUTURE_ROUTES}"
    )
