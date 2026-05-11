"""Fetch conversation repository."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol
from uuid import uuid4


class CursorLike(Protocol):
    def execute(self, operation: str, params: tuple = ()) -> None:
        ...

    def fetchall(self):
        ...

    def fetchone(self):
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
class FetchConversationRecord:
    conversation_id: str
    user_id: int
    title: str
    status: str
    route_state: str
    message_count: int = 0


@dataclass(frozen=True)
class FetchMessageRecord:
    message_id: str
    conversation_id: str
    user_id: int
    role: str
    content: str
    route_key: str
    model_label: Optional[str] = None
    context_percent: Optional[int] = None
    context_state: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class FetchRepository:
    def __init__(self, connection_factory: ConnectionFactory):
        self._connection_factory = connection_factory

    def create_conversation(
        self,
        user_id: int,
        title: str = "New Fetch conversation",
        route_state: str = "local",
    ) -> FetchConversationRecord:
        conversation_id = str(uuid4())
        clean_title = self._clean_title(title)
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO fetch_conversations
                  (conversation_id, user_id, title, route_state)
                VALUES (%s, %s, %s, %s)
                """,
                (conversation_id, user_id, clean_title, route_state),
            )
        finally:
            cursor.close()
            conn.close()
        return FetchConversationRecord(
            conversation_id=conversation_id,
            user_id=user_id,
            title=clean_title,
            status="active",
            route_state=route_state,
            message_count=0,
        )

    def get_conversation(
        self, user_id: int, conversation_id: str
    ) -> Optional[FetchConversationRecord]:
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT c.conversation_id, c.user_id, c.title, c.status, c.route_state,
                       COUNT(m.id) AS message_count
                FROM fetch_conversations c
                LEFT JOIN fetch_messages m ON m.conversation_id = c.conversation_id
                WHERE c.user_id = %s
                  AND c.conversation_id = %s
                  AND c.deleted_at IS NULL
                GROUP BY c.conversation_id, c.user_id, c.title, c.status, c.route_state
                LIMIT 1
                """,
                (user_id, conversation_id),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
        return self._conversation_from_row(row) if row else None

    def list_conversations(self, user_id: int) -> list[FetchConversationRecord]:
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT c.conversation_id, c.user_id, c.title, c.status, c.route_state,
                       COUNT(m.id) AS message_count
                FROM fetch_conversations c
                LEFT JOIN fetch_messages m ON m.conversation_id = c.conversation_id
                WHERE c.user_id = %s
                  AND c.deleted_at IS NULL
                GROUP BY c.conversation_id, c.user_id, c.title, c.status, c.route_state,
                         c.last_message_at, c.created_at
                ORDER BY COALESCE(c.last_message_at, c.created_at) DESC
                """,
                (user_id,),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
        return [self._conversation_from_row(row) for row in rows]

    def rename_conversation(self, user_id: int, conversation_id: str, title: str) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE fetch_conversations
                SET title = %s
                WHERE user_id = %s
                  AND conversation_id = %s
                  AND deleted_at IS NULL
                """,
                (self._clean_title(title), user_id, conversation_id),
            )
        finally:
            cursor.close()
            conn.close()

    def soft_delete_conversation(self, user_id: int, conversation_id: str) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE fetch_conversations
                SET deleted_at = NOW(),
                    status = 'deleted'
                WHERE user_id = %s
                  AND conversation_id = %s
                  AND deleted_at IS NULL
                """,
                (user_id, conversation_id),
            )
        finally:
            cursor.close()
            conn.close()

    def append_message(
        self,
        user_id: int,
        conversation_id: str,
        role: str,
        content: str,
        route_key: str = "local",
        model_label: Optional[str] = None,
        context_percent: Optional[int] = None,
        context_state: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> FetchMessageRecord:
        if role not in {"user", "assistant", "system"}:
            raise ValueError("Invalid Fetch message role")
        message_id = str(uuid4())
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO fetch_messages
                  (message_id, conversation_id, user_id, role, content, route_key,
                   model_label, context_percent, context_state, metadata_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    message_id,
                    conversation_id,
                    user_id,
                    role,
                    content,
                    route_key,
                    model_label,
                    context_percent,
                    context_state,
                    json.dumps(metadata, separators=(",", ":")) if metadata else None,
                ),
            )
            cursor.execute(
                """
                UPDATE fetch_conversations
                SET last_message_at = NOW(),
                    route_state = %s
                WHERE user_id = %s
                  AND conversation_id = %s
                  AND deleted_at IS NULL
                """,
                (route_key, user_id, conversation_id),
            )
        finally:
            cursor.close()
            conn.close()
        return FetchMessageRecord(
            message_id=message_id,
            conversation_id=conversation_id,
            user_id=user_id,
            role=role,
            content=content,
            route_key=route_key,
            model_label=model_label,
            context_percent=context_percent,
            context_state=context_state,
            metadata=metadata,
        )

    def list_messages(self, user_id: int, conversation_id: str) -> list[FetchMessageRecord]:
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT message_id, conversation_id, user_id, role, content, route_key,
                       model_label, context_percent, context_state, metadata_json
                FROM fetch_messages
                WHERE user_id = %s
                  AND conversation_id = %s
                ORDER BY created_at ASC, id ASC
                """,
                (user_id, conversation_id),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
        return [self._message_from_row(row) for row in rows]

    def _clean_title(self, title: str) -> str:
        clean = " ".join(title.split()).strip()
        return clean[:255] or "New Fetch conversation"

    def _conversation_from_row(self, row) -> FetchConversationRecord:
        return FetchConversationRecord(
            conversation_id=row["conversation_id"],
            user_id=int(row["user_id"]),
            title=row["title"],
            status=row["status"],
            route_state=row["route_state"],
            message_count=int(row.get("message_count") or 0),
        )

    def _message_from_row(self, row) -> FetchMessageRecord:
        return FetchMessageRecord(
            message_id=row["message_id"],
            conversation_id=row["conversation_id"],
            user_id=int(row["user_id"]),
            role=row["role"],
            content=row["content"],
            route_key=row["route_key"],
            model_label=row.get("model_label"),
            context_percent=row.get("context_percent"),
            context_state=row.get("context_state"),
            metadata=self._metadata_from_row(row.get("metadata_json")),
        )

    def _metadata_from_row(self, raw: object) -> Optional[dict[str, Any]]:
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        if not isinstance(raw, str) or not raw.strip():
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None
