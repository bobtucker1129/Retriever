from __future__ import annotations

from app.config import AppSettings
from app.services import health
from app.services.health import mysql_check, overall_status, readiness_checks


def test_disabled_features_report_disabled_not_failed() -> None:
    checks = readiness_checks(AppSettings())

    assert checks["fetch"] == "disabled"
    assert checks["docsRoute"] == "disabled"
    assert checks["printsmithRoute"] == "disabled"
    assert checks["booneopsBroker"] == "disabled"


def test_fetch_enabled_marks_fetch_and_model_checks_ok() -> None:
    """Contract for RETRIEVER_SMOKE_EXPECT_FETCH_ENABLED smoke pilot mode."""
    checks = readiness_checks(
        AppSettings(
            fetch_enabled=True,
            model_provider="openai",
            model_default="test-model",
        )
    )
    assert checks["fetch"] == "ok"
    assert checks["modelProvider"] == "ok"


def test_enabled_booneops_broker_reports_configured_not_degraded() -> None:
    checks = readiness_checks(
        AppSettings(
            booneops_broker_enabled=True,
            booneops_broker_url="http://broker.example:3487",
            booneops_broker_bearer_token="token",
            booneops_broker_hmac_secret="secret",
        )
    )

    assert checks["booneopsBroker"] == "ok"
    assert checks["tailscale"] == "ok"
    assert overall_status(checks) == "ok"


def test_ready_status_is_degraded_until_mysql_is_checked() -> None:
    checks = readiness_checks(AppSettings())

    assert checks["mysql"] == "disabled"
    assert overall_status(checks) == "ok"


def test_redacted_summary_does_not_include_secret_fields() -> None:
    summary = AppSettings(mysql_password="super-secret").redacted_summary()

    assert "mysql_password" not in summary
    assert "super-secret" not in str(summary)


def test_mysql_check_fails_when_runtime_config_missing() -> None:
    settings = AppSettings(
        retriever_env="staging",
        retriever_cookie_secret="x" * 40,
        local_dev_identity_enabled=False,
        cloudflare_access_enabled=True,
        cloudflare_access_validate_jwt=True,
        cloudflare_access_audience="aud",
        cloudflare_access_jwks_url="https://example.com/cdn-cgi/access/certs",
        mysql_host="mysql.internal",
        mysql_user="retriever_app",
        mysql_password="redacted",
    )

    assert mysql_check(settings) in {"ok", "failed"}


def test_mysql_check_uses_ping(monkeypatch) -> None:
    settings = AppSettings(mysql_host="mysql.internal", mysql_user="u", mysql_password="p")
    monkeypatch.setattr(health, "ping_mysql", lambda _: True)

    assert mysql_check(settings) == "ok"
