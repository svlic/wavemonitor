from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel, select

from wavemonitor_backend.models import (
    AlertEvent,
    AlertKind,
    Instrument,
    LastRuleState,
    MarketType,
    Provider,
    SourceMapping,
)
from wavemonitor_backend.rule_persistence import (
    evaluate_and_persist_rules,
    persist_rule_evaluation,
)
from wavemonitor_backend.rules import AlertDecision, InvalidRuleState, RuleEvaluation, RuleState

OBSERVED_AT = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


def persisted_instrument_and_source(session: Session) -> tuple[Instrument, SourceMapping]:
    instrument = Instrument(
        name="Bitcoin",
        supports=["98"],
        resistances=["130"],
        near_support_threshold="0.02",
        risk_reward_threshold="20",
        created_at=OBSERVED_AT,
        updated_at=OBSERVED_AT,
        rule_cycle_started_at=OBSERVED_AT,
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
    engine = create_engine(
        f"sqlite:///{tmp_path / 'rules.sqlite3'}", connect_args={"check_same_thread": False}
    )
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
                near_support_alert_bucket=2,
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
        assert stored_state.near_support_alert_bucket == 2
        assert stored_state.near_support_last_alert_at == OBSERVED_AT.replace(tzinfo=None)
        assert stored_state.last_invalid_state is None


def test_persistence_rejects_evaluation_from_previous_rule_cycle(tmp_path: Path):
    # Given: an evaluation was computed before another session advanced the rule cycle.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'stale-cycle.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        instrument, source = persisted_instrument_and_source(session)
        previous_cycle = instrument.rule_cycle_started_at
        evaluation = RuleEvaluation(
            alerts=(
                AlertDecision(
                    kind=AlertKind.SUPPORT_BREACH,
                    price=Decimal("90"),
                    support=Decimal("98"),
                    resistance=Decimal("130"),
                    threshold=Decimal("98"),
                    metric=Decimal("-8"),
                    triggered_at=OBSERVED_AT,
                    message="BTCUSDT breached support",
                ),
            ),
            next_state=RuleState(last_price=Decimal("90"), support_breach_active=True),
            invalid_state=None,
        )
        with Session(engine) as edit_session:
            current = edit_session.get(Instrument, instrument.id)
            assert current is not None
            current.rule_cycle_started_at = OBSERVED_AT + timedelta(minutes=1)
            edit_session.add(current)
            edit_session.commit()

        # When: persistence receives the now-stale evaluation cycle snapshot.
        events = persist_rule_evaluation(
            session=session,
            instrument_id=instrument.id,
            source_mapping_id=source.id,
            rule_cycle_started_at=previous_cycle,
            evaluation=evaluation,
            observed_at=OBSERVED_AT,
        )

        # Then: no event or rule state crosses into the newer cycle.
        assert events == []
        assert session.exec(select(AlertEvent)).all() == []
        assert session.exec(select(LastRuleState)).all() == []


def test_persist_invalid_state_without_alerts(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'invalid.sqlite3'}", connect_args={"check_same_thread": False}
    )
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
    engine = create_engine(
        f"sqlite:///{tmp_path / 'dedupe.sqlite3'}", connect_args={"check_same_thread": False}
    )
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


def test_persisted_near_support_alerts_rearm_after_condition_resets(tmp_path: Path):
    # Given: near-support becomes active, stays active, resets, then triggers again.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'edge.sqlite3'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        instrument, source = persisted_instrument_and_source(session)

        # When: first trigger, repeat while active, move away, then near support again.
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
            observed_at=OBSERVED_AT + timedelta(hours=1),
        )
        evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=Decimal("105"),
            observed_at=OBSERVED_AT + timedelta(hours=2),
        )
        retriggered = evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=Decimal("100"),
            observed_at=OBSERVED_AT + timedelta(hours=3),
        )
        stored_events = session.exec(
            select(AlertEvent).where(AlertEvent.source_mapping_id == source.id)
        ).all()
        stored_state = session.exec(select(LastRuleState)).one()

        # Then: LastRuleState suppresses while active and re-arms after reset.
        assert [alert.kind for alert in first.alerts] == [AlertKind.NEAR_SUPPORT]
        assert repeated.alerts == ()
        assert [alert.kind for alert in retriggered.alerts] == [AlertKind.NEAR_SUPPORT]
        assert len(stored_events) == 2
        assert stored_state.near_support_active is True
        assert stored_state.near_support_last_alert_at == (
            OBSERVED_AT + timedelta(hours=3)
        ).replace(tzinfo=None)


def test_no_alert_evaluation_updates_last_rule_state_timestamp(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'tick.sqlite3'}", connect_args={"check_same_thread": False}
    )
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


