from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Final, Self, assert_never

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from wavemonitor_backend.models import AlertKind, MarketType, Provider, normalize_market_symbol
from wavemonitor_backend.source_pairs import validate_provider_market_pair
from wavemonitor_backend.support_resistance import (
    AlertMode,
    derived_support,
    normalize_optional_level,
    validate_instrument_levels,
)

ZERO: Final[Decimal] = Decimal("0")
ONE: Final[Decimal] = Decimal("1")


class InstrumentLevelMixin(BaseModel):
    @field_validator(
        "high_water",
        "fixed_drawdown",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def parse_optional_level(cls, value: Decimal | str | int | float | None) -> Decimal | None:
        return normalize_optional_level(value)

    @field_serializer("high_water", "fixed_drawdown", check_fields=False)
    def serialize_optional_level(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)

    @field_validator("supports", "resistances", mode="before", check_fields=False)
    @classmethod
    def parse_levels(
        cls,
        value: list[Decimal | str | int | float] | tuple[Decimal | str | int | float, ...],
    ) -> list[Decimal]:
        levels: list[Decimal] = []
        for item in value:
            level = normalize_optional_level(item)
            if level is not None:
                levels.append(level)
        return levels

    @field_serializer("supports", "resistances", check_fields=False)
    def serialize_levels(self, value: list[Decimal]) -> list[str]:
        return [str(level) for level in value]


class DecimalStringMixin(BaseModel):
    @field_validator(
        "near_support_threshold",
        "risk_reward_threshold",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def parse_decimal_string(cls, value: Decimal | str | int | float | None) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            return None if stripped == "" else Decimal(stripped)
        if isinstance(value, int):
            return Decimal(value)
        raise ValueError("Decimal values must be provided as strings, Decimal, or integers")

    @field_serializer("near_support_threshold", "risk_reward_threshold", check_fields=False)
    def serialize_decimal(self, value: Decimal | None) -> str | None:
        return None if value is None else str(value)


class SourceMappingRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: Provider
    market_type: MarketType
    symbol: str = Field(min_length=1, max_length=80)
    enabled: bool = True

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return normalize_market_symbol(value)

    @model_validator(mode="after")
    def validate_adapter_pair(self) -> Self:
        validate_provider_market_pair(self.provider, self.market_type)
        return self


class SourceMappingResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    provider: Provider
    market_type: MarketType
    symbol: str
    enabled: bool


class InstrumentRequest(InstrumentLevelMixin, DecimalStringMixin):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    alert_mode: AlertMode = AlertMode.STATIC
    supports: list[Decimal] = Field(default_factory=list)
    resistances: list[Decimal] = Field(default_factory=list)
    high_water: Decimal | None = None
    fixed_drawdown: Decimal | None = None
    near_support_threshold: Decimal | None = None
    risk_reward_threshold: Decimal | None = None
    source_mappings: tuple[SourceMappingRequest, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_rule_contract(self) -> Self:
        validate_instrument_levels(
            supports=self.supports,
            resistances=self.resistances,
            alert_mode=self.alert_mode,
            high_water=self.high_water,
            fixed_drawdown=self.fixed_drawdown,
        )
        has_support = bool(self.supports)
        match self.alert_mode:
            case AlertMode.STATIC:
                pass
            case AlertMode.FIXED_DRAWDOWN:
                if self.supports:
                    raise ValueError("support is derived")
                if self.high_water is not None and self.fixed_drawdown is not None:
                    derived_support(self.high_water, self.fixed_drawdown)
                    has_support = True
            case unreachable:
                assert_never(unreachable)
        if has_support and self.near_support_threshold is None:
            raise ValueError("near_support_threshold is required when support is set")
        if self.near_support_threshold is not None and not ZERO < self.near_support_threshold < ONE:
            raise ValueError("near_support_threshold must be a decimal fraction between 0 and 1")
        if has_support and self.resistances and self.risk_reward_threshold is None:
            raise ValueError(
                "risk_reward_threshold is required when support and resistance are set"
            )
        if self.risk_reward_threshold is not None and self.risk_reward_threshold <= ZERO:
            raise ValueError("risk_reward_threshold must be greater than 0")
        return self


class InstrumentEnabledPatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool


class InstrumentResponse(InstrumentLevelMixin, DecimalStringMixin):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    enabled: bool
    alert_mode: AlertMode
    supports: list[Decimal]
    resistances: list[Decimal]
    high_water: Decimal | None = None
    fixed_drawdown: Decimal | None = None
    near_support_threshold: Decimal | None = None
    risk_reward_threshold: Decimal | None = None
    source_mappings: tuple[SourceMappingResponse, ...]


class SourceStatusResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    provider: Provider
    market_type: MarketType
    symbol: str
    enabled: bool
    last_price: str | None
    last_observed_at: datetime | None
    last_error: str | None
    last_invalid_state: str | None = None


class LatestPriceResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_id: int
    instrument_name: str
    source_mapping_id: int
    provider: Provider
    market_type: MarketType
    symbol: str
    last_price: str
    last_observed_at: datetime
    last_error: str | None
    support_breached: bool
    resistance_broken: bool


class SourceErrorResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_id: int
    instrument_name: str
    source_mapping_id: int
    provider: Provider
    market_type: MarketType
    symbol: str
    last_observed_at: datetime
    last_error: str


class AlertResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    instrument_id: int
    source_mapping_id: int
    alert_kind: AlertKind
    price: str
    message: str
    triggered_at: datetime


class InstrumentStatusResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument_id: int
    enabled: bool
    sources: tuple[SourceStatusResponse, ...]
    recent_alerts: tuple[AlertResponse, ...]
