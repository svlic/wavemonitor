from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
from sqlmodel import select

from wavemonitor_backend.db import create_database_engine, create_schema, session_scope
from wavemonitor_backend.models import Instrument
from wavemonitor_backend.support_resistance import AlertMode


def json_decimals(value: object) -> list[Decimal]:
    parsed = json.loads(value) if isinstance(value, str) else value
    assert isinstance(parsed, list)
    levels: list[Decimal] = []
    for item in parsed:
        assert isinstance(item, str)
        levels.append(Decimal(item))
    return levels


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

    # Then: scalar levels become JSON arrays and per-instrument source identity is preserved.
    with sqlite3.connect(database_path) as connection:
        instrument_columns = {
            row[1]: row[3] for row in connection.execute("PRAGMA table_info(instrument)")
        }
        source_table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'sourcemapping'"
        ).fetchone()[0]
        assert "supports" in instrument_columns
        assert "resistances" in instrument_columns
        assert "support" not in instrument_columns
        assert "resistance" not in instrument_columns
        assert instrument_columns["near_support_threshold"] == 0
        assert instrument_columns["risk_reward_threshold"] == 0
        assert "uq_source_mapping_per_instrument" in source_table_sql
        assert "uq_source_mapping_identity" not in source_table_sql
        migrated = connection.execute(
            "SELECT supports, resistances FROM instrument WHERE id = 1"
        ).fetchone()
        assert json_decimals(migrated[0]) == [Decimal("90000.1")]
        assert json_decimals(migrated[1]) == [Decimal("110000.25")]
        connection.execute(
            """
                INSERT INTO instrument (
                    id, name, enabled, supports, resistances,
                    near_support_threshold, risk_reward_threshold, rule_cycle_started_at
                ) VALUES (
                    2, 'Resistance only', 1, '[]', '["120000"]', NULL, NULL,
                    '2026-01-01 00:00:00'
                )

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


def test_create_schema_migrates_alert_claims_to_instrument_rule_cycles(tmp_path: Path):
    # Given: historical instrument and alert tables without explicit rule-cycle identity.
    database_path = tmp_path / "legacy-alerts.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE instrument (
                id INTEGER NOT NULL PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                enabled BOOLEAN NOT NULL,
                support NUMERIC(24, 10),
                resistance NUMERIC(24, 10),
                near_support_threshold NUMERIC(24, 10),
                risk_reward_threshold NUMERIC(24, 10),
                created_at DATETIME,
                updated_at DATETIME
            );
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
            INSERT INTO instrument VALUES
                (1, 'Bitcoin', 1, 98, 130, 0.02, 20, '2026-01-01', '2026-01-03');
            INSERT INTO alertevent VALUES
                (1, 1, 1, 'support_breach', 99, 100, 120, NULL, 'before edit', '2026-01-02'),
                (2, 1, 1, 'near_support', 101, 100, 120, 0.02, 'first', '2026-01-04'),
                (3, 1, 1, 'near_support', 102, 100, 120, 0.02, 'duplicate', '2026-01-05');
            """
        )

    # When: application startup migrates the existing database twice.
    engine = create_database_engine(f"sqlite:///{database_path}")
    create_schema(engine)
    create_schema(engine)

    # Then: boundaries are backfilled and claims are unique only inside one cycle.
    with sqlite3.connect(database_path) as connection:
        cycle = connection.execute(
            "SELECT rule_cycle_started_at FROM instrument WHERE id = 1"
        ).fetchone()[0]
        rows = connection.execute(
            "SELECT id, message, rule_cycle_started_at FROM alertevent"
        ).fetchall()
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'alertevent'"
        ).fetchone()[0]
        foreign_keys = {
            row[3] for row in connection.execute("PRAGMA foreign_key_list(alertevent)")
        }
        levels = connection.execute(
            "SELECT supports, resistances FROM instrument WHERE id = 1"
        ).fetchone()
        assert cycle == "2026-01-03"
        assert json_decimals(levels[0]) == [Decimal("98")]
        assert json_decimals(levels[1]) == [Decimal("130")]
        assert rows == [
            (1, "before edit", "2026-01-02"),
            (2, "first", "2026-01-03"),
        ]
        assert "rule_cycle_started_at" in table_sql
        assert foreign_keys == {"instrument_id", "source_mapping_id"}
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO alertevent (
                    id, instrument_id, source_mapping_id, alert_kind, price,
                    support, resistance, threshold, message, triggered_at,
                    rule_cycle_started_at
                ) VALUES (
                    3, 1, 1, 'near_support', 103, 100, 120, 0.02, 'same cycle',
                    '2026-01-06', '2026-01-03'
                )
                """
            )
        connection.execute(
            """
            INSERT INTO alertevent (
                id, instrument_id, source_mapping_id, alert_kind, price,
                support, resistance, threshold, message, triggered_at,
                rule_cycle_started_at
            ) VALUES (
                4, 1, 1, 'near_support', 104, 100, 120, 0.02, 'new cycle',
                '2026-02-01', '2026-02-01'
            )
            """
        )
        assert connection.execute("SELECT COUNT(*) FROM alertevent").fetchone()[0] == 3


def test_create_schema_preserves_orphan_alert_history(tmp_path: Path):
    # Given: a legacy alert references an instrument that no longer exists.
    database_path = tmp_path / "orphan-alert.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE instrument (
                id INTEGER NOT NULL PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                enabled BOOLEAN NOT NULL,
                support NUMERIC(24, 10),
                resistance NUMERIC(24, 10),
                near_support_threshold NUMERIC(24, 10),
                risk_reward_threshold NUMERIC(24, 10),
                created_at DATETIME,
                updated_at DATETIME
            );
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
                (1, 999, 1, 'support_breach', 99, 100, 120, NULL, 'orphan', '2026-01-02');
            """
        )

    # When: application startup performs the cycle-aware migration.
    engine = create_database_engine(f"sqlite:///{database_path}")
    create_schema(engine)

    # Then: the historical source row is preserved under its event-time cycle identity.
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT id, message, rule_cycle_started_at FROM alertevent"
        ).fetchall()
        assert rows == [(1, "orphan", "2026-01-02")]


