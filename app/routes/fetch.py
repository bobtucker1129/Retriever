"""Fetch shell: conversation CRUD (DB-backed) and gated ask stub when Fetch is enabled."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.cloudflare import get_identity_from_request
from app.auth.permissions import CurrentUser
from app.auth.sessions import (
    current_user_from_identity,
    ensure_session_cookie,
    require_active_user,
)
from app.config import AppSettings
from app.db.connection import create_connection
from app.db.repositories.fetch import FetchRepository
from app.dependencies import settings_dependency
from app.fetch.answer_render import (
    assistant_body_html,
    build_assistant_status_line,
    fetch_assistant_body_display,
    fetch_thread_load_metadata_for_turn,
)
from app.fetch.safe_links import safe_fetch_download_href
from app.fetch.booneops_broker import (
    BooneOpsBrokerTurnResult,
    BrokerArtifactProxyFailure,
    call_booneops_broker,
    normalize_and_validate_booneops_artifact_id,
    prior_messages_from_history,
    proxy_booneops_artifact_download_response,
)
from app.fetch.followup_routing import (
    html_export_prior_assistant,
    is_artifact_refinement_followup_text,
    is_answer_snapshot_pdf_followup_text,
    is_export_download_followup_text,
    is_export_format_request_text,
    is_html_export_followup_text,
    pdf_export_prior_assistant,
    resolve_fetch_ask_route,
)
from app.fetch.report_context import report_context_from_prior_assistant_table
from app.fetch.general_llm import (
    GeneralLlmTurnResult,
    call_email_cleanup_llm,
    call_general_conversation_llm,
    should_use_general_llm,
)
from app.fetch.artifact_retention import (
    filter_message_metadata_for_local_retention,
    prune_expired_local_html_exports,
    unlink_local_snapshot_files_from_messages,
)
from app.fetch.html_export import (
    HTML_EXPORT_NEED_PRIOR_REPLY,
    PDF_EXPORT_NEED_PRIOR_REPLY,
    build_local_html_export_artifact_entry,
    build_local_pdf_export_artifact_entry,
    build_standalone_html_export_document,
    convert_html_export_document_to_pdf,
    resolve_export_disk_path,
    resolve_pdf_export_disk_path,
    short_html_export_confirmation,
    short_pdf_export_confirmation,
    write_html_export_file,
    write_pdf_export_file,
)
from app.fetch.local_routing import (
    build_fetch_stub_reply,
    classify_fetch_intent,
    should_delegate_ask_to_booneops_broker,
)

router = APIRouter(prefix="/fetch", tags=["fetch"])
booneops_artifact_compat_router = APIRouter(tags=["fetch"])
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["fetch_assistant_body"] = assistant_body_html
templates.env.filters["fetch_assistant_status"] = build_assistant_status_line
templates.env.filters["fetch_assistant_body_display"] = fetch_assistant_body_display
templates.env.filters["fetch_safe_artifact_href"] = safe_fetch_download_href

logger = logging.getLogger(__name__)


def _last_user_message_id(messages: list) -> Optional[str]:
    for record in reversed(messages):
        if getattr(record, "role", None) == "user":
            return str(getattr(record, "message_id", "") or "") or None
    return None


def _has_exportable_prior_assistant(records: list) -> bool:
    for record in reversed(records):
        if getattr(record, "role", None) != "assistant":
            continue
        state = str(getattr(record, "context_state", "") or "").strip().lower()
        if state and state not in {"stub", "booneops_error", "error"}:
            return True
    return False


_FETCH_ACCESS_MSG = "Fetch access is required"
_NO_DB_MSG = "Conversation storage requires a configured database"
_FETCH_ASK_DISABLED_MSG = "Fetch ask is not permitted for this account"
_MAX_SAVED_FETCH_ASSISTANT_CHARS = 60_000
_MAX_SAVED_FETCH_METADATA_JSON_BYTES = 250_000
_FETCH_ASSISTANT_TRIM_NOTICE = (
    "\n\n[Fetch trimmed this answer before saving because it was too large for the chat log. "
    "Ask for a narrower range or request an Excel, CSV, or PDF export for the full detail.]"
)
_FETCH_ASSISTANT_SAVE_FAILURE_MSG = (
    "BooneOps returned an answer, but Retriever could not save the full reply in this chat. "
    "Try a narrower date range or request the result as an Excel, CSV, or PDF report."
)


def _trim_fetch_assistant_text_for_storage(text: str) -> str:
    if len(text) <= _MAX_SAVED_FETCH_ASSISTANT_CHARS:
        return text
    keep = max(0, _MAX_SAVED_FETCH_ASSISTANT_CHARS - len(_FETCH_ASSISTANT_TRIM_NOTICE))
    return text[:keep].rstrip() + _FETCH_ASSISTANT_TRIM_NOTICE


def _metadata_json_size(metadata: dict[str, Any]) -> int:
    return len(json.dumps(metadata, separators=(",", ":"), default=str).encode("utf-8"))


def _bounded_fetch_assistant_metadata(metadata: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not metadata:
        return None
    bounded = dict(metadata)
    try:
        if _metadata_json_size(bounded) <= _MAX_SAVED_FETCH_METADATA_JSON_BYTES:
            return bounded
    except (TypeError, ValueError):
        logger.warning("Fetch assistant metadata is not JSON-serializable; saving minimal metadata.")
        return {"fetch_metadata_truncated": True}

    removed: list[str] = []
    for key in ("reportContext", "report_context", "sessionContext", "session_context"):
        if key in bounded:
            bounded.pop(key, None)
            removed.append(key)
    if removed:
        bounded["fetch_metadata_truncated"] = True
        bounded["fetch_metadata_truncated_keys"] = removed
    try:
        if _metadata_json_size(bounded) <= _MAX_SAVED_FETCH_METADATA_JSON_BYTES:
            return bounded
    except (TypeError, ValueError):
        pass

    slim: dict[str, Any] = {"fetch_metadata_truncated": True}
    for key in (
        "artifacts",
        "source_cards",
        "booneops_actions",
        "gateway_model_id",
        "fetch_thread_load_bucket",
        "fetch_thread_load_chars",
    ):
        if key in bounded:
            slim[key] = bounded[key]
    try:
        if _metadata_json_size(slim) <= _MAX_SAVED_FETCH_METADATA_JSON_BYTES:
            return slim
    except (TypeError, ValueError):
        pass
    return {"fetch_metadata_truncated": True}


def _append_fetch_assistant_message_safely(
    repo: FetchRepository,
    user_id: int,
    conversation_id: str,
    *,
    content: str,
    route_key: str,
    model_label: Optional[str],
    context_state: str,
    metadata: Optional[dict[str, Any]],
) -> None:
    safe_content = _trim_fetch_assistant_text_for_storage(content)
    safe_metadata = _bounded_fetch_assistant_metadata(metadata)
    try:
        repo.append_message(
            user_id,
            conversation_id,
            role="assistant",
            content=safe_content,
            route_key=route_key,
            model_label=model_label,
            context_percent=0,
            context_state=context_state,
            metadata=safe_metadata,
        )
        return
    except Exception:
        logger.exception("Fetch assistant message save failed; saving compact fallback.")
    repo.append_message(
        user_id,
        conversation_id,
        role="assistant",
        content=_FETCH_ASSISTANT_SAVE_FAILURE_MSG,
        route_key=route_key,
        model_label=model_label,
        context_percent=0,
        context_state="booneops_error" if context_state == "booneops" else context_state,
        metadata={"fetch_save_failed": True},
    )


def _has_db(settings: AppSettings) -> bool:
    return bool(settings.mysql_host and settings.mysql_user and settings.mysql_password)


def _repository(settings: AppSettings) -> Optional[FetchRepository]:
    if not _has_db(settings):
        return None
    return FetchRepository(lambda: create_connection(settings))


def _metadata_contains_artifact_reference(
    value: Any,
    *,
    artifact_id: Optional[str],
    download_paths: tuple[str, ...],
) -> bool:
    if isinstance(value, dict):
        if artifact_id and str(value.get("artifactId") or "").strip() == artifact_id:
            return True
        raw_download = str(value.get("downloadPath") or "").strip()
        if raw_download and raw_download in download_paths:
            return True
        return any(
            _metadata_contains_artifact_reference(
                item, artifact_id=artifact_id, download_paths=download_paths
            )
            for item in value.values()
        )
    if isinstance(value, list):
        return any(
            _metadata_contains_artifact_reference(
                item, artifact_id=artifact_id, download_paths=download_paths
            )
            for item in value
        )
    if isinstance(value, str):
        raw = value.strip()
        return raw in download_paths
    return False


def _user_has_fetch_artifact_reference(
    repo: FetchRepository,
    user_id: int,
    *,
    artifact_id: Optional[str] = None,
    download_paths: tuple[str, ...] = (),
) -> bool:
    """Return true when a user's saved Fetch metadata references an artifact download."""
    for conversation in repo.list_conversations(user_id):
        for message in repo.list_messages(user_id, conversation.conversation_id):
            metadata = message.metadata
            if isinstance(metadata, dict) and _metadata_contains_artifact_reference(
                metadata,
                artifact_id=artifact_id,
                download_paths=download_paths,
            ):
                return True
    return False


