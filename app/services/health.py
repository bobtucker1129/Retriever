"""Health check service."""

from __future__ import annotations

import re
from typing import Literal

from app.config import AppSettings
from app.db.connection import ping_mysql
from app.db.mis_connection import create_mis_connection, is_mis_configured
from app.db.repositories.locations import ProductionLocationRepository

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
        "productionLocations": production_locations_check(settings),
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


def production_locations_check(settings: AppSettings) -> CheckState:
    if not is_mis_configured(settings):
        return "disabled"
    try:
        locations = ProductionLocationRepository(
            lambda: create_mis_connection(settings),
            schema_name="public",
        ).list_active()
    except Exception:
        return "degraded"
    return "ok" if locations else "degraded"


def production_locations_diagnostics(settings: AppSettings) -> dict[str, object]:
    diagnostic: dict[str, object] = {
        "configured": is_mis_configured(settings),
        "source": "mis-postgres" if is_mis_configured(settings) else "disabled",
        "table": "public.productionlocations",
        "status": "disabled",
        "count": None,
        "sampleNames": [],
        "errorType": None,
        "error": None,
    }
    if not is_mis_configured(settings):
        return diagnostic

    try:
        locations = ProductionLocationRepository(
            lambda: create_mis_connection(settings),
            schema_name="public",
        ).list_active()
        diagnostic["count"] = len(locations)
        diagnostic["sampleNames"] = [location.name for location in locations[:8]]
        diagnostic["status"] = "ok" if locations else "empty"
    except Exception as exc:
        diagnostic["status"] = "error"
        diagnostic["errorType"] = type(exc).__name__
        diagnostic["error"] = _safe_location_error(exc)
    return diagnostic


def _safe_location_error(exc: Exception) -> str:
    message = str(exc)
    message = re.sub(r'user "[^"]+"', 'user "<redacted>"', message, flags=re.IGNORECASE)
    message = re.sub(
        r'server at "[^"]+", port \d+',
        'server at "<redacted>"',
        message,
        flags=re.IGNORECASE,
    )
    return message[:240]


def overall_status(checks: dict[str, CheckState]) -> CheckState:
    if any(value == "failed" for value in checks.values()):
        return "failed"
    if any(value == "degraded" for value in checks.values()):
        return "degraded"
    return "ok"
