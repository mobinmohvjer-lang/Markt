"""
test_aggregator.py
--------------------
Purpose:
    Unit tests for the Analysis Engine Part 4 concrete module:
    `analysis.aggregator.AnalysisAggregator`.

Mirrors the local-factory / assertion style already used by
`tests/test_analysis_technical.py` (Part 2), `tests/test_volatility_analyzer.py`
(Part 3A), `tests/test_volume_analyzer.py` (Part 3B), and
`tests/test_market_structure_analyzer.py` (Part 3C), all left untouched
by this change. Uses the standard-library ``unittest`` framework, no
external test-runner dependency, no network access.

Most tests inject fake `BaseAnalyzer` sub-analyzers (constructor-
injected, matching the project's dependency-injection convention) so
the aggregation/merging logic itself can be exercised precisely,
without needing to hand-construct valid indicator data for all five
real analyzers on every test. A dedicated integration section at the
bottom builds a real `AnalysisAggregator()` (default, real
sub-analyzers) against real indicator/candle data to prove the module
actually reuses `analysis.technical` end-to-end, as required.

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from analysis import (
    AnalysisContext,
    AnalysisResult,
    AnalyzerConfigurationError,
    BaseAnalyzer,
    InsufficientDataError,
    InvalidAnalysisContextError,
)
from analysis.aggregator import AnalysisAggregator
from analysis.technical import (
    MarketStructureAnalyzer,
    MomentumAnalyzer,
    TrendAnalyzer,
    VolatilityAnalyzer,
    VolumeAnalyzer,
)
from core.entities.candle import Candle
from core.entities.indicator_result import IndicatorResult
from core.entities.market_state import MarketState

NOW = datetime.now(timezone.utc)
SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"


# ----------------------------------------------------------------------
# Local test factories
# ----------------------------------------------------------------------
def make_market_state(candle: Candle | None = None) -> MarketState:
    return MarketState(symbol=SYMBOL, timeframe=TIMEFRAME, timestamp=NOW, latest_candle=candle)


def make_context(indicators: list[IndicatorResult] | None = None) -> AnalysisContext:
    return AnalysisContext(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        market_state=make_market_state(),
        indicators=indicators or [],
    )


def make_indicator(name: str, values: dict) -> IndicatorResult:
    return IndicatorResult(
        indicator_name=name, symbol=SYMBOL, timeframe=TIMEFRAME, timestamp=NOW, values=values
    )


class _FakeAnalyzer(BaseAnalyzer):
    """
    Test double for a sub-analyzer: returns a fixed `AnalysisResult`
    (score/confidence/summary/metadata) or raises `InsufficientDataError`
    if configured to be "unavailable". Lets aggregation logic be tested
    independently of any real indicator data.
    """

    def __init__(
        self,
        *,
        score: float = 0.0,
        confidence: float = 1.0,
        summary: str = "fake result",
        metadata: dict | None = None,
        unavailable: bool = False,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        self.score = score
        self.confidence = confidence
        self.summary = summary
        self.metadata = metadata or {}
        self.unavailable = unavailable

    def analyze(self, context: AnalysisContext) -> AnalysisResult:
        self.validate_context(context)
        if self.unavailable:
            raise InsufficientDataError(f"{self.name} has no data")
        return self._build_result(
            context,
            score=self.score,
            confidence=self.confidence,
            summary=self.summary,
            metadata=self.metadata,
        )


def make_aggregator(
    *,
    trend_score=0.5,
    momentum_score=0.5,
    volatility_score=0.0,
    volume_score=0.5,
    market_structure_score=0.5,
    trend_confidence=1.0,
    momentum_confidence=1.0,
    volatility_confidence=1.0,
    volume_confidence=1.0,
    market_structure_confidence=1.0,
    trend_unavailable=False,
    momentum_unavailable=False,
    volatility_unavailable=False,
    volume_unavailable=False,
    market_structure_unavailable=False,
    weights=None,
    name=None,
) -> AnalysisAggregator:
    return AnalysisAggregator(
        trend_analyzer=_FakeAnalyzer(
            score=trend_score,
            confidence=trend_confidence,
            unavailable=trend_unavailable,
            name="TrendAnalyzer",
        ),
        momentum_analyzer=_FakeAnalyzer(
            score=momentum_score,
            confidence=momentum_confidence,
            unavailable=momentum_unavailable,
            name="MomentumAnalyzer",
        ),
        volatility_analyzer=_FakeAnalyzer(
            score=volatility_score,
            confidence=volatility_confidence,
            unavailable=volatility_unavailable,
            name="VolatilityAnalyzer",
        ),
        volume_analyzer=_FakeAnalyzer(
            score=volume_score,
            confidence=volume_confidence,
            unavailable=volume_unavailable,
            name="VolumeAnalyzer",
        ),
        market_structure_analyzer=_FakeAnalyzer(
            score=market_structure_score,
            confidence=market_structure_confidence,
            unavailable=market_structure_unavailable,
            name="MarketStructureAnalyzer",
        ),
        weights=weights,
        name=name,
    )


# ----------------------------------------------------------------------
# Construction
# ----------------------------------------------------------------------
class TestConstruction(unittest.TestCase):
    def test_default_construction_uses_real_analyzers(self):
        aggregator = AnalysisAggregator()
        self.assertIsInstance(aggregator._analyzers["trend"], TrendAnalyzer)
        self.assertIsInstance(aggregator._analyzers["momentum"], MomentumAnalyzer)
        self.assertIsInstance(aggregator._analyzers["volatility"], VolatilityAnalyzer)
        self.assertIsInstance(aggregator._analyzers["volume"], VolumeAnalyzer)
        self.assertIsInstance(aggregator._analyzers["market_structure"], MarketStructureAnalyzer)

    def test_default_name_is_class_name(self):
        self.assertEqual(AnalysisAggregator().name, "AnalysisAggregator")

    def test_custom_name_is_used(self):
        self.assertEqual(AnalysisAggregator(name="Combined").name, "Combined")

    def test_default_weights_are_equal(self):
        aggregator = AnalysisAggregator()
        self.assertEqual(
            aggregator.weights,
            {
                "trend": 1.0,
                "momentum": 1.0,
                "volatility": 1.0,
                "volume": 1.0,
                "market_structure": 1.0,
            },
        )

    def test_custom_weights_override_defaults(self):
        aggregator = make_aggregator(weights={"trend": 2.0})
        self.assertEqual(aggregator.weights["trend"], 2.0)
        self.assertEqual(aggregator.weights["momentum"], 1.0)

    def test_rejects_unknown_weight_key(self):
        with self.assertRaises(AnalyzerConfigurationError):
            make_aggregator(weights={"not_a_real_analyzer": 1.0})

    def test_rejects_negative_weight(self):
        with self.assertRaises(AnalyzerConfigurationError):
            make_aggregator(weights={"trend": -1.0})

    def test_rejects_non_numeric_weight(self):
        with self.assertRaises(AnalyzerConfigurationError):
            make_aggregator(weights={"trend": "high"})

    def test_rejects_non_finite_weight(self):
        with self.assertRaises(AnalyzerConfigurationError):
            make_aggregator(weights={"trend": float("nan")})


# ----------------------------------------------------------------------
# analyze() -- context validation
# ----------------------------------------------------------------------
class TestAnalyzeValidation(unittest.TestCase):
    def test_rejects_non_context(self):
        aggregator = make_aggregator()
        with self.assertRaises(InvalidAnalysisContextError):
            aggregator.analyze("not-a-context")  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# analyze() -- full availability
# ----------------------------------------------------------------------
class TestAnalyzeAllAvailable(unittest.TestCase):
    def test_returns_analysis_result(self):
        aggregator = make_aggregator()
        result = aggregator.analyze(make_context())
        self.assertIsInstance(result, AnalysisResult)
        self.assertEqual(result.analyzer_name, "AnalysisAggregator")
        self.assertEqual(result.symbol, SYMBOL)
        self.assertEqual(result.timeframe, TIMEFRAME)

    def test_bullish_directional_inputs_produce_bullish_overall_score(self):
        aggregator = make_aggregator(
            trend_score=0.8, momentum_score=0.8, volume_score=0.8, market_structure_score=0.8
        )
        result = aggregator.analyze(make_context())
        self.assertGreater(result.score, 0.5)

    def test_bearish_directional_inputs_produce_bearish_overall_score(self):
        aggregator = make_aggregator(
            trend_score=-0.8, momentum_score=-0.8, volume_score=-0.8, market_structure_score=-0.8
        )
        result = aggregator.analyze(make_context())
        self.assertLess(result.score, -0.5)

    def test_volatility_score_never_shifts_overall_score_direction(self):
        # Every directional analyzer is exactly neutral (0.0); a strongly
        # non-neutral volatility regime score must not pull overall_score
        # away from 0.0, since VolatilityAnalyzer is direction-free.
        aggregator = make_aggregator(
            trend_score=0.0,
            momentum_score=0.0,
            volume_score=0.0,
            market_structure_score=0.0,
            volatility_score=0.9,
        )
        result = aggregator.analyze(make_context())
        self.assertEqual(result.score, 0.0)

    def test_score_within_bounds(self):
        aggregator = make_aggregator(
            trend_score=1.0, momentum_score=1.0, volume_score=1.0, market_structure_score=1.0
        )
        result = aggregator.analyze(make_context())
        self.assertLessEqual(result.score, 1.0)
        self.assertGreaterEqual(result.score, -1.0)

    def test_confidence_within_bounds(self):
        aggregator = make_aggregator()
        result = aggregator.analyze(make_context())
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_full_availability_yields_full_completeness(self):
        aggregator = make_aggregator()
        result = aggregator.analyze(make_context())
        self.assertEqual(result.metadata["completeness_ratio"], 1.0)
        self.assertEqual(
            result.metadata["directional_components_used"],
            ["market_structure", "momentum", "trend", "volume"],
        )
        self.assertEqual(result.metadata["components_missing"], [])

    def test_low_confidence_sub_analyzer_contributes_less(self):
        high_conf = make_aggregator(
            trend_score=1.0,
            momentum_score=0.0,
            volume_score=0.0,
            market_structure_score=0.0,
            trend_confidence=1.0,
        )
        low_conf = make_aggregator(
            trend_score=1.0,
            momentum_score=0.0,
            volume_score=0.0,
            market_structure_score=0.0,
            trend_confidence=0.1,
        )
        result_high = high_conf.analyze(make_context())
        result_low = low_conf.analyze(make_context())
        self.assertGreater(result_high.score, result_low.score)


# ----------------------------------------------------------------------
# analyze() -- partial / missing availability
# ----------------------------------------------------------------------
class TestAnalyzePartialAvailability(unittest.TestCase):
    def test_one_directional_analyzer_missing_still_produces_result(self):
        aggregator = make_aggregator(momentum_unavailable=True)
        result = aggregator.analyze(make_context())
        self.assertIsInstance(result, AnalysisResult)
        self.assertIn("momentum", result.metadata["components_missing"])
        self.assertNotIn("momentum", result.metadata["directional_components_used"])

    def test_volatility_missing_does_not_block_result(self):
        aggregator = make_aggregator(volatility_unavailable=True)
        result = aggregator.analyze(make_context())
        self.assertIsInstance(result, AnalysisResult)
        self.assertIn("volatility", result.metadata["components_missing"])

    def test_all_directional_missing_but_volatility_present_raises(self):
        aggregator = make_aggregator(
            trend_unavailable=True,
            momentum_unavailable=True,
            volume_unavailable=True,
            market_structure_unavailable=True,
            volatility_unavailable=False,
        )
        with self.assertRaises(InsufficientDataError):
            aggregator.analyze(make_context())

    def test_all_five_missing_raises(self):
        aggregator = make_aggregator(
            trend_unavailable=True,
            momentum_unavailable=True,
            volume_unavailable=True,
            market_structure_unavailable=True,
            volatility_unavailable=True,
        )
        with self.assertRaises(InsufficientDataError):
            aggregator.analyze(make_context())

    def test_single_directional_analyzer_available_produces_result(self):
        aggregator = make_aggregator(
            trend_score=0.6,
            momentum_unavailable=True,
            volume_unavailable=True,
            market_structure_unavailable=True,
            volatility_unavailable=True,
        )
        result = aggregator.analyze(make_context())
        self.assertEqual(result.score, 0.6)
        self.assertEqual(result.metadata["directional_components_used"], ["trend"])

    def test_missing_component_reason_is_recorded(self):
        aggregator = make_aggregator(momentum_unavailable=True)
        result = aggregator.analyze(make_context())
        component = result.metadata["components"]["momentum"]
        self.assertFalse(component["available"])
        self.assertIn("reason", component)

    def test_partial_availability_lowers_confidence_vs_full(self):
        full = make_aggregator()
        partial = make_aggregator(momentum_unavailable=True, volume_unavailable=True)
        result_full = full.analyze(make_context())
        result_partial = partial.analyze(make_context())
        self.assertLess(result_partial.confidence, result_full.confidence)


# ----------------------------------------------------------------------
# Metadata merging
# ----------------------------------------------------------------------
class TestMetadataMerging(unittest.TestCase):
    def test_metadata_includes_all_five_components(self):
        aggregator = make_aggregator()
        result = aggregator.analyze(make_context())
        self.assertEqual(
            set(result.metadata["components"]),
            {"trend", "momentum", "volatility", "volume", "market_structure"},
        )

    def test_available_component_carries_score_confidence_summary_metadata(self):
        aggregator = make_aggregator(trend_score=0.42)
        result = aggregator.analyze(make_context())
        trend_component = result.metadata["components"]["trend"]
        self.assertTrue(trend_component["available"])
        self.assertEqual(trend_component["score"], 0.42)
        self.assertEqual(trend_component["analyzer_name"], "TrendAnalyzer")
        self.assertIn("summary", trend_component)
        self.assertIn("metadata", trend_component)

    def test_volatility_component_flagged_as_non_directional(self):
        aggregator = make_aggregator()
        result = aggregator.analyze(make_context())
        self.assertFalse(
            result.metadata["components"]["volatility"]["contributes_to_directional_score"]
        )

    def test_directional_component_flagged_as_directional(self):
        aggregator = make_aggregator()
        result = aggregator.analyze(make_context())
        self.assertTrue(
            result.metadata["components"]["trend"]["contributes_to_directional_score"]
        )

    def test_top_level_volatility_metadata_matches_component(self):
        aggregator = make_aggregator()
        result = aggregator.analyze(make_context())
        self.assertEqual(
            result.metadata["volatility"], result.metadata["components"]["volatility"]
        )

    def test_weights_reflected_in_metadata(self):
        aggregator = make_aggregator(weights={"trend": 3.0})
        result = aggregator.analyze(make_context())
        self.assertEqual(result.metadata["weights"]["trend"], 3.0)

    def test_summary_mentions_missing_components(self):
        aggregator = make_aggregator(momentum_unavailable=True)
        result = aggregator.analyze(make_context())
        self.assertIn("missing", result.summary)
        self.assertIn("momentum", result.summary)

    def test_summary_omits_missing_clause_when_all_available(self):
        aggregator = make_aggregator()
        result = aggregator.analyze(make_context())
        self.assertNotIn("missing", result.summary)


# ----------------------------------------------------------------------
# Integration -- real sub-analyzers, real indicator/candle data
# ----------------------------------------------------------------------
class TestRealAnalyzerIntegration(unittest.TestCase):
    """
    Confirms `AnalysisAggregator` actually reuses the real, existing
    `analysis.technical` analyzers end-to-end (not just the fakes used
    above), without modifying any of them.
    """

    def _make_candle(self, *, close: float = 105.0) -> Candle:
        return Candle(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            open_time=NOW,
            close_time=NOW,
            open=Decimal("100"),
            high=Decimal(str(close + 1)),
            low=Decimal("99"),
            close=Decimal(str(close)),
            volume=Decimal("1500"),
        )

    def _make_context(self) -> AnalysisContext:
        candle = self._make_candle()
        market_state = MarketState(
            symbol=SYMBOL, timeframe=TIMEFRAME, timestamp=NOW, latest_candle=candle
        )
        indicators = [
            # Trend
            make_indicator("SMA_20", {"value": 110.0}),
            make_indicator("SMA_50", {"value": 100.0}),
            make_indicator("ADX_14", {"adx": 30.0, "plus_di": 25.0, "minus_di": 10.0}),
            # Momentum
            make_indicator("RSI_14", {"value": 65.0}),
            # Volatility
            make_indicator("ATR_14", {"value": 2.0}),
            make_indicator(
                "BollingerBands_20", {"middle": 105.0, "upper": 115.0, "lower": 95.0}
            ),
            # Volume
            make_indicator("OBV_1", {"value": 5000.0}),
            make_indicator("VWAP_14", {"value": 103.0}),
            make_indicator("VolumeSMA_20", {"value": 1000.0}),
            # Market structure
            make_indicator(
                "SwingPoints_1",
                {
                    "swing_high_1": 112.0,
                    "swing_high_2": 108.0,
                    "swing_low_1": 101.0,
                    "swing_low_2": 98.0,
                },
            ),
        ]
        return AnalysisContext(
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            market_state=market_state,
            indicators=indicators,
        )

    def test_real_aggregator_produces_result_from_real_sub_analyzers(self):
        aggregator = AnalysisAggregator()
        result = aggregator.analyze(self._make_context())
        self.assertIsInstance(result, AnalysisResult)
        self.assertEqual(result.analyzer_name, "AnalysisAggregator")
        self.assertGreaterEqual(result.score, -1.0)
        self.assertLessEqual(result.score, 1.0)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)
        # Bullish-leaning input data (fast SMA above slow, RSI 65, OBV
        # rising, higher-high/higher-low swing structure) should produce
        # a net-positive overall score.
        self.assertGreater(result.score, 0.0)

    def test_real_sub_results_are_real_analysis_results(self):
        aggregator = AnalysisAggregator()
        result = aggregator.analyze(self._make_context())
        trend_component = result.metadata["components"]["trend"]
        self.assertEqual(trend_component["analyzer_name"], "TrendAnalyzer")
        self.assertTrue(trend_component["available"])

    def test_real_aggregator_handles_missing_market_structure_input(self):
        # Drop the SwingPoints indicator -- MarketStructureAnalyzer will
        # raise InsufficientDataError internally; the aggregator must
        # still succeed using the remaining four.
        candle = self._make_candle()
        market_state = MarketState(
            symbol=SYMBOL, timeframe=TIMEFRAME, timestamp=NOW, latest_candle=candle
        )
        indicators = [
            make_indicator("SMA_20", {"value": 110.0}),
            make_indicator("SMA_50", {"value": 100.0}),
            make_indicator("RSI_14", {"value": 65.0}),
            make_indicator("ATR_14", {"value": 2.0}),
            make_indicator("OBV_1", {"value": 5000.0}),
        ]
        context = AnalysisContext(
            symbol=SYMBOL, timeframe=TIMEFRAME, market_state=market_state, indicators=indicators
        )
        aggregator = AnalysisAggregator()
        result = aggregator.analyze(context)
        self.assertIsInstance(result, AnalysisResult)
        self.assertIn("market_structure", result.metadata["components_missing"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
