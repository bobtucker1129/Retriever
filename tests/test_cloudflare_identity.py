from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jwt import PyJWK
from starlette.requests import Request

from app.auth.cloudflare import get_identity_from_request, validate_access_jwt
from app.config import AppSettings


def make_request() -> Request:
    return Request({"type": "http", "headers": []})


class StaticJwksClient:
    def __init__(self, public_key):
        self.public_key = public_key

    def get_signing_key_from_jwt(self, token: str):
        return PyJWK.from_dict(
            {
                "kty": "RSA",
                "kid": "test-key",
                "use": "sig",
                "alg": "RS256",
                **jwt.algorithms.RSAAlgorithm.to_jwk(self.public_key, as_dict=True),
            }
        )


def make_key_pair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def make_settings() -> AppSettings:
    return AppSettings(
        retriever_env="staging",
        retriever_cookie_secret="x" * 40,
        local_dev_identity_enabled=False,
        cloudflare_access_enabled=True,
        cloudflare_access_validate_jwt=True,
        cloudflare_access_audience="retriever-audience",
        cloudflare_access_jwks_url="https://example.com/cdn-cgi/access/certs",
        mysql_host="mysql.internal",
        mysql_user="retriever_app",
        mysql_password="redacted",
    )


def make_token(private_key, audience="retriever-audience", email="STATE@BOONEGRAPHICS.NET"):
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "aud": audience,
            "email": email,
            "name": "Master Tate",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )


def test_local_identity_fixture_is_local_only() -> None:
    settings = AppSettings(
        retriever_env="local",
        local_dev_identity_enabled=True,
        local_dev_email="STATE@BOONEGRAPHICS.NET",
        local_dev_display_name="Master Tate",
    )

    identity = get_identity_from_request(make_request(), settings)

    assert identity.email == "state@boonegraphics.net"
    assert identity.display_name == "Master Tate"


def test_local_identity_fixture_rejected_outside_local() -> None:
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

    with pytest.raises(HTTPException):
        get_identity_from_request(make_request(), settings)


def test_valid_cloudflare_jwt_returns_identity() -> None:
    private_key, public_key = make_key_pair()
    token = make_token(private_key)

    identity = validate_access_jwt(token, make_settings(), StaticJwksClient(public_key))

    assert identity.email == "state@boonegraphics.net"
    assert identity.display_name == "Master Tate"


def test_wrong_audience_is_rejected() -> None:
    private_key, public_key = make_key_pair()
    token = make_token(private_key, audience="wrong")

    with pytest.raises(HTTPException) as exc_info:
        validate_access_jwt(token, make_settings(), StaticJwksClient(public_key))

    assert exc_info.value.status_code == 401


def test_missing_email_is_rejected() -> None:
    private_key, public_key = make_key_pair()
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "aud": "retriever-audience",
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    with pytest.raises(HTTPException) as exc_info:
        validate_access_jwt(token, make_settings(), StaticJwksClient(public_key))

    assert exc_info.value.status_code == 401


def test_spoofed_header_without_jwt_is_rejected() -> None:
    settings = make_settings()
    request = Request(
        {
            "type": "http",
            "headers": [(b"cf-access-authenticated-user-email", b"state@boonegraphics.net")],
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        get_identity_from_request(request, settings)

    assert exc_info.value.status_code == 401

