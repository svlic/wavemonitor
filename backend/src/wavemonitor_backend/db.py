from collections.abc import Iterator
from contextlib import contextmanager
from os import getenv
from typing import Final

from sqlalchemy import Engine
from sqlalchemy.engine import Connection
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL_ENV: Final[str] = "DATABASE_URL"
LOCAL_SQLITE_DATABASE_URL: Final[str] = "sqlite:///./wavemonitor.sqlite3"
DEFAULT_DATABASE_URL: Final[str] = LOCAL_SQLITE_DATABASE_URL


INSTRUMENT_COLUMNS: Final[str] = """
    id, name, enabled, support, resistance, near_support_threshold,
    risk_reward_threshold, created_at, updated_at
"""
SOURCE_MAPPING_COLUMNS: Final[str] = """
    id, instrument_id, provider, market_type, symbol, enabled
"""


def database_url_from_env() -> str:
    return getenv(DATABASE_URL_ENV, LOCAL_SQLITE_DATABASE_URL)


def create_database_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def create_schema(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
    if engine.dialect.name == "sqlite":
        with engine.begin() as connection:
            migrate_sqlite_schema(connection)


def migrate_sqlite_schema(connection: Connection) -> None:
    if _sqlite_column_is_not_null(connection, "instrument", "support"):
        _rebuild_sqlite_instrument_table(connection)
    if _sqlite_column_is_not_null(connection, "instrument", "resistance"):
        _rebuild_sqlite_instrument_table(connection)
    source_mapping_sql = _sqlite_table_sql(connection, "sourcemapping")
    if source_mapping_sql is not None and (
        "uq_source_mapping_identity" in source_mapping_sql
        or "uq_source_mapping_per_instrument" not in source_mapping_sql
    ):
        _rebuild_sqlite_source_mapping_table(connection)


def _sqlite_table_sql(connection: Connection, table_name: str) -> str | None:
    row = connection.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return None if row is None else str(row[0])


def _sqlite_column_is_not_null(connection: Connection, table_name: str, column_name: str) -> bool:
    rows = connection.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
    return any(str(row[1]) == column_name and int(row[3]) == 1 for row in rows)


def _rebuild_sqlite_instrument_table(connection: Connection) -> None:
    connection.exec_driver_sql("DROP TABLE IF EXISTS instrument_new")
    connection.exec_driver_sql(
        """
        CREATE TABLE instrument_new (
            id INTEGER NOT NULL,
            name VARCHAR(120) NOT NULL,
            enabled BOOLEAN NOT NULL,
            support NUMERIC(24, 10),
            resistance NUMERIC(24, 10),
            near_support_threshold NUMERIC(24, 10) NOT NULL,
            risk_reward_threshold NUMERIC(24, 10) NOT NULL,
            created_at DATETIME,
            updated_at DATETIME,
            PRIMARY KEY (id)
        )
        """
    )
    connection.exec_driver_sql(
        f"INSERT INTO instrument_new ({INSTRUMENT_COLUMNS}) "
        f"SELECT {INSTRUMENT_COLUMNS} FROM instrument"
    )
    connection.exec_driver_sql("DROP TABLE instrument")
    connection.exec_driver_sql("ALTER TABLE instrument_new RENAME TO instrument")
    connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_instrument_name ON instrument (name)")


def _rebuild_sqlite_source_mapping_table(connection: Connection) -> None:
    connection.exec_driver_sql("DROP TABLE IF EXISTS sourcemapping_new")
    connection.exec_driver_sql(
        """
        CREATE TABLE sourcemapping_new (
            id INTEGER NOT NULL,
            instrument_id INTEGER NOT NULL,
            provider VARCHAR(11) NOT NULL,
            market_type VARCHAR(13) NOT NULL,
            symbol VARCHAR(80) NOT NULL,
            enabled BOOLEAN NOT NULL,
            PRIMARY KEY (id),
            CONSTRAINT uq_source_mapping_per_instrument UNIQUE (
                instrument_id, provider, market_type, symbol
            ),
            FOREIGN KEY(instrument_id) REFERENCES instrument (id)
        )
        """
    )
    connection.exec_driver_sql(
        f"INSERT INTO sourcemapping_new ({SOURCE_MAPPING_COLUMNS}) "
        f"SELECT {SOURCE_MAPPING_COLUMNS} FROM sourcemapping"
    )
    connection.exec_driver_sql("DROP TABLE sourcemapping")
    connection.exec_driver_sql("ALTER TABLE sourcemapping_new RENAME TO sourcemapping")
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_sourcemapping_instrument_id ON sourcemapping (instrument_id)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_sourcemapping_market_type ON sourcemapping (market_type)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_sourcemapping_provider ON sourcemapping (provider)"
    )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_sourcemapping_symbol ON sourcemapping (symbol)"
    )


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
