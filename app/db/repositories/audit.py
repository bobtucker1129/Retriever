"""Audit repository."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol


REDACTED_METADATA_KEYS = {
    "authorization",
    "cookie",
    "x-token-proxy-key",
    "token",
    "password",
    "secret",
}


class CursorLike(Protocol):
    def execute(self, operation: str, params: tuple = ()) -> None:
        ...

    def close(self) -> None:
        ...


class ConnectionLike(Protocol):
    def cursor(self, dictionary: bool = False) -> CursorLike:
        ...

    def close(self) -> None:
        ...


ConnectionFactory = Callable[[], ConnectionLike]


@dataclass(frozen=True)
class AuditEvent:
    actor_type: str
    action_key: str
    result: str
    actor_id: Optional[str] = None
    user_id: Optional[int] = None
    module_key: Optional[str] = None
    route_key: Optional[str] = None
    capability_key: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    risk_level: str = "light"
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    error_category: Optional[str] = None
    metadata_redacted: Optional[str] = None


class AuditRepository:
    def __init__(self, connection_factory: ConnectionFactory):
        self._connection_factory = connection_factory

    def write_event(self, event: AuditEvent) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO audit_events
                  (actor_type, actor_id, user_id, module_key, action_key, route_key,
                   capability_key, target_type, target_id, risk_level, result,
                   request_id, correlation_id, error_category, metadata_redacted)
                VALUES
                  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    event.actor_type,
                    event.actor_id,
                    event.user_id,
                    event.module_key,
                    event.action_key,
                    event.route_key,
                    event.capability_key,
                    event.target_type,
                    event.target_id,
                    event.risk_level,
                    event.result,
                    event.request_id,
                    event.correlation_id,
                    event.error_category,
                    event.metadata_redacted,
                ),
            )
        finally:
            cursor.close()
            conn.close()

