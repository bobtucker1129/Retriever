from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import AppSettings


def test_fetch_local_artifact_retention_defaults_to_thirty_days() -> None:
    assert AppSettings().fetch_local_artifact_retention_days == 30


def test_local_config_can_start_without_cloudflare_or_mysql_secret() -> None:
    settings = AppSettings()

    assert settings.retriever_env == "local"
    assert settings.mysql_database == "retriever_core"
    assert settings.fetch_enabled is False


def test_staging_requires_cloudflare_validation() -> None:
    with pytest.raises(ValidationError) as exc_info:
        AppSettings(
            retriever_env="staging",
            retriever_cookie_secret="x" * 40,
            local_dev_identity_enabled=False,
            cloudflare_access_enabled=False,
            cloudflare_access_validate_jwt=False,
            mysql_host="mysql.internal",
            mysql_user="retriever_app",
            mysql_password="redacted",
        )

    assert "CLOUDFLARE_ACCESS_ENABLED must be true" in str(exc_info.value)


def test_staging_rejects_wrong_database() -> None:
    with pytest.raises(ValidationError) as exc_info:
        AppSettings(
            retriever_env="staging",
            retriever_cookie_secret="x" * 40,
            local_dev_identity_enabled=False,
            cloudflare_access_enabled=True,
            cloudflare_access_validate_jwt=True,
            cloudflare_access_audience="aud",
            cloudflare_access_jwks_url="https://example.com/cdn-cgi/access/certs",
            mysql_host="mysql.internal",
            mysql_database="retriever_cloudflare",
            mysql_user="retriever_app",
            mysql_password="redacted",
        )

    assert "MYSQL_DATABASE must be retriever_core" in str(exc_info.value)


def test_fetch_enabled_requires_model_config() -> None:
    with pytest.raises(ValidationError) as exc_info:
        AppSettings(fetch_enabled=True)

    assert "MODEL_PROVIDER is required when Fetch is enabled" in str(exc_info.value)
