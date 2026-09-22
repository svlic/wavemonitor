from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_CEILING, Decimal
from enum import StrEnum
from typing import Final

from wavemonitor_backend.models import AlertKind
from wavemonitor_backend.support_resistance import levels_for_alerts

ZERO: Final[Decimal] = Decimal("0")
PERCENTAGE_POINT: Final[Decimal] = Decimal("0.01")


class InvalidRuleState(StrEnum):
    PRICE_NOT_ABOVE_SUPPORT = "price_not_above_support"


@dataclass(frozen=True, slots=True)
class RuleState:
    last_price: Decimal | None = None
    near_support_active: bool = False
    near_support_alert_bucket: int | None = None
    risk_reward_active: bool = False
    above_resistance_active: bool = False
    support_breach_active: bool = False
    near_support_last_alert_at: datetime | None = None
    risk_reward_last_alert_at: datetime | None = None
    breakout_last_alert_at: datetime | None = None
    support_breach_last_alert_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AlertDecision:
    kind: AlertKind
    price: Decimal
    support: Decimal
    resistance: Decimal
    threshold: Decimal | None
    metric: Decimal
    triggered_at: datetime
    message: str


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    alerts: tuple[AlertDecision, ...]
    next_state: RuleState
    invalid_state: InvalidRuleState | None


