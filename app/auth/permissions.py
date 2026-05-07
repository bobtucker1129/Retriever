"""Permission helpers for the auth shell."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CurrentUser:
    id: int
    email: str
    display_name: str
    status: str = "pending"
    capabilities: frozenset[str] = field(default_factory=frozenset)
    modules: frozenset[str] = field(default_factory=frozenset)
    is_admin: bool = False

    def has_capability(self, capability: str) -> bool:
        return self.is_admin or capability in self.capabilities

    def has_module(self, module: str) -> bool:
        return self.is_admin or module in self.modules

