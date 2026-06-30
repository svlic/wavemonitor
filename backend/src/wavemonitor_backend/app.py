from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

import anyio

from fastapi import Depends, FastAPI, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import Session

from wavemonitor_backend.api import (
    create_instrument,
    delete_instrument,
    get_instrument_status,
    list_instruments,
    list_recent_alerts,
    record_telegram_delivery,
    update_instrument,
)
from wavemonitor_backend.db import DEFAULT_DATABASE_URL, create_database_engine, create_schema, database_url_from_env, session_scope
from wavemonitor_backend.models import AlertKind
from wavemonitor_backend.monitoring import RuntimeMetricsStore
from wavemonitor_backend.operational_api import list_latest_prices, list_source_errors
from wavemonitor_backend.notifier import (
    MessageKind,
    TelegramAlert,
    TelegramHttpFailure,
    TelegramNotifier,
    TelegramSendSuccess,
    TelegramTransport,
    message_for_kind,
    sanitize_telegram_failure,
)
from wavemonitor_backend.schemas import (
    AlertResponse,
    InstrumentRequest,
    InstrumentResponse,
    InstrumentStatusResponse,
    LatestPriceResponse,
    SourceErrorResponse,
)
from wavemonitor_backend.monitoring_bootstrap import default_monitoring_lifecycle
from wavemonitor_backend.settings import Settings


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    telegram_ready: bool


class RuntimeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    scheduler_ready: bool
    providers_ready: bool
    telegram_ready: bool
    enabled_sources: int
    polled_sources: int
    observations_written: int
    source_errors: int
    alert_events_created: int
    telegram_deliveries_attempted: int
    last_tick_started_at: str | None
    last_tick_finished_at: str | None


class TelegramReadinessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    telegram_ready: bool


class TelegramTestRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument: str = Field(min_length=1, max_length=120)
    source: str = Field(min_length=1, max_length=220)
    rule: AlertKind
    price: Decimal
    support: Decimal
    resistance: Decimal

    @field_validator("price", "support", "resistance", mode="before")
    @classmethod
    def parse_decimal_string(cls, value: Decimal | str | int | float) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, str | int):
            try:
                return Decimal(value)
            except InvalidOperation as exc:
                raise ValueError("Decimal values must be provided as strings, Decimal, or integers") from exc
        raise ValueError("Decimal values must be provided as strings, Decimal, or integers")


class TelegramTestResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    sent: bool
    telegram_ready: bool
    detail: str
    delivery_id: int | None


class AppLifecycle(Protocol):
    async def run(self) -> None: ...


@dataclass(frozen=True, slots=True)
class AppRuntime:
    settings: Settings
    database_url: str = DEFAULT_DATABASE_URL
    telegram_transport: TelegramTransport | None = None
    metrics_store: RuntimeMetricsStore = field(default_factory=RuntimeMetricsStore)
    monitoring_lifecycle: AppLifecycle | None = None


