"""Small user query compatibility layer for legacy PrePress alias matching."""

from __future__ import annotations

from app.config import get_settings
from app.db.connection import create_connection


def list_users() -> list[dict]:
    settings = get_settings()
    conn = create_connection(settings)
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            SELECT username, full_name, display_name, email, cloudflare_email
            FROM users
            WHERE status IN ('active', 'pending', 'suspended')
            ORDER BY id
            """
        )
        rows = cursor.fetchall() or []
    finally:
        cursor.close()
        conn.close()

    users = []
    for row in rows:
        full_name = row.get("full_name") or row.get("display_name") or ""
        parts = str(full_name).split()
        users.append(
            {
                "username": row.get("username") or row.get("email") or row.get("cloudflare_email"),
                "full_name": full_name,
                "first_name": parts[0] if parts else "",
                "last_name": parts[-1] if len(parts) > 1 else "",
            }
        )
    return users

