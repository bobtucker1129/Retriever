CREATE DATABASE IF NOT EXISTS retriever_core
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS retriever_core.schema_migrations (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  version VARCHAR(120) NOT NULL,
  description VARCHAR(255) NOT NULL,
  applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  applied_by VARCHAR(120) DEFAULT NULL,
  checksum VARCHAR(128) DEFAULT NULL,
  UNIQUE KEY uq_schema_migrations_version (version)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS retriever_core.users (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  first_name VARCHAR(100) DEFAULT NULL,
  last_name VARCHAR(100) DEFAULT NULL,
  full_name VARCHAR(255) DEFAULT NULL,
  email VARCHAR(255) DEFAULT NULL,
  phone VARCHAR(50) DEFAULT NULL,
  role ENUM('admin','super','project_manager','sales','production','viewer') DEFAULT 'viewer',
  department VARCHAR(100) DEFAULT NULL,
  location_id BIGINT UNSIGNED DEFAULT NULL,
  location_name VARCHAR(255) DEFAULT NULL,
  pm_id INT DEFAULT NULL,
  notes TEXT DEFAULT NULL,
  active BOOLEAN DEFAULT FALSE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  last_login DATETIME DEFAULT NULL,
  created_by VARCHAR(120) DEFAULT NULL
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

ALTER TABLE retriever_core.users
  ADD COLUMN cloudflare_email VARCHAR(255) DEFAULT NULL;

ALTER TABLE retriever_core.users
  ADD COLUMN display_name VARCHAR(255) DEFAULT NULL;

ALTER TABLE retriever_core.users
  ADD COLUMN job_role VARCHAR(100) DEFAULT NULL;

ALTER TABLE retriever_core.users
  ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'pending';

ALTER TABLE retriever_core.users
  ADD COLUMN role_id BIGINT UNSIGNED DEFAULT NULL;

ALTER TABLE retriever_core.users
  ADD COLUMN booneops_level VARCHAR(32) NOT NULL DEFAULT 'none';

ALTER TABLE retriever_core.users
  ADD COLUMN inventory_level VARCHAR(32) NOT NULL DEFAULT 'no';

ALTER TABLE retriever_core.users
  ADD COLUMN proofs_level VARCHAR(32) NOT NULL DEFAULT 'no';

ALTER TABLE retriever_core.users
  ADD COLUMN production_location_id BIGINT UNSIGNED DEFAULT NULL;

ALTER TABLE retriever_core.users
  ADD COLUMN production_location_name VARCHAR(255) DEFAULT NULL;

ALTER TABLE retriever_core.users
  ADD COLUMN is_seed_admin BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE retriever_core.users
  ADD COLUMN last_seen_at DATETIME DEFAULT NULL;

ALTER TABLE retriever_core.users
  ADD COLUMN approved_at DATETIME DEFAULT NULL;

ALTER TABLE retriever_core.users
  ADD COLUMN approved_by_user_id BIGINT UNSIGNED DEFAULT NULL;

ALTER TABLE retriever_core.users
  ADD COLUMN suspended_at DATETIME DEFAULT NULL;

ALTER TABLE retriever_core.users
  ADD COLUMN blocked_at DATETIME DEFAULT NULL;

CREATE INDEX idx_users_cloudflare_email ON retriever_core.users (cloudflare_email);
CREATE INDEX idx_users_status ON retriever_core.users (status);
CREATE INDEX idx_users_role_id ON retriever_core.users (role_id);
CREATE INDEX idx_users_booneops_level ON retriever_core.users (booneops_level);
CREATE INDEX idx_users_production_location_id ON retriever_core.users (production_location_id);

UPDATE retriever_core.users
SET cloudflare_email = COALESCE(cloudflare_email, email, username),
    email = COALESCE(email, cloudflare_email, username),
    display_name = COALESCE(display_name, full_name, email, username),
    status = CASE WHEN active = TRUE THEN 'active' ELSE status END
WHERE cloudflare_email IS NULL
   OR email IS NULL
   OR display_name IS NULL
   OR (active = TRUE AND status <> 'active');

CREATE TABLE IF NOT EXISTS retriever_core.roles (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  role_key VARCHAR(64) NOT NULL,
  label VARCHAR(120) NOT NULL,
  description TEXT DEFAULT NULL,
  is_admin_role BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_roles_role_key (role_key)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS retriever_core.capabilities (
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

CREATE TABLE IF NOT EXISTS retriever_core.user_capabilities (
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

CREATE TABLE IF NOT EXISTS retriever_core.user_module_access (
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

CREATE TABLE IF NOT EXISTS retriever_core.sessions (
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

CREATE TABLE IF NOT EXISTS retriever_core.app_settings (
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

CREATE TABLE IF NOT EXISTS retriever_core.delayed_reports (
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

CREATE TABLE IF NOT EXISTS retriever_core.report_artifacts (
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

CREATE TABLE IF NOT EXISTS retriever_core.audit_events (
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

INSERT IGNORE INTO retriever_core.schema_migrations
  (version, description, applied_by)
VALUES
  ('0001_retriever_core_auth', 'Retriever core Cloudflare auth compatibility schema', 'migration');
