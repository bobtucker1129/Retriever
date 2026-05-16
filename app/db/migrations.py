"""Migration helpers."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Iterable

import mysql.connector

from app.config import get_settings
from app.db.connection import create_connection


def find_migrations_dir() -> Path:
    """Find repo/release migrations even when app is imported from site-packages."""

    candidates = [
        Path.cwd() / "migrations",
        Path(__file__).resolve().parents[2] / "migrations",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


MIGRATIONS_DIR = find_migrations_dir()
SEEDS_DIR = MIGRATIONS_DIR / "seeds"


def list_sql_migrations() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def list_seed_files() -> list[Path]:
    return sorted(SEEDS_DIR.glob("*.sql"))


def split_sql_statements(sql_text: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(current).strip()
            if statement:
                statements.append(statement[:-1].strip())
            current = []
    if current:
        statements.append("\n".join(current).strip())
    return statements


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_sql_file(connection, path: Path) -> int:
    statements = split_sql_statements(path.read_text())
    cursor = connection.cursor()
    executed = 0
    try:
        for statement in statements:
            try:
                cursor.execute(statement)
                executed += 1
            except mysql.connector.Error as exc:
                if exc.errno in {1060, 1061}:
                    continue
                raise
    finally:
        cursor.close()
    return executed


def run_sql_files(files: Iterable[Path]) -> list[tuple[str, int]]:
    settings = get_settings()
    connection = create_connection(settings)
    applied: list[tuple[str, int]] = []
    try:
        for path in files:
            applied.append((path.name, apply_sql_file(connection, path)))
    finally:
        connection.close()
    return applied


def run_migrations(include_seeds: bool = False) -> list[tuple[str, int]]:
    files = list_sql_migrations()
    if include_seeds:
        files.extend(list_seed_files())
    return run_sql_files(files)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Retriever MySQL migrations.")
    parser.add_argument("--seeds", action="store_true", help="Also run seed SQL files.")
    args = parser.parse_args()
    for name, count in run_migrations(include_seeds=args.seeds):
        print(f"applied {name}: {count} statements")


if __name__ == "__main__":
    main()