def create_app(runtime: AppRuntime | None = None) -> FastAPI:
    base_runtime = runtime or AppRuntime(settings=Settings.from_env(), database_url=database_url_from_env())
    engine = create_database_engine(base_runtime.database_url)
    monitoring_lifecycle = base_runtime.monitoring_lifecycle
    if monitoring_lifecycle is None and runtime is None:
        monitoring_lifecycle = default_monitoring_lifecycle(
            engine=engine,
            settings=base_runtime.settings,
            metrics_store=base_runtime.metrics_store,
        )
    app_runtime = AppRuntime(
        settings=base_runtime.settings,
        database_url=base_runtime.database_url,
        telegram_transport=base_runtime.telegram_transport,
        metrics_store=base_runtime.metrics_store,
        monitoring_lifecycle=monitoring_lifecycle,
    )
    runtime_settings = app_runtime.settings
    metrics_store = app_runtime.metrics_store
    telegram_notifier = TelegramNotifier(runtime_settings, app_runtime.telegram_transport)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        create_schema(engine)
        lifecycle = app_runtime.monitoring_lifecycle
        if lifecycle is None:
            yield
            return
        async with anyio.create_task_group() as task_group:
            task_group.start_soon(lifecycle.run)
            yield
            task_group.cancel_scope.cancel()

    app = FastAPI(title=runtime_settings.app_name, version="0.1.0", lifespan=lifespan)

    def get_session() -> Iterator[Session]:
        with session_scope(engine) as session:
            yield session

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", telegram_ready=runtime_settings.telegram_ready)

    @app.get("/api/instruments", response_model=list[InstrumentResponse])
    def list_instruments_endpoint(session: Session = Depends(get_session)) -> list[InstrumentResponse]:
        return list_instruments(session)

    @app.post("/api/instruments", response_model=InstrumentResponse, status_code=status.HTTP_201_CREATED)
    def create_instrument_endpoint(
        payload: InstrumentRequest,
        session: Session = Depends(get_session),
    ) -> InstrumentResponse:
        return create_instrument(session, payload)

    @app.put("/api/instruments/{instrument_id}", response_model=InstrumentResponse)
    def update_instrument_endpoint(
        instrument_id: int,
        payload: InstrumentRequest,
        session: Session = Depends(get_session),
    ) -> InstrumentResponse:
        return update_instrument(session, instrument_id, payload)

    @app.delete("/api/instruments/{instrument_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_instrument_endpoint(instrument_id: int, session: Session = Depends(get_session)) -> Response:
        delete_instrument(session, instrument_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/api/instruments/{instrument_id}/status", response_model=InstrumentStatusResponse)
    def instrument_status_endpoint(
        instrument_id: int,
        session: Session = Depends(get_session),
    ) -> InstrumentStatusResponse:
        return get_instrument_status(session, instrument_id)

    @app.get("/api/alerts", response_model=list[AlertResponse])
    def list_alerts_endpoint(session: Session = Depends(get_session)) -> list[AlertResponse]:
        return list_recent_alerts(session)

    @app.get("/api/prices/latest", response_model=list[LatestPriceResponse])
    def list_latest_prices_endpoint(session: Session = Depends(get_session)) -> list[LatestPriceResponse]:
        return list_latest_prices(session)

    @app.get("/api/source-errors", response_model=list[SourceErrorResponse])
    def list_source_errors_endpoint(session: Session = Depends(get_session)) -> list[SourceErrorResponse]:
        return list_source_errors(session)

    @app.get("/api/runtime", response_model=RuntimeResponse)
    def runtime() -> RuntimeResponse:
        metrics = metrics_store.metrics
        return RuntimeResponse(
            scheduler_ready=metrics.scheduler_ready,
            providers_ready=metrics.providers_ready,
            telegram_ready=runtime_settings.telegram_ready,
            enabled_sources=metrics.enabled_sources,
            polled_sources=metrics.polled_sources,
            observations_written=metrics.observations_written,
            source_errors=metrics.source_errors,
            alert_events_created=metrics.alert_events_created,
            telegram_deliveries_attempted=metrics.telegram_deliveries_attempted,
            last_tick_started_at=api_timestamp(metrics.last_tick_started_at),
            last_tick_finished_at=api_timestamp(metrics.last_tick_finished_at),
        )

    @app.get("/api/telegram/readiness", response_model=TelegramReadinessResponse)
    def telegram_readiness() -> TelegramReadinessResponse:
        return TelegramReadinessResponse(telegram_ready=runtime_settings.telegram_ready)

    @app.post("/api/telegram/test", response_model=TelegramTestResponse)
    def test_telegram(
        payload: TelegramTestRequest | None = None,
        session: Session = Depends(get_session),
    ) -> TelegramTestResponse | JSONResponse:
        if not runtime_settings.telegram_ready:
            body = TelegramTestResponse(
                sent=False,
                telegram_ready=False,
                detail="Telegram credentials are not configured.",
                delivery_id=None,
            )
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=body.model_dump(),
            )
        message_kind = MessageKind.TEST if payload is None else MessageKind.ALERT
        alert = None if payload is None else TelegramAlert(
            instrument=payload.instrument,
            source=payload.source,
            rule=payload.rule,
            price=payload.price,
            support=payload.support,
            resistance=payload.resistance,
        )
        message = message_for_kind(message_kind, alert)
        result = telegram_notifier.send_text(message)
        if result is None:
            return TelegramTestResponse(
                sent=False,
                telegram_ready=False,
                detail="Telegram credentials are not configured.",
                delivery_id=None,
            )
        delivery = record_telegram_delivery(
            session,
            message_kind=message_kind.value,
            message_text=message,
            result=result,
        )
        delivery_id = delivery.id
        match result:
            case TelegramSendSuccess():
                return TelegramTestResponse(
                    sent=True,
                    telegram_ready=True,
                    detail="Telegram test message delivered.",
                    delivery_id=delivery_id,
                )
            case TelegramHttpFailure() as failure:
                body = TelegramTestResponse(
                    sent=False,
                    telegram_ready=True,
                    detail=sanitize_telegram_failure(failure),
                    delivery_id=delivery_id,
                )
                return JSONResponse(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    content=body.model_dump(),
                )

    return app


def api_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


app = create_app()
