"""
test_volatility_analyzer.py
----------------------------
Purpose:
    Unit tests for the Analysis Engine Part 3A concrete analyzer:
    `analysis.technical.VolatilityAnalyzer`.

Mirrors the local-factory / assertion style already used by
`tests/test_analysis_technical.py` (Part 2's test file, left untouched
by this change). Uses the standard-library ``unittest`` framework, no
external test-runner dependency, no network access.

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from analysis import AnalysisContext, AnalysisResult, InsufficientDataError, InvalidAnalysisContextError
from analysis.technical import VolatilityAnalyzer
from analysis.technical.volatility_analyzer import _volatility_label
from core.entities.indicator_result import IndicatorResult
from core.entities.market_state import MarketState

NOW = datetime.now(timezone.utc)
SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"


# ----------------------------------------------------------------------
# Local test factories (mirrors tests/test_analysis_technical.py -- no
# changes made to tests/helpers.py, which is scoped to Data Engine
# tests, nor to test_analysis_technical.py itself).
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


def atr(value: float, period: int = 14) -> IndicatorResult:
    return make_indicator(f"ATR_{period}", {"value": value})


def bollinger(middle: float, upper: float, lower: float, period: int = 20) -> IndicatorResult:
    return make_indicator(
        f"BollingerBands_{period}", {"middle": middle, "upper": upper, "lower": lower}
    )


def keltner(middle: float, upper: float, lower: float, period: int = 20) -> IndicatorResult:
    return make_indicator(
        f"KeltnerChannel_{period}", {"middle": middle, "upper": upper, "lower": lower}
    )


def donchian(middle: float, upper: float, lower: float, period: int = 20) -> IndicatorResult:
    return make_indicator(
        f"DonchianChannel_{period}", {"middle": middle, "upper": upper, "lower": lower}
    )


def band_with_width(width: float, *, middle: float = 100.0) -> tuple[float, float, float]:
    """Return (middle, upper, lower) whose (upper-lower)/middle == width."""
    half = (width * middle) / 2.0
    return middle, middle + half, middle - half


# ----------------------------------------------------------------------
# _volatility_label
# ----------------------------------------------------------------------
class TestVolatilityLabel(unittest.TestCase):
    def test_strong_expansion_at_threshold(self):
        self.assertEqual(_volatility_label(0.5), "strong expansion")

    def test_strong_expansion_above_threshold(self):
        self.assertEqual(_volatility_label(1.0), "strong expansion")

    def test_mild_expansion(self):
        self.assertEqual(_volatility_label(0.3), "mild expansion")

    def test_mild_expansion_at_threshold(self):
        self.assertEqual(_volatility_label(0.15), "mild expansion")

    def test_stable_at_zero(self):
        self.assertEqual(_volatility_label(0.0), "stable")

    def test_stable_just_below_mild_expansion(self):
        self.assertEqual(_volatility_label(0.14), "stable")

    def test_mild_contraction_at_negative_threshold(self):
        self.assertEqual(_volatility_label(-0.15), "mild contraction")

    def test_mild_contraction(self):
        self.assertEqual(_volatility_label(-0.3), "mild contraction")

    def test_strong_contraction_at_threshold(self):
        self.assertEqual(_volatility_label(-0.5), "strong contraction")

    def test_strong_contraction_below_threshold(self):
        self.assertEqual(_volatility_label(-1.0), "strong contraction")


# ----------------------------------------------------------------------
# Constructor validation
# ----------------------------------------------------------------------
class TestConstructor(unittest.TestCase):
    def test_default_indicator_names(self):
        analyzer = VolatilityAnalyzer()
        self.assertEqual(analyzer.atr_name, "ATR_14")
        self.assertEqual(analyzer.bollinger_name, "BollingerBands_20")
        self.assertEqual(analyzer.keltner_name, "KeltnerChannel_20")
        self.assertEqual(analyzer.donchian_name, "DonchianChannel_20")

    def test_default_name_is_class_name(self):
        analyzer = VolatilityAnalyzer()
        self.assertEqual(analyzer.name, "VolatilityAnalyzer")

    def test_custom_name(self):
        analyzer = VolatilityAnalyzer(name="MyVolatility")
        self.assertEqual(analyzer.name, "MyVolatility")

    def test_custom_indicator_names(self):
        analyzer = VolatilityAnalyzer(
            atr_name="ATR_20",
            bollinger_name="BollingerBands_10",
            keltner_name="KeltnerChannel_10",
            donchian_name="DonchianChannel_10",
        )
        self.assertEqual(analyzer.atr_name, "ATR_20")
        self.assertEqual(analyzer.bollinger_name, "BollingerBands_10")
        self.assertEqual(analyzer.keltner_name, "KeltnerChannel_10")
        self.assertEqual(analyzer.donchian_name, "DonchianChannel_10")

    def test_zero_atr_scale_raises(self):
        with self.assertRaises(ValueError):
            VolatilityAnalyzer(atr_scale=0)

    def test_zero_bollinger_width_scale_raises(self):
        with self.assertRaises(ValueError):
            VolatilityAnalyzer(bollinger_width_scale=0)

    def test_zero_keltner_width_scale_raises(self):
        with self.assertRaises(ValueError):
            VolatilityAnalyzer(keltner_width_scale=0)

    def test_zero_donchian_width_scale_raises(self):
        with self.assertRaises(ValueError):
            VolatilityAnalyzer(donchian_width_scale=0)


# ----------------------------------------------------------------------
# analyze() -- context validation / insufficient data
# ----------------------------------------------------------------------
class TestContextValidation(unittest.TestCase):
    def test_invalid_context_type_raises(self):
        analyzer = VolatilityAnalyzer()
        with self.assertRaises(InvalidAnalysisContextError):
            analyzer.analyze("not a context")  # type: ignore[arg-type]

    def test_no_indicators_raises_insufficient_data(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([])
        with self.assertRaises(InsufficientDataError):
            analyzer.analyze(context)

    def test_unrelated_indicator_only_raises_insufficient_data(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([make_indicator("RSI_14", {"value": 55.0})])
        with self.assertRaises(InsufficientDataError):
            analyzer.analyze(context)

    def test_insufficient_data_message_names_all_four_indicators(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([])
        try:
            analyzer.analyze(context)
            self.fail("expected InsufficientDataError")
        except InsufficientDataError as exc:
            message = str(exc)
            self.assertIn("ATR_14", message)
            self.assertIn("BollingerBands_20", message)
            self.assertIn("KeltnerChannel_20", message)
            self.assertIn("DonchianChannel_20", message)


# ----------------------------------------------------------------------
# analyze() -- result shape / passthrough
# ----------------------------------------------------------------------
class TestResultShape(unittest.TestCase):
    def test_returns_analysis_result(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(1.0)])
        result = analyzer.analyze(context)
        self.assertIsInstance(result, AnalysisResult)

    def test_result_symbol_and_timeframe_passthrough(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(1.0)])
        result = analyzer.analyze(context)
        self.assertEqual(result.symbol, SYMBOL)
        self.assertEqual(result.timeframe, TIMEFRAME)

    def test_result_analyzer_name_passthrough(self):
        analyzer = VolatilityAnalyzer(name="CustomVol")
        context = make_context([atr(1.0)])
        result = analyzer.analyze(context)
        self.assertEqual(result.analyzer_name, "CustomVol")

    def test_score_within_bounds(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(5.0)])
        result = analyzer.analyze(context)
        self.assertGreaterEqual(result.score, -1.0)
        self.assertLessEqual(result.score, 1.0)

    def test_confidence_within_bounds(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(5.0)])
        result = analyzer.analyze(context)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_summary_is_non_empty_string(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(1.0)])
        result = analyzer.analyze(context)
        self.assertIsInstance(result.summary, str)
        self.assertGreater(len(result.summary), 0)

    def test_metadata_contains_required_keys(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(1.0), *self._full_band_set()])
        result = analyzer.analyze(context)
        for key in (
            "components_used",
            "component_scores",
            "completeness_ratio",
            "conviction",
            "agreement_modifier",
            "score_scale",
            "confidence_scale",
            "volatility_expansion",
            "volatility_contraction",
            "range_compression",
            "breakout_probability",
            "trend_strength_contribution",
            "squeeze",
            "atr",
            "bollinger",
            "keltner",
            "donchian",
        ):
            self.assertIn(key, result.metadata)

    @staticmethod
    def _full_band_set():
        return [
            bollinger(*band_with_width(0.04)),
            keltner(*band_with_width(0.03)),
            donchian(*band_with_width(0.05)),
        ]


# ----------------------------------------------------------------------
# analyze() -- neutral / expansion / contraction regimes
# ----------------------------------------------------------------------
class TestVolatilityRegimes(unittest.TestCase):
    def _full_context(self, *, atr_value, bb_width, kc_width, dc_width):
        return make_context(
            [
                atr(atr_value),
                bollinger(*band_with_width(bb_width)),
                keltner(*band_with_width(kc_width)),
                donchian(*band_with_width(dc_width)),
            ]
        )

    def test_all_normal_readings_yield_neutral_score(self):
        analyzer = VolatilityAnalyzer()
        context = self._full_context(atr_value=1.0, bb_width=0.04, kc_width=0.03, dc_width=0.05)
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.score, 0.0, places=6)

    def test_all_normal_readings_yield_low_confidence(self):
        # Zero conviction (every component reads exactly "normal") means
        # there is no strong signal either way -- confidence should be
        # at its floor (0.0), matching TrendAnalyzer/MomentumAnalyzer's
        # conviction-weighted confidence design.
        analyzer = VolatilityAnalyzer()
        context = self._full_context(atr_value=1.0, bb_width=0.04, kc_width=0.03, dc_width=0.05)
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.confidence, 0.0, places=6)

    def test_all_expanded_readings_yield_positive_score(self):
        analyzer = VolatilityAnalyzer()
        context = self._full_context(atr_value=2.0, bb_width=0.08, kc_width=0.06, dc_width=0.10)
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.score, 1.0, places=6)

    def test_all_expanded_readings_yield_full_confidence(self):
        analyzer = VolatilityAnalyzer()
        context = self._full_context(atr_value=2.0, bb_width=0.08, kc_width=0.06, dc_width=0.10)
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.confidence, 1.0, places=6)

    def test_all_contracted_readings_yield_negative_score(self):
        analyzer = VolatilityAnalyzer()
        context = self._full_context(atr_value=0.0, bb_width=0.0, kc_width=0.0, dc_width=0.0)
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.score, -1.0, places=6)

    def test_all_contracted_readings_yield_full_confidence(self):
        analyzer = VolatilityAnalyzer()
        context = self._full_context(atr_value=0.0, bb_width=0.0, kc_width=0.0, dc_width=0.0)
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.confidence, 1.0, places=6)

    def test_expansion_summary_mentions_label(self):
        analyzer = VolatilityAnalyzer()
        context = self._full_context(atr_value=2.0, bb_width=0.08, kc_width=0.06, dc_width=0.10)
        result = analyzer.analyze(context)
        self.assertIn("expansion", result.summary.lower())

    def test_contraction_summary_mentions_label(self):
        analyzer = VolatilityAnalyzer()
        context = self._full_context(atr_value=0.0, bb_width=0.0, kc_width=0.0, dc_width=0.0)
        result = analyzer.analyze(context)
        self.assertIn("contraction", result.summary.lower())

    def test_volatility_expansion_metadata_degree(self):
        analyzer = VolatilityAnalyzer()
        context = self._full_context(atr_value=2.0, bb_width=0.08, kc_width=0.06, dc_width=0.10)
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.metadata["volatility_expansion"], 1.0, places=6)
        self.assertAlmostEqual(result.metadata["volatility_contraction"], 0.0, places=6)

    def test_volatility_contraction_metadata_degree(self):
        analyzer = VolatilityAnalyzer()
        context = self._full_context(atr_value=0.0, bb_width=0.0, kc_width=0.0, dc_width=0.0)
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.metadata["volatility_contraction"], 1.0, places=6)
        self.assertAlmostEqual(result.metadata["volatility_expansion"], 0.0, places=6)


# ----------------------------------------------------------------------
# analyze() -- partial data / missing indicators reduce confidence
# ----------------------------------------------------------------------
class TestPartialData(unittest.TestCase):
    def test_single_indicator_present_does_not_raise(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(2.0)])
        result = analyzer.analyze(context)
        self.assertIsInstance(result, AnalysisResult)

    def test_single_indicator_present_lowers_confidence_vs_full_set(self):
        analyzer = VolatilityAnalyzer()
        partial_context = make_context([atr(2.0)])
        full_context = make_context(
            [
                atr(2.0),
                bollinger(*band_with_width(0.08)),
                keltner(*band_with_width(0.06)),
                donchian(*band_with_width(0.10)),
            ]
        )
        partial_result = analyzer.analyze(partial_context)
        full_result = analyzer.analyze(full_context)
        self.assertLess(partial_result.confidence, full_result.confidence)

    def test_single_indicator_completeness_ratio(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(2.0)])
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.metadata["completeness_ratio"], 0.25, places=6)

    def test_three_of_four_indicators_completeness_ratio(self):
        analyzer = VolatilityAnalyzer()
        context = make_context(
            [atr(1.0), bollinger(*band_with_width(0.04)), keltner(*band_with_width(0.03))]
        )
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.metadata["completeness_ratio"], 0.75, places=6)

    def test_components_used_reflects_available_indicators(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(1.0), donchian(*band_with_width(0.05))])
        result = analyzer.analyze(context)
        self.assertEqual(result.metadata["components_used"], ["atr", "donchian"])

    def test_missing_bollinger_recorded_in_metadata(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(1.0)])
        result = analyzer.analyze(context)
        self.assertFalse(result.metadata["bollinger"]["used"])
        self.assertIn("reason", result.metadata["bollinger"])


# ----------------------------------------------------------------------
# analyze() -- malformed / invalid indicator data degrades gracefully
# ----------------------------------------------------------------------
class TestMalformedData(unittest.TestCase):
    def test_negative_atr_is_treated_as_missing(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(-1.0), donchian(*band_with_width(0.05))])
        result = analyzer.analyze(context)
        self.assertFalse(result.metadata["atr"]["used"])
        self.assertNotIn("atr", result.metadata["components_used"])

    def test_zero_middle_band_is_treated_as_missing(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(1.0), bollinger(middle=0.0, upper=2.0, lower=-2.0)])
        result = analyzer.analyze(context)
        self.assertFalse(result.metadata["bollinger"]["used"])
        self.assertNotIn("bollinger", result.metadata["components_used"])

    def test_upper_below_lower_is_treated_as_missing(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(1.0), keltner(middle=100.0, upper=95.0, lower=105.0)])
        result = analyzer.analyze(context)
        self.assertFalse(result.metadata["keltner"]["used"])
        self.assertNotIn("keltner", result.metadata["components_used"])

    def test_all_missing_and_malformed_raises_insufficient_data(self):
        analyzer = VolatilityAnalyzer()
        context = make_context(
            [
                atr(-1.0),
                bollinger(middle=0.0, upper=1.0, lower=-1.0),
            ]
        )
        with self.assertRaises(InsufficientDataError):
            analyzer.analyze(context)

    def test_non_finite_indicator_value_treated_as_missing(self):
        analyzer = VolatilityAnalyzer()
        context = make_context(
            [make_indicator("ATR_14", {"value": float("nan")}), donchian(*band_with_width(0.05))]
        )
        result = analyzer.analyze(context)
        self.assertFalse(result.metadata["atr"]["used"])


# ----------------------------------------------------------------------
# analyze() -- squeeze / breakout probability / range compression
# ----------------------------------------------------------------------
class TestSqueezeAndBreakout(unittest.TestCase):
    def test_squeeze_detected_when_bollinger_inside_keltner(self):
        analyzer = VolatilityAnalyzer()
        context = make_context(
            [
                bollinger(*band_with_width(0.02)),
                keltner(*band_with_width(0.05)),
            ]
        )
        result = analyzer.analyze(context)
        squeeze = result.metadata["squeeze"]
        self.assertTrue(squeeze["computable"])
        self.assertTrue(squeeze["squeeze_on"])
        self.assertAlmostEqual(squeeze["squeeze_ratio"], 0.4, places=6)

    def test_squeeze_not_on_when_bollinger_wider_than_keltner(self):
        analyzer = VolatilityAnalyzer()
        context = make_context(
            [
                bollinger(*band_with_width(0.08)),
                keltner(*band_with_width(0.03)),
            ]
        )
        result = analyzer.analyze(context)
        squeeze = result.metadata["squeeze"]
        self.assertTrue(squeeze["computable"])
        self.assertFalse(squeeze["squeeze_on"])

    def test_squeeze_not_computable_without_both_bands(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(1.0)])
        result = analyzer.analyze(context)
        squeeze = result.metadata["squeeze"]
        self.assertFalse(squeeze["computable"])

    def test_breakout_probability_boosted_when_squeeze_on(self):
        analyzer = VolatilityAnalyzer()
        squeeze_context = make_context(
            [bollinger(*band_with_width(0.02)), keltner(*band_with_width(0.05))]
        )
        no_squeeze_context = make_context(
            [bollinger(*band_with_width(0.08)), keltner(*band_with_width(0.03))]
        )
        squeeze_result = analyzer.analyze(squeeze_context)
        no_squeeze_result = analyzer.analyze(no_squeeze_context)
        self.assertGreater(
            squeeze_result.metadata["breakout_probability"],
            no_squeeze_result.metadata["breakout_probability"],
        )

    def test_breakout_probability_within_bounds(self):
        analyzer = VolatilityAnalyzer()
        context = make_context(
            [bollinger(*band_with_width(0.001)), keltner(*band_with_width(0.5))]
        )
        result = analyzer.analyze(context)
        self.assertGreaterEqual(result.metadata["breakout_probability"], 0.0)
        self.assertLessEqual(result.metadata["breakout_probability"], 1.0)

    def test_range_compression_within_bounds(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(0.5), donchian(*band_with_width(0.01))])
        result = analyzer.analyze(context)
        self.assertGreaterEqual(result.metadata["range_compression"], 0.0)
        self.assertLessEqual(result.metadata["range_compression"], 1.0)

    def test_range_compression_high_for_contracted_market(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(0.0), donchian(*band_with_width(0.0))])
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.metadata["range_compression"], 1.0, places=6)

    def test_range_compression_low_for_expanded_market(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(2.0), donchian(*band_with_width(0.10))])
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.metadata["range_compression"], 0.0, places=6)


# ----------------------------------------------------------------------
# analyze() -- trend strength contribution (confidence-only, descriptive)
# ----------------------------------------------------------------------
class TestTrendStrengthContribution(unittest.TestCase):
    def test_present_as_dict_with_value_and_explanation(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(1.0)])
        result = analyzer.analyze(context)
        contribution = result.metadata["trend_strength_contribution"]
        self.assertIn("value", contribution)
        self.assertIn("explanation", contribution)

    def test_value_within_bounds(self):
        analyzer = VolatilityAnalyzer()
        context = make_context([atr(2.0), donchian(*band_with_width(0.10))])
        result = analyzer.analyze(context)
        value = result.metadata["trend_strength_contribution"]["value"]
        self.assertGreaterEqual(value, 0.0)
        self.assertLessEqual(value, 1.0)

    def test_zero_when_no_conviction(self):
        analyzer = VolatilityAnalyzer()
        context = make_context(
            [
                atr(1.0),
                bollinger(*band_with_width(0.04)),
                keltner(*band_with_width(0.03)),
                donchian(*band_with_width(0.05)),
            ]
        )
        result = analyzer.analyze(context)
        value = result.metadata["trend_strength_contribution"]["value"]
        self.assertAlmostEqual(value, 0.0, places=6)


# ----------------------------------------------------------------------
# analyze() -- custom scale/normal tuning
# ----------------------------------------------------------------------
class TestCustomTuning(unittest.TestCase):
    def test_custom_atr_normal_and_scale(self):
        analyzer = VolatilityAnalyzer(atr_normal=10.0, atr_scale=5.0)
        context = make_context([atr(15.0)])
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.metadata["atr"]["score"], 1.0, places=6)

    def test_custom_bollinger_width_normal_and_scale(self):
        analyzer = VolatilityAnalyzer(bollinger_width_normal=0.10, bollinger_width_scale=0.05)
        context = make_context([bollinger(*band_with_width(0.10))])
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.metadata["bollinger"]["score"], 0.0, places=6)

    def test_custom_indicator_names_used_for_lookup(self):
        analyzer = VolatilityAnalyzer(atr_name="ATR_20")
        context = make_context([atr(1.0, period=20)])
        result = analyzer.analyze(context)
        self.assertTrue(result.metadata["atr"]["used"])

    def test_default_atr_name_not_found_when_custom_name_configured(self):
        analyzer = VolatilityAnalyzer(atr_name="ATR_20")
        context = make_context([atr(1.0, period=14)])
        with self.assertRaises(InsufficientDataError):
            analyzer.analyze(context)


if __name__ == "__main__":
    unittest.main()
