"""Disabled Fetch placeholder."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth.cloudflare import get_identity_from_request
from app.auth.sessions import current_user_from_identity
from app.config import AppSettings
from app.dependencies import settings_dependency

router = APIRouter(prefix="/fetch", tags=["fetch"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def fetch_disabled(
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)
    return templates.TemplateResponse(
        request,
        "fetch/disabled.html",
        {
            "settings": settings,
            "user": user,
            "active_nav": "fetch",
            "fetch_model_label": settings.model_default or "model not connected",
            "fetch_context_percent": 0,
            "fetch_context_state": "ready",
        },
        status_code=200,
    )

