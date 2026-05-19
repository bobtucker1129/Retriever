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
    inventory_level: str = "no"
    is_admin: bool = False

    def has_capability(self, capability: str) -> bool:
        return self.is_admin or capability in self.capabilities

    def has_module(self, module: str) -> bool:
        return self.is_admin or module in self.modules

    def can_open_fetch_shell(self) -> bool:
        """Fetch UI (conversation rail); separate from FETCH_ENABLED / model routing."""
        if self.status != "active":
            return False
        return self.has_module("fetch") or self.has_capability("fetch.access")

    def can_submit_fetch_ask(self) -> bool:
        """POST /fetch/.../ask for the #printsmith-equivalent internal lane."""
        return self.can_open_fetch_shell()

    def can_open_prepress(self) -> bool:
        if self.status != "active":
            return False
        return self.has_module("prepress") or self.has_capability("prepress.access")

    def can_open_wiki(self) -> bool:
        """Internal Boone knowledge base; active employees can read by default."""
        return self.status == "active"

    def can_open_inventory(self) -> bool:
        if self.status != "active":
            return False
        return self.is_admin or self.inventory_level in {"viewer", "manager"}

    def can_manage_inventory(self) -> bool:
        if self.status != "active":
            return False
        return self.is_admin or self.inventory_level == "manager"
