"""FastAPI entrypoint for the new Retriever auth shell."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.middleware.request_id import RequestIdMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.routes import admin, auth_shell, fetch, health, prepress

_STATIC_ROOT = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Retriever",
        version=settings.app_version,
        docs_url=None if settings.retriever_env != "local" else "/docs",
        redoc_url=None,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.mount("/static", StaticFiles(directory=str(_STATIC_ROOT)), name="static")

    app.include_router(health.router)
    app.include_router(auth_shell.router)
    app.include_router(admin.router)
    app.include_router(prepress.router)
    app.include_router(fetch.router)
    app.include_router(fetch.booneops_artifact_compat_router)
    return app


app = create_app()