def evaluate_rules(
    *,
    price: Decimal,
    support: Decimal | None,
    resistance: Decimal | None,
    near_support_threshold: Decimal | None,
    risk_reward_threshold: Decimal | None,
    previous_state: RuleState,
    observed_at: datetime,
) -> RuleEvaluation:
    if support is not None and near_support_threshold is None:
        raise ValueError("near_support_threshold is required when support is set")
    if support is not None and resistance is not None and risk_reward_threshold is None:
        raise ValueError("risk_reward_threshold is required when support and resistance are set")

    alert_support, alert_resistance = levels_for_alerts(
        support=support, resistance=resistance, price=price
    )

    if support is not None and price < support:
        support_breach_active = True
        breach_alert = support_breach_alert(
            active=support_breach_active,
            previous_state=previous_state,
            observed_at=observed_at,
            price=price,
            support=alert_support,
            resistance=alert_resistance,
        )
        alerts = (breach_alert,) if breach_alert is not None else ()
        return RuleEvaluation(
            alerts=alerts,
            next_state=RuleState(
                last_price=price,
                support_breach_active=support_breach_active,
                # Other conditions are inactive while price is below support → re-arm.
                near_support_alert_bucket=None,
                near_support_last_alert_at=None,
                risk_reward_last_alert_at=None,
                breakout_last_alert_at=None,
                support_breach_last_alert_at=next_alert_time(
                    active=support_breach_active,
                    alerts=alerts,
                    kind=AlertKind.SUPPORT_BREACH,
                    previous=previous_state.support_breach_last_alert_at,
                ),
            ),
            invalid_state=InvalidRuleState.PRICE_NOT_ABOVE_SUPPORT,
        )

    near_support_active = False
    near_support_metric: Decimal | None = None
    if support is not None and near_support_threshold is not None:
        near_support_metric = (price - support) / price
        near_support_active = near_support_metric <= near_support_threshold
    near_support_bucket = (
        percentage_point_bucket(near_support_metric)
        if near_support_active and near_support_metric is not None
        else None
    )

    risk_reward_metric: Decimal | None = None
    risk_reward_active = False
    if support is not None and resistance is not None and risk_reward_threshold is not None:
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
                bucket=near_support_bucket,
                previous_state=previous_state,
                observed_at=observed_at,
                price=price,
                support=alert_support,
                resistance=alert_resistance,
                threshold=near_support_threshold,
                metric=near_support_metric if near_support_metric is not None else ZERO,
            )
            if support is not None and near_support_threshold is not None
            else None,
            risk_reward_alert(
                active=risk_reward_active,
                previous_state=previous_state,
                observed_at=observed_at,
                price=price,
                support=alert_support,
                resistance=alert_resistance,
                threshold=risk_reward_threshold,
                metric=risk_reward_metric,
            )
            if support is not None and resistance is not None and risk_reward_threshold is not None
            else None,
            breakout_alert(
                active=above_resistance_active,
                previous_state=previous_state,
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
            near_support_alert_bucket=next_near_support_bucket(
                active=near_support_active,
                bucket=near_support_bucket,
                alerts=alerts,
                previous=previous_state.near_support_alert_bucket,
            ),
            risk_reward_active=risk_reward_active,
            above_resistance_active=above_resistance_active,
            support_breach_active=False,
            near_support_last_alert_at=next_alert_time(
                active=near_support_active,
                alerts=alerts,
                kind=AlertKind.NEAR_SUPPORT,
                previous=previous_state.near_support_last_alert_at,
            ),
            risk_reward_last_alert_at=next_alert_time(
                active=risk_reward_active,
                alerts=alerts,
                kind=AlertKind.RISK_REWARD,
                previous=previous_state.risk_reward_last_alert_at,
            ),
            breakout_last_alert_at=next_alert_time(
                active=above_resistance_active,
                alerts=alerts,
                kind=AlertKind.RESISTANCE_BREAKOUT,
                previous=previous_state.breakout_last_alert_at,
            ),
            support_breach_last_alert_at=None,
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
    bucket: int | None,
    previous_state: RuleState,
    observed_at: datetime,
    price: Decimal,
    support: Decimal,
    resistance: Decimal,
    threshold: Decimal,
    metric: Decimal,
) -> AlertDecision | None:
    can_emit = should_emit_near_support(
        active=active,
        bucket=bucket,
        previous_state=previous_state,
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
        last_alert_at=previous_state.risk_reward_last_alert_at,
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
    observed_at: datetime,
    price: Decimal,
    support: Decimal,
    resistance: Decimal,
    resistance_level: Decimal,
) -> AlertDecision | None:
    previous_price = previous_state.last_price
    can_emit = active and (
        previous_state.breakout_last_alert_at is None
        or (previous_price is not None and previous_price <= resistance_level)
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


def support_breach_alert(
    *,
    active: bool,
    previous_state: RuleState,
    observed_at: datetime,
    price: Decimal,
    support: Decimal,
    resistance: Decimal,
) -> AlertDecision | None:
    previous_price = previous_state.last_price
    can_emit = active and (
        previous_state.support_breach_last_alert_at is None
        or (previous_price is not None and previous_price >= support)
    )
    if not can_emit:
        return None
    return AlertDecision(
        kind=AlertKind.SUPPORT_BREACH,
        price=price,
        support=support,
        resistance=resistance,
        threshold=support,
        metric=price,
        triggered_at=observed_at,
        message=f"price {price} breached support {support}",
    )


def should_emit(*, active: bool, last_alert_at: datetime | None) -> bool:
    """Emit while condition is active only if not yet stamped (edge / re-arm / retry)."""
    if not active:
        return False
    return last_alert_at is None


def percentage_point_bucket(metric: Decimal) -> int:
    return int((metric / PERCENTAGE_POINT).to_integral_value(rounding=ROUND_CEILING))


def should_emit_near_support(
    *, active: bool, bucket: int | None, previous_state: RuleState
) -> bool:
    if not active or bucket is None:
        return False
    previous_bucket = previous_state.near_support_alert_bucket
    if previous_bucket is not None:
        return bucket < previous_bucket
    # A legacy active state has an alert timestamp but no bucket.
    # Preserve its dedupe until re-armed.
    return previous_state.near_support_last_alert_at is None


def next_near_support_bucket(
    *,
    active: bool,
    bucket: int | None,
    alerts: tuple[AlertDecision, ...],
    previous: int | None,
) -> int | None:
    if not active:
        return None
    if any(alert.kind == AlertKind.NEAR_SUPPORT for alert in alerts):
        return bucket
    return previous


def next_alert_time(
    *,
    active: bool,
    alerts: tuple[AlertDecision, ...],
    kind: AlertKind,
    previous: datetime | None,
) -> datetime | None:
    """Stamp on emit; clear when inactive so the next rising edge can re-fire."""
    if not active:
        return None
    for alert in alerts:
        if alert.kind == kind:
            return alert.triggered_at
    return previous
