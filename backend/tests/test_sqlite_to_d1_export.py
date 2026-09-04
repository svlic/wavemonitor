from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from types import ModuleType


def load_exporter() -> ModuleType:
    path = Path(__file__).parents[2] / "worker" / "scripts" / "export_sqlite_to_d1.py"
    spec = importlib.util.spec_from_file_location("export_sqlite_to_d1", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load SQLite exporter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_export_database_preserves_current_business_rows(tmp_path: Path):
    source = tmp_path / "source.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.executescript(
            """
            CREATE TABLE instrument (
                id INTEGER PRIMARY KEY, name TEXT, enabled INTEGER, alert_mode TEXT,
                supports TEXT, resistances TEXT, high_water NUMERIC, fixed_drawdown NUMERIC,
                near_support_threshold NUMERIC, risk_reward_threshold NUMERIC,
                created_at TEXT, updated_at TEXT, rule_cycle_started_at TEXT
            );
            CREATE TABLE sourcemapping (
                id INTEGER PRIMARY KEY, instrument_id INTEGER, provider TEXT,
                market_type TEXT, symbol TEXT, enabled INTEGER
            );
            CREATE TABLE priceobservation (
                id INTEGER PRIMARY KEY, source_mapping_id INTEGER, price NUMERIC,
                observed_at TEXT, raw_path TEXT, error TEXT
            );
            CREATE TABLE alertevent (
                id INTEGER PRIMARY KEY, instrument_id INTEGER, source_mapping_id INTEGER,
                alert_kind TEXT, price NUMERIC, support NUMERIC, resistance NUMERIC,
                threshold NUMERIC, message TEXT, triggered_at TEXT, rule_cycle_started_at TEXT
            );
            CREATE TABLE lastrulestate (
                id INTEGER PRIMARY KEY, instrument_id INTEGER, source_mapping_id INTEGER,
                last_price NUMERIC, near_support_active INTEGER, risk_reward_active INTEGER,
                above_resistance_active INTEGER, support_breach_active INTEGER,
                near_support_last_alert_at TEXT, risk_reward_last_alert_at TEXT,
                breakout_last_alert_at TEXT, support_breach_last_alert_at TEXT,
                last_invalid_state TEXT, updated_at TEXT
            );
            CREATE TABLE telegramdelivery (
                id INTEGER PRIMARY KEY, status TEXT, message_kind TEXT, message_text TEXT,
                chat_ref TEXT, telegram_message_id TEXT, safe_error TEXT, delivered_at TEXT
            );
            INSERT INTO instrument VALUES (
                1, 'Owner''s setup', 1, 'static', '["90"]', '["110"]', NULL, NULL,
                0.02, 3.5, '2026-01-01', '2026-01-01', '2026-01-01'
            );
            INSERT INTO sourcemapping VALUES
                (2, 1, 'binance', 'usd_m_futures', 'BTCUSDT', 1);
            INSERT INTO priceobservation VALUES
                (3, 2, 100.125, '2026-01-01T00:02:00Z', 'mark_price.markPrice', NULL);
            INSERT INTO alertevent VALUES (
                4, 1, 2, 'near_support', 100.125, 90, 110, 0.02, 'owner''s alert',
                '2026-01-01T00:02:00Z', '2026-01-01'
            );
            INSERT INTO lastrulestate VALUES (
                5, 1, 2, 100.125, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL,
                '2026-01-01T00:02:00Z'
            );
            INSERT INTO telegramdelivery VALUES (
                6, 'sent', 'alert', 'owner''s alert', 'redacted', '7', NULL,
                '2026-01-01T00:02:01Z'
            );
            """
        )

    target = sqlite3.connect(":memory:")
    migration = Path(__file__).parents[2] / "worker" / "migrations" / "0001_initial.sql"
    target.executescript(migration.read_text(encoding="utf-8"))
    target.executescript(load_exporter().export_database(source))

    assert target.execute("SELECT name,supports,resistances FROM instrument").fetchone() == (
        "Owner's setup",
        '["90"]',
        '["110"]',
    )
    assert target.execute("SELECT symbol FROM source_mapping").fetchone() == ("BTCUSDT",)
    assert target.execute("SELECT price FROM price_observation").fetchone() == ("100.125",)
    assert target.execute("SELECT message FROM alert_event").fetchone() == ("owner's alert",)
    assert target.execute("SELECT last_price FROM last_rule_state").fetchone() == ("100.125",)
    assert target.execute("SELECT telegram_message_id FROM telegram_delivery").fetchone() == ("7",)
