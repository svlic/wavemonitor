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
    MarketType,
    Provider,
    SourceMapping,
)
from wavemonitor_backend.rule_persistence import evaluate_and_persist_rules
from wavemonitor_backend.rule_types import InvalidRuleState
from wavemonitor_backend.rules import RuleState, evaluate_rules

OBSERVED_AT = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


def test_risk_reward_uses_long_setup_decimal_exactness():
    # Given: a long setup with support below price and resistance above price.
    state = RuleState()

    # When: rules are evaluated at price 100 between support 90 and resistance 130.
    evaluation = evaluate_rules(
        price=Decimal("100"),
        support=Decimal("90"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("3"),
        previous_state=state,
        observed_at=OBSERVED_AT,
    )

    # Then: risk/reward is exactly (130 - 100) / (100 - 90) = 3 and emits one alert.
    risk_reward = next(alert for alert in evaluation.alerts if alert.kind == AlertKind.RISK_REWARD)
    assert risk_reward.metric == Decimal("3")
    assert risk_reward.threshold == Decimal("3")
    assert risk_reward.price == Decimal("100")
    assert evaluation.next_state.risk_reward_active is True


def test_near_support_true_and_false_threshold_boundary():
    # Given: support-distance threshold is 2% of current price.
    inactive_state = RuleState()

    # When: price is 100 with support 98 and support 97.
    near_result = evaluate_rules(
        price=Decimal("100"),
        support=Decimal("98"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        previous_state=inactive_state,
        observed_at=OBSERVED_AT,
    )
    far_result = evaluate_rules(
        price=Decimal("100"),
        support=Decimal("97"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        previous_state=inactive_state,
        observed_at=OBSERVED_AT,
    )

    # Then: 2% distance alerts and 3% distance does not.
    assert [alert.kind for alert in near_result.alerts] == [AlertKind.NEAR_SUPPORT]
    assert near_result.alerts[0].metric == Decimal("0.02")
    assert far_result.alerts == ()
    assert far_result.next_state.near_support_active is False


def test_breakout_requires_crossing_from_at_or_below_resistance():
    # Given: resistance is 110 and prior observations can be absent, below, or already above.
    first_observation = RuleState()
    below_previous = RuleState(last_price=Decimal("100"))
    above_previous = RuleState(last_price=Decimal("111"), above_resistance_active=True)

    # When: observations are evaluated around the resistance crossing.
    first = evaluate_rules(
        price=Decimal("111"),
        support=Decimal("90"),
        resistance=Decimal("110"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("3"),
        previous_state=first_observation,
        observed_at=OBSERVED_AT,
    )
    crossing = evaluate_rules(
        price=Decimal("111"),
        support=Decimal("90"),
        resistance=Decimal("110"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("3"),
        previous_state=below_previous,
        observed_at=OBSERVED_AT,
    )
    already_above = evaluate_rules(
        price=Decimal("112"),
        support=Decimal("90"),
        resistance=Decimal("110"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("3"),
        previous_state=above_previous,
        observed_at=OBSERVED_AT,
    )

    # Then: only the true crossing emits resistance-breakout.
    assert AlertKind.RESISTANCE_BREAKOUT not in {alert.kind for alert in first.alerts}
    assert [alert.kind for alert in crossing.alerts] == [AlertKind.RESISTANCE_BREAKOUT]
    assert crossing.next_state.above_resistance_active is True
    assert already_above.alerts == ()


def test_price_at_or_below_support_emits_support_breach_and_invalid_state():
    # Given: prices at and below support make the long risk denominator zero or negative.
    state = RuleState(
        last_price=Decimal("101"),
        near_support_last_alert_at=OBSERVED_AT - timedelta(minutes=1),
    )

    # When: equal-support and below-support prices are evaluated.
    equal_support = evaluate_rules(
        price=Decimal("100"),
        support=Decimal("100"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("3"),
        previous_state=state,
        observed_at=OBSERVED_AT,
    )
    below_support = evaluate_rules(
        price=Decimal("99"),
        support=Decimal("100"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("3"),
        previous_state=equal_support.next_state,
        observed_at=OBSERVED_AT + timedelta(seconds=30),
    )

    # Then: support-breach emits once, other stamps re-arm, no divide-by-zero.
    assert [alert.kind for alert in equal_support.alerts] == [AlertKind.SUPPORT_BREACH]
    assert equal_support.invalid_state == InvalidRuleState.PRICE_NOT_ABOVE_SUPPORT
    assert equal_support.next_state.support_breach_active is True
    assert equal_support.next_state.support_breach_last_alert_at == OBSERVED_AT
    assert equal_support.next_state.near_support_last_alert_at is None
    assert equal_support.next_state.risk_reward_last_alert_at is None
    assert equal_support.next_state.breakout_last_alert_at is None
    assert below_support.alerts == ()
    assert below_support.invalid_state == InvalidRuleState.PRICE_NOT_ABOVE_SUPPORT
    assert below_support.next_state.support_breach_last_alert_at == OBSERVED_AT


def test_support_breach_rearms_after_price_recovers_above_support():
    # Given: a prior support breach already stamped an alert.
    breached = evaluate_rules(
        price=Decimal("99"),
        support=Decimal("100"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("3"),
        previous_state=RuleState(last_price=Decimal("101")),
        observed_at=OBSERVED_AT,
    )

    # When: price recovers above support, then breaches again.
    recovered = evaluate_rules(
        price=Decimal("105"),
        support=Decimal("100"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        previous_state=breached.next_state,
        observed_at=OBSERVED_AT + timedelta(seconds=30),
    )
    rebreached = evaluate_rules(
        price=Decimal("98"),
        support=Decimal("100"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("3"),
        previous_state=recovered.next_state,
        observed_at=OBSERVED_AT + timedelta(seconds=60),
    )

    # Then: the second breach re-fires after the rising edge re-arm.
    assert [alert.kind for alert in breached.alerts] == [AlertKind.SUPPORT_BREACH]
    assert recovered.next_state.support_breach_active is False
    assert recovered.next_state.support_breach_last_alert_at is None
    assert [alert.kind for alert in rebreached.alerts] == [AlertKind.SUPPORT_BREACH]


def test_resistance_at_or_below_price_resets_long_setup_without_risk_reward_alert():
    # Given: long risk/reward is only valid when price is below resistance.
    state = RuleState(last_price=Decimal("100"), risk_reward_active=True)

    # When: price equals resistance without crossing from below.
    evaluation = evaluate_rules(
        price=Decimal("110"),
        support=Decimal("90"),
        resistance=Decimal("110"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("3"),
        previous_state=state,
        observed_at=OBSERVED_AT,
    )

    # Then: no risk/reward alert is produced and the risk state resets.
    assert AlertKind.RISK_REWARD not in {alert.kind for alert in evaluation.alerts}
    assert evaluation.next_state.risk_reward_active is False


def test_repeated_near_support_suppressed_until_condition_resets():
    # Given: a first near-support observation has activated that rule.
    first = evaluate_rules(
        price=Decimal("100"),
        support=Decimal("98"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        previous_state=RuleState(),
        observed_at=OBSERVED_AT,
    )

    # When: the same active condition repeats, then resets, then becomes active again.
    repeated = evaluate_rules(
        price=Decimal("100.5"),
        support=Decimal("98.5"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        previous_state=first.next_state,
        observed_at=OBSERVED_AT + timedelta(seconds=30),
    )
    reset = evaluate_rules(
        price=Decimal("105"),
        support=Decimal("98"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        previous_state=repeated.next_state,
        observed_at=OBSERVED_AT + timedelta(seconds=60),
    )
    retriggered = evaluate_rules(
        price=Decimal("100"),
        support=Decimal("98"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        previous_state=reset.next_state,
        observed_at=OBSERVED_AT + timedelta(seconds=90),
    )

    # Then: duplicates while active are suppressed; re-entry after reset re-fires.
    assert [alert.kind for alert in first.alerts] == [AlertKind.NEAR_SUPPORT]
    assert repeated.alerts == ()
    assert reset.next_state.near_support_active is False
    assert reset.next_state.near_support_last_alert_at is None
    assert [alert.kind for alert in retriggered.alerts] == [AlertKind.NEAR_SUPPORT]


def test_active_near_support_never_re_alerts_while_condition_stays_true():
    # Given: near-support is already active and an alert was already emitted.
    previous_state = RuleState(
        last_price=Decimal("100"),
        near_support_active=True,
        near_support_last_alert_at=OBSERVED_AT,
    )

    # When: the active condition repeats long after the previous alert.
    still_active = evaluate_rules(
        price=Decimal("100"),
        support=Decimal("98"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        previous_state=previous_state,
        observed_at=OBSERVED_AT + timedelta(hours=24),
    )

    # Then: no second alert is emitted for that source/rule.
    assert still_active.alerts == ()


def test_rule_state_is_source_specific():
    # Given: one source has prior near-support state; another is inactive.
    active_source_state = RuleState(
        last_price=Decimal("100"),
        near_support_active=True,
        near_support_last_alert_at=OBSERVED_AT,
    )
    other_source_state = RuleState()

    # When: the same near-support price is evaluated for both source states.
    active_source = evaluate_rules(
        price=Decimal("100"),
        support=Decimal("98"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        previous_state=active_source_state,
        observed_at=OBSERVED_AT,
    )
    other_source = evaluate_rules(
        price=Decimal("100"),
        support=Decimal("98"),
        resistance=Decimal("130"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("20"),
        previous_state=other_source_state,
        observed_at=OBSERVED_AT,
    )

    # Then: dedupe is scoped to the provided source state, not the instrument globally.
    assert active_source.alerts == ()
    assert [alert.kind for alert in other_source.alerts] == [AlertKind.NEAR_SUPPORT]


def test_persistence_integration_records_alert_and_suppresses_duplicate(tmp_path: Path):
    # Given: a persisted instrument/source with no previous LastRuleState.
    engine = create_engine(
        f"sqlite:///{tmp_path / 'rules.sqlite3'}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
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

        # Then: AlertEvent is durable and LastRuleState suppresses the duplicate source alert.
        assert [alert.kind for alert in first.alerts] == [AlertKind.NEAR_SUPPORT]
        assert repeated.alerts == ()
        assert len(stored_events) == 1
        assert stored_events[0].price == Decimal("100.0000000000")


def test_support_only_emits_near_support_not_risk_reward_or_breakout():
    state = RuleState()

    evaluation = evaluate_rules(
        price=Decimal("100"),
        support=Decimal("98"),
        resistance=None,
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("3"),
        previous_state=state,
        observed_at=OBSERVED_AT,
    )

    kinds = {alert.kind for alert in evaluation.alerts}
    assert kinds == {AlertKind.NEAR_SUPPORT}
    assert evaluation.next_state.risk_reward_active is False
    assert evaluation.next_state.above_resistance_active is False


def test_resistance_only_emits_breakout_not_near_support_or_risk_reward():
    below = RuleState(last_price=Decimal("100"))

    evaluation = evaluate_rules(
        price=Decimal("111"),
        support=None,
        resistance=Decimal("110"),
        near_support_threshold=Decimal("0.02"),
        risk_reward_threshold=Decimal("3"),
        previous_state=below,
        observed_at=OBSERVED_AT,
    )

    kinds = {alert.kind for alert in evaluation.alerts}
    assert kinds == {AlertKind.RESISTANCE_BREAKOUT}
    assert evaluation.next_state.near_support_active is False
    assert evaluation.next_state.risk_reward_active is False
