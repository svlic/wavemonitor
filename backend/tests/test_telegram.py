from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from wavemonitor_backend.app import AppRuntime, create_app
from wavemonitor_backend.db import create_database_engine, create_schema, session_scope
from wavemonitor_backend.models import AlertKind, DeliveryStatus, Instrument, SourceMapping, TelegramDelivery
from wavemonitor_backend.notifier import (
    TelegramAlert,
    TelegramHttpFailure,
    TelegramSendSuccess,
    format_telegram_alert,
)
from wavemonitor_backend.settings import Settings

TOKEN: Final[str] = "123456:secret-token"
CHAT_ID: Final[str] = "-100987654321"


@dataclass(frozen=True, slots=True)
class CapturedPost:
    url: str
    json: dict[str, str]


class FakeTelegramTransport:
    def __init__(self, response: TelegramSendSuccess | TelegramHttpFailure) -> None:
        self.response = response
        self.posts: list[CapturedPost] = []

    def post_json(self, url: str, payload: dict[str, str]) -> TelegramSendSuccess | TelegramHttpFailure:
        self.posts.append(CapturedPost(url=url, json=payload))
        return self.response


@pytest.fixture
def ready_settings() -> Settings:
    return Settings(telegram_bot_token=TOKEN, telegram_chat_id=CHAT_ID)


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path / 'telegram.sqlite3'}"


@pytest.fixture
def session(database_url: str) -> Iterator[Session]:
    engine = create_database_engine(database_url)
    create_schema(engine)
    with session_scope(engine) as db_session:
        yield db_session


def make_alert() -> TelegramAlert:
    return TelegramAlert(
        instrument="Bitcoin",
        source="binance:usd_m_futures:BTCUSDT",
        rule=AlertKind.NEAR_SUPPORT,
        price=Decimal("100.25"),
        support=Decimal("98.00"),
        resistance=Decimal("130.00"),
    )


def test_missing_env_readiness_false_and_no_send_attempt(monkeypatch, database_url: str):
    # Given: Telegram env vars are missing and a fake transport would fail the test if used.
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    transport = FakeTelegramTransport(TelegramSendSuccess(message_id="not-used"))
    with TestClient(create_app(AppRuntime(settings=Settings(), database_url=database_url, telegram_transport=transport))) as client:
        # When: readiness and test-send endpoints are called.
        readiness_response = client.get("/api/telegram/readiness")
        send_response = client.post("/api/telegram/test")
        health_response = client.get("/health")

    # Then: the app stays healthy, readiness is false, and no Telegram HTTP attempt occurs.
    assert health_response.json() == {"status": "ok", "telegram_ready": False}
    assert readiness_response.json() == {"telegram_ready": False}
    assert send_response.status_code == 503
    assert send_response.json() == {
        "sent": False,
        "telegram_ready": False,
        "detail": "Telegram credentials are not configured.",
        "delivery_id": None,
    }
    assert transport.posts == []


def test_successful_mocked_send_persists_delivery_and_logs_safe_metadata(
    ready_settings: Settings,
    database_url: str,
    caplog: pytest.LogCaptureFixture,
):
    # Given: ready credentials and a mocked Telegram Bot API success response.
    caplog.set_level(logging.INFO, logger="wavemonitor_backend.telegram")
    transport = FakeTelegramTransport(TelegramSendSuccess(message_id="777"))
    with TestClient(
        create_app(AppRuntime(settings=ready_settings, database_url=database_url, telegram_transport=transport)),
    ) as client:
        # When: the API sends a test message.
        response = client.post("/api/telegram/test")

    # Then: the send is successful, persisted, and only safe metadata is returned.
    assert response.status_code == 200
    assert response.json() == {
        "sent": True,
        "telegram_ready": True,
        "detail": "Telegram test message delivered.",
        "delivery_id": 1,
    }
    assert transport.posts == [
        CapturedPost(
            url=f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": "WaveMonitor Telegram test message.", "parse_mode": "HTML"},
        )
    ]
    engine = create_database_engine(database_url)
    with Session(engine) as db_session:
        delivery = db_session.exec(select(TelegramDelivery)).one()
    assert delivery.status == DeliveryStatus.SENT
    assert delivery.telegram_message_id == "777"
    assert delivery.safe_error is None
    assert delivery.chat_ref == "redacted"
    log_output = caplog.text
    assert "telegram_delivery_result" in log_output
    assert "status=sent" in log_output
    assert "message_kind=test" in log_output
    assert "delivery_id=1" in log_output
    assert TOKEN not in response.text
    assert CHAT_ID not in response.text
    assert TOKEN not in log_output
    assert CHAT_ID not in log_output


