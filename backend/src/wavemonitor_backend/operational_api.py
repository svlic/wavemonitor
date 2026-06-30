from __future__ import annotations

from fastapi import HTTPException, status
from sqlmodel import Session, select

from wavemonitor_backend.api import (
    decimal_to_api_string,
    latest_observation_for,
    require_id,
    source_mappings_for,
)
from wavemonitor_backend.models import Instrument, PriceObservation, SourceMapping
from wavemonitor_backend.schemas import LatestPriceResponse, SourceErrorResponse


def list_latest_prices(session: Session) -> list[LatestPriceResponse]:
    prices: list[LatestPriceResponse] = []
    for instrument in session.exec(select(Instrument).order_by(Instrument.id)).all():
        for source in source_mappings_for(session, require_id(instrument.id)):
            observation = latest_observation_for(session, source)
            if observation is not None and observation.error is None:
                prices.append(latest_price_response(instrument, source, observation))
    return prices


def list_source_errors(session: Session) -> list[SourceErrorResponse]:
    errors: list[SourceErrorResponse] = []
    for instrument in session.exec(select(Instrument).order_by(Instrument.id)).all():
        for source in source_mappings_for(session, require_id(instrument.id)):
            observation = latest_observation_for(session, source)
            if observation is not None and observation.error is not None:
                errors.append(source_error_response(instrument, source, observation))
    return errors


def latest_price_response(
    instrument: Instrument,
    source: SourceMapping,
    observation: PriceObservation,
) -> LatestPriceResponse:
    return LatestPriceResponse(
        instrument_id=require_id(instrument.id),
        instrument_name=instrument.name,
        source_mapping_id=require_id(source.id),
        provider=source.provider,
        market_type=source.market_type,
        symbol=source.symbol,
        last_price=decimal_to_api_string(observation.price),
        last_observed_at=observation.observed_at,
        last_error=observation.error,
    )


def source_error_response(
    instrument: Instrument,
    source: SourceMapping,
    observation: PriceObservation,
) -> SourceErrorResponse:
    error = observation.error
    if error is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Source error row is missing error text")
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
