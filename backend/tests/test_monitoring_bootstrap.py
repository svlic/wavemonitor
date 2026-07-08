from __future__ import annotations

import pytest

import wavemonitor_backend.monitoring_bootstrap as bootstrap


def test_default_poll_interval_is_two_minutes() -> None:
    assert bootstrap.DEFAULT_POLL_INTERVAL_SECONDS == 120.0


def test_poll_interval_seconds_from_env_uses_default_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(bootstrap.POLL_INTERVAL_SECONDS_ENV, raising=False)
    assert bootstrap.poll_interval_seconds_from_env() == 120.0


def test_poll_interval_seconds_from_env_parses_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(bootstrap.POLL_INTERVAL_SECONDS_ENV, "30")
    assert bootstrap.poll_interval_seconds_from_env() == 30.0