def test_telegram_http_failure_persists_redacted_error(
    ready_settings: Settings,
    database_url: str,
    caplog: pytest.LogCaptureFixture,
):
    # Given: Telegram rejects the mocked request and includes secret-looking text in its body.
    caplog.set_level(logging.INFO, logger="wavemonitor_backend.telegram")
    transport = FakeTelegramTransport(
        TelegramHttpFailure(
            status_code=401,
            description=f"Unauthorized for {TOKEN} and chat {CHAT_ID}",
        )
    )
    with TestClient(
        create_app(AppRuntime(settings=ready_settings, database_url=database_url, telegram_transport=transport)),
    ) as client:
        # When: the API sends a test message.
        response = client.post("/api/telegram/test")

    # Then: the failure is not reported as success and raw secrets are redacted everywhere.
    assert response.status_code == 502
    assert response.json() == {
        "sent": False,
        "telegram_ready": True,
        "detail": "Telegram delivery failed with HTTP 401.",
        "delivery_id": 1,
    }
    engine = create_database_engine(database_url)
    with Session(engine) as db_session:
        delivery = db_session.exec(select(TelegramDelivery)).one()
    assert delivery.status == DeliveryStatus.FAILED
    assert delivery.safe_error == "Telegram delivery failed with HTTP 401."
    log_output = caplog.text
    assert "telegram_delivery_result" in log_output
    assert "status=failed" in log_output
    assert "message_kind=test" in log_output
    assert "delivery_id=1" in log_output
    combined = f"{response.text} {delivery.safe_error} {delivery.chat_ref} {log_output}"
    assert TOKEN not in combined
    assert CHAT_ID not in combined
    assert "Unauthorized" not in combined


def test_formatter_includes_instrument_source_rule_price_support_and_resistance():
    # Given: a long-only alert delivery payload.
    alert = make_alert()

    # When: the Telegram message is formatted.
    message = format_telegram_alert(alert)

    # Then: operators see the instrument, source, rule, price, support, and resistance.
    assert "Bitcoin" in message
    assert "binance:usd_m_futures:BTCUSDT" in message
    assert "near_support" in message
    assert "100.25" in message
    assert "98.00" in message
    assert "130.00" in message


def test_send_alert_persists_delivery_result_without_storing_credentials(
    ready_settings: Settings,
    database_url: str,
    session: Session,
):
    # Given: a persisted alert event context and mocked Telegram success transport.
    instrument = Instrument(
        name="Bitcoin",
        support=Decimal("98"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("3"),
    )
    session.add(instrument)
    session.commit()
    session.refresh(instrument)
    source = SourceMapping(
        instrument_id=instrument.id,
        provider="binance",
        market_type="usd_m_futures",
        symbol="btcusdt",
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    transport = FakeTelegramTransport(TelegramSendSuccess(message_id="888"))
    with TestClient(
        create_app(AppRuntime(settings=ready_settings, database_url=database_url, telegram_transport=transport)),
    ) as client:
        # When: a scoped alert delivery request is sent through the API.
        response = client.post(
            "/api/telegram/test",
            json={
                "instrument": instrument.name,
                "source": source.identity_key,
                "rule": "near_support",
                "price": "100.25",
                "support": "98.00",
                "resistance": "130.00",
            },
        )

    # Then: delivery result persistence captures status/message id only, not credentials.
    assert response.status_code == 200
    engine = create_database_engine(database_url)
    with Session(engine) as db_session:
        delivery = db_session.exec(select(TelegramDelivery)).one()
    assert delivery.status == DeliveryStatus.SENT
    assert delivery.telegram_message_id == "888"
    assert delivery.message_kind == "alert"
    stored = f"{delivery.message_text} {delivery.chat_ref} {delivery.safe_error}"
    assert TOKEN not in stored
    assert CHAT_ID not in stored
    assert "Bitcoin" in delivery.message_text


@pytest.mark.parametrize(
    "payload",
    [
        {"instrument": "", "source": "binance", "rule": "near_support", "price": "1", "support": "1", "resistance": "2"},
        {"instrument": "Bitcoin", "source": "binance", "rule": "unknown", "price": "1", "support": "1", "resistance": "2"},
        {"instrument": "Bitcoin", "source": "binance", "rule": "near_support", "price": "bad", "support": "1", "resistance": "2"},
    ],
)
def test_test_send_endpoint_rejects_malformed_input_without_success_output(
    ready_settings: Settings,
    database_url: str,
    payload: dict[str, str],
):
    # Given: malformed alert test-send input crosses the API boundary.
    transport = FakeTelegramTransport(TelegramSendSuccess(message_id="not-used"))
    with TestClient(
        create_app(AppRuntime(settings=ready_settings, database_url=database_url, telegram_transport=transport)),
    ) as client:
        # When: the malformed request is submitted.
        response = client.post("/api/telegram/test", json=payload)

    # Then: validation fails before any send attempt or misleading success output.
    assert response.status_code == 422
    assert "sent" not in response.text
    assert transport.posts == []