def test_create_schema_migrates_fixed_drawdown_columns(tmp_path: Path):
    # Given: a historical SQLite schema without alert-mode or trailing-drawdown columns.
    database_path = tmp_path / "legacy-drawdown.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE instrument (
                id INTEGER NOT NULL PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                enabled BOOLEAN NOT NULL,
                support NUMERIC(24, 10),
                resistance NUMERIC(24, 10),
                near_support_threshold NUMERIC(24, 10),
                risk_reward_threshold NUMERIC(24, 10),
                created_at DATETIME,
                updated_at DATETIME,
                rule_cycle_started_at DATETIME NOT NULL
            );
            INSERT INTO instrument VALUES
                (1, 'Bitcoin', 1, 90000.1, 110000.25, 0.02, 3.5,
                 '2026-01-01', '2026-01-03', '2026-01-03');
            """
        )

    # When: application startup migrates the existing database twice.
    engine = create_database_engine(f"sqlite:///{database_path}")
    create_schema(engine)
    create_schema(engine)

    # Then: new columns exist and legacy rows default to static mode with no trailing levels.
    with sqlite3.connect(database_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(instrument)")}
        row = connection.execute(
            """
            SELECT alert_mode, high_water, fixed_drawdown, supports, resistances
            FROM instrument WHERE id = 1
            """
        ).fetchone()
    assert {"alert_mode", "high_water", "fixed_drawdown", "supports", "resistances"} <= columns
    assert "support" not in columns
    assert "resistance" not in columns
    assert row[0:3] == ("static", None, None)
    assert json_decimals(row[3]) == [Decimal("90000.1")]
    assert json_decimals(row[4]) == [Decimal("110000.25")]


def test_orm_loads_legacy_static_alert_mode_value(tmp_path: Path):
    # Given: a historical SQLite row persisted with alert_mode value 'static', not name 'STATIC'.
    database_path = tmp_path / "legacy-static-alert-mode.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE instrument (
                id INTEGER NOT NULL PRIMARY KEY,
                name VARCHAR(120) NOT NULL,
                enabled BOOLEAN NOT NULL,
                support NUMERIC(24, 10),
                resistance NUMERIC(24, 10),
                near_support_threshold NUMERIC(24, 10),
                risk_reward_threshold NUMERIC(24, 10),
                created_at DATETIME,
                updated_at DATETIME,
                rule_cycle_started_at DATETIME NOT NULL
            );
            INSERT INTO instrument VALUES
                (1, 'Bitcoin', 1, 90000.1, 110000.25, 0.02, 3.5,
                 '2026-01-01', '2026-01-03', '2026-01-03');
            """
        )

    # When: startup migrates the schema and the ORM loads instruments.
    engine = create_database_engine(f"sqlite:///{database_path}")
    create_schema(engine)
    with session_scope(engine) as session:
        instruments = list(session.exec(select(Instrument).order_by(Instrument.id)).all())

    # Then: the legacy value maps to AlertMode.STATIC without LookupError.
    assert len(instruments) == 1
    assert instruments[0].alert_mode is AlertMode.STATIC
    assert instruments[0].supports == [Decimal("90000.1")]
    assert instruments[0].resistances == [Decimal("110000.25")]
