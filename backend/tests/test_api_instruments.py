from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from wavemonitor_backend.app import AppRuntime, create_app
from wavemonitor_backend.db import create_database_engine, session_scope
from wavemonitor_backend.models import (
    AlertEvent,
    AlertKind,
    Instrument,
    LastRuleState,
    SourceMapping,
)
from wavemonitor_backend.notifier import TelegramSendSuccess
from wavemonitor_backend.rule_persistence import (
    evaluate_and_persist_rules,
    persist_rule_evaluation,
)
from wavemonitor_backend.rule_types import RuleEvaluation
from wavemonitor_backend.rules import RuleState
from wavemonitor_backend.settings import Settings


class FakeTelegramTransport:
    def post_json(self, url: str, payload: dict[str, str]) -> TelegramSendSuccess:
        return TelegramSendSuccess(message_id="redaction-test")


class FakeRequestingLifecycle:
    def __init__(self) -> None:
        self.tick_requests = 0

    async def run(self) -> None:
        return None

    def request_tick(self) -> None:
        self.tick_requests += 1


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
    with TestClient(
        create_app(AppRuntime(settings=Settings(), database_url=database_url))
    ) as test_client:
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


def test_create_instrument_with_support_only(client: TestClient):
    payload = VALID_PAYLOAD | {
        "support": "90000.00",
        "resistance": None,
        "risk_reward_threshold": None,
    }
    response = client.post("/api/instruments", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["support"] is not None
    assert body["resistance"] is None
    assert body["near_support_threshold"] == "0.0200000000"
    assert body["risk_reward_threshold"] is None


def test_create_support_only_instrument_requires_near_support_threshold(client: TestClient):
    payload = VALID_PAYLOAD | {
        "support": "90000.00",
        "resistance": None,
        "near_support_threshold": None,
        "risk_reward_threshold": None,
    }
    response = client.post("/api/instruments", json=payload)
    assert response.status_code == 422


def test_create_instrument_requests_immediate_monitoring_tick(tmp_path: Path):
    # Given: the API is wired to a monitoring lifecycle with an observable tick request hook.
    lifecycle = FakeRequestingLifecycle()
    database_url = f"sqlite:///{tmp_path / 'immediate.sqlite3'}"
    with TestClient(
        create_app(
            AppRuntime(
                settings=Settings(),
                database_url=database_url,
                monitoring_lifecycle=lifecycle,
            )
        )
    ) as test_client:
        # When: a valid instrument is created through the HTTP API.
        response = test_client.post("/api/instruments", json=VALID_PAYLOAD)

    # Then: the mutation commits and asks the scheduler to run without waiting for the interval.
    assert response.status_code == 201
    assert lifecycle.tick_requests == 1


def test_create_instrument_with_resistance_only(client: TestClient):
    payload = VALID_PAYLOAD | {
        "support": None,
        "resistance": "110000.00",
        "near_support_threshold": None,
        "risk_reward_threshold": None,
    }
    response = client.post("/api/instruments", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["support"] is None
    assert body["resistance"] is not None
    assert body["near_support_threshold"] is None
    assert body["risk_reward_threshold"] is None


def test_create_instrument_with_both_levels_requires_risk_reward_threshold(
    client: TestClient,
):
    payload = VALID_PAYLOAD | {"risk_reward_threshold": None}
    response = client.post("/api/instruments", json=payload)
    assert response.status_code == 422


def test_create_instrument_rejects_both_levels_null(client: TestClient):
    payload = VALID_PAYLOAD | {"support": None, "resistance": None}
    response = client.post("/api/instruments", json=payload)
    assert response.status_code == 422


def test_patch_instrument_enabled_toggles_without_full_put(client: TestClient):
    create_response = client.post("/api/instruments", json=VALID_PAYLOAD)
    assert create_response.status_code == 201
    instrument_id = create_response.json()["id"]

    pause_response = client.patch(f"/api/instruments/{instrument_id}", json={"enabled": False})
    assert pause_response.status_code == 200
    assert pause_response.json()["enabled"] is False
    assert pause_response.json()["name"] == "Bitcoin"
    assert pause_response.json()["source_mappings"][0]["enabled"] is True

    resume_response = client.patch(f"/api/instruments/{instrument_id}", json={"enabled": True})
    assert resume_response.status_code == 200
    assert resume_response.json()["enabled"] is True


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
        (
            VALID_PAYLOAD | {"source_mappings": [{"market_type": "equity", "symbol": "AAPL"}]},
            "provider",
        ),
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
            | {
                "source_mappings": [
                    {"provider": "yfinance", "market_type": "usd_m_futures", "symbol": "AAPL"}
                ]
            },
            "not supported",
        ),
        (
            VALID_PAYLOAD
            | {
                "source_mappings": [
                    {"provider": "yfinance", "market_type": "equity", "symbol": " "}
                ]
            },
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


def test_update_rule_fields_clears_last_rule_state(client: TestClient, tmp_path: Path):
    create_response = client.post("/api/instruments", json=VALID_PAYLOAD)
    assert create_response.status_code == 201
    created = create_response.json()
    instrument_id = created["id"]
    source_mapping_id = created["source_mappings"][0]["id"]

    engine = create_database_engine(f"sqlite:///{tmp_path / 'api.sqlite3'}")
    observed_at = datetime(2026, 7, 2, 4, 0, tzinfo=UTC)
    with session_scope(engine) as session:
        instrument = session.get(Instrument, instrument_id)
        assert instrument is not None
        persist_rule_evaluation(
            session=session,
            instrument_id=instrument_id,
            source_mapping_id=source_mapping_id,
            rule_cycle_started_at=instrument.rule_cycle_started_at,
            evaluation=RuleEvaluation(
                alerts=(),
                next_state=RuleState(
                    last_price=Decimal("95000"),
                    near_support_active=True,
                ),
                invalid_state=None,
            ),
            observed_at=observed_at,
        )
        session.commit()
        assert session.exec(select(LastRuleState)).all()

    update_response = client.put(
        f"/api/instruments/{instrument_id}",
        json={**VALID_PAYLOAD, "support": "89000.00"},
    )
    assert update_response.status_code == 200

    with session_scope(engine) as session:
        states = session.exec(
            select(LastRuleState).where(LastRuleState.instrument_id == instrument_id)
        ).all()
        assert states == []


def test_patch_enabled_preserves_rule_cycle(client: TestClient, tmp_path: Path):
    # Given: an instrument has an established rule-cycle boundary.
    create_response = client.post("/api/instruments", json=VALID_PAYLOAD)
    assert create_response.status_code == 201
    instrument_id = create_response.json()["id"]
    engine = create_database_engine(f"sqlite:///{tmp_path / 'api.sqlite3'}")
    with session_scope(engine) as session:
        instrument = session.get(Instrument, instrument_id)
        assert instrument is not None
        cycle_started_at = instrument.rule_cycle_started_at

    # When: monitoring is paused and resumed through PATCH.
    assert client.patch(
        f"/api/instruments/{instrument_id}", json={"enabled": False}
    ).status_code == 200
    assert client.patch(
        f"/api/instruments/{instrument_id}", json={"enabled": True}
    ).status_code == 200

    # Then: the full-edit rule cycle remains unchanged.
    with session_scope(engine) as session:
        instrument = session.get(Instrument, instrument_id)
        assert instrument is not None
        assert instrument.rule_cycle_started_at == cycle_started_at


def test_update_starts_new_crossing_cycle(client: TestClient, tmp_path: Path):
    # Given: the instrument already has a support-breach event from its current edit cycle.
    create_response = client.post("/api/instruments", json=VALID_PAYLOAD)
    assert create_response.status_code == 201
    created = create_response.json()
    instrument_id = created["id"]
    source_mapping_id = created["source_mappings"][0]["id"]

    engine = create_database_engine(f"sqlite:///{tmp_path / 'api.sqlite3'}")
    old_triggered_at = datetime(2026, 7, 2, 4, 0, tzinfo=UTC)
    with session_scope(engine) as session:
        session.add(
            AlertEvent(
                instrument_id=instrument_id,
                source_mapping_id=source_mapping_id,
                alert_kind=AlertKind.SUPPORT_BREACH,
                price=Decimal("89000"),
                support=Decimal("90000.10"),
                resistance=Decimal("110000.25"),
                threshold=Decimal("90000.10"),
                message="old cycle breach",
                triggered_at=old_triggered_at,
            )
        )
        session.commit()

    # When: the instrument is edited and the same source breaches support again.
    update_response = client.put(
        f"/api/instruments/{instrument_id}",
        json={**VALID_PAYLOAD, "name": "Bitcoin renamed"},
    )
    assert update_response.status_code == 200
    with session_scope(engine) as session:
        old_event = session.exec(
            select(AlertEvent).where(
                AlertEvent.instrument_id == instrument_id,
                AlertEvent.alert_kind == AlertKind.SUPPORT_BREACH,
            )
        ).one()
        assert old_event.triggered_at == old_triggered_at.replace(tzinfo=None)

    new_triggered_at = datetime.now(UTC)
    with session_scope(engine) as session:
        instrument = session.get(Instrument, instrument_id)
        source = session.get(SourceMapping, source_mapping_id)
        assert instrument is not None
        assert source is not None
        evaluation = evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=Decimal("89000"),
            observed_at=new_triggered_at,
        )
        stored_events = session.exec(
            select(AlertEvent)
            .where(
                AlertEvent.instrument_id == instrument_id,
                AlertEvent.alert_kind == AlertKind.SUPPORT_BREACH,
            )
            .order_by(AlertEvent.triggered_at)
        ).all()

    # Then: the post-edit breach is emitted while the previous cycle remains historical.
    assert [alert.kind for alert in evaluation.alerts] == [AlertKind.SUPPORT_BREACH]
    assert [event.triggered_at for event in stored_events] == [
        old_triggered_at.replace(tzinfo=None),
        new_triggered_at.replace(tzinfo=None),
    ]
    assert stored_events[-1].price == Decimal("89000.0000000000")


def test_pre_cycle_observation_does_not_replace_crossing_event(
    client: TestClient, tmp_path: Path
):
    # Given: a completed edit cycle still retains its previous support-breach marker.
    create_response = client.post("/api/instruments", json=VALID_PAYLOAD)
    assert create_response.status_code == 201
    created = create_response.json()
    instrument_id = created["id"]
    source_mapping_id = created["source_mappings"][0]["id"]
    engine = create_database_engine(f"sqlite:///{tmp_path / 'api.sqlite3'}")
    old_triggered_at = datetime(2026, 7, 2, 4, 0, tzinfo=UTC)
    with session_scope(engine) as session:
        session.add(
            AlertEvent(
                instrument_id=instrument_id,
                source_mapping_id=source_mapping_id,
                alert_kind=AlertKind.SUPPORT_BREACH,
                price=Decimal("89000"),
                support=Decimal("90000.10"),
                resistance=Decimal("110000.25"),
                threshold=Decimal("90000.10"),
                message="old cycle breach",
                triggered_at=old_triggered_at,
            )
        )
        session.commit()

    update_response = client.put(
        f"/api/instruments/{instrument_id}",
        json={**VALID_PAYLOAD, "name": "Bitcoin renamed"},
    )
    assert update_response.status_code == 200

    # When: a delayed quote from before the new cycle is evaluated afterward.
    with session_scope(engine) as session:
        instrument = session.get(Instrument, instrument_id)
        source = session.get(SourceMapping, source_mapping_id)
        assert instrument is not None
        assert source is not None
        evaluation = evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=Decimal("89000"),
            observed_at=old_triggered_at,
        )
        stored_event = session.exec(
            select(AlertEvent).where(
                AlertEvent.instrument_id == instrument_id,
                AlertEvent.alert_kind == AlertKind.SUPPORT_BREACH,
            )
        ).one()
        states = session.exec(
            select(LastRuleState).where(LastRuleState.instrument_id == instrument_id)
        ).all()

    # Then: no alert is emitted and the old marker remains untouched.
    assert evaluation.alerts == ()
    assert stored_event.triggered_at == old_triggered_at.replace(tzinfo=None)
    assert states == []


