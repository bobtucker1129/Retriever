"""Session repository."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Optional, Protocol


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


def hash_optional(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    user_id: int
    cloudflare_email: str


class SessionRepository:
    def __init__(self, connection_factory: ConnectionFactory):
        self._connection_factory = connection_factory

    def create_session(
        self,
        user_id: int,
        cloudflare_email: str,
        ttl_seconds: int,
        user_agent: Optional[str] = None,
        source_ip: Optional[str] = None,
    ) -> str:
        session_id = secrets.token_hex(32)
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO sessions
                  (session_id, user_id, cloudflare_email, expires_at,
                   user_agent_hash, source_ip_hash)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    session_id,
                    user_id,
                    cloudflare_email,
                    expires_at,
                    hash_optional(user_agent),
                    hash_optional(source_ip),
                ),
            )
            cursor.execute(
                """
                UPDATE users
                SET last_seen_at = NOW(),
                    last_login = COALESCE(last_login, NOW())
                WHERE id = %s
                """,
                (user_id,),
            )
        finally:
            cursor.close()
            conn.close()
        return session_id

    def get_active_session(self, session_id: str, user_id: int) -> Optional[SessionRecord]:
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT session_id, user_id, cloudflare_email
                FROM sessions
                WHERE session_id = %s
                  AND user_id = %s
                  AND revoked_at IS NULL
                  AND expires_at > NOW()
                LIMIT 1
                """,
                (session_id, user_id),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return SessionRecord(
                session_id=row["session_id"],
                user_id=int(row["user_id"]),
                cloudflare_email=row["cloudflare_email"],
            )
        finally:
            cursor.close()
            conn.close()

    def touch_session(self, session_id: str) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE sessions
                SET last_seen_at = NOW()
                WHERE session_id = %s AND revoked_at IS NULL
                """,
                (session_id,),
            )
            cursor.execute(
                """
                UPDATE users u
                JOIN sessions s ON s.user_id = u.id
                SET u.last_seen_at = NOW()
                WHERE s.session_id = %s AND s.revoked_at IS NULL
                """,
                (session_id,),
            )
        finally:
            cursor.close()
            conn.close()

    def revoke_session(self, session_id: str) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE sessions
                SET revoked_at = NOW()
                WHERE session_id = %s
                """,
                (session_id,),
            )
        finally:
            cursor.close()
            conn.close()

    def revoke_user_sessions(self, user_id: int) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE sessions
                SET revoked_at = NOW()
                WHERE user_id = %s AND revoked_at IS NULL
                """,
                (user_id,),
            )
        finally:
            cursor.close()
            conn.close()
