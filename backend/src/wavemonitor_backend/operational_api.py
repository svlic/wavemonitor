from __future__ import annotations

from fastapi import HTTPException, status
from sqlmodel import Session, select

from wavemonitor_backend.api import (
    latest_observation_for,
    latest_successful_observation_for,
    require_id,
    source_mappings_for,
)
from wavemonitor_backend.models import (
    AlertEvent,
    AlertKind,
    Instrument,
    PriceObservation,
    SourceMapping,
)
from wavemonitor_backend.schemas import LatestPriceResponse, SourceErrorResponse


def list_latest_prices(session: Session) -> list[LatestPriceResponse]:
    crossing_kinds_by_source: dict[int, set[AlertKind]] = {}
    crossing_events = session.exec(
        select(AlertEvent.source_mapping_id, AlertEvent.alert_kind)
        .join(Instrument, AlertEvent.instrument_id == Instrument.id)
        .where(
            AlertEvent.alert_kind.in_((AlertKind.SUPPORT_BREACH, AlertKind.RESISTANCE_BREAKOUT)),
            AlertEvent.rule_cycle_started_at == Instrument.rule_cycle_started_at,
        )
    ).all()
    for source_mapping_id, alert_kind in crossing_events:
        crossing_kinds_by_source.setdefault(source_mapping_id, set()).add(alert_kind)

    prices: list[LatestPriceResponse] = []
    for instrument in session.exec(select(Instrument).order_by(Instrument.id)).all():
        if not instrument.enabled:
            continue
        for source in source_mappings_for(session, require_id(instrument.id)):
            if not source.enabled:
                continue
            observation = latest_successful_observation_for(session, source)
            if observation is None:
                continue
            source_id = require_id(source.id)
            crossing_kinds = crossing_kinds_by_source.get(source_id, set())
            prices.append(
                LatestPriceResponse(
                    instrument_id=require_id(instrument.id),
                    instrument_name=instrument.name,
                    source_mapping_id=source_id,
                    provider=source.provider,
                    market_type=source.market_type,
                    symbol=source.symbol,
                    last_price=str(observation.price)
                    if observation.price is not None
                    else "",
                    last_observed_at=observation.observed_at,
                    last_error=observation.error,
                    support_breached=AlertKind.SUPPORT_BREACH in crossing_kinds,
                    resistance_broken=AlertKind.RESISTANCE_BREAKOUT in crossing_kinds,
                )
            )
    return prices


def list_source_errors(session: Session) -> list[SourceErrorResponse]:
    errors: list[SourceErrorResponse] = []
    for instrument in session.exec(select(Instrument).order_by(Instrument.id)).all():
        if not instrument.enabled:
            continue
        for source in source_mappings_for(session, require_id(instrument.id)):
            if not source.enabled:
                continue
            observation = latest_observation_for(session, source)
            if observation is not None and observation.error is not None:
                errors.append(source_error_response(instrument, source, observation))
    return errors


def source_error_response(
    instrument: Instrument,
    source: SourceMapping,
    observation: PriceObservation,
) -> SourceErrorResponse:
    error = observation.error
    if error is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Source error row is missing error text",
        )
    return SourceErrorResponse(
        instrument_id=require_id(instrument.id),
        instrument_name=instrument.name,
        source_mapping_id=require_id(source.id),
        provider=source.provider,
        market_type=source.market_type,
        symbol=source.symbol,
        last_observed_at=observation.observed_at,
        last_error=error,
    )
