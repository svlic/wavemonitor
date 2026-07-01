from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from wavemonitor_backend.models import (
    AlertEvent,
    Instrument,
    LastRuleState,
    MarketType,
    PriceObservation,
    Provider,
    SourceMapping,
)
from wavemonitor_backend.notifier import TelegramHttpFailure, TelegramSendSuccess, sanitize_telegram_failure
from wavemonitor_backend.schemas import (
    AlertResponse,
    InstrumentRequest,
    InstrumentResponse,
    InstrumentStatusResponse,
    SourceMappingRequest,
    SourceMappingResponse,
    SourceStatusResponse,
)
from wavemonitor_backend.telegram_delivery import record_telegram_delivery


def list_instruments(session: Session) -> list[InstrumentResponse]:
    instruments = session.exec(select(Instrument).order_by(Instrument.id)).all()
    return [instrument_response(session, instrument) for instrument in instruments]


def create_instrument(session: Session, payload: InstrumentRequest) -> InstrumentResponse:
    now = datetime.now(UTC)
    instrument = Instrument(
        name=payload.name,
        enabled=payload.enabled,
        support=payload.support,
        resistance=payload.resistance,
        near_support_threshold=payload.near_support_threshold,
        risk_reward_threshold=payload.risk_reward_threshold,
        created_at=now,
        updated_at=now,
    )
    try:
        session.add(instrument)
        session.flush()
        instrument_id = require_id(instrument.id)
        add_source_mappings(session, instrument_id, payload)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source mapping already exists",
        ) from exc
    session.refresh(instrument)
    return instrument_response(session, instrument)


def update_instrument(session: Session, instrument_id: int, payload: InstrumentRequest) -> InstrumentResponse:
    instrument = get_instrument(session, instrument_id)
    rule_fields_changed = instrument_rule_fields_changed(instrument, payload)
    instrument.name = payload.name
    instrument.enabled = payload.enabled
    instrument.support = payload.support
    instrument.resistance = payload.resistance
    instrument.near_support_threshold = payload.near_support_threshold
    instrument.risk_reward_threshold = payload.risk_reward_threshold
    instrument.updated_at = datetime.now(UTC)
    try:
        sync_source_mappings(session, instrument_id, payload)
        if rule_fields_changed:
            clear_last_rule_states_for_instrument(session, instrument_id)
        session.add(instrument)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Source mapping already exists",
        ) from exc
    session.refresh(instrument)
    return instrument_response(session, instrument)


def delete_instrument(session: Session, instrument_id: int) -> None:
    instrument = get_instrument(session, instrument_id)
    delete_instrument_cascade(session, instrument_id)
    session.delete(instrument)
    session.commit()


def get_instrument_status(session: Session, instrument_id: int) -> InstrumentStatusResponse:
    instrument = get_instrument(session, instrument_id)
    source_statuses = tuple(source_status(session, source) for source in source_mappings_for(session, instrument_id))
    alerts = tuple(alert_response(alert) for alert in recent_alerts_for(session, instrument_id))
    return InstrumentStatusResponse(
        instrument_id=instrument_id,
        enabled=instrument.enabled,
        sources=source_statuses,
        recent_alerts=alerts,
    )


def list_recent_alerts(session: Session) -> list[AlertResponse]:
    statement = select(AlertEvent).order_by(desc(AlertEvent.triggered_at)).limit(50)
    return [alert_response(alert) for alert in session.exec(statement).all()]


def instrument_response(session: Session, instrument: Instrument) -> InstrumentResponse:
    return InstrumentResponse(
        id=require_id(instrument.id),
        name=instrument.name,
        enabled=instrument.enabled,
        support=instrument.support,
        resistance=instrument.resistance,
        near_support_threshold=instrument.near_support_threshold,
        risk_reward_threshold=instrument.risk_reward_threshold,
        source_mappings=tuple(source_response(source) for source in source_mappings_for(session, require_id(instrument.id))),
    )


def source_response(source: SourceMapping) -> SourceMappingResponse:
    return SourceMappingResponse(
        id=require_id(source.id),
        provider=source.provider,
        market_type=source.market_type,
        symbol=source.symbol,
        enabled=source.enabled,
    )


def source_status(session: Session, source: SourceMapping) -> SourceStatusResponse:
    observation = latest_observation_for(session, source)
    rule_state = latest_rule_state_for(session, source)
    return SourceStatusResponse(
        id=require_id(source.id),
        provider=source.provider,
        market_type=source.market_type,
        symbol=source.symbol,
        enabled=source.enabled,
        last_price=decimal_to_api_string(observation.price) if observation is not None and observation.price is not None else None,
        last_observed_at=observation.observed_at if observation is not None else None,
        last_error=observation.error if observation is not None else None,
        last_invalid_state=rule_state.last_invalid_state if rule_state is not None else None,
    )


