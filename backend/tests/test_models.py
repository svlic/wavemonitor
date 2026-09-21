from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel

from wavemonitor_backend.models import (
    AlertEvent,
    AlertKind,
    AlertMode,
    Instrument,
    LastRuleState,
    MarketType,
    Provider,
    SourceMapping,
)
from wavemonitor_backend.support_resistance import normalize_optional_level


@pytest.mark.parametrize("value", [0.0, 90000.10, float("inf"), float("nan")])
def test_normalize_optional_level_rejects_floats(value: float):
    with pytest.raises(ValueError) as error:
        normalize_optional_level(value)
    assert str(error.value) == ("Decimal values must be provided as strings, Decimal, or integers")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("  ", None),
        (" 1.20 ", Decimal("1.20")),
        (2, Decimal(2)),
        (Decimal("3.40"), Decimal("3.40")),
    ],
)
def test_normalize_optional_level_preserves_supported_inputs(
    value: Decimal | str | int | None,
    expected: Decimal | None,
):
    assert normalize_optional_level(value) == expected


def test_instrument_accepts_decimal_string_levels_and_fraction_thresholds():
    # Given: one instrument configured with exact decimal strings.
    instrument = Instrument(
        name="Bitcoin",
        supports=["90000.10"],
        resistances=["110000.25"],
        near_support_threshold="0.02",
        risk_reward_threshold="3.5",
    )

    # When: the model parses the configuration.
    # Then: rule values are Decimal instances, not floats, and fractions remain fractions.
    assert instrument.supports == [Decimal("90000.10")]
    assert instrument.resistances == [Decimal("110000.25")]
    assert instrument.near_support_threshold == Decimal("0.02")
    assert instrument.risk_reward_threshold == Decimal("3.5")


def test_instrument_rejects_float_only_rule_inputs():
    # Given: binary floats would introduce inexact rule arithmetic.
    # When / Then: the model rejects floats at the domain boundary.
    with pytest.raises(ValidationError, match="Decimal values must be provided as strings"):
        Instrument.model_validate(
            {
                "name": "Bitcoin",
                "supports": [90000.10],
                "resistances": ["110000.25"],
                "near_support_threshold": "0.02",
                "risk_reward_threshold": "3.5",
            }
        )


def test_instrument_rejects_support_greater_than_or_equal_to_resistance():
    # Given: an invalid support/resistance pair.
    # When / Then: validation rejects the rule contract.
    with pytest.raises(ValidationError, match="support must be less than resistance"):
        Instrument.model_validate(
            {
                "name": "Broken range",
                "supports": ["100"],
                "resistances": ["100"],
                "near_support_threshold": "0.02",
                "risk_reward_threshold": "2",
            }
        )


def test_instrument_rejects_overlapping_multi_level_range():
    # Given: the highest support sits at or above the lowest resistance.
    # When / Then: validation rejects the range even when other levels are ordered.
    with pytest.raises(ValidationError, match="support must be less than resistance"):
        Instrument.model_validate(
            {
                "name": "Overlapping bands",
                "supports": ["90", "110"],
                "resistances": ["105", "130"],
                "near_support_threshold": "0.02",
                "risk_reward_threshold": "2",
            }
        )


def test_instrument_accepts_support_only_without_risk_reward_threshold():
    instrument = Instrument(
        name="Resistance TBD",
        supports=["100"],
        resistances=[],
        near_support_threshold="0.02",
        risk_reward_threshold=None,
    )
    assert instrument.supports == [Decimal("100")]
    assert instrument.resistances == []
    assert instrument.near_support_threshold == Decimal("0.02")
    assert instrument.risk_reward_threshold is None


def test_instrument_accepts_resistance_only_without_thresholds():
    instrument = Instrument(
        name="Support TBD",
        supports=[],
        resistances=["120"],
        near_support_threshold=None,
        risk_reward_threshold=None,
    )
    assert instrument.supports == []
    assert instrument.resistances == [Decimal("120")]
    assert instrument.near_support_threshold is None
    assert instrument.risk_reward_threshold is None


def test_instrument_rejects_support_without_near_support_threshold():
    with pytest.raises(ValidationError, match="near_support_threshold is required"):
        Instrument.model_validate(
            {
                "name": "Missing near threshold",
                "supports": ["100"],
                "resistances": [],
                "near_support_threshold": None,
                "risk_reward_threshold": None,
            }
        )


