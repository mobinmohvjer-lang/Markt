"""
test_technical_signal_generator.py
-----------------------------------
Purpose:
    Unit tests for the Signal Engine Part 2 concrete module:
    `signals.technical_signal_generator.TechnicalSignalGenerator`.

Mirrors the local-factory / assertion style already used by
`tests/test_signals.py` (Part 1, left untouched by this change) and
`tests/test_aggregator.py` (Analysis Engine Part 4). Most tests build
`AnalysisResult`/`SignalContext` objects directly so the mapping logic
(score -> Bullish/Bearish/Neutral, threshold handling, missing-data
handling) can be exercised precisely. A dedicated integration section
at the bottom wires a real `analysis.aggregator.AnalysisAggregator`
(with injected fake sub-analyzers, mirroring `tests/test_aggregator.py`'s
own `_FakeAnalyzer`) into a real `TechnicalSignalGenerator`, to prove
actual end-to-end reuse of `analysis.aggregator.AnalysisAggregator`'s
output shape, as required.

Uses the standard-library ``unittest`` framework, no external
test-runner dependency, no network access.

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from analysis import AnalysisContext, AnalysisResult, BaseAnalyzer, InsufficientDataError
from analysis.aggregator import AnalysisAggregator
from core.entities.market_state import MarketState
from core.enums import SignalDirection
from signals import (
    InsufficientSignalDataError,
    InvalidSignalContextError,
    SignalContext,
    SignalGeneratorConfigurationError,
    TechnicalSignalGenerator,
)
from signals.technical_signal_generator import DEFAULT_AGGREGATOR_NAME

NOW = datetime.now(timezone.utc)
SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"


# ----------------------------------------------------------------------
# Local test factories
# ----------------------------------------------------------------------
def make_aggregator_result(
    *, score: float = 0.5, confidence: float = 0.8, analyzer_name: str = DEFAULT_AGGREGATOR_NAME,
    metadata: dict | None = None,
) -> AnalysisResult:
    return AnalysisResult(
        analyzer_name=analyzer_name,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        score=score,
        confidence=confidence,
        summary="Overall market view is bullish.",
        metadata=metadata or {},
    )


def make_signal_context(results: list[AnalysisResult] | None = None) -> SignalContext:
    return SignalContext(symbol=SYMBOL, timeframe=TIMEFRAME, analysis_results=results or [])


# ----------------------------------------------------------------------
# Construction / configuration validation
# ----------------------------------------------------------------------
class TestConstruction(unittest.TestCase):
    def test_defaults(self):
        generator = TechnicalSignalGenerator()
        self.assertEqual(generator.aggregator_name, DEFAULT_AGGREGATOR_NAME)
        self.assertEqual(generator.buy_threshold, 0.2)
        self.assertEqual(generator.sell_threshold, -0.2)
        self.assertEqual(generator.name, "TechnicalSignalGenerator")

    def test_is_a_base_signal_generator(self):
        self.assertIsInstance(TechnicalSignalGenerator(), object)
        from signals import BaseSignalGenerator

        self.assertIsInstance(TechnicalSignalGenerator(), BaseSignalGenerator)

    def test_custom_name_and_aggregator_name(self):
        generator = TechnicalSignalGenerator(aggregator_name="MyAggregator", name="Custom")
        self.assertEqual(generator.aggregator_name, "MyAggregator")
        self.assertEqual(generator.name, "Custom")

    def test_rejects_empty_aggregator_name(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            TechnicalSignalGenerator(aggregator_name="   ")

    def test_rejects_non_string_aggregator_name(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            TechnicalSignalGenerator(aggregator_name=123)  # type: ignore[arg-type]

    def test_rejects_non_numeric_thresholds(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            TechnicalSignalGenerator(buy_threshold="high")  # type: ignore[arg-type]
        with self.assertRaises(SignalGeneratorConfigurationError):
            TechnicalSignalGenerator(sell_threshold=None)  # type: ignore[arg-type]

    def test_rejects_boolean_thresholds(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            TechnicalSignalGenerator(buy_threshold=True)  # type: ignore[arg-type]

    def test_rejects_non_finite_thresholds(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            TechnicalSignalGenerator(buy_threshold=float("nan"))
        with self.assertRaises(SignalGeneratorConfigurationError):
            TechnicalSignalGenerator(sell_threshold=float("-inf"))

    def test_rejects_buy_threshold_out_of_range(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            TechnicalSignalGenerator(buy_threshold=1.5)
        with self.assertRaises(SignalGeneratorConfigurationError):
            TechnicalSignalGenerator(buy_threshold=0.0)
        with self.assertRaises(SignalGeneratorConfigurationError):
            TechnicalSignalGenerator(buy_threshold=-0.1)

    def test_rejects_sell_threshold_out_of_range(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            TechnicalSignalGenerator(sell_threshold=-1.5)
        with self.assertRaises(SignalGeneratorConfigurationError):
            TechnicalSignalGenerator(sell_threshold=0.0)
        with self.assertRaises(SignalGeneratorConfigurationError):
            TechnicalSignalGenerator(sell_threshold=0.1)

    def test_accepts_boundary_thresholds(self):
        generator = TechnicalSignalGenerator(buy_threshold=1.0, sell_threshold=-1.0)
        self.assertEqual(generator.buy_threshold, 1.0)
        self.assertEqual(generator.sell_threshold, -1.0)


# ----------------------------------------------------------------------
# generate() -- context validation
# ----------------------------------------------------------------------
class TestGenerateValidation(unittest.TestCase):
    def setUp(self):
        self.generator = TechnicalSignalGenerator()

    def test_rejects_non_signal_context(self):
        with self.assertRaises(InvalidSignalContextError):
            self.generator.generate("not a context")  # type: ignore[arg-type]

    def test_raises_when_no_results_present(self):
        context = make_signal_context([])
        with self.assertRaises(InsufficientSignalDataError):
            self.generator.generate(context)

    def test_raises_when_aggregator_result_absent(self):
        context = make_signal_context(
            [make_aggregator_result(analyzer_name="TrendAnalyzer", score=0.9)]
        )
        with self.assertRaises(InsufficientSignalDataError):
            self.generator.generate(context)

    def test_ignores_non_aggregator_results_alongside_aggregator_result(self):
        context = make_signal_context(
            [
                make_aggregator_result(analyzer_name="TrendAnalyzer", score=-0.9),
                make_aggregator_result(score=0.5, confidence=0.9),
            ]
        )
        result = self.generator.generate(context)
        # Must reflect the aggregator's score (0.5), not TrendAnalyzer's (-0.9).
        self.assertEqual(result.direction, SignalDirection.BUY)


# ----------------------------------------------------------------------
# generate() -- direction mapping (Bullish / Bearish / Neutral)
# ----------------------------------------------------------------------
class TestGenerateDirectionMapping(unittest.TestCase):
    def setUp(self):
        self.generator = TechnicalSignalGenerator()

    def test_bullish_above_buy_threshold(self):
        context = make_signal_context([make_aggregator_result(score=0.6, confidence=0.75)])
        result = self.generator.generate(context)
        self.assertEqual(result.direction, SignalDirection.BUY)
        self.assertAlmostEqual(result.strength, 0.6)
        self.assertAlmostEqual(result.confidence, 0.75)
        self.assertIn("Bullish", result.summary)

    def test_bearish_below_sell_threshold(self):
        context = make_signal_context([make_aggregator_result(score=-0.7, confidence=0.6)])
        result = self.generator.generate(context)
        self.assertEqual(result.direction, SignalDirection.SELL)
        self.assertAlmostEqual(result.strength, 0.7)
        self.assertAlmostEqual(result.confidence, 0.6)
        self.assertIn("Bearish", result.summary)

    def test_neutral_between_thresholds(self):
        context = make_signal_context([make_aggregator_result(score=0.05, confidence=0.5)])
        result = self.generator.generate(context)
        self.assertEqual(result.direction, SignalDirection.HOLD)
        self.assertIn("Neutral", result.summary)

    def test_neutral_at_zero(self):
        context = make_signal_context([make_aggregator_result(score=0.0, confidence=0.2)])
        result = self.generator.generate(context)
        self.assertEqual(result.direction, SignalDirection.HOLD)
        self.assertEqual(result.strength, 0.0)

    def test_score_exactly_at_buy_threshold_is_neutral(self):
        # Thresholds are exclusive, so a score exactly on the boundary
        # does not cross into Bullish/Bearish territory.
        context = make_signal_context([make_aggregator_result(score=0.2, confidence=0.5)])
        result = self.generator.generate(context)
        self.assertEqual(result.direction, SignalDirection.HOLD)

    def test_score_exactly_at_sell_threshold_is_neutral(self):
        context = make_signal_context([make_aggregator_result(score=-0.2, confidence=0.5)])
        result = self.generator.generate(context)
        self.assertEqual(result.direction, SignalDirection.HOLD)

    def test_full_bullish_score_yields_max_strength(self):
        context = make_signal_context([make_aggregator_result(score=1.0, confidence=1.0)])
        result = self.generator.generate(context)
        self.assertEqual(result.direction, SignalDirection.BUY)
        self.assertEqual(result.strength, 1.0)

    def test_full_bearish_score_yields_max_strength(self):
        context = make_signal_context([make_aggregator_result(score=-1.0, confidence=1.0)])
        result = self.generator.generate(context)
        self.assertEqual(result.direction, SignalDirection.SELL)
        self.assertEqual(result.strength, 1.0)

    def test_custom_thresholds_change_classification(self):
        generator = TechnicalSignalGenerator(buy_threshold=0.5, sell_threshold=-0.5)
        context = make_signal_context([make_aggregator_result(score=0.3, confidence=0.5)])
        result = generator.generate(context)
        # 0.3 is Bullish under default thresholds (0.2) but Neutral here.
        self.assertEqual(result.direction, SignalDirection.HOLD)

    def test_custom_aggregator_name_is_used_for_lookup(self):
        generator = TechnicalSignalGenerator(aggregator_name="CustomAggregator")
        context = make_signal_context(
            [make_aggregator_result(analyzer_name="CustomAggregator", score=0.5, confidence=0.9)]
        )
        result = generator.generate(context)
        self.assertEqual(result.direction, SignalDirection.BUY)


# ----------------------------------------------------------------------
# generate() -- populated fields (metadata / summary content)
# ----------------------------------------------------------------------
class TestGenerateOutputShape(unittest.TestCase):
    def setUp(self):
        self.generator = TechnicalSignalGenerator()

    def test_metadata_traces_source(self):
        aggregator_metadata = {"components_missing": [], "conviction": 0.5}
        context = make_signal_context(
            [make_aggregator_result(score=0.4, confidence=0.7, metadata=aggregator_metadata)]
        )
        result = self.generator.generate(context)
        self.assertEqual(result.metadata["source_analyzer"], DEFAULT_AGGREGATOR_NAME)
        self.assertEqual(result.metadata["source_score"], 0.4)
        self.assertEqual(result.metadata["source_confidence"], 0.7)
        self.assertEqual(result.metadata["score_label"], "bullish")
        self.assertEqual(result.metadata["buy_threshold"], 0.2)
        self.assertEqual(result.metadata["sell_threshold"], -0.2)
        self.assertEqual(result.metadata["aggregator_metadata"], aggregator_metadata)

    def test_summary_mentions_symbol_and_timeframe(self):
        context = make_signal_context([make_aggregator_result(score=0.5, confidence=0.6)])
        result = self.generator.generate(context)
        self.assertIn(SYMBOL, result.summary)
        self.assertIn(TIMEFRAME, result.summary)

    def test_result_is_a_valid_signal_result_with_five_fields(self):
        context = make_signal_context([make_aggregator_result(score=0.5, confidence=0.6)])
        result = self.generator.generate(context)
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        self.assertEqual(
            field_names, {"direction", "strength", "confidence", "summary", "metadata"}
        )

    def test_confidence_passes_through_unchanged(self):
        context = make_signal_context([make_aggregator_result(score=0.9, confidence=0.33)])
        result = self.generator.generate(context)
        self.assertEqual(result.confidence, 0.33)


# ----------------------------------------------------------------------
# Real AnalysisAggregator integration
# ----------------------------------------------------------------------
class _FakeAnalyzer(BaseAnalyzer):
    """Minimal fake sub-analyzer, mirroring tests/test_aggregator.py's own."""

    def __init__(self, *, score: float = 0.0, confidence: float = 1.0, name: str | None = None):
        super().__init__(name=name)
        self.score = score
        self.confidence = confidence

    def analyze(self, context: AnalysisContext) -> AnalysisResult:
        self.validate_context(context)
        return self._build_result(
            context,
            score=self.score,
            confidence=self.confidence,
            summary="fake sub-analyzer result",
        )


