"""Shared FastAPI dependencies."""

from __future__ import annotations

from app.config import AppSettings, get_settings


def settings_dependency() -> AppSettings:
    return get_settings()