def test_instrument_rejects_both_levels_without_risk_reward_threshold():
    with pytest.raises(ValidationError, match="risk_reward_threshold is required"):
        Instrument.model_validate(
            {
                "name": "Missing risk threshold",
                "supports": ["100"],
                "resistances": ["120"],
                "near_support_threshold": "0.02",
                "risk_reward_threshold": None,
            }
        )


def test_instrument_rejects_both_levels_unset():
    with pytest.raises(ValidationError, match="at least one of support or resistance"):
        Instrument.model_validate(
            {
                "name": "No levels",
                "supports": [],
                "resistances": [],
                "near_support_threshold": "0.02",
                "risk_reward_threshold": "2",
            }
        )


def test_instrument_defaults_to_static_alert_mode():
    # Given: a legacy-style instrument with no explicit alert mode.
    instrument = Instrument(
        name="Bitcoin",
        supports=["90000.10"],
        resistances=["110000.25"],
        near_support_threshold="0.02",
        risk_reward_threshold="3.5",
    )

    # When / Then: existing rows stay on static support/resistance.
    assert instrument.alert_mode is AlertMode.STATIC
    assert instrument.high_water is None
    assert instrument.fixed_drawdown is None


def test_instrument_derives_support_from_high_water_minus_fixed_drawdown():
    # Given: a fixed-drawdown instrument with an initial high water and absolute drawdown.
    instrument = Instrument(
        name="Bitcoin trail",
        alert_mode=AlertMode.FIXED_DRAWDOWN,
        high_water="100000",
        fixed_drawdown="5000",
        resistances=["120000"],
        near_support_threshold="0.02",
        risk_reward_threshold="3.5",
    )

    # When / Then: support is derived and stored as high water minus drawdown.
    assert instrument.supports == [Decimal("95000")]
    assert instrument.high_water == Decimal("100000")
    assert instrument.fixed_drawdown == Decimal("5000")


def test_instrument_rejects_client_support_in_fixed_drawdown_mode():
    # Given: a drawdown instrument that also tries to set support directly.
    # When / Then: the domain rejects client-owned support in this mode.
    with pytest.raises(ValidationError, match="support is derived"):
        Instrument.model_validate(
            {
                "name": "Bitcoin trail",
                "alert_mode": "fixed_drawdown",
                "supports": ["90000"],
                "high_water": "100000",
                "fixed_drawdown": "5000",
                "near_support_threshold": "0.02",
            }
        )


def test_instrument_requires_high_water_and_drawdown_in_fixed_drawdown_mode():
    with pytest.raises(ValidationError, match="high_water and fixed_drawdown are required"):
        Instrument.model_validate(
            {
                "name": "Bitcoin trail",
                "alert_mode": "fixed_drawdown",
                "near_support_threshold": "0.02",
            }
        )


def test_instrument_rejects_non_positive_fixed_drawdown():
    with pytest.raises(ValidationError, match="fixed_drawdown must be positive"):
        Instrument.model_validate(
            {
                "name": "Bitcoin trail",
                "alert_mode": "fixed_drawdown",
                "high_water": "100000",
                "fixed_drawdown": "0",
                "near_support_threshold": "0.02",
            }
        )


def test_instrument_rejects_derived_support_that_is_not_positive():
    with pytest.raises(ValidationError, match="support must be positive"):
        Instrument.model_validate(
            {
                "name": "Bitcoin trail",
                "alert_mode": "fixed_drawdown",
                "high_water": "100",
                "fixed_drawdown": "100",
                "near_support_threshold": "0.02",
            }
        )


def test_instrument_rejects_drawdown_fields_in_static_mode():
    with pytest.raises(ValidationError, match="high_water and fixed_drawdown"):
        Instrument.model_validate(
            {
                "name": "Bitcoin",
                "alert_mode": "static",
                "supports": ["90000"],
                "high_water": "100000",
                "fixed_drawdown": "5000",
                "near_support_threshold": "0.02",
            }
        )


def test_instrument_accepts_multiple_supports_and_resistances():
    # Given: a static instrument with more than one support and resistance.
    instrument = Instrument(
        name="Apple",
        supports=["140", "150"],
        resistances=["200", "220"],
        near_support_threshold="0.01",
        risk_reward_threshold="2",
    )

    # When / Then: the domain stores Decimal arrays, not a scalar pair.
    assert instrument.supports == [Decimal("140"), Decimal("150")]
    assert instrument.resistances == [Decimal("200"), Decimal("220")]


