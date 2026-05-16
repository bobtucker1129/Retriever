# retriever_core MySQL Schema

**Status:** planning document  
**Scope:** first MySQL schema for new Retriever auth, Fetch readiness, delayed reports, settings, and audit metadata  
**Inputs:** `AUTH_REDESIGN.md`, `FETCH_TRUST_PLAN.md`, `AUDIT_LOG_DESIGN.md`, `RUNTIME_NOTES.md`

## Plain-English Summary

New Retriever should use the existing Boone MySQL server and the existing `retriever_core` schema. The old Windows Retriever already uses `retriever_core.users`; the rebuild extends that app-state home with Cloudflare identity, module gates, sessions, audit, and Fetch metadata instead of creating a separate `retriever_cloudflare` schema.

Do not migrate old Fetch conversations or private library data by default. Old Fetch is not a compatibility target.

## Schema Boundary

Use `retriever_core` for:

- Cloudflare-linked users
- pending/active/suspended/blocked user states
- app roles
- capabilities
- module access
- BooneOps level
- app sessions or session metadata
- app settings
- delayed reports and report artifacts
- audit metadata
- schema migration tracking

Do not use `retriever_core` for:

- PrintSmith business source data
- MIS/Postgres source-of-truth data
- old Fetch conversation migration by default
- production secrets
- raw customer-upload corpuses
- generic SQL proxy behavior

## Naming Rules

- Use plural table names.
- Use `id BIGINT UNSIGNED AUTO_INCREMENT` primary keys for app-owned records.
- Use `created_at` and `updated_at` consistently.
- Store Cloudflare emails lowercase.
- Prefer explicit join tables over comma-separated lists.
- Avoid MySQL `ENUM` for business concepts that may grow; use constrained strings in app validation.
- Use JSON columns only for metadata that does not need frequent querying.

## First Tables

Minimum first schema:

1. `schema_migrations`
2. `users`
3. `roles`
4. `capabilities`
5. `user_capabilities`
6. `user_module_access`
7. `sessions`
8. `app_settings`
9. `delayed_reports`
10. `report_artifacts`
11. `audit_events`

These are enough to build the Cloudflare auth shell and first Fetch skeleton while preserving the old password-auth compatibility fields already present in `retriever_core.users`.

## Users

Plain English: one row per person who reaches Retriever through Cloudflare.

