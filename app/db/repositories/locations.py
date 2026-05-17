"""Production location lookup for admin onboarding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol


@dataclass(frozen=True)
class ProductionLocation:
    id: int
    name: str


class CursorLike(Protocol):
    def execute(self, operation: str, params: tuple = ()) -> None:
        ...

    def fetchall(self):
        ...

    def close(self) -> None:
        ...


class ConnectionLike(Protocol):
    def cursor(self, dictionary: bool = False) -> CursorLike:
        ...

    def close(self) -> None:
        ...


ConnectionFactory = Callable[[], ConnectionLike]


class ProductionLocationRepository:
    def __init__(self, connection_factory: ConnectionFactory, schema_name: Optional[str] = None):
        self._connection_factory = connection_factory
        self._table_name = f"{schema_name}.productionlocations" if schema_name else "productionlocations"

    def list_active(self) -> list[ProductionLocation]:
        conn = self._connection_factory()
        cursor = _dict_cursor(conn)
        try:
            cursor.execute(
                f"""
                SELECT id, name
                FROM {self._table_name}
                WHERE COALESCE(isdeleted, false) = false
                  AND COALESCE(ishidden, false) = false
                ORDER BY name
                """
            )
            return [
                ProductionLocation(
                    id=int(_row_value(row, "id", 0)),
                    name=str(_row_value(row, "name", 1)),
                )
                for row in cursor.fetchall()
            ]
        finally:
            cursor.close()
            conn.close()


def _dict_cursor(conn: ConnectionLike) -> CursorLike:
    """Open a dictionary-like cursor for either mysql-connector or psycopg2."""
    try:
        return conn.cursor(dictionary=True)
    except TypeError:
        real_dict_cursor = _real_dict_cursor_class()
        if real_dict_cursor is not None:
            try:
                return conn.cursor(cursor_factory=real_dict_cursor)
            except TypeError:
                pass
        return conn.cursor()


def _real_dict_cursor_class():
    try:
        from psycopg2.extras import RealDictCursor

        return RealDictCursor
    except ImportError:
        return None


def _row_value(row, key: str, index: int):
    if isinstance(row, dict):
        return row[key]
    return row[index]
