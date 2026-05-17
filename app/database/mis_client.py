"""MIS PostgreSQL client compatibility layer for migrated legacy modules."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.db.mis_connection import create_mis_connection


class MISClient:
    def get_connection(self):
        return create_mis_connection(get_settings())


@lru_cache(maxsize=1)
def get_mis_client() -> MISClient:
    return MISClient()

