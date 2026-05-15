"""User-visible BooneOps / Fetch copy for broker transport failures.

Phrases are aligned with what employees already hear on Discord BooneOps when the
broker reports a hard failure, while keeping Fetch-specific context where the failure
is between Retriever and the broker (HTTP layer), not inside the broker JSON body.

See ``projects/booneops-bots/docs/DISCORD_FETCH_PARITY.md`` — *User-facing error parity*.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FetchBrokerTransportCopy:
    headline: str
    detail_line: str
    status_card_state: str
    status_card_detail: str


def copy_http_timeout(*, request_id: str) -> FetchBrokerTransportCopy:
    """Retriever client timed out waiting for the broker HTTP response."""
    _ = request_id
    return FetchBrokerTransportCopy(
        headline="BooneOps did not respond in time.",
        detail_line=(
            "The BooneOps broker did not finish this turn before Fetch stopped waiting. "
            "That often means the OpenClaw gateway was still working on a long answer, or "
            "there was a brief slowdown — it is not usually a mistake in what you typed."
        ),
        status_card_state="Timeout",
        status_card_detail="Fetch stopped waiting for the broker HTTP response (client timeout).",
    )


def copy_http_network(*, request_id: str) -> FetchBrokerTransportCopy:
    _ = request_id
    return FetchBrokerTransportCopy(
        headline="BooneOps encountered a connection problem.",
        detail_line=(
            "Fetch could not complete the call to the BooneOps broker. "
            "That usually means a brief network outage or a reachability issue, not your message text."
        ),
        status_card_state="Network issue",
        status_card_detail="Fetch could not complete the HTTP call to the broker.",
    )


def copy_http_401(*, request_id: str) -> FetchBrokerTransportCopy:
    _ = request_id
    return FetchBrokerTransportCopy(
        headline="BooneOps rejected Fetch's credentials.",
        detail_line=(
            "This is almost always a service configuration issue on Retriever's side "
            "(broker token or signature secret), not something you can fix by signing in again."
        ),
        status_card_state="Configuration issue",
        status_card_detail="Fetch was rejected when calling the broker (HTTP 401).",
    )


def copy_http_non_json(*, request_id: str) -> FetchBrokerTransportCopy:
    _ = request_id
    return FetchBrokerTransportCopy(
        headline="BooneOps returned an unreadable response.",
        detail_line=(
            "The payload was not valid JSON, so Fetch could not interpret BooneOps's reply. "
            "That can happen when an error page or proxy body is returned instead of the normal API shape."
        ),
        status_card_state="Unexpected response format",
        status_card_detail="Broker response was not JSON.",
    )


def copy_http_5xx_after_retry(*, request_id: str) -> FetchBrokerTransportCopy:
    _ = request_id
    return FetchBrokerTransportCopy(
        headline="BooneOps encountered a server error.",
        detail_line=(
            "The broker returned a server error after Fetch retried the request once. "
            "That usually means BooneOps or an upstream dependency was overloaded or failing briefly."
        ),
        status_card_state="BooneOps server error",
        status_card_detail="The broker returned HTTP 5xx after one automatic retry.",
    )


def copy_booneops_denied_no_body(*, request_id: str) -> FetchBrokerTransportCopy:
    """HTTP 4xx with empty or unusable JSON body — match Discord-style short denial."""
    _ = request_id
    return FetchBrokerTransportCopy(
        headline="BooneOps denied this request.",
        detail_line="Your message was saved; contact an operator if you need access.",
        status_card_state="Request denied",
        status_card_detail="Broker returned HTTP 4xx without a usable JSON message.",
    )
