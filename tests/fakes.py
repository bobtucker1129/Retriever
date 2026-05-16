from __future__ import annotations

from datetime import datetime, timezone


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
            email = params[0]
            display_name = params[3]
            self.db.add_user(email=email, display_name=display_name, status="active", is_seed_admin=True)
            return

        if normalized.startswith("UPDATE users SET status = %s"):
            status = params[0]
            user_id = params[-1]
            self.db.user_by_id(user_id)["status"] = status
            return

        if "UPDATE users SET role_id" in normalized:
            role_key, _legacy_role, user_id = params
            self.db.user_by_id(user_id)["role_key"] = role_key
            self.db.user_by_id(user_id)["is_admin_role"] = role_key == "owner_admin"
            return

        if "UPDATE users SET booneops_level" in normalized:
            booneops_level, user_id = params
            self.db.user_by_id(user_id)["booneops_level"] = booneops_level
            return

        if "UPDATE users SET cloudflare_email = COALESCE" in normalized:
            email = params[0]
            user = self.db.users[email]
            user["cloudflare_email"] = user.get("cloudflare_email") or user.get("email") or user.get("username")
            user["email"] = user.get("email") or user.get("cloudflare_email") or user.get("username")
            user["display_name"] = user.get("display_name") or user.get("full_name") or user["email"]
            user["status"] = "active"
            user["role_key"] = "owner_admin"
            user["is_admin_role"] = True
            user["booneops_level"] = "medium"
            user["is_seed_admin"] = True
            return

        if "UPDATE users SET full_name" in normalized:
            (
                full_name,
                _cleaned_name,
                display_name,
                production_location_id,
                production_location_name,
                _production_location_id_again,
                _production_location_name_again,
                inventory_level,
                proofs_level,
                user_id,
            ) = params
            user = self.db.user_by_id(user_id)
            user["full_name"] = full_name
            if display_name:
                user["display_name"] = display_name
            user["production_location_id"] = production_location_id
            user["production_location_name"] = production_location_name
            user["inventory_level"] = inventory_level
            user["proofs_level"] = proofs_level
            return

        if "INSERT INTO users" in normalized:
            email = params[0]
            display_name = params[3]
            status = params[5]
            booneops_level = params[6]
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
            capability_key, email = params[0], params[1]
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

        if "FROM productionlocations" in normalized:
            self.last_result = [
                {"id": location_id, "name": name}
                for location_id, name in sorted(self.db.production_locations.items(), key=lambda item: item[1])
            ]
            return

        if "INSERT IGNORE INTO user_module_access" in normalized:
            module_key, email = params[0], params[1]
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

        if (
            normalized.startswith("DELETE uc FROM user_capabilities")
            and "WHERE uc.user_id = %s" in normalized
            and "JOIN capabilities" not in normalized
        ):
            user_id = params[0]
            self.db.capabilities_by_user.pop(user_id, None)
            return

        if normalized.startswith("DELETE uc FROM user_capabilities"):
            user_id, capability_key = params
            self.db.capabilities_by_user.setdefault(user_id, set()).discard(capability_key)
            return

        if normalized.startswith("DELETE uma FROM user_module_access"):
            user_id = params[0]
            self.db.modules_by_user.pop(user_id, None)
            return

        if normalized.startswith("DELETE FROM users"):
            user_id = params[0]
            email_to_delete = None
            for email, user in self.db.users.items():
                if user["id"] == user_id:
                    email_to_delete = email
                    break
            if email_to_delete:
                del self.db.users[email_to_delete]
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

        if "INSERT INTO fetch_conversations" in normalized:
            conversation_id, user_id, title, route_state = params
            self.db.fetch_conversations[conversation_id] = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "title": title,
                "status": "active",
                "route_state": route_state,
                "deleted": False,
            }
            return

        if "FROM fetch_conversations c" in normalized:
            user_id = params[0]
            if len(params) == 2:
                conversation_id = params[1]
                conversations = []
                for conversation in self.db.fetch_conversations.values():
                    if (
                        conversation["user_id"] == user_id
                        and not conversation.get("deleted")
                        and conversation["conversation_id"] == conversation_id
                    ):
                        message_count = len(
                            [
                                message
                                for message in self.db.fetch_messages
                                if message["conversation_id"] == conversation["conversation_id"]
                            ]
                        )
                        conversations.append({**conversation, "message_count": message_count})
                self.last_result = conversations[0] if conversations else None
                return
            conversations = []
            for conversation in self.db.fetch_conversations.values():
                if conversation["user_id"] == user_id and not conversation.get("deleted"):
                    message_count = len(
                        [
                            message
                            for message in self.db.fetch_messages
                            if message["conversation_id"] == conversation["conversation_id"]
                        ]
                    )
                    conversations.append({**conversation, "message_count": message_count})
            self.last_result = conversations
            return

        if normalized.startswith("UPDATE fetch_conversations SET title"):
            title, user_id, conversation_id = params
            conversation = self.db.fetch_conversations[conversation_id]
            if conversation["user_id"] == user_id and not conversation.get("deleted"):
                conversation["title"] = title
            return

        if normalized.startswith("UPDATE fetch_conversations SET deleted_at"):
            user_id, conversation_id = params
            conversation = self.db.fetch_conversations[conversation_id]
            if conversation["user_id"] == user_id:
                conversation["deleted"] = True
                conversation["status"] = "deleted"
            return

        if "INSERT INTO fetch_messages" in normalized:
            (
                message_id,
                conversation_id,
                user_id,
                role,
                content,
                route_key,
                model_label,
                context_percent,
                context_state,
                metadata_json,
            ) = params
            self.db.fetch_messages.append(
                {
                    "message_id": message_id,
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "role": role,
                    "content": content,
                    "route_key": route_key,
                    "model_label": model_label,
                    "context_percent": context_percent,
                    "context_state": context_state,
                    "metadata_json": metadata_json,
                    "created_at": datetime.now(timezone.utc),
                }
            )
            return

        if normalized.startswith("UPDATE fetch_conversations SET last_message_at"):
            route_key, user_id, conversation_id = params
            conversation = self.db.fetch_conversations[conversation_id]
            if conversation["user_id"] == user_id and not conversation.get("deleted"):
                conversation["route_state"] = route_key
            return

        if "FROM fetch_messages" in normalized:
            user_id, conversation_id = params
            self.last_result = [
                message
                for message in self.db.fetch_messages
                if message["user_id"] == user_id and message["conversation_id"] == conversation_id
            ]
            return

        if "WHERE u.cloudflare_email = %s" in normalized:
            email = params[0]
            self.last_result = self.db.users.get(email)
            return

        if "FROM users u" in normalized and "WHERE u.id = %s" in normalized:
            uid = params[0]
            self.last_result = None
            for u in self.db.users.values():
                if u["id"] == uid:
                    self.last_result = dict(u)
                    break
            return

        if "FROM users u" in normalized and "WHERE u.status IN" in normalized:
            rows = [dict(u) for u in self.db.users.values() if u["status"] in {"pending", "active", "suspended", "blocked"}]
            order = {"pending": 0, "active": 1, "suspended": 2, "blocked": 3}
            rows.sort(key=lambda r: (order.get(r["status"], 9), r["id"]))
            self.last_result = rows
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
        self.fetch_conversations = {}
        self.fetch_messages = []
        self.production_locations = {
            1: "00/Scott - Working",
            2: "PrePress",
        }

    def connection(self) -> FakeConnection:
        return FakeConnection(self)

    def add_user(
        self,
        email: str,
        display_name: str,
        status: str,
        booneops_level: str = "none",
        is_seed_admin: bool = False,
        last_seen_at: object = None,
        full_name: str = "",
        production_location_id: object = None,
        production_location_name: str = "",
        inventory_level: str = "no",
        proofs_level: str = "no",
    ) -> None:
        user_id = self.next_id
        self.next_id += 1
        self.users[email] = {
            "id": user_id,
            "username": email,
            "cloudflare_email": email,
            "email": email,
            "display_name": display_name,
            "full_name": full_name,
            "status": status,
            "role_key": "owner_admin" if is_seed_admin else None,
            "is_admin_role": is_seed_admin,
            "booneops_level": "medium" if is_seed_admin else booneops_level,
            "inventory_level": inventory_level,
            "proofs_level": proofs_level,
            "production_location_id": production_location_id,
            "production_location_name": production_location_name,
            "is_seed_admin": is_seed_admin,
            "last_seen_at": last_seen_at,
        }

    def user_by_id(self, user_id: int):
        for user in self.users.values():
            if user["id"] == user_id:
                return user
        raise KeyError(user_id)
