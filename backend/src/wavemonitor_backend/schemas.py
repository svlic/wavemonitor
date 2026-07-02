from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator

from wavemonitor_backend.models import AlertKind, MarketType, Provider, normalize_market_symbol
from wavemonitor_backend.source_pairs import validate_provider_market_pair

ZERO: Final[Decimal] = Decimal("0")
ONE: Final[Decimal] = Decimal("1")


class DecimalStringMixin(BaseModel):
    @field_validator(
        "support",
        "resistance",
        "near_support_threshold",
        "risk_reward_threshold",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def parse_decimal_string(cls, value: Decimal | str | int | float) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if isinstance(value, str):
            return Decimal(value)
        if isinstance(value, int):
            return Decimal(value)
        raise ValueError("Decimal values must be provided as strings, Decimal, or integers")

    @field_serializer("support", "resistance", "near_support_threshold", "risk_reward_threshold", check_fields=False)
    def serialize_decimal(self, value: Decimal) -> str:
        return str(value)


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


class InstrumentRequest(DecimalStringMixin):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    support: Decimal
    resistance: Decimal
    near_support_threshold: Decimal
    risk_reward_threshold: Decimal
    source_mappings: tuple[SourceMappingRequest, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_rule_contract(self) -> Self:
        if self.support >= self.resistance:
            raise ValueError("support must be less than resistance")
        if self.near_support_threshold <= ZERO or self.near_support_threshold >= ONE:
            raise ValueError("near_support_threshold must be a decimal fraction between 0 and 1")
        if self.risk_reward_threshold <= ZERO:
            raise ValueError("risk_reward_threshold must be greater than 0")
        return self


class InstrumentResponse(DecimalStringMixin):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    enabled: bool
    support: Decimal
    resistance: Decimal
    near_support_threshold: Decimal
    risk_reward_threshold: Decimal
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
