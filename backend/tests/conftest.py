from __future__ import annotations

import os

import pytest


def pytest_configure() -> None:
    os.environ.setdefault("WAVEMONITOR_MONITORING_DISABLED", "1")


@pytest.fixture(autouse=True)
def disable_default_monitoring_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WAVEMONITOR_MONITORING_DISABLED", "1")
