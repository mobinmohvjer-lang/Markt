"""
test_risk_management.py
--------------------------
Purpose:
    Unit tests for the Risk Engine foundation (Part 1):
    `RiskResult`, `RiskContext`, `BaseRiskManager`, and the
    `strategies.risk_management.exceptions` / `.utils` helpers.

Uses the standard-library ``unittest`` framework, matching the
`analysis`/`signals`/`indicators`/`data` test suites (no external
test-runner dependency).

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from core.entities.candle import Candle
from core.entities.market_state import MarketState
from core.entities.portfolio import Portfolio
from core.entities.signal import Signal
from core.enums import SignalDirection
from strategies.risk_management import (
    BaseRiskManager,
    InsufficientRiskDataError,
    InvalidRiskContextError,
    RiskContext,
    RiskError,
    RiskManagerConfigurationError,
    RiskResult,
    RiskValidationError,
)
from strategies.risk_management.utils import (
    merge_metadata,
    validate_bool,
    validate_non_empty_str,
    validate_unit_range,
)

NOW = datetime.now(timezone.utc)


def make_signal(*, direction: SignalDirection = SignalDirection.BUY, confidence: float = 0.8) -> Signal:
    return Signal(
        signal_id="sig-1",
        symbol="BTCUSDT",
        direction=direction,
        confidence=confidence,
        source="TechnicalSignalGenerator",
        timeframe="1h",
        generated_at=NOW,
    )


def make_portfolio(*, cash_balance: Decimal = Decimal("10000")) -> Portfolio:
    return Portfolio(
        portfolio_id="portfolio-1",
        base_currency="USDT",
        cash_balance=cash_balance,
    )


def make_market_state() -> MarketState:
    return MarketState(
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=NOW,
        latest_candle=Candle(
            symbol="BTCUSDT",
            timeframe="1h",
            open_time=NOW,
            close_time=NOW,
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("95"),
            close=Decimal("105"),
            volume=Decimal("1000"),
        ),
    )


# ----------------------------------------------------------------------
# RiskResult
# ----------------------------------------------------------------------
class TestRiskResult(unittest.TestCase):
    def test_instantiates_with_required_fields(self):
        result = RiskResult(
            approved=True,
            risk_score=0.2,
            confidence=0.9,
            summary="Signal within acceptable risk tolerance",
        )
        self.assertTrue(result.approved)
        self.assertEqual(result.risk_score, 0.2)
        self.assertEqual(result.confidence, 0.9)
        self.assertEqual(result.summary, "Signal within acceptable risk tolerance")
        self.assertEqual(result.metadata, {})

    def test_only_has_the_five_documented_fields(self):
        result = RiskResult(approved=False, risk_score=0.9, confidence=0.5, summary="Too risky")
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        self.assertEqual(
            field_names, {"approved", "risk_score", "confidence", "summary", "metadata"}
        )

    def test_is_frozen(self):
        result = RiskResult(approved=True, risk_score=0.1, confidence=0.9, summary="OK")
        with self.assertRaises(Exception):
            result.approved = False  # type: ignore[misc]

    def test_rejects_non_bool_approved(self):
        with self.assertRaises(RiskValidationError):
            RiskResult(approved="yes", risk_score=0.1, confidence=0.9, summary="OK")  # type: ignore[arg-type]

    def test_rejects_out_of_range_risk_score(self):
        with self.assertRaises(RiskValidationError):
            RiskResult(approved=True, risk_score=1.5, confidence=0.9, summary="OK")

    def test_rejects_out_of_range_confidence(self):
        with self.assertRaises(RiskValidationError):
            RiskResult(approved=True, risk_score=0.5, confidence=-0.1, summary="OK")

    def test_rejects_non_finite_risk_score(self):
        with self.assertRaises(RiskValidationError):
            RiskResult(approved=True, risk_score=float("nan"), confidence=0.5, summary="OK")

    def test_rejects_blank_summary(self):
        with self.assertRaises(RiskValidationError):
            RiskResult(approved=True, risk_score=0.1, confidence=0.9, summary="   ")

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(TypeError):
            RiskResult(
                approved=True,
                risk_score=0.1,
                confidence=0.9,
                summary="OK",
                metadata="not-a-dict",  # type: ignore[arg-type]
            )

    def test_with_metadata_returns_new_instance(self):
        original = RiskResult(
            approved=True, risk_score=0.1, confidence=0.9, summary="OK", metadata={"a": 1}
        )
        updated = original.with_metadata(b=2)
        self.assertIsNot(updated, original)
        self.assertEqual(original.metadata, {"a": 1})
        self.assertEqual(updated.metadata, {"a": 1, "b": 2})

    def test_with_metadata_overrides_on_conflict(self):
        original = RiskResult(
            approved=True, risk_score=0.1, confidence=0.9, summary="OK", metadata={"a": 1}
        )
        updated = original.with_metadata(a=99)
        self.assertEqual(updated.metadata, {"a": 99})


# ----------------------------------------------------------------------
# RiskContext
# ----------------------------------------------------------------------
class TestRiskContext(unittest.TestCase):
    def test_instantiates_with_required_fields(self):
        context = RiskContext(
            symbol="BTCUSDT", timeframe="1h", signal=make_signal(), portfolio=make_portfolio()
        )
        self.assertEqual(context.symbol, "BTCUSDT")
        self.assertEqual(context.timeframe, "1h")
        self.assertIsInstance(context.signal, Signal)
        self.assertIsInstance(context.portfolio, Portfolio)
        self.assertIsNone(context.market_state)
        self.assertEqual(context.metadata, {})

    def test_accepts_optional_market_state(self):
        context = RiskContext(
            symbol="BTCUSDT",
            timeframe="1h",
            signal=make_signal(),
            portfolio=make_portfolio(),
            market_state=make_market_state(),
        )
        self.assertTrue(context.has_market_state())

    def test_has_market_state_false_when_absent(self):
        context = RiskContext(
            symbol="BTCUSDT", timeframe="1h", signal=make_signal(), portfolio=make_portfolio()
        )
        self.assertFalse(context.has_market_state())

    def test_is_frozen(self):
        context = RiskContext(
            symbol="BTCUSDT", timeframe="1h", signal=make_signal(), portfolio=make_portfolio()
        )
        with self.assertRaises(Exception):
            context.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_rejects_blank_symbol(self):
        with self.assertRaises(InvalidRiskContextError):
            RiskContext(
                symbol="   ", timeframe="1h", signal=make_signal(), portfolio=make_portfolio()
            )

    def test_rejects_blank_timeframe(self):
        with self.assertRaises(InvalidRiskContextError):
            RiskContext(
                symbol="BTCUSDT", timeframe="", signal=make_signal(), portfolio=make_portfolio()
            )

    def test_rejects_non_signal(self):
        with self.assertRaises(InvalidRiskContextError):
            RiskContext(
                symbol="BTCUSDT",
                timeframe="1h",
                signal="not-a-signal",  # type: ignore[arg-type]
                portfolio=make_portfolio(),
            )

    def test_rejects_non_portfolio(self):
        with self.assertRaises(InvalidRiskContextError):
            RiskContext(
                symbol="BTCUSDT",
                timeframe="1h",
                signal=make_signal(),
                portfolio="not-a-portfolio",  # type: ignore[arg-type]
            )

    def test_rejects_invalid_market_state(self):
        with self.assertRaises(InvalidRiskContextError):
            RiskContext(
                symbol="BTCUSDT",
                timeframe="1h",
                signal=make_signal(),
                portfolio=make_portfolio(),
                market_state="not-a-market-state",  # type: ignore[arg-type]
            )

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(InvalidRiskContextError):
            RiskContext(
                symbol="BTCUSDT",
                timeframe="1h",
                signal=make_signal(),
                portfolio=make_portfolio(),
                metadata="not-a-dict",  # type: ignore[arg-type]
            )


# ----------------------------------------------------------------------
# strategies.risk_management.utils
# ----------------------------------------------------------------------
class TestUtils(unittest.TestCase):
    def test_validate_non_empty_str_accepts_valid_string(self):
        self.assertEqual(validate_non_empty_str("BTCUSDT", name="symbol"), "BTCUSDT")

    def test_validate_non_empty_str_rejects_blank(self):
        with self.assertRaises(RiskValidationError):
            validate_non_empty_str("   ", name="symbol")

    def test_validate_non_empty_str_rejects_non_string(self):
        with self.assertRaises(RiskValidationError):
            validate_non_empty_str(123, name="symbol")  # type: ignore[arg-type]

    def test_validate_unit_range_accepts_boundaries(self):
        self.assertEqual(validate_unit_range(0.0, name="risk_score"), 0.0)
        self.assertEqual(validate_unit_range(1.0, name="risk_score"), 1.0)

    def test_validate_unit_range_rejects_out_of_range(self):
        with self.assertRaises(RiskValidationError):
            validate_unit_range(1.1, name="risk_score")
        with self.assertRaises(RiskValidationError):
            validate_unit_range(-0.1, name="risk_score")

    def test_validate_unit_range_rejects_non_numeric(self):
        with self.assertRaises(RiskValidationError):
            validate_unit_range("high", name="risk_score")  # type: ignore[arg-type]

    def test_validate_unit_range_rejects_bool(self):
        with self.assertRaises(RiskValidationError):
            validate_unit_range(True, name="risk_score")  # type: ignore[arg-type]

    def test_validate_unit_range_rejects_non_finite(self):
        with self.assertRaises(RiskValidationError):
            validate_unit_range(float("inf"), name="risk_score")

    def test_validate_bool_accepts_bool(self):
        self.assertTrue(validate_bool(True, name="approved"))
        self.assertFalse(validate_bool(False, name="approved"))

    def test_validate_bool_rejects_non_bool(self):
        with self.assertRaises(RiskValidationError):
            validate_bool(1, name="approved")  # type: ignore[arg-type]

    def test_merge_metadata_combines_sources(self):
        merged = merge_metadata({"a": 1}, {"b": 2})
        self.assertEqual(merged, {"a": 1, "b": 2})

    def test_merge_metadata_later_source_wins(self):
        merged = merge_metadata({"a": 1}, {"a": 2})
        self.assertEqual(merged, {"a": 2})

    def test_merge_metadata_skips_none(self):
        merged = merge_metadata(None, {"a": 1}, None)
        self.assertEqual(merged, {"a": 1})

    def test_merge_metadata_no_sources_returns_empty_dict(self):
        self.assertEqual(merge_metadata(), {})


# ----------------------------------------------------------------------
# strategies.risk_management.exceptions
# ----------------------------------------------------------------------
class TestExceptionHierarchy(unittest.TestCase):
    def test_risk_validation_error_is_risk_error(self):
        self.assertTrue(issubclass(RiskValidationError, RiskError))

    def test_invalid_risk_context_error_is_risk_validation_error(self):
        self.assertTrue(issubclass(InvalidRiskContextError, RiskValidationError))

    def test_insufficient_risk_data_error_is_risk_error(self):
        self.assertTrue(issubclass(InsufficientRiskDataError, RiskError))
        self.assertFalse(issubclass(InsufficientRiskDataError, RiskValidationError))

    def test_risk_manager_configuration_error_is_risk_error(self):
        self.assertTrue(issubclass(RiskManagerConfigurationError, RiskError))

    def test_risk_error_is_exception(self):
        self.assertTrue(issubclass(RiskError, Exception))


# ----------------------------------------------------------------------
# BaseRiskManager (via a minimal concrete fake, mirroring
# test_analysis.py's fake BaseAnalyzer / test_signals.py's fake
# BaseSignalGenerator pattern)
# ----------------------------------------------------------------------
class FakeRiskManager(BaseRiskManager):
    """Minimal concrete `BaseRiskManager` used only to exercise the base class."""

    def __init__(self, *, name=None, approved: bool = True, risk_score: float = 0.3):
        super().__init__(name=name)
        self._approved = approved
        self._risk_score = risk_score

    def evaluate(self, context: RiskContext) -> RiskResult:
        self.validate_context(context)
        if context.portfolio.cash_balance <= 0:
            raise InsufficientRiskDataError("portfolio has no available cash balance")
        return self._build_result(
            approved=self._approved,
            risk_score=self._risk_score,
            confidence=context.signal.confidence,
            summary=f"Evaluated {context.symbol} signal",
            metadata={"evaluated_by": self.name},
        )


class TestBaseRiskManager(unittest.TestCase):
    def test_defaults_name_to_class_name(self):
        manager = FakeRiskManager()
        self.assertEqual(manager.name, "FakeRiskManager")

    def test_accepts_custom_name(self):
        manager = FakeRiskManager(name="CustomRiskManager")
        self.assertEqual(manager.name, "CustomRiskManager")

    def test_cannot_instantiate_abstract_base_directly(self):
        with self.assertRaises(TypeError):
            BaseRiskManager()  # type: ignore[abstract]

    def test_validate_context_accepts_valid_context(self):
        manager = FakeRiskManager()
        context = RiskContext(
            symbol="BTCUSDT", timeframe="1h", signal=make_signal(), portfolio=make_portfolio()
        )
        self.assertIs(manager.validate_context(context), context)

    def test_validate_context_rejects_non_context(self):
        manager = FakeRiskManager()
        with self.assertRaises(InvalidRiskContextError):
            manager.validate_context("not-a-context")  # type: ignore[arg-type]

    def test_evaluate_returns_risk_result(self):
        manager = FakeRiskManager(approved=True, risk_score=0.25)
        context = RiskContext(
            symbol="BTCUSDT", timeframe="1h", signal=make_signal(), portfolio=make_portfolio()
        )
        result = manager.evaluate(context)
        self.assertIsInstance(result, RiskResult)
        self.assertTrue(result.approved)
        self.assertEqual(result.risk_score, 0.25)
        self.assertEqual(result.confidence, 0.8)
        self.assertEqual(result.metadata, {"evaluated_by": "FakeRiskManager"})

    def test_evaluate_raises_insufficient_data_when_no_cash(self):
        manager = FakeRiskManager()
        context = RiskContext(
            symbol="BTCUSDT",
            timeframe="1h",
            signal=make_signal(),
            portfolio=make_portfolio(cash_balance=Decimal("0")),
        )
        with self.assertRaises(InsufficientRiskDataError):
            manager.evaluate(context)

    def test_build_result_defaults_metadata_to_empty_dict(self):
        manager = FakeRiskManager()
        result = manager._build_result(
            approved=False, risk_score=0.9, confidence=0.4, summary="Rejected"
        )
        self.assertEqual(result.metadata, {})

    def test_repr_includes_class_and_name(self):
        manager = FakeRiskManager(name="Guard")
        self.assertEqual(repr(manager), "FakeRiskManager(name='Guard')")


# ----------------------------------------------------------------------
# Integration: a realistic RiskContext built from Signal + Portfolio +
# MarketState, evaluated end-to-end by a real BaseRiskManager subclass.
# ----------------------------------------------------------------------
class TestIntegration(unittest.TestCase):
    def test_end_to_end_evaluation_with_market_state(self):
        manager = FakeRiskManager(approved=True, risk_score=0.15)
        context = RiskContext(
            symbol="BTCUSDT",
            timeframe="1h",
            signal=make_signal(direction=SignalDirection.SELL, confidence=0.65),
            portfolio=make_portfolio(cash_balance=Decimal("5000")),
            market_state=make_market_state(),
            metadata={"source_signal_metadata": {"score_label": "bearish"}},
        )
        result = manager.evaluate(context)

        self.assertTrue(context.has_market_state())
        self.assertTrue(result.approved)
        self.assertEqual(result.confidence, 0.65)
        self.assertIn("BTCUSDT", result.summary)

    def test_no_position_sizing_stop_loss_or_take_profit_fields(self):
        # Defensive: RiskResult must expose exactly the five documented
        # fields -- no position size, stop loss, or take profit fields
        # have been introduced by this part.
        result = RiskResult(approved=True, risk_score=0.1, confidence=0.9, summary="OK")
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        for forbidden in ("position_size", "stop_loss", "take_profit", "order_id"):
            self.assertNotIn(forbidden, field_names)


if __name__ == "__main__":
    unittest.main()
