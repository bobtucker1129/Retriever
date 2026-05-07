"""Application settings and startup validation."""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RetrieverEnvironment(str, Enum):
    LOCAL = "local"
    STAGING = "staging"
    PRODUCTION = "production"


class TokenAuthorityMode(str, Enum):
    DISABLED = "disabled"
    USING_OLD_AUTHORITY = "using_old_authority"
    USING_NEW_AUTHORITY = "using_new_authority"


class AppSettings(BaseSettings):
    """Typed settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    retriever_env: RetrieverEnvironment = RetrieverEnvironment.LOCAL
    retriever_public_base_url: str = "http://127.0.0.1:8810"
    retriever_bind_host: str = "127.0.0.1"
    retriever_port: int = 8810
    retriever_cookie_secret: str = "local-dev-cookie-secret-change-me-32chars"
    retriever_session_ttl_seconds: int = 86400
    retriever_seed_admin_email: str = "state@boonegraphics.net"

    local_dev_identity_enabled: bool = True
    local_dev_email: str = "state@boonegraphics.net"
    local_dev_display_name: str = "Master Tate"

    cloudflare_access_enabled: bool = False
    cloudflare_access_team_domain: Optional[str] = None
    cloudflare_access_audience: Optional[str] = None
    cloudflare_access_jwks_url: Optional[str] = None
    cloudflare_access_validate_jwt: bool = False

    mysql_host: Optional[str] = None
    mysql_port: int = 3306
    mysql_database: str = "retriever_cloudflare"
    mysql_user: Optional[str] = None
    mysql_password: Optional[str] = None
    mysql_ssl_mode: str = "preferred"

    fetch_enabled: bool = False
    fetch_general_questions_enabled: bool = False
    fetch_uploads_enabled: bool = False
    fetch_delayed_reports_enabled: bool = True

    model_provider: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    model_default: Optional[str] = None

    docs_route_enabled: bool = False
    docs_service_url: Optional[str] = None
    printsmith_route_enabled: bool = False
    printsmith_token_authority_mode: TokenAuthorityMode = TokenAuthorityMode.DISABLED
    printsmith_token_proxy_url: Optional[str] = None
    printsmith_token_proxy_key: Optional[str] = None
    printsmith_api_base_url: Optional[str] = None
    printsmith_api_vendor: str = "LordTate"
    printsmith_api_username: Optional[str] = None
    printsmith_api_password: Optional[str] = None

    booneops_broker_enabled: bool = False
    booneops_broker_url: Optional[str] = None
    booneops_broker_bearer_token: Optional[str] = None
    booneops_broker_hmac_secret: Optional[str] = None
    booneops_broker_requires_tailscale: bool = True

    retriever_shared_dir: Path = Path("/opt/retriever-rebuild/shared")
    retriever_upload_dir: Path = Path("/opt/retriever-rebuild/shared/uploads")
    retriever_report_dir: Path = Path("/opt/retriever-rebuild/shared/reports")

    log_level: str = "info"
    audit_log_mode: str = "mysql"
    audit_log_file: Path = Path("/var/log/retriever-rebuild/audit.jsonl")

    app_version: str = "0.1.0"
    git_sha: str = "dev"
    git_ref: str = "local"
    built_at: Optional[str] = None
    deployed_at: Optional[str] = None
    host_name: str = Field(default="local")

    @field_validator("retriever_seed_admin_email", "local_dev_email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_contract(self) -> AppSettings:
        errors: list[str] = []
        is_runtime = self.retriever_env in {
            RetrieverEnvironment.STAGING,
            RetrieverEnvironment.PRODUCTION,
        }

        if self.mysql_database != "retriever_cloudflare":
            errors.append("MYSQL_DATABASE must be retriever_cloudflare")

        if is_runtime:
            if len(self.retriever_cookie_secret or "") < 32:
                errors.append("RETRIEVER_COOKIE_SECRET must be at least 32 characters")
            if "change-me" in self.retriever_cookie_secret.lower():
                errors.append("RETRIEVER_COOKIE_SECRET cannot be a default placeholder")
            if not self.cloudflare_access_enabled:
                errors.append("CLOUDFLARE_ACCESS_ENABLED must be true")
            if not self.cloudflare_access_validate_jwt:
                errors.append("CLOUDFLARE_ACCESS_VALIDATE_JWT must be true")
            if self.local_dev_identity_enabled:
                errors.append("LOCAL_DEV_IDENTITY_ENABLED must be false outside local")

        if self.cloudflare_access_enabled and self.cloudflare_access_validate_jwt:
            if not self.cloudflare_access_audience:
                errors.append("CLOUDFLARE_ACCESS_AUDIENCE is required")
            if not self.cloudflare_access_jwks_url:
                errors.append("CLOUDFLARE_ACCESS_JWKS_URL is required")

        if is_runtime:
            for field_name in ("mysql_host", "mysql_user", "mysql_password"):
                if not getattr(self, field_name):
                    errors.append(f"{field_name.upper()} is required")

        if self.fetch_enabled:
            if not self.model_provider:
                errors.append("MODEL_PROVIDER is required when Fetch is enabled")
            if self.model_provider == "anthropic" and not self.anthropic_api_key:
                errors.append("ANTHROPIC_API_KEY is required when Fetch uses Anthropic")
            if not self.model_default:
                errors.append("MODEL_DEFAULT is required when Fetch is enabled")

        if self.fetch_uploads_enabled and not self.retriever_upload_dir:
            errors.append("RETRIEVER_UPLOAD_DIR is required when uploads are enabled")

        if self.fetch_delayed_reports_enabled and not self.retriever_report_dir:
            errors.append("RETRIEVER_REPORT_DIR is required when delayed reports are enabled")

        if self.booneops_broker_enabled:
            for field_name in (
                "booneops_broker_url",
                "booneops_broker_bearer_token",
                "booneops_broker_hmac_secret",
            ):
                if not getattr(self, field_name):
                    errors.append(f"{field_name.upper()} is required when BooneOps broker is enabled")

        if self.docs_route_enabled and not self.docs_service_url:
            errors.append("DOCS_SERVICE_URL is required when docs route is enabled")

        mode = self.printsmith_token_authority_mode
        has_direct_printsmith = any(
            [
                self.printsmith_api_base_url,
                self.printsmith_api_username,
                self.printsmith_api_password,
            ]
        )
        if mode == TokenAuthorityMode.USING_OLD_AUTHORITY:
            if not self.printsmith_token_proxy_url or not self.printsmith_token_proxy_key:
                errors.append("PrintSmith old-authority mode requires proxy URL and proxy key")
            if has_direct_printsmith:
                errors.append("Direct PrintSmith credentials conflict with old-authority mode")
        if mode == TokenAuthorityMode.USING_NEW_AUTHORITY:
            for field_name in (
                "printsmith_api_base_url",
                "printsmith_api_username",
                "printsmith_api_password",
            ):
                if not getattr(self, field_name):
                    errors.append(f"{field_name.upper()} is required for new-authority mode")
        if self.printsmith_route_enabled and mode == TokenAuthorityMode.DISABLED:
            errors.append("PrintSmith route cannot be enabled when token authority is disabled")

        if errors:
            raise ValueError("; ".join(errors))
        return self

    def redacted_summary(self) -> dict[str, Any]:
        """Return non-secret runtime settings for diagnostics."""

        return {
            "retrieverEnv": self.retriever_env,
            "publicBaseUrl": self.retriever_public_base_url,
            "bindHost": self.retriever_bind_host,
            "port": self.retriever_port,
            "mysqlDatabase": self.mysql_database,
            "cloudflareAccessEnabled": self.cloudflare_access_enabled,
            "cloudflareJwtValidation": self.cloudflare_access_validate_jwt,
            "fetchEnabled": self.fetch_enabled,
            "docsRouteEnabled": self.docs_route_enabled,
            "printsmithRouteEnabled": self.printsmith_route_enabled,
            "tokenAuthorityMode": self.printsmith_token_authority_mode,
            "booneopsBrokerEnabled": self.booneops_broker_enabled,
        }


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()


def format_config_error(exc: ValidationError | ValueError) -> str:
    """Format config errors without leaking environment values."""

    if isinstance(exc, ValidationError):
        return "; ".join(error["msg"] for error in exc.errors())
    return str(exc)

