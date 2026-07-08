from __future__ import annotations

from pathlib import Path

import pytest

from wavemonitor_backend.session_secrets import (
    load_or_create_persisted_session_secret,
    resolve_session_signing_secret,
    session_secret_path_for_database_url,
)


def test_session_secret_path_next_to_sqlite_file(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'nested' / 'wavemonitor.sqlite3'}"
    assert (
        session_secret_path_for_database_url(database_url) == tmp_path / "nested" / "session_secret"
    )


def test_session_secret_path_for_docker_sqlite() -> None:
    assert session_secret_path_for_database_url("sqlite:////data/wavemonitor.sqlite3") == Path(
        "/data/session_secret"
    )


def test_load_or_create_persisted_session_secret_is_stable(tmp_path: Path) -> None:
    secret_path = tmp_path / "session_secret"
    first = load_or_create_persisted_session_secret(secret_path)
    second = load_or_create_persisted_session_secret(secret_path)
    assert first == second
    assert len(first) >= 32


def test_resolve_session_signing_secret_prefers_env() -> None:
    assert (
        resolve_session_signing_secret(
            auth_enabled=True,
            env_session_secret="from-env",
            database_url="sqlite:////data/wavemonitor.sqlite3",
        )
        == "from-env"
    )


def test_resolve_session_signing_secret_skips_persist_when_auth_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_url = f"sqlite:///{tmp_path / 'db.sqlite3'}"
    assert (
        resolve_session_signing_secret(
            auth_enabled=False,
            env_session_secret=None,
            database_url=database_url,
        )
        is None
    )
    assert not (tmp_path / "session_secret").exists()


def test_settings_from_env_auto_persists_session_secret_when_password_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wavemonitor_backend.settings import Settings

    database_url = f"sqlite:///{tmp_path / 'wavemonitor.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("WAVEMONITOR_WEB_PASSWORD", "open-sesame")
    monkeypatch.delenv("WAVEMONITOR_SESSION_SECRET", raising=False)

    settings = Settings.from_env()
    secret_path = tmp_path / "session_secret"

    assert settings.auth_enabled is True
    assert settings.session_secret
    assert secret_path.read_text(encoding="utf-8").strip() == settings.session_secret
