from collections.abc import Iterator
from contextlib import contextmanager
from os import getenv
from typing import Final

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine


DATABASE_URL_ENV: Final[str] = "DATABASE_URL"
LOCAL_SQLITE_DATABASE_URL: Final[str] = "sqlite:///./wavemonitor.sqlite3"
DEFAULT_DATABASE_URL: Final[str] = LOCAL_SQLITE_DATABASE_URL


def database_url_from_env() -> str:
    return getenv(DATABASE_URL_ENV, LOCAL_SQLITE_DATABASE_URL)


def create_database_engine(database_url: str) -> Engine:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def create_schema(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