def _require_fetch_shell_user(user: CurrentUser) -> None:
    require_active_user(user)
    if not user.can_open_fetch_shell():
        raise HTTPException(status_code=403, detail=_FETCH_ACCESS_MSG)


def _prepare_fetch_shell_messages(messages: list, settings: AppSettings) -> list:
    """Drop expired / missing local HTML/PDF snapshot cards; broker cards unchanged."""
    if not messages:
        return messages
    now = datetime.now(timezone.utc)
    out: list = []
    for record in messages:
        filtered = filter_message_metadata_for_local_retention(
            record.metadata,
            settings,
            now_utc=now,
            message_created_at=record.created_at,
        )
        if filtered is record.metadata:
            out.append(record)
        else:
            out.append(replace(record, metadata=filtered))
    return out


@router.get("", response_class=HTMLResponse)
async def fetch_shell(
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
    c: Optional[str] = None,
    rename: Optional[str] = None,
    focus: Optional[str] = None,
):
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)

    if user.status != "active":
        return templates.TemplateResponse(
            request,
            "fetch/forbidden.html",
            {
                "settings": settings,
                "user": user,
                "active_nav": "fetch",
                "fetch_forbidden_reason": "inactive",
                "nav_shell": "minimal" if user.status == "pending" else "full",
            },
            status_code=403,
        )

    if not user.can_open_fetch_shell():
        return templates.TemplateResponse(
            request,
            "fetch/forbidden.html",
            {
                "settings": settings,
                "user": user,
                "active_nav": "fetch",
                "fetch_forbidden_reason": "no_module",
                "nav_shell": "full",
            },
            status_code=403,
        )

    repo = _repository(settings)
    conversations: list = []
    messages: list = []
    active_id: Optional[str] = None
    warn_no_db = repo is None

    if repo is not None:
        conversations = repo.list_conversations(user.id)
        if not conversations:
            repo.adopt_conversations_for_identity(user.id, user.email)
            conversations = repo.list_conversations(user.id)
        if (
            not conversations
            and settings.fetch_enabled
            and user.can_submit_fetch_ask()
        ):
            created = repo.create_conversation(user_id=user.id)
            conversations = [created]
        if c:
            current = repo.get_conversation(user.id, c)
            if current:
                active_id = c
            else:
                active_id = conversations[0].conversation_id if conversations else None
        else:
            active_id = conversations[0].conversation_id if conversations else None

        if rename and not any(conv.conversation_id == rename for conv in conversations):
            rename = None

        if active_id:
            messages = repo.list_messages(user.id, active_id)
            messages = _prepare_fetch_shell_messages(messages, settings)

    fetch_can_use_composer = bool(
        settings.fetch_enabled
        and not warn_no_db
        and active_id
        and user.can_submit_fetch_ask()
    )
    fetch_composer_disabled_reason = ""
    if settings.fetch_enabled and not fetch_can_use_composer:
        if warn_no_db:
            fetch_composer_disabled_reason = "Connect MySQL to send messages."
        elif not active_id:
            fetch_composer_disabled_reason = "Select or create a conversation first."
        else:
            fetch_composer_disabled_reason = (
                "Ask Fetch requires active Fetch module or Fetch access permission."
            )

    last_user_mid = _last_user_message_id(messages) if active_id else None
    # Anchor to newest turn whenever this thread already has turns; refresh without ?focus stays at bottom.
    # Opt-out: ?focus=history (read transcript from the top).
    fetch_focus_latest = bool(
        active_id and messages and focus != "history"
    )

    response = templates.TemplateResponse(
        request,
        "fetch/shell.html",
        {
            "settings": settings,
            "user": user,
            "active_nav": "fetch",
            "conversations": conversations,
            "active_conversation_id": active_id,
            "rename_conversation_id": rename,
            "messages": messages,
            "fetch_can_use_composer": fetch_can_use_composer,
            "fetch_composer_disabled_reason": fetch_composer_disabled_reason,
            "warn_no_db": warn_no_db,
            "fetch_focus_latest": fetch_focus_latest,
            "last_user_message_id": last_user_mid,
        },
    )
    ensure_session_cookie(request, response, user, settings)
    return response


