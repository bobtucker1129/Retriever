"""Health and version endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth.cloudflare import get_identity_from_request
from app.auth.sessions import current_user_from_identity
from app.config import AppSettings
from app.dependencies import settings_dependency
from app.services.health import overall_status, readiness_checks

router = APIRouter(tags=["health"])
templates = Jinja2Templates(directory="app/templates")


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept.lower()


def _template_user(request: Request, settings: AppSettings):
    try:
        identity = get_identity_from_request(request, settings)
        return current_user_from_identity(identity, settings)
    except Exception:
        return None


@router.get("/health/live")
async def health_live(
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
) -> Any:
    payload = {
        "status": "ok",
        "app": "retriever-rebuild",
        "environment": settings.retriever_env.value,
    }
    if _wants_html(request):
        return templates.TemplateResponse(
            request,
            "system/status.html",
            {
                "settings": settings,
                "user": _template_user(request, settings),
                "page_title": "Health",
                "active_nav": None,
                "status_title": "Health",
                "status_label": "Live",
                "status": payload["status"],
                "rows": [
                    ("App", payload["app"]),
                    ("Environment", payload["environment"]),
                ],
                "checks": None,
            },
        )
    return payload


@router.get("/health/ready")
async def health_ready(
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
) -> Any:
    checks = readiness_checks(settings)
    payload = {
        "status": overall_status(checks),
        "environment": settings.retriever_env.value,
        "checks": checks,
    }
    if _wants_html(request):
        return templates.TemplateResponse(
            request,
            "system/status.html",
            {
                "settings": settings,
                "user": _template_user(request, settings),
                "page_title": "Health",
                "active_nav": None,
                "status_title": "Health",
                "status_label": "Ready",
                "status": payload["status"],
                "rows": [("Environment", payload["environment"])],
                "checks": checks,
            },
        )
    return payload


@router.get("/health/deep")
async def health_deep(
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
) -> Any:
    checks = readiness_checks(settings)
    checked_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "status": overall_status(checks),
        "environment": settings.retriever_env.value,
        "checks": checks,
        "config": settings.redacted_summary(),
        "checkedAt": checked_at,
    }
    if _wants_html(request):
        return templates.TemplateResponse(
            request,
            "system/status.html",
            {
                "settings": settings,
                "user": _template_user(request, settings),
                "page_title": "Deep Health",
                "active_nav": None,
                "status_title": "Health",
                "status_label": "Deep",
                "status": payload["status"],
                "rows": [
                    ("Environment", payload["environment"]),
                    ("Checked at", checked_at),
                ],
                "checks": checks,
                "config": payload["config"],
            },
        )
    return payload


@router.get("/version")
async def version(
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
) -> Any:
    payload = {
        "app": "retriever-rebuild",
        "version": settings.app_version,
        "gitSha": settings.git_sha,
        "gitRef": settings.git_ref,
        "builtAt": settings.built_at,
        "deployedAt": settings.deployed_at,
        "environment": settings.retriever_env.value,
        "host": settings.host_name,
    }
    if _wants_html(request):
        return templates.TemplateResponse(
            request,
            "system/version.html",
            {
                "settings": settings,
                "user": _template_user(request, settings),
                "page_title": "Version",
                "active_nav": None,
                "version_info": payload,
            },
        )
    return payload