def alert_response(alert: AlertEvent) -> AlertResponse:
    return AlertResponse(
        id=require_id(alert.id),
        instrument_id=alert.instrument_id,
        source_mapping_id=alert.source_mapping_id,
        alert_kind=alert.alert_kind,
        price=decimal_to_api_string(alert.price),
        message=alert.message,
        triggered_at=alert.triggered_at,
    )


def source_mappings_for(session: Session, instrument_id: int) -> list[SourceMapping]:
    statement = select(SourceMapping).where(SourceMapping.instrument_id == instrument_id).order_by(SourceMapping.id)
    return list(session.exec(statement).all())


def latest_observation_for(session: Session, source: SourceMapping) -> PriceObservation | None:
    statement = (
        select(PriceObservation)
        .where(PriceObservation.source_mapping_id == require_id(source.id))
        .order_by(desc(PriceObservation.observed_at))
        .limit(1)
    )
    return session.exec(statement).first()


def recent_alerts_for(session: Session, instrument_id: int) -> list[AlertEvent]:
    statement = (
        select(AlertEvent)
        .where(AlertEvent.instrument_id == instrument_id)
        .order_by(desc(AlertEvent.triggered_at))
        .limit(10)
    )
    return list(session.exec(statement).all())


def instrument_rule_fields_changed(instrument: Instrument, payload: InstrumentRequest) -> bool:
    return (
        instrument.support != payload.support
        or instrument.resistance != payload.resistance
        or instrument.near_support_threshold != payload.near_support_threshold
        or instrument.risk_reward_threshold != payload.risk_reward_threshold
    )


def clear_last_rule_states_for_instrument(session: Session, instrument_id: int) -> None:
    for state in session.exec(
        select(LastRuleState).where(LastRuleState.instrument_id == instrument_id)
    ).all():
        session.delete(state)


def add_source_mappings(session: Session, instrument_id: int, payload: InstrumentRequest) -> None:
    for source in payload.source_mappings:
        session.add(
            SourceMapping(
                instrument_id=instrument_id,
                provider=source.provider,
                market_type=source.market_type,
                symbol=source.symbol,
                enabled=source.enabled,
            )
        )


def sync_source_mappings(session: Session, instrument_id: int, payload: InstrumentRequest) -> None:
    existing = {mapping_identity_key(source): source for source in source_mappings_for(session, instrument_id)}
    desired_keys = {mapping_identity_key_from_request(source) for source in payload.source_mappings}
    for key, row in list(existing.items()):
        if key not in desired_keys:
            delete_source_mapping_cascade(session, row)
    for source in payload.source_mappings:
        key = mapping_identity_key_from_request(source)
        row = existing.get(key)
        if row is None:
            session.add(
                SourceMapping(
                    instrument_id=instrument_id,
                    provider=source.provider,
                    market_type=source.market_type,
                    symbol=source.symbol,
                    enabled=source.enabled,
                )
            )
        else:
            row.enabled = source.enabled
            session.add(row)


def mapping_identity_key(source: SourceMapping) -> tuple[Provider, MarketType, str]:
    return (source.provider, source.market_type, source.symbol)


def mapping_identity_key_from_request(source: SourceMappingRequest) -> tuple[Provider, MarketType, str]:
    return (source.provider, source.market_type, source.symbol)


def latest_rule_state_for(session: Session, source: SourceMapping) -> LastRuleState | None:
    statement = select(LastRuleState).where(LastRuleState.source_mapping_id == require_id(source.id))
    return session.exec(statement).first()


def delete_instrument_cascade(session: Session, instrument_id: int) -> None:
    for source in source_mappings_for(session, instrument_id):
        delete_source_mapping_cascade(session, source)


def delete_source_mapping_cascade(session: Session, source: SourceMapping) -> None:
    source_id = require_id(source.id)
    for observation in session.exec(
        select(PriceObservation).where(PriceObservation.source_mapping_id == source_id)
    ).all():
        session.delete(observation)
    for alert in session.exec(select(AlertEvent).where(AlertEvent.source_mapping_id == source_id)).all():
        session.delete(alert)
    for state in session.exec(
        select(LastRuleState).where(LastRuleState.source_mapping_id == source_id)
    ).all():
        session.delete(state)
    session.delete(source)


def get_instrument(session: Session, instrument_id: int) -> Instrument:
    instrument = session.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instrument not found")
    return instrument


def require_id(value: int | None) -> int:
    if value is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database row id is missing")
    return value


def decimal_to_api_string(value: Decimal) -> str:
    return str(value)
