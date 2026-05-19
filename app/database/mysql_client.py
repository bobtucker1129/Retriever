"""MySQL client compatibility layer for migrated legacy modules."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional

import mysql.connector

from app.config import get_settings


@lru_cache(maxsize=64)
def _get_table_columns(database: str, table: str) -> List[str]:
    conn = None
    cursor = None
    try:
        conn = get_mysql_client().get_connection(database)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COLUMN_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            """,
            (database, table),
        )
        return [row[0] for row in (cursor.fetchall() or [])]
    except Exception:
        return []
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


def _build_active_filter(database: str, table: str, alias: str = "") -> str:
    cols = {c.lower() for c in _get_table_columns(database, table)}
    prefix = f"{alias}." if alias else ""
    for name in ("active", "is_active", "enabled", "is_enabled"):
        if name in cols:
            return f"WHERE {prefix}{name} = 1"
    return ""


class MySQLClient:
    def get_connection(self, database: Optional[str] = None):
        settings = get_settings()
        target_database = database or settings.mysql_database
        host = settings.mysql_host
        port = settings.mysql_port
        user = settings.mysql_user
        password = settings.mysql_password
        if target_database == settings.inventory_mysql_database and settings.inventory_mysql_user:
            host = settings.inventory_mysql_host or settings.mysql_host
            port = settings.inventory_mysql_port or settings.mysql_port
            user = settings.inventory_mysql_user
            password = settings.inventory_mysql_password
        return mysql.connector.connect(
            host=host,
            port=port,
            database=target_database,
            user=user,
            password=password,
            charset="utf8mb4",
            autocommit=True,
        )

    def get_prepress_operators(self) -> List[Dict[str, Any]]:
        conn = None
        cursor = None
        try:
            conn = self.get_connection("switch_shared")
            cursor = conn.cursor(dictionary=True)
            active_filter = _build_active_filter("switch_shared", "prepress")
            query = """
            SELECT id, name, email, location_id
            FROM prepress
            {active_filter}
            ORDER BY name
            """
            try:
                cursor.execute(query.format(active_filter=active_filter))
            except mysql.connector.errors.ProgrammingError as exc:
                if "Unknown column" not in str(exc):
                    raise
                _get_table_columns.cache_clear()
                cursor.execute(query.format(active_filter=""))
            return cursor.fetchall() or []
        except Exception:
            return []
        finally:
            if cursor is not None:
                cursor.close()
            if conn is not None:
                conn.close()


@lru_cache(maxsize=1)
def get_mysql_client() -> MySQLClient:
    return MySQLClient()
