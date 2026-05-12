"""Fetch shell: conversation CRUD (DB-backed) and gated ask stub when Fetch is enabled."""

from __future__ import annotations

import uuid
from typing import Optional
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
from app.fetch.answer_render import assistant_body_html, build_assistant_status_line
from app.fetch.safe_links import safe_fetch_download_href
from app.fetch.booneops_broker import (
    BooneOpsBrokerTurnResult,
    call_booneops_broker,
    prior_messages_from_history,
)
from app.fetch.followup_routing import (
    html_export_prior_assistant,
    is_html_export_followup_text,
    resolve_fetch_ask_route,
)
from app.fetch.html_export import (
    HTML_EXPORT_NEED_PRIOR_REPLY,
    build_standalone_html_export_document,
    resolve_export_disk_path,
    short_html_export_confirmation,
    write_html_export_file,
)
from app.fetch.local_routing import (
    build_fetch_stub_reply,
    classify_fetch_intent,
    should_delegate_ask_to_booneops_broker,
)

router = APIRouter(prefix="/fetch", tags=["fetch"])
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["fetch_assistant_body"] = assistant_body_html
templates.env.filters["fetch_assistant_status"] = build_assistant_status_line
templates.env.filters["fetch_safe_artifact_href"] = safe_fetch_download_href


def _last_user_message_id(messages: list) -> Optional[str]:
    for record in reversed(messages):
        if getattr(record, "role", None) == "user":
            return str(getattr(record, "message_id", "") or "") or None
    return None

_FETCH_ACCESS_MSG = "Fetch access is required"
_NO_DB_MSG = "Conversation storage requires a configured database"
_FETCH_ASK_DISABLED_MSG = "Fetch ask is not permitted for this account"


def _has_db(settings: AppSettings) -> bool:
    return bool(settings.mysql_host and settings.mysql_user and settings.mysql_password)


def _repository(settings: AppSettings) -> Optional[FetchRepository]:
    if not _has_db(settings):
        return None
    return FetchRepository(lambda: create_connection(settings))


def _require_fetch_shell_user(user: CurrentUser) -> None:
    require_active_user(user)
    if not user.can_open_fetch_shell():
        raise HTTPException(status_code=403, detail=_FETCH_ACCESS_MSG)


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
    repo.soft_delete_conversation(user.id, conversation_id)
    return RedirectResponse(url="/fetch", status_code=303)


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

    path_obj = resolve_export_disk_path(settings, stem)
    if path_obj is None or not path_obj.is_file():
        raise HTTPException(status_code=404, detail="Export not found")
    return FileResponse(
        path=str(path_obj),
        media_type="text/html; charset=utf-8",
        filename="fetch-answer-export.html",
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
    route, session_metadata_extra = resolve_fetch_ask_route(cleaned, base_route, prior_records)
    if is_html_export_followup_text(cleaned):
        route = "fetch_html_export"
        session_metadata_extra = {}
    repo.append_message(
        user.id,
        conversation_id,
        role="user",
        content=cleaned,
        route_key=route,
    )

    request_id = str(uuid.uuid4())
    use_broker = should_delegate_ask_to_booneops_broker(route, settings)
    if route == "fetch_html_export":
        if html_prior is not None:
            doc = build_standalone_html_export_document(
                html_prior.content,
                source_route_label=(html_prior.route_key or "prior").strip(),
            )
            download_path, _disk = write_html_export_file(settings, doc)
            assistant_text = short_html_export_confirmation()
            context_state = "ready"
            model_label = settings.model_default
            assistant_metadata = {
                "artifacts": [
                    {
                        "filename": "fetch-answer-export.html",
                        "description": "Sanitized standalone HTML snapshot of the prior answer.",
                        "downloadPath": download_path,
                    }
                ]
            }
        else:
            assistant_text = HTML_EXPORT_NEED_PRIOR_REPLY
            context_state = "stub"
            model_label = settings.model_default
            assistant_metadata = None
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
        model_label = settings.model_default
        assistant_metadata = broker_result.metadata
    else:
        assistant_text = build_fetch_stub_reply(route)
        context_state = "stub"
        model_label = settings.model_default
        assistant_metadata = None

    repo.append_message(
        user.id,
        conversation_id,
        role="assistant",
        content=assistant_text,
        route_key=route,
        model_label=model_label,
        context_percent=0,
        context_state=context_state,
        metadata=assistant_metadata,
    )
    response = RedirectResponse(
        url="/fetch?" + urlencode({"c": conversation_id}),
        status_code=303,
    )
    ensure_session_cookie(request, response, user, settings)
    return response
