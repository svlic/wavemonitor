from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlmodel import Session, select

from wavemonitor_backend.models import AlertEvent, Instrument, LastRuleState, SourceMapping
from wavemonitor_backend.rule_types import DEFAULT_COOLDOWN, RuleEvaluation, RuleState


def evaluate_and_persist_rules(
    *,
    session: Session,
    instrument: Instrument,
    source_mapping: SourceMapping,
    price: Decimal,
    observed_at: datetime,
    cooldown: timedelta = DEFAULT_COOLDOWN,
) -> RuleEvaluation:
    from wavemonitor_backend.rules import evaluate_rules

    instrument_id = require_id(instrument.id)
    source_mapping_id = require_id(source_mapping.id)
    evaluation = evaluate_rules(
        price=price,
        support=instrument.support,
        resistance=instrument.resistance,
        near_support_threshold=instrument.near_support_threshold,
        risk_reward_threshold=instrument.risk_reward_threshold,
        previous_state=rule_state_from_persisted(
            load_or_create_state(
                session=session,
                instrument_id=instrument_id,
                source_mapping_id=source_mapping_id,
            )
        ),
        observed_at=observed_at,
        cooldown=cooldown,
    )
    persist_rule_evaluation(
        session=session,
        instrument_id=instrument_id,
        source_mapping_id=source_mapping_id,
        evaluation=evaluation,
    )
    return evaluation


def persist_rule_evaluation(
    *,
    session: Session,
    instrument_id: int,
    source_mapping_id: int,
    evaluation: RuleEvaluation,
) -> list[AlertEvent]:
    events = [
        AlertEvent(
            instrument_id=instrument_id,
            source_mapping_id=source_mapping_id,
            alert_kind=alert.kind,
            price=alert.price,
            support=alert.support,
            resistance=alert.resistance,
            threshold=alert.threshold,
            message=alert.message,
            triggered_at=alert.triggered_at,
        )
        for alert in evaluation.alerts
    ]
    for event in events:
        session.add(event)
    state = load_or_create_state(session=session, instrument_id=instrument_id, source_mapping_id=source_mapping_id)
    state.last_price = evaluation.next_state.last_price
    state.near_support_active = evaluation.next_state.near_support_active
    state.risk_reward_active = evaluation.next_state.risk_reward_active
    state.above_resistance_active = evaluation.next_state.above_resistance_active
    state.near_support_last_alert_at = evaluation.next_state.near_support_last_alert_at
    state.risk_reward_last_alert_at = evaluation.next_state.risk_reward_last_alert_at
    state.breakout_last_alert_at = evaluation.next_state.breakout_last_alert_at
    state.last_invalid_state = (
        None if evaluation.invalid_state is None else evaluation.invalid_state.value
    )
    state.updated_at = max((alert.triggered_at for alert in evaluation.alerts), default=state.updated_at)
    if not events and evaluation.invalid_state is not None:
        state.updated_at = datetime.now(UTC)
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
        near_support_last_alert_at=utc_timestamp(state.near_support_last_alert_at),
        risk_reward_last_alert_at=utc_timestamp(state.risk_reward_last_alert_at),
        breakout_last_alert_at=utc_timestamp(state.breakout_last_alert_at),
    )


def utc_timestamp(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def load_or_create_state(*, session: Session, instrument_id: int, source_mapping_id: int) -> LastRuleState:
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
