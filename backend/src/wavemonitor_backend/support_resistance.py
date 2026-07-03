from __future__ import annotations

from decimal import Decimal
from typing import Final

ZERO: Final[Decimal] = Decimal("0")


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


def validate_instrument_levels(*, support: Decimal | None, resistance: Decimal | None) -> None:
    if support is None and resistance is None:
        raise ValueError("at least one of support or resistance must be set")
    if support is not None and support <= ZERO:
        raise ValueError("support must be positive when set")
    if resistance is not None and resistance <= ZERO:
        raise ValueError("resistance must be positive when set")
    if support is not None and resistance is not None and support >= resistance:
        raise ValueError("support must be less than resistance")


def levels_for_alerts(
    *, support: Decimal | None, resistance: Decimal | None, price: Decimal
) -> tuple[Decimal, Decimal]:
    """Snapshot values stored on alert rows when a level was not configured."""
    return (
        support if support is not None else price,
        resistance if resistance is not None else price,
    )