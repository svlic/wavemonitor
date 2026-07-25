from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final, Self

from pydantic import ConfigDict, field_validator, model_validator
from sqlalchemy import Column, DateTime, Numeric, UniqueConstraint
from sqlmodel import Field, SQLModel

from wavemonitor_backend.support_resistance import (
    normalize_optional_level,
    validate_instrument_levels,
)

DECIMAL_MAX_DIGITS: Final[int] = 24
DECIMAL_PLACES: Final[int] = 10


def decimal_column(*, nullable: bool = False) -> Column[Decimal]:
    return Column(Numeric(DECIMAL_MAX_DIGITS, DECIMAL_PLACES, asdecimal=True), nullable=nullable)


def timestamp_column(*, nullable: bool = False, index: bool = False) -> Column[datetime]:
    return Column(DateTime(timezone=True), nullable=nullable, index=index)


def normalize_market_symbol(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("symbol must not be blank")
    if ":" not in normalized:
        return normalized.upper()
    prefix, symbol = normalized.split(":", maxsplit=1)
    return f"{prefix.lower()}:{symbol.upper()}"


class Provider(StrEnum):
    YFINANCE = "yfinance"
    BINANCE = "binance"
    HYPERLIQUID = "hyperliquid"


class MarketType(StrEnum):
    EQUITY = "equity"
    USD_M_FUTURES = "usd_m_futures"
    COIN_M_FUTURES = "coin_m_futures"
    PERPETUAL = "perpetual"


class AlertKind(StrEnum):
    NEAR_SUPPORT = "near_support"
    RISK_REWARD = "risk_reward"
    RESISTANCE_BREAKOUT = "resistance_breakout"
    SUPPORT_BREACH = "support_breach"


class DeliveryStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"


class RuleDecimalMixin(SQLModel):
    @field_validator("support", "resistance", mode="before", check_fields=False)
    @classmethod
    def parse_optional_level(cls, value: Decimal | str | int | float | None) -> Decimal | None:
        return normalize_optional_level(value)

    @field_validator(
        "near_support_threshold",
        "risk_reward_threshold",
        "price",
        "threshold",
        "last_price",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def parse_decimal_from_string(cls, value: Decimal | str | int | float | None) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "":
                return None
            return Decimal(stripped)
        if isinstance(value, int):
            return Decimal(value)
        raise ValueError("Decimal values must be provided as strings, Decimal, or integers")


class Instrument(RuleDecimalMixin, table=True):
    model_config = ConfigDict(validate_assignment=False)

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(min_length=1, max_length=120, index=True)
    enabled: bool = Field(default=True)
    support: Decimal | None = Field(default=None, sa_column=decimal_column(nullable=True))
    resistance: Decimal | None = Field(default=None, sa_column=decimal_column(nullable=True))
    near_support_threshold: Decimal | None = Field(
        default=None, sa_column=decimal_column(nullable=True)
    )
    risk_reward_threshold: Decimal | None = Field(
        default=None, sa_column=decimal_column(nullable=True)
    )
    created_at: datetime | None = Field(default=None, sa_column=timestamp_column(nullable=True))
    updated_at: datetime | None = Field(default=None, sa_column=timestamp_column(nullable=True))
    rule_cycle_started_at: datetime = Field(
        default=datetime.min, sa_column=timestamp_column()
    )

    @model_validator(mode="after")
    def validate_rule_contract(self) -> Self:
        self._coerce_rule_fields()
        self._assert_rule_contract()
        return self

    def model_post_init(self, __context: object) -> None:
        if self._needs_rule_field_coercion():
            self._coerce_rule_fields()
        self._assert_rule_contract()

    def _needs_rule_field_coercion(self) -> bool:
        return (
            self.support is not None
            and not isinstance(self.support, Decimal)
            or self.resistance is not None
            and not isinstance(self.resistance, Decimal)
            or self.near_support_threshold is not None
            and not isinstance(self.near_support_threshold, Decimal)
            or self.risk_reward_threshold is not None
            and not isinstance(self.risk_reward_threshold, Decimal)
        )

    def _coerce_rule_fields(self) -> None:
        self.support = normalize_optional_level(self.support)
        self.resistance = normalize_optional_level(self.resistance)
        self.near_support_threshold = self.parse_decimal_from_string(
            self.near_support_threshold
        )
        self.risk_reward_threshold = self.parse_decimal_from_string(
            self.risk_reward_threshold
        )

    def _assert_rule_contract(self) -> None:
        validate_instrument_levels(support=self.support, resistance=self.resistance)
        near = self.near_support_threshold
        risk = self.risk_reward_threshold
        if self.support is not None and near is None:
            raise ValueError("near_support_threshold is required when support is set")
        if near is not None and not Decimal("0") < near < Decimal("1"):
            raise ValueError("near_support_threshold must be a decimal fraction between 0 and 1")
        if self.support is not None and self.resistance is not None and risk is None:
            raise ValueError(
                "risk_reward_threshold is required when support and resistance are set"
            )
        if risk is not None and risk <= Decimal("0"):
            raise ValueError("risk_reward_threshold must be greater than 0")


class SourceMapping(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "provider",
            "market_type",
            "symbol",
            name="uq_source_mapping_per_instrument",
        ),
    )
    model_config = ConfigDict(validate_assignment=True)

    id: int | None = Field(default=None, primary_key=True)
    instrument_id: int = Field(foreign_key="instrument.id", index=True)
    provider: Provider = Field(index=True)
    market_type: MarketType = Field(index=True)
    symbol: str = Field(min_length=1, max_length=80, index=True)
    enabled: bool = Field(default=True)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return normalize_market_symbol(value)

    @property
    def identity_key(self) -> str:
        return f"{self.provider.value}:{self.market_type.value}:{self.symbol}"


class PriceObservation(RuleDecimalMixin, table=True):
    model_config = ConfigDict(validate_assignment=True)

    id: int | None = Field(default=None, primary_key=True)
    source_mapping_id: int = Field(foreign_key="sourcemapping.id", index=True)
    price: Decimal | None = Field(default=None, sa_column=decimal_column(nullable=True))
    observed_at: datetime = Field(sa_column=timestamp_column(index=True))
    raw_path: str | None = Field(default=None, max_length=120)
    error: str | None = Field(default=None, max_length=500)


class AlertEvent(RuleDecimalMixin, table=True):
    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "source_mapping_id",
            "alert_kind",
            "rule_cycle_started_at",
            name="uq_alert_event_source_rule_cycle",
        ),
    )
    model_config = ConfigDict(validate_assignment=True)

    id: int | None = Field(default=None, primary_key=True)
    instrument_id: int = Field(foreign_key="instrument.id", index=True)
    source_mapping_id: int = Field(foreign_key="sourcemapping.id", index=True)
    alert_kind: AlertKind = Field(index=True)
    price: Decimal = Field(sa_column=decimal_column())
    support: Decimal = Field(sa_column=decimal_column())
    resistance: Decimal = Field(sa_column=decimal_column())
    threshold: Decimal | None = Field(default=None, sa_column=decimal_column(nullable=True))
    message: str = Field(min_length=1, max_length=1000)
    triggered_at: datetime = Field(sa_column=timestamp_column())
    rule_cycle_started_at: datetime = Field(
        default=datetime.min, sa_column=timestamp_column()
    )


class LastRuleState(RuleDecimalMixin, table=True):
    __table_args__ = (
        UniqueConstraint("instrument_id", "source_mapping_id", name="uq_last_rule_state_source"),
    )
    model_config = ConfigDict(validate_assignment=True)

    id: int | None = Field(default=None, primary_key=True)
    instrument_id: int = Field(foreign_key="instrument.id", index=True)
    source_mapping_id: int = Field(foreign_key="sourcemapping.id", index=True)
    last_price: Decimal | None = Field(default=None, sa_column=decimal_column(nullable=True))
    near_support_active: bool = Field(default=False)
    risk_reward_active: bool = Field(default=False)
    above_resistance_active: bool = Field(default=False)
    support_breach_active: bool = Field(default=False)
    near_support_last_alert_at: datetime | None = Field(
        default=None,
        sa_column=timestamp_column(nullable=True),
    )
    risk_reward_last_alert_at: datetime | None = Field(
        default=None,
        sa_column=timestamp_column(nullable=True),
    )
    breakout_last_alert_at: datetime | None = Field(
        default=None,
        sa_column=timestamp_column(nullable=True),
    )
    support_breach_last_alert_at: datetime | None = Field(
        default=None,
        sa_column=timestamp_column(nullable=True),
    )
    last_invalid_state: str | None = Field(default=None, max_length=80)
    updated_at: datetime = Field(sa_column=timestamp_column())


class TelegramDelivery(SQLModel, table=True):
    model_config = ConfigDict(validate_assignment=True)

    id: int | None = Field(default=None, primary_key=True)
    status: DeliveryStatus = Field(index=True)
    message_kind: str = Field(min_length=1, max_length=40, index=True)
    message_text: str = Field(min_length=1, max_length=1000)
    chat_ref: str = Field(default="redacted", max_length=40)
    telegram_message_id: str | None = Field(default=None, max_length=120)
    safe_error: str | None = Field(default=None, max_length=500)
    delivered_at: datetime = Field(sa_column=timestamp_column())
