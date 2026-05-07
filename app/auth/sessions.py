"""Current-user profile lookup and session cookie helpers."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request
from starlette.responses import Response

from app.auth.cloudflare import CloudflareIdentity
from app.auth.permissions import CurrentUser
from app.config import AppSettings, RetrieverEnvironment
from app.db.connection import create_connection
from app.db.repositories.sessions import SessionRepository
from app.db.repositories.users import UserRecord, UserRepository

SESSION_COOKIE_NAME = "retriever_session"


def current_user_from_identity(
    identity: CloudflareIdentity,
    settings: AppSettings,
    repository: Optional[UserRepository] = None,
) -> CurrentUser:
    """Return the current Retriever user, creating pending profiles when DB is configured."""

    if repository is None and _has_db_config(settings):
        repository = UserRepository(lambda: create_connection(settings))

    if repository is not None:
        record = repository.ensure_profile(identity, settings.retriever_seed_admin_email)
        return _current_user_from_record(record)

    return _local_scaffold_user(identity, settings)


def _current_user_from_record(record: UserRecord) -> CurrentUser:
    return CurrentUser(
        id=record.id,
        email=record.email,
        display_name=record.display_name,
        status=record.status,
        capabilities=record.capabilities,
        modules=record.modules,
        is_admin=record.is_admin,
    )


def _local_scaffold_user(identity: CloudflareIdentity, settings: AppSettings) -> CurrentUser:
    is_seed_admin = identity.email == settings.retriever_seed_admin_email
    if is_seed_admin:
        return CurrentUser(
            id=0,
            email=identity.email,
            display_name=identity.display_name or identity.email,
            status="active",
            capabilities=frozenset({"admin.manage_users", "admin.manage_settings"}),
            modules=frozenset({"admin", "help"}),
            is_admin=True,
        )

    return CurrentUser(
        id=0,
        email=identity.email,
        display_name=identity.display_name or identity.email,
        status="pending",
    )


def _has_db_config(settings: AppSettings) -> bool:
    return bool(settings.mysql_host and settings.mysql_user and settings.mysql_password)


def require_active_user(user: CurrentUser) -> None:
    if user.status == "active":
        return
    if user.status == "pending":
        raise HTTPException(status_code=403, detail="Retriever access is pending")
    if user.status in {"suspended", "blocked"}:
        raise HTTPException(status_code=403, detail="Retriever access is disabled")
    raise HTTPException(status_code=403, detail="Retriever access is not active")


def ensure_session_cookie(
    request: Request,
    response: Response,
    user: CurrentUser,
    settings: AppSettings,
    repository: Optional[SessionRepository] = None,
) -> Optional[str]:
    """Ensure an active DB-backed session exists and is present as an opaque cookie."""

    if user.status != "active" or not _has_db_config(settings):
        return None

    repository = repository or SessionRepository(lambda: create_connection(settings))
    existing_session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if existing_session_id and repository.get_active_session(existing_session_id, user.id):
        repository.touch_session(existing_session_id)
        return existing_session_id

    session_id = repository.create_session(
        user_id=user.id,
        cloudflare_email=user.email,
        ttl_seconds=settings.retriever_session_ttl_seconds,
        user_agent=request.headers.get("user-agent"),
        source_ip=request.client.host if request.client else None,
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=settings.retriever_env != RetrieverEnvironment.LOCAL,
        samesite="lax",
        max_age=settings.retriever_session_ttl_seconds,
    )
    return session_id


def revoke_session_cookie(
    request: Request,
    response: Response,
    settings: AppSettings,
    repository: Optional[SessionRepository] = None,
) -> None:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id and _has_db_config(settings):
        repository = repository or SessionRepository(lambda: create_connection(settings))
        repository.revoke_session(session_id)
    response.delete_cookie(SESSION_COOKIE_NAME)

