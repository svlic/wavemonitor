from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Final, assert_never

ZERO: Final[Decimal] = Decimal("0")


class AlertMode(StrEnum):
    STATIC = "static"
    FIXED_DRAWDOWN = "fixed_drawdown"


def normalize_optional_level(value: Decimal | str | int | float | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == "":
            return None
        return Decimal(stripped)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        raise ValueError("Decimal values must be provided as strings, Decimal, or integers")
    raise ValueError("Decimal values must be provided as strings, Decimal, or integers")


def derived_support(high_water: Decimal, fixed_drawdown: Decimal) -> Decimal:
    support = high_water - fixed_drawdown
    if support <= ZERO:
        raise ValueError("support must be positive")
    return support


def lift_high_water(
    *, high_water: Decimal, fixed_drawdown: Decimal, price: Decimal
) -> tuple[Decimal, Decimal, bool]:
    """Return the high-water mark, trailing support, and whether the mark was raised."""
    if price > high_water:
        return price, derived_support(price, fixed_drawdown), True
    return high_water, derived_support(high_water, fixed_drawdown), False


def validate_instrument_levels(
    *,
    support: Decimal | None,
    resistance: Decimal | None,
    alert_mode: AlertMode = AlertMode.STATIC,
    high_water: Decimal | None = None,
    fixed_drawdown: Decimal | None = None,
) -> None:
    match alert_mode:
        case AlertMode.STATIC:
            if high_water is not None or fixed_drawdown is not None:
                raise ValueError("high_water and fixed_drawdown must not be set in static mode")
            if support is None and resistance is None:
                raise ValueError("at least one of support or resistance must be set")
            if support is not None and support <= ZERO:
                raise ValueError("support must be positive when set")
            if resistance is not None and resistance <= ZERO:
                raise ValueError("resistance must be positive when set")
            if support is not None and resistance is not None and support >= resistance:
                raise ValueError("support must be less than resistance")
        case AlertMode.FIXED_DRAWDOWN:
            if high_water is None or fixed_drawdown is None:
                raise ValueError("high_water and fixed_drawdown are required")
            if fixed_drawdown <= ZERO:
                raise ValueError("fixed_drawdown must be positive")
            computed = derived_support(high_water, fixed_drawdown)
            if support is not None and support != computed:
                raise ValueError("support is derived")
            if resistance is not None and resistance <= ZERO:
                raise ValueError("resistance must be positive when set")
            if resistance is not None and computed >= resistance:
                raise ValueError("support must be less than resistance")
        case unreachable:
            assert_never(unreachable)


def levels_for_alerts(
    *, support: Decimal | None, resistance: Decimal | None, price: Decimal
) -> tuple[Decimal, Decimal]:
    """Snapshot values stored on alert rows when a level was not configured."""
    return (
        support if support is not None else price,
        resistance if resistance is not None else price,
    )
