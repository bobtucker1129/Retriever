from __future__ import annotations

import httpx
import pytest

from app.config import AppSettings
from app.prepress import printsmith_job_ticket


def test_prepress_job_ticket_settings_accept_old_api_base_alias(monkeypatch) -> None:
    monkeypatch.setenv("PREPRESS_PRINTSMITH_API_BASE_URL", "http://printsmith.test/api")

    settings = AppSettings(
        retriever_env="local",
        printsmith_token_authority_mode="using_old_authority",
        printsmith_token_proxy_url="http://old-retriever.test/api/printsmith-token",
        printsmith_token_proxy_key="proxy-key",
        prepress_job_ticket_save_enabled=True,
    )

    assert settings.printsmith_api_base_url == "http://printsmith.test/api"


def test_prepress_job_ticket_settings_accept_field_name_api_base() -> None:
    settings = AppSettings(
        retriever_env="local",
        printsmith_token_authority_mode="using_old_authority",
        printsmith_token_proxy_url="http://old-retriever.test/api/printsmith-token",
        printsmith_token_proxy_key="proxy-key",
        printsmith_api_base_url="http://printsmith.test/api",
        prepress_job_ticket_save_enabled=True,
    )

    assert settings.printsmith_api_base_url == "http://printsmith.test/api"


@pytest.mark.asyncio
async def test_get_valid_token_borrows_from_old_authority(monkeypatch) -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, str(request.url)))
        assert request.headers["X-Token-Proxy-Key"] == "proxy-key"
        return httpx.Response(200, json={"token": "borrowed-token", "vendor": "LordTate"})

    transport = httpx.MockTransport(handler)
    original_async_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    monkeypatch.setattr(printsmith_job_ticket.httpx, "AsyncClient", client_factory)

    settings = AppSettings(
        retriever_env="local",
        printsmith_token_authority_mode="using_old_authority",
        printsmith_token_proxy_url="http://old-retriever.test/api/printsmith-token",
        printsmith_token_proxy_key="proxy-key",
    )

    token = await printsmith_job_ticket.get_valid_token(settings)

    assert token == "borrowed-token"
    assert requests == [("GET", "http://old-retriever.test/api/printsmith-token")]
