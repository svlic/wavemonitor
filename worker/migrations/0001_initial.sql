PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS instrument (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL CHECK(length(name) BETWEEN 1 AND 120),
  enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
  alert_mode TEXT NOT NULL DEFAULT 'static' CHECK(alert_mode IN ('static', 'fixed_drawdown')),
  supports TEXT NOT NULL DEFAULT '[]',
  resistances TEXT NOT NULL DEFAULT '[]',
  high_water TEXT,
  fixed_drawdown TEXT,
  near_support_threshold TEXT,
  risk_reward_threshold TEXT,
  created_at TEXT,
  updated_at TEXT,
  rule_cycle_started_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_instrument_name ON instrument(name);

CREATE TABLE IF NOT EXISTS source_mapping (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  instrument_id INTEGER NOT NULL REFERENCES instrument(id) ON DELETE CASCADE,
  provider TEXT NOT NULL CHECK(provider IN ('yfinance', 'binance', 'hyperliquid')),
  market_type TEXT NOT NULL CHECK(market_type IN ('equity', 'usd_m_futures', 'coin_m_futures', 'perpetual')),
  symbol TEXT NOT NULL CHECK(length(symbol) BETWEEN 1 AND 80),
  enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0, 1)),
  UNIQUE(instrument_id, provider, market_type, symbol)
);
CREATE INDEX IF NOT EXISTS ix_source_mapping_instrument_id ON source_mapping(instrument_id);

CREATE TABLE IF NOT EXISTS price_observation (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_mapping_id INTEGER NOT NULL REFERENCES source_mapping(id) ON DELETE CASCADE,
  price TEXT,
  observed_at TEXT NOT NULL,
  raw_path TEXT,
  error TEXT
);
CREATE INDEX IF NOT EXISTS ix_price_source_time ON price_observation(source_mapping_id, observed_at);
CREATE INDEX IF NOT EXISTS ix_price_observation_observed_at ON price_observation(observed_at);

CREATE TABLE IF NOT EXISTS alert_event (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  instrument_id INTEGER NOT NULL REFERENCES instrument(id) ON DELETE CASCADE,
  source_mapping_id INTEGER NOT NULL REFERENCES source_mapping(id) ON DELETE CASCADE,
  alert_kind TEXT NOT NULL CHECK(alert_kind IN ('near_support', 'risk_reward', 'resistance_breakout', 'support_breach')),
  price TEXT NOT NULL,
  support TEXT NOT NULL,
  resistance TEXT NOT NULL,
  threshold TEXT,
  message TEXT NOT NULL,
  triggered_at TEXT NOT NULL,
  rule_cycle_started_at TEXT NOT NULL,
  UNIQUE(instrument_id, source_mapping_id, alert_kind, rule_cycle_started_at)
);
CREATE INDEX IF NOT EXISTS ix_alert_event_triggered_at ON alert_event(triggered_at DESC);

CREATE TABLE IF NOT EXISTS last_rule_state (
  instrument_id INTEGER NOT NULL REFERENCES instrument(id) ON DELETE CASCADE,
  source_mapping_id INTEGER NOT NULL REFERENCES source_mapping(id) ON DELETE CASCADE,
  last_price TEXT,
  near_support_active INTEGER NOT NULL DEFAULT 0,
  risk_reward_active INTEGER NOT NULL DEFAULT 0,
  above_resistance_active INTEGER NOT NULL DEFAULT 0,
  support_breach_active INTEGER NOT NULL DEFAULT 0,
  near_support_last_alert_at TEXT,
  risk_reward_last_alert_at TEXT,
  breakout_last_alert_at TEXT,
  support_breach_last_alert_at TEXT,
  last_invalid_state TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(instrument_id, source_mapping_id)
);

CREATE TABLE IF NOT EXISTS telegram_delivery (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  status TEXT NOT NULL CHECK(status IN ('sent', 'failed')),
  message_kind TEXT NOT NULL,
  message_text TEXT NOT NULL,
  chat_ref TEXT NOT NULL DEFAULT 'redacted',
  telegram_message_id TEXT,
  safe_error TEXT,
  delivered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runtime_state (
  singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
  scheduler_ready INTEGER NOT NULL DEFAULT 0,
  providers_ready INTEGER NOT NULL DEFAULT 0,
  enabled_sources INTEGER NOT NULL DEFAULT 0,
  polled_sources INTEGER NOT NULL DEFAULT 0,
  observations_written INTEGER NOT NULL DEFAULT 0,
  source_errors INTEGER NOT NULL DEFAULT 0,
  alert_events_created INTEGER NOT NULL DEFAULT 0,
  telegram_deliveries_attempted INTEGER NOT NULL DEFAULT 0,
  last_tick_started_at TEXT,
  last_tick_finished_at TEXT
);
INSERT OR IGNORE INTO runtime_state(singleton) VALUES (1);
