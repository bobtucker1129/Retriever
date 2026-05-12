"""BooneOps broker client: signed POST /v1/booneops/message (Phase 1 contract).

See projects/booneops-bots/BROKER.md and FETCH_HANDOFF.md for the server contract.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from urllib.parse import unquote
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence

import httpx
from starlette.responses import Response

from app.auth.permissions import CurrentUser
from app.config import AppSettings
from app.db.repositories.fetch import FetchMessageRecord

logger = logging.getLogger(__name__)

BOONEOPS_MESSAGE_PATH = "/v1/booneops/message"
BOONEOPS_BROKER_ARTIFACT_PATH_TEMPLATE = "/v1/booneops/artifacts/{artifact_id}"
_DEFAULT_HTTP_TIMEOUT = 115.0
_BROKER_ARTIFACT_HTTP_TIMEOUT = 120.0

_UUID_ARTIFACT_ID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$",
)
_OPAQUE_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9_-]+$")

# Docs-routed turns: appended to ``message`` only (not echoed in stored user text).
_DOCS_ROUTE_BROKER_INSTRUCTIONS = (
    "\n\n---\n[Retriever docs route] Answer with a short summary first, then add detail if needed. "
    "When real source metadata exists (titles, URLs, or doc paths), return it in sourceCards or "
    "sources so Fetch can show compact links—do not invent placeholder citations."
)

# Presentation: keep broker metadata cards link-focused in the shell.
_SOURCE_CARD_TITLE_MAX = 140
_SOURCE_CARD_DETAIL_MAX = 72
_ARTIFACT_DESCRIPTION_MAX = 72

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
    """Map Retriever user to broker ``(botId, role)`` per ``ROLE_TO_ALLOWED_BOTS``."""
    if user.is_admin:
        return "booneops.admin", "admin"
    level = (user.booneops_level or "none").strip().lower()
    if level == "medium":
        return "booneops.super", "super"
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
    caps = sorted(user.capabilities) if user.capabilities else []
    session_metadata: dict[str, Any] = {
        "source": "retriever-fetch",
        "routeLabel": route_label,
        "booneopsLevel": user.booneops_level or "none",
        "retrieverCapabilities": caps,
    }
    if session_metadata_extra:
        for key, value in session_metadata_extra.items():
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


def augment_broker_user_message_for_route(user_message: str, route_label: str) -> str:
    """Add upstream instructions for BooneOps on documentation-routed broker calls only."""
    base = (user_message or "").strip()
    if route_label != "docs_candidate":
        return base
    return base + _DOCS_ROUTE_BROKER_INSTRUCTIONS


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
    cards: list[dict[str, str]] = []
    source_candidates: list[object] = []
    for key in ("sourceCards", "source_cards", "sources", "citations"):
        value = data.get(key)
        if isinstance(value, list):
            source_candidates.extend(value)

    for item in source_candidates[:6]:
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
        detail = _safe_text(
            item.get("description") or item.get("snippet") or item.get("detail"),
            max_len=_SOURCE_CARD_DETAIL_MAX,
        )
        if detail:
            card["detail"] = detail
        url = _safe_text(item.get("url") or item.get("href") or item.get("downloadPath"))
        if url and _is_probably_url(url):
            card["url"] = url
        cards.append(card)

    return cards


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


def _first_nonempty_lines(text: str, *, limit: int = 3) -> list[str]:
    lines = [line.strip(" -•\t") for line in text.splitlines()]
    return [line for line in lines if line][:limit]


def _summarize_broker_answer(raw_message: str, route_label: str) -> Optional[str]:
    if route_label != "docs_candidate":
        return None
    if len(raw_message) < 520 and raw_message.count("\n") < 5:
        return None
    lines = _first_nonempty_lines(raw_message, limit=3)
    if not lines:
        return None
    summary = " ".join(lines)
    return summary[:420]


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
        return (
            f"{body}\n\n"
            "Your message was saved. You can try again or rephrase the question."
        ), {}

    if not raw_message:
        return (
            "BooneOps returned an empty reply.\n\n"
            "Your message was saved; try again in a moment."
        ), {}

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
    summary = _summarize_broker_answer(raw_message, route_label)
    if summary:
        assistant_text = f"Summary\n{summary}\n\nDetails\n{assistant_text}"

    metadata: dict[str, Any] = {}
    source_cards = _extract_broker_source_cards(data)
    if source_cards:
        metadata["source_cards"] = source_cards
    artifact_cards = _extract_broker_artifact_cards(data)
    if artifact_cards:
        metadata["artifacts"] = artifact_cards
    request_id = _safe_text(data.get("requestId"), max_len=80)
    if request_id:
        metadata["request_id"] = request_id
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
    broker_user_message = augment_broker_user_message_for_route(user_message, route_label)
    payload = build_broker_payload(
        bot_id=bot_id,
        role=role,
        user=user,
        conversation_id=conversation_id,
        user_message=broker_user_message,
        request_id=request_id,
        route_label=route_label,
        prior_messages=prior_messages,
        session_metadata_extra=session_metadata_extra,
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

    try:
        response = post(
            url,
            content=body_bytes,
            headers=headers,
            timeout=_DEFAULT_HTTP_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        logger.warning("BooneOps broker HTTP error request_id=%s err=%s", request_id, type(exc).__name__)
        return BooneOpsBrokerTurnResult(
            assistant_text=(
                "Fetch could not reach the BooneOps broker (network error).\n\n"
                "Your message was saved. Try again shortly, or contact an operator if this persists."
            ),
            context_state="booneops_error",
            metadata={"status_cards": [{"state": "Network issue", "detail": "BooneOps did not receive this turn."}]},
        )

    try:
        data = response.json() if response.content else {}
        if not isinstance(data, dict):
            data = {}
    except json.JSONDecodeError:
        logger.warning("BooneOps broker non-JSON request_id=%s status=%s", request_id, response.status_code)
        return BooneOpsBrokerTurnResult(
            assistant_text=(
                "BooneOps returned an unexpected response.\n\n"
                "Your message was saved; try again later."
            ),
            context_state="booneops_error",
            metadata={"status_cards": [{"state": "Unexpected response", "detail": "BooneOps returned data Fetch could not read."}]},
        )

    if response.status_code == 401:
        logger.warning("BooneOps broker auth rejected request_id=%s", request_id)
        return BooneOpsBrokerTurnResult(
            assistant_text=(
                "Fetch could not authenticate to the BooneOps broker.\n\n"
                "Your message was saved. This is a service configuration issue—contact an operator."
            ),
            context_state="booneops_error",
            metadata={"status_cards": [{"state": "Configuration issue", "detail": "Fetch could not authenticate to BooneOps."}]},
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
        return BooneOpsBrokerTurnResult(
            assistant_text=(
                "BooneOps encountered a server error.\n\n"
                "Your message was saved; try again later."
            ),
            context_state="booneops_error",
            metadata={"status_cards": [{"state": "BooneOps server error", "detail": "The broker or an upstream dependency failed."}]},
        )

    if response.status_code >= 400:
        text, metadata = build_broker_message_presentation(data, route_label)
        if text.strip():
            return BooneOpsBrokerTurnResult(
                assistant_text=text, context_state="booneops_error", metadata=metadata
            )
        return BooneOpsBrokerTurnResult(
            assistant_text=(
                "BooneOps denied this request.\n\n"
                "Your message was saved; contact an operator if you need access."
            ),
            context_state="booneops_error",
        )

    text, metadata = build_broker_message_presentation(data, route_label)
    errs = data.get("errors") if isinstance(data.get("errors"), list) else []
    ok = bool(data.get("ok", True))
    policy = any(
        isinstance(e, dict) and str(e.get("code") or "") == "policy_denied" for e in errs
    )
    ctx = "booneops_error" if policy or ok is False else "booneops"

    return BooneOpsBrokerTurnResult(assistant_text=text, context_state=ctx, metadata=metadata)