def test_evaluate_and_persist_uses_nearest_support_and_resistance_pair(tmp_path: Path):
    # Given: several supports below price and several resistances above it.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'nearest-pair.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        instrument = Instrument(
            name="Bitcoin",
            supports=["90", "98"],
            resistances=["130", "150"],
            near_support_threshold="0.02",
            risk_reward_threshold="20",
            created_at=OBSERVED_AT,
            updated_at=OBSERVED_AT,
            rule_cycle_started_at=OBSERVED_AT,
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

        # When: price sits between 98 and 130, closer to the inner pair than the outer bands.
        evaluation = evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=Decimal("100"),
            observed_at=OBSERVED_AT,
        )
        stored_events = session.exec(select(AlertEvent)).all()

        # Then: the persisted snapshot uses the nearest pair, not the farther levels.
        assert [alert.kind for alert in evaluation.alerts] == [AlertKind.NEAR_SUPPORT]
        assert len(stored_events) == 1
        assert stored_events[0].support == Decimal("98.0000000000")
        assert stored_events[0].resistance == Decimal("130.0000000000")


def test_first_persisted_observation_above_resistance_emits_breakout(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'first-breakout.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        instrument = Instrument(
            name="Bitcoin",
            supports=[],
            resistances=["110"],
            created_at=OBSERVED_AT,
            updated_at=OBSERVED_AT,
            rule_cycle_started_at=OBSERVED_AT,
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

        evaluation = evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=Decimal("111"),
            observed_at=OBSERVED_AT,
        )

        assert [alert.kind for alert in evaluation.alerts] == [AlertKind.RESISTANCE_BREAKOUT]
        assert session.exec(select(AlertEvent)).one().resistance == Decimal("110.0000000000")


def test_persisted_state_above_resistance_without_prior_alert_self_heals(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'missed-breakout.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        instrument, source = persisted_instrument_and_source(session)
        session.add(
            LastRuleState(
                instrument_id=instrument.id,
                source_mapping_id=source.id,
                last_price=Decimal("131"),
                updated_at=OBSERVED_AT,
            )
        )
        session.commit()

        first = evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=Decimal("132"),
            observed_at=OBSERVED_AT + timedelta(minutes=1),
        )
        repeated = evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=Decimal("133"),
            observed_at=OBSERVED_AT + timedelta(minutes=2),
        )
        after_rearm = evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=Decimal("134"),
            observed_at=OBSERVED_AT + timedelta(minutes=3),
        )

        assert [alert.kind for alert in first.alerts] == [AlertKind.RESISTANCE_BREAKOUT]
        assert repeated.alerts == ()
        assert after_rearm.alerts == ()
        assert [event.alert_kind for event in session.exec(select(AlertEvent)).all()] == [
            AlertKind.RESISTANCE_BREAKOUT
        ]


def test_multiple_support_levels_emit_each_downward_crossing(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'support-levels.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        instrument = Instrument(
            name="Bitcoin",
            supports=["90", "98"],
            resistances=[],
            near_support_threshold="0.01",
            created_at=OBSERVED_AT,
            updated_at=OBSERVED_AT,
            rule_cycle_started_at=OBSERVED_AT,
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

        for minute, price in enumerate(("100", "95", "89")):
            evaluate_and_persist_rules(
                session=session,
                instrument=instrument,
                source_mapping=source,
                price=Decimal(price),
                observed_at=OBSERVED_AT + timedelta(minutes=minute),
            )

        breaches = session.exec(
            select(AlertEvent).where(AlertEvent.alert_kind == AlertKind.SUPPORT_BREACH)
        ).all()
        assert [event.support for event in breaches] == [Decimal("98"), Decimal("90")]


def test_multiple_resistance_levels_emit_each_upward_crossing(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'resistance-levels.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        instrument = Instrument(
            name="Bitcoin",
            supports=[],
            resistances=["110", "130"],
            created_at=OBSERVED_AT,
            updated_at=OBSERVED_AT,
            rule_cycle_started_at=OBSERVED_AT,
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

        for minute, price in enumerate(("100", "120", "140")):
            evaluate_and_persist_rules(
                session=session,
                instrument=instrument,
                source_mapping=source,
                price=Decimal(price),
                observed_at=OBSERVED_AT + timedelta(minutes=minute),
            )

        breakouts = session.exec(
            select(AlertEvent).where(AlertEvent.alert_kind == AlertKind.RESISTANCE_BREAKOUT)
        ).all()
        assert [event.resistance for event in breakouts] == [Decimal("110"), Decimal("130")]


def test_fixed_drawdown_derived_support_emits_breach(tmp_path: Path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'fixed-drawdown.sqlite3'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        instrument = Instrument(
            name="Bitcoin trail",
            alert_mode="fixed_drawdown",
            high_water="100",
            fixed_drawdown="10",
            near_support_threshold="0.01",
            created_at=OBSERVED_AT,
            updated_at=OBSERVED_AT,
            rule_cycle_started_at=OBSERVED_AT,
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

        evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=Decimal("100"),
            observed_at=OBSERVED_AT,
        )
        evaluation = evaluate_and_persist_rules(
            session=session,
            instrument=instrument,
            source_mapping=source,
            price=Decimal("89"),
            observed_at=OBSERVED_AT + timedelta(minutes=1),
        )

        assert instrument.supports == [Decimal("90")]
        assert [alert.kind for alert in evaluation.alerts] == [AlertKind.SUPPORT_BREACH]
        assert session.exec(select(AlertEvent)).one().support == Decimal("90")
