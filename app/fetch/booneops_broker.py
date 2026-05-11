"""BooneOps broker client: signed POST /v1/booneops/message (Phase 1 contract).

See projects/booneops-bots/BROKER.md and FETCH_HANDOFF.md for the server contract.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Sequence

import httpx

from app.auth.permissions import CurrentUser
from app.config import AppSettings
from app.db.repositories.fetch import FetchMessageRecord

logger = logging.getLogger(__name__)

BOONEOPS_MESSAGE_PATH = "/v1/booneops/message"
_DEFAULT_HTTP_TIMEOUT = 115.0

HttpPostFn = Callable[..., Any]


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
) -> dict[str, Any]:
    caps = sorted(user.capabilities) if user.capabilities else []
    session_metadata: dict[str, Any] = {
        "source": "retriever-fetch",
        "routeLabel": route_label,
        "booneopsLevel": user.booneops_level or "none",
        "retrieverCapabilities": caps,
    }
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


def format_assistant_text_from_broker_json(data: dict[str, Any]) -> str:
    """Build user-visible assistant text from broker JSON (only safe fields)."""
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
            )
        return (
            "BooneOps policy blocked this request.\n\n"
            "Your message was saved; no automated action ran."
        )

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
        )

    if not raw_message:
        return (
            "BooneOps returned an empty reply.\n\n"
            "Your message was saved; try again in a moment."
        )

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
    return "\n".join(lines)


@dataclass(frozen=True)
class BooneOpsBrokerTurnResult:
    assistant_text: str
    context_state: str


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
    http_post: Optional[HttpPostFn] = None,
) -> BooneOpsBrokerTurnResult:
    """POST a signed broker message; never logs secrets or raw bearer tokens."""
    bot_id, role = map_user_to_broker_principal(user)
    payload = build_broker_payload(
        bot_id=bot_id,
        role=role,
        user=user,
        conversation_id=conversation_id,
        user_message=user_message,
        request_id=request_id,
        route_label=route_label,
        prior_messages=prior_messages,
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
        )

    if response.status_code == 401:
        logger.warning("BooneOps broker auth rejected request_id=%s", request_id)
        return BooneOpsBrokerTurnResult(
            assistant_text=(
                "Fetch could not authenticate to the BooneOps broker.\n\n"
                "Your message was saved. This is a service configuration issue—contact an operator."
            ),
            context_state="booneops_error",
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
        )

    if response.status_code >= 400:
        text = format_assistant_text_from_broker_json(data)
        if text.strip():
            return BooneOpsBrokerTurnResult(assistant_text=text, context_state="booneops_error")
        return BooneOpsBrokerTurnResult(
            assistant_text=(
                "BooneOps denied this request.\n\n"
                "Your message was saved; contact an operator if you need access."
            ),
            context_state="booneops_error",
        )

    text = format_assistant_text_from_broker_json(data)
    errs = data.get("errors") if isinstance(data.get("errors"), list) else []
    ok = bool(data.get("ok", True))
    policy = any(
        isinstance(e, dict) and str(e.get("code") or "") == "policy_denied" for e in errs
    )
    ctx = "booneops_error" if policy or ok is False else "booneops"

    return BooneOpsBrokerTurnResult(assistant_text=text, context_state=ctx)
