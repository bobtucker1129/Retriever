DELETE uc
FROM retriever_core.user_capabilities uc
JOIN retriever_core.capabilities c ON c.id = uc.capability_id
WHERE c.capability_key = 'fetch.ask_general';

DELETE FROM retriever_core.capabilities
WHERE capability_key = 'fetch.ask_general';

DELETE FROM retriever_core.app_settings
WHERE setting_key = 'fetch.general_questions_enabled';

ALTER TABLE retriever_core.users
  DROP INDEX idx_users_booneops_level;

ALTER TABLE retriever_core.users
  DROP COLUMN booneops_level;
