from __future__ import annotations


class FakeCursor:
    def __init__(self, db: "FakeDb", dictionary: bool = False):
        self.db = db
        self.dictionary = dictionary
        self.last_result = None
        self.statements = db.statements

    def execute(self, operation: str, params: tuple = ()) -> None:
        normalized = " ".join(operation.split())
        self.statements.append((normalized, params))

        if "INSERT INTO users" in normalized and "'active'" in normalized:
            email, display_name = params
            self.db.add_user(email=email, display_name=display_name, status="active", is_seed_admin=True)
            return

        if normalized.startswith("UPDATE users SET status = %s"):
            status = params[0]
            user_id = params[-1]
            self.db.user_by_id(user_id)["status"] = status
            return

        if "UPDATE users SET role_id" in normalized:
            role_key, user_id = params
            self.db.user_by_id(user_id)["role_key"] = role_key
            self.db.user_by_id(user_id)["is_admin_role"] = role_key == "owner_admin"
            return

        if "UPDATE users SET booneops_level" in normalized:
            booneops_level, user_id = params
            self.db.user_by_id(user_id)["booneops_level"] = booneops_level
            return

        if "INSERT INTO users" in normalized:
            email, display_name, status, booneops_level = params
            self.db.add_user(
                email=email,
                display_name=display_name,
                status=status,
                booneops_level=booneops_level,
            )
            return

        if (
            "user_capabilities" in normalized
            and "capability_key = %s" in normalized
            and "WHERE u.cloudflare_email = %s" in normalized
        ):
            capability_key, email = params
            user_id = self.db.users[email]["id"]
            self.db.capabilities_by_user.setdefault(user_id, set()).add(capability_key)
            return

        if "SELECT c.capability_key" in normalized:
            user_id = params[0]
            self.last_result = [
                {"capability_key": key}
                for key in sorted(self.db.capabilities_by_user.get(user_id, set()))
            ]
            return

        if "INSERT IGNORE INTO user_module_access" in normalized:
            module_key, email = params
            user_id = self.db.users[email]["id"]
            self.db.modules_by_user.setdefault(user_id, set()).add(module_key)
            return

        if "INSERT INTO user_module_access" in normalized:
            user_id, module_key, enabled = params
            modules = self.db.modules_by_user.setdefault(user_id, set())
            if enabled:
                modules.add(module_key)
            else:
                modules.discard(module_key)
            return

        if "INSERT IGNORE INTO user_capabilities" in normalized:
            user_id, _actor_id, capability_key = params
            self.db.capabilities_by_user.setdefault(user_id, set()).add(capability_key)
            return

        if normalized.startswith("DELETE uc FROM user_capabilities"):
            user_id, capability_key = params
            self.db.capabilities_by_user.setdefault(user_id, set()).discard(capability_key)
            return

        if "UPDATE sessions SET revoked_at" in normalized and "session_id = %s" in normalized:
            session_id = params[0]
            self.db.revoked_sessions.append(session_id)
            if session_id in self.db.sessions:
                self.db.sessions[session_id]["revoked"] = True
            return

        if "UPDATE sessions SET revoked_at" in normalized and "user_id = %s" in normalized:
            self.db.revoked_sessions.append(("user", params[0]))
            return

        if "UPDATE sessions SET last_seen_at" in normalized:
            self.db.touched_sessions.append(params[0])
            return

        if "INSERT INTO sessions" in normalized:
            session_id, user_id, email, _expires_at, _user_agent_hash, _source_ip_hash = params
            self.db.sessions[session_id] = {
                "session_id": session_id,
                "user_id": user_id,
                "cloudflare_email": email,
                "revoked": False,
            }
            return

        if "FROM sessions" in normalized and "WHERE session_id = %s" in normalized:
            session_id, user_id = params
            session = self.db.sessions.get(session_id)
            if session and session["user_id"] == user_id and not session.get("revoked"):
                self.last_result = session
            else:
                self.last_result = None
            return

        if "INSERT INTO audit_events" in normalized:
            self.db.audit_events.append(params)
            return

        if "WHERE u.cloudflare_email = %s" in normalized:
            email = params[0]
            self.last_result = self.db.users.get(email)
            return

        if "WHERE u.status = %s" in normalized:
            status = params[0]
            self.last_result = [row for row in self.db.users.values() if row["status"] == status]
            return

        if "SELECT module_key" in normalized:
            user_id = params[0]
            self.last_result = [
                {"module_key": key}
                for key in sorted(self.db.modules_by_user.get(user_id, set()))
            ]
            return

        if "SELECT setting_value" in normalized:
            self.last_result = self.db.settings.get(params[0])
            return

    def fetchone(self):
        if isinstance(self.last_result, list):
            return self.last_result[0] if self.last_result else None
        return self.last_result

    def fetchall(self):
        if isinstance(self.last_result, list):
            return self.last_result
        return [] if self.last_result is None else [self.last_result]

    def close(self) -> None:
        pass


class FakeConnection:
    def __init__(self, db: "FakeDb"):
        self.db = db

    def cursor(self, dictionary: bool = False) -> FakeCursor:
        return FakeCursor(self.db, dictionary=dictionary)

    def close(self) -> None:
        pass


class FakeDb:
    def __init__(self):
        self.next_id = 1
        self.users = {}
        self.capabilities_by_user = {}
        self.modules_by_user = {}
        self.settings = {}
        self.statements = []
        self.audit_events = []
        self.revoked_sessions = []
        self.touched_sessions = []
        self.sessions = {}

    def connection(self) -> FakeConnection:
        return FakeConnection(self)

    def add_user(
        self,
        email: str,
        display_name: str,
        status: str,
        booneops_level: str = "none",
        is_seed_admin: bool = False,
    ) -> None:
        user_id = self.next_id
        self.next_id += 1
        self.users[email] = {
            "id": user_id,
            "cloudflare_email": email,
            "display_name": display_name,
            "status": status,
            "role_key": "owner_admin" if is_seed_admin else None,
            "is_admin_role": is_seed_admin,
            "booneops_level": "medium" if is_seed_admin else booneops_level,
            "is_seed_admin": is_seed_admin,
        }

    def user_by_id(self, user_id: int):
        for user in self.users.values():
            if user["id"] == user_id:
                return user
        raise KeyError(user_id)

