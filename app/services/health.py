"""Health check service."""

from __future__ import annotations

from typing import Literal

from app.config import AppSettings
from app.db.connection import ping_mysql

CheckState = Literal["ok", "disabled", "degraded", "failed"]


def readiness_checks(settings: AppSettings) -> dict[str, CheckState]:
    """Return readiness checks for enabled runtime dependencies."""

    checks: dict[str, CheckState] = {
        "config": "ok",
        "mysql": mysql_check(settings),
        "cloudflareAccess": "ok" if settings.cloudflare_access_enabled else "disabled",
        "sessions": "ok",
        "audit": "ok" if settings.audit_log_mode in {"mysql", "file", "both"} else "degraded",
        "fetch": "ok" if settings.fetch_enabled else "disabled",
        "modelProvider": "ok" if settings.fetch_enabled else "disabled",
        "uploads": "ok" if settings.fetch_uploads_enabled else "disabled",
        "delayedReports": "ok" if settings.fetch_delayed_reports_enabled else "disabled",
        "docsRoute": "ok" if settings.docs_route_enabled else "disabled",
        "printsmithRoute": "ok" if settings.printsmith_route_enabled else "disabled",
        "tokenAuthority": (
            "disabled"
            if settings.printsmith_token_authority_mode == "disabled"
            else "degraded"
        ),
        "booneopsBroker": "ok" if settings.booneops_broker_enabled else "disabled",
        "tailscale": (
            "ok"
            if settings.booneops_broker_enabled and settings.booneops_broker_requires_tailscale
            else "disabled"
        ),
        "artifactStorage": "ok" if settings.fetch_delayed_reports_enabled else "disabled",
    }
    return checks


def mysql_check(settings: AppSettings) -> CheckState:
    if not settings.mysql_host or not settings.mysql_user or not settings.mysql_password:
        return "disabled" if settings.retriever_env == "local" else "failed"
    return "ok" if ping_mysql(settings) else "failed"


def overall_status(checks: dict[str, CheckState]) -> CheckState:
    if any(value == "failed" for value in checks.values()):
        return "failed"
    if any(value == "degraded" for value in checks.values()):
        return "degraded"
    return "ok"
