"""
test_risk_rules.py
-----------------------
Purpose:
    Unit tests for the three Risk Engine Part 3 concrete
    `strategies.risk_management.base.BaseRiskManager` implementations:
    `PositionSizeRule`, `StopLossRule`, and `TakeProfitRule`.

    Complements `tests/test_risk_management.py` (Part 1 foundation) and
    `tests/test_basic_risk_manager.py` (Part 2, `BasicRiskManager`),
    both left untouched here.

Coverage areas per rule:
    - Construction / configuration validation.
    - `validate_context()` shared behavior (inherited from
      `BaseRiskManager`).
    - Normal-path evaluation (BUY/SELL, ATR available, reference price
      available).
    - Edge cases (fallback to percentage-based distance, missing
      optional data, clamping/capping behavior, HOLD short-circuit).
    - Invalid input (non-numeric/non-finite `signal.confidence`, wrong
      context type, unresolvable required data).
    - `metadata` shape/traceability.
    - `confidence` behavior (degrades gracefully with missing optional
      data, never raises for it).
    - Rule independence (each rule does not import or depend on the
      others; running one does not require or mutate state from
      another).

Uses the standard-library ``unittest`` framework, matching every other
test file in this suite (no external test-runner dependency).

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import math
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from core.entities.candle import Candle
from core.entities.indicator_result import IndicatorResult
from core.entities.market_state import MarketState
from core.entities.portfolio import Portfolio
from core.entities.position import Position
from core.entities.signal import Signal
from core.enums import PositionSide, PositionStatus, SignalDirection
from strategies.risk_management import (
    BaseRiskManager,
    InsufficientRiskDataError,
    InvalidRiskContextError,
    PositionSizeRule,
    RiskContext,
    RiskManagerConfigurationError,
    RiskResult,
    StopLossRule,
    TakeProfitRule,
)

NOW = datetime.now(timezone.utc)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
def make_signal(
    *,
    direction: SignalDirection = SignalDirection.BUY,
    confidence: float = 0.8,
    metadata: dict | None = None,
) -> Signal:
    return Signal(
        signal_id="sig-1",
        symbol="BTCUSDT",
        direction=direction,
        confidence=confidence,
        source="TechnicalSignalGenerator",
        timeframe="1h",
        generated_at=NOW,
        metadata=metadata or {},
    )


def make_position(
    *,
    quantity: Decimal = Decimal("1"),
    entry_price: Decimal = Decimal("100"),
    current_price: Decimal | None = Decimal("100"),
) -> Position:
    return Position(
        position_id="pos-1",
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        entry_price=entry_price,
        quantity=quantity,
        opened_at=NOW,
        status=PositionStatus.OPEN,
        current_price=current_price,
    )


def make_portfolio(
    *,
    cash_balance: Decimal = Decimal("10000"),
    positions: list[Position] | None = None,
    total_equity: Decimal | None = None,
) -> Portfolio:
    return Portfolio(
        portfolio_id="portfolio-1",
        base_currency="USDT",
        cash_balance=cash_balance,
        positions=positions or [],
        total_equity=total_equity,
    )


def make_atr_indicator(
    *, value: float = 5.0, name: str = "ATR_14"
) -> IndicatorResult:
    return IndicatorResult(
        indicator_name=name,
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=NOW,
        values={"value": value},
        parameters={"period": 14},
    )


def make_candle(*, close: Decimal = Decimal("105")) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        timeframe="1h",
        open_time=NOW,
        close_time=NOW,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("95"),
        close=close,
        volume=Decimal("1000"),
    )


def make_market_state(
    *,
    latest_candle: Candle | None = None,
    indicators: list[IndicatorResult] | None = None,
    include_candle: bool = True,
) -> MarketState:
    return MarketState(
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=NOW,
        latest_candle=(latest_candle if latest_candle is not None else make_candle())
        if include_candle
        else None,
        indicators=indicators or [],
    )


def make_context(
    *,
    signal: Signal | None = None,
    portfolio: Portfolio | None = None,
    market_state: MarketState | None = None,
) -> RiskContext:
    return RiskContext(
        symbol="BTCUSDT",
        timeframe="1h",
        signal=signal if signal is not None else make_signal(),
        portfolio=portfolio if portfolio is not None else make_portfolio(),
        market_state=market_state,
    )


# ========================================================================
# PositionSizeRule
# ========================================================================
class TestPositionSizeRuleConstruction(unittest.TestCase):
    def test_default_construction(self):
        rule = PositionSizeRule()
        self.assertEqual(rule.name, "PositionSizeRule")
        self.assertIsInstance(rule, BaseRiskManager)

    def test_custom_name(self):
        rule = PositionSizeRule(name="MySizer")
        self.assertEqual(rule.name, "MySizer")

    def test_custom_configuration_accepted(self):
        rule = PositionSizeRule(
            risk_per_trade=0.02,
            max_position_fraction=0.5,
            default_stop_distance_pct=0.03,
            atr_multiplier=1.5,
            min_signal_confidence=0.4,
            atr_indicator_name="ATR_20",
        )
        self.assertEqual(rule.risk_per_trade, 0.02)
        self.assertEqual(rule.max_position_fraction, 0.5)
        self.assertEqual(rule.atr_multiplier, 1.5)
        self.assertEqual(rule.atr_indicator_name, "ATR_20")

    def test_rejects_non_numeric_risk_per_trade(self):
        with self.assertRaises(RiskManagerConfigurationError):
            PositionSizeRule(risk_per_trade="high")  # type: ignore[arg-type]

    def test_rejects_bool_risk_per_trade(self):
        with self.assertRaises(RiskManagerConfigurationError):
            PositionSizeRule(risk_per_trade=True)  # type: ignore[arg-type]

    def test_rejects_out_of_range_risk_per_trade(self):
        with self.assertRaises(RiskManagerConfigurationError):
            PositionSizeRule(risk_per_trade=0.0)
        with self.assertRaises(RiskManagerConfigurationError):
            PositionSizeRule(risk_per_trade=1.5)

    def test_rejects_out_of_range_max_position_fraction(self):
        with self.assertRaises(RiskManagerConfigurationError):
            PositionSizeRule(max_position_fraction=-0.1)

    def test_rejects_non_positive_atr_multiplier(self):
        with self.assertRaises(RiskManagerConfigurationError):
            PositionSizeRule(atr_multiplier=0.0)
        with self.assertRaises(RiskManagerConfigurationError):
            PositionSizeRule(atr_multiplier=-2.0)

    def test_rejects_non_numeric_atr_multiplier(self):
        with self.assertRaises(RiskManagerConfigurationError):
            PositionSizeRule(atr_multiplier="big")  # type: ignore[arg-type]

    def test_rejects_empty_atr_indicator_name(self):
        with self.assertRaises(RiskManagerConfigurationError):
            PositionSizeRule(atr_indicator_name="")
        with self.assertRaises(RiskManagerConfigurationError):
            PositionSizeRule(atr_indicator_name="   ")

    def test_rejects_non_string_atr_indicator_name(self):
        with self.assertRaises(RiskManagerConfigurationError):
            PositionSizeRule(atr_indicator_name=123)  # type: ignore[arg-type]


class TestPositionSizeRuleContextValidation(unittest.TestCase):
    def test_evaluate_rejects_non_risk_context(self):
        rule = PositionSizeRule()
        with self.assertRaises(InvalidRiskContextError):
            rule.evaluate("not-a-context")  # type: ignore[arg-type]

    def test_evaluate_rejects_none_context(self):
        rule = PositionSizeRule()
        with self.assertRaises(InvalidRiskContextError):
            rule.evaluate(None)  # type: ignore[arg-type]


class TestPositionSizeRuleNormalBehavior(unittest.TestCase):
    def test_returns_risk_result(self):
        rule = PositionSizeRule()
        result = rule.evaluate(make_context())
        self.assertIsInstance(result, RiskResult)

    def test_buy_signal_with_atr_and_reference_price_is_sized(self):
        rule = PositionSizeRule()
        context = make_context(
            market_state=make_market_state(indicators=[make_atr_indicator(value=2.0)])
        )
        result = rule.evaluate(context)
        self.assertTrue(result.approved)
        self.assertIsNotNone(result.metadata["recommended_position_size"])
        self.assertEqual(result.metadata["basis"], "atr")

    def test_sell_signal_is_sized_the_same_way(self):
        rule = PositionSizeRule()
        context = make_context(
            signal=make_signal(direction=SignalDirection.SELL),
            market_state=make_market_state(indicators=[make_atr_indicator(value=2.0)]),
        )
        result = rule.evaluate(context)
        self.assertTrue(result.approved)
        self.assertEqual(result.metadata["signal_direction"], "sell")

    def test_position_value_scales_with_equity(self):
        rule = PositionSizeRule()
        small = rule.evaluate(
            make_context(portfolio=make_portfolio(cash_balance=Decimal("1000")))
        )
        large = rule.evaluate(
            make_context(portfolio=make_portfolio(cash_balance=Decimal("100000")))
        )
        small_value = Decimal(small.metadata["recommended_position_value"])
        large_value = Decimal(large.metadata["recommended_position_value"])
        self.assertLess(small_value, large_value)

    def test_falls_back_to_default_pct_without_atr(self):
        rule = PositionSizeRule()
        context = make_context(market_state=make_market_state(indicators=[]))
        result = rule.evaluate(context)
        self.assertEqual(result.metadata["basis"], "default_pct")
        self.assertFalse(result.metadata["atr_available"])


class TestPositionSizeRuleEdgeCases(unittest.TestCase):
    def test_hold_signal_short_circuits_to_unapproved_zero_size(self):
        rule = PositionSizeRule()
        context = make_context(signal=make_signal(direction=SignalDirection.HOLD))
        result = rule.evaluate(context)
        self.assertFalse(result.approved)
        self.assertEqual(result.risk_score, 0.0)
        self.assertIsNone(result.metadata["recommended_position_size"])
        self.assertIsNone(result.metadata["recommended_position_value"])
        self.assertEqual(result.metadata["reason"], "hold_signal")

    def test_no_market_state_falls_back_to_default_and_no_reference_price(self):
        rule = PositionSizeRule()
        context = make_context(market_state=None)
        result = rule.evaluate(context)
        self.assertFalse(result.metadata["atr_available"])
        self.assertFalse(result.metadata["reference_price_available"])
        self.assertIsNone(result.metadata["recommended_position_size"])
        # Quote-currency value is still reported even without a price.
        self.assertIsNotNone(result.metadata["recommended_position_value"])

    def test_entry_price_override_used_over_candle_close(self):
        rule = PositionSizeRule()
        context = make_context(
            signal=make_signal(metadata={"entry_price": 50.0}),
            market_state=make_market_state(),
        )
        result = rule.evaluate(context)
        self.assertEqual(result.metadata["reference_price"], 50.0)
        self.assertEqual(
            result.metadata["reference_price_source"], "signal_metadata_entry_price"
        )

    def test_capped_by_max_position_fraction(self):
        rule = PositionSizeRule(
            risk_per_trade=0.9,
            max_position_fraction=0.1,
            default_stop_distance_pct=0.001,
        )
        result = rule.evaluate(make_context())
        self.assertTrue(result.metadata["capped_by_max_fraction"])
        max_value = Decimal(result.metadata["equity_used"]) * Decimal("0.1")
        self.assertEqual(Decimal(result.metadata["recommended_position_value"]), max_value)

    def test_rejected_when_signal_confidence_below_minimum(self):
        rule = PositionSizeRule(min_signal_confidence=0.9)
        context = make_context(signal=make_signal(confidence=0.5))
        result = rule.evaluate(context)
        self.assertFalse(result.approved)
        self.assertIn(
            "signal_confidence", result.metadata["hard_reject_reasons"][0]
        )

    def test_out_of_range_confidence_is_clamped_not_rejected(self):
        rule = PositionSizeRule()
        context = make_context(signal=make_signal(confidence=1.5))
        result = rule.evaluate(context)
        self.assertEqual(result.metadata["signal_confidence"], 1.0)
        self.assertTrue(result.metadata["signal_confidence_clamped"])

    def test_negative_confidence_is_clamped_to_zero(self):
        rule = PositionSizeRule()
        context = make_context(signal=make_signal(confidence=-0.5))
        result = rule.evaluate(context)
        self.assertEqual(result.metadata["signal_confidence"], 0.0)

    def test_zero_or_negative_atr_value_treated_as_unavailable(self):
        rule = PositionSizeRule()
        context = make_context(
            market_state=make_market_state(indicators=[make_atr_indicator(value=-1.0)])
        )
        result = rule.evaluate(context)
        self.assertFalse(result.metadata["atr_available"])

    def test_positions_with_missing_current_price_fall_back_to_entry_price(self):
        rule = PositionSizeRule()
        position = make_position(current_price=None)
        context = make_context(
            portfolio=make_portfolio(positions=[position], total_equity=None)
        )
        result = rule.evaluate(context)
        # Should not raise; equity is cash_balance + entry_price*qty.
        self.assertIsInstance(result, RiskResult)


class TestPositionSizeRuleInvalidInput(unittest.TestCase):
    def test_raises_on_non_numeric_signal_confidence(self):
        rule = PositionSizeRule()
        context = make_context(signal=make_signal(confidence="high"))  # type: ignore[arg-type]
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)

    def test_raises_on_nan_signal_confidence(self):
        rule = PositionSizeRule()
        context = make_context(signal=make_signal(confidence=float("nan")))
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)

    def test_raises_on_infinite_signal_confidence(self):
        rule = PositionSizeRule()
        context = make_context(signal=make_signal(confidence=float("inf")))
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)

    def test_raises_on_bool_signal_confidence(self):
        rule = PositionSizeRule()
        context = make_context(signal=make_signal(confidence=True))  # type: ignore[arg-type]
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)

    def test_raises_on_non_positive_equity(self):
        rule = PositionSizeRule()
        context = make_context(
            portfolio=make_portfolio(cash_balance=Decimal("0"), total_equity=None)
        )
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)

    def test_raises_on_negative_equity(self):
        rule = PositionSizeRule()
        context = make_context(
            portfolio=make_portfolio(total_equity=Decimal("-500"))
        )
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)


class TestPositionSizeRuleMetadata(unittest.TestCase):
    def test_metadata_contains_expected_keys(self):
        rule = PositionSizeRule()
        result = rule.evaluate(make_context())
        expected_keys = {
            "risk_manager",
            "signal_direction",
            "signal_confidence",
            "signal_confidence_clamped",
            "equity_used",
            "risk_amount",
            "reference_price",
            "reference_price_available",
            "reference_price_source",
            "atr_available",
            "atr_value",
            "atr_indicator_name",
            "stop_distance_ratio",
            "basis",
            "recommended_position_value",
            "recommended_position_size",
            "capped_by_max_fraction",
            "config",
            "hard_reject_reasons",
        }
        self.assertTrue(expected_keys.issubset(result.metadata.keys()))

    def test_metadata_config_reflects_constructor_args(self):
        rule = PositionSizeRule(risk_per_trade=0.05, max_position_fraction=0.4)
        result = rule.evaluate(make_context())
        self.assertEqual(result.metadata["config"]["risk_per_trade"], 0.05)
        self.assertEqual(result.metadata["config"]["max_position_fraction"], 0.4)

    def test_metadata_risk_manager_name_matches_instance(self):
        rule = PositionSizeRule(name="CustomSizer")
        result = rule.evaluate(make_context())
        self.assertEqual(result.metadata["risk_manager"], "CustomSizer")


class TestPositionSizeRuleConfidence(unittest.TestCase):
    def test_confidence_within_unit_range(self):
        rule = PositionSizeRule()
        result = rule.evaluate(make_context())
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_confidence_higher_with_full_data_than_without(self):
        rule = PositionSizeRule()
        full_context = make_context(
            market_state=make_market_state(indicators=[make_atr_indicator(value=2.0)])
        )
        partial_context = make_context(market_state=None)
        full_result = rule.evaluate(full_context)
        partial_result = rule.evaluate(partial_context)
        self.assertGreater(full_result.confidence, partial_result.confidence)

    def test_confidence_scales_with_signal_confidence(self):
        rule = PositionSizeRule()
        high = rule.evaluate(make_context(signal=make_signal(confidence=0.9)))
        low = rule.evaluate(make_context(signal=make_signal(confidence=0.3)))
        self.assertGreater(high.confidence, low.confidence)


# ========================================================================
# StopLossRule
# ========================================================================
class TestStopLossRuleConstruction(unittest.TestCase):
    def test_default_construction(self):
        rule = StopLossRule()
        self.assertEqual(rule.name, "StopLossRule")
        self.assertIsInstance(rule, BaseRiskManager)

    def test_custom_name(self):
        rule = StopLossRule(name="MyStopper")
        self.assertEqual(rule.name, "MyStopper")

    def test_custom_configuration_accepted(self):
        rule = StopLossRule(
            atr_multiplier=1.5,
            default_stop_distance_pct=0.03,
            min_stop_distance_pct=0.005,
            max_stop_distance_pct=0.1,
            atr_indicator_name="ATR_20",
        )
        self.assertEqual(rule.atr_multiplier, 1.5)
        self.assertEqual(rule.min_stop_distance_pct, 0.005)
        self.assertEqual(rule.max_stop_distance_pct, 0.1)

    def test_rejects_non_positive_atr_multiplier(self):
        with self.assertRaises(RiskManagerConfigurationError):
            StopLossRule(atr_multiplier=0.0)

    def test_rejects_non_numeric_atr_multiplier(self):
        with self.assertRaises(RiskManagerConfigurationError):
            StopLossRule(atr_multiplier="x")  # type: ignore[arg-type]

    def test_rejects_min_greater_or_equal_max(self):
        with self.assertRaises(RiskManagerConfigurationError):
            StopLossRule(min_stop_distance_pct=0.1, max_stop_distance_pct=0.1)
        with self.assertRaises(RiskManagerConfigurationError):
            StopLossRule(min_stop_distance_pct=0.2, max_stop_distance_pct=0.1)

    def test_rejects_default_outside_min_max_range(self):
        with self.assertRaises(RiskManagerConfigurationError):
            StopLossRule(
                min_stop_distance_pct=0.05,
                max_stop_distance_pct=0.1,
                default_stop_distance_pct=0.01,
            )

    def test_rejects_out_of_range_min_stop_distance_pct(self):
        with self.assertRaises(RiskManagerConfigurationError):
            StopLossRule(min_stop_distance_pct=0.0)
        with self.assertRaises(RiskManagerConfigurationError):
            StopLossRule(min_stop_distance_pct=1.5)

    def test_rejects_empty_atr_indicator_name(self):
        with self.assertRaises(RiskManagerConfigurationError):
            StopLossRule(atr_indicator_name="")


class TestStopLossRuleContextValidation(unittest.TestCase):
    def test_evaluate_rejects_non_risk_context(self):
        rule = StopLossRule()
        with self.assertRaises(InvalidRiskContextError):
            rule.evaluate(123)  # type: ignore[arg-type]


class TestStopLossRuleNormalBehavior(unittest.TestCase):
    def test_returns_risk_result(self):
        rule = StopLossRule()
        result = rule.evaluate(make_context(market_state=make_market_state()))
        self.assertIsInstance(result, RiskResult)
        self.assertTrue(result.approved)

    def test_buy_signal_stop_loss_below_reference_price(self):
        rule = StopLossRule()
        context = make_context(
            market_state=make_market_state(indicators=[make_atr_indicator(value=2.0)])
        )
        result = rule.evaluate(context)
        self.assertLess(result.metadata["stop_loss_price"], result.metadata["reference_price"])

    def test_sell_signal_stop_loss_above_reference_price(self):
        rule = StopLossRule()
        context = make_context(
            signal=make_signal(direction=SignalDirection.SELL),
            market_state=make_market_state(indicators=[make_atr_indicator(value=2.0)]),
        )
        result = rule.evaluate(context)
        self.assertGreater(result.metadata["stop_loss_price"], result.metadata["reference_price"])

    def test_atr_basis_used_when_available(self):
        rule = StopLossRule()
        context = make_context(
            market_state=make_market_state(indicators=[make_atr_indicator(value=2.0)])
        )
        result = rule.evaluate(context)
        self.assertEqual(result.metadata["basis"], "atr")
        self.assertTrue(result.metadata["atr_available"])

    def test_default_pct_basis_used_without_atr(self):
        rule = StopLossRule()
        context = make_context(market_state=make_market_state(indicators=[]))
        result = rule.evaluate(context)
        self.assertEqual(result.metadata["basis"], "default_pct")
        self.assertFalse(result.metadata["atr_available"])


class TestStopLossRuleEdgeCases(unittest.TestCase):
    def test_hold_signal_short_circuits(self):
        rule = StopLossRule()
        context = make_context(signal=make_signal(direction=SignalDirection.HOLD))
        result = rule.evaluate(context)
        self.assertFalse(result.approved)
        self.assertIsNone(result.metadata["stop_loss_price"])
        self.assertEqual(result.metadata["reason"], "hold_signal")

    def test_distance_clamped_to_max_when_atr_huge(self):
        rule = StopLossRule(max_stop_distance_pct=0.05)
        context = make_context(
            market_state=make_market_state(indicators=[make_atr_indicator(value=1000.0)])
        )
        result = rule.evaluate(context)
        self.assertTrue(result.metadata["distance_clamped"])
        self.assertAlmostEqual(result.metadata["distance_pct"], 0.05)

    def test_distance_clamped_to_min_when_atr_tiny(self):
        rule = StopLossRule(min_stop_distance_pct=0.01)
        context = make_context(
            market_state=make_market_state(indicators=[make_atr_indicator(value=0.00001)])
        )
        result = rule.evaluate(context)
        self.assertTrue(result.metadata["distance_clamped"])
        self.assertAlmostEqual(result.metadata["distance_pct"], 0.01)

    def test_entry_price_override_used_over_candle_close(self):
        rule = StopLossRule()
        context = make_context(
            signal=make_signal(metadata={"entry_price": 50.0}),
            market_state=make_market_state(),
        )
        result = rule.evaluate(context)
        self.assertEqual(result.metadata["reference_price"], 50.0)

    def test_low_priced_instrument_floors_to_min_price(self):
        rule = StopLossRule(default_stop_distance_pct=0.99, min_stop_distance_pct=0.5, max_stop_distance_pct=1.0)
        context = make_context(
            signal=make_signal(metadata={"entry_price": 1e-9}),
        )
        result = rule.evaluate(context)
        self.assertTrue(result.metadata["floored_to_min_price"])
        self.assertGreater(result.metadata["stop_loss_price"], 0.0)

    def test_out_of_range_confidence_is_clamped(self):
        rule = StopLossRule()
        context = make_context(signal=make_signal(confidence=2.0), market_state=make_market_state())
        result = rule.evaluate(context)
        self.assertEqual(result.metadata["signal_confidence"], 1.0)
        self.assertTrue(result.metadata["signal_confidence_clamped"])


class TestStopLossRuleInvalidInput(unittest.TestCase):
    def test_raises_on_non_numeric_signal_confidence(self):
        rule = StopLossRule()
        context = make_context(signal=make_signal(confidence="bad"))  # type: ignore[arg-type]
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)

    def test_raises_on_nan_signal_confidence(self):
        rule = StopLossRule()
        context = make_context(signal=make_signal(confidence=float("nan")))
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)

    def test_raises_on_bool_signal_confidence(self):
        rule = StopLossRule()
        context = make_context(signal=make_signal(confidence=False))  # type: ignore[arg-type]
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)

    def test_raises_when_no_reference_price_available(self):
        rule = StopLossRule()
        context = make_context(market_state=None)
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)

    def test_raises_when_market_state_present_but_no_candle(self):
        rule = StopLossRule()
        context = make_context(market_state=make_market_state(include_candle=False))
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)


class TestStopLossRuleMetadata(unittest.TestCase):
    def test_metadata_contains_expected_keys(self):
        rule = StopLossRule()
        result = rule.evaluate(make_context(market_state=make_market_state()))
        expected_keys = {
            "risk_manager",
            "signal_direction",
            "signal_confidence",
            "reference_price",
            "reference_price_source",
            "atr_available",
            "atr_value",
            "basis",
            "distance_pct",
            "distance_clamped",
            "stop_loss_price",
            "floored_to_min_price",
            "config",
        }
        self.assertTrue(expected_keys.issubset(result.metadata.keys()))

    def test_metadata_risk_manager_name_matches_instance(self):
        rule = StopLossRule(name="CustomStopper")
        result = rule.evaluate(make_context(market_state=make_market_state()))
        self.assertEqual(result.metadata["risk_manager"], "CustomStopper")


class TestStopLossRuleConfidence(unittest.TestCase):
    def test_confidence_within_unit_range(self):
        rule = StopLossRule()
        result = rule.evaluate(make_context(market_state=make_market_state()))
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_confidence_higher_with_atr_than_without(self):
        rule = StopLossRule()
        with_atr = rule.evaluate(
            make_context(
                market_state=make_market_state(indicators=[make_atr_indicator(value=2.0)])
            )
        )
        without_atr = rule.evaluate(
            make_context(market_state=make_market_state(indicators=[]))
        )
        self.assertGreater(with_atr.confidence, without_atr.confidence)


# ========================================================================
# TakeProfitRule
# ========================================================================
class TestTakeProfitRuleConstruction(unittest.TestCase):
    def test_default_construction(self):
        rule = TakeProfitRule()
        self.assertEqual(rule.name, "TakeProfitRule")
        self.assertIsInstance(rule, BaseRiskManager)

    def test_custom_name(self):
        rule = TakeProfitRule(name="MyTargeter")
        self.assertEqual(rule.name, "MyTargeter")

    def test_custom_configuration_accepted(self):
        rule = TakeProfitRule(
            atr_multiplier=1.5,
            risk_reward_ratio=3.0,
            default_stop_distance_pct=0.03,
        )
        self.assertEqual(rule.risk_reward_ratio, 3.0)

    def test_rejects_non_positive_risk_reward_ratio(self):
        with self.assertRaises(RiskManagerConfigurationError):
            TakeProfitRule(risk_reward_ratio=0.0)
        with self.assertRaises(RiskManagerConfigurationError):
            TakeProfitRule(risk_reward_ratio=-1.0)

    def test_rejects_non_numeric_risk_reward_ratio(self):
        with self.assertRaises(RiskManagerConfigurationError):
            TakeProfitRule(risk_reward_ratio="two")  # type: ignore[arg-type]

    def test_rejects_min_greater_or_equal_max(self):
        with self.assertRaises(RiskManagerConfigurationError):
            TakeProfitRule(min_stop_distance_pct=0.1, max_stop_distance_pct=0.05)

    def test_rejects_default_outside_min_max_range(self):
        with self.assertRaises(RiskManagerConfigurationError):
            TakeProfitRule(
                min_stop_distance_pct=0.05,
                max_stop_distance_pct=0.1,
                default_stop_distance_pct=0.5,
            )

    def test_rejects_empty_atr_indicator_name(self):
        with self.assertRaises(RiskManagerConfigurationError):
            TakeProfitRule(atr_indicator_name="")


class TestTakeProfitRuleContextValidation(unittest.TestCase):
    def test_evaluate_rejects_non_risk_context(self):
        rule = TakeProfitRule()
        with self.assertRaises(InvalidRiskContextError):
            rule.evaluate({"not": "a context"})  # type: ignore[arg-type]


class TestTakeProfitRuleNormalBehavior(unittest.TestCase):
    def test_returns_risk_result(self):
        rule = TakeProfitRule()
        result = rule.evaluate(make_context(market_state=make_market_state()))
        self.assertIsInstance(result, RiskResult)
        self.assertTrue(result.approved)

    def test_buy_signal_take_profit_above_reference_price(self):
        rule = TakeProfitRule()
        context = make_context(
            market_state=make_market_state(indicators=[make_atr_indicator(value=2.0)])
        )
        result = rule.evaluate(context)
        self.assertGreater(
            result.metadata["take_profit_price"], result.metadata["reference_price"]
        )

    def test_sell_signal_take_profit_below_reference_price(self):
        rule = TakeProfitRule()
        context = make_context(
            signal=make_signal(direction=SignalDirection.SELL),
            market_state=make_market_state(indicators=[make_atr_indicator(value=2.0)]),
        )
        result = rule.evaluate(context)
        self.assertLess(
            result.metadata["take_profit_price"], result.metadata["reference_price"]
        )

    def test_higher_risk_reward_ratio_gives_farther_target(self):
        low_rr = TakeProfitRule(risk_reward_ratio=1.0)
        high_rr = TakeProfitRule(risk_reward_ratio=5.0)
        context = make_context(
            market_state=make_market_state(indicators=[make_atr_indicator(value=2.0)])
        )
        low_result = low_rr.evaluate(context)
        high_result = high_rr.evaluate(context)
        low_distance = low_result.metadata["take_profit_price"] - low_result.metadata["reference_price"]
        high_distance = high_result.metadata["take_profit_price"] - high_result.metadata["reference_price"]
        self.assertGreater(high_distance, low_distance)

    def test_atr_basis_used_when_available(self):
        rule = TakeProfitRule()
        context = make_context(
            market_state=make_market_state(indicators=[make_atr_indicator(value=2.0)])
        )
        result = rule.evaluate(context)
        self.assertEqual(result.metadata["basis"], "atr")


class TestTakeProfitRuleEdgeCases(unittest.TestCase):
    def test_hold_signal_short_circuits(self):
        rule = TakeProfitRule()
        context = make_context(signal=make_signal(direction=SignalDirection.HOLD))
        result = rule.evaluate(context)
        self.assertFalse(result.approved)
        self.assertIsNone(result.metadata["take_profit_price"])
        self.assertEqual(result.metadata["reason"], "hold_signal")

    def test_default_pct_basis_used_without_atr(self):
        rule = TakeProfitRule()
        context = make_context(market_state=make_market_state(indicators=[]))
        result = rule.evaluate(context)
        self.assertEqual(result.metadata["basis"], "default_pct")

    def test_base_distance_clamped_to_max(self):
        rule = TakeProfitRule(max_stop_distance_pct=0.05)
        context = make_context(
            market_state=make_market_state(indicators=[make_atr_indicator(value=1000.0)])
        )
        result = rule.evaluate(context)
        self.assertTrue(result.metadata["base_distance_clamped"])

    def test_entry_price_override_used_over_candle_close(self):
        rule = TakeProfitRule()
        context = make_context(
            signal=make_signal(metadata={"entry_price": 50.0}),
            market_state=make_market_state(),
        )
        result = rule.evaluate(context)
        self.assertEqual(result.metadata["reference_price"], 50.0)

    def test_low_priced_instrument_floors_to_min_price_on_sell(self):
        rule = TakeProfitRule(default_stop_distance_pct=0.99, min_stop_distance_pct=0.5, max_stop_distance_pct=1.0)
        context = make_context(
            signal=make_signal(direction=SignalDirection.SELL, metadata={"entry_price": 1e-9}),
        )
        result = rule.evaluate(context)
        self.assertTrue(result.metadata["floored_to_min_price"])
        self.assertGreater(result.metadata["take_profit_price"], 0.0)

    def test_out_of_range_confidence_is_clamped(self):
        rule = TakeProfitRule()
        context = make_context(signal=make_signal(confidence=-1.0), market_state=make_market_state())
        result = rule.evaluate(context)
        self.assertEqual(result.metadata["signal_confidence"], 0.0)
        self.assertTrue(result.metadata["signal_confidence_clamped"])


class TestTakeProfitRuleInvalidInput(unittest.TestCase):
    def test_raises_on_non_numeric_signal_confidence(self):
        rule = TakeProfitRule()
        context = make_context(signal=make_signal(confidence=None))  # type: ignore[arg-type]
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)

    def test_raises_on_infinite_signal_confidence(self):
        rule = TakeProfitRule()
        context = make_context(signal=make_signal(confidence=float("-inf")))
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)

    def test_raises_on_bool_signal_confidence(self):
        rule = TakeProfitRule()
        context = make_context(signal=make_signal(confidence=True))  # type: ignore[arg-type]
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)

    def test_raises_when_no_reference_price_available(self):
        rule = TakeProfitRule()
        context = make_context(market_state=None)
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)

    def test_raises_when_market_state_present_but_no_candle(self):
        rule = TakeProfitRule()
        context = make_context(market_state=make_market_state(include_candle=False))
        with self.assertRaises(InsufficientRiskDataError):
            rule.evaluate(context)


class TestTakeProfitRuleMetadata(unittest.TestCase):
    def test_metadata_contains_expected_keys(self):
        rule = TakeProfitRule()
        result = rule.evaluate(make_context(market_state=make_market_state()))
        expected_keys = {
            "risk_manager",
            "signal_direction",
            "signal_confidence",
            "reference_price",
            "reference_price_source",
            "atr_available",
            "atr_value",
            "basis",
            "base_distance_pct",
            "risk_reward_ratio",
            "target_distance_pct",
            "take_profit_price",
            "floored_to_min_price",
            "config",
        }
        self.assertTrue(expected_keys.issubset(result.metadata.keys()))

    def test_metadata_risk_manager_name_matches_instance(self):
        rule = TakeProfitRule(name="CustomTargeter")
        result = rule.evaluate(make_context(market_state=make_market_state()))
        self.assertEqual(result.metadata["risk_manager"], "CustomTargeter")


class TestTakeProfitRuleConfidence(unittest.TestCase):
    def test_confidence_within_unit_range(self):
        rule = TakeProfitRule()
        result = rule.evaluate(make_context(market_state=make_market_state()))
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_confidence_higher_with_atr_than_without(self):
        rule = TakeProfitRule()
        with_atr = rule.evaluate(
            make_context(
                market_state=make_market_state(indicators=[make_atr_indicator(value=2.0)])
            )
        )
        without_atr = rule.evaluate(
            make_context(market_state=make_market_state(indicators=[]))
        )
        self.assertGreater(with_atr.confidence, without_atr.confidence)


# ========================================================================
# Rule independence
# ========================================================================
class TestRuleIndependence(unittest.TestCase):
    """
    Verifies the independence guarantees documented in each rule's
    module docstring: none of the three rules imports or depends on
    either of the other two, and running one rule's `evaluate()` never
    requires or is influenced by another rule's instance or output.
    """

    def test_rules_do_not_import_each_other(self):
        import strategies.risk_management.position_size_rule as psr_module
        import strategies.risk_management.stop_loss_rule as sl_module
        import strategies.risk_management.take_profit_rule as tp_module

        self.assertNotIn("StopLossRule", dir(psr_module))
        self.assertNotIn("TakeProfitRule", dir(psr_module))
        self.assertNotIn("PositionSizeRule", dir(sl_module))
        self.assertNotIn("TakeProfitRule", dir(sl_module))
        self.assertNotIn("PositionSizeRule", dir(tp_module))
        self.assertNotIn("StopLossRule", dir(tp_module))

    def test_evaluating_one_rule_does_not_affect_another(self):
        context = make_context(
            market_state=make_market_state(indicators=[make_atr_indicator(value=2.0)])
        )
        sizer = PositionSizeRule()
        stopper = StopLossRule()
        targeter = TakeProfitRule()

        baseline_stop = stopper.evaluate(context)
        # Running the other two rules against the same (immutable)
        # context repeatedly must not change StopLossRule's output.
        sizer.evaluate(context)
        targeter.evaluate(context)
        sizer.evaluate(context)
        again_stop = stopper.evaluate(context)

        self.assertEqual(baseline_stop.metadata["stop_loss_price"], again_stop.metadata["stop_loss_price"])

    def test_each_rule_produces_independent_result_instances(self):
        context = make_context(
            market_state=make_market_state(indicators=[make_atr_indicator(value=2.0)])
        )
        size_result = PositionSizeRule().evaluate(context)
        stop_result = StopLossRule().evaluate(context)
        profit_result = TakeProfitRule().evaluate(context)

        self.assertIsNot(size_result, stop_result)
        self.assertIsNot(stop_result, profit_result)
        self.assertNotEqual(size_result.metadata.keys(), stop_result.metadata.keys())

    def test_stop_loss_does_not_read_take_profit_config_keys(self):
        # StopLossRule has no risk_reward_ratio concept at all.
        rule = StopLossRule()
        self.assertFalse(hasattr(rule, "risk_reward_ratio"))

    def test_take_profit_does_not_consume_stop_loss_output(self):
        # TakeProfitRule computes its own base distance independently
        # rather than reading a StopLossRule RiskResult.
        stop_rule = StopLossRule(atr_multiplier=100.0)  # deliberately wide
        profit_rule = TakeProfitRule(atr_multiplier=2.0)
        context = make_context(
            market_state=make_market_state(indicators=[make_atr_indicator(value=2.0)])
        )
        stop_rule.evaluate(context)  # produced, but never passed onward
        profit_result = profit_rule.evaluate(context)
        # profit_rule's own atr_multiplier (2.0), not stop_rule's (100.0),
        # determines its distance.
        self.assertAlmostEqual(
            profit_result.metadata["atr_value"] * profit_rule.atr_multiplier
            / profit_result.metadata["reference_price"],
            profit_result.metadata["raw_base_distance_pct"],
        )


if __name__ == "__main__":
    unittest.main()