def test_instrument_rejects_multiple_resistances_in_fixed_drawdown_mode():
    # Given: fixed_drawdown still owns a single derived support and at most one resistance.
    # When / Then: extra resistances are rejected.
    with pytest.raises(ValidationError, match="fixed_drawdown accepts at most one resistance"):
        Instrument.model_validate(
            {
                "name": "Bitcoin trail",
                "alert_mode": "fixed_drawdown",
                "high_water": "100000",
                "fixed_drawdown": "5000",
                "resistances": ["120000", "130000"],
                "near_support_threshold": "0.02",
                "risk_reward_threshold": "3.5",
            }
        )


def test_source_mapping_identity_is_provider_market_type_and_symbol():
    # Given: two mappings for the same provider/symbol but different market types.
    spot_like = SourceMapping(
        instrument_id=1,
        provider=Provider.BINANCE,
        market_type=MarketType.USD_M_FUTURES,
        symbol="BTCUSDT",
    )
    coin_m = SourceMapping(
        instrument_id=1,
        provider=Provider.BINANCE,
        market_type=MarketType.COIN_M_FUTURES,
        symbol="BTCUSD_PERP",
    )

    # When / Then: stable identity is provider + market type + normalized symbol.
    assert spot_like.identity_key == "binance:usd_m_futures:BTCUSDT"
    assert coin_m.identity_key == "binance:coin_m_futures:BTCUSD_PERP"


def test_source_mapping_preserves_hyperliquid_dex_prefix_case():
    # Given: a Hyperliquid HIP-3 symbol uses the SDK-required dex:coin format.
    mapping = SourceMapping(
        instrument_id=1,
        provider=Provider.HYPERLIQUID,
        market_type=MarketType.PERPETUAL,
        symbol="XYZ:crcl",
    )

    # When / Then: only the coin is uppercased; the dex prefix remains lowercase for API routing.
    assert mapping.symbol == "xyz:CRCL"
    assert mapping.identity_key == "hyperliquid:perpetual:xyz:CRCL"


def test_alert_and_rule_state_models_keep_rule_amounts_decimal():
    # Given: persisted event-like domain objects with rule amounts.
    alert = AlertEvent(
        instrument_id=3,
        source_mapping_id=7,
        alert_kind=AlertKind.NEAR_SUPPORT,
        price="101.25",
        support="100.00",
        resistance="130.00",
        threshold="0.02",
        message="BTC is near support",
        triggered_at="2026-06-30T12:00:00Z",
    )
    state = LastRuleState(
        instrument_id=3,
        source_mapping_id=7,
        last_price="101.25",
        near_support_active=True,
        risk_reward_active=False,
        above_resistance_active=False,
        updated_at="2026-06-30T12:00:00Z",
    )

    # When / Then: Decimal values survive parsing across model contracts.
    assert alert.threshold == Decimal("0.02")
    assert state.last_price == Decimal("101.25")


def test_database_schema_excludes_transient_price_observations():
    # Given: metadata for the current persistence models.
    engine = create_engine("sqlite:///:memory:")

    # When: the schema is created.
    SQLModel.metadata.create_all(engine)

    # Then: transient prices do not get a database table.
    assert "priceobservation" not in inspect(engine).get_table_names()


def test_database_schema_does_not_persist_telegram_credentials():
    # Given: metadata for all Todo 2 persistence models.
    engine = create_engine("sqlite:///:memory:")

    # When: the schema is created and inspected.
    SQLModel.metadata.create_all(engine)
    columns_by_table = {
        table_name: {column["name"] for column in inspect(engine).get_columns(table_name)}
        for table_name in inspect(engine).get_table_names()
    }

    # Then: no table has Telegram token/chat-id credential columns.
    forbidden_fragments = ("token", "chat_id", "bot_token")
    persisted_columns = {
        f"{table_name}.{column_name}"
        for table_name, column_names in columns_by_table.items()
        for column_name in column_names
    }
    assert all(
        fragment not in column_name
        for column_name in persisted_columns
        for fragment in forbidden_fragments
    )
