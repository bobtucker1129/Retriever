INSERT IGNORE INTO retriever_cloudflare.roles
  (role_key, label, description, is_admin_role)
VALUES
  ('owner_admin', 'Owner/Admin', 'Full Retriever admin/operator for launch.', TRUE),
  ('viewer', 'Viewer', 'Default limited user role.', FALSE);

INSERT IGNORE INTO retriever_cloudflare.capabilities
  (capability_key, label, description, risk_level)
VALUES
  ('admin.manage_users', 'Manage users', 'Approve and manage Retriever users.', 'strict'),
  ('admin.manage_settings', 'Manage settings', 'Update app-level settings.', 'strict'),
  ('fetch.access', 'Access Fetch', 'Open the Fetch module when enabled.', 'light'),
  ('fetch.ask_internal', 'Ask internal questions', 'Use approved Boone/internal routes.', 'light'),
  ('fetch.ask_general', 'Ask general questions', 'Use general LLM path when enabled.', 'light'),
  ('fetch.email_cleanup', 'Email cleanup', 'Use the ephemeral email cleanup helper.', 'light'),
  ('fetch.upload', 'Upload files', 'Upload files into Fetch when enabled.', 'standard'),
  ('fetch.schedule_report', 'Schedule reports', 'Create or manage scheduled reports.', 'standard'),
  ('fetch.view_reports', 'View reports', 'View generated report artifacts.', 'light');

INSERT IGNORE INTO retriever_cloudflare.app_settings
  (setting_key, setting_value, value_type, description)
VALUES
  ('fetch.enabled', 'false', 'boolean', 'Enable new Fetch module.'),
  ('fetch.general_questions_enabled', 'false', 'boolean', 'Enable general outside-world answers.'),
  ('fetch.uploads_enabled', 'false', 'boolean', 'Enable Fetch uploads.'),
  ('fetch.delayed_reports_enabled', 'true', 'boolean', 'Enable delayed report state.'),
  ('auth.pending_users_enabled', 'true', 'boolean', 'Auto-create pending users after Cloudflare Access.');

