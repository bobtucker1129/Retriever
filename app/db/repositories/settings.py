"""Settings repository."""

from __future__ import annotations

from typing import Callable, Optional, Protocol


DEFAULT_APP_SETTINGS = {
    "fetch.enabled": "false",
    "fetch.delayed_reports_enabled": "true",
    "auth.pending_users_enabled": "true",
}


class CursorLike(Protocol):
    def execute(self, operation: str, params: tuple = ()) -> None:
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


class SettingsRepository:
    def __init__(self, connection_factory: ConnectionFactory):
        self._connection_factory = connection_factory

    def get(self, setting_key: str) -> Optional[str]:
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT setting_value
                FROM app_settings
                WHERE setting_key = %s
                LIMIT 1
                """,
                (setting_key,),
            )
            row = cursor.fetchone()
            return row["setting_value"] if row else None
        finally:
            cursor.close()
            conn.close()

    def is_enabled(self, setting_key: str, default: bool = False) -> bool:
        value = self.get(setting_key)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}
