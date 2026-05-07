"""Cloudflare Access identity parsing and JWT validation."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from fastapi import HTTPException, Request
import httpx
import jwt
from jwt import PyJWKClient
from jwt.exceptions import InvalidTokenError

from app.config import AppSettings, RetrieverEnvironment


@dataclass(frozen=True)
class CloudflareIdentity:
    email: str
    display_name: Optional[str] = None


def get_identity_from_request(
    request: Request,
    settings: AppSettings,
    jwks_client: Optional[PyJWKClient] = None,
) -> CloudflareIdentity:
    if settings.local_dev_identity_enabled:
        if settings.retriever_env != RetrieverEnvironment.LOCAL:
            raise HTTPException(status_code=500, detail="Local identity is not allowed")
        return CloudflareIdentity(
            email=settings.local_dev_email.lower(),
            display_name=settings.local_dev_display_name,
        )

    token = request.headers.get("cf-access-jwt-assertion")
    if not token:
        raise HTTPException(status_code=401, detail="Cloudflare identity is required")

    if not settings.cloudflare_access_validate_jwt:
        raise HTTPException(status_code=500, detail="Cloudflare JWT validation is disabled")

    identity = validate_access_jwt(token, settings, jwks_client=jwks_client)
    return identity


def validate_access_jwt(
    token: str,
    settings: AppSettings,
    jwks_client: Optional[PyJWKClient] = None,
) -> CloudflareIdentity:
    if not settings.cloudflare_access_audience:
        raise HTTPException(status_code=500, detail="Cloudflare audience is not configured")
    if not settings.cloudflare_access_jwks_url:
        raise HTTPException(status_code=500, detail="Cloudflare JWKS URL is not configured")

    try:
        client = jwks_client or get_jwks_client(settings.cloudflare_access_jwks_url)
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.cloudflare_access_audience,
            options={"require": ["aud", "exp"]},
        )
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid Cloudflare identity") from exc

    email = _claim_as_email(claims)
    if not email:
        raise HTTPException(status_code=401, detail="Cloudflare identity is missing email")

    display_name = (
        claims.get("name")
        or claims.get("common_name")
        or claims.get("given_name")
        or email
    )
    return CloudflareIdentity(email=email, display_name=display_name)


@lru_cache(maxsize=8)
def get_jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


def _claim_as_email(claims: dict) -> Optional[str]:
    value = claims.get("email") or claims.get("common_name")
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    if "@" not in value:
        return None
    return value


def fetch_access_jwks(jwks_url: str) -> dict:
    """Small helper for explicit diagnostics/tests; PyJWKClient handles normal fetches."""

    response = httpx.get(jwks_url, timeout=5.0)
    response.raise_for_status()
    data = response.json()
    if "keys" not in data:
        raise ValueError("JWKS response missing keys")
    return data

