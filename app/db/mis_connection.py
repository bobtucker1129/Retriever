"""Optional PostgreSQL connection for PrintSmith/MIS read lookups."""

from __future__ import annotations

from app.config import AppSettings


def is_mis_configured(settings: AppSettings) -> bool:
    return bool(
        settings.mis_db_host
        and settings.mis_db_database
        and settings.mis_db_user
        and settings.mis_db_password
    )


def create_mis_connection(settings: AppSettings):
    import psycopg2

    return psycopg2.connect(
        host=settings.mis_db_host,
        port=settings.mis_db_port,
        database=settings.mis_db_database,
        user=settings.mis_db_user,
        password=settings.mis_db_password,
    )
