"""
test_analysis_technical.py
---------------------------
Purpose:
    Unit tests for the Analysis Engine Part 2 concrete analyzers:
    `analysis.technical.TrendAnalyzer` and
    `analysis.technical.MomentumAnalyzer`, plus the shared
    `analysis.technical.utils` normalization helpers they build on.

Uses the standard-library ``unittest`` framework, matching the rest of
the test suite (no external test-runner dependency, no network access).

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from analysis import AnalysisContext, AnalysisResult, InsufficientDataError, InvalidAnalysisContextError
from analysis.technical import MomentumAnalyzer, TrendAnalyzer
from analysis.technical.utils import (
    clip,
    completeness_ratio,
    mean_abs,
    normalize_center,
    normalize_diff,
    normalize_scaled,
    score_label,
    weighted_average,
)
from core.entities.indicator_result import IndicatorResult
from core.entities.market_state import MarketState

NOW = datetime.now(timezone.utc)
SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"


# ----------------------------------------------------------------------
# Local test factories (mirrors the local-factory style used by
# tests/test_analysis.py -- no changes made to tests/helpers.py, which
# is scoped to the Data Engine tests).
# ----------------------------------------------------------------------
def make_market_state() -> MarketState:
    return MarketState(symbol=SYMBOL, timeframe=TIMEFRAME, timestamp=NOW)


def make_indicator(name: str, values: dict, **overrides) -> IndicatorResult:
    base = dict(
        indicator_name=name,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        timestamp=NOW,
        values=values,
    )
    base.update(overrides)
    return IndicatorResult(**base)


def make_context(indicators: list[IndicatorResult]) -> AnalysisContext:
    return AnalysisContext(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        market_state=make_market_state(),
        indicators=indicators,
    )


def sma(value: float, period: int = 20) -> IndicatorResult:
    return make_indicator(f"SMA_{period}", {"value": value})


def ema(value: float, period: int = 12) -> IndicatorResult:
    return make_indicator(f"EMA_{period}", {"value": value})


def macd(macd_value: float, signal_value: float, histogram: float | None = None) -> IndicatorResult:
    if histogram is None:
        histogram = macd_value - signal_value
    return make_indicator(
        "MACD_12_26_9", {"macd": macd_value, "signal": signal_value, "histogram": histogram}
    )


def adx(value: float) -> IndicatorResult:
    return make_indicator("ADX_14", {"adx": value, "plus_di": 20.0, "minus_di": 10.0})


def rsi(value: float) -> IndicatorResult:
    return make_indicator("RSI_14", {"value": value})


def roc(value: float) -> IndicatorResult:
    return make_indicator("ROC_12", {"value": value})


def stochastic(k: float, d: float) -> IndicatorResult:
    return make_indicator("Stochastic_14_3", {"k": k, "d": d})


# ----------------------------------------------------------------------
# analysis.technical.utils
# ----------------------------------------------------------------------
class TestUtils(unittest.TestCase):
    def test_clip_within_range(self):
        self.assertEqual(clip(0.3), 0.3)

    def test_clip_above_range(self):
        self.assertEqual(clip(5.0), 1.0)

    def test_clip_below_range(self):
        self.assertEqual(clip(-5.0), -1.0)

    def test_clip_custom_bounds(self):
        self.assertEqual(clip(150, lo=0.0, hi=100.0), 100.0)

    def test_clip_invalid_bounds_raises(self):
        with self.assertRaises(ValueError):
            clip(0.5, lo=1.0, hi=0.0)

    def test_normalize_diff_bullish(self):
        self.assertAlmostEqual(normalize_diff(110, 100), 0.10)

    def test_normalize_diff_bearish(self):
        self.assertAlmostEqual(normalize_diff(90, 100), -0.10)

    def test_normalize_diff_clips_large_difference(self):
        self.assertEqual(normalize_diff(1000, 100), 1.0)
        self.assertEqual(normalize_diff(-1000, 100), -1.0)

    def test_normalize_diff_zero_slow_positive_diff(self):
        self.assertEqual(normalize_diff(5, 0), 1.0)

    def test_normalize_diff_zero_slow_negative_diff(self):
        self.assertEqual(normalize_diff(-5, 0), -1.0)

    def test_normalize_diff_zero_slow_zero_diff(self):
        self.assertEqual(normalize_diff(0, 0), 0.0)

    def test_normalize_center_midpoint_is_neutral(self):
        self.assertEqual(normalize_center(50), 0.0)

    def test_normalize_center_max_is_bullish(self):
        self.assertEqual(normalize_center(100), 1.0)

    def test_normalize_center_min_is_bearish(self):
        self.assertEqual(normalize_center(0), -1.0)

    def test_normalize_center_zero_scale_raises(self):
        with self.assertRaises(ValueError):
            normalize_center(50, center=50, scale=0)

    def test_normalize_scaled_basic(self):
        self.assertAlmostEqual(normalize_scaled(5.0, 10.0), 0.5)

    def test_normalize_scaled_negative(self):
        self.assertAlmostEqual(normalize_scaled(-5.0, 10.0), -0.5)

    def test_normalize_scaled_clips(self):
        self.assertEqual(normalize_scaled(100.0, 10.0), 1.0)

    def test_normalize_scaled_zero_scale_raises(self):
        with self.assertRaises(ValueError):
            normalize_scaled(1.0, 0.0)

    def test_weighted_average_basic(self):
        self.assertAlmostEqual(weighted_average([(1.0, 1.0), (0.0, 1.0)]), 0.5)

    def test_weighted_average_empty(self):
        self.assertEqual(weighted_average([]), 0.0)

    def test_weighted_average_zero_total_weight(self):
        self.assertEqual(weighted_average([(1.0, 0.0), (-1.0, 0.0)]), 0.0)

    def test_mean_abs_basic(self):
        self.assertAlmostEqual(mean_abs([0.5, -0.5, 0.0]), 1 / 3)

    def test_mean_abs_empty(self):
        self.assertEqual(mean_abs([]), 0.0)

    def test_completeness_ratio_basic(self):
        self.assertAlmostEqual(completeness_ratio(2, 4), 0.5)

    def test_completeness_ratio_zero_expected(self):
        self.assertEqual(completeness_ratio(0, 0), 0.0)

    def test_score_label_thresholds(self):
        self.assertEqual(score_label(0.9), "strong bullish")
        self.assertEqual(score_label(0.3), "mild bullish")
        self.assertEqual(score_label(0.0), "neutral")
        self.assertEqual(score_label(-0.3), "mild bearish")
        self.assertEqual(score_label(-0.9), "strong bearish")


# ----------------------------------------------------------------------
# TrendAnalyzer
# ----------------------------------------------------------------------
class TestTrendAnalyzerBasics(unittest.TestCase):
    def setUp(self):
        self.analyzer = TrendAnalyzer()

    def test_is_base_analyzer_subclass(self):
        from analysis.base import BaseAnalyzer

        self.assertIsInstance(self.analyzer, BaseAnalyzer)

    def test_default_name_is_class_name(self):
        self.assertEqual(self.analyzer.name, "TrendAnalyzer")

    def test_custom_name(self):
        analyzer = TrendAnalyzer(name="MyTrend")
        self.assertEqual(analyzer.name, "MyTrend")

    def test_rejects_non_context(self):
        with self.assertRaises(InvalidAnalysisContextError):
            self.analyzer.analyze("not a context")

    def test_raises_when_no_directional_indicators_present(self):
        context = make_context([adx(30.0)])  # ADX alone is not directional
        with self.assertRaises(InsufficientDataError):
            self.analyzer.analyze(context)

    def test_raises_on_completely_empty_context(self):
        context = make_context([])
        with self.assertRaises(InsufficientDataError):
            self.analyzer.analyze(context)

    def test_returns_analysis_result(self):
        context = make_context([sma(110, 20), sma(100, 50)])
        result = self.analyzer.analyze(context)
        self.assertIsInstance(result, AnalysisResult)
        self.assertEqual(result.analyzer_name, "TrendAnalyzer")
        self.assertEqual(result.symbol, SYMBOL)
        self.assertEqual(result.timeframe, TIMEFRAME)


class TestTrendAnalyzerScoring(unittest.TestCase):
    def setUp(self):
        self.analyzer = TrendAnalyzer()

    def test_bullish_sma_only(self):
        context = make_context([sma(110, 20), sma(100, 50)])
        result = self.analyzer.analyze(context)
        self.assertGreater(result.score, 0.0)
        self.assertEqual(result.metadata["components_used"], ["sma"])

    def test_bearish_sma_only(self):
        context = make_context([sma(90, 20), sma(100, 50)])
        result = self.analyzer.analyze(context)
        self.assertLess(result.score, 0.0)

    def test_neutral_when_sma_equal(self):
        context = make_context([sma(100, 20), sma(100, 50)])
        result = self.analyzer.analyze(context)
        self.assertEqual(result.score, 0.0)

    def test_all_bullish_components_strongly_bullish(self):
        context = make_context(
            [
                sma(120, 20),
                sma(100, 50),
                ema(120, 12),
                ema(100, 26),
                macd(5.0, 1.0),
                adx(40.0),
            ]
        )
        result = self.analyzer.analyze(context)
        # sma: (120-100)/100=0.2, ema: (120-100)/100=0.2, macd: (5-1)/1=4 -> clipped to 1.0
        # average = (0.2 + 0.2 + 1.0) / 3 ~= 0.467
        self.assertGreater(result.score, 0.4)
        self.assertEqual(sorted(result.metadata["components_used"]), ["ema", "macd", "sma"])
        self.assertGreater(result.confidence, 0.0)

    def test_mixed_signals_average_toward_neutral(self):
        context = make_context(
            [
                sma(110, 20),
                sma(100, 50),  # bullish
                ema(90, 12),
                ema(100, 26),  # bearish
            ]
        )
        result = self.analyzer.analyze(context)
        # Roughly offsetting: score should be small in magnitude.
        self.assertLess(abs(result.score), 0.2)

    def test_score_never_exceeds_bounds(self):
        context = make_context(
            [
                sma(1_000_000, 20),
                sma(1, 50),
                ema(1_000_000, 12),
                ema(1, 26),
                macd(1_000_000, 1),
            ]
        )
        result = self.analyzer.analyze(context)
        self.assertLessEqual(result.score, 1.0)
        self.assertGreaterEqual(result.score, -1.0)

    def test_missing_sma_slow_excludes_sma_component(self):
        context = make_context([sma(110, 20)])
        with self.assertRaises(InsufficientDataError):
            self.analyzer.analyze(context)

    def test_partial_sma_with_macd_present_only_uses_macd(self):
        context = make_context([sma(110, 20), macd(2.0, 1.0)])
        result = self.analyzer.analyze(context)
        self.assertEqual(result.metadata["components_used"], ["macd"])
        self.assertFalse(result.metadata["sma"]["used"])
        self.assertTrue(result.metadata["macd"]["used"])


class TestTrendAnalyzerConfidence(unittest.TestCase):
    def setUp(self):
        self.analyzer = TrendAnalyzer()

    def test_confidence_within_bounds(self):
        context = make_context([sma(110, 20), sma(100, 50), adx(60.0)])
        result = self.analyzer.analyze(context)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_more_components_and_stronger_adx_increase_confidence(self):
        weak_context = make_context([sma(101, 20), sma(100, 50), adx(10.0)])
        strong_context = make_context(
            [
                sma(150, 20),
                sma(100, 50),
                ema(150, 12),
                ema(100, 26),
                macd(10.0, 1.0),
                adx(60.0),
            ]
        )
        weak_result = self.analyzer.analyze(weak_context)
        strong_result = self.analyzer.analyze(strong_context)
        self.assertGreater(strong_result.confidence, weak_result.confidence)

    def test_missing_adx_defaults_to_neutral_strength_factor(self):
        context = make_context([sma(150, 20), sma(100, 50)])
        result = self.analyzer.analyze(context)
        self.assertEqual(result.metadata["adx"]["used"], False)
        self.assertAlmostEqual(result.metadata["strength_modifier"], 0.75)

    def test_strong_adx_increases_strength_modifier(self):
        context = make_context([sma(150, 20), sma(100, 50), adx(100.0)])
        result = self.analyzer.analyze(context)
        self.assertAlmostEqual(result.metadata["strength_modifier"], 1.0)

    def test_weak_adx_lowers_strength_modifier_below_neutral_default(self):
        context = make_context([sma(150, 20), sma(100, 50), adx(0.0)])
        result = self.analyzer.analyze(context)
        self.assertAlmostEqual(result.metadata["strength_modifier"], 0.5)


class TestTrendAnalyzerMetadata(unittest.TestCase):
    def test_metadata_explains_every_contributing_indicator(self):
        analyzer = TrendAnalyzer()
        context = make_context(
            [
                sma(110, 20),
                sma(100, 50),
                ema(105, 12),
                ema(100, 26),
                macd(3.0, 1.0),
                adx(30.0),
            ]
        )
        result = analyzer.analyze(context)
        for key in ("sma", "ema", "macd", "adx"):
            self.assertIn(key, result.metadata)
            self.assertIn("explanation", result.metadata[key])
        self.assertIn("score_scale", result.metadata)
        self.assertIn("confidence_scale", result.metadata)
        self.assertIn("component_scores", result.metadata)

    def test_summary_mentions_score_and_confidence(self):
        analyzer = TrendAnalyzer()
        context = make_context([sma(110, 20), sma(100, 50)])
        result = analyzer.analyze(context)
        self.assertIn("score=", result.summary)
        self.assertIn("confidence=", result.summary)


class TestTrendAnalyzerCustomNames(unittest.TestCase):
    def test_custom_indicator_names_are_used_for_lookup(self):
        analyzer = TrendAnalyzer(
            sma_fast_name="SMA_9",
            sma_slow_name="SMA_21",
            ema_fast_name="EMA_5",
            ema_slow_name="EMA_15",
            macd_name="MyMACD",
            adx_name="MyADX",
        )
        context = make_context(
            [
                make_indicator("SMA_9", {"value": 110}),
                make_indicator("SMA_21", {"value": 100}),
                make_indicator("MyADX", {"adx": 30.0}),
            ]
        )
        result = analyzer.analyze(context)
        self.assertEqual(result.metadata["components_used"], ["sma"])
        self.assertTrue(result.metadata["adx"]["used"])

    def test_default_names_do_not_match_when_custom_names_used(self):
        analyzer = TrendAnalyzer(sma_fast_name="SMA_9", sma_slow_name="SMA_21")
        # Uses default-named SMA_20/SMA_50, which this analyzer isn't
        # configured to look for.
        context = make_context([sma(110, 20), sma(100, 50)])
        with self.assertRaises(InsufficientDataError):
            analyzer.analyze(context)


# ----------------------------------------------------------------------
# MomentumAnalyzer
# ----------------------------------------------------------------------
class TestMomentumAnalyzerBasics(unittest.TestCase):
    def setUp(self):
        self.analyzer = MomentumAnalyzer()

    def test_is_base_analyzer_subclass(self):
        from analysis.base import BaseAnalyzer

        self.assertIsInstance(self.analyzer, BaseAnalyzer)

    def test_default_name_is_class_name(self):
        self.assertEqual(self.analyzer.name, "MomentumAnalyzer")

    def test_rejects_non_context(self):
        with self.assertRaises(InvalidAnalysisContextError):
            self.analyzer.analyze(123)

    def test_raises_on_empty_context(self):
        context = make_context([])
        with self.assertRaises(InsufficientDataError):
            self.analyzer.analyze(context)

    def test_returns_analysis_result(self):
        context = make_context([rsi(70.0)])
        result = self.analyzer.analyze(context)
        self.assertIsInstance(result, AnalysisResult)
        self.assertEqual(result.analyzer_name, "MomentumAnalyzer")

    def test_invalid_roc_scale_raises(self):
        with self.assertRaises(ValueError):
            MomentumAnalyzer(roc_scale=0)

    def test_invalid_macd_hist_scale_raises(self):
        with self.assertRaises(ValueError):
            MomentumAnalyzer(macd_hist_scale=0)


class TestMomentumAnalyzerScoring(unittest.TestCase):
    def setUp(self):
        self.analyzer = MomentumAnalyzer()

    def test_overbought_rsi_is_bullish(self):
        context = make_context([rsi(90.0)])
        result = self.analyzer.analyze(context)
        self.assertGreater(result.score, 0.0)

    def test_oversold_rsi_is_bearish(self):
        context = make_context([rsi(10.0)])
        result = self.analyzer.analyze(context)
        self.assertLess(result.score, 0.0)

    def test_neutral_rsi_is_neutral_score(self):
        context = make_context([rsi(50.0)])
        result = self.analyzer.analyze(context)
        self.assertEqual(result.score, 0.0)

    def test_positive_roc_is_bullish(self):
        context = make_context([roc(5.0)])
        result = self.analyzer.analyze(context)
        self.assertAlmostEqual(result.score, 0.5)

    def test_negative_roc_is_bearish(self):
        context = make_context([roc(-5.0)])
        result = self.analyzer.analyze(context)
        self.assertAlmostEqual(result.score, -0.5)

    def test_stochastic_bullish(self):
        context = make_context([stochastic(80.0, 75.0)])
        result = self.analyzer.analyze(context)
        self.assertGreater(result.score, 0.0)

    def test_stochastic_bearish(self):
        context = make_context([stochastic(20.0, 25.0)])
        result = self.analyzer.analyze(context)
        self.assertLess(result.score, 0.0)

    def test_macd_histogram_bullish(self):
        context = make_context([macd(2.0, 1.0, histogram=1.0)])
        result = self.analyzer.analyze(context)
        self.assertGreater(result.score, 0.0)

    def test_macd_histogram_bearish(self):
        context = make_context([macd(1.0, 2.0, histogram=-1.0)])
        result = self.analyzer.analyze(context)
        self.assertLess(result.score, 0.0)

    def test_all_components_combine(self):
        context = make_context(
            [
                rsi(80.0),
                roc(8.0),
                stochastic(85.0, 80.0),
                macd(3.0, 1.0, histogram=2.0),
            ]
        )
        result = self.analyzer.analyze(context)
        self.assertGreater(result.score, 0.5)
        self.assertEqual(
            sorted(result.metadata["components_used"]),
            ["macd_histogram", "roc", "rsi", "stochastic"],
        )

    def test_score_never_exceeds_bounds(self):
        context = make_context([roc(1000.0), macd(1000.0, 1.0, histogram=999.0)])
        result = self.analyzer.analyze(context)
        self.assertLessEqual(result.score, 1.0)
        self.assertGreaterEqual(result.score, -1.0)

    def test_custom_roc_scale_changes_normalization(self):
        analyzer = MomentumAnalyzer(roc_scale=20.0)
        context = make_context([roc(10.0)])
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.score, 0.5)

    def test_custom_macd_hist_scale_changes_normalization(self):
        analyzer = MomentumAnalyzer(macd_hist_scale=4.0)
        context = make_context([macd(3.0, 1.0, histogram=2.0)])
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.score, 0.5)


class TestMomentumAnalyzerConfidence(unittest.TestCase):
    def setUp(self):
        self.analyzer = MomentumAnalyzer()

    def test_confidence_within_bounds(self):
        context = make_context([rsi(80.0), roc(5.0), stochastic(80.0, 78.0)])
        result = self.analyzer.analyze(context)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_more_components_increase_confidence_when_aligned(self):
        weak_context = make_context([rsi(55.0)])
        strong_context = make_context(
            [
                rsi(90.0),
                roc(9.0),
                stochastic(90.0, 88.0),
                macd(3.0, 1.0, histogram=2.0),
            ]
        )
        weak_result = self.analyzer.analyze(weak_context)
        strong_result = self.analyzer.analyze(strong_context)
        self.assertGreater(strong_result.confidence, weak_result.confidence)

    def test_stochastic_agreement_increases_confidence(self):
        agreeing_context = make_context([rsi(80.0), stochastic(80.0, 79.0)])
        disagreeing_context = make_context([rsi(80.0), stochastic(80.0, 20.0)])
        agreeing_result = self.analyzer.analyze(agreeing_context)
        disagreeing_result = self.analyzer.analyze(disagreeing_context)
        self.assertGreater(agreeing_result.confidence, disagreeing_result.confidence)

    def test_missing_stochastic_defaults_to_neutral_agreement_modifier(self):
        context = make_context([rsi(80.0)])
        result = self.analyzer.analyze(context)
        self.assertAlmostEqual(result.metadata["agreement_modifier"], 0.75)


class TestMomentumAnalyzerMetadata(unittest.TestCase):
    def test_metadata_explains_every_contributing_indicator(self):
        analyzer = MomentumAnalyzer()
        context = make_context(
            [
                rsi(70.0),
                roc(5.0),
                stochastic(70.0, 65.0),
                macd(3.0, 1.0, histogram=2.0),
            ]
        )
        result = analyzer.analyze(context)
        for key in ("rsi", "roc", "stochastic", "macd_histogram"):
            self.assertIn(key, result.metadata)
            self.assertIn("explanation", result.metadata[key])
        self.assertIn("score_scale", result.metadata)
        self.assertIn("confidence_scale", result.metadata)

    def test_metadata_marks_missing_components_as_unused(self):
        analyzer = MomentumAnalyzer()
        context = make_context([rsi(70.0)])
        result = analyzer.analyze(context)
        self.assertFalse(result.metadata["roc"]["used"])
        self.assertFalse(result.metadata["stochastic"]["used"])
        self.assertFalse(result.metadata["macd_histogram"]["used"])


class TestAnalyzersAreIndependent(unittest.TestCase):
    """
    TrendAnalyzer and MomentumAnalyzer must be usable independently --
    neither should import, instantiate, or otherwise depend on the
    other.
    """

    def test_trend_module_does_not_reference_momentum_analyzer(self):
        import analysis.technical.trend_analyzer as trend_module

        self.assertNotIn("MomentumAnalyzer", dir(trend_module))

    def test_momentum_module_does_not_reference_trend_analyzer(self):
        import analysis.technical.momentum_analyzer as momentum_module

        self.assertNotIn("TrendAnalyzer", dir(momentum_module))

    def test_each_analyzer_works_without_the_other_present_in_context(self):
        trend_context = make_context([sma(110, 20), sma(100, 50)])
        momentum_context = make_context([rsi(70.0)])
        trend_result = TrendAnalyzer().analyze(trend_context)
        momentum_result = MomentumAnalyzer().analyze(momentum_context)
        self.assertIsInstance(trend_result, AnalysisResult)
        self.assertIsInstance(momentum_result, AnalysisResult)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
