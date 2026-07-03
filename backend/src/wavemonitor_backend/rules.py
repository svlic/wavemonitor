from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Final

from wavemonitor_backend.models import AlertKind
from wavemonitor_backend.rule_types import DEFAULT_COOLDOWN, AlertDecision, InvalidRuleState, RuleEvaluation, RuleState
from wavemonitor_backend.support_resistance import levels_for_alerts

ZERO: Final[Decimal] = Decimal("0")


def evaluate_rules(
    *,
    price: Decimal,
    support: Decimal | None,
    resistance: Decimal | None,
    near_support_threshold: Decimal,
    risk_reward_threshold: Decimal,
    previous_state: RuleState,
    observed_at: datetime,
    cooldown: timedelta = DEFAULT_COOLDOWN,
) -> RuleEvaluation:
    alert_support, alert_resistance = levels_for_alerts(
        support=support, resistance=resistance, price=price
    )

    if support is not None and price <= support:
        return RuleEvaluation(
            alerts=(),
            next_state=RuleState(last_price=price),
            invalid_state=InvalidRuleState.PRICE_NOT_ABOVE_SUPPORT,
        )

    near_support_active = False
    near_support_metric: Decimal | None = None
    if support is not None:
        near_support_metric = (price - support) / price
        near_support_active = near_support_metric <= near_support_threshold

    risk_reward_metric: Decimal | None = None
    risk_reward_active = False
    if support is not None and resistance is not None:
        risk_reward_metric = risk_reward_ratio(price=price, support=support, resistance=resistance)
        risk_reward_active = (
            risk_reward_metric is not None and risk_reward_metric >= risk_reward_threshold
        )

    above_resistance_active = resistance is not None and price > resistance

    alerts = tuple(
        alert
        for alert in (
            near_support_alert(
                active=near_support_active,
                previous_state=previous_state,
                cooldown=cooldown,
                observed_at=observed_at,
                price=price,
                support=alert_support,
                resistance=alert_resistance,
                threshold=near_support_threshold,
                metric=near_support_metric if near_support_metric is not None else ZERO,
            )
            if support is not None
            else None,
            risk_reward_alert(
                active=risk_reward_active,
                previous_state=previous_state,
                cooldown=cooldown,
                observed_at=observed_at,
                price=price,
                support=alert_support,
                resistance=alert_resistance,
                threshold=risk_reward_threshold,
                metric=risk_reward_metric,
            )
            if support is not None and resistance is not None
            else None,
            breakout_alert(
                active=above_resistance_active,
                previous_state=previous_state,
                cooldown=cooldown,
                observed_at=observed_at,
                price=price,
                support=alert_support,
                resistance=alert_resistance,
                resistance_level=resistance,
            )
            if resistance is not None
            else None,
        )
        if alert is not None
    )
    return RuleEvaluation(
        alerts=alerts,
        next_state=RuleState(
            last_price=price,
            near_support_active=near_support_active,
            risk_reward_active=risk_reward_active,
            above_resistance_active=above_resistance_active,
            near_support_last_alert_at=next_alert_time(
                alerts=alerts,
                kind=AlertKind.NEAR_SUPPORT,
                previous=previous_state.near_support_last_alert_at,
            ),
            risk_reward_last_alert_at=next_alert_time(
                alerts=alerts,
                kind=AlertKind.RISK_REWARD,
                previous=previous_state.risk_reward_last_alert_at,
            ),
            breakout_last_alert_at=next_alert_time(
                alerts=alerts,
                kind=AlertKind.RESISTANCE_BREAKOUT,
                previous=previous_state.breakout_last_alert_at,
            ),
        ),
        invalid_state=None,
    )


def risk_reward_ratio(*, price: Decimal, support: Decimal, resistance: Decimal) -> Decimal | None:
    if price <= support or price >= resistance:
        return None
    denominator = price - support
    if denominator <= ZERO:
        return None
    return (resistance - price) / denominator


def near_support_alert(
    *,
    active: bool,
    previous_state: RuleState,
    cooldown: timedelta,
    observed_at: datetime,
    price: Decimal,
    support: Decimal,
    resistance: Decimal,
    threshold: Decimal,
    metric: Decimal,
) -> AlertDecision | None:
    can_emit = should_emit(
        active=active,
        was_active=previous_state.near_support_active,
        last_alert_at=previous_state.near_support_last_alert_at,
        observed_at=observed_at,
        cooldown=cooldown,
    )
    if not can_emit:
        return None
    return AlertDecision(
        kind=AlertKind.NEAR_SUPPORT,
        price=price,
        support=support,
        resistance=resistance,
        threshold=threshold,
        metric=metric,
        triggered_at=observed_at,
        message=f"price {price} is within {metric} of support {support}",
    )


def risk_reward_alert(
    *,
    active: bool,
    previous_state: RuleState,
    cooldown: timedelta,
    observed_at: datetime,
    price: Decimal,
    support: Decimal,
    resistance: Decimal,
    threshold: Decimal,
    metric: Decimal | None,
) -> AlertDecision | None:
    if metric is None:
        return None
    can_emit = should_emit(
        active=active,
        was_active=previous_state.risk_reward_active,
        last_alert_at=previous_state.risk_reward_last_alert_at,
        observed_at=observed_at,
        cooldown=cooldown,
    )
    if not can_emit:
        return None
    return AlertDecision(
        kind=AlertKind.RISK_REWARD,
        price=price,
        support=support,
        resistance=resistance,
        threshold=threshold,
        metric=metric,
        triggered_at=observed_at,
        message=f"risk/reward {metric} reached threshold {threshold} at price {price}",
    )


def breakout_alert(
    *,
    active: bool,
    previous_state: RuleState,
    cooldown: timedelta,
    observed_at: datetime,
    price: Decimal,
    support: Decimal,
    resistance: Decimal,
    resistance_level: Decimal,
) -> AlertDecision | None:
    previous_price = previous_state.last_price
    crossed = previous_price is not None and previous_price <= resistance_level and active
    can_emit = should_emit(
        active=crossed,
        was_active=previous_state.above_resistance_active,
        last_alert_at=previous_state.breakout_last_alert_at,
        observed_at=observed_at,
        cooldown=cooldown,
    )
    if not can_emit:
        return None
    return AlertDecision(
        kind=AlertKind.RESISTANCE_BREAKOUT,
        price=price,
        support=support,
        resistance=resistance,
        threshold=resistance_level,
        metric=price,
        triggered_at=observed_at,
        message=f"price {price} crossed resistance {resistance_level}",
    )


def should_emit(
    *,
    active: bool,
    was_active: bool,
    last_alert_at: datetime | None,
    observed_at: datetime,
    cooldown: timedelta,
) -> bool:
    del last_alert_at, observed_at, cooldown
    if not active:
        return False
    return not was_active


def next_alert_time(*, alerts: tuple[AlertDecision, ...], kind: AlertKind, previous: datetime | None) -> datetime | None:
    for alert in alerts:
        if alert.kind == kind:
            return alert.triggered_at
    return previous


from wavemonitor_backend.rule_persistence import (  # noqa: E402
    evaluate_and_persist_rules as evaluate_and_persist_rules,
    persist_rule_evaluation as persist_rule_evaluation,
)
