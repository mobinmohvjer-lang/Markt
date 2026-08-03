"""
test_signals.py
-------------------
Purpose:
    Unit tests for the Signal Engine foundation (Part 1):
    `SignalResult`, `SignalContext`, `BaseSignalGenerator`, and the
    `signals.exceptions` / `signals.utils` helpers.

Uses the standard-library ``unittest`` framework, matching the
`analysis`/`indicators`/`data` test suites (no external test-runner
dependency).

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from analysis.result import AnalysisResult
from core.enums import SignalDirection
from signals import (
    BaseSignalGenerator,
    InsufficientSignalDataError,
    InvalidSignalContextError,
    SignalContext,
    SignalError,
    SignalGeneratorConfigurationError,
    SignalResult,
    SignalValidationError,
)
from signals.utils import (
    merge_metadata,
    validate_direction,
    validate_instance_list,
    validate_non_empty_str,
    validate_unit_range,
)

NOW = datetime.now(timezone.utc)


def make_analysis_result(
    analyzer_name: str = "TrendAnalyzer", *, score: float = 0.5, confidence: float = 0.8
) -> AnalysisResult:
    return AnalysisResult(
        analyzer_name=analyzer_name,
        symbol="BTCUSDT",
        timeframe="1h",
        score=score,
        confidence=confidence,
        summary="Bullish trend",
    )


# ----------------------------------------------------------------------
# SignalResult
# ----------------------------------------------------------------------
class TestSignalResult(unittest.TestCase):
    def test_instantiates_with_required_fields(self):
        result = SignalResult(
            direction=SignalDirection.BUY,
            strength=0.7,
            confidence=0.8,
            summary="Bullish confluence across trend and momentum",
        )
        self.assertEqual(result.direction, SignalDirection.BUY)
        self.assertEqual(result.strength, 0.7)
        self.assertEqual(result.confidence, 0.8)
        self.assertEqual(result.summary, "Bullish confluence across trend and momentum")
        self.assertEqual(result.metadata, {})

    def test_only_has_the_five_documented_fields(self):
        result = SignalResult(
            direction=SignalDirection.HOLD, strength=0.0, confidence=0.0, summary="Neutral"
        )
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        self.assertEqual(field_names, {"direction", "strength", "confidence", "summary", "metadata"})

    def test_is_frozen(self):
        result = SignalResult(
            direction=SignalDirection.SELL, strength=0.5, confidence=0.5, summary="Bearish"
        )
        with self.assertRaises(Exception):
            result.strength = 1.0  # type: ignore[misc]

    def test_with_metadata_returns_new_instance(self):
        original = SignalResult(
            direction=SignalDirection.BUY,
            strength=0.6,
            confidence=0.6,
            summary="Bullish",
            metadata={"a": 1},
        )
        updated = original.with_metadata(b=2)
        self.assertEqual(original.metadata, {"a": 1})
        self.assertEqual(updated.metadata, {"a": 1, "b": 2})
        self.assertIsNot(original, updated)

    def test_rejects_non_signal_direction(self):
        with self.assertRaises(SignalValidationError):
            SignalResult(
                direction="buy",  # type: ignore[arg-type]
                strength=0.5,
                confidence=0.5,
                summary="Bullish",
            )

    def test_rejects_empty_summary(self):
        with self.assertRaises(SignalValidationError):
            SignalResult(
                direction=SignalDirection.BUY, strength=0.5, confidence=0.5, summary=""
            )

    def test_rejects_strength_out_of_range(self):
        with self.assertRaises(SignalValidationError):
            SignalResult(
                direction=SignalDirection.BUY, strength=1.5, confidence=0.5, summary="Bullish"
            )

    def test_rejects_negative_strength(self):
        with self.assertRaises(SignalValidationError):
            SignalResult(
                direction=SignalDirection.BUY, strength=-0.1, confidence=0.5, summary="Bullish"
            )

    def test_rejects_confidence_out_of_range(self):
        with self.assertRaises(SignalValidationError):
            SignalResult(
                direction=SignalDirection.BUY, strength=0.5, confidence=1.1, summary="Bullish"
            )

    def test_rejects_non_finite_strength(self):
        with self.assertRaises(SignalValidationError):
            SignalResult(
                direction=SignalDirection.BUY,
                strength=float("nan"),
                confidence=0.5,
                summary="Bullish",
            )

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(TypeError):
            SignalResult(
                direction=SignalDirection.BUY,
                strength=0.5,
                confidence=0.5,
                summary="Bullish",
                metadata=["not", "a", "dict"],  # type: ignore[arg-type]
            )


# ----------------------------------------------------------------------
# SignalContext
# ----------------------------------------------------------------------
class TestSignalContext(unittest.TestCase):
    def test_instantiates_with_minimal_fields(self):
        context = SignalContext(symbol="BTCUSDT", timeframe="1h")
        self.assertEqual(context.symbol, "BTCUSDT")
        self.assertEqual(context.timeframe, "1h")
        self.assertEqual(context.analysis_results, [])
        self.assertFalse(context.has_results())

    def test_holds_analysis_results_collection(self):
        trend = make_analysis_result("TrendAnalyzer")
        momentum = make_analysis_result("MomentumAnalyzer")
        context = SignalContext(
            symbol="BTCUSDT", timeframe="1h", analysis_results=[trend, momentum]
        )
        self.assertEqual(len(context.analysis_results), 2)
        self.assertIn(trend, context.analysis_results)
        self.assertTrue(context.has_results())

    def test_get_result_returns_match(self):
        trend = make_analysis_result("TrendAnalyzer")
        context = SignalContext(symbol="BTCUSDT", timeframe="1h", analysis_results=[trend])
        found = context.get_result("TrendAnalyzer")
        self.assertIs(found, trend)

    def test_get_result_returns_none_when_missing(self):
        context = SignalContext(symbol="BTCUSDT", timeframe="1h")
        self.assertIsNone(context.get_result("TrendAnalyzer"))

    def test_accepts_analysis_aggregator_shaped_result(self):
        # AnalysisAggregator produces a plain AnalysisResult too -- a
        # SignalContext should accept it exactly like any other.
        aggregated = make_analysis_result("AnalysisAggregator", score=0.42, confidence=0.9)
        context = SignalContext(
            symbol="BTCUSDT", timeframe="1h", analysis_results=[aggregated]
        )
        self.assertIs(context.get_result("AnalysisAggregator"), aggregated)

    def test_rejects_empty_symbol(self):
        with self.assertRaises(InvalidSignalContextError):
            SignalContext(symbol="", timeframe="1h")

    def test_rejects_empty_timeframe(self):
        with self.assertRaises(InvalidSignalContextError):
            SignalContext(symbol="BTCUSDT", timeframe="")

    def test_rejects_analysis_results_not_a_list(self):
        with self.assertRaises(InvalidSignalContextError):
            SignalContext(
                symbol="BTCUSDT",
                timeframe="1h",
                analysis_results=make_analysis_result(),  # type: ignore[arg-type]
            )

    def test_rejects_analysis_results_with_wrong_item_type(self):
        with self.assertRaises(InvalidSignalContextError):
            SignalContext(
                symbol="BTCUSDT",
                timeframe="1h",
                analysis_results=["not-an-analysis-result"],  # type: ignore[list-item]
            )

    def test_is_frozen(self):
        context = SignalContext(symbol="BTCUSDT", timeframe="1h")
        with self.assertRaises(Exception):
            context.symbol = "ETHUSDT"  # type: ignore[misc]


# ----------------------------------------------------------------------
# BaseSignalGenerator
# ----------------------------------------------------------------------
class _AlwaysBullishSignalGenerator(BaseSignalGenerator):
    """Minimal concrete generator used to exercise `BaseSignalGenerator`."""

    def generate(self, context: SignalContext) -> SignalResult:
        self.validate_context(context)
        trend = context.get_result("TrendAnalyzer")
        if trend is None:
            raise InsufficientSignalDataError("TrendAnalyzer result is required")
        return self._build_result(
            direction=SignalDirection.BUY,
            strength=abs(trend.score),
            confidence=trend.confidence,
            summary="Bullish (stub generator)",
            metadata={"trend_score": trend.score},
        )


class TestBaseSignalGenerator(unittest.TestCase):
    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            BaseSignalGenerator()  # type: ignore[abstract]

    def test_default_name_is_class_name(self):
        generator = _AlwaysBullishSignalGenerator()
        self.assertEqual(generator.name, "_AlwaysBullishSignalGenerator")

    def test_custom_name_is_used(self):
        generator = _AlwaysBullishSignalGenerator(name="CustomGenerator")
        self.assertEqual(generator.name, "CustomGenerator")

    def test_generate_produces_result_from_context(self):
        generator = _AlwaysBullishSignalGenerator(name="CustomGenerator")
        context = SignalContext(
            symbol="BTCUSDT",
            timeframe="1h",
            analysis_results=[make_analysis_result("TrendAnalyzer", score=0.65, confidence=0.9)],
        )
        result = generator.generate(context)
        self.assertIsInstance(result, SignalResult)
        self.assertEqual(result.direction, SignalDirection.BUY)
        self.assertAlmostEqual(result.strength, 0.65)
        self.assertAlmostEqual(result.confidence, 0.9)
        self.assertEqual(result.metadata, {"trend_score": 0.65})

    def test_generate_raises_insufficient_data_when_result_missing(self):
        generator = _AlwaysBullishSignalGenerator()
        context = SignalContext(symbol="BTCUSDT", timeframe="1h")
        with self.assertRaises(InsufficientSignalDataError):
            generator.generate(context)

    def test_validate_context_rejects_non_context(self):
        generator = _AlwaysBullishSignalGenerator()
        with self.assertRaises(InvalidSignalContextError):
            generator.validate_context("not-a-context")  # type: ignore[arg-type]

    def test_repr_contains_name(self):
        generator = _AlwaysBullishSignalGenerator(name="CustomGenerator")
        self.assertIn("CustomGenerator", repr(generator))


# ----------------------------------------------------------------------
# signals.exceptions hierarchy
# ----------------------------------------------------------------------
class TestExceptionHierarchy(unittest.TestCase):
    def test_all_exceptions_derive_from_signal_error(self):
        for exc_type in (
            SignalValidationError,
            InvalidSignalContextError,
            InsufficientSignalDataError,
            SignalGeneratorConfigurationError,
        ):
            self.assertTrue(issubclass(exc_type, SignalError))

    def test_invalid_context_error_derives_from_validation_error(self):
        self.assertTrue(issubclass(InvalidSignalContextError, SignalValidationError))

    def test_signal_error_derives_from_exception(self):
        self.assertTrue(issubclass(SignalError, Exception))


# ----------------------------------------------------------------------
# signals.utils
# ----------------------------------------------------------------------
class TestUtils(unittest.TestCase):
    def test_validate_non_empty_str_accepts_valid_string(self):
        self.assertEqual(validate_non_empty_str("BTCUSDT", name="symbol"), "BTCUSDT")

    def test_validate_non_empty_str_rejects_blank(self):
        with self.assertRaises(SignalValidationError):
            validate_non_empty_str("   ", name="symbol")

    def test_validate_unit_range_accepts_bounds(self):
        self.assertEqual(validate_unit_range(0.0, name="strength"), 0.0)
        self.assertEqual(validate_unit_range(1.0, name="strength"), 1.0)

    def test_validate_unit_range_rejects_bool(self):
        with self.assertRaises(SignalValidationError):
            validate_unit_range(True, name="strength")

    def test_validate_unit_range_rejects_non_numeric(self):
        with self.assertRaises(SignalValidationError):
            validate_unit_range("high", name="strength")

    def test_validate_unit_range_rejects_infinite(self):
        with self.assertRaises(SignalValidationError):
            validate_unit_range(float("inf"), name="strength")

    def test_validate_unit_range_rejects_out_of_bounds(self):
        with self.assertRaises(SignalValidationError):
            validate_unit_range(1.5, name="confidence")
        with self.assertRaises(SignalValidationError):
            validate_unit_range(-0.5, name="confidence")

    def test_validate_direction_accepts_signal_direction(self):
        self.assertEqual(validate_direction(SignalDirection.HOLD), SignalDirection.HOLD)

    def test_validate_direction_rejects_plain_string(self):
        with self.assertRaises(SignalValidationError):
            validate_direction("buy")

    def test_validate_instance_list_accepts_matching_items(self):
        results = [make_analysis_result()]
        self.assertEqual(
            validate_instance_list(results, AnalysisResult, name="analysis_results"), results
        )

    def test_validate_instance_list_rejects_non_list(self):
        with self.assertRaises(SignalValidationError):
            validate_instance_list(make_analysis_result(), AnalysisResult, name="analysis_results")

    def test_validate_instance_list_rejects_wrong_item_type(self):
        with self.assertRaises(SignalValidationError):
            validate_instance_list(["not-a-result"], AnalysisResult, name="analysis_results")

    def test_merge_metadata_merges_and_prioritizes_later_sources(self):
        merged = merge_metadata({"a": 1}, None, {"a": 2, "b": 3})
        self.assertEqual(merged, {"a": 2, "b": 3})

    def test_merge_metadata_with_no_sources_returns_empty_dict(self):
        self.assertEqual(merge_metadata(), {})


if __name__ == "__main__":
    unittest.main()