def test_update_name_only_preserves_last_rule_state(client: TestClient, tmp_path: Path):
    create_response = client.post("/api/instruments", json=VALID_PAYLOAD)
    assert create_response.status_code == 201
    created = create_response.json()
    instrument_id = created["id"]
    source_mapping_id = created["source_mappings"][0]["id"]

    engine = create_database_engine(f"sqlite:///{tmp_path / 'api.sqlite3'}")
    observed_at = datetime(2026, 7, 2, 4, 0, tzinfo=UTC)
    with session_scope(engine) as session:
        instrument = session.get(Instrument, instrument_id)
        assert instrument is not None
        persist_rule_evaluation(
            session=session,
            instrument_id=instrument_id,
            source_mapping_id=source_mapping_id,
            rule_cycle_started_at=instrument.rule_cycle_started_at,
            evaluation=RuleEvaluation(
                alerts=(),
                next_state=RuleState(last_price=Decimal("95000"), near_support_active=True),
                invalid_state=None,
            ),
            observed_at=observed_at,
        )
        session.commit()

    update_response = client.put(
        f"/api/instruments/{instrument_id}",
        json={**VALID_PAYLOAD, "name": "Bitcoin renamed"},
    )
    assert update_response.status_code == 200

    with session_scope(engine) as session:
        state = session.exec(
            select(LastRuleState).where(LastRuleState.instrument_id == instrument_id)
        ).one()
        assert state.near_support_active is True


def test_create_instrument_normalizes_hyperliquid_colon_symbol_like_models(client: TestClient):
    payload = VALID_PAYLOAD | {
        "name": "CRCL HIP-3",
        "source_mappings": [
            {
                "provider": "hyperliquid",
                "market_type": "perpetual",
                "symbol": "XYZ:crcl",
                "enabled": True,
            }
        ],
    }
    response = client.post("/api/instruments", json=payload)

    assert response.status_code == 201
    assert response.json()["source_mappings"][0]["symbol"] == "xyz:CRCL"
