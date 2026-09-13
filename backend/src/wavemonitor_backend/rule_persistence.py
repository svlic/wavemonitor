from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from wavemonitor_backend.models import (
    AlertEvent,
    Instrument,
    LastRuleState,
    SourceMapping,
)
from wavemonitor_backend.rules import RuleEvaluation, RuleState
from wavemonitor_backend.support_resistance import nearest_pair


def evaluate_and_persist_rules(
    *,
    session: Session,
    instrument: Instrument,
    source_mapping: SourceMapping,
    price: Decimal,
    observed_at: datetime,
) -> RuleEvaluation:
    from wavemonitor_backend.rules import evaluate_rules

    instrument_id = require_id(instrument.id)
    source_mapping_id = require_id(source_mapping.id)
    evaluation_cycle_started_at = instrument.rule_cycle_started_at
    cycle_started_at = utc_timestamp(evaluation_cycle_started_at)
    observed_stamp = utc_timestamp(observed_at)
    if (
        observed_stamp is not None
        and cycle_started_at is not None
        and observed_stamp < cycle_started_at
    ):
        return RuleEvaluation(alerts=(), next_state=RuleState(), invalid_state=None)

    persisted_state = load_or_create_state(
        session=session,
        instrument_id=instrument_id,
        source_mapping_id=source_mapping_id,
    )
    state_updated_at = utc_timestamp(persisted_state.updated_at)
    previous_state = (
        RuleState()
        if cycle_started_at is not None
        and state_updated_at is not None
        and state_updated_at < cycle_started_at
        else rule_state_from_persisted(persisted_state)
    )
    support, resistance = nearest_pair(instrument.supports, instrument.resistances, price)
    if support is None and instrument.supports:
        support = min(instrument.supports)
    evaluation = evaluate_rules(
        price=price,
        support=support,
        resistance=resistance,
        near_support_threshold=instrument.near_support_threshold,
        risk_reward_threshold=instrument.risk_reward_threshold,
        previous_state=previous_state,
        observed_at=observed_at,
    )
    events = persist_rule_evaluation(
        session=session,
        instrument_id=instrument_id,
        source_mapping_id=source_mapping_id,
        rule_cycle_started_at=evaluation_cycle_started_at,
        evaluation=evaluation,
        observed_at=observed_at,
    )
    claimed_kinds = {event.alert_kind for event in events}
    return replace(
        evaluation,
        alerts=tuple(alert for alert in evaluation.alerts if alert.kind in claimed_kinds),
    )


def persist_rule_evaluation(
    *,
    session: Session,
    instrument_id: int,
    source_mapping_id: int,
    evaluation: RuleEvaluation,
    observed_at: datetime,
    rule_cycle_started_at: datetime | None = None,
) -> list[AlertEvent]:
    instrument = session.get(Instrument, instrument_id)
    if instrument is None:
        raise MissingPersistedIdError
    if rule_cycle_started_at is not None:
        cycle_claim = session.execute(
            update(Instrument)
            .where(
                Instrument.id == instrument_id,
                Instrument.rule_cycle_started_at == rule_cycle_started_at,
            )
            .values(rule_cycle_started_at=Instrument.rule_cycle_started_at)
        )
        if cycle_claim.rowcount != 1:
            session.rollback()
            return []
        session.refresh(instrument)
    events: list[AlertEvent] = []
    for alert in evaluation.alerts:
        event = AlertEvent(
            instrument_id=instrument_id,
            source_mapping_id=source_mapping_id,
            alert_kind=alert.kind,
            price=alert.price,
            support=alert.support,
            resistance=alert.resistance,
            threshold=alert.threshold,
            message=alert.message,
            triggered_at=alert.triggered_at,
            rule_cycle_started_at=instrument.rule_cycle_started_at,
        )
        try:
            with session.begin_nested():
                session.add(event)
                session.flush()
        except IntegrityError:
            continue
        events.append(event)
    state = load_or_create_state(
        session=session, instrument_id=instrument_id, source_mapping_id=source_mapping_id
    )
    state.last_price = evaluation.next_state.last_price
    state.near_support_active = evaluation.next_state.near_support_active
    state.risk_reward_active = evaluation.next_state.risk_reward_active
    state.above_resistance_active = evaluation.next_state.above_resistance_active
    state.support_breach_active = evaluation.next_state.support_breach_active
    state.near_support_last_alert_at = evaluation.next_state.near_support_last_alert_at
    state.risk_reward_last_alert_at = evaluation.next_state.risk_reward_last_alert_at
    state.breakout_last_alert_at = evaluation.next_state.breakout_last_alert_at
    state.support_breach_last_alert_at = evaluation.next_state.support_breach_last_alert_at
    state.last_invalid_state = (
        None if evaluation.invalid_state is None else evaluation.invalid_state.value
    )
    observed_stamp = (
        observed_at if observed_at.tzinfo is not None else observed_at.replace(tzinfo=UTC)
    )
    state.updated_at = max(
        (alert.triggered_at for alert in evaluation.alerts),
        default=observed_stamp,
    )
    session.add(state)
    session.commit()
    for event in events:
        session.refresh(event)
    return events


def rule_state_from_persisted(state: LastRuleState) -> RuleState:
    return RuleState(
        last_price=state.last_price,
        near_support_active=state.near_support_active,
        risk_reward_active=state.risk_reward_active,
        above_resistance_active=state.above_resistance_active,
        support_breach_active=state.support_breach_active,
        near_support_last_alert_at=utc_timestamp(state.near_support_last_alert_at),
        risk_reward_last_alert_at=utc_timestamp(state.risk_reward_last_alert_at),
        breakout_last_alert_at=utc_timestamp(state.breakout_last_alert_at),
        support_breach_last_alert_at=utc_timestamp(state.support_breach_last_alert_at),
    )


def utc_timestamp(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def load_or_create_state(
    *, session: Session, instrument_id: int, source_mapping_id: int
) -> LastRuleState:
    statement = select(LastRuleState).where(
        LastRuleState.instrument_id == instrument_id,
        LastRuleState.source_mapping_id == source_mapping_id,
    )
    state = session.exec(statement).first()
    if state is not None:
        return state
    return LastRuleState(
        instrument_id=instrument_id,
        source_mapping_id=source_mapping_id,
        updated_at=datetime.min,
    )


def require_id(value: int | None) -> int:
    if value is None:
        raise MissingPersistedIdError
    return value


class MissingPersistedIdError(RuntimeError):
    def __str__(self) -> str:
        return "rule persistence requires saved instrument and source mapping rows"
