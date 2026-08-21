from decimal import Decimal

import pytest

from wavemonitor_backend.models import AlertMode
from wavemonitor_backend.support_resistance import (
    derived_support,
    lift_high_water,
    validate_instrument_levels,
)


def test_derived_support_is_high_water_minus_fixed_drawdown():
    # Given: an absolute drawdown from a high-water mark.
    # When: support is derived.
    # Then: the result is the price difference, not a percentage.
    assert derived_support(
        high_water=Decimal("100000"),
        fixed_drawdown=Decimal("5000"),
    ) == Decimal("95000")


def test_derived_support_rejects_non_positive_result():
    with pytest.raises(ValueError, match="support must be positive"):
        derived_support(high_water=Decimal("100"), fixed_drawdown=Decimal("100"))


def test_lift_high_water_raises_mark_when_price_exceeds_it():
    # Given: latest price breaks the current high water.
    # When: the high-water helper runs.
    # Then: high water becomes the latest price and support trails by the same drawdown.
    high_water, support, lifted = lift_high_water(
        high_water=Decimal("100000"),
        fixed_drawdown=Decimal("5000"),
        price=Decimal("101250"),
    )

    assert lifted is True
    assert high_water == Decimal("101250")
    assert support == Decimal("96250")


def test_lift_high_water_keeps_mark_when_price_does_not_exceed_it():
    high_water, support, lifted = lift_high_water(
        high_water=Decimal("100000"),
        fixed_drawdown=Decimal("5000"),
        price=Decimal("100000"),
    )

    assert lifted is False
    assert high_water == Decimal("100000")
    assert support == Decimal("95000")


def test_validate_instrument_levels_accepts_fixed_drawdown_without_client_support():
    validate_instrument_levels(
        alert_mode=AlertMode.FIXED_DRAWDOWN,
        support=Decimal("95000"),
        resistance=Decimal("120000"),
        high_water=Decimal("100000"),
        fixed_drawdown=Decimal("5000"),
    )


def test_validate_instrument_levels_still_requires_a_level_in_static_mode():
    with pytest.raises(ValueError, match="at least one of support or resistance"):
        validate_instrument_levels(
            alert_mode=AlertMode.STATIC,
            support=None,
            resistance=None,
        )
