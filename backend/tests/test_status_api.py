from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from wavemonitor_backend.app import AppRuntime, create_app
from wavemonitor_backend.db import create_database_engine, create_schema, session_scope
from wavemonitor_backend.models import (
    AlertEvent,
    AlertKind,
    Instrument,
    MarketType,
    PriceObservation,
    Provider,
    SourceMapping,
)
from wavemonitor_backend.monitoring import RuntimeMetrics, RuntimeMetricsStore
from wavemonitor_backend.settings import Settings

BASE_TIME: Final[datetime] = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    # Given: each status API test owns an isolated SQLite database.
    engine = create_database_engine(f"sqlite:///{tmp_path / 'status-api.sqlite3'}")
    create_schema(engine)
    with session_scope(engine) as db_session:
        yield db_session


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    # Given: the API runs against an isolated empty SQLite database.
    database_url = f"sqlite:///{tmp_path / 'status-api-client.sqlite3'}"
    with TestClient(
        create_app(AppRuntime(settings=Settings(), database_url=database_url))
    ) as test_client:
        yield test_client


def seed_operational_rows(session: Session) -> None:
    instrument = Instrument(
        name="Bitcoin",
        supports=[Decimal("98")],
        resistances=[Decimal("130")],
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
    session.add(instrument)
    session.commit()
    session.refresh(instrument)
    source = SourceMapping(
        instrument_id=instrument.id,
        provider=Provider.BINANCE,
        market_type=MarketType.USD_M_FUTURES,
        symbol="BTCUSDT",
    )
    failing_source = SourceMapping(
        instrument_id=instrument.id,
        provider=Provider.YFINANCE,
        market_type=MarketType.EQUITY,
        symbol="BTC",
    )
    session.add(source)
    session.add(failing_source)
    session.commit()
    session.refresh(source)
    session.refresh(failing_source)
    session.add(
        PriceObservation(
            source_mapping_id=source.id,
            price=Decimal("100"),
            observed_at=BASE_TIME,
            raw_path="fake.price",
        )
    )
    session.add(
        PriceObservation(
            source_mapping_id=failing_source.id,
            price=Decimal("0"),
            observed_at=BASE_TIME,
            error="provider_error: provider down",
        )
    )
    session.add(
        AlertEvent(
            instrument_id=instrument.id,
            source_mapping_id=source.id,
            alert_kind=AlertKind.NEAR_SUPPORT,
            price=Decimal("100"),
            support=Decimal("98"),
            resistance=Decimal("130"),
            threshold=Decimal("0.02"),
            message="Bitcoin is near support on binance:usd_m_futures:BTCUSDT",
            triggered_at=BASE_TIME,
        )
    )
    session.commit()


def test_operational_surfaces_expose_runtime_latest_alerts_and_source_errors(
    tmp_path: Path, session: Session
):
    # Given: scheduler metrics and operational persistence rows exist.
    seed_operational_rows(session)
    metrics_store = RuntimeMetricsStore()
    metrics_store.update(
        RuntimeMetrics(
            scheduler_ready=True,
            providers_ready=False,
            enabled_sources=2,
            polled_sources=2,
            observations_written=1,
            source_errors=1,
            alert_events_created=1,
            telegram_deliveries_attempted=0,
            last_tick_started_at=BASE_TIME,
            last_tick_finished_at=BASE_TIME,
        )
    )
    database_url = f"sqlite:///{tmp_path / 'status-api.sqlite3'}"
    with TestClient(
        create_app(
            AppRuntime(settings=Settings(), database_url=database_url, metrics_store=metrics_store)
        )
    ) as test_client:
        # When: operational read endpoints are queried.
        health_response = test_client.get("/health")
        runtime_response = test_client.get("/api/runtime")
        latest_response = test_client.get("/api/prices/latest")
        alerts_response = test_client.get("/api/alerts")
        errors_response = test_client.get("/api/source-errors")

    # Then: safe scheduler state, latest prices, recent alerts, and source errors are exposed.
    assert health_response.json() == {"status": "ok", "telegram_ready": False}
    assert runtime_response.json()["scheduler_ready"] is True
    assert runtime_response.json()["providers_ready"] is False
    assert runtime_response.json()["source_errors"] == 1
    assert latest_response.status_code == 200
    assert latest_response.json() == [
        {
            "instrument_id": 1,
            "instrument_name": "Bitcoin",
            "source_mapping_id": 1,
            "provider": "binance",
            "market_type": "usd_m_futures",
            "symbol": "BTCUSDT",
            "last_price": "100.0000000000",
            "last_observed_at": "2026-06-30T12:00:00",
            "last_error": None,
            "support_breached": False,
            "resistance_broken": False,
        }
    ]
    assert alerts_response.status_code == 200
    assert (
        alerts_response.json()[0]["message"]
        == "Bitcoin is near support on binance:usd_m_futures:BTCUSDT"
    )
    assert errors_response.status_code == 200
    assert errors_response.json() == [
        {
            "instrument_id": 1,
            "instrument_name": "Bitcoin",
            "source_mapping_id": 2,
            "provider": "yfinance",
            "market_type": "equity",
            "symbol": "BTC",
            "last_observed_at": "2026-06-30T12:00:00",
            "last_error": "provider_error: provider down",
        }
    ]


def test_latest_prices_marks_only_crossings_after_last_instrument_edit(
    tmp_path: Path, session: Session
):
    # Given: one source crossed both levels before its instrument's latest edit.
    seed_operational_rows(session)
    instrument = session.exec(select(Instrument)).one()
    source = session.exec(
        select(SourceMapping).where(SourceMapping.provider == Provider.BINANCE)
    ).one()
    for kind in (AlertKind.SUPPORT_BREACH, AlertKind.RESISTANCE_BREAKOUT):
        session.add(
            AlertEvent(
                instrument_id=instrument.id,
                source_mapping_id=source.id,
                alert_kind=kind,
                price=Decimal("100"),
                support=Decimal("98"),
                resistance=Decimal("130"),
                threshold=Decimal("98") if kind == AlertKind.SUPPORT_BREACH else Decimal("130"),
                message=kind.value,
                triggered_at=BASE_TIME,
                rule_cycle_started_at=BASE_TIME,
            )
        )
    new_cycle = datetime(2026, 6, 30, 12, 1, tzinfo=UTC)
    instrument.updated_at = new_cycle
    instrument.rule_cycle_started_at = new_cycle
    session.add(instrument)
    session.add(
        AlertEvent(
            instrument_id=instrument.id,
            source_mapping_id=source.id,
            alert_kind=AlertKind.RESISTANCE_BREAKOUT,
            price=Decimal("131"),
            support=Decimal("98"),
            resistance=Decimal("130"),
            threshold=Decimal("130"),
            message="new cycle breakout",
            triggered_at=datetime(2026, 6, 30, 12, 2, tzinfo=UTC),
            rule_cycle_started_at=new_cycle,
        )
    )
    session.commit()

    # When: latest prices are requested after a new-cycle resistance breakout.
    database_url = f"sqlite:///{tmp_path / 'status-api.sqlite3'}"
    with TestClient(
        create_app(AppRuntime(settings=Settings(), database_url=database_url))
    ) as test_client:
        response = test_client.get("/api/prices/latest")

    # Then: only the post-edit crossing is marked and the latest price is unchanged.
    assert response.status_code == 200
    row = response.json()[0]
    assert row["last_price"] == "100.0000000000"
    assert row["support_breached"] is False
    assert row["resistance_broken"] is True


def test_source_errors_omit_disabled_instrument_and_source(tmp_path: Path, session: Session):
    seed_operational_rows(session)
    failing_source = session.exec(
        select(SourceMapping).where(
            SourceMapping.symbol == "BTC", SourceMapping.provider == Provider.YFINANCE
        )
    ).one()
    failing_source.enabled = False
    session.add(failing_source)
    session.commit()

    database_url = f"sqlite:///{tmp_path / 'status-api.sqlite3'}"
    with TestClient(
        create_app(AppRuntime(settings=Settings(), database_url=database_url))
    ) as test_client:
        errors_response = test_client.get("/api/source-errors")

    assert errors_response.status_code == 200
    assert errors_response.json() == []


def test_latest_observation_tie_breaks_on_highest_id(tmp_path: Path, session: Session):
    instrument = Instrument(
        name="Tie break",
        supports=[Decimal("98")],
        resistances=[Decimal("130")],
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
    session.add(instrument)
    session.commit()
    session.refresh(instrument)
    source = SourceMapping(
        instrument_id=instrument.id,
        provider=Provider.BINANCE,
        market_type=MarketType.USD_M_FUTURES,
        symbol="BTCUSDT",
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    session.add(
        PriceObservation(
            source_mapping_id=source.id,
            price=Decimal("99"),
            observed_at=BASE_TIME,
            raw_path="older",
        )
    )
    session.add(
        PriceObservation(
            source_mapping_id=source.id,
            price=Decimal("101"),
            observed_at=BASE_TIME,
            raw_path="newer",
        )
    )
    session.commit()

    database_url = f"sqlite:///{tmp_path / 'status-api.sqlite3'}"
    with TestClient(
        create_app(AppRuntime(settings=Settings(), database_url=database_url))
    ) as test_client:
        response = test_client.get("/api/prices/latest")

    assert response.status_code == 200
    assert response.json()[0]["last_price"] == "101.0000000000"
    assert response.json()[0]["source_mapping_id"] == source.id


def test_latest_prices_keep_last_success_after_newer_source_error(tmp_path: Path, session: Session):
    # Given: one enabled source has an older successful price and a newer provider error.
    instrument = Instrument(
        name="Bitcoin",
        supports=[Decimal("98")],
        resistances=[Decimal("130")],
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
    session.add(instrument)
    session.commit()
    session.refresh(instrument)
    source = SourceMapping(
        instrument_id=instrument.id,
        provider=Provider.BINANCE,
        market_type=MarketType.USD_M_FUTURES,
        symbol="BTCUSDT",
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    session.add(
        PriceObservation(
            source_mapping_id=source.id,
            price=Decimal("100"),
            observed_at=BASE_TIME,
            raw_path="success.price",
        )
    )
    session.add(
        PriceObservation(
            source_mapping_id=source.id,
            price=Decimal("0"),
            observed_at=datetime(2026, 6, 30, 12, 1, tzinfo=UTC),
            error="provider_error: provider down",
        )
    )
    session.commit()

    database_url = f"sqlite:///{tmp_path / 'status-api.sqlite3'}"
    with TestClient(
        create_app(AppRuntime(settings=Settings(), database_url=database_url))
    ) as test_client:
        response = test_client.get("/api/prices/latest")

    # Then: the latest prices endpoint reports the last successful price, not the newer error row.
    assert response.status_code == 200
    assert response.json() == [
        {
            "instrument_id": instrument.id,
            "instrument_name": "Bitcoin",
            "source_mapping_id": source.id,
            "provider": "binance",
            "market_type": "usd_m_futures",
            "symbol": "BTCUSDT",
            "last_price": "100.0000000000",
            "last_observed_at": "2026-06-30T12:00:00",
            "last_error": None,
            "support_breached": False,
            "resistance_broken": False,
        }
    ]


def test_instrument_status_keeps_last_success_after_newer_source_error(
    tmp_path: Path, session: Session
):
    # Given: one enabled source has an older successful price and a newer provider error.
    instrument = Instrument(
        name="Bitcoin",
        supports=[Decimal("98")],
        resistances=[Decimal("130")],
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
    session.add(instrument)
    session.commit()
    session.refresh(instrument)
    source = SourceMapping(
        instrument_id=instrument.id,
        provider=Provider.BINANCE,
        market_type=MarketType.USD_M_FUTURES,
        symbol="BTCUSDT",
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    session.add(
        PriceObservation(
            source_mapping_id=source.id,
            price=Decimal("100"),
            observed_at=BASE_TIME,
            raw_path="success.price",
        )
    )
    session.add(
        PriceObservation(
            source_mapping_id=source.id,
            price=Decimal("0"),
            observed_at=datetime(2026, 6, 30, 12, 1, tzinfo=UTC),
            error="provider_error: provider down",
        )
    )
    session.commit()

    database_url = f"sqlite:///{tmp_path / 'status-api.sqlite3'}"
    with TestClient(
        create_app(AppRuntime(settings=Settings(), database_url=database_url))
    ) as test_client:
        response = test_client.get(f"/api/instruments/{instrument.id}/status")

    # Then: source status preserves the last successful price while also exposing the latest error.
    assert response.status_code == 200
    source_status = response.json()["sources"][0]
    assert source_status["last_price"] == "100.0000000000"
    assert source_status["last_observed_at"] == "2026-06-30T12:00:00"
    assert source_status["last_error"] == "provider_error: provider down"


def test_latest_prices_omit_disabled_instruments_and_sources(tmp_path: Path, session: Session):
    enabled_instrument = Instrument(
        name="Active",
        enabled=True,
        supports=[Decimal("98")],
        resistances=[Decimal("130")],
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
    paused_instrument = Instrument(
        name="Paused",
        enabled=False,
        supports=[Decimal("1")],
        resistances=[Decimal("2")],
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
    session.add(enabled_instrument)
    session.add(paused_instrument)
    session.commit()
    session.refresh(enabled_instrument)
    session.refresh(paused_instrument)
    active_source = SourceMapping(
        instrument_id=enabled_instrument.id,
        provider=Provider.BINANCE,
        market_type=MarketType.USD_M_FUTURES,
        symbol="ETHUSDT",
        enabled=True,
    )
    disabled_source = SourceMapping(
        instrument_id=enabled_instrument.id,
        provider=Provider.YFINANCE,
        market_type=MarketType.EQUITY,
        symbol="ETH",
        enabled=False,
    )
    paused_source = SourceMapping(
        instrument_id=paused_instrument.id,
        provider=Provider.BINANCE,
        market_type=MarketType.USD_M_FUTURES,
        symbol="BTCUSDT",
        enabled=True,
    )
    session.add(active_source)
    session.add(disabled_source)
    session.add(paused_source)
    session.commit()
    session.refresh(active_source)
    session.refresh(disabled_source)
    session.refresh(paused_source)
    for source, price in (
        (active_source, Decimal("200")),
        (disabled_source, Decimal("199")),
        (paused_source, Decimal("100")),
    ):
        session.add(
            PriceObservation(
                source_mapping_id=source.id,
                price=price,
                observed_at=BASE_TIME,
                raw_path="test",
            )
        )
    session.commit()

    database_url = f"sqlite:///{tmp_path / 'status-api.sqlite3'}"
    with TestClient(
        create_app(AppRuntime(settings=Settings(), database_url=database_url))
    ) as test_client:
        response = test_client.get("/api/prices/latest")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["instrument_name"] == "Active"
    assert payload[0]["symbol"] == "ETHUSDT"
    assert payload[0]["last_price"] == "200.0000000000"


def test_empty_operational_surfaces_return_empty_lists_without_500(client: TestClient):
    # Given: no instruments are configured.
    # When: collection operational endpoints are queried.
    latest_response = client.get("/api/prices/latest")
    alerts_response = client.get("/api/alerts")
    errors_response = client.get("/api/source-errors")

    # Then: missing runtime data is represented as empty payloads, not server errors.
    assert latest_response.status_code == 200
    assert latest_response.json() == []
    assert alerts_response.status_code == 200
    assert alerts_response.json() == []
    assert errors_response.status_code == 200
    assert errors_response.json() == []


def test_openapi_documents_operational_paths(client: TestClient):
    # Given: the backend app is available offline through TestClient.
    # When: OpenAPI JSON is requested.
    response = client.get("/openapi.json")

    # Then: Todo 9 operational paths are documented.
    assert response.status_code == 200
    paths = set(response.json()["paths"])
    assert {
        "/health",
        "/api/runtime",
        "/api/prices/latest",
        "/api/alerts",
        "/api/source-errors",
        "/api/instruments/{instrument_id}/status",
    }.issubset(paths)