```sql
CREATE TABLE retriever_core.users (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  cloudflare_email VARCHAR(255) NOT NULL,
  display_name VARCHAR(255) DEFAULT NULL,
  first_name VARCHAR(100) DEFAULT NULL,
  last_name VARCHAR(100) DEFAULT NULL,
  department VARCHAR(100) DEFAULT NULL,
  job_role VARCHAR(100) DEFAULT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  role_id BIGINT UNSIGNED DEFAULT NULL,
  booneops_level VARCHAR(32) NOT NULL DEFAULT 'none',
  is_seed_admin BOOLEAN NOT NULL DEFAULT FALSE,
  last_seen_at DATETIME DEFAULT NULL,
  approved_at DATETIME DEFAULT NULL,
  approved_by_user_id BIGINT UNSIGNED DEFAULT NULL,
  suspended_at DATETIME DEFAULT NULL,
  blocked_at DATETIME DEFAULT NULL,
  notes TEXT DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_users_cloudflare_email (cloudflare_email),
  KEY idx_users_status (status),
  KEY idx_users_role_id (role_id),
  KEY idx_users_booneops_level (booneops_level)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Allowed `status` values in app validation:

- `pending`
- `active`
- `suspended`
- `blocked`

Allowed `booneops_level` values in app validation:

- `none`
- `light`
- `medium`

Launch behavior:

- seed Master Tate as admin/operator
- auto-create other Cloudflare users as `pending`
- pending users see an access-pending page
- admin activates users and assigns capabilities

No normal employee password hash belongs here.

## Roles

Plain English: role is the person's broad business/app role, not their exact permission list.

```sql
CREATE TABLE retriever_core.roles (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  role_key VARCHAR(64) NOT NULL,
  label VARCHAR(120) NOT NULL,
  description TEXT DEFAULT NULL,
  is_admin_role BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_roles_role_key (role_key)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Recommended seed roles:

- `owner_admin`
- `project_manager`
- `sales`
- `production`
- `prepress`
- `dsf_operator`
- `shipping`
- `viewer`

## Capabilities

Plain English: capabilities are the exact things the app checks before showing or doing work.

```sql
CREATE TABLE retriever_core.capabilities (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  capability_key VARCHAR(120) NOT NULL,
  label VARCHAR(160) NOT NULL,
  description TEXT DEFAULT NULL,
  risk_level VARCHAR(32) NOT NULL DEFAULT 'light',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_capabilities_key (capability_key),
  KEY idx_capabilities_risk_level (risk_level)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Recommended first seed capabilities:

- `admin.manage_users`
- `admin.manage_settings`
- `fetch.access`
- `fetch.ask_internal`
- `fetch.ask_general`
- `fetch.email_cleanup`
- `fetch.upload`
- `fetch.schedule_report`
- `fetch.view_reports`

Hold for later:

- `prepress.view_wip`
- `prepress.update_wip`
- `prepress.save_job_ticket`
- `dsf.view_invoice`
- `dsf.run_actions`
- `inventory.view`
- `inventory.adjust_stock`

## User Capabilities

Plain English: per-user permission assignments.

```sql
CREATE TABLE retriever_core.user_capabilities (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  capability_id BIGINT UNSIGNED NOT NULL,
  granted_by_user_id BIGINT UNSIGNED DEFAULT NULL,
  granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  notes TEXT DEFAULT NULL,
  UNIQUE KEY uq_user_capability (user_id, capability_id),
  KEY idx_user_capabilities_user_id (user_id),
  KEY idx_user_capabilities_capability_id (capability_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Application rule:

- a row means the capability is currently active
- revoking a capability deletes the row or moves it through an explicit app action
- every grant/revoke writes an audit event, so history lives in `audit_events`

## Module Access

Plain English: module access controls what appears in the app shell.

```sql
CREATE TABLE retriever_core.user_module_access (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT UNSIGNED NOT NULL,
  module_key VARCHAR(64) NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  granted_by_user_id BIGINT UNSIGNED DEFAULT NULL,
  granted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_user_module (user_id, module_key),
  KEY idx_user_module_access_user_id (user_id),
  KEY idx_user_module_access_module_key (module_key)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

First module keys:

- `fetch`
- `admin`
- `help`

Later module keys:

- `proofs`
- `prepress`
- `dsf`
- `inventory`

Do not show old modules in new Retriever until they are rebuilt or intentionally bridged.

## Sessions

Plain English: track Retriever sessions enough to revoke them and troubleshoot auth without relying only on a signed cookie.

```sql
CREATE TABLE retriever_core.sessions (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  session_id CHAR(64) NOT NULL,
  user_id BIGINT UNSIGNED NOT NULL,
  cloudflare_email VARCHAR(255) NOT NULL,
  cloudflare_identity_hash CHAR(64) DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at DATETIME DEFAULT NULL,
  expires_at DATETIME NOT NULL,
  revoked_at DATETIME DEFAULT NULL,
  user_agent_hash CHAR(64) DEFAULT NULL,
  source_ip_hash CHAR(64) DEFAULT NULL,
  UNIQUE KEY uq_sessions_session_id (session_id),
  KEY idx_sessions_user_id (user_id),
  KEY idx_sessions_expires_at (expires_at),
  KEY idx_sessions_revoked_at (revoked_at)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Rules:

- cookie values are never stored raw
- source IP and user agent can be hashed if retained
- deleting or suspending a user should revoke active sessions

## App Settings

Plain English: settings that should change without a code deploy.

```sql
CREATE TABLE retriever_core.app_settings (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  setting_key VARCHAR(120) NOT NULL,
  setting_value TEXT NOT NULL,
  value_type VARCHAR(32) NOT NULL DEFAULT 'string',
  description TEXT DEFAULT NULL,
  updated_by_user_id BIGINT UNSIGNED DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_app_settings_key (setting_key)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Recommended first settings:

- `fetch.enabled`
- `fetch.general_questions_enabled`
- `fetch.uploads_enabled`
- `fetch.delayed_reports_enabled`
- `auth.pending_users_enabled`
- `runtime.maintenance_banner`

## Delayed Reports

Plain English: report jobs are first-class app records so heavy Fetch work does not look frozen.

```sql
CREATE TABLE retriever_core.delayed_reports (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  report_id CHAR(36) NOT NULL,
  user_id BIGINT UNSIGNED NOT NULL,
  conversation_id VARCHAR(64) DEFAULT NULL,
  route_key VARCHAR(64) NOT NULL,
  title VARCHAR(255) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'queued',
  progress_label VARCHAR(255) DEFAULT NULL,
  request_summary TEXT DEFAULT NULL,
  metadata_json JSON DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at DATETIME DEFAULT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  completed_at DATETIME DEFAULT NULL,
  failed_at DATETIME DEFAULT NULL,
  error_category VARCHAR(80) DEFAULT NULL,
  request_id VARCHAR(80) DEFAULT NULL,
  correlation_id VARCHAR(80) DEFAULT NULL,
  UNIQUE KEY uq_delayed_reports_report_id (report_id),
  KEY idx_delayed_reports_user_status (user_id, status),
  KEY idx_delayed_reports_route_key (route_key),
  KEY idx_delayed_reports_created_at (created_at)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Allowed `status` values in app validation:

- `queued`
- `running`
- `waiting`
- `completed`
- `failed`
- `cancelled`

Do not store full customer payloads in `request_summary`. Use redacted summaries and correlation IDs.

## Report Artifacts

Plain English: downloadable files from delayed reports.

```sql
CREATE TABLE retriever_core.report_artifacts (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  report_id CHAR(36) NOT NULL,
  artifact_id CHAR(36) NOT NULL,
  label VARCHAR(255) NOT NULL,
  content_type VARCHAR(120) DEFAULT NULL,
  storage_path VARCHAR(500) NOT NULL,
  size_bytes BIGINT UNSIGNED DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at DATETIME DEFAULT NULL,
  downloaded_at DATETIME DEFAULT NULL,
  UNIQUE KEY uq_report_artifacts_artifact_id (artifact_id),
  KEY idx_report_artifacts_report_id (report_id),
  KEY idx_report_artifacts_expires_at (expires_at)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Rules:

- `storage_path` is a server-side path or object key, not an arbitrary public URL
- downloads go through Retriever authorization
- artifacts inherit report/user access

## Audit Events

Plain English: record important app and service actions without storing sensitive full content by default.

```sql
CREATE TABLE retriever_core.audit_events (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actor_type VARCHAR(32) NOT NULL,
  actor_id VARCHAR(120) DEFAULT NULL,
  user_id BIGINT UNSIGNED DEFAULT NULL,
  module_key VARCHAR(64) DEFAULT NULL,
  action_key VARCHAR(120) NOT NULL,
  route_key VARCHAR(64) DEFAULT NULL,
  capability_key VARCHAR(120) DEFAULT NULL,
  target_type VARCHAR(80) DEFAULT NULL,
  target_id VARCHAR(120) DEFAULT NULL,
  risk_level VARCHAR(32) NOT NULL DEFAULT 'light',
  result VARCHAR(32) NOT NULL,
  request_id VARCHAR(80) DEFAULT NULL,
  correlation_id VARCHAR(80) DEFAULT NULL,
  error_category VARCHAR(80) DEFAULT NULL,
  metadata_redacted JSON DEFAULT NULL,
  KEY idx_audit_events_occurred_at (occurred_at),
  KEY idx_audit_events_user_id (user_id),
  KEY idx_audit_events_module_action (module_key, action_key),
  KEY idx_audit_events_risk_result (risk_level, result),
  KEY idx_audit_events_correlation_id (correlation_id)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Allowed `actor_type` values in app validation:

- `user`
- `service`
- `agent`
- `system`

Allowed `risk_level` values in app validation:

- `light`
- `standard`
- `strict`

Allowed `result` values in app validation:

- `requested`
- `succeeded`
- `failed`
- `denied`

Required first audit events:

- Cloudflare identity accepted
- pending user created
- user activated/suspended/blocked
- capability granted/revoked
- BooneOps level changed
- Fetch route used
- delayed report created/completed/failed
- artifact downloaded
- broker auth rejected
- token authority dependency degraded

## Schema Migrations

Plain English: track which DB migrations have run.

```sql
CREATE TABLE retriever_core.schema_migrations (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  version VARCHAR(120) NOT NULL,
  description VARCHAR(255) NOT NULL,
  applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  applied_by VARCHAR(120) DEFAULT NULL,
  checksum VARCHAR(128) DEFAULT NULL,
  UNIQUE KEY uq_schema_migrations_version (version)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## First Seed Data

Seed only enough to start safely:

- owner/admin role
- viewer role
- first Fetch capabilities
- Master Tate user as active admin
- `fetch.enabled=false`
- `fetch.general_questions_enabled=false`
- `fetch.delayed_reports_enabled=true`
- `auth.pending_users_enabled=true`

Do not seed a default password.

## Migration Rules

- Do not auto-create `admin/admin123`.
- Do not copy old Fetch conversations by default.
- Do not copy old private library data by default.
- Do not copy old local password hashes into new auth.
- Do not write to `retriever_core` from the new app.
- Do not store production secrets in MySQL.
- Every schema change should be a named migration with rollback notes.

## Open Questions

- Is the Boone MySQL version new enough for JSON columns, or should JSON fields be `LONGTEXT` with app validation?
- Should sessions be fully server-side or cookie-plus-session-metadata?
- What is the initial audit retention period?
- Which report artifacts should expire automatically?
- Should `retriever_app` have migration privileges in production, or should deploy scripts use a separate migration user?
