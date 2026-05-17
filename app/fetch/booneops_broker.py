"""BooneOps broker client: signed POST /v1/booneops/message (Phase 1 contract).

See projects/booneops-bots/BROKER.md and FETCH_HANDOFF.md for the server contract.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
from urllib.parse import unquote
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence

import httpx
from starlette.responses import Response

from app.auth.permissions import CurrentUser
from app.config import AppSettings
from app.db.repositories.fetch import FetchMessageRecord
from app.fetch.broker_user_visible_copy import (
    copy_booneops_denied_no_body,
    copy_http_401,
    copy_http_5xx_after_retry,
    copy_http_network,
    copy_http_non_json,
    copy_http_timeout,
)
from app.fetch.local_routing import broker_message_after_slash_route_prefix

logger = logging.getLogger(__name__)

_MAX_BOONEOPS_ACTION_TYPES = 12


def _broker_action_types_from_payload(data: dict[str, Any]) -> list[str]:
    """Compact list of broker ``actionsTaken[].type`` for logs and stored assistant metadata."""
    raw = data.get("actionsTaken")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw[:_MAX_BOONEOPS_ACTION_TYPES]:
        if isinstance(item, dict):
            t = str(item.get("type") or "").strip()
            if t:
                out.append(t)
    return out


def _metadata_with_booneops_actions(
    metadata: Optional[dict[str, Any]], data: dict[str, Any]
) -> dict[str, Any]:
    merged: dict[str, Any] = dict(metadata) if metadata else {}
    actions = _broker_action_types_from_payload(data)
    if actions:
        merged["booneops_actions"] = actions
    return merged

BOONEOPS_MESSAGE_PATH = "/v1/booneops/message"
BOONEOPS_BROKER_ARTIFACT_PATH_TEMPLATE = "/v1/booneops/artifacts/{artifact_id}"
# Keep a few seconds above broker ``BOONEOPS_GATEWAY_TIMEOUT_MS`` (default 110s) so structured
# broker errors usually arrive before the client aborts; see ``DISCORD_FETCH_PARITY.md``.
_DEFAULT_HTTP_TIMEOUT = 115.0
_BROKER_ARTIFACT_HTTP_TIMEOUT = 120.0
_BROKER_TRANSIENT_RETRY_BACKOFF_SEC = 0.35

_UUID_ARTIFACT_ID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
)
_OPAQUE_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9_-]+$")

# Docs-routed turns: sent in ``sessionMetadata.retrieverDocsPresentationGuidance`` only.
# Never append this to ``message`` — upstream tooling treats ``message`` as the user's search text.
# The BooneOps broker may merge this into the gateway envelope when it learns the key; today it is
# carried for contract completeness and operator visibility without polluting retrieval queries.
_DOCS_ROUTE_PRESENTATION_GUIDANCE = (
    "Lead with a short Summary (what matters), then practical Steps "
    "(numbered or bulleted) when the user asked how-to or steps are inferable, then optional detail. "
    "When real source metadata exists (titles, URLs, or doc paths), put at most two entries in "
    "sourceCards or sources—titles only from the corpus; do not invent placeholder citations. "
    "When grounding is weak, set answerConfidence to \"low\" or needsClarification true instead "
    "of speculating."
)

# Presentation: keep broker metadata cards link-focused in the shell.
_SOURCE_CARD_TITLE_MAX = 140
_MAX_DOCS_SOURCE_CARDS = 2
_ARTIFACT_DESCRIPTION_MAX = 72

_DOCS_WEAK_CONFIDENCE_LEVELS = frozenset({"low", "uncertain", "none", "unknown"})
_DOCS_CLARIFY_USER_MESSAGE = (
    "I could not tie that confidently to a specific doc entry.\n\n"
    "Which product, version, or manual should we use (for example Switch, XMPie uProduce, or PrintSmith)?"
)

_LIST_ITEM_LINE = re.compile(
    r"^(\d{1,3}[\.\)]|[*\-•]|step\s+\d+)\s+\S",
    re.IGNORECASE,
)
# Echo back on later broker turns via assistant metadata (follow-up exports / styling).
_MAX_PERSISTED_STRUCTURED_CONTEXT_JSON_BYTES = 750_000

HttpPostFn = Callable[..., Any]
BrokerArtifactGetFn = Callable[..., Any]


class BrokerArtifactProxyFailure(Exception):
    """Upstream broker artifact GET could not yield a downloadable file."""

    __slots__ = ("status_code", "detail")

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _artifact_id_has_controls(s: str) -> bool:
    return any(ord(ch) < 32 or ch == "\x7f" for ch in s)


def normalize_and_validate_booneops_artifact_id(raw: object) -> Optional[str]:
    """Return a tight artifact identifier or ``None`` (no slashes, traversal, or control chars)."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or len(s) > 128:
        return None
    if ".." in s or "/" in s or "\\" in s:
        return None
    if _artifact_id_has_controls(s):
        return None
    if _UUID_ARTIFACT_ID.match(s):
        return s
    if _OPAQUE_ARTIFACT_ID.fullmatch(s) and 4 <= len(s) <= 128:
        return s
    return None


def canonical_booneops_artifact_browser_path(artifact_id: str) -> str:
    return f"/fetch/artifacts/broker/{artifact_id}"


