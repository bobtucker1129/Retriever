from __future__ import annotations

from pathlib import Path

from app.db.migrations import (
    apply_sql_file,
    find_migrations_dir,
    list_seed_files,
    list_sql_migrations,
    split_sql_statements,
)


def test_initial_migration_contains_required_tables() -> None:
    sql = Path("migrations/0001_retriever_core_auth.sql").read_text()

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
        assert f"retriever_core.{table}" in sql


def test_initial_migration_does_not_create_cloudflare_schema() -> None:
    sql = Path("migrations/0001_retriever_core_auth.sql").read_text()

    assert "retriever_cloudflare" not in sql


def test_fetch_migration_adds_conversation_storage_without_model_routes() -> None:
    sql = Path("migrations/0002_fetch_conversations.sql").read_text()

    assert "retriever_core.fetch_conversations" in sql
    assert "retriever_core.fetch_messages" in sql
    assert "model_provider" not in sql
    assert "anthropic_api_key" not in sql
    assert "retriever_cloudflare" not in sql


def test_migration_helpers_find_migration_and_seed_files() -> None:
    assert any(path.name == "0001_retriever_core_auth.sql" for path in list_sql_migrations())
    assert any(path.name == "0002_fetch_conversations.sql" for path in list_sql_migrations())
    assert any(path.name == "0001_seed_auth_shell.sql" for path in list_seed_files())


def test_migration_dir_prefers_current_release_working_directory(monkeypatch, tmp_path) -> None:
    release_migrations = tmp_path / "migrations"
    release_migrations.mkdir()
    monkeypatch.chdir(tmp_path)

    assert find_migrations_dir() == release_migrations


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


def test_apply_sql_file_skips_duplicate_column_and_index_errors(tmp_path) -> None:
    class DuplicateError(Exception):
        errno = 1060

    class Cursor:
        def __init__(self):
            self.executed = []

        def execute(self, statement):
            self.executed.append(statement)
            if "duplicate_column" in statement:
                import mysql.connector

                raise mysql.connector.Error(errno=1060, msg="Duplicate column")
            if "duplicate_index" in statement:
                import mysql.connector

                raise mysql.connector.Error(errno=1061, msg="Duplicate key name")

        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.cursor_obj = Cursor()

        def cursor(self):
            return self.cursor_obj

    sql = tmp_path / "dupes.sql"
    sql.write_text(
        """
        SELECT 1;
        ALTER TABLE users ADD COLUMN duplicate_column VARCHAR(10);
        CREATE INDEX duplicate_index ON users (id);
        SELECT 2;
        """
    )
    conn = Connection()

    assert apply_sql_file(conn, sql) == 2
