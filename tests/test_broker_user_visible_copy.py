"""Sanity checks for BooneOps transport copy used in Fetch."""

from app.fetch.broker_user_visible_copy import (
    copy_http_401,
    copy_http_5xx_after_retry,
    copy_http_network,
    copy_http_non_json,
    copy_http_timeout,
)


def test_server_error_headline_matches_discord_style_phrasing() -> None:
    c = copy_http_5xx_after_retry(request_id="r1")
    assert "BooneOps encountered a server error" in c.headline


def test_timeout_copy_mentions_gateway_context() -> None:
    c = copy_http_timeout(request_id="r2")
    assert "did not respond" in c.headline.lower()
    assert "openclaw" in c.detail_line.lower()


def test_network_copy_mentions_network() -> None:
    c = copy_http_network(request_id="r3")
    assert "network" in c.detail_line.lower()


def test_401_is_configuration_not_user_login() -> None:
    c = copy_http_401(request_id="r4")
    assert "credentials" in c.headline.lower()
    assert "signing in" in c.detail_line.lower() or "sign" in c.detail_line.lower()


def test_non_json_headline_stable() -> None:
    c = copy_http_non_json(request_id="r5")
    assert "unreadable" in c.headline.lower()
