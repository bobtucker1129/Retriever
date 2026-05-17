from __future__ import annotations

from app.db.repositories import locations as locations_module
from app.db.repositories.locations import ProductionLocationRepository


class PostgresStyleCursor:
    def __init__(self):
        self.executed = ""

    def execute(self, operation: str, params: tuple = ()) -> None:
        self.executed = operation

    def fetchall(self):
        return [
            {"id": 2, "name": "PrePress"},
            {"id": 1, "name": "00/Scott - Working"},
        ]

    def close(self) -> None:
        pass


class PostgresStyleConnection:
    def __init__(self):
        self.cursor_factory = None
        self.cursor_obj = PostgresStyleCursor()

    def cursor(self, *args, **kwargs):
        if "dictionary" in kwargs:
            raise TypeError("psycopg2 cursor does not accept dictionary")
        self.cursor_factory = kwargs.get("cursor_factory")
        return self.cursor_obj

    def close(self) -> None:
        pass


def test_production_locations_support_postgres_dict_cursor(monkeypatch) -> None:
    conn = PostgresStyleConnection()
    monkeypatch.setattr(locations_module, "_real_dict_cursor_class", lambda: object)
    repo = ProductionLocationRepository(lambda: conn, schema_name="public")

    locations = repo.list_active()

    assert [location.name for location in locations] == ["PrePress", "00/Scott - Working"]
    assert conn.cursor_factory is not None
    assert "FROM public.productionlocations" in conn.cursor_obj.executed


class TupleCursor:
    def execute(self, operation: str, params: tuple = ()) -> None:
        pass

    def fetchall(self):
        return [(3, "Bindery")]

    def close(self) -> None:
        pass


class TupleConnection:
    def cursor(self, *args, **kwargs):
        raise TypeError("no keyword cursor support")

    def close(self) -> None:
        pass


class FallbackTupleConnection(TupleConnection):
    def cursor(self, *args, **kwargs):
        if args or kwargs:
            raise TypeError("no keyword cursor support")
        return TupleCursor()


def test_production_locations_support_tuple_cursor_fallback() -> None:
    repo = ProductionLocationRepository(lambda: FallbackTupleConnection())

    locations = repo.list_active()

    assert [(location.id, location.name) for location in locations] == [(3, "Bindery")]
