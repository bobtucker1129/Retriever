"""Admin user-management actions with audit logging."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.auth.permissions import CurrentUser
from app.db.repositories.audit import AuditEvent, AuditRepository
from app.db.repositories.sessions import SessionRepository
from app.db.repositories.users import UserRepository


@dataclass(frozen=True)
class AdminRepositories:
    users: UserRepository
    audit: AuditRepository
    sessions: SessionRepository


class AdminActionService:
    def __init__(self, repositories: AdminRepositories):
        self.repositories = repositories

    def activate_user(self, target_user_id: int, actor: CurrentUser) -> None:
        target = self.repositories.users.get_by_id(target_user_id)
        if not target:
            raise ValueError("Unknown user")
        if not target.full_name.strip():
            raise ValueError("Full name is required before approval.")
        self.repositories.users.activate_user(target_user_id, actor.id)
        self._audit(actor, "admin.user.activated", target_user_id, "succeeded")

    def suspend_user(self, target_user_id: int, actor: CurrentUser) -> None:
        self._require_mutable_target(target_user_id)
        self.repositories.users.suspend_user(target_user_id, actor.id)
        self.repositories.sessions.revoke_user_sessions(target_user_id)
        self._audit(actor, "admin.user.suspended", target_user_id, "succeeded")

    def block_user(self, target_user_id: int, actor: CurrentUser) -> None:
        self._require_mutable_target(target_user_id)
        self.repositories.users.block_user(target_user_id, actor.id)
        self.repositories.sessions.revoke_user_sessions(target_user_id)
        self._audit(actor, "admin.user.blocked", target_user_id, "succeeded")

    def delete_user(self, target_user_id: int, actor: CurrentUser) -> None:
        self._require_mutable_target(target_user_id)
        self.repositories.sessions.revoke_user_sessions(target_user_id)
        self.repositories.users.delete_user(target_user_id)
        self._audit(actor, "admin.user.deleted", target_user_id, "succeeded")

    def assign_role(self, target_user_id: int, role_key: str, actor: CurrentUser) -> None:
        self._require_mutable_target(target_user_id)
        self.repositories.users.assign_role(target_user_id, role_key)
        self._audit(actor, "admin.user.role_assigned", target_user_id, "succeeded")

    def set_module_access(
        self,
        target_user_id: int,
        module_key: str,
        enabled: bool,
        actor: CurrentUser,
    ) -> None:
        self._require_mutable_target(target_user_id)
        self.repositories.users.set_module_access(target_user_id, module_key, enabled)
        self._audit(actor, "admin.user.module_access_changed", target_user_id, "succeeded")

    def grant_capability(
        self,
        target_user_id: int,
        capability_key: str,
        actor: CurrentUser,
    ) -> None:
        self._require_mutable_target(target_user_id)
        self.repositories.users.grant_capability(target_user_id, capability_key, actor.id)
        self._audit(actor, "admin.user.capability_granted", target_user_id, "succeeded")

    def revoke_capability(
        self,
        target_user_id: int,
        capability_key: str,
        actor: CurrentUser,
    ) -> None:
        self._require_mutable_target(target_user_id)
        self.repositories.users.revoke_capability(target_user_id, capability_key)
        self._audit(actor, "admin.user.capability_revoked", target_user_id, "succeeded")

    def apply_user_matrix_row(
        self,
        target_user_id: int,
        actor: CurrentUser,
        *,
        full_name: str,
        production_location_id: Optional[int],
        production_location_name: str,
        admin_module: bool,
        fetch_module: bool,
        prepress_module: bool,
        fetch_access: bool,
        dsf_module: bool,
        inventory_level: str,
        proofs_level: str,
    ) -> None:
        """Apply entitlements from the admin matrix (one explicit Save per row)."""
        target = self.repositories.users.get_by_id(target_user_id)
        if not target:
            raise ValueError("Unknown user")
        if target.is_seed_admin:
            raise ValueError("The seed operator account cannot be changed from this matrix.")
        role_key = "owner_admin" if admin_module else "viewer"
        self.repositories.users.update_admin_matrix_profile(
            target_user_id,
            full_name=full_name,
            production_location_id=production_location_id,
            production_location_name=production_location_name,
            inventory_level=inventory_level,
            proofs_level=proofs_level,
        )
        self.assign_role(target_user_id, role_key, actor)
        self.set_module_access(target_user_id, "admin", admin_module, actor)
        self.set_module_access(target_user_id, "fetch", fetch_module, actor)
        self.set_module_access(target_user_id, "prepress", prepress_module, actor)
        self.set_module_access(target_user_id, "dsf", dsf_module, actor)
        self.set_module_access(target_user_id, "inventory", inventory_level != "no", actor)
        self.set_module_access(target_user_id, "proofs", proofs_level != "no", actor)
        if admin_module:
            self.grant_capability(target_user_id, "admin.manage_users", actor)
            self.grant_capability(target_user_id, "booneops.admin", actor)
        else:
            self.revoke_capability(target_user_id, "admin.manage_users", actor)
            self.revoke_capability(target_user_id, "booneops.admin", actor)
        if fetch_access:
            self.grant_capability(target_user_id, "fetch.access", actor)
        else:
            self.revoke_capability(target_user_id, "fetch.access", actor)
        if prepress_module:
            self.grant_capability(target_user_id, "prepress.access", actor)
        else:
            self.revoke_capability(target_user_id, "prepress.access", actor)
        if dsf_module:
            self.grant_capability(target_user_id, "dsf.access", actor)
        else:
            self.revoke_capability(target_user_id, "dsf.access", actor)

    def _require_mutable_target(self, target_user_id: int) -> None:
        target = self.repositories.users.get_by_id(target_user_id)
        if not target:
            raise ValueError("Unknown user")
        if target.is_seed_admin:
            raise ValueError("The seed operator account cannot be changed from admin actions.")

    def _audit(self, actor: CurrentUser, action_key: str, target_user_id: int, result: str) -> None:
        self.repositories.audit.write_event(
            AuditEvent(
                actor_type="user",
                actor_id=actor.email,
                user_id=actor.id,
                module_key="admin",
                action_key=action_key,
                capability_key="admin.manage_users",
                target_type="user",
                target_id=str(target_user_id),
                risk_level="strict",
                result=result,
            )
        )
