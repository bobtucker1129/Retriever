"""Admin user-management actions with audit logging."""

from __future__ import annotations

from dataclasses import dataclass

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
        self.repositories.users.activate_user(target_user_id, actor.id)
        self._audit(actor, "admin.user.activated", target_user_id, "succeeded")

    def suspend_user(self, target_user_id: int, actor: CurrentUser) -> None:
        self.repositories.users.suspend_user(target_user_id, actor.id)
        self.repositories.sessions.revoke_user_sessions(target_user_id)
        self._audit(actor, "admin.user.suspended", target_user_id, "succeeded")

    def block_user(self, target_user_id: int, actor: CurrentUser) -> None:
        self.repositories.users.block_user(target_user_id, actor.id)
        self.repositories.sessions.revoke_user_sessions(target_user_id)
        self._audit(actor, "admin.user.blocked", target_user_id, "succeeded")

    def assign_role(self, target_user_id: int, role_key: str, actor: CurrentUser) -> None:
        self.repositories.users.assign_role(target_user_id, role_key)
        self._audit(actor, "admin.user.role_assigned", target_user_id, "succeeded")

    def assign_booneops_level(
        self,
        target_user_id: int,
        booneops_level: str,
        actor: CurrentUser,
    ) -> None:
        self.repositories.users.assign_booneops_level(target_user_id, booneops_level)
        self._audit(actor, "admin.user.booneops_level_assigned", target_user_id, "succeeded")

    def set_module_access(
        self,
        target_user_id: int,
        module_key: str,
        enabled: bool,
        actor: CurrentUser,
    ) -> None:
        self.repositories.users.set_module_access(target_user_id, module_key, enabled)
        self._audit(actor, "admin.user.module_access_changed", target_user_id, "succeeded")

    def grant_capability(
        self,
        target_user_id: int,
        capability_key: str,
        actor: CurrentUser,
    ) -> None:
        self.repositories.users.grant_capability(target_user_id, capability_key, actor.id)
        self._audit(actor, "admin.user.capability_granted", target_user_id, "succeeded")

    def revoke_capability(
        self,
        target_user_id: int,
        capability_key: str,
        actor: CurrentUser,
    ) -> None:
        self.repositories.users.revoke_capability(target_user_id, capability_key)
        self._audit(actor, "admin.user.capability_revoked", target_user_id, "succeeded")

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

