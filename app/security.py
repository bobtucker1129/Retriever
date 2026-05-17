"""Compatibility security helpers used by migrated legacy modules."""

from __future__ import annotations

import html
import logging
import re
import time
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class InputValidator:
    @staticmethod
    def validate_invoice_number(invoice_number: str) -> bool:
        if not invoice_number:
            return False
        return bool(re.match(r"^[a-zA-Z0-9_-]{1,50}$", invoice_number))

    @staticmethod
    def sanitize_text(text: str, max_length: int = 1000) -> str:
        if not text:
            return ""
        if len(text) > max_length:
            text = text[:max_length] + "..."
        return re.sub(r'[<>"\']', "", html.escape(text)).strip()


class SecureErrorHandler:
    @staticmethod
    def handle_database_error(error: Exception, operation: str = "database operation") -> Tuple[str, str]:
        logger.error("Database error during %s: %s", operation, type(error).__name__)
        return "database-error", f"An error occurred during {operation}."


class RateLimiter:
    def __init__(self, max_requests: int = 120, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests: Dict[str, List[float]] = {}

    def is_allowed(self, identifier: str) -> bool:
        now = time.time()
        recent = [
            timestamp
            for timestamp in self.requests.get(identifier, [])
            if now - timestamp <= self.time_window
        ]
        if len(recent) >= self.max_requests:
            self.requests[identifier] = recent
            return False
        recent.append(now)
        self.requests[identifier] = recent
        return True


rate_limiter = RateLimiter()