def booneops_artifact_upstream_url(settings: AppSettings, artifact_id: str) -> str:
    """Full broker URL for ``GET /v1/booneops/artifacts/{artifact_id}`` (server-to-server only)."""
    base = (settings.booneops_broker_url or "").strip().rstrip("/")
    return f"{base}{BOONEOPS_BROKER_ARTIFACT_PATH_TEMPLATE.format(artifact_id=artifact_id)}"


def broker_message_url(settings: AppSettings) -> str:
    base = (settings.booneops_broker_url or "").strip().rstrip("/")
    return f"{base}{BOONEOPS_MESSAGE_PATH}"


def map_user_to_broker_principal(user: CurrentUser) -> tuple[str, str]:
    """Map Retriever Fetch users to the broker role surfaced by app permissions."""
    if user.is_admin or user.has_capability("booneops.admin"):
        return "booneops.admin", "admin"
    return "booneops.production", "production"


def prior_messages_from_history(
    records: Sequence[FetchMessageRecord],
    *,
    limit: int = 12,
) -> list[dict[str, str]]:
    """Shape ``priorMessages`` for the broker (role + text)."""
    out: list[dict[str, str]] = []
    for rec in records[-limit:]:
        if rec.role not in {"user", "assistant"}:
            continue
        text = (rec.content or "").strip()
        if not text:
            continue
        out.append({"role": rec.role, "text": text})
    return out


