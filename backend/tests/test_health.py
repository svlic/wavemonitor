from fastapi.testclient import TestClient

from wavemonitor_backend.app import create_app


def test_health_reports_ok_and_telegram_not_ready_when_env_missing(monkeypatch):
    # Given: optional Telegram credentials are absent.
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    client = TestClient(create_app())

    # When: the health endpoint is requested.
    response = client.get("/health")

    # Then: the app stays healthy while reporting Telegram readiness as false.
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "telegram_ready": False,
    }


def test_api_contract_stub_exposes_mvp_paths():
    # Given: the app is created from the checked-in contract skeleton.
    client = TestClient(create_app())

    # When: OpenAPI is requested.
    response = client.get("/openapi.json")

    # Then: all Todo 1 contract paths are present for later implementation todos.
    assert response.status_code == 200
    paths = set(response.json()["paths"])
    assert {
        "/health",
        "/api/instruments",
        "/api/instruments/{instrument_id}",
        "/api/instruments/{instrument_id}/status",
        "/api/alerts",
        "/api/runtime",
        "/api/telegram/test",
    }.issubset(paths)
