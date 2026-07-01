from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select

from wavemonitor_backend.models import AlertEvent, AlertKind, Instrument, LastRuleState, MarketType, Provider, SourceMapping
from wavemonitor_backend.rule_types import InvalidRuleState, RuleEvaluation
from wavemonitor_backend.rules import (
    AlertDecision,
    RuleState,
    evaluate_and_persist_rules,
    persist_rule_evaluation,
)

OBSERVED_AT = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


def persisted_instrument_and_source(session: Session) -> tuple[Instrument, SourceMapping]:
    instrument = Instrument(
        name="Bitcoin",
        support="98",
        resistance="130",
        near_support_threshold="0.02",
        risk_reward_threshold="20",
        created_at=OBSERVED_AT,
        updated_at=OBSERVED_AT,
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
    return instrument, source


def test_persistence_creates_alert_event_and_updates_last_rule_state(tmp_path: Path):
    # Given: a persisted instrument/source and an evaluation that emits near-support.
    engine = create_engine(f"sqlite:///{tmp_path / 'rules.sqlite3'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        instrument, source = persisted_instrument_and_source(session)
        evaluation = RuleEvaluation(
            alerts=(
                AlertDecision(
                    kind=AlertKind.NEAR_SUPPORT,
                    price=Decimal("100"),
                    support=Decimal("98"),
                    resistance=Decimal("130"),
                    threshold=Decimal("0.02"),
                    metric=Decimal("0.02"),
                    triggered_at=OBSERVED_AT,
                    message="BTCUSDT is within 0.02 of support 98 at price 100",
                ),
            ),
            next_state=RuleState(
                last_price=Decimal("100"),
                near_support_active=True,
                near_support_last_alert_at=OBSERVED_AT,
            ),
            invalid_state=None,
        )

        # When: the evaluation is persisted for this instrument/source pair.
        events = persist_rule_evaluation(
            session=session,
            instrument_id=instrument.id,
            source_mapping_id=source.id,
            evaluation=evaluation,
            observed_at=OBSERVED_AT,
        )
        stored_events = session.exec(select(AlertEvent)).all()
        stored_state = session.exec(select(LastRuleState)).one()

        # Then: AlertEvent and source-specific LastRuleState are durable and Decimal-preserving.
        assert events == stored_events
        assert len(stored_events) == 1
        assert stored_events[0].alert_kind == AlertKind.NEAR_SUPPORT
        assert stored_events[0].price == Decimal("100.0000000000")
        assert stored_events[0].threshold == Decimal("0.0200000000")
        assert stored_state.instrument_id == instrument.id
        assert stored_state.source_mapping_id == source.id
        assert stored_state.last_price == Decimal("100.0000000000")
        assert stored_state.near_support_active is True
        assert stored_state.near_support_last_alert_at == OBSERVED_AT.replace(tzinfo=None)
        assert stored_state.last_invalid_state is None


def test_persist_invalid_state_without_alerts(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'invalid.sqlite3'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        instrument, source = persisted_instrument_and_source(session)
        evaluation = RuleEvaluation(
            alerts=(),
            next_state=RuleState(last_price=Decimal("97")),
            invalid_state=InvalidRuleState.PRICE_NOT_ABOVE_SUPPORT,
        )
        persist_rule_evaluation(
            session=session,
            instrument_id=instrument.id,
            source_mapping_id=source.id,
            evaluation=evaluation,
            observed_at=OBSERVED_AT,
        )
        stored_state = session.exec(select(LastRuleState)).one()
        assert stored_state.last_invalid_state == "price_not_above_support"
        assert stored_state.updated_at == OBSERVED_AT.replace(tzinfo=None)
        assert session.exec(select(AlertEvent)).all() == []


def test_evaluate_and_persist_uses_last_rule_state_for_dedupe(tmp_path: Path):
    # Given: a persisted source with no previous rule state.
    engine = create_engine(f"sqlite:///{tmp_path / 'dedupe.sqlite3'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        instrument, source = persisted_instrument_and_source(session)

        # When: the same near-support observation is evaluated twice through persistence.
        first = evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=Decimal("100"),
            observed_at=OBSERVED_AT,
        )
        repeated = evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=Decimal("100"),
            observed_at=OBSERVED_AT + timedelta(seconds=30),
        )
        stored_events = session.exec(select(AlertEvent)).all()

        # Then: LastRuleState suppresses the duplicate active alert for that exact source.
        assert [alert.kind for alert in first.alerts] == [AlertKind.NEAR_SUPPORT]
        assert repeated.alerts == ()
        assert len(stored_events) == 1


def test_persisted_cooldown_retriggers_active_near_support_at_boundary(tmp_path: Path):
    # Given: a persisted source whose near-support condition remains active across the cooldown window.
    engine = create_engine(f"sqlite:///{tmp_path / 'cooldown.sqlite3'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        instrument, source = persisted_instrument_and_source(session)

        # When: the same source is evaluated at first alert time and exactly five minutes later.
        first = evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=Decimal("100"),
            observed_at=OBSERVED_AT,
            cooldown=timedelta(minutes=5),
        )
        second = evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=Decimal("100"),
            observed_at=OBSERVED_AT + timedelta(minutes=5),
            cooldown=timedelta(minutes=5),
        )
        stored_events = session.exec(select(AlertEvent).where(AlertEvent.source_mapping_id == source.id)).all()

        # Then: persisted last-alert timestamps allow cooldown retriggering without condition reset.
        assert [alert.kind for alert in first.alerts] == [AlertKind.NEAR_SUPPORT]
        assert [alert.kind for alert in second.alerts] == [AlertKind.NEAR_SUPPORT]
        assert len(stored_events) == 2


def test_no_alert_evaluation_updates_last_rule_state_timestamp(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'tick.sqlite3'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        instrument, source = persisted_instrument_and_source(session)
        tick_at = OBSERVED_AT + timedelta(minutes=1)
        evaluation = RuleEvaluation(
            alerts=(),
            next_state=RuleState(last_price=Decimal("120")),
            invalid_state=None,
        )
        persist_rule_evaluation(
            session=session,
            instrument_id=instrument.id,
            source_mapping_id=source.id,
            evaluation=evaluation,
            observed_at=tick_at,
        )
        stored_state = session.exec(select(LastRuleState)).one()
        assert stored_state.last_price == Decimal("120.0000000000")
        assert stored_state.updated_at == tick_at.replace(tzinfo=None)
