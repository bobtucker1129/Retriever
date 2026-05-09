CREATE TABLE IF NOT EXISTS retriever_cloudflare.fetch_conversations (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  conversation_id CHAR(36) NOT NULL,
  user_id BIGINT UNSIGNED NOT NULL,
  title VARCHAR(255) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  route_state VARCHAR(64) NOT NULL DEFAULT 'local',
  last_message_at DATETIME DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at DATETIME DEFAULT NULL,
  UNIQUE KEY uq_fetch_conversations_id (conversation_id),
  KEY idx_fetch_conversations_user_status (user_id, status, deleted_at),
  KEY idx_fetch_conversations_last_message (user_id, last_message_at)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS retriever_cloudflare.fetch_messages (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  message_id CHAR(36) NOT NULL,
  conversation_id CHAR(36) NOT NULL,
  user_id BIGINT UNSIGNED NOT NULL,
  role VARCHAR(32) NOT NULL,
  content TEXT NOT NULL,
  route_key VARCHAR(64) NOT NULL DEFAULT 'local',
  model_label VARCHAR(120) DEFAULT NULL,
  context_percent TINYINT UNSIGNED DEFAULT NULL,
  context_state VARCHAR(32) DEFAULT NULL,
  metadata_json JSON DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_fetch_messages_id (message_id),
  KEY idx_fetch_messages_conversation (conversation_id, created_at),
  KEY idx_fetch_messages_user_created (user_id, created_at),
  KEY idx_fetch_messages_route_key (route_key)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

INSERT IGNORE INTO retriever_cloudflare.schema_migrations
  (version, description, applied_by)
VALUES
  ('0002_fetch_conversations', 'Fetch conversation and message storage', 'migration');
