from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Final

from wavemonitor_backend.models import AlertKind

DEFAULT_COOLDOWN: Final[timedelta] = timedelta(minutes=5)


class InvalidRuleState(StrEnum):
    PRICE_NOT_ABOVE_SUPPORT = "price_not_above_support"


@dataclass(frozen=True, slots=True)
class RuleState:
    last_price: Decimal | None = None
    near_support_active: bool = False
    risk_reward_active: bool = False
    above_resistance_active: bool = False
    near_support_last_alert_at: datetime | None = None
    risk_reward_last_alert_at: datetime | None = None
    breakout_last_alert_at: datetime | None = None


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
