"""Admin routes for the first auth shell scaffold."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.cloudflare import get_identity_from_request
from app.auth.sessions import current_user_from_identity, require_active_user
from app.config import AppSettings
from app.db.connection import create_connection
from app.db.mis_connection import create_mis_connection, is_mis_configured
from app.db.repositories.audit import AuditRepository
from app.db.repositories.locations import ProductionLocationRepository
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

    admin_users: list = []
    production_locations: list = []
    if settings.mysql_host and settings.mysql_user and settings.mysql_password:
        connection_factory = lambda: create_connection(settings)
        admin_users = UserRepository(connection_factory).list_users_for_admin_directory()
        try:
            if is_mis_configured(settings):
                production_locations = ProductionLocationRepository(
                    lambda: create_mis_connection(settings),
                    schema_name="public",
                ).list_active()
            else:
                production_locations = ProductionLocationRepository(connection_factory).list_active()
        except Exception:
            production_locations = []

    return templates.TemplateResponse(
        request,
        "admin/users.html",
        {
            "user": user,
            "settings": settings,
            "admin_users": admin_users,
            "production_locations": production_locations,
            "active_nav": "admin",
            "nav_shell": "full",
        },
    )


@router.post("/users/{user_id}/activate")
async def activate_user(
    user_id: int,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    _admin_action(lambda: _admin_service(settings).activate_user(user_id, actor))
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/suspend")
async def suspend_user(
    user_id: int,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    if actor.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot suspend your own account")
    _admin_action(lambda: _admin_service(settings).suspend_user(user_id, actor))
    return RedirectResponse(url="/admin/users", status_code=303)


def _parse_matrix_form_bool(raw: str) -> bool:
    return str(raw).strip().lower() in ("true", "1", "on", "yes")


def _parse_location_choice(raw: str) -> tuple[Optional[int], str]:
    cleaned = str(raw or "").strip()
    if not cleaned:
        return None, ""
    if "|" not in cleaned:
        raise HTTPException(status_code=400, detail="Invalid location")
    location_id, location_name = cleaned.split("|", 1)
    try:
        return int(location_id), location_name.strip()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid location") from exc


def _admin_action(action) -> None:
    try:
        action()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/users/{user_id}/matrix-update")
async def update_user_matrix_row(
    user_id: int,
    request: Request,
    full_name: str = Form(""),
    production_location_choice: str = Form(""),
    admin_module: str = Form("false"),
    fetch_module: str = Form("false"),
    prepress_module: str = Form("false"),
    fetch_access: str = Form("false"),
    dsf_module: str = Form("false"),
    inventory_level: str = Form("no"),
    proofs_level: str = Form("no"),
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    location_id, location_name = _parse_location_choice(production_location_choice)
    _admin_action(
        lambda: _admin_service(settings).apply_user_matrix_row(
            user_id,
            actor,
            full_name=full_name.strip(),
            production_location_id=location_id,
            production_location_name=location_name,
            admin_module=_parse_matrix_form_bool(admin_module),
            fetch_module=_parse_matrix_form_bool(fetch_module),
            prepress_module=_parse_matrix_form_bool(prepress_module),
            fetch_access=_parse_matrix_form_bool(fetch_access),
            dsf_module=_parse_matrix_form_bool(dsf_module),
            inventory_level=inventory_level.strip(),
            proofs_level=proofs_level.strip(),
        )
    )
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/block")
async def block_user(
    user_id: int,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    if actor.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot block your own account")
    _admin_action(lambda: _admin_service(settings).block_user(user_id, actor))
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/delete")
async def delete_user(
    user_id: int,
    request: Request,
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    if actor.id == user_id:
        raise HTTPException(status_code=400, detail="Cannot remove your own account")
    _admin_action(lambda: _admin_service(settings).delete_user(user_id, actor))
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/role")
async def assign_role(
    user_id: int,
    request: Request,
    role_key: str = Form(...),
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    _admin_action(lambda: _admin_service(settings).assign_role(user_id, role_key, actor))
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/booneops-level")
async def assign_booneops_level(
    user_id: int,
    request: Request,
    booneops_level: str = Form(...),
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    _admin_action(lambda: _admin_service(settings).assign_booneops_level(user_id, booneops_level, actor))
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
    _admin_action(lambda: _admin_service(settings).set_module_access(user_id, module_key, enabled, actor))
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/capabilities/grant")
async def grant_capability(
    user_id: int,
    request: Request,
    capability_key: str = Form(...),
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    _admin_action(lambda: _admin_service(settings).grant_capability(user_id, capability_key, actor))
    return RedirectResponse(url="/admin/users", status_code=303)


@router.post("/users/{user_id}/capabilities/revoke")
async def revoke_capability(
    user_id: int,
    request: Request,
    capability_key: str = Form(...),
    settings: AppSettings = Depends(settings_dependency),
):
    actor = _require_admin_actor(request, settings)
    _admin_action(lambda: _admin_service(settings).revoke_capability(user_id, capability_key, actor))
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
