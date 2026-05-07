"""Health and version endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.config import AppSettings
from app.dependencies import settings_dependency
from app.services.health import overall_status, readiness_checks

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def health_live(settings: AppSettings = Depends(settings_dependency)) -> dict[str, str]:
    return {
        "status": "ok",
        "app": "retriever-rebuild",
        "environment": settings.retriever_env,
    }


@router.get("/health/ready")
async def health_ready(settings: AppSettings = Depends(settings_dependency)) -> dict:
    checks = readiness_checks(settings)
    return {
        "status": overall_status(checks),
        "environment": settings.retriever_env,
        "checks": checks,
    }


@router.get("/health/deep")
async def health_deep(settings: AppSettings = Depends(settings_dependency)) -> dict:
    checks = readiness_checks(settings)
    return {
        "status": overall_status(checks),
        "environment": settings.retriever_env,
        "checks": checks,
        "config": settings.redacted_summary(),
        "checkedAt": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/version")
async def version(settings: AppSettings = Depends(settings_dependency)) -> dict:
    return {
        "app": "retriever-rebuild",
        "version": settings.app_version,
        "gitSha": settings.git_sha,
        "gitRef": settings.git_ref,
        "builtAt": settings.built_at,
        "deployedAt": settings.deployed_at,
        "environment": settings.retriever_env,
        "host": settings.host_name,
    }