@router.post("/conversations/new", response_class=RedirectResponse)
async def new_conversation(
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
    title: str = Form("New Fetch conversation"),
):
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)
    _require_fetch_shell_user(user)
    repo = _repository(settings)
    if repo is None:
        raise HTTPException(status_code=503, detail=_NO_DB_MSG)
    created = repo.create_conversation(user_id=user.id, title=title)
    return RedirectResponse(url=f"/fetch?c={created.conversation_id}", status_code=303)


@router.post("/conversations/{conversation_id}/rename", response_class=RedirectResponse)
async def rename_conversation(
    conversation_id: str,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
    title: str = Form(...),
):
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)
    _require_fetch_shell_user(user)
    repo = _repository(settings)
    if repo is None:
        raise HTTPException(status_code=503, detail=_NO_DB_MSG)
    if repo.get_conversation(user.id, conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    repo.rename_conversation(user.id, conversation_id, title)
    return RedirectResponse(url=f"/fetch?c={conversation_id}", status_code=303)


@router.post("/conversations/{conversation_id}/delete", response_class=RedirectResponse)
async def delete_conversation_route(
    conversation_id: str,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)
    _require_fetch_shell_user(user)
    repo = _repository(settings)
    if repo is None:
        raise HTTPException(status_code=503, detail=_NO_DB_MSG)
    if repo.get_conversation(user.id, conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = repo.list_messages(user.id, conversation_id)
    unlink_local_snapshot_files_from_messages(messages, settings)
    repo.soft_delete_conversation(user.id, conversation_id)
    return RedirectResponse(url="/fetch", status_code=303)


def _serve_booneops_broker_artifact_download(
    artifact_id: str,
    request: Request,
    settings: AppSettings,
):
    validated = normalize_and_validate_booneops_artifact_id(artifact_id)
    if not validated:
        raise HTTPException(status_code=400, detail="Invalid artifact id")
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)
    _require_fetch_shell_user(user)
    if not (settings.booneops_broker_url or "").strip() or not (
        settings.booneops_broker_bearer_token or ""
    ).strip():
        try:
            return proxy_booneops_artifact_download_response(settings, validated)
        except BrokerArtifactProxyFailure as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    repo = _repository(settings)
    if repo is None or not _user_has_fetch_artifact_reference(
        repo,
        user.id,
        artifact_id=validated,
        download_paths=(
            f"/fetch/artifacts/broker/{validated}",
            f"/v1/booneops/artifacts/{validated}",
        ),
    ):
        raise HTTPException(status_code=404, detail="Artifact not found")
    try:
        return proxy_booneops_artifact_download_response(settings, validated)
    except BrokerArtifactProxyFailure as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@router.get("/artifacts/broker/{artifact_id}")
def download_booneops_broker_artifact(
    artifact_id: str,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    """Stream a BooneOps-generated artifact; browser never sees broker credentials."""
    return _serve_booneops_broker_artifact_download(artifact_id, request, settings)


@booneops_artifact_compat_router.get("/v1/booneops/artifacts/{artifact_id}")
def download_booneops_broker_artifact_compat_route(
    artifact_id: str,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    """Compatibility path for artifact links saved before canonical ``/fetch/artifacts/broker/``."""
    return _serve_booneops_broker_artifact_download(artifact_id, request, settings)


@router.get("/artifacts/html/{stem}.html")
async def download_fetch_html_export(
    stem: str,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    """Serve locally generated HTML exports (uuid stem only; under report directory)."""
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)
    _require_fetch_shell_user(user)
    repo = _repository(settings)
    download_path = f"/fetch/artifacts/html/{stem}.html"
    if repo is None or not _user_has_fetch_artifact_reference(
        repo, user.id, download_paths=(download_path,)
    ):
        raise HTTPException(status_code=404, detail="Export not found")

    path_obj = resolve_export_disk_path(settings, stem)
    if path_obj is None or not path_obj.is_file():
        raise HTTPException(status_code=404, detail="Export not found")
    return FileResponse(
        path=str(path_obj),
        media_type="text/html; charset=utf-8",
        filename="fetch-answer-export.html",
    )


@router.get("/artifacts/pdf/{stem}.pdf")
async def download_fetch_pdf_export(
    stem: str,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    """Serve locally generated answer snapshots as PDF (uuid stem only under report directory)."""
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)
    _require_fetch_shell_user(user)
    repo = _repository(settings)
    download_path = f"/fetch/artifacts/pdf/{stem}.pdf"
    if repo is None or not _user_has_fetch_artifact_reference(
        repo, user.id, download_paths=(download_path,)
    ):
        raise HTTPException(status_code=404, detail="Export not found")

    path_obj = resolve_pdf_export_disk_path(settings, stem)
    if path_obj is None or not path_obj.is_file():
        raise HTTPException(status_code=404, detail="Export not found")
    return FileResponse(
        path=str(path_obj),
        media_type="application/pdf",
        filename="fetch-answer-export.pdf",
    )


@router.post("/conversations/{conversation_id}/ask", response_class=RedirectResponse)
async def ask_in_conversation(
    conversation_id: str,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
    question: str = Form(""),
):
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)
    _require_fetch_shell_user(user)
    if not settings.fetch_enabled:
        return RedirectResponse(url=f"/fetch?c={conversation_id}", status_code=303)
    if not user.can_submit_fetch_ask():
        raise HTTPException(status_code=403, detail=_FETCH_ASK_DISABLED_MSG)
    repo = _repository(settings)
    if repo is None:
        raise HTTPException(status_code=503, detail=_NO_DB_MSG)
    if repo.get_conversation(user.id, conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    cleaned = " ".join(question.split()).strip()
    if not cleaned:
        return RedirectResponse(url=f"/fetch?c={conversation_id}", status_code=303)
    base_route = classify_fetch_intent(cleaned)
    prior_records = repo.list_messages(user.id, conversation_id)
    html_prior = html_export_prior_assistant(prior_records, cleaned)
    pdf_prior = pdf_export_prior_assistant(prior_records, cleaned)
    route, session_metadata_extra = resolve_fetch_ask_route(cleaned, base_route, prior_records)
    if is_html_export_followup_text(cleaned):
        route = "fetch_html_export"
        session_metadata_extra = {}
    elif is_answer_snapshot_pdf_followup_text(cleaned):
        route = "fetch_pdf_export"
        session_metadata_extra = {}
    repo.append_message(
        user.id,
        conversation_id,
        role="user",
        content=cleaned,
        route_key=route,
    )

    request_id = str(uuid.uuid4())
    export_or_refinement_without_prior_context = (
        route in ("general_candidate", "unknown", "local")
        and (
            is_export_download_followup_text(cleaned)
            or is_export_format_request_text(cleaned)
            or is_artifact_refinement_followup_text(cleaned)
        )
        and not _has_exportable_prior_assistant(prior_records)
    )
    if (
        not export_or_refinement_without_prior_context
        and (
            is_export_download_followup_text(cleaned)
            or is_export_format_request_text(cleaned)
            or is_artifact_refinement_followup_text(cleaned)
        )
        and "reportContext" not in session_metadata_extra
        and "report_context" not in session_metadata_extra
    ):
        prior_report_context = report_context_from_prior_assistant_table(
            prior_records,
            conversation_id=conversation_id,
            request_id=request_id,
        )
        if prior_report_context is not None:
            session_metadata_extra = {
                **session_metadata_extra,
                "reportContext": prior_report_context,
            }
    use_broker = should_delegate_ask_to_booneops_broker(route, settings) and not (
        export_or_refinement_without_prior_context
    )
    use_general_llm = should_use_general_llm(route, settings) and not (
        use_broker
        or
        is_export_download_followup_text(cleaned)
        or is_artifact_refinement_followup_text(cleaned)
    )
    if route == "fetch_html_export":
        if html_prior is not None:
            doc = build_standalone_html_export_document(
                html_prior.content,
                source_route_label=(html_prior.route_key or "prior").strip(),
            )
            download_path, _disk = write_html_export_file(settings, doc)
            prune_expired_local_html_exports(settings)
            assistant_text = short_html_export_confirmation()
            context_state = "ready"
            model_label = settings.model_default
            assistant_metadata = {
                "artifacts": [
                    build_local_html_export_artifact_entry(download_path, settings),
                ]
            }
        else:
            assistant_text = HTML_EXPORT_NEED_PRIOR_REPLY
            context_state = "stub"
            model_label = settings.model_default
            assistant_metadata = None
    elif route == "fetch_pdf_export":
        if pdf_prior is not None:
            doc = build_standalone_html_export_document(
                pdf_prior.content,
                source_route_label=(pdf_prior.route_key or "prior").strip(),
            )
            pdf_bytes, pdf_err = convert_html_export_document_to_pdf(doc)
            if pdf_bytes is None:
                lead = pdf_err or "PDF export failed on this server."
                assistant_text = f"{lead}\n\nNothing was saved as a downloadable file.\n\n"
                assistant_text += (
                    "You can still export the same answer as HTML from Fetch when that path is enabled."
                )
                context_state = "stub"
                model_label = settings.model_default
                assistant_metadata = None
            else:
                download_path, _disk_pdf = write_pdf_export_file(settings, pdf_bytes)
                prune_expired_local_html_exports(settings)
                assistant_text = short_pdf_export_confirmation()
                context_state = "ready"
                model_label = settings.model_default
                assistant_metadata = {
                    "artifacts": [
                        build_local_pdf_export_artifact_entry(download_path, settings),
                    ]
                }
        else:
            assistant_text = PDF_EXPORT_NEED_PRIOR_REPLY
            context_state = "stub"
            model_label = settings.model_default
            assistant_metadata = None
    elif use_general_llm:
        llm_result: GeneralLlmTurnResult = call_general_conversation_llm(
            settings,
            user_message=cleaned,
            prior_records=prior_records,
        )
        assistant_text = llm_result.assistant_text
        context_state = llm_result.context_state
        model_label = llm_result.model_label or settings.model_default
        assistant_metadata = dict(llm_result.metadata) if llm_result.metadata else {}
        assistant_metadata.update(
            fetch_thread_load_metadata_for_turn(prior_records, cleaned, assistant_text)
        )
    elif use_broker:
        prior_messages = prior_messages_from_history(prior_records)
        broker_result: BooneOpsBrokerTurnResult = call_booneops_broker(
            settings,
            user=user,
            conversation_id=conversation_id,
            user_message=cleaned,
            route_label=route,
            request_id=request_id,
            prior_messages=prior_messages,
            session_metadata_extra=session_metadata_extra or None,
        )
        assistant_text = broker_result.assistant_text
        context_state = broker_result.context_state
        assistant_metadata = broker_result.metadata
        if assistant_metadata is None:
            assistant_metadata = {}
        else:
            assistant_metadata = dict(assistant_metadata)
        assistant_metadata.update(
            fetch_thread_load_metadata_for_turn(prior_records, cleaned, assistant_text)
        )
        slug = str(assistant_metadata.get("gateway_model_id") or "").strip()
        model_label = (
            slug
            if slug
            else (None if context_state in ("booneops", "booneops_error") else settings.model_default)
        )
    else:
        assistant_text = build_fetch_stub_reply(route)
        context_state = "stub"
        model_label = settings.model_default
        assistant_metadata = None

    _append_fetch_assistant_message_safely(
        repo,
        user.id,
        conversation_id,
        content=assistant_text,
        route_key=route,
        model_label=model_label,
        context_state=context_state,
        metadata=assistant_metadata,
    )
    response = RedirectResponse(
        url="/fetch?" + urlencode({"c": conversation_id}),
        status_code=303,
    )
    ensure_session_cookie(request, response, user, settings)
    return response


@router.post("/conversations/{conversation_id}/cleanup-email", response_class=RedirectResponse)
async def cleanup_email_in_conversation(
    conversation_id: str,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
    question: str = Form(""),
):
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)
    _require_fetch_shell_user(user)
    if not settings.fetch_enabled:
        return RedirectResponse(url=f"/fetch?c={conversation_id}", status_code=303)
    if not user.can_submit_fetch_ask():
        raise HTTPException(status_code=403, detail=_FETCH_ASK_DISABLED_MSG)
    repo = _repository(settings)
    if repo is None:
        raise HTTPException(status_code=503, detail=_NO_DB_MSG)
    if repo.get_conversation(user.id, conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    draft = question.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not draft:
        return RedirectResponse(url=f"/fetch?c={conversation_id}", status_code=303)

    prior_records = repo.list_messages(user.id, conversation_id)
    repo.append_message(
        user.id,
        conversation_id,
        role="user",
        content=draft,
        route_key="email_cleanup",
    )

    llm_result: GeneralLlmTurnResult = call_email_cleanup_llm(
        settings,
        email_draft=draft,
    )
    assistant_text = llm_result.assistant_text
    assistant_metadata = dict(llm_result.metadata) if llm_result.metadata else {}
    assistant_metadata["email_cleanup"] = True
    assistant_metadata.update(
        fetch_thread_load_metadata_for_turn(prior_records, draft, assistant_text)
    )
    assistant = repo.append_message(
        user.id,
        conversation_id,
        role="assistant",
        content=assistant_text,
        route_key="email_cleanup",
        model_label=llm_result.model_label or settings.model_default,
        context_percent=0,
        context_state=llm_result.context_state,
        metadata=assistant_metadata,
    )
    response = RedirectResponse(
        url="/fetch?" + urlencode({"c": conversation_id, "focus": "latest"}),
        status_code=303,
    )
    ensure_session_cookie(request, response, user, settings)
    response.headers["X-Fetch-Assistant-Message-Id"] = assistant.message_id
    return response
