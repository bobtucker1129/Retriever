from __future__ import annotations

from pathlib import Path

from app.db.migrations import list_seed_files, list_sql_migrations, split_sql_statements


def test_initial_migration_contains_required_tables() -> None:
    sql = Path("migrations/0001_retriever_cloudflare.sql").read_text()

    for table in [
        "schema_migrations",
        "users",
        "roles",
        "capabilities",
        "user_capabilities",
        "user_module_access",
        "sessions",
        "app_settings",
        "delayed_reports",
        "report_artifacts",
        "audit_events",
    ]:
        assert f"retriever_cloudflare.{table}" in sql


def test_initial_migration_does_not_touch_old_schema() -> None:
    sql = Path("migrations/0001_retriever_cloudflare.sql").read_text()

    assert "retriever_core" not in sql


def test_migration_helpers_find_migration_and_seed_files() -> None:
    assert any(path.name == "0001_retriever_cloudflare.sql" for path in list_sql_migrations())
    assert any(path.name == "0001_seed_auth_shell.sql" for path in list_seed_files())


def test_split_sql_statements_ignores_comments_and_blank_lines() -> None:
    statements = split_sql_statements(
        """
        -- comment

        CREATE TABLE example (id INT);
        INSERT INTO example VALUES (1);
        """
    )

    assert statements == [
        "CREATE TABLE example (id INT)",
        "INSERT INTO example VALUES (1)",
    ]

