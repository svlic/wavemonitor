from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Final

import pytest
from fastapi.testclient import TestClient

from wavemonitor_backend.app import AppRuntime, create_app
from wavemonitor_backend.notifier import TelegramSendSuccess
from wavemonitor_backend.settings import Settings


class FakeTelegramTransport:
    def post_json(self, url: str, payload: dict[str, str]) -> TelegramSendSuccess:
        return TelegramSendSuccess(message_id="redaction-test")


VALID_PAYLOAD: Final[dict[str, str | bool | list[dict[str, str | bool]]]] = {
    "name": "Bitcoin",
    "enabled": True,
    "support": "90000.10",
    "resistance": "110000.25",
    "near_support_threshold": "0.02",
    "risk_reward_threshold": "3.5",
    "source_mappings": [
        {
            "provider": "binance",
            "market_type": "usd_m_futures",
            "symbol": "btcusdt",
            "enabled": True,
        }
    ],
}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    # Given: each test owns an isolated SQLite database.
    database_url = f"sqlite:///{tmp_path / 'api.sqlite3'}"
    with TestClient(create_app(AppRuntime(settings=Settings(), database_url=database_url))) as test_client:
        yield test_client


def test_create_list_update_delete_instrument_with_temp_sqlite(client: TestClient):
    # Given: a valid instrument request with one source mapping.
    # When: the instrument is created, listed, updated, and deleted.
    create_response = client.post("/api/instruments", json=VALID_PAYLOAD)
    created = create_response.json()
    instrument_id = created["id"]
    update_response = client.put(
        f"/api/instruments/{instrument_id}",
        json={
            "name": "Bitcoin long setup",
            "enabled": False,
            "support": "91000.00",
            "resistance": "111000.00",
            "near_support_threshold": "0.03",
            "risk_reward_threshold": "4.0",
            "source_mappings": [
                {
                    "provider": "binance",
                    "market_type": "usd_m_futures",
                    "symbol": "BTCUSDT",
                    "enabled": False,
                }
            ],
        },
    )
    list_response = client.get("/api/instruments")
    delete_response = client.delete(f"/api/instruments/{instrument_id}")
    list_after_delete = client.get("/api/instruments")

    # Then: database-backed CRUD preserves API decimal strings and source identity.
    assert create_response.status_code == 201
    assert created["support"] == "90000.1000000000"
    assert created["resistance"] == "110000.2500000000"
    assert created["source_mappings"] == [
        {
            "id": 1,
            "provider": "binance",
            "market_type": "usd_m_futures",
            "symbol": "BTCUSDT",
            "enabled": True,
        }
    ]
    assert update_response.status_code == 200
    assert update_response.json()["enabled"] is False
    assert update_response.json()["source_mappings"][0]["enabled"] is False
    assert list_response.status_code == 200
    assert list_response.json()[0]["name"] == "Bitcoin long setup"
    assert delete_response.status_code == 204
    assert list_after_delete.json() == []


def test_enabled_and_disabled_source_mappings_round_trip(client: TestClient):
    # Given: one instrument configured with active and inactive sources.
    payload = VALID_PAYLOAD | {
        "source_mappings": [
            {
                "provider": "binance",
                "market_type": "usd_m_futures",
                "symbol": "BTCUSDT",
                "enabled": True,
            },
            {
                "provider": "hyperliquid",
                "market_type": "perpetual",
                "symbol": "btc",
                "enabled": False,
            },
        ]
    }

    # When: the instrument is stored and fetched by list.
    create_response = client.post("/api/instruments", json=payload)
    list_response = client.get("/api/instruments")

    # Then: both source mappings are persisted with their enabled flags and identity.
    assert create_response.status_code == 201
    sources = list_response.json()[0]["source_mappings"]
    assert sources == [
        {
            "id": 1,
            "provider": "binance",
            "market_type": "usd_m_futures",
            "symbol": "BTCUSDT",
            "enabled": True,
        },
        {
            "id": 2,
            "provider": "hyperliquid",
            "market_type": "perpetual",
            "symbol": "BTC",
            "enabled": False,
        },
    ]


def test_status_endpoint_reports_sources_and_recent_alerts(client: TestClient):
    # Given: one persisted instrument and no rule engine alerts yet.
    create_response = client.post("/api/instruments", json=VALID_PAYLOAD)
    instrument_id = create_response.json()["id"]

    # When: its status endpoint is requested.
    response = client.get(f"/api/instruments/{instrument_id}/status")

    # Then: status is database-backed and includes runtime-safe empty alert state.
    assert response.status_code == 200
    assert response.json() == {
        "instrument_id": instrument_id,
        "enabled": True,
        "sources": [
            {
                "id": 1,
                "provider": "binance",
                "market_type": "usd_m_futures",
                "symbol": "BTCUSDT",
                "enabled": True,
                "last_price": None,
                "last_observed_at": None,
                "last_error": None,
                "last_invalid_state": None,
            }
        ],
        "recent_alerts": [],
    }


