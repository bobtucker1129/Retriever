"""Dynamic bilingual Help routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth.cloudflare import get_identity_from_request
from app.auth.permissions import CurrentUser
from app.auth.sessions import current_user_from_identity, require_active_user
from app.config import AppSettings
from app.dependencies import settings_dependency
from app.help.content import (
    get_module,
    get_topic,
    topic_visible_to_user,
    visible_modules,
    visible_topics,
)

router = APIRouter(prefix="/help", tags=["help"])
templates = Jinja2Templates(directory="app/templates")


def _current_help_user(
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
) -> CurrentUser:
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)
    require_active_user(user)
    return user


def _context(request: Request, user: CurrentUser, settings: AppSettings) -> dict:
    modules = visible_modules(user)
    return {
        "request": request,
        "user": user,
        "settings": settings,
        "active_nav": "help",
        "nav_shell": "full",
        "modules": modules,
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def help_overview(
    request: Request,
    user: CurrentUser = Depends(_current_help_user),
    settings: AppSettings = Depends(settings_dependency),
):
    context = _context(request, user, settings)
    context["page_title"] = "Help"
    return templates.TemplateResponse(request, "help/overview.html", context)


@router.get("/{module_slug}", response_class=HTMLResponse)
async def help_module(
    module_slug: str,
    request: Request,
    user: CurrentUser = Depends(_current_help_user),
    settings: AppSettings = Depends(settings_dependency),
):
    context = _context(request, user, settings)
    module = get_module(module_slug, context["modules"])
    if module is None:
        raise HTTPException(status_code=404, detail="Help module not found")
    context.update(
        {
            "page_title": f"Help - {module['title']['en']}",
            "module": module,
            "topics": visible_topics(user, module),
        }
    )
    return templates.TemplateResponse(request, "help/module.html", context)


@router.get("/{module_slug}/{topic_slug}", response_class=HTMLResponse)
async def help_topic(
    module_slug: str,
    topic_slug: str,
    request: Request,
    user: CurrentUser = Depends(_current_help_user),
    settings: AppSettings = Depends(settings_dependency),
):
    context = _context(request, user, settings)
    module = get_module(module_slug, context["modules"])
    if module is None:
        raise HTTPException(status_code=404, detail="Help module not found")
    topic = get_topic(module, topic_slug)
    if topic is None or not topic_visible_to_user(user, topic):
        raise HTTPException(status_code=404, detail="Help topic not found")
    context.update(
        {
            "page_title": f"Help - {topic['title']['en']}",
            "module": module,
            "topic": topic,
            "topics": visible_topics(user, module),
        }
    )
    return templates.TemplateResponse(request, "help/topic.html", context)
