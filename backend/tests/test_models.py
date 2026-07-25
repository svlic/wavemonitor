from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect
from sqlmodel import SQLModel

from wavemonitor_backend.models import (
    AlertEvent,
    AlertKind,
    Instrument,
    LastRuleState,
    MarketType,
    PriceObservation,
    Provider,
    SourceMapping,
)


def test_instrument_accepts_decimal_string_levels_and_fraction_thresholds():
    # Given: one instrument configured with exact decimal strings.
    instrument = Instrument(
        name="Bitcoin",
        support="90000.10",
        resistance="110000.25",
        near_support_threshold="0.02",
        risk_reward_threshold="3.5",
    )

    # When: the model parses the configuration.
    # Then: rule values are Decimal instances, not floats, and fractions remain fractions.
    assert instrument.support == Decimal("90000.10")
    assert instrument.resistance == Decimal("110000.25")
    assert instrument.near_support_threshold == Decimal("0.02")
    assert instrument.risk_reward_threshold == Decimal("3.5")


def test_instrument_rejects_float_only_rule_inputs():
    # Given: binary floats would introduce inexact rule arithmetic.
    # When / Then: the model rejects floats at the domain boundary.
    with pytest.raises(ValidationError, match="Decimal values must be provided as strings"):
        Instrument.model_validate(
            {
                "name": "Bitcoin",
                "support": 90000.10,
                "resistance": "110000.25",
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
                "support": "100",
                "resistance": "100",
                "near_support_threshold": "0.02",
                "risk_reward_threshold": "2",
            }
        )


def test_instrument_accepts_support_only_without_risk_reward_threshold():
    instrument = Instrument(
        name="Resistance TBD",
        support="100",
        resistance=None,
        near_support_threshold="0.02",
        risk_reward_threshold=None,
    )
    assert instrument.support == Decimal("100")
    assert instrument.resistance is None
    assert instrument.near_support_threshold == Decimal("0.02")
    assert instrument.risk_reward_threshold is None


def test_instrument_accepts_resistance_only_without_thresholds():
    instrument = Instrument(
        name="Support TBD",
        support=None,
        resistance="120",
        near_support_threshold=None,
        risk_reward_threshold=None,
    )
    assert instrument.support is None
    assert instrument.resistance == Decimal("120")
    assert instrument.near_support_threshold is None
    assert instrument.risk_reward_threshold is None


def test_instrument_rejects_support_without_near_support_threshold():
    with pytest.raises(ValidationError, match="near_support_threshold is required"):
        Instrument.model_validate(
            {
                "name": "Missing near threshold",
                "support": "100",
                "resistance": None,
                "near_support_threshold": None,
                "risk_reward_threshold": None,
            }
        )


def test_instrument_rejects_both_levels_without_risk_reward_threshold():
    with pytest.raises(ValidationError, match="risk_reward_threshold is required"):
        Instrument.model_validate(
            {
                "name": "Missing risk threshold",
                "support": "100",
                "resistance": "120",
                "near_support_threshold": "0.02",
                "risk_reward_threshold": None,
            }
        )


def test_instrument_rejects_both_levels_unset():
    with pytest.raises(ValidationError, match="at least one of support or resistance"):
        Instrument.model_validate(
            {
                "name": "No levels",
                "support": None,
                "resistance": None,
                "near_support_threshold": "0.02",
                "risk_reward_threshold": "2",
            }
        )


def test_instrument_enforces_one_support_resistance_pair():
    # Given: MVP rule config has one support and one resistance per instrument.
    instrument = Instrument(
        name="Apple",
        support="150",
        resistance="200",
        near_support_threshold="0.01",
        risk_reward_threshold="2",
    )

    # When / Then: the domain exposes exactly one scalar Decimal pair.
    assert instrument.support == Decimal("150")
    assert instrument.resistance == Decimal("200")
    assert not hasattr(instrument, "support_levels")
    assert not hasattr(instrument, "resistance_levels")


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


def test_observation_and_alert_models_keep_rule_amounts_decimal():
    # Given: persisted event-like domain objects with rule amounts.
    observation = PriceObservation(
        source_mapping_id=7,
        price="101.25",
        observed_at="2026-06-30T12:00:00Z",
    )
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
    assert observation.price == Decimal("101.25")
    assert alert.threshold == Decimal("0.02")
    assert state.last_price == Decimal("101.25")


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
