"""
test_strategies.py
--------------------
Purpose:
    Unit tests for the Strategy Engine foundation (Part 1):
    `StrategyResult`, `StrategyContext`, `BaseStrategy`, and the
    `strategies.exceptions` / `strategies.utils` helpers.

Uses the standard-library ``unittest`` framework, matching the
`analysis`/`signals`/`strategies.risk_management` test suites (no
external test-runner dependency).

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from analysis.result import AnalysisResult
from core.enums import SignalDirection
from signals.result import SignalResult
from strategies import (
    BaseStrategy,
    InsufficientStrategyDataError,
    InvalidStrategyContextError,
    StrategyConfigurationError,
    StrategyContext,
    StrategyError,
    StrategyResult,
    StrategyValidationError,
)
from strategies.risk_management.result import RiskResult
from strategies.utils import (
    clip,
    merge_metadata,
    validate_action,
    validate_instance_list,
    validate_non_empty_str,
    validate_unit_range,
)

NOW = datetime.now(timezone.utc)


def make_analysis_result(
    *, analyzer_name: str = "AnalysisAggregator", score: float = 0.6, confidence: float = 0.8
) -> AnalysisResult:
    return AnalysisResult(
        analyzer_name=analyzer_name,
        symbol="BTCUSDT",
        timeframe="1h",
        score=score,
        confidence=confidence,
        summary="Bullish confluence across trend/momentum",
        timestamp=NOW,
    )


def make_signal_result(
    *, direction: SignalDirection = SignalDirection.BUY, strength: float = 0.7,
    confidence: float = 0.8,
) -> SignalResult:
    return SignalResult(
        direction=direction,
        strength=strength,
        confidence=confidence,
        summary="Technical signal generator produced a bullish signal",
    )


def make_risk_result(*, approved: bool = True, risk_score: float = 0.2) -> RiskResult:
    return RiskResult(
        approved=approved,
        risk_score=risk_score,
        confidence=0.75,
        summary="Signal within acceptable risk tolerance",
    )


# ----------------------------------------------------------------------
# StrategyResult
# ----------------------------------------------------------------------
class TestStrategyResult(unittest.TestCase):
    def test_instantiates_with_required_fields(self):
        result = StrategyResult(
            action=SignalDirection.BUY,
            confidence=0.9,
            summary="Enough confluence to act",
        )
        self.assertEqual(result.action, SignalDirection.BUY)
        self.assertEqual(result.confidence, 0.9)
        self.assertEqual(result.summary, "Enough confluence to act")
        self.assertEqual(result.metadata, {})

    def test_only_has_the_four_documented_fields(self):
        result = StrategyResult(action=SignalDirection.HOLD, confidence=0.5, summary="Wait")
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        self.assertEqual(field_names, {"action", "confidence", "summary", "metadata"})

    def test_is_frozen(self):
        result = StrategyResult(action=SignalDirection.BUY, confidence=0.9, summary="OK")
        with self.assertRaises(Exception):
            result.action = SignalDirection.SELL  # type: ignore[misc]

    def test_rejects_non_signal_direction_action(self):
        with self.assertRaises(StrategyValidationError):
            StrategyResult(action="buy", confidence=0.9, summary="OK")  # type: ignore[arg-type]

    def test_rejects_out_of_range_confidence(self):
        with self.assertRaises(StrategyValidationError):
            StrategyResult(action=SignalDirection.BUY, confidence=1.5, summary="OK")

    def test_rejects_non_finite_confidence(self):
        with self.assertRaises(StrategyValidationError):
            StrategyResult(action=SignalDirection.BUY, confidence=float("nan"), summary="OK")

    def test_rejects_blank_summary(self):
        with self.assertRaises(StrategyValidationError):
            StrategyResult(action=SignalDirection.BUY, confidence=0.9, summary="   ")

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(TypeError):
            StrategyResult(
                action=SignalDirection.BUY,
                confidence=0.9,
                summary="OK",
                metadata="not-a-dict",  # type: ignore[arg-type]
            )

    def test_with_metadata_returns_new_instance(self):
        original = StrategyResult(action=SignalDirection.BUY, confidence=0.9, summary="OK")
        updated = original.with_metadata(a=99)
        self.assertIsNot(original, updated)
        self.assertEqual(original.metadata, {})
        self.assertEqual(updated.metadata, {"a": 99})

    def test_with_metadata_overrides_on_conflict(self):
        original = StrategyResult(
            action=SignalDirection.BUY, confidence=0.9, summary="OK", metadata={"a": 1}
        )
        updated = original.with_metadata(a=2)
        self.assertEqual(updated.metadata, {"a": 2})

    def test_no_position_sizing_stop_loss_or_order_fields(self):
        # Defensive: StrategyResult must expose exactly the four
        # documented fields -- no position size, stop loss, take
        # profit, order-id, or strategy_name fields introduced.
        result = StrategyResult(action=SignalDirection.HOLD, confidence=0.5, summary="Wait")
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        for forbidden in (
            "position_size",
            "stop_loss",
            "take_profit",
            "order_id",
            "strategy_name",
        ):
            self.assertNotIn(forbidden, field_names)


# ----------------------------------------------------------------------
# StrategyContext
# ----------------------------------------------------------------------
class TestStrategyContext(unittest.TestCase):
    def test_instantiates_with_required_fields_only(self):
        context = StrategyContext(symbol="BTCUSDT", timeframe="1h")
        self.assertEqual(context.symbol, "BTCUSDT")
        self.assertEqual(context.timeframe, "1h")
        self.assertEqual(context.analysis_results, [])
        self.assertIsNone(context.signal_result)
        self.assertIsNone(context.risk_result)
        self.assertEqual(context.metadata, {})

    def test_accepts_full_analysis_signal_and_risk_results(self):
        analysis_result = make_analysis_result()
        signal_result = make_signal_result()
        risk_result = make_risk_result()
        context = StrategyContext(
            symbol="BTCUSDT",
            timeframe="1h",
            analysis_results=[analysis_result],
            signal_result=signal_result,
            risk_result=risk_result,
        )
        self.assertEqual(context.analysis_results, [analysis_result])
        self.assertIs(context.signal_result, signal_result)
        self.assertIs(context.risk_result, risk_result)

    def test_has_analysis_results_false_when_absent(self):
        context = StrategyContext(symbol="BTCUSDT", timeframe="1h")
        self.assertFalse(context.has_analysis_results())

    def test_has_analysis_results_true_when_present(self):
        context = StrategyContext(
            symbol="BTCUSDT", timeframe="1h", analysis_results=[make_analysis_result()]
        )
        self.assertTrue(context.has_analysis_results())

    def test_has_signal_result_reflects_presence(self):
        without = StrategyContext(symbol="BTCUSDT", timeframe="1h")
        with_signal = StrategyContext(
            symbol="BTCUSDT", timeframe="1h", signal_result=make_signal_result()
        )
        self.assertFalse(without.has_signal_result())
        self.assertTrue(with_signal.has_signal_result())

    def test_has_risk_result_reflects_presence(self):
        without = StrategyContext(symbol="BTCUSDT", timeframe="1h")
        with_risk = StrategyContext(
            symbol="BTCUSDT", timeframe="1h", risk_result=make_risk_result()
        )
        self.assertFalse(without.has_risk_result())
        self.assertTrue(with_risk.has_risk_result())

    def test_get_analysis_result_matches_by_analyzer_name(self):
        trend_result = make_analysis_result(analyzer_name="TrendAnalyzer", score=0.4)
        aggregator_result = make_analysis_result(analyzer_name="AnalysisAggregator", score=0.5)
        context = StrategyContext(
            symbol="BTCUSDT",
            timeframe="1h",
            analysis_results=[trend_result, aggregator_result],
        )
        self.assertIs(context.get_analysis_result("AnalysisAggregator"), aggregator_result)
        self.assertIs(context.get_analysis_result("TrendAnalyzer"), trend_result)

    def test_get_analysis_result_returns_none_when_missing(self):
        context = StrategyContext(symbol="BTCUSDT", timeframe="1h")
        self.assertIsNone(context.get_analysis_result("AnalysisAggregator"))

    def test_is_frozen(self):
        context = StrategyContext(symbol="BTCUSDT", timeframe="1h")
        with self.assertRaises(Exception):
            context.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_rejects_blank_symbol(self):
        with self.assertRaises(InvalidStrategyContextError):
            StrategyContext(symbol="   ", timeframe="1h")

    def test_rejects_blank_timeframe(self):
        with self.assertRaises(InvalidStrategyContextError):
            StrategyContext(symbol="BTCUSDT", timeframe="")

    def test_rejects_non_list_analysis_results(self):
        with self.assertRaises(InvalidStrategyContextError):
            StrategyContext(
                symbol="BTCUSDT",
                timeframe="1h",
                analysis_results="not-a-list",  # type: ignore[arg-type]
            )

    def test_rejects_analysis_results_with_wrong_item_type(self):
        with self.assertRaises(InvalidStrategyContextError):
            StrategyContext(
                symbol="BTCUSDT",
                timeframe="1h",
                analysis_results=["not-an-analysis-result"],  # type: ignore[list-item]
            )

    def test_rejects_invalid_signal_result(self):
        with self.assertRaises(InvalidStrategyContextError):
            StrategyContext(
                symbol="BTCUSDT",
                timeframe="1h",
                signal_result="not-a-signal-result",  # type: ignore[arg-type]
            )

    def test_rejects_invalid_risk_result(self):
        with self.assertRaises(InvalidStrategyContextError):
            StrategyContext(
                symbol="BTCUSDT",
                timeframe="1h",
                risk_result="not-a-risk-result",  # type: ignore[arg-type]
            )

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(InvalidStrategyContextError):
            StrategyContext(
                symbol="BTCUSDT",
                timeframe="1h",
                metadata="not-a-dict",  # type: ignore[arg-type]
            )


# ----------------------------------------------------------------------
# strategies.utils
# ----------------------------------------------------------------------
class TestUtils(unittest.TestCase):
    def test_validate_non_empty_str_accepts_valid_string(self):
        self.assertEqual(validate_non_empty_str("BTCUSDT", name="symbol"), "BTCUSDT")

    def test_validate_non_empty_str_rejects_blank(self):
        with self.assertRaises(StrategyValidationError):
            validate_non_empty_str("   ", name="symbol")

    def test_validate_non_empty_str_rejects_non_string(self):
        with self.assertRaises(StrategyValidationError):
            validate_non_empty_str(123, name="symbol")  # type: ignore[arg-type]

    def test_validate_unit_range_accepts_boundaries(self):
        self.assertEqual(validate_unit_range(0.0, name="confidence"), 0.0)
        self.assertEqual(validate_unit_range(1.0, name="confidence"), 1.0)

    def test_validate_unit_range_rejects_out_of_range(self):
        with self.assertRaises(StrategyValidationError):
            validate_unit_range(1.1, name="confidence")
        with self.assertRaises(StrategyValidationError):
            validate_unit_range(-0.1, name="confidence")

    def test_validate_unit_range_rejects_non_numeric(self):
        with self.assertRaises(StrategyValidationError):
            validate_unit_range("high", name="confidence")  # type: ignore[arg-type]

    def test_validate_unit_range_rejects_bool(self):
        with self.assertRaises(StrategyValidationError):
            validate_unit_range(True, name="confidence")  # type: ignore[arg-type]

    def test_validate_unit_range_rejects_non_finite(self):
        with self.assertRaises(StrategyValidationError):
            validate_unit_range(float("inf"), name="confidence")

    def test_validate_action_accepts_signal_direction(self):
        self.assertEqual(validate_action(SignalDirection.SELL), SignalDirection.SELL)

    def test_validate_action_rejects_non_signal_direction(self):
        with self.assertRaises(StrategyValidationError):
            validate_action("sell")

    def test_validate_instance_list_accepts_matching_items(self):
        items = [make_analysis_result()]
        self.assertEqual(
            validate_instance_list(items, AnalysisResult, name="analysis_results"), items
        )

    def test_validate_instance_list_rejects_non_list(self):
        with self.assertRaises(StrategyValidationError):
            validate_instance_list("not-a-list", AnalysisResult, name="analysis_results")

    def test_validate_instance_list_rejects_wrong_item_type(self):
        with self.assertRaises(StrategyValidationError):
            validate_instance_list(["nope"], AnalysisResult, name="analysis_results")

    def test_clip_clamps_low_and_high(self):
        self.assertEqual(clip(-0.5), 0.0)
        self.assertEqual(clip(1.5), 1.0)
        self.assertEqual(clip(0.4), 0.4)

    def test_clip_respects_custom_bounds(self):
        self.assertEqual(clip(5, low=-1.0, high=1.0), 1.0)

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
# strategies.exceptions
# ----------------------------------------------------------------------
class TestExceptionHierarchy(unittest.TestCase):
    def test_strategy_validation_error_is_strategy_error(self):
        self.assertTrue(issubclass(StrategyValidationError, StrategyError))

    def test_invalid_strategy_context_error_is_strategy_validation_error(self):
        self.assertTrue(issubclass(InvalidStrategyContextError, StrategyValidationError))

    def test_insufficient_strategy_data_error_is_strategy_error(self):
        self.assertTrue(issubclass(InsufficientStrategyDataError, StrategyError))
        self.assertFalse(issubclass(InsufficientStrategyDataError, StrategyValidationError))

    def test_strategy_configuration_error_is_strategy_error(self):
        self.assertTrue(issubclass(StrategyConfigurationError, StrategyError))

    def test_strategy_error_is_exception(self):
        self.assertTrue(issubclass(StrategyError, Exception))


# ----------------------------------------------------------------------
# BaseStrategy (via a minimal concrete fake, mirroring
# test_risk_management.py's FakeRiskManager pattern)
# ----------------------------------------------------------------------
class FakeStrategy(BaseStrategy):
    """Minimal concrete `BaseStrategy` used only to exercise the base class."""

    def __init__(self, *, name=None, action: SignalDirection = SignalDirection.BUY):
        super().__init__(name=name)
        self._action = action

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        if not context.has_signal_result():
            raise InsufficientStrategyDataError("no SignalResult available to decide on")
        return self._build_result(
            action=self._action,
            confidence=context.signal_result.confidence,
            summary=f"Decided on {context.symbol}",
            metadata={"decided_by": self.name},
        )


class TestBaseStrategy(unittest.TestCase):
    def test_defaults_name_to_class_name(self):
        strategy = FakeStrategy()
        self.assertEqual(strategy.name, "FakeStrategy")

    def test_accepts_custom_name(self):
        strategy = FakeStrategy(name="CustomStrategy")
        self.assertEqual(strategy.name, "CustomStrategy")

    def test_cannot_instantiate_abstract_base_directly(self):
        with self.assertRaises(TypeError):
            BaseStrategy()  # type: ignore[abstract]

    def test_validate_context_accepts_valid_context(self):
        strategy = FakeStrategy()
        context = StrategyContext(symbol="BTCUSDT", timeframe="1h")
        self.assertIs(strategy.validate_context(context), context)

    def test_validate_context_rejects_non_context(self):
        strategy = FakeStrategy()
        with self.assertRaises(InvalidStrategyContextError):
            strategy.validate_context("not-a-context")  # type: ignore[arg-type]

    def test_decide_returns_strategy_result(self):
        strategy = FakeStrategy(action=SignalDirection.BUY)
        context = StrategyContext(
            symbol="BTCUSDT", timeframe="1h", signal_result=make_signal_result(confidence=0.77)
        )
        result = strategy.decide(context)
        self.assertIsInstance(result, StrategyResult)
        self.assertEqual(result.action, SignalDirection.BUY)
        self.assertEqual(result.confidence, 0.77)
        self.assertEqual(result.metadata, {"decided_by": "FakeStrategy"})

    def test_decide_raises_insufficient_data_when_no_signal_result(self):
        strategy = FakeStrategy()
        context = StrategyContext(symbol="BTCUSDT", timeframe="1h")
        with self.assertRaises(InsufficientStrategyDataError):
            strategy.decide(context)

    def test_build_result_defaults_metadata_to_empty_dict(self):
        strategy = FakeStrategy()
        result = strategy._build_result(
            action=SignalDirection.HOLD, confidence=0.4, summary="Wait"
        )
        self.assertEqual(result.metadata, {})

    def test_repr_includes_class_and_name(self):
        strategy = FakeStrategy(name="Trend")
        self.assertEqual(repr(strategy), "FakeStrategy(name='Trend')")


# ----------------------------------------------------------------------
# Integration: a realistic StrategyContext built from AnalysisResult +
# SignalResult + RiskResult, decided end-to-end by a real BaseStrategy
# subclass.
# ----------------------------------------------------------------------
class TestIntegration(unittest.TestCase):
    def test_end_to_end_decision_with_full_context(self):
        strategy = FakeStrategy(action=SignalDirection.SELL)
        context = StrategyContext(
            symbol="BTCUSDT",
            timeframe="1h",
            analysis_results=[make_analysis_result(score=-0.6)],
            signal_result=make_signal_result(direction=SignalDirection.SELL, confidence=0.6),
            risk_result=make_risk_result(approved=True, risk_score=0.3),
            metadata={"source": "integration-test"},
        )
        result = strategy.decide(context)

        self.assertTrue(context.has_analysis_results())
        self.assertTrue(context.has_signal_result())
        self.assertTrue(context.has_risk_result())
        self.assertEqual(result.action, SignalDirection.SELL)
        self.assertEqual(result.confidence, 0.6)
        self.assertIn("BTCUSDT", result.summary)

    def test_no_ai_order_execution_or_broker_fields(self):
        # Defensive: this milestone introduces no AI/order-execution
        # concepts anywhere in the Strategy Engine foundation.
        result = StrategyResult(action=SignalDirection.HOLD, confidence=0.5, summary="Wait")
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        for forbidden in ("broker", "order_id", "ai_model", "execution_status"):
            self.assertNotIn(forbidden, field_names)


if __name__ == "__main__":
    unittest.main()
