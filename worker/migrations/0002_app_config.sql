CREATE TABLE IF NOT EXISTS app_config (
  singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
  password_hash TEXT NOT NULL,
  password_salt TEXT NOT NULL,
  password_iterations INTEGER NOT NULL,
  session_secret TEXT NOT NULL,
  telegram_bot_token TEXT,
  telegram_chat_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  CHECK(
    (telegram_bot_token IS NULL AND telegram_chat_id IS NULL)
    OR (length(telegram_bot_token) > 0 AND length(telegram_chat_id) > 0)
  )
);
