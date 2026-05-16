"""User repository for Cloudflare-backed Retriever profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional, Protocol

from app.auth.cloudflare import CloudflareIdentity


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True)
class UserRecord:
    id: int
    email: str
    display_name: str
    status: str
    full_name: str = ""
    role_key: Optional[str] = None
    booneops_level: str = "none"
    inventory_level: str = "no"
    proofs_level: str = "no"
    production_location_id: Optional[int] = None
    production_location_name: str = ""
    is_admin: bool = False
    is_seed_admin: bool = False
    capabilities: frozenset[str] = field(default_factory=frozenset)
    modules: frozenset[str] = field(default_factory=frozenset)
    last_seen_at: Optional[datetime] = None


class CursorLike(Protocol):
    def execute(self, operation: str, params: tuple = ()) -> None:
        ...

    def fetchone(self):
        ...

    def fetchall(self):
        ...

    def close(self) -> None:
        ...


class ConnectionLike(Protocol):
    def cursor(self, dictionary: bool = False) -> CursorLike:
        ...

    def close(self) -> None:
        ...


ConnectionFactory = Callable[[], ConnectionLike]


class UserRepository:
    def __init__(self, connection_factory: ConnectionFactory):
        self._connection_factory = connection_factory

    def get_by_email(self, email: str) -> Optional[UserRecord]:
        email = normalize_email(email)
        row = self._fetch_user_row(email)
        if not row:
            return None
        return self._record_from_row(row)

    def get_by_id(self, user_id: int) -> Optional[UserRecord]:
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT u.id,
                       COALESCE(u.cloudflare_email, u.email, u.username) AS cloudflare_email,
                       u.display_name, u.full_name, u.status,
                       u.booneops_level, u.inventory_level, u.proofs_level,
                       u.production_location_id, u.production_location_name,
                       u.is_seed_admin, u.last_seen_at,
                       r.role_key, r.is_admin_role
                FROM users u
                LEFT JOIN roles r ON r.id = u.role_id
                WHERE u.id = %s
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()
        finally:
            cursor.close()
            conn.close()
        if not row:
            return None
        return self._record_from_row(row)

    def ensure_profile(
        self,
        identity: CloudflareIdentity,
        seed_admin_email: str,
    ) -> UserRecord:
        email = normalize_email(identity.email)
        existing = self.get_by_email(email)
        if existing:
            if email == normalize_email(seed_admin_email) and not existing.is_admin:
                self._promote_seed_admin(email)
                promoted = self.get_by_email(email)
                if promoted:
                    return promoted
            return existing

        if email == normalize_email(seed_admin_email):
            self._insert_seed_admin(identity)
        else:
            self._insert_pending(identity)

        created = self.get_by_email(email)
        if not created:
            raise RuntimeError("Profile was not created")
        return created

    def list_pending(self) -> list[UserRecord]:
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT u.id,
                       COALESCE(u.cloudflare_email, u.email, u.username) AS cloudflare_email,
                       u.display_name, u.full_name, u.status,
                       u.booneops_level, u.inventory_level, u.proofs_level,
                       u.production_location_id, u.production_location_name,
                       u.is_seed_admin, u.last_seen_at,
                       r.role_key, r.is_admin_role
                FROM users u
                LEFT JOIN roles r ON r.id = u.role_id
                WHERE u.status = %s
                ORDER BY u.created_at ASC
                """,
                ("pending",),
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
        return [self._record_from_row(row) for row in rows]

    def list_users_for_admin_directory(self) -> list[UserRecord]:
        """Pending first, then active, suspended, blocked — for the admin matrix."""
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT u.id,
                       COALESCE(u.cloudflare_email, u.email, u.username) AS cloudflare_email,
                       u.display_name, u.full_name, u.status,
                       u.booneops_level, u.inventory_level, u.proofs_level,
                       u.production_location_id, u.production_location_name,
                       u.is_seed_admin, u.last_seen_at,
                       r.role_key, r.is_admin_role
                FROM users u
                LEFT JOIN roles r ON r.id = u.role_id
                WHERE u.status IN ('pending', 'active', 'suspended', 'blocked')
                  AND COALESCE(u.cloudflare_email, u.email, u.username) IS NOT NULL
                ORDER BY FIELD(u.status, 'pending', 'active', 'suspended', 'blocked'),
                         u.id ASC
                """
            )
            rows = cursor.fetchall()
        finally:
            cursor.close()
            conn.close()
        return [self._record_from_row(row) for row in rows]

    def activate_user(self, user_id: int, approved_by_user_id: int) -> None:
        self._update_status(
            user_id=user_id,
            status="active",
            actor_user_id=approved_by_user_id,
            timestamp_column="approved_at",
        )

    def suspend_user(self, user_id: int, actor_user_id: int) -> None:
        self._update_status(
            user_id=user_id,
            status="suspended",
            actor_user_id=actor_user_id,
            timestamp_column="suspended_at",
        )

    def block_user(self, user_id: int, actor_user_id: int) -> None:
        self._update_status(
            user_id=user_id,
            status="blocked",
            actor_user_id=actor_user_id,
            timestamp_column="blocked_at",
        )

    def assign_role(self, user_id: int, role_key: str) -> None:
        legacy_role = "admin" if role_key == "owner_admin" else "viewer"
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE users
                SET role_id = (SELECT id FROM roles WHERE role_key = %s LIMIT 1),
                    role = %s
                WHERE id = %s
                """,
                (role_key, legacy_role, user_id),
            )
        finally:
            cursor.close()
            conn.close()

    def assign_booneops_level(self, user_id: int, booneops_level: str) -> None:
        if booneops_level not in {"none", "light", "medium"}:
            raise ValueError("Invalid BooneOps level")
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE users
                SET booneops_level = %s
                WHERE id = %s
                """,
                (booneops_level, user_id),
            )
        finally:
            cursor.close()
            conn.close()

    def update_admin_matrix_profile(
        self,
        user_id: int,
        *,
        full_name: str,
        production_location_id: Optional[int],
        production_location_name: str,
        inventory_level: str,
        proofs_level: str,
    ) -> None:
        inventory_level = _normalize_access_level(inventory_level)
        proofs_level = _normalize_access_level(proofs_level)
        cleaned_name = full_name.strip()
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE users
                SET full_name = %s,
                    display_name = CASE WHEN %s <> '' THEN %s ELSE display_name END,
                    email = COALESCE(email, cloudflare_email),
                    location_id = %s,
                    location_name = %s,
                    production_location_id = %s,
                    production_location_name = %s,
                    inventory_level = %s,
                    proofs_level = %s
                WHERE id = %s
                """,
                (
                    cleaned_name or None,
                    cleaned_name,
                    cleaned_name,
                    production_location_id,
                    production_location_name.strip() or None,
                    production_location_id,
                    production_location_name.strip() or None,
                    inventory_level,
                    proofs_level,
                    user_id,
                ),
            )
        finally:
            cursor.close()
            conn.close()

    def set_module_access(self, user_id: int, module_key: str, enabled: bool = True) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO user_module_access (user_id, module_key, enabled)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE enabled = VALUES(enabled)
                """,
                (user_id, module_key, enabled),
            )
        finally:
            cursor.close()
            conn.close()

    def grant_capability(self, user_id: int, capability_key: str, granted_by_user_id: int) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT IGNORE INTO user_capabilities
                  (user_id, capability_id, granted_by_user_id)
                SELECT %s, id, %s
                FROM capabilities
                WHERE capability_key = %s
                """,
                (user_id, granted_by_user_id, capability_key),
            )
        finally:
            cursor.close()
            conn.close()

    def revoke_capability(self, user_id: int, capability_key: str) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                DELETE uc
                FROM user_capabilities uc
                JOIN capabilities c ON c.id = uc.capability_id
                WHERE uc.user_id = %s AND c.capability_key = %s
                """,
                (user_id, capability_key),
            )
        finally:
            cursor.close()
            conn.close()

    def delete_user(self, user_id: int) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                DELETE uc
                FROM user_capabilities uc
                WHERE uc.user_id = %s
                """,
                (user_id,),
            )
            cursor.execute(
                """
                DELETE uma
                FROM user_module_access uma
                WHERE uma.user_id = %s
                """,
                (user_id,),
            )
            cursor.execute(
                """
                DELETE FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
        finally:
            cursor.close()
            conn.close()

    def _update_status(
        self,
        user_id: int,
        status: str,
        actor_user_id: int,
        timestamp_column: str,
    ) -> None:
        allowed_columns = {"approved_at", "suspended_at", "blocked_at"}
        if timestamp_column not in allowed_columns:
            raise ValueError("Invalid status timestamp column")
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"""
                UPDATE users
                SET status = %s,
                    active = CASE
                      WHEN %s = 'active' THEN TRUE
                      WHEN %s IN ('suspended', 'blocked') THEN FALSE
                      ELSE active
                    END,
                    {timestamp_column} = NOW(),
                    approved_by_user_id = CASE
                      WHEN %s = 'active' THEN %s
                      ELSE approved_by_user_id
                    END
                WHERE id = %s
                """,
                (status, status, status, status, actor_user_id, user_id),
            )
        finally:
            cursor.close()
            conn.close()

    def _fetch_user_row(self, email: str):
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT u.id,
                       COALESCE(u.cloudflare_email, u.email, u.username) AS cloudflare_email,
                       u.display_name, u.full_name, u.status,
                       u.booneops_level, u.inventory_level, u.proofs_level,
                       u.production_location_id, u.production_location_name,
                       u.is_seed_admin, u.last_seen_at,
                       r.role_key, r.is_admin_role
                FROM users u
                LEFT JOIN roles r ON r.id = u.role_id
                WHERE u.cloudflare_email = %s OR u.email = %s OR u.username = %s
                LIMIT 1
                """,
                (email, email, email),
            )
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

    def _insert_pending(self, identity: CloudflareIdentity) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO users
                  (username, password_hash, cloudflare_email, display_name, email,
                   status, booneops_level, role, active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'viewer', FALSE)
                """,
                (
                    normalize_email(identity.email),
                    _cloudflare_only_password_hash(),
                    normalize_email(identity.email),
                    identity.display_name or normalize_email(identity.email),
                    normalize_email(identity.email),
                    "pending",
                    "none",
                ),
            )
        finally:
            cursor.close()
            conn.close()

    def _insert_seed_admin(self, identity: CloudflareIdentity) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                INSERT INTO users
                  (username, password_hash, cloudflare_email, display_name, email,
                   status, role, active, role_id, booneops_level, is_seed_admin, approved_at)
                VALUES (
                  %s, %s, %s, %s, %s, 'active', 'admin', TRUE,
                  (SELECT id FROM roles WHERE role_key = 'owner_admin' LIMIT 1),
                  'medium', TRUE, NOW()
                )
                """,
                (
                    normalize_email(identity.email),
                    _cloudflare_only_password_hash(),
                    normalize_email(identity.email),
                    identity.display_name or normalize_email(identity.email),
                    normalize_email(identity.email),
                ),
            )
            self._grant_seed_admin_capabilities(cursor, normalize_email(identity.email))
            self._grant_seed_admin_modules(cursor, normalize_email(identity.email))
        finally:
            cursor.close()
            conn.close()

    def _promote_seed_admin(self, email: str) -> None:
        conn = self._connection_factory()
        cursor = conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE users
                SET cloudflare_email = COALESCE(cloudflare_email, email, username),
                    email = COALESCE(email, cloudflare_email, username),
                    display_name = COALESCE(display_name, full_name, email, username),
                    status = 'active',
                    role = 'admin',
                    active = TRUE,
                    role_id = (SELECT id FROM roles WHERE role_key = 'owner_admin' LIMIT 1),
                    booneops_level = 'medium',
                    is_seed_admin = TRUE,
                    approved_at = COALESCE(approved_at, NOW())
                WHERE cloudflare_email = %s OR email = %s OR username = %s
                """,
                (email, email, email),
            )
            self._grant_seed_admin_capabilities(cursor, email)
            self._grant_seed_admin_modules(cursor, email)
        finally:
            cursor.close()
            conn.close()

    def _grant_seed_admin_capabilities(self, cursor: CursorLike, email: str) -> None:
        for capability_key in ("admin.manage_users", "admin.manage_settings"):
            cursor.execute(
                """
                INSERT IGNORE INTO user_capabilities (user_id, capability_id)
                SELECT u.id, c.id
                FROM users u
                JOIN capabilities c ON c.capability_key = %s
                WHERE u.cloudflare_email = %s OR u.email = %s OR u.username = %s
                """,
                (capability_key, email, email, email),
            )

    def _grant_seed_admin_modules(self, cursor: CursorLike, email: str) -> None:
        for module_key in ("admin", "help"):
            cursor.execute(
                """
                INSERT IGNORE INTO user_module_access (user_id, module_key, enabled)
                SELECT id, %s, TRUE
                FROM users
                WHERE cloudflare_email = %s OR email = %s OR username = %s
                """,
                (module_key, email, email, email),
            )

    def _record_from_row(self, row) -> UserRecord:
        user_id = int(row["id"])
        identity_email = row.get("cloudflare_email") or row.get("email") or row.get("username")
        email = normalize_email(identity_email) if identity_email else f"user-{user_id}@unknown.local"
        raw_seen = row.get("last_seen_at")
        last_seen: Optional[datetime] = None
        if raw_seen is not None and not isinstance(raw_seen, datetime):
            try:
                last_seen = datetime.fromisoformat(str(raw_seen).replace("Z", "+00:00"))
            except ValueError:
                last_seen = None
        elif isinstance(raw_seen, datetime):
            last_seen = raw_seen
        return UserRecord(
            id=user_id,
            email=email,
            display_name=row.get("display_name") or email,
            full_name=row.get("full_name") or "",
            status=row.get("status") or "pending",
            role_key=row.get("role_key"),
            booneops_level=row.get("booneops_level") or "none",
            inventory_level=row.get("inventory_level") or "no",
            proofs_level=row.get("proofs_level") or "no",
            production_location_id=_optional_int(row.get("production_location_id")),
            production_location_name=row.get("production_location_name") or "",
            is_admin=bool(row.get("is_seed_admin") or row.get("is_admin_role")),
            is_seed_admin=bool(row.get("is_seed_admin")),
            capabilities=frozenset(self._capabilities_for_user(user_id)),
            modules=frozenset(self._modules_for_user(user_id)),
            last_seen_at=last_seen,
        )

    def _capabilities_for_user(self, user_id: int) -> list[str]:
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT c.capability_key
                FROM user_capabilities uc
                JOIN capabilities c ON c.id = uc.capability_id
                WHERE uc.user_id = %s
                ORDER BY c.capability_key
                """,
                (user_id,),
            )
            return [row["capability_key"] for row in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()

    def _modules_for_user(self, user_id: int) -> list[str]:
        conn = self._connection_factory()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT module_key
                FROM user_module_access
                WHERE user_id = %s AND enabled = TRUE
                ORDER BY module_key
                """,
                (user_id,),
            )
            return [row["module_key"] for row in cursor.fetchall()]
        finally:
            cursor.close()
            conn.close()


def _optional_int(value) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_access_level(value: str) -> str:
    normalized = (value or "no").strip().lower()
    if normalized not in {"no", "viewer", "manager"}:
        raise ValueError("Invalid module level")
    return normalized


def _cloudflare_only_password_hash() -> str:
    return "0" * 128
