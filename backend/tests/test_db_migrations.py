from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from wavemonitor_backend.db import create_database_engine, create_schema


def test_create_schema_migrates_legacy_sqlite_rule_and_source_constraints(tmp_path: Path):
    # Given: a historical SQLite schema with NOT NULL levels and global source identity.
    database_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE instrument (
                id INTEGER NOT NULL,
                name VARCHAR(120) NOT NULL,
                enabled BOOLEAN NOT NULL,
                support NUMERIC(24, 10) NOT NULL,
                resistance NUMERIC(24, 10) NOT NULL,
                near_support_threshold NUMERIC(24, 10) NOT NULL,
                risk_reward_threshold NUMERIC(24, 10) NOT NULL,
                created_at DATETIME,
                updated_at DATETIME,
                PRIMARY KEY (id)
            );
            CREATE TABLE sourcemapping (
                id INTEGER NOT NULL,
                instrument_id INTEGER NOT NULL,
                provider VARCHAR(11) NOT NULL,
                market_type VARCHAR(13) NOT NULL,
                symbol VARCHAR(80) NOT NULL,
                enabled BOOLEAN NOT NULL,
                PRIMARY KEY (id),
                CONSTRAINT uq_source_mapping_identity UNIQUE (
                    provider, market_type, symbol
                ),
                FOREIGN KEY(instrument_id) REFERENCES instrument (id)
            );
            INSERT INTO instrument (
                id, name, enabled, support, resistance,
                near_support_threshold, risk_reward_threshold
            ) VALUES (1, 'Bitcoin', 1, 90000.1, 110000.25, 0.02, 3.5);
            INSERT INTO sourcemapping (
                id, instrument_id, provider, market_type, symbol, enabled
            ) VALUES (1, 1, 'binance', 'usd_m_futures', 'BTCUSDT', 1);
            """
        )

    # When: application startup creates/migrates schema.
    create_schema(create_database_engine(f"sqlite:///{database_path}"))

    # Then: nullable levels and per-instrument source identity work with old rows preserved.
    with sqlite3.connect(database_path) as connection:
        instrument_columns = {
            row[1]: row[3] for row in connection.execute("PRAGMA table_info(instrument)")
        }
        source_table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'sourcemapping'"
        ).fetchone()[0]
        assert instrument_columns["support"] == 0
        assert instrument_columns["resistance"] == 0
        assert instrument_columns["near_support_threshold"] == 0
        assert instrument_columns["risk_reward_threshold"] == 0
        assert "uq_source_mapping_per_instrument" in source_table_sql
        assert "uq_source_mapping_identity" not in source_table_sql
        connection.execute(
            """
            INSERT INTO instrument (
                id, name, enabled, support, resistance,
                near_support_threshold, risk_reward_threshold
            ) VALUES (2, 'Resistance only', 1, NULL, 120000, NULL, NULL)
            """
        )
        connection.execute(
            """
            INSERT INTO sourcemapping (instrument_id, provider, market_type, symbol, enabled)
            VALUES (2, 'binance', 'usd_m_futures', 'BTCUSDT', 1)
            """
        )
        migrated_rows = connection.execute("SELECT COUNT(*) FROM instrument").fetchone()[0]
        assert migrated_rows == 2


def test_create_schema_updates_support_breach_state_and_observation_index(tmp_path: Path):
    # Given: a database created before support-breach alerts were introduced.
    database_path = tmp_path / "legacy-rule-state.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE lastrulestate (
                id INTEGER NOT NULL PRIMARY KEY,
                instrument_id INTEGER NOT NULL,
                source_mapping_id INTEGER NOT NULL,
                last_price NUMERIC(24, 10),
                near_support_active BOOLEAN NOT NULL,
                risk_reward_active BOOLEAN NOT NULL,
                above_resistance_active BOOLEAN NOT NULL,
                near_support_last_alert_at DATETIME,
                risk_reward_last_alert_at DATETIME,
                breakout_last_alert_at DATETIME,
                last_invalid_state VARCHAR(80),
                updated_at DATETIME NOT NULL
            );
            CREATE TABLE priceobservation (
                id INTEGER NOT NULL PRIMARY KEY,
                source_mapping_id INTEGER NOT NULL,
                price NUMERIC(24, 10),
                observed_at DATETIME NOT NULL,
                raw_path VARCHAR(120),
                error VARCHAR(500)
            );
            INSERT INTO lastrulestate (
                id, instrument_id, source_mapping_id, near_support_active,
                risk_reward_active, above_resistance_active, updated_at
            ) VALUES (1, 1, 1, 0, 0, 0, '2026-01-01 00:00:00');
            """
        )

    # When: the current application initializes the existing database twice.
    engine = create_database_engine(f"sqlite:///{database_path}")
    create_schema(engine)
    create_schema(engine)

    # Then: new columns exist and existing rows receive safe defaults.
    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(lastrulestate)")
        }
        state = connection.execute(
            """
            SELECT support_breach_active, support_breach_last_alert_at
            FROM lastrulestate WHERE id = 1
            """
        ).fetchone()
        observation_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(priceobservation)")
        }
    assert {"support_breach_active", "support_breach_last_alert_at"} <= columns
    assert state == (0, None)
    assert "ix_priceobservation_observed_at" in observation_indexes


def test_create_schema_deduplicates_alerts_and_adds_once_only_index(tmp_path: Path):
    # Given: a historical alert table containing duplicate source/rule rows.
    database_path = tmp_path / "legacy-alerts.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE alertevent (
                id INTEGER NOT NULL PRIMARY KEY,
                instrument_id INTEGER NOT NULL,
                source_mapping_id INTEGER NOT NULL,
                alert_kind VARCHAR(19) NOT NULL,
                price NUMERIC(24, 10) NOT NULL,
                support NUMERIC(24, 10) NOT NULL,
                resistance NUMERIC(24, 10) NOT NULL,
                threshold NUMERIC(24, 10),
                message VARCHAR(1000) NOT NULL,
                triggered_at DATETIME NOT NULL
            );
            INSERT INTO alertevent VALUES
                (1, 1, 1, 'near_support', 101, 100, 120, 0.02, 'first', '2026-01-01'),
                (2, 1, 1, 'near_support', 102, 100, 120, 0.02, 'duplicate', '2026-01-02');
            """
        )

    # When: application startup migrates the existing database.
    create_schema(create_database_engine(f"sqlite:///{database_path}"))

    # Then: one durable claim remains and the database rejects another duplicate claim.
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute("SELECT id, message FROM alertevent").fetchall()
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(alertevent)")}
        assert rows == [(1, "first")]
        assert "uq_alert_event_source_rule" in indexes
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO alertevent VALUES
                    (3, 1, 1, 'near_support', 103, 100, 120, 0.02, 'third', '2026-01-03')
                """
            )
