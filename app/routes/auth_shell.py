"""Auth shell routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.cloudflare import get_identity_from_request
from app.auth.sessions import (
    current_user_from_identity,
    ensure_session_cookie,
    revoke_session_cookie,
)
from app.config import AppSettings
from app.dependencies import settings_dependency

router = APIRouter(tags=["auth-shell"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)
    if user.status != "active":
        return templates.TemplateResponse(
            request,
            "pending.html",
            {"user": user, "settings": settings, "active_nav": "home"},
        )
    response = templates.TemplateResponse(
        request,
        "base.html",
        {"user": user, "settings": settings, "page_title": "Retriever", "active_nav": "home"},
    )
    ensure_session_cookie(request, response, user, settings)
    return response


@router.post("/logout")
async def logout(
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    response = RedirectResponse(url="/", status_code=303)
    revoke_session_cookie(request, response, settings)
    return response