def sign_body_hmac_sha256(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def build_broker_payload(
    *,
    bot_id: str,
    role: str,
    user: CurrentUser,
    conversation_id: str,
    user_message: str,
    request_id: str,
    route_label: str,
    prior_messages: list[dict[str, str]],
    session_metadata_extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Wire JSON key order matches ``projects/booneops-bots/lib/broker-message-build.cjs``."""
    caps = sorted(user.capabilities) if user.capabilities else []
    session_metadata: dict[str, Any] = {
        "source": "retriever-fetch",
        "routeLabel": route_label,
        "retrieverCapabilities": caps,
        # Broker gateway envelope: ask BooneOps to answer like Discord channel turns.
        "retrieverDiscordAnswerParity": True,
    }
    if session_metadata_extra:
        for key in sorted(session_metadata_extra.keys()):
            value = session_metadata_extra[key]
            if value is not None:
                session_metadata[key] = value
    return {
        "botId": bot_id,
        "userId": str(user.id),
        "displayName": user.display_name.strip() or user.email,
        "role": role,
        "conversationId": conversation_id,
        "message": user_message,
        "requestId": request_id,
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "priorMessages": prior_messages,
        "sessionMetadata": session_metadata,
    }


def serialize_broker_json(payload: dict[str, Any]) -> bytes:
    """Serialize JSON with stable key order (insertion order) for HMAC over raw bytes."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def augment_broker_user_message_for_route(user_message: str, _route_label: str) -> str:
    """Normalize broker user text; docs presentation hints live in sessionMetadata, not ``message``."""
    return (user_message or "").strip()


def augment_fetch_broker_user_message_for_turn(
    user_message: str,
    route_label: str,
    session_metadata_extra: Optional[dict[str, Any]] = None,
) -> str:
    """Normalize Fetch broker text (styled spreadsheet follow-ups) before route-specific augmentation."""
    base = broker_message_after_slash_route_prefix(user_message or "", route_label)
    extra = session_metadata_extra or {}
    if extra.get("reportStyle") == "basic_styled_excel":
        base = (
            "[Retriever follow-up: basic styled Excel]\n"
            "Regenerate the previous spreadsheet or tabular report export with styled headers "
            "(bold text and a conservative header fill color), light cell borders, readable column widths, "
            "and the same underlying data—do not invent new rows or metrics.\n\n"
            f"User wording: {base}"
        )
    return augment_broker_user_message_for_route(base, route_label)


def _normalize_broker_error_message(raw: str, *, max_len: int = 200) -> str:
    """Collapse to one line and truncate for safe logs (no raw body)."""
    one_line = " ".join((raw or "").split())
    if len(one_line) <= max_len:
        return one_line
    return one_line[:max_len]


def sanitized_broker_error_summary(data: dict[str, Any]) -> tuple[Optional[str], Optional[str], list[str]]:
    """Extract broker error code, one-line message, and ``details`` key names only (no values)."""
    err_obj: Optional[dict[str, Any]] = None
    errors = data.get("errors")
    if isinstance(errors, list) and errors:
        first = errors[0]
        if isinstance(first, dict):
            err_obj = first
    if err_obj is None:
        err = data.get("error")
        if isinstance(err, dict):
            err_obj = err

    if err_obj is None:
        return None, None, []

    code_raw = str(err_obj.get("code") or "").strip()
    code = code_raw if code_raw else None
    msg_raw = str(err_obj.get("message") or "").strip()
    message = _normalize_broker_error_message(msg_raw) if msg_raw else None

    detail_keys: list[str] = []
    details = err_obj.get("details")
    if isinstance(details, dict):
        detail_keys = sorted(str(k) for k in details.keys())

    return code, message, detail_keys


def _safe_text(value: object, *, max_len: int = 240) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text[:max_len]


def _is_probably_url(value: str) -> bool:
    return value.startswith(("http://", "https://", "/"))


def _extract_broker_source_cards(data: dict[str, Any]) -> list[dict[str, str]]:
    """Title and optional same-origin/external URL only; capped for compact UI."""
    cards: list[dict[str, str]] = []
    source_candidates: list[object] = []
    for key in ("sourceCards", "source_cards", "sources", "citations"):
        value = data.get(key)
        if isinstance(value, list):
            source_candidates.extend(value)

    for item in source_candidates[:12]:
        if len(cards) >= _MAX_DOCS_SOURCE_CARDS:
            break
        if isinstance(item, str):
            title = _safe_text(item, max_len=_SOURCE_CARD_TITLE_MAX)
            if title:
                cards.append({"kind": "source", "title": title})
            continue
        if not isinstance(item, dict):
            continue
        title = _safe_text(
            item.get("title")
            or item.get("label")
            or item.get("name")
            or item.get("filename")
            or item.get("source"),
            max_len=_SOURCE_CARD_TITLE_MAX,
        )
        if not title:
            continue
        card: dict[str, str] = {
            "kind": _safe_text(item.get("kind") or item.get("type") or "source", max_len=40),
            "title": title,
        }
        url = _safe_text(item.get("url") or item.get("href") or item.get("downloadPath"))
        if url and _is_probably_url(url):
            card["url"] = url
        cards.append(card)

    return cards[:_MAX_DOCS_SOURCE_CARDS]


def _raw_source_list_len(data: dict[str, Any]) -> int:
    total = 0
    for key in ("sourceCards", "source_cards", "sources", "citations"):
        value = data.get(key)
        if isinstance(value, list):
            total += len(value)
    return total


def _parse_confidence_float(value: object) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _string_confidence_is_weak(raw: object) -> bool:
    if not isinstance(raw, str):
        return False
    return raw.strip().lower() in _DOCS_WEAK_CONFIDENCE_LEVELS


def _message_suggests_weak_ungrounded_docs(text: str) -> bool:
    t = " ".join((text or "").lower().split())
    needles = (
        "not enough information",
        "couldn't find relevant",
        "could not find relevant",
        "cannot find any",
        "can't find any",
        "no relevant documentation",
        "no documentation was",
        "i'm not able to find",
        "i am not able to find",
        "unable to find",
        "did not find",
        "don't have access to",
        "do not have access to",
    )
    return any(n in t for n in needles)


def _broker_docs_answer_is_low_confidence(data: dict[str, Any], raw_message: str) -> bool:
    """Prefer a short clarify prompt over dumping retrieval when metadata/text says the match is weak."""
    if data.get("needsClarification") is True:
        return True
    if data.get("clarifyOnly") is True:
        return True
    if data.get("lowConfidenceDocsAnswer") is True:
        return True
    for key in ("answerConfidence", "confidenceLevel", "docConfidence", "docsConfidence"):
        if _string_confidence_is_weak(data.get(key)):
            return True
    for key in ("confidence", "answerConfidenceScore", "docConfidenceScore"):
        score = _parse_confidence_float(data.get(key))
        if score is not None and score < 0.5:
            return True
    nested = data.get("docsAnswer")
    if isinstance(nested, dict):
        if nested.get("needsClarification") is True:
            return True
        if _string_confidence_is_weak(nested.get("confidence") or nested.get("confidenceLevel")):
            return True
        nested_score = _parse_confidence_float(nested.get("score"))
        if nested_score is not None and nested_score < 0.5:
            return True
    am = data.get("answerMetadata")
    if isinstance(am, dict):
        if am.get("needsClarification") is True:
            return True
        if _string_confidence_is_weak(am.get("confidence") or am.get("confidenceLevel")):
            return True
    if _raw_source_list_len(data) == 0 and _message_suggests_weak_ungrounded_docs(raw_message):
        return True
    return False


def _split_doc_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _line_looks_like_list_item(ln: str) -> bool:
    return bool(_LIST_ITEM_LINE.match(ln.strip()))


def _paragraph_is_mostly_list(p: str) -> bool:
    lines = [ln.strip() for ln in p.splitlines() if ln.strip()]
    if len(lines) < 2:
        return False
    hits = sum(1 for ln in lines if _line_looks_like_list_item(ln))
    return hits >= 2 and hits >= (len(lines) + 1) // 2


def _message_is_mcp_structured_fetch_docs(raw_message: str) -> bool:
    """MCP employee docs answers already ship labeled markdown (**## Summary**, **### Sources**)."""
    base = (raw_message or "").strip()
    if not base.startswith("## Summary"):
        return False
    return "### Sources" in base


_HELP_DETAILS_AUTH_BOILERPLATE = re.compile(
    r"(?i)"
    r"\b(?:sign out|log out|logout|my account|account settings|"
    r"forgot (?:your )?password|create (?:an? )?account)\b"
    r"|\bsign in\s*[|•]|[|•]\s*sign in\b"
)


def _details_looks_like_help_portal_chrome(details: str) -> bool:
    text = details or ""
    low = text.lower()
    if "<script" in low:
        return True
    if "javascript:" in low:
        return True
    markers = (
        "you are here:",
        "filter: all files",
        "submit search",
        "skip to main content",
        "skip navigation",
        "chatbase",
    )
    if any(m in low for m in markers):
        return True
    return bool(_HELP_DETAILS_AUTH_BOILERPLATE.search(text))


def _docs_should_shape_heavily(raw_message: str) -> bool:
    base = (raw_message or "").strip()
    if _message_is_mcp_structured_fetch_docs(base):
        return False
    if len(raw_message) >= 520:
        return True
    if raw_message.count("\n") >= 5:
        return True
    paras = _split_doc_paragraphs(raw_message)
    if len(paras) >= 3:
        return True
    if len(paras) >= 2 and any(_paragraph_is_mostly_list(p) for p in paras[1:]):
        return True
    return False


def _shape_docs_message_body(raw_message: str) -> str:
    """Summary / Steps / Details from broker prose (docs route)."""
    base = (raw_message or "").strip()
    if not base or not _docs_should_shape_heavily(base):
        return base
    paras = _split_doc_paragraphs(base)
    if not paras:
        return base
    summary = paras[0]
    steps: Optional[str] = None
    steps_idx: Optional[int] = None
    for i, p in enumerate(paras[1:], start=1):
        if _paragraph_is_mostly_list(p):
            steps = p
            steps_idx = i
            break
    used = {0}
    if steps_idx is not None:
        used.add(steps_idx)
    detail_paras = [paras[i] for i in range(len(paras)) if i not in used]
    details = "\n\n".join(detail_paras).strip()
    if details and _details_looks_like_help_portal_chrome(details):
        details = ""

    parts: list[str] = []
    if summary:
        parts.append("Summary")
        parts.append(summary)
    if steps:
        parts.append("")
        parts.append("Steps")
        parts.append(steps)
    if details:
        parts.append("")
        parts.append("Details")
        parts.append(details)
    return "\n".join(parts).strip()


def _append_artifact_section(body: str, data: dict[str, Any]) -> str:
    fragments: list[str] = []
    trimmed = (body or "").strip()
    if trimmed:
        fragments.append(trimmed)
    artifacts = data.get("artifacts") or []
    if isinstance(artifacts, list) and artifacts:
        block = ["Attachments:"]
        for art in artifacts:
            if not isinstance(art, dict):
                continue
            fn = str(art.get("filename") or "attachment").strip()
            aid = str(art.get("artifactId") or "").strip()
            block.append(f"- {fn}" + (f" ({aid})" if aid else ""))
        if len(block) > 1:
            if fragments:
                fragments.append("")
            fragments.append("\n".join(block))
    return "\n".join(fragments).strip()


_RE_MEDIA_FULL_LINE = re.compile(r"(?im)^\s*MEDIA:\S*\s*$")
_RE_MEDIA_INLINE = re.compile(r"\bMEDIA:\S+", re.IGNORECASE)
_RE_FILE_URI = re.compile(r"\bfile://[^\s)>`'\"]+", re.IGNORECASE)
_RE_UNIX_USERS_EXPORT_PATH = re.compile(
    r"/Users/[^\s\n<'\"`]+\.(?:xlsx|xlsm|xls|csv|pdf|html)\b",
    re.IGNORECASE,
)
_RE_UNIX_HOME_EXPORT_PATH = re.compile(
    r"/home/[^\s\n<'\"`]+\.(?:xlsx|xlsm|xls|csv|pdf|html)\b",
    re.IGNORECASE,
)
_RE_WIN_USERS_EXPORT_PATH = re.compile(
    r"(?:[A-Za-z]:\\Users\\[^\s\n<'\"`]+\.(?:xlsx|xlsm|xls|csv|pdf|html))\b",
    re.IGNORECASE,
)


def scrub_gateway_host_file_paths_from_employee_fetch_text(text: str) -> str:
    """Remove OpenClaw ``MEDIA:`` paths and obvious gateway-host absolute paths from assistant prose.

    Employees only have Retriever same-origin download links (artifact cards). Paths on the
    operator or gateway machine are useless and leak host layout.
    """
    raw = text or ""
    out = _RE_MEDIA_FULL_LINE.sub("", raw)
    out = _RE_MEDIA_INLINE.sub("", out)
    out = _RE_FILE_URI.sub("", out)
    out = _RE_UNIX_USERS_EXPORT_PATH.sub("", out)
    out = _RE_UNIX_HOME_EXPORT_PATH.sub("", out)
    out = _RE_WIN_USERS_EXPORT_PATH.sub("", out)
    out = re.sub(r"[ \t]+\n", "\n", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def strip_redundant_markdown_sources_section(body: str, source_cards: object) -> str:
    """Remove a trailing Markdown **Sources** section when ``source_cards`` will show the same links.

    Used for ``docs_candidate`` turns so the shell does not duplicate sources in the body and metadata.
    """
    if not isinstance(source_cards, list) or len(source_cards) == 0:
        return body
    text = body or ""
    if not text.strip():
        return text
    lines = text.splitlines()
    heading_re = re.compile(r"^#{1,4}\s*sources\s*$", re.IGNORECASE)
    plain_re = re.compile(r"^sources\s*:\s*$", re.IGNORECASE)
    next_heading_re = re.compile(r"^#{1,6}\s+\S")
    start_idx: Optional[int] = None
    for i, line in enumerate(lines):
        s = line.strip()
        if heading_re.match(s) or plain_re.match(s):
            start_idx = i
            break
    if start_idx is None:
        return body
    end_idx = len(lines)
    for j in range(start_idx + 1, len(lines)):
        if next_heading_re.match(lines[j].strip()):
            end_idx = j
            break
    new_lines = lines[:start_idx] + lines[end_idx:]
    out = "\n".join(new_lines).strip()
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out if out else body


def _extract_broker_artifact_cards(data: dict[str, Any]) -> list[dict[str, str]]:
    artifacts = data.get("artifacts") or []
    if not isinstance(artifacts, list):
        return []
    cards: list[dict[str, str]] = []
    for art in artifacts[:6]:
        if not isinstance(art, dict):
            continue
        filename = _safe_text(art.get("filename") or "attachment")
        artifact_id_raw = _safe_text(art.get("artifactId"), max_len=128)
        validated_id = normalize_and_validate_booneops_artifact_id(artifact_id_raw)
        card = {"filename": filename}
        if validated_id:
            card["artifactId"] = validated_id
            card["downloadPath"] = canonical_booneops_artifact_browser_path(validated_id)
        description = _safe_text(
            art.get("description") or art.get("sizeLabel"), max_len=_ARTIFACT_DESCRIPTION_MAX
        )
        if description:
            card["description"] = description
        if "downloadPath" not in card:
            download_path = _safe_text(art.get("downloadPath"))
            if download_path and _is_probably_url(download_path):
                card["downloadPath"] = download_path
        cards.append(card)
    return cards


def _bounded_json_object_for_metadata(obj: object, *, max_bytes: int) -> Optional[dict[str, Any]]:
    """Return a JSON-round-trippable dict copy, or None if missing, not a dict, or too large."""
    if not isinstance(obj, dict):
        return None
    try:
        raw = json.dumps(obj, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        logger.warning("Broker structured context is not JSON-serializable; skipping persistence.")
        return None
    if len(raw.encode("utf-8")) > max_bytes:
        logger.warning(
            "Broker structured context exceeds %s bytes; skipping persistence.",
            max_bytes,
        )
        return None
    return json.loads(raw)


def _structured_context_metadata_from_broker(data: dict[str, Any]) -> dict[str, Any]:
    """Allowlisted nested payloads from broker JSON for assistant metadata (session echo).

    Keys align with ``sessionMetadata`` follow-up contract (camelCase). Snake_case
    top-level broker fields are normalized to the camelCase metadata key BooneOps expects.
    ``resultData`` is intentionally omitted: the broker rebuilds it from ``reportContext``.
    """
    meta: dict[str, Any] = {}
    rc = data.get("reportContext")
    if rc is None:
        rc = data.get("report_context")
    bounded = _bounded_json_object_for_metadata(
        rc, max_bytes=_MAX_PERSISTED_STRUCTURED_CONTEXT_JSON_BYTES
    )
    if bounded is not None:
        meta["reportContext"] = bounded

    sc = data.get("sessionContext")
    if sc is None:
        sc = data.get("session_context")
    bounded_sc = _bounded_json_object_for_metadata(
        sc, max_bytes=_MAX_PERSISTED_STRUCTURED_CONTEXT_JSON_BYTES
    )
    if bounded_sc is not None:
        meta["sessionContext"] = bounded_sc
    return meta


def _merge_gateway_telemetry_into_metadata(
    metadata: Optional[dict[str, Any]], data: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """Persist OpenClaw gateway identifiers from broker JSON (structured fields only)."""
    gw_model = _safe_text(data.get("gatewayModelId"), max_len=120)
    gw_run = _safe_text(data.get("gatewayRunId"), max_len=80)
    if not gw_model and not gw_run:
        return metadata
    merged = dict(metadata) if metadata else {}
    if gw_model:
        merged["gateway_model_id"] = gw_model
    if gw_run:
        merged["gateway_run_id"] = gw_run
    return merged


def _finalize_employee_visible_assistant_text(
    body: str, *, has_downloadable_artifacts: bool
) -> str:
    before = (body or "").strip()
    cleaned = scrub_gateway_host_file_paths_from_employee_fetch_text(before)
    if not cleaned.strip():
        if has_downloadable_artifacts:
            return "Your file is ready — use the Download link below."
        return cleaned
    return cleaned


def build_broker_message_presentation(
    data: dict[str, Any], route_label: str
) -> tuple[str, dict[str, Any]]:
    """Build safe user-visible text and rendering metadata from broker JSON."""
    errors = data.get("errors") or []
    policy_denied = any(
        isinstance(e, dict) and str(e.get("code") or "") == "policy_denied" for e in errors
    )
    if policy_denied:
        msg = ""
        for e in errors:
            if isinstance(e, dict) and str(e.get("code") or "") == "policy_denied":
                msg = str(e.get("message") or "").strip()
                break
        if msg:
            msg = scrub_gateway_host_file_paths_from_employee_fetch_text(msg)
            return (
                "BooneOps policy blocked this request.\n\n"
                f"{msg}\n\n"
                "If you think this is a mistake, contact an operator."
            ), {}
        return (
            "BooneOps policy blocked this request.\n\n"
            "Your message was saved; no automated action ran."
        ), {}

    ok = bool(data.get("ok", True)) if "ok" in data else not errors
    raw_message = str(data.get("message") or "").strip()

    if not ok and errors:
        parts: list[str] = []
        for e in errors:
            if isinstance(e, dict):
                em = str(e.get("message") or e.get("code") or "").strip()
                if em:
                    parts.append(em)
            elif e:
                parts.append(str(e))
        body = "\n".join(parts) if parts else "BooneOps could not complete this turn."
        body = scrub_gateway_host_file_paths_from_employee_fetch_text(body)
        return (
            f"{body}\n\n"
            "Your message was saved. You can try again or rephrase the question."
        ), {}

    if not raw_message:
        return (
            "BooneOps returned an empty reply.\n\n"
            "Your message was saved; try again in a moment."
        ), {}

    metadata: dict[str, Any] = {}
    if route_label == "docs_candidate":
        if _broker_docs_answer_is_low_confidence(data, raw_message):
            assistant_text = _append_artifact_section(_DOCS_CLARIFY_USER_MESSAGE, data)
        else:
            shaped = _shape_docs_message_body(raw_message)
            assistant_text = _append_artifact_section(shaped, data)
            source_cards = _extract_broker_source_cards(data)
            if source_cards:
                metadata["source_cards"] = source_cards
                assistant_text = strip_redundant_markdown_sources_section(
                    assistant_text, source_cards
                )
        artifact_cards = _extract_broker_artifact_cards(data)
        if artifact_cards:
            metadata["artifacts"] = artifact_cards
        request_id = _safe_text(data.get("requestId"), max_len=80)
        if request_id:
            metadata["request_id"] = request_id
        structured = _structured_context_metadata_from_broker(data)
        if structured:
            metadata.update(structured)
        has_dl = any(isinstance(c, dict) and c.get("downloadPath") for c in artifact_cards)
        assistant_text = _finalize_employee_visible_assistant_text(
            assistant_text, has_downloadable_artifacts=has_dl
        )
        return assistant_text, metadata

    lines = [raw_message]
    artifacts = data.get("artifacts") or []
    if isinstance(artifacts, list) and artifacts:
        lines.append("")
        lines.append("Attachments:")
        for art in artifacts:
            if not isinstance(art, dict):
                continue
            fn = str(art.get("filename") or "attachment").strip()
            aid = str(art.get("artifactId") or "").strip()
            label = f"- {fn}" + (f" ({aid})" if aid else "")
            lines.append(label)
    assistant_text = "\n".join(lines)

    source_cards = _extract_broker_source_cards(data)
    if source_cards:
        metadata["source_cards"] = source_cards
    artifact_cards = _extract_broker_artifact_cards(data)
    if artifact_cards:
        metadata["artifacts"] = artifact_cards
    request_id = _safe_text(data.get("requestId"), max_len=80)
    if request_id:
        metadata["request_id"] = request_id
    structured = _structured_context_metadata_from_broker(data)
    if structured:
        metadata.update(structured)
    has_dl = any(isinstance(c, dict) and c.get("downloadPath") for c in artifact_cards)
    assistant_text = _finalize_employee_visible_assistant_text(
        assistant_text, has_downloadable_artifacts=has_dl
    )
    return assistant_text, metadata


def format_assistant_text_from_broker_json(data: dict[str, Any]) -> str:
    """Build user-visible assistant text from broker JSON (only safe fields)."""
    text, _metadata = build_broker_message_presentation(data, route_label="")
    return text


_CONTENT_TYPE_SAFE = re.compile(r"^[\w!#$&^+.=-]+/[\w!#$&^+.=-]+$")
_CD_FILENAME_PARAM = re.compile(
    r"filename\*=(?:UTF-8''([^;]+))|filename=\"([^\"]+)\"|filename=([^;\s]+)",
    re.IGNORECASE,
)


def sanitize_upstream_media_type(header_value: Optional[str]) -> str:
    """Return a single safe ``type/subtype`` token or octet-stream."""
    if not header_value:
        return "application/octet-stream"
    base = header_value.split(";", maxsplit=1)[0].strip()
    if _CONTENT_TYPE_SAFE.fullmatch(base):
        return base
    return "application/octet-stream"


def _extract_filename_from_content_disposition(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    m = _CD_FILENAME_PARAM.search(value)
    if not m:
        return None
    grp = ""
    if m.group(2):
        grp = m.group(2).strip().strip("\"")
    elif m.group(3):
        grp = m.group(3).strip().strip("\"")
    else:
        grp = (m.group(1) or "").strip()
        if grp.lower().startswith("utf-8''"):
            grp = grp[7:]
        grp = unquote(grp, errors="replace")
    if not grp:
        return None
    return grp


def _safe_attachment_filename(value: Optional[str]) -> str:
    if not value:
        return ""
    trimmed = "".join(
        ch for ch in value if ord(ch) >= 32 and ch not in '<>:"/\r\n|?*\x7f\t\\'
    ).strip()
    if not trimmed:
        return ""
    base = trimmed.replace("\\", "/").rsplit("/", 1)[-1]
    base = "".join(ch for ch in base if ch not in '\\/:|?*"')
    if base in {"", ".", ".."}:
        return ""
    return base[:220]


def _fallback_attachment_filename(media_type: str, artifact_id: str) -> str:
    lowered = media_type.lower()
    if lowered == "application/pdf":
        ext = ".pdf"
    elif lowered == "text/csv":
        ext = ".csv"
    elif "spreadsheetml" in lowered or lowered.endswith("sheet"):
        ext = ".xlsx"
    elif lowered == "application/vnd.ms-excel":
        ext = ".xls"
    else:
        ext = ""
    short = "".join(ch for ch in artifact_id[:24] if ch.isalnum() or ch in "-_")
    if not short:
        short = "artifact"
    return f"{short}{ext}"


def default_broker_artifact_http_get(
    full_url: str, *, bearer_token: str, timeout: float
) -> httpx.Response:
    return httpx.get(
        full_url,
        headers={"Authorization": f"Bearer {bearer_token}"},
        timeout=timeout,
        follow_redirects=False,
    )


def proxy_booneops_artifact_download_response(
    settings: AppSettings,
    artifact_id: str,
    *,
    http_get: Optional[BrokerArtifactGetFn] = None,
) -> Response:
    """Fetch artifact bytes from BooneOps (Bearer only) and return an attachment ``Response``."""
    broker_url = (settings.booneops_broker_url or "").strip()
    token = (settings.booneops_broker_bearer_token or "").strip()
    if not broker_url or not token:
        raise BrokerArtifactProxyFailure(503, "BooneOps broker is not configured for downloads")

    full_url = booneops_artifact_upstream_url(settings, artifact_id)
    getter = http_get or default_broker_artifact_http_get
    try:
        upstream = getter(full_url, bearer_token=token, timeout=_BROKER_ARTIFACT_HTTP_TIMEOUT)
    except httpx.HTTPError as exc:
        logger.warning(
            "BooneOps artifact upstream HTTP failure id=%s err=%s",
            artifact_id,
            type(exc).__name__,
        )
        raise BrokerArtifactProxyFailure(502, "Could not retrieve artifact from BooneOps") from exc

    status = upstream.status_code
    raw_ct = upstream.headers.get("content-type") or ""
    media_type = sanitize_upstream_media_type(raw_ct)

    if status == 404:
        raise BrokerArtifactProxyFailure(404, "Artifact not found")

    if status == 403:
        raise BrokerArtifactProxyFailure(403, "Artifact access denied")

    if status >= 500:
        raise BrokerArtifactProxyFailure(502, "BooneOps could not retrieve this artifact")

    if status >= 400:
        raise BrokerArtifactProxyFailure(502, "BooneOps rejected this artifact request")

    if status != 200:
        raise BrokerArtifactProxyFailure(502, "Unexpected artifact response from BooneOps")

    if media_type.startswith("application/json") or raw_ct.lower().strip().startswith("application/json"):
        raise BrokerArtifactProxyFailure(503, "Artifact is not available for download")

    body = upstream.content
    sniff = body.lstrip()[:1]
    if sniff in (b"{", b"[") and len(body) < 65536:
        raise BrokerArtifactProxyFailure(503, "Artifact is not available for download")

    raw_name = _extract_filename_from_content_disposition(upstream.headers.get("content-disposition"))
    safe_name = _safe_attachment_filename(raw_name)
    attachment_name = safe_name if safe_name else _fallback_attachment_filename(media_type, artifact_id)
    esc = (
        attachment_name.replace('"', "")
        .replace("\\", "")
        .replace("\r", "")
        .replace("\n", "")
    )
    disposition = f'attachment; filename="{esc}"'

    headers = {
        "Content-Disposition": disposition,
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
    }

    return Response(content=body, media_type=media_type, headers=headers)


@dataclass(frozen=True)
class BooneOpsBrokerTurnResult:
    assistant_text: str
    context_state: str
    metadata: Optional[dict[str, Any]] = None


def default_http_post(url: str, *, content: bytes, headers: dict[str, str], timeout: float) -> Any:
    return httpx.post(url, content=content, headers=headers, timeout=timeout)


def _booneops_broker_http_error_kind(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    return "network"


def _booneops_broker_client_error(
    *,
    request_id: str,
    headline: str,
    detail_line: str,
    status_card_state: str,
    status_card_detail: str,
) -> BooneOpsBrokerTurnResult:
    assistant_text = (
        f"{headline}\n\n"
        f"{detail_line}\n\n"
        "Your message was saved. You can try again in a little while."
    )
    return BooneOpsBrokerTurnResult(
        assistant_text=assistant_text,
        context_state="booneops_error",
        metadata={
            "request_id": request_id,
            "status_cards": [
                {
                    "state": status_card_state,
                    "detail": status_card_detail,
                    "request_id": request_id,
                }
            ],
        },
    )


def call_booneops_broker(
    settings: AppSettings,
    *,
    user: CurrentUser,
    conversation_id: str,
    user_message: str,
    route_label: str,
    request_id: str,
    prior_messages: list[dict[str, str]],
    session_metadata_extra: Optional[dict[str, Any]] = None,
    http_post: Optional[HttpPostFn] = None,
) -> BooneOpsBrokerTurnResult:
    """POST a signed broker message; never logs secrets or raw bearer tokens."""
    bot_id, role = map_user_to_broker_principal(user)
    merged_session_extra: dict[str, Any] = (
        dict(session_metadata_extra) if session_metadata_extra else {}
    )
    if route_label == "docs_candidate":
        merged_session_extra["retrieverDocsPresentationGuidance"] = _DOCS_ROUTE_PRESENTATION_GUIDANCE
    broker_user_message = augment_fetch_broker_user_message_for_turn(
        user_message, route_label, merged_session_extra
    )
    payload = build_broker_payload(
        bot_id=bot_id,
        role=role,
        user=user,
        conversation_id=conversation_id,
        user_message=broker_user_message,
        request_id=request_id,
        route_label=route_label,
        prior_messages=prior_messages,
        session_metadata_extra=merged_session_extra or None,
    )
    body_bytes = serialize_broker_json(payload)
    secret = settings.booneops_broker_hmac_secret or ""
    token = settings.booneops_broker_bearer_token or ""
    signature = sign_body_hmac_sha256(body_bytes, secret)

    headers: dict[str, str] = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {token}",
        "X-BooneOps-Signature": signature,
        "X-Correlation-Id": request_id,
        "X-Retriever-Request-Id": request_id,
    }

    post = http_post or default_http_post
    url = broker_message_url(settings)

    response: Any = None
    for attempt in (0, 1):
        try:
            response = post(
                url,
                content=body_bytes,
                headers=headers,
                timeout=_DEFAULT_HTTP_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            if attempt == 0:
                logger.warning(
                    "BooneOps broker HTTP error request_id=%s err=%s (retrying once)",
                    request_id,
                    type(exc).__name__,
                )
                time.sleep(_BROKER_TRANSIENT_RETRY_BACKOFF_SEC)
                continue
            kind = _booneops_broker_http_error_kind(exc)
            logger.warning(
                "BooneOps broker HTTP error request_id=%s err=%s kind=%s",
                request_id,
                type(exc).__name__,
                kind,
            )
            if kind == "timeout":
                c = copy_http_timeout(request_id=request_id)
                return _booneops_broker_client_error(
                    request_id=request_id,
                    headline=c.headline,
                    detail_line=c.detail_line,
                    status_card_state=c.status_card_state,
                    status_card_detail=c.status_card_detail,
                )
            c = copy_http_network(request_id=request_id)
            return _booneops_broker_client_error(
                request_id=request_id,
                headline=c.headline,
                detail_line=c.detail_line,
                status_card_state=c.status_card_state,
                status_card_detail=c.status_card_detail,
            )

        if response.status_code >= 500 and attempt == 0:
            logger.warning(
                "BooneOps broker server error request_id=%s status=%s (retrying once)",
                request_id,
                response.status_code,
            )
            time.sleep(_BROKER_TRANSIENT_RETRY_BACKOFF_SEC)
            continue
        break
    assert response is not None

    if response.status_code == 401:
        logger.warning("BooneOps broker auth rejected request_id=%s", request_id)
        c = copy_http_401(request_id=request_id)
        return _booneops_broker_client_error(
            request_id=request_id,
            headline=c.headline,
            detail_line=c.detail_line,
            status_card_state=c.status_card_state,
            status_card_detail=c.status_card_detail,
        )

    try:
        data = response.json() if response.content else {}
        if not isinstance(data, dict):
            data = {}
    except json.JSONDecodeError:
        logger.warning("BooneOps broker non-JSON request_id=%s status=%s", request_id, response.status_code)
        c = copy_http_non_json(request_id=request_id)
        return _booneops_broker_client_error(
            request_id=request_id,
            headline=c.headline,
            detail_line=c.detail_line,
            status_card_state=c.status_card_state,
            status_card_detail=c.status_card_detail,
        )

    if response.status_code >= 500:
        b_code, b_msg, b_detail_keys = sanitized_broker_error_summary(data)
        logger.warning(
            "BooneOps broker server error request_id=%s status=%s broker_code=%s broker_message=%s "
            "broker_detail_keys=%s",
            request_id,
            response.status_code,
            b_code if b_code is not None else "-",
            b_msg if b_msg is not None else "-",
            ",".join(b_detail_keys) if b_detail_keys else "-",
        )
        c = copy_http_5xx_after_retry(request_id=request_id)
        return _booneops_broker_client_error(
            request_id=request_id,
            headline=c.headline,
            detail_line=c.detail_line,
            status_card_state=c.status_card_state,
            status_card_detail=c.status_card_detail,
        )

    if response.status_code >= 400:
        text, metadata = build_broker_message_presentation(data, route_label)
        metadata = _metadata_with_booneops_actions(metadata, data)
        metadata = _merge_gateway_telemetry_into_metadata(metadata, data)
        if text.strip():
            return BooneOpsBrokerTurnResult(
                assistant_text=text, context_state="booneops_error", metadata=metadata
            )
        c = copy_booneops_denied_no_body(request_id=request_id)
        return _booneops_broker_client_error(
            request_id=request_id,
            headline=c.headline,
            detail_line=c.detail_line,
            status_card_state=c.status_card_state,
            status_card_detail=c.status_card_detail,
        )

    text, metadata = build_broker_message_presentation(data, route_label)
    metadata = _metadata_with_booneops_actions(metadata, data)
    metadata = _merge_gateway_telemetry_into_metadata(metadata, data)
    errs = data.get("errors") if isinstance(data.get("errors"), list) else []
    ok = bool(data.get("ok", True))
    policy = any(
        isinstance(e, dict) and str(e.get("code") or "") == "policy_denied" for e in errs
    )
    ctx = "booneops_error" if policy or ok is False else "booneops"

    err_codes_log = ",".join(
        str(e.get("code") or "").strip()
        for e in errs
        if isinstance(e, dict) and str(e.get("code") or "").strip()
    ) or "-"
    arts = data.get("artifacts")
    artifact_count = len(arts) if isinstance(arts, list) else 0
    gw_slug = str((metadata or {}).get("gateway_model_id") or "").strip() or "-"

    logger.info(
        "BooneOps broker turn request_id=%s route=%s ok=%s actions=%s gateway_model=%s err_codes=%s artifact_count=%s",
        request_id,
        route_label,
        ok,
        ",".join((metadata or {}).get("booneops_actions") or []) or "-",
        gw_slug,
        err_codes_log,
        artifact_count,
    )

    return BooneOpsBrokerTurnResult(assistant_text=text, context_state=ctx, metadata=metadata)
