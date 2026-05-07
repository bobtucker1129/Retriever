"""MySQL connection helpers."""

from __future__ import annotations

import mysql.connector
from mysql.connector.connection import MySQLConnection
from mysql.connector.pooling import MySQLConnectionPool

from app.config import AppSettings


def create_pool(settings: AppSettings) -> MySQLConnectionPool:
    return MySQLConnectionPool(
        pool_name="retriever_cloudflare",
        pool_size=5,
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        user=settings.mysql_user,
        password=settings.mysql_password,
        autocommit=True,
    )


def create_connection(settings: AppSettings) -> MySQLConnection:
    return mysql.connector.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        database=settings.mysql_database,
        user=settings.mysql_user,
        password=settings.mysql_password,
        autocommit=True,
    )


def ping_mysql(settings: AppSettings) -> bool:
    if not settings.mysql_host or not settings.mysql_user or not settings.mysql_password:
        return False
    try:
        conn = mysql.connector.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            database=settings.mysql_database,
            user=settings.mysql_user,
            password=settings.mysql_password,
            connection_timeout=3,
        )
        conn.close()
        return True
    except mysql.connector.Error:
        return False

