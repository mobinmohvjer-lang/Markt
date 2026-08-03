"""
test_execution.py
-------------------
Purpose:
    Unit tests for the Execution Engine foundation (Part 1):
    `ExecutionResult`, `ExecutionContext`, `BaseExecutionEngine`, and
    the `execution.exceptions` / `execution.utils` helpers.

Uses the standard-library ``unittest`` framework, matching the
`analysis`/`signals`/`strategies`/`strategies.risk_management`/
`strategies.portfolio_management`/`backtesting` test suites (no
external test-runner dependency).

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from core.entities.portfolio import Portfolio
from core.enums import SignalDirection

from strategies.result import StrategyResult
from strategies.risk_management.result import RiskResult
from strategies.portfolio_management.result import PortfolioResult

from execution import (
    BaseExecutionEngine,
    ExecutionContext,
    ExecutionEngineConfigurationError,
    ExecutionError,
    ExecutionResult,
    ExecutionValidationError,
    InsufficientExecutionDataError,
    InvalidExecutionContextError,
)
from execution.utils import (
    clip,
    merge_metadata,
    validate_bool,
    validate_non_empty_str,
    validate_unit_range,
)


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


def make_portfolio_result(*, new_positions_allowed: bool = True) -> PortfolioResult:
    return PortfolioResult(
        new_positions_allowed=new_positions_allowed,
        confidence=0.85,
        summary="Portfolio has capacity for a new position",
    )


# ----------------------------------------------------------------------
# ExecutionResult
# ----------------------------------------------------------------------
class TestExecutionResult(unittest.TestCase):
    def test_instantiates_with_required_fields(self):
        result = ExecutionResult(
            execution_approved=True,
            confidence=0.9,
            summary="Decision cleared for execution",
        )
        self.assertTrue(result.execution_approved)
        self.assertEqual(result.confidence, 0.9)
        self.assertEqual(result.summary, "Decision cleared for execution")
        self.assertEqual(result.metadata, {})

    def test_only_has_the_four_documented_fields(self):
        result = ExecutionResult(
            execution_approved=False, confidence=0.5, summary="Not cleared"
        )
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        self.assertEqual(
            field_names, {"execution_approved", "confidence", "summary", "metadata"}
        )

    def test_is_frozen(self):
        result = ExecutionResult(execution_approved=True, confidence=0.9, summary="OK")
        with self.assertRaises(Exception):
            result.execution_approved = False  # type: ignore[misc]

    def test_rejects_non_bool_execution_approved(self):
        with self.assertRaises(ExecutionValidationError):
            ExecutionResult(
                execution_approved="yes", confidence=0.9, summary="OK"  # type: ignore[arg-type]
            )

    def test_rejects_out_of_range_confidence(self):
        with self.assertRaises(ExecutionValidationError):
            ExecutionResult(execution_approved=True, confidence=1.5, summary="OK")

    def test_rejects_non_finite_confidence(self):
        with self.assertRaises(ExecutionValidationError):
            ExecutionResult(
                execution_approved=True, confidence=float("nan"), summary="OK"
            )

    def test_rejects_blank_summary(self):
        with self.assertRaises(ExecutionValidationError):
            ExecutionResult(execution_approved=True, confidence=0.9, summary="   ")

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(TypeError):
            ExecutionResult(
                execution_approved=True,
                confidence=0.9,
                summary="OK",
                metadata="not-a-dict",  # type: ignore[arg-type]
            )

    def test_with_metadata_returns_new_instance(self):
        original = ExecutionResult(
            execution_approved=True, confidence=0.9, summary="OK", metadata={"a": 1}
        )
        updated = original.with_metadata(b=2)
        self.assertIsNot(updated, original)
        self.assertEqual(original.metadata, {"a": 1})
        self.assertEqual(updated.metadata, {"a": 1, "b": 2})

    def test_with_metadata_overrides_on_conflict(self):
        original = ExecutionResult(
            execution_approved=True, confidence=0.9, summary="OK", metadata={"a": 1}
        )
        updated = original.with_metadata(a=99)
        self.assertEqual(updated.metadata, {"a": 99})

    def test_no_order_broker_or_networking_fields(self):
        # Defensive: ExecutionResult must expose exactly the four
        # documented fields -- no order/broker/networking fields have
        # been introduced by this part.
        result = ExecutionResult(execution_approved=True, confidence=0.9, summary="OK")
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        for forbidden in (
            "order_id",
            "fill_price",
            "fill_quantity",
            "broker",
            "exchange",
            "venue",
        ):
            self.assertNotIn(forbidden, field_names)


# ----------------------------------------------------------------------
# ExecutionContext
# ----------------------------------------------------------------------
class TestExecutionContext(unittest.TestCase):
    def test_instantiates_with_required_fields_only(self):
        context = ExecutionContext(symbol="BTCUSDT", timeframe="1h", portfolio=make_portfolio())
        self.assertEqual(context.symbol, "BTCUSDT")
        self.assertEqual(context.timeframe, "1h")
        self.assertIsInstance(context.portfolio, Portfolio)
        self.assertIsNone(context.strategy_result)
        self.assertIsNone(context.risk_result)
        self.assertIsNone(context.portfolio_result)
        self.assertEqual(context.metadata, {})

    def test_accepts_optional_strategy_result(self):
        context = ExecutionContext(
            symbol="BTCUSDT",
            timeframe="1h",
            portfolio=make_portfolio(),
            strategy_result=make_strategy_result(),
        )
        self.assertTrue(context.has_strategy_result())
        self.assertFalse(context.has_risk_result())
        self.assertFalse(context.has_portfolio_result())

    def test_accepts_optional_risk_result(self):
        context = ExecutionContext(
            symbol="BTCUSDT",
            timeframe="1h",
            portfolio=make_portfolio(),
            risk_result=make_risk_result(),
        )
        self.assertTrue(context.has_risk_result())
        self.assertFalse(context.has_strategy_result())
        self.assertFalse(context.has_portfolio_result())

    def test_accepts_optional_portfolio_result(self):
        context = ExecutionContext(
            symbol="BTCUSDT",
            timeframe="1h",
            portfolio=make_portfolio(),
            portfolio_result=make_portfolio_result(),
        )
        self.assertTrue(context.has_portfolio_result())
        self.assertFalse(context.has_strategy_result())
        self.assertFalse(context.has_risk_result())

    def test_accepts_all_optional_results(self):
        context = ExecutionContext(
            symbol="BTCUSDT",
            timeframe="1h",
            portfolio=make_portfolio(),
            strategy_result=make_strategy_result(),
            risk_result=make_risk_result(),
            portfolio_result=make_portfolio_result(),
        )
        self.assertTrue(context.has_strategy_result())
        self.assertTrue(context.has_risk_result())
        self.assertTrue(context.has_portfolio_result())

    def test_has_strategy_result_false_when_absent(self):
        context = ExecutionContext(symbol="BTCUSDT", timeframe="1h", portfolio=make_portfolio())
        self.assertFalse(context.has_strategy_result())

    def test_has_risk_result_false_when_absent(self):
        context = ExecutionContext(symbol="BTCUSDT", timeframe="1h", portfolio=make_portfolio())
        self.assertFalse(context.has_risk_result())

    def test_has_portfolio_result_false_when_absent(self):
        context = ExecutionContext(symbol="BTCUSDT", timeframe="1h", portfolio=make_portfolio())
        self.assertFalse(context.has_portfolio_result())

    def test_is_frozen(self):
        context = ExecutionContext(symbol="BTCUSDT", timeframe="1h", portfolio=make_portfolio())
        with self.assertRaises(Exception):
            context.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_rejects_blank_symbol(self):
        with self.assertRaises(InvalidExecutionContextError):
            ExecutionContext(symbol="   ", timeframe="1h", portfolio=make_portfolio())

    def test_rejects_blank_timeframe(self):
        with self.assertRaises(InvalidExecutionContextError):
            ExecutionContext(symbol="BTCUSDT", timeframe="", portfolio=make_portfolio())

    def test_rejects_non_portfolio(self):
        with self.assertRaises(InvalidExecutionContextError):
            ExecutionContext(
                symbol="BTCUSDT",
                timeframe="1h",
                portfolio="not-a-portfolio",  # type: ignore[arg-type]
            )

    def test_rejects_invalid_strategy_result(self):
        with self.assertRaises(InvalidExecutionContextError):
            ExecutionContext(
                symbol="BTCUSDT",
                timeframe="1h",
                portfolio=make_portfolio(),
                strategy_result="not-a-strategy-result",  # type: ignore[arg-type]
            )

    def test_rejects_invalid_risk_result(self):
        with self.assertRaises(InvalidExecutionContextError):
            ExecutionContext(
                symbol="BTCUSDT",
                timeframe="1h",
                portfolio=make_portfolio(),
                risk_result="not-a-risk-result",  # type: ignore[arg-type]
            )

    def test_rejects_invalid_portfolio_result(self):
        with self.assertRaises(InvalidExecutionContextError):
            ExecutionContext(
                symbol="BTCUSDT",
                timeframe="1h",
                portfolio=make_portfolio(),
                portfolio_result="not-a-portfolio-result",  # type: ignore[arg-type]
            )

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(InvalidExecutionContextError):
            ExecutionContext(
                symbol="BTCUSDT",
                timeframe="1h",
                portfolio=make_portfolio(),
                metadata="not-a-dict",  # type: ignore[arg-type]
            )


# ----------------------------------------------------------------------
# execution.utils
# ----------------------------------------------------------------------
class TestUtils(unittest.TestCase):
    def test_validate_non_empty_str_accepts_valid_string(self):
        self.assertEqual(validate_non_empty_str("BTCUSDT", name="symbol"), "BTCUSDT")

    def test_validate_non_empty_str_rejects_blank(self):
        with self.assertRaises(ExecutionValidationError):
            validate_non_empty_str("   ", name="symbol")

    def test_validate_non_empty_str_rejects_non_string(self):
        with self.assertRaises(ExecutionValidationError):
            validate_non_empty_str(123, name="symbol")  # type: ignore[arg-type]

    def test_validate_unit_range_accepts_boundaries(self):
        self.assertEqual(validate_unit_range(0.0, name="confidence"), 0.0)
        self.assertEqual(validate_unit_range(1.0, name="confidence"), 1.0)

    def test_validate_unit_range_rejects_out_of_range(self):
        with self.assertRaises(ExecutionValidationError):
            validate_unit_range(1.1, name="confidence")
        with self.assertRaises(ExecutionValidationError):
            validate_unit_range(-0.1, name="confidence")

    def test_validate_unit_range_rejects_non_numeric(self):
        with self.assertRaises(ExecutionValidationError):
            validate_unit_range("high", name="confidence")  # type: ignore[arg-type]

    def test_validate_unit_range_rejects_bool(self):
        with self.assertRaises(ExecutionValidationError):
            validate_unit_range(True, name="confidence")  # type: ignore[arg-type]

    def test_validate_unit_range_rejects_non_finite(self):
        with self.assertRaises(ExecutionValidationError):
            validate_unit_range(float("inf"), name="confidence")

    def test_validate_bool_accepts_bool(self):
        self.assertTrue(validate_bool(True, name="execution_approved"))
        self.assertFalse(validate_bool(False, name="execution_approved"))

    def test_validate_bool_rejects_non_bool(self):
        with self.assertRaises(ExecutionValidationError):
            validate_bool(1, name="execution_approved")  # type: ignore[arg-type]

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
# execution.exceptions
# ----------------------------------------------------------------------
class TestExceptionHierarchy(unittest.TestCase):
    def test_execution_validation_error_is_execution_error(self):
        self.assertTrue(issubclass(ExecutionValidationError, ExecutionError))

    def test_invalid_execution_context_error_is_execution_validation_error(self):
        self.assertTrue(issubclass(InvalidExecutionContextError, ExecutionValidationError))

    def test_insufficient_execution_data_error_is_execution_error(self):
        self.assertTrue(issubclass(InsufficientExecutionDataError, ExecutionError))
        self.assertFalse(issubclass(InsufficientExecutionDataError, ExecutionValidationError))

    def test_execution_engine_configuration_error_is_execution_error(self):
        self.assertTrue(issubclass(ExecutionEngineConfigurationError, ExecutionError))

    def test_execution_error_is_exception(self):
        self.assertTrue(issubclass(ExecutionError, Exception))


# ----------------------------------------------------------------------
# BaseExecutionEngine (via a minimal concrete fake, mirroring
# test_portfolio_management.py's FakePortfolioManager /
# test_risk_management.py's FakeRiskManager pattern)
# ----------------------------------------------------------------------
class FakeExecutionEngine(BaseExecutionEngine):
    """Minimal concrete `BaseExecutionEngine` used only to exercise the base class."""

    def __init__(self, *, name=None, execution_approved: bool = True):
        super().__init__(name=name)
        self._execution_approved = execution_approved

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        self.validate_context(context)
        if context.portfolio.cash_balance <= 0:
            raise InsufficientExecutionDataError("portfolio has no available cash balance")
        return self._build_result(
            execution_approved=self._execution_approved,
            confidence=0.75,
            summary=f"Evaluated {context.symbol} for execution readiness",
            metadata={"evaluated_by": self.name},
        )


class TestBaseExecutionEngine(unittest.TestCase):
    def test_defaults_name_to_class_name(self):
        engine = FakeExecutionEngine()
        self.assertEqual(engine.name, "FakeExecutionEngine")

    def test_accepts_custom_name(self):
        engine = FakeExecutionEngine(name="CustomExecutionEngine")
        self.assertEqual(engine.name, "CustomExecutionEngine")

    def test_cannot_instantiate_abstract_base_directly(self):
        with self.assertRaises(TypeError):
            BaseExecutionEngine()  # type: ignore[abstract]

    def test_validate_context_accepts_valid_context(self):
        engine = FakeExecutionEngine()
        context = ExecutionContext(symbol="BTCUSDT", timeframe="1h", portfolio=make_portfolio())
        self.assertIs(engine.validate_context(context), context)

    def test_validate_context_rejects_non_context(self):
        engine = FakeExecutionEngine()
        with self.assertRaises(InvalidExecutionContextError):
            engine.validate_context("not-a-context")  # type: ignore[arg-type]

    def test_execute_returns_execution_result(self):
        engine = FakeExecutionEngine(execution_approved=True)
        context = ExecutionContext(symbol="BTCUSDT", timeframe="1h", portfolio=make_portfolio())
        result = engine.execute(context)
        self.assertIsInstance(result, ExecutionResult)
        self.assertTrue(result.execution_approved)
        self.assertEqual(result.confidence, 0.75)
        self.assertEqual(result.metadata, {"evaluated_by": "FakeExecutionEngine"})

    def test_execute_raises_insufficient_data_when_no_cash(self):
        engine = FakeExecutionEngine()
        context = ExecutionContext(
            symbol="BTCUSDT",
            timeframe="1h",
            portfolio=make_portfolio(cash_balance=Decimal("0")),
        )
        with self.assertRaises(InsufficientExecutionDataError):
            engine.execute(context)

    def test_build_result_defaults_metadata_to_empty_dict(self):
        engine = FakeExecutionEngine()
        result = engine._build_result(
            execution_approved=False, confidence=0.4, summary="Rejected"
        )
        self.assertEqual(result.metadata, {})

    def test_repr_includes_class_and_name(self):
        engine = FakeExecutionEngine(name="Gatekeeper")
        self.assertEqual(repr(engine), "FakeExecutionEngine(name='Gatekeeper')")


# ----------------------------------------------------------------------
# Integration: a realistic ExecutionContext built from a real
# StrategyResult + RiskResult + PortfolioResult + Portfolio, evaluated
# end-to-end by a real BaseExecutionEngine subclass.
# ----------------------------------------------------------------------
class TestIntegration(unittest.TestCase):
    def test_end_to_end_evaluation_with_all_upstream_results(self):
        engine = FakeExecutionEngine(execution_approved=True)
        context = ExecutionContext(
            symbol="BTCUSDT",
            timeframe="1h",
            portfolio=make_portfolio(cash_balance=Decimal("5000")),
            strategy_result=make_strategy_result(action=SignalDirection.SELL, confidence=0.6),
            risk_result=make_risk_result(approved=True, risk_score=0.15),
            portfolio_result=make_portfolio_result(new_positions_allowed=True),
        )
        result = engine.execute(context)

        self.assertTrue(context.has_strategy_result())
        self.assertTrue(context.has_risk_result())
        self.assertTrue(context.has_portfolio_result())
        self.assertTrue(result.execution_approved)
        self.assertIn("BTCUSDT", result.summary)

    def test_unapproved_upstream_results_still_just_data(self):
        # ExecutionContext is a pure data container: it does not itself
        # interpret an unapproved RiskResult, a blocked PortfolioResult,
        # or a HOLD StrategyResult -- that remains a concrete
        # BaseExecutionEngine's job (future Execution Engine part), not
        # this foundation's.
        context = ExecutionContext(
            symbol="BTCUSDT",
            timeframe="1h",
            portfolio=make_portfolio(),
            strategy_result=make_strategy_result(action=SignalDirection.HOLD, confidence=0.3),
            risk_result=make_risk_result(approved=False, risk_score=0.9),
            portfolio_result=make_portfolio_result(new_positions_allowed=False),
        )
        self.assertEqual(context.strategy_result.action, SignalDirection.HOLD)
        self.assertFalse(context.risk_result.approved)
        self.assertFalse(context.portfolio_result.new_positions_allowed)

    def test_no_order_broker_or_networking_fields_end_to_end(self):
        engine = FakeExecutionEngine()
        context = ExecutionContext(symbol="BTCUSDT", timeframe="1h", portfolio=make_portfolio())
        result = engine.execute(context)
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        for forbidden in ("order_id", "fill_price", "fill_quantity", "broker", "exchange"):
            self.assertNotIn(forbidden, field_names)


if __name__ == "__main__":
    unittest.main()
