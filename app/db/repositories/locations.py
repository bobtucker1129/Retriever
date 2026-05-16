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
        cursor = conn.cursor(dictionary=True)
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
                ProductionLocation(id=int(row["id"]), name=str(row["name"]))
                for row in cursor.fetchall()
            ]
        finally:
            cursor.close()
            conn.close()