def test_health_runtime_recent_alerts_and_telegram_test_redact_secrets(tmp_path: Path):
    # Given: runtime Telegram settings contain raw secrets.
    database_url = f"sqlite:///{tmp_path / 'redaction.sqlite3'}"
    settings = Settings(telegram_bot_token="123456:secret-token", telegram_chat_id="-100987654321")
    with TestClient(
        create_app(
            AppRuntime(
                settings=settings,
                database_url=database_url,
                telegram_transport=FakeTelegramTransport(),
            )
        )
    ) as client:
        # When: runtime/status endpoints are called.
        health_response = client.get("/health")
        runtime_response = client.get("/api/runtime")
        alerts_response = client.get("/api/alerts")
        telegram_response = client.post("/api/telegram/test")

    # Then: readiness is exposed without raw token/chat-id persistence or exposure.
    combined_output = " ".join(
        str(payload)
        for payload in (
            health_response.json(),
            runtime_response.json(),
            alerts_response.json(),
            telegram_response.json(),
        )
    )
    assert health_response.json() == {"status": "ok", "telegram_ready": True}
    assert runtime_response.json() == {
        "scheduler_ready": False,
        "providers_ready": False,
        "telegram_ready": True,
        "enabled_sources": 0,
        "polled_sources": 0,
        "observations_written": 0,
        "source_errors": 0,
        "alert_events_created": 0,
        "telegram_deliveries_attempted": 0,
        "last_tick_started_at": None,
        "last_tick_finished_at": None,
    }
    assert alerts_response.json() == []
    assert telegram_response.status_code == 200
    assert telegram_response.json() == {
        "sent": True,
        "telegram_ready": True,
        "detail": "Telegram test message delivered.",
        "delivery_id": 1,
    }
    assert "123456:secret-token" not in combined_output
    assert "-100987654321" not in combined_output


@pytest.mark.parametrize(
    ("payload", "expected_fragment"),
    [
        (VALID_PAYLOAD | {"source_mappings": [{"market_type": "equity", "symbol": "AAPL"}]}, "provider"),
        (
            VALID_PAYLOAD
            | {
                "source_mappings": [
                    {"provider": "unsupported", "market_type": "equity", "symbol": "AAPL"}
                ]
            },
            "provider",
        ),
        (
            VALID_PAYLOAD
            | {"source_mappings": [{"provider": "yfinance", "market_type": "equity", "symbol": " "}]},
            "symbol",
        ),
        (VALID_PAYLOAD | {"near_support_threshold": "1.5"}, "near_support_threshold"),
        (VALID_PAYLOAD | {"support": "100", "resistance": "100"}, "support must be less"),
        (VALID_PAYLOAD | {"source_mappings": []}, "source_mappings"),
    ],
)
def test_create_instrument_validation_errors(
    client: TestClient,
    payload: dict[str, str | bool | list[dict[str, str | bool]]],
    expected_fragment: str,
):
    # Given: malformed input crossing the API boundary.
    # When: create is attempted.
    response = client.post("/api/instruments", json=payload)

    # Then: the API rejects it without misleading success output.
    assert response.status_code in {400, 422}
    assert expected_fragment in response.text


def test_create_without_source_mapping_fails(client: TestClient):
    # Given: an otherwise valid instrument with no source mapping configured.
    payload = VALID_PAYLOAD | {"source_mappings": []}

    # When: create is attempted.
    response = client.post("/api/instruments", json=payload)

    # Then: Todo 4 requires a 400/422 failure rather than a disabled monitor shell.
    assert response.status_code in {400, 422}
    assert response.json()["detail"]


def test_create_duplicate_source_mapping_rolls_back_instrument(client: TestClient):
    # Given: one create request contains two source mappings with the same database identity.
    payload = VALID_PAYLOAD | {
        "source_mappings": [
            {
                "provider": "binance",
                "market_type": "usd_m_futures",
                "symbol": "BTCUSDT",
                "enabled": True,
            },
            {
                "provider": "binance",
                "market_type": "usd_m_futures",
                "symbol": "btcusdt",
                "enabled": False,
            },
        ]
    }

    # When: create is attempted and the source mapping uniqueness constraint rejects it.
    response = client.post("/api/instruments", json=payload)
    list_response = client.get("/api/instruments")

    # Then: the API reports a create conflict and leaves no empty instrument shell behind.
    assert response.status_code == 409
    assert response.json()["detail"] == "Source mapping already exists"
    assert list_response.json() == []


def test_two_instruments_may_share_same_source_identity(client: TestClient):
    first = client.post("/api/instruments", json=VALID_PAYLOAD)
    assert first.status_code == 201
    second_payload = VALID_PAYLOAD | {"name": "Bitcoin alt strategy"}
    second = client.post("/api/instruments", json=second_payload)
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    listed = client.get("/api/instruments").json()
    assert len(listed) == 2
    assert {row["name"] for row in listed} == {"Bitcoin", "Bitcoin alt strategy"}


def test_update_duplicate_source_mapping_returns_409_without_partial_commit(client: TestClient):
    create_payload = VALID_PAYLOAD | {
        "source_mappings": [
            {
                "provider": "hyperliquid",
                "market_type": "perpetual",
                "symbol": "BTC",
                "enabled": True,
            }
        ]
    }
    create_response = client.post("/api/instruments", json=create_payload)
    instrument_id = create_response.json()["id"]
    update_payload = create_payload | {
        "name": "Should not persist",
        "source_mappings": [
            {
                "provider": "binance",
                "market_type": "usd_m_futures",
                "symbol": "BTCUSDT",
                "enabled": True,
            },
            {
                "provider": "binance",
                "market_type": "usd_m_futures",
                "symbol": "btcusdt",
                "enabled": False,
            },
        ],
    }
    update_response = client.put(f"/api/instruments/{instrument_id}", json=update_payload)
    listed = client.get("/api/instruments").json()
    row = next(item for item in listed if item["id"] == instrument_id)

    assert update_response.status_code == 409
    assert update_response.json()["detail"] == "Source mapping already exists"
    assert row["name"] == "Bitcoin"
    assert len(row["source_mappings"]) == 1
    assert row["source_mappings"][0]["provider"] == "hyperliquid"
