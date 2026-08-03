"""
test_portfolio_management.py
-------------------------------
Purpose:
    Unit tests for the Portfolio Management foundation (Part 1):
    `PortfolioResult`, `PortfolioContext`, `BasePortfolioManager`, and
    the `strategies.portfolio_management.exceptions` / `.utils`
    helpers.

Uses the standard-library ``unittest`` framework, matching the
`analysis`/`signals`/`strategies`/`strategies.risk_management` test
suites (no external test-runner dependency).

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from core.entities.portfolio import Portfolio
from core.enums import SignalDirection

from strategies.portfolio_management import (
    BasePortfolioManager,
    InsufficientPortfolioDataError,
    InvalidPortfolioContextError,
    PortfolioContext,
    PortfolioError,
    PortfolioManagerConfigurationError,
    PortfolioResult,
    PortfolioValidationError,
)
from strategies.portfolio_management.utils import (
    clip,
    merge_metadata,
    validate_bool,
    validate_non_empty_str,
    validate_unit_range,
)
from strategies.result import StrategyResult
from strategies.risk_management.result import RiskResult


def make_portfolio(*, cash_balance: Decimal = Decimal("10000")) -> Portfolio:
    return Portfolio(
        portfolio_id="portfolio-1",
        base_currency="USDT",
        cash_balance=cash_balance,
    )


def make_strategy_result(
    *, action: SignalDirection = SignalDirection.BUY, confidence: float = 0.7
) -> StrategyResult:
    return StrategyResult(
        action=action,
        confidence=confidence,
        summary="Directional decision from analysis/signal inputs",
        metadata={"overall_score": 0.4},
    )


def make_risk_result(*, approved: bool = True, risk_score: float = 0.2) -> RiskResult:
    return RiskResult(
        approved=approved,
        risk_score=risk_score,
        confidence=0.8,
        summary="Signal within acceptable risk tolerance",
    )


# ----------------------------------------------------------------------
# PortfolioResult
# ----------------------------------------------------------------------
class TestPortfolioResult(unittest.TestCase):
    def test_instantiates_with_required_fields(self):
        result = PortfolioResult(
            new_positions_allowed=True,
            confidence=0.9,
            summary="Portfolio has capacity for a new position",
        )
        self.assertTrue(result.new_positions_allowed)
        self.assertEqual(result.confidence, 0.9)
        self.assertEqual(result.summary, "Portfolio has capacity for a new position")
        self.assertEqual(result.metadata, {})

    def test_only_has_the_four_documented_fields(self):
        result = PortfolioResult(
            new_positions_allowed=False, confidence=0.5, summary="Constraint violated"
        )
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        self.assertEqual(
            field_names, {"new_positions_allowed", "confidence", "summary", "metadata"}
        )

    def test_is_frozen(self):
        result = PortfolioResult(new_positions_allowed=True, confidence=0.9, summary="OK")
        with self.assertRaises(Exception):
            result.new_positions_allowed = False  # type: ignore[misc]

    def test_rejects_non_bool_new_positions_allowed(self):
        with self.assertRaises(PortfolioValidationError):
            PortfolioResult(
                new_positions_allowed="yes", confidence=0.9, summary="OK"  # type: ignore[arg-type]
            )

    def test_rejects_out_of_range_confidence(self):
        with self.assertRaises(PortfolioValidationError):
            PortfolioResult(new_positions_allowed=True, confidence=1.5, summary="OK")

    def test_rejects_non_finite_confidence(self):
        with self.assertRaises(PortfolioValidationError):
            PortfolioResult(
                new_positions_allowed=True, confidence=float("nan"), summary="OK"
            )

    def test_rejects_blank_summary(self):
        with self.assertRaises(PortfolioValidationError):
            PortfolioResult(new_positions_allowed=True, confidence=0.9, summary="   ")

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(TypeError):
            PortfolioResult(
                new_positions_allowed=True,
                confidence=0.9,
                summary="OK",
                metadata="not-a-dict",  # type: ignore[arg-type]
            )

    def test_with_metadata_returns_new_instance(self):
        original = PortfolioResult(
            new_positions_allowed=True, confidence=0.9, summary="OK", metadata={"a": 1}
        )
        updated = original.with_metadata(b=2)
        self.assertIsNot(updated, original)
        self.assertEqual(original.metadata, {"a": 1})
        self.assertEqual(updated.metadata, {"a": 1, "b": 2})

    def test_with_metadata_overrides_on_conflict(self):
        original = PortfolioResult(
            new_positions_allowed=True, confidence=0.9, summary="OK", metadata={"a": 1}
        )
        updated = original.with_metadata(a=99)
        self.assertEqual(updated.metadata, {"a": 99})

    def test_no_allocation_sizing_or_rebalancing_fields(self):
        # Defensive: PortfolioResult must expose exactly the four
        # documented fields -- no allocation, position size, or
        # rebalancing fields have been introduced by this part.
        result = PortfolioResult(new_positions_allowed=True, confidence=0.9, summary="OK")
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        for forbidden in (
            "allocation",
            "target_weight",
            "position_size",
            "rebalance_instructions",
            "order_id",
        ):
            self.assertNotIn(forbidden, field_names)


# ----------------------------------------------------------------------
# PortfolioContext
# ----------------------------------------------------------------------
class TestPortfolioContext(unittest.TestCase):
    def test_instantiates_with_required_fields_only(self):
        context = PortfolioContext(symbol="BTCUSDT", timeframe="1h", portfolio=make_portfolio())
        self.assertEqual(context.symbol, "BTCUSDT")
        self.assertEqual(context.timeframe, "1h")
        self.assertIsInstance(context.portfolio, Portfolio)
        self.assertIsNone(context.strategy_result)
        self.assertIsNone(context.risk_result)
        self.assertEqual(context.metadata, {})

    def test_accepts_optional_strategy_result(self):
        context = PortfolioContext(
            symbol="BTCUSDT",
            timeframe="1h",
            portfolio=make_portfolio(),
            strategy_result=make_strategy_result(),
        )
        self.assertTrue(context.has_strategy_result())
        self.assertFalse(context.has_risk_result())

    def test_accepts_optional_risk_result(self):
        context = PortfolioContext(
            symbol="BTCUSDT",
            timeframe="1h",
            portfolio=make_portfolio(),
            risk_result=make_risk_result(),
        )
        self.assertTrue(context.has_risk_result())
        self.assertFalse(context.has_strategy_result())

    def test_accepts_both_optional_results(self):
        context = PortfolioContext(
            symbol="BTCUSDT",
            timeframe="1h",
            portfolio=make_portfolio(),
            strategy_result=make_strategy_result(),
            risk_result=make_risk_result(),
        )
        self.assertTrue(context.has_strategy_result())
        self.assertTrue(context.has_risk_result())

    def test_has_strategy_result_false_when_absent(self):
        context = PortfolioContext(symbol="BTCUSDT", timeframe="1h", portfolio=make_portfolio())
        self.assertFalse(context.has_strategy_result())

    def test_has_risk_result_false_when_absent(self):
        context = PortfolioContext(symbol="BTCUSDT", timeframe="1h", portfolio=make_portfolio())
        self.assertFalse(context.has_risk_result())

    def test_is_frozen(self):
        context = PortfolioContext(symbol="BTCUSDT", timeframe="1h", portfolio=make_portfolio())
        with self.assertRaises(Exception):
            context.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_rejects_blank_symbol(self):
        with self.assertRaises(InvalidPortfolioContextError):
            PortfolioContext(symbol="   ", timeframe="1h", portfolio=make_portfolio())

    def test_rejects_blank_timeframe(self):
        with self.assertRaises(InvalidPortfolioContextError):
            PortfolioContext(symbol="BTCUSDT", timeframe="", portfolio=make_portfolio())

    def test_rejects_non_portfolio(self):
        with self.assertRaises(InvalidPortfolioContextError):
            PortfolioContext(
                symbol="BTCUSDT",
                timeframe="1h",
                portfolio="not-a-portfolio",  # type: ignore[arg-type]
            )

    def test_rejects_invalid_strategy_result(self):
        with self.assertRaises(InvalidPortfolioContextError):
            PortfolioContext(
                symbol="BTCUSDT",
                timeframe="1h",
                portfolio=make_portfolio(),
                strategy_result="not-a-strategy-result",  # type: ignore[arg-type]
            )

    def test_rejects_invalid_risk_result(self):
        with self.assertRaises(InvalidPortfolioContextError):
            PortfolioContext(
                symbol="BTCUSDT",
                timeframe="1h",
                portfolio=make_portfolio(),
                risk_result="not-a-risk-result",  # type: ignore[arg-type]
            )

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(InvalidPortfolioContextError):
            PortfolioContext(
                symbol="BTCUSDT",
                timeframe="1h",
                portfolio=make_portfolio(),
                metadata="not-a-dict",  # type: ignore[arg-type]
            )


# ----------------------------------------------------------------------
# strategies.portfolio_management.utils
# ----------------------------------------------------------------------
class TestUtils(unittest.TestCase):
    def test_validate_non_empty_str_accepts_valid_string(self):
        self.assertEqual(validate_non_empty_str("BTCUSDT", name="symbol"), "BTCUSDT")

    def test_validate_non_empty_str_rejects_blank(self):
        with self.assertRaises(PortfolioValidationError):
            validate_non_empty_str("   ", name="symbol")

    def test_validate_non_empty_str_rejects_non_string(self):
        with self.assertRaises(PortfolioValidationError):
            validate_non_empty_str(123, name="symbol")  # type: ignore[arg-type]

    def test_validate_unit_range_accepts_boundaries(self):
        self.assertEqual(validate_unit_range(0.0, name="confidence"), 0.0)
        self.assertEqual(validate_unit_range(1.0, name="confidence"), 1.0)

    def test_validate_unit_range_rejects_out_of_range(self):
        with self.assertRaises(PortfolioValidationError):
            validate_unit_range(1.1, name="confidence")
        with self.assertRaises(PortfolioValidationError):
            validate_unit_range(-0.1, name="confidence")

    def test_validate_unit_range_rejects_non_numeric(self):
        with self.assertRaises(PortfolioValidationError):
            validate_unit_range("high", name="confidence")  # type: ignore[arg-type]

    def test_validate_unit_range_rejects_bool(self):
        with self.assertRaises(PortfolioValidationError):
            validate_unit_range(True, name="confidence")  # type: ignore[arg-type]

    def test_validate_unit_range_rejects_non_finite(self):
        with self.assertRaises(PortfolioValidationError):
            validate_unit_range(float("inf"), name="confidence")

    def test_validate_bool_accepts_bool(self):
        self.assertTrue(validate_bool(True, name="new_positions_allowed"))
        self.assertFalse(validate_bool(False, name="new_positions_allowed"))

    def test_validate_bool_rejects_non_bool(self):
        with self.assertRaises(PortfolioValidationError):
            validate_bool(1, name="new_positions_allowed")  # type: ignore[arg-type]

    def test_clip_clamps_low_and_high(self):
        self.assertEqual(clip(-0.5), 0.0)
        self.assertEqual(clip(1.5), 1.0)
        self.assertEqual(clip(0.5), 0.5)

    def test_clip_respects_custom_bounds(self):
        self.assertEqual(clip(5, low=0, high=10), 5)
        self.assertEqual(clip(-5, low=0, high=10), 0)
        self.assertEqual(clip(15, low=0, high=10), 10)

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
# strategies.portfolio_management.exceptions
# ----------------------------------------------------------------------
class TestExceptionHierarchy(unittest.TestCase):
    def test_portfolio_validation_error_is_portfolio_error(self):
        self.assertTrue(issubclass(PortfolioValidationError, PortfolioError))

    def test_invalid_portfolio_context_error_is_portfolio_validation_error(self):
        self.assertTrue(issubclass(InvalidPortfolioContextError, PortfolioValidationError))

    def test_insufficient_portfolio_data_error_is_portfolio_error(self):
        self.assertTrue(issubclass(InsufficientPortfolioDataError, PortfolioError))
        self.assertFalse(issubclass(InsufficientPortfolioDataError, PortfolioValidationError))

    def test_portfolio_manager_configuration_error_is_portfolio_error(self):
        self.assertTrue(issubclass(PortfolioManagerConfigurationError, PortfolioError))

    def test_portfolio_error_is_exception(self):
        self.assertTrue(issubclass(PortfolioError, Exception))


# ----------------------------------------------------------------------
# BasePortfolioManager (via a minimal concrete fake, mirroring
# test_risk_management.py's FakeRiskManager / test_strategies.py's
# fake BaseStrategy pattern)
# ----------------------------------------------------------------------
class FakePortfolioManager(BasePortfolioManager):
    """Minimal concrete `BasePortfolioManager` used only to exercise the base class."""

    def __init__(self, *, name=None, new_positions_allowed: bool = True):
        super().__init__(name=name)
        self._new_positions_allowed = new_positions_allowed

    def evaluate(self, context: PortfolioContext) -> PortfolioResult:
        self.validate_context(context)
        if context.portfolio.cash_balance <= 0:
            raise InsufficientPortfolioDataError("portfolio has no available cash balance")
        return self._build_result(
            new_positions_allowed=self._new_positions_allowed,
            confidence=0.75,
            summary=f"Evaluated {context.symbol} portfolio state",
            metadata={"evaluated_by": self.name},
        )


class TestBasePortfolioManager(unittest.TestCase):
    def test_defaults_name_to_class_name(self):
        manager = FakePortfolioManager()
        self.assertEqual(manager.name, "FakePortfolioManager")

    def test_accepts_custom_name(self):
        manager = FakePortfolioManager(name="CustomPortfolioManager")
        self.assertEqual(manager.name, "CustomPortfolioManager")

    def test_cannot_instantiate_abstract_base_directly(self):
        with self.assertRaises(TypeError):
            BasePortfolioManager()  # type: ignore[abstract]

    def test_validate_context_accepts_valid_context(self):
        manager = FakePortfolioManager()
        context = PortfolioContext(symbol="BTCUSDT", timeframe="1h", portfolio=make_portfolio())
        self.assertIs(manager.validate_context(context), context)

    def test_validate_context_rejects_non_context(self):
        manager = FakePortfolioManager()
        with self.assertRaises(InvalidPortfolioContextError):
            manager.validate_context("not-a-context")  # type: ignore[arg-type]

    def test_evaluate_returns_portfolio_result(self):
        manager = FakePortfolioManager(new_positions_allowed=True)
        context = PortfolioContext(symbol="BTCUSDT", timeframe="1h", portfolio=make_portfolio())
        result = manager.evaluate(context)
        self.assertIsInstance(result, PortfolioResult)
        self.assertTrue(result.new_positions_allowed)
        self.assertEqual(result.confidence, 0.75)
        self.assertEqual(result.metadata, {"evaluated_by": "FakePortfolioManager"})

    def test_evaluate_raises_insufficient_data_when_no_cash(self):
        manager = FakePortfolioManager()
        context = PortfolioContext(
            symbol="BTCUSDT",
            timeframe="1h",
            portfolio=make_portfolio(cash_balance=Decimal("0")),
        )
        with self.assertRaises(InsufficientPortfolioDataError):
            manager.evaluate(context)

    def test_build_result_defaults_metadata_to_empty_dict(self):
        manager = FakePortfolioManager()
        result = manager._build_result(
            new_positions_allowed=False, confidence=0.4, summary="Rejected"
        )
        self.assertEqual(result.metadata, {})

    def test_repr_includes_class_and_name(self):
        manager = FakePortfolioManager(name="Guard")
        self.assertEqual(repr(manager), "FakePortfolioManager(name='Guard')")


# ----------------------------------------------------------------------
# Integration: a realistic PortfolioContext built from a real
# StrategyResult + RiskResult + Portfolio, evaluated end-to-end by a
# real BasePortfolioManager subclass.
# ----------------------------------------------------------------------
class TestIntegration(unittest.TestCase):
    def test_end_to_end_evaluation_with_strategy_and_risk_results(self):
        manager = FakePortfolioManager(new_positions_allowed=True)
        context = PortfolioContext(
            symbol="BTCUSDT",
            timeframe="1h",
            portfolio=make_portfolio(cash_balance=Decimal("5000")),
            strategy_result=make_strategy_result(
                action=SignalDirection.SELL, confidence=0.6
            ),
            risk_result=make_risk_result(approved=True, risk_score=0.15),
        )
        result = manager.evaluate(context)

        self.assertTrue(context.has_strategy_result())
        self.assertTrue(context.has_risk_result())
        self.assertTrue(result.new_positions_allowed)
        self.assertIn("BTCUSDT", result.summary)

    def test_downgraded_strategy_and_unapproved_risk_still_just_data(self):
        # PortfolioContext is a pure data container: it does not itself
        # interpret an unapproved RiskResult or a HOLD StrategyResult --
        # that remains a concrete BasePortfolioManager's job (future
        # Portfolio Management part), not this foundation's.
        context = PortfolioContext(
            symbol="BTCUSDT",
            timeframe="1h",
            portfolio=make_portfolio(),
            strategy_result=make_strategy_result(action=SignalDirection.HOLD, confidence=0.3),
            risk_result=make_risk_result(approved=False, risk_score=0.9),
        )
        self.assertEqual(context.strategy_result.action, SignalDirection.HOLD)
        self.assertFalse(context.risk_result.approved)

    def test_no_allocation_sizing_or_rebalancing_fields_end_to_end(self):
        manager = FakePortfolioManager()
        context = PortfolioContext(symbol="BTCUSDT", timeframe="1h", portfolio=make_portfolio())
        result = manager.evaluate(context)
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        for forbidden in ("allocation", "target_weight", "position_size", "order_id"):
            self.assertNotIn(forbidden, field_names)


if __name__ == "__main__":
    unittest.main()