class TestRealAggregatorIntegration(unittest.TestCase):
    def test_generates_bullish_signal_from_real_aggregator_output(self):
        aggregator = AnalysisAggregator(
            trend_analyzer=_FakeAnalyzer(score=0.8, confidence=0.9, name="trend"),
            momentum_analyzer=_FakeAnalyzer(score=0.7, confidence=0.9, name="momentum"),
            volatility_analyzer=_FakeAnalyzer(score=0.0, confidence=0.5, name="volatility"),
            volume_analyzer=_FakeAnalyzer(score=0.6, confidence=0.8, name="volume"),
            market_structure_analyzer=_FakeAnalyzer(score=0.5, confidence=0.8, name="structure"),
        )
        analysis_context = AnalysisContext(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            market_state=MarketState(symbol=SYMBOL, timeframe=TIMEFRAME, timestamp=NOW),
            indicators=[],
        )
        aggregate_result = aggregator.analyze(analysis_context)
        self.assertEqual(aggregate_result.analyzer_name, DEFAULT_AGGREGATOR_NAME)

        signal_context = SignalContext(
            symbol=SYMBOL, timeframe=TIMEFRAME, analysis_results=[aggregate_result]
        )
        generator = TechnicalSignalGenerator()
        signal = generator.generate(signal_context)

        self.assertEqual(signal.direction, SignalDirection.BUY)
        self.assertGreater(signal.strength, 0.0)
        self.assertEqual(signal.metadata["source_analyzer"], DEFAULT_AGGREGATOR_NAME)
        self.assertEqual(signal.metadata["aggregator_metadata"], aggregate_result.metadata)

    def test_raises_when_all_sub_analyzers_unavailable(self):
        aggregator = AnalysisAggregator(
            trend_analyzer=_FakeUnavailableAnalyzer(name="trend"),
            momentum_analyzer=_FakeUnavailableAnalyzer(name="momentum"),
            volatility_analyzer=_FakeUnavailableAnalyzer(name="volatility"),
            volume_analyzer=_FakeUnavailableAnalyzer(name="volume"),
            market_structure_analyzer=_FakeUnavailableAnalyzer(name="structure"),
        )
        analysis_context = AnalysisContext(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            market_state=MarketState(symbol=SYMBOL, timeframe=TIMEFRAME, timestamp=NOW),
            indicators=[],
        )
        with self.assertRaises(InsufficientDataError):
            aggregator.analyze(analysis_context)


class _FakeUnavailableAnalyzer(BaseAnalyzer):
    def analyze(self, context: AnalysisContext) -> AnalysisResult:
        self.validate_context(context)
        raise InsufficientDataError(f"{self.name} has no data")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
