"""Admin routes for the first auth shell scaffold."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.cloudflare import get_identity_from_request
from app.auth.sessions import current_user_from_identity, require_active_user
from app.config import AppSettings
from app.db.connection import create_connection
from app.db.repositories.audit import AuditRepository
from app.db.repositories.sessions import SessionRepository
from app.db.repositories.users import UserRepository
from app.dependencies import settings_dependency
from app.services.admin_actions import AdminActionService, AdminRepositories

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/users", response_class=HTMLResponse)
async def users(
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    identity = get_identity_from_request(request, settings)
    user = current_user_from_identity(identity, settings)
    require_active_user(user)
    if not user.has_capability("admin.manage_users"):
        raise HTTPException(status_code=403, detail="Admin access required")

    pending_users = []
    if settings.mysql_host and settings.mysql_user and settings.mysql_password:
        pending_users = UserRepository(lambda: create_connection(settings)).list_pending()

    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "user": user,
            "settings": settings,
            "pending_users": pending_users,
            "active_nav": "admin",
        },
    )


@router.post("/users/{user_id}/activate")
async def activate_user(
    user_id: int,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    _admin_service(settings).activate_user(user_id, actor)
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: int,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    _admin_service(settings).suspend_user(user_id, actor)
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/block")
async def block_user(
    user_id: int,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    _admin_service(settings).block_user(user_id, actor)
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/role")
async def assign_role(
    user_id: int,
    request: Request,
    role_key: str = Form(...),
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    _admin_service(settings).assign_role(user_id, role_key, actor)
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/booneops-level")
async def assign_booneops_level(
    user_id: int,
    request: Request,
    booneops_level: str = Form(...),
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    _admin_service(settings).assign_booneops_level(user_id, booneops_level, actor)
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/module-access")
async def set_module_access(
    user_id: int,
    request: Request,
    module_key: str = Form(...),
    enabled: bool = Form(True),
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    _admin_service(settings).set_module_access(user_id, module_key, enabled, actor)
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/capabilities/grant")
async def grant_capability(
    user_id: int,
    request: Request,
    capability_key: str = Form(...),
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    _admin_service(settings).grant_capability(user_id, capability_key, actor)
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/capabilities/revoke")
async def revoke_capability(
    user_id: int,
    request: Request,
    capability_key: str = Form(...),
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    _admin_service(settings).revoke_capability(user_id, capability_key, actor)
    return RedirectResponse(url="/admin/users", status_code=303)


def _require_admin_actor(request: Request, settings: AppSettings):
    identity = get_identity_from_request(request, settings)
    actor = current_user_from_identity(identity, settings)
    require_active_user(actor)
    if not actor.has_capability("admin.manage_users"):
        raise HTTPException(status_code=403, detail="Admin access required")
    if not settings.mysql_host or not settings.mysql_user or not settings.mysql_password:
        raise HTTPException(status_code=503, detail="Admin actions require database config")
    return actor


def _admin_service(settings: AppSettings) -> AdminActionService:
    connection_factory = lambda: create_connection(settings)
    return AdminActionService(
        AdminRepositories(
            users=UserRepository(connection_factory),
            audit=AuditRepository(connection_factory),
            sessions=SessionRepository(connection_factory),
        )
    )

