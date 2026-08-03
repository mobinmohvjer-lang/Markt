"""
test_volume_analyzer.py
-------------------------
Purpose:
    Unit tests for the Analysis Engine Part 3B concrete analyzer:
    `analysis.technical.VolumeAnalyzer`.

Mirrors the local-factory / assertion style already used by
`tests/test_analysis_technical.py` (Part 2) and
`tests/test_volatility_analyzer.py` (Part 3A), both left untouched by
this change. Uses the standard-library ``unittest`` framework, no
external test-runner dependency, no network access.

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from analysis import AnalysisContext, AnalysisResult, InsufficientDataError, InvalidAnalysisContextError
from analysis.technical import VolumeAnalyzer
from core.entities.candle import Candle
from core.entities.indicator_result import IndicatorResult
from core.entities.market_state import MarketState

NOW = datetime.now(timezone.utc)
SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"


# ----------------------------------------------------------------------
# Local test factories (mirrors tests/test_volatility_analyzer.py -- no
# changes made to tests/helpers.py, which is scoped to Data Engine
# tests, nor to any existing analysis test file).
# ----------------------------------------------------------------------
def make_candle(*, open_: float = 100.0, close: float = 100.0, volume: float = 1000.0) -> Candle:
    return Candle(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        open_time=NOW,
        close_time=NOW,
        open=Decimal(str(open_)),
        high=Decimal(str(max(open_, close) + 1)),
        low=Decimal(str(min(open_, close) - 1)),
        close=Decimal(str(close)),
        volume=Decimal(str(volume)),
    )


def make_market_state(candle: Candle | None = None) -> MarketState:
    return MarketState(
        symbol=SYMBOL, timeframe=TIMEFRAME, timestamp=NOW, latest_candle=candle
    )


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


def make_context(
    indicators: list[IndicatorResult], candle: Candle | None = None
) -> AnalysisContext:
    return AnalysisContext(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        market_state=make_market_state(candle),
        indicators=indicators,
    )


def obv(value: float, period: int = 1) -> IndicatorResult:
    return make_indicator(f"OBV_{period}", {"value": value})


def vwap(value: float, period: int = 14) -> IndicatorResult:
    return make_indicator(f"VWAP_{period}", {"value": value})


def volume_sma(value: float, period: int = 20) -> IndicatorResult:
    return make_indicator(f"VolumeSMA_{period}", {"value": value})


# ----------------------------------------------------------------------
# analyze() -- context validation / insufficient data
# ----------------------------------------------------------------------
class TestAnalyzeValidation(unittest.TestCase):
    def setUp(self):
        self.analyzer = VolumeAnalyzer()

    def test_rejects_non_context(self):
        with self.assertRaises(InvalidAnalysisContextError):
            self.analyzer.analyze("not a context")  # type: ignore[arg-type]

    def test_raises_insufficient_data_when_no_indicators(self):
        context = make_context([])
        with self.assertRaises(InsufficientDataError):
            self.analyzer.analyze(context)

    def test_raises_insufficient_data_when_indicators_all_invalid(self):
        # VWAP <= 0 and Volume SMA <= 0 are treated as invalid readings;
        # OBV missing entirely -> nothing usable.
        context = make_context([vwap(-1.0), volume_sma(0.0)])
        with self.assertRaises(InsufficientDataError):
            self.analyzer.analyze(context)

    def test_returns_analysis_result_when_at_least_one_component_present(self):
        context = make_context([obv(0.0)])
        result = self.analyzer.analyze(context)
        self.assertIsInstance(result, AnalysisResult)


# ----------------------------------------------------------------------
# OBV component
# ----------------------------------------------------------------------
class TestObvComponent(unittest.TestCase):
    def test_obv_at_normal_is_neutral(self):
        analyzer = VolumeAnalyzer(obv_normal=0.0, obv_scale=100.0)
        context = make_context([obv(0.0)])
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.score, 0.0)
        self.assertTrue(result.metadata["obv"]["used"])

    def test_obv_above_normal_is_bullish(self):
        analyzer = VolumeAnalyzer(obv_normal=0.0, obv_scale=100.0)
        context = make_context([obv(100.0)])
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.score, 1.0)

    def test_obv_below_normal_is_bearish(self):
        analyzer = VolumeAnalyzer(obv_normal=0.0, obv_scale=100.0)
        context = make_context([obv(-100.0)])
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.score, -1.0)

    def test_obv_missing_is_marked_unused(self):
        analyzer = VolumeAnalyzer()
        context = make_context([volume_sma(1000.0)], make_candle(volume=1500.0))
        result = analyzer.analyze(context)
        self.assertFalse(result.metadata["obv"]["used"])

    def test_obv_non_finite_value_is_ignored(self):
        analyzer = VolumeAnalyzer()
        context = make_context([obv(float("nan"))])
        with self.assertRaises(InsufficientDataError):
            analyzer.analyze(context)


# ----------------------------------------------------------------------
# VWAP component / price_vs_vwap
# ----------------------------------------------------------------------
class TestVwapComponent(unittest.TestCase):
    def test_price_above_vwap_is_bullish(self):
        analyzer = VolumeAnalyzer(vwap_scale=0.02)
        candle = make_candle(open_=100.0, close=102.0)  # +2% above vwap=100
        context = make_context([vwap(100.0)], candle)
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.score, 1.0)
        self.assertEqual(result.metadata["price_vs_vwap"]["relation"], "above")

    def test_price_below_vwap_is_bearish(self):
        analyzer = VolumeAnalyzer(vwap_scale=0.02)
        candle = make_candle(open_=100.0, close=98.0)  # -2% below vwap=100
        context = make_context([vwap(100.0)], candle)
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.score, -1.0)
        self.assertEqual(result.metadata["price_vs_vwap"]["relation"], "below")

    def test_price_at_vwap_is_neutral(self):
        analyzer = VolumeAnalyzer()
        candle = make_candle(open_=100.0, close=100.0)
        context = make_context([vwap(100.0)], candle)
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.score, 0.0)
        self.assertEqual(result.metadata["price_vs_vwap"]["relation"], "at")

    def test_vwap_without_candle_is_unused(self):
        analyzer = VolumeAnalyzer()
        context = make_context([vwap(100.0), obv(0.0)])  # no candle -> no price
        result = analyzer.analyze(context)
        self.assertFalse(result.metadata["vwap"]["used"])
        self.assertFalse(result.metadata["price_vs_vwap"]["computable"])

    def test_vwap_non_positive_is_unused(self):
        analyzer = VolumeAnalyzer()
        candle = make_candle(close=100.0)
        context = make_context([vwap(0.0), obv(0.0)], candle)
        result = analyzer.analyze(context)
        self.assertFalse(result.metadata["vwap"]["used"])

    def test_vwap_missing_marks_price_vs_vwap_not_computable(self):
        analyzer = VolumeAnalyzer()
        context = make_context([obv(0.0)], make_candle())
        result = analyzer.analyze(context)
        self.assertFalse(result.metadata["price_vs_vwap"]["computable"])


# ----------------------------------------------------------------------
# Volume participation / buying-selling pressure / volume trend
# ----------------------------------------------------------------------
class TestParticipationComponent(unittest.TestCase):
    def test_above_average_volume_on_up_candle_is_bullish_and_buying_pressure(self):
        analyzer = VolumeAnalyzer(participation_scale=1.0)
        candle = make_candle(open_=100.0, close=105.0, volume=2000.0)  # ratio = 2.0
        context = make_context([volume_sma(1000.0)], candle)
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.score, 1.0)
        self.assertGreater(result.metadata["buying_pressure"], 0.0)
        self.assertEqual(result.metadata["selling_pressure"], 0.0)

    def test_above_average_volume_on_down_candle_is_bearish_and_selling_pressure(self):
        analyzer = VolumeAnalyzer(participation_scale=1.0)
        candle = make_candle(open_=100.0, close=95.0, volume=2000.0)  # ratio = 2.0
        context = make_context([volume_sma(1000.0)], candle)
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.score, -1.0)
        self.assertGreater(result.metadata["selling_pressure"], 0.0)
        self.assertEqual(result.metadata["buying_pressure"], 0.0)

    def test_below_average_volume_pulls_score_toward_neutral(self):
        analyzer = VolumeAnalyzer(participation_scale=1.0)
        candle = make_candle(open_=100.0, close=105.0, volume=500.0)  # ratio = 0.5
        context = make_context([volume_sma(1000.0)], candle)
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.score, 0.0)
        self.assertEqual(result.metadata["buying_pressure"], 0.0)
        self.assertEqual(result.metadata["selling_pressure"], 0.0)

    def test_volume_trend_positive_when_above_average(self):
        analyzer = VolumeAnalyzer()
        candle = make_candle(open_=100.0, close=101.0, volume=1500.0)
        context = make_context([volume_sma(1000.0)], candle)
        result = analyzer.analyze(context)
        self.assertGreater(result.metadata["volume_trend"], 0.0)
        self.assertGreater(result.metadata["participation_strength"], 0.0)

    def test_volume_trend_negative_when_below_average(self):
        analyzer = VolumeAnalyzer()
        candle = make_candle(open_=100.0, close=99.0, volume=500.0)
        context = make_context([volume_sma(1000.0)], candle)
        result = analyzer.analyze(context)
        self.assertLess(result.metadata["volume_trend"], 0.0)
        self.assertGreater(result.metadata["participation_strength"], 0.0)

    def test_volume_sma_without_candle_is_unused(self):
        analyzer = VolumeAnalyzer()
        context = make_context([volume_sma(1000.0), obv(0.0)])  # no candle -> no current volume
        result = analyzer.analyze(context)
        self.assertFalse(result.metadata["volume_participation"]["used"])

    def test_volume_sma_non_positive_is_unused(self):
        analyzer = VolumeAnalyzer()
        candle = make_candle(volume=500.0)
        context = make_context([volume_sma(0.0), obv(0.0)], candle)
        result = analyzer.analyze(context)
        self.assertFalse(result.metadata["volume_participation"]["used"])

    def test_negative_current_volume_is_unused(self):
        analyzer = VolumeAnalyzer()
        candle = make_candle(volume=-1.0)
        context = make_context([volume_sma(1000.0), obv(0.0)], candle)
        result = analyzer.analyze(context)
        self.assertFalse(result.metadata["volume_participation"]["used"])


# ----------------------------------------------------------------------
# Confirmation / divergence
# ----------------------------------------------------------------------
class TestConfirmationDivergence(unittest.TestCase):
    def test_agreeing_direction_yields_confirmation(self):
        analyzer = VolumeAnalyzer(obv_normal=0.0, obv_scale=100.0)
        candle = make_candle(open_=100.0, close=105.0)  # up candle
        context = make_context([obv(100.0)], candle)  # bullish OBV
        result = analyzer.analyze(context)
        self.assertGreater(result.metadata["volume_confirmation"], 0.0)
        self.assertEqual(result.metadata["volume_divergence"], 0.0)

    def test_disagreeing_direction_yields_divergence(self):
        analyzer = VolumeAnalyzer(obv_normal=0.0, obv_scale=100.0)
        candle = make_candle(open_=100.0, close=95.0)  # down candle
        context = make_context([obv(100.0)], candle)  # bullish OBV
        result = analyzer.analyze(context)
        self.assertGreater(result.metadata["volume_divergence"], 0.0)
        self.assertEqual(result.metadata["volume_confirmation"], 0.0)

    def test_no_candle_direction_yields_neither(self):
        analyzer = VolumeAnalyzer(obv_normal=0.0, obv_scale=100.0)
        candle = make_candle(open_=100.0, close=100.0)  # flat candle
        context = make_context([obv(100.0)], candle)
        result = analyzer.analyze(context)
        self.assertEqual(result.metadata["volume_confirmation"], 0.0)
        self.assertEqual(result.metadata["volume_divergence"], 0.0)
        self.assertFalse(result.metadata["confirmation_detail"]["computable"])

    def test_missing_obv_yields_not_computable(self):
        analyzer = VolumeAnalyzer()
        candle = make_candle(open_=100.0, close=105.0)
        context = make_context([vwap(100.0)], candle)
        result = analyzer.analyze(context)
        self.assertFalse(result.metadata["confirmation_detail"]["computable"])


# ----------------------------------------------------------------------
# Combined scoring / confidence / completeness
# ----------------------------------------------------------------------
class TestCombinedScoring(unittest.TestCase):
    def test_all_three_components_agree_yields_high_confidence(self):
        analyzer = VolumeAnalyzer(obv_normal=0.0, obv_scale=100.0, vwap_scale=0.02, participation_scale=1.0)
        candle = make_candle(open_=100.0, close=104.0, volume=2000.0)
        context = make_context([obv(100.0), vwap(100.0), volume_sma(1000.0)], candle)
        result = analyzer.analyze(context)
        self.assertGreater(result.score, 0.0)
        self.assertGreater(result.confidence, 0.5)
        self.assertEqual(result.metadata["components_used"], ["obv", "volume_participation", "vwap"])

    def test_conflicting_components_lower_confidence_via_agreement(self):
        analyzer = VolumeAnalyzer(obv_normal=0.0, obv_scale=100.0, vwap_scale=0.02)
        candle = make_candle(open_=100.0, close=95.0)  # bearish price positioning
        context = make_context([obv(100.0), vwap(100.0)], candle)  # bullish OBV
        result = analyzer.analyze(context)
        self.assertLess(result.metadata["agreement_modifier"], 1.0)

    def test_completeness_ratio_scales_with_components_present(self):
        analyzer = VolumeAnalyzer()
        context_one = make_context([obv(0.0)])
        context_three = make_context(
            [obv(0.0), vwap(100.0), volume_sma(1000.0)], make_candle()
        )
        result_one = analyzer.analyze(context_one)
        result_three = analyzer.analyze(context_three)
        self.assertAlmostEqual(result_one.metadata["completeness_ratio"], 1 / 3)
        self.assertAlmostEqual(result_three.metadata["completeness_ratio"], 1.0)

    def test_score_and_confidence_are_within_bounds(self):
        analyzer = VolumeAnalyzer()
        candle = make_candle(open_=100.0, close=110.0, volume=5000.0)
        context = make_context([obv(1_000_000.0), vwap(90.0), volume_sma(100.0)], candle)
        result = analyzer.analyze(context)
        self.assertGreaterEqual(result.score, -1.0)
        self.assertLessEqual(result.score, 1.0)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_summary_mentions_components_used(self):
        analyzer = VolumeAnalyzer()
        context = make_context([obv(0.0)])
        result = analyzer.analyze(context)
        self.assertIn("obv", result.metadata["components_used"])
        self.assertIsInstance(result.summary, str)
        self.assertTrue(len(result.summary) > 0)

    def test_result_carries_symbol_and_timeframe_and_analyzer_name(self):
        analyzer = VolumeAnalyzer(name="MyVolumeAnalyzer")
        context = make_context([obv(0.0)])
        result = analyzer.analyze(context)
        self.assertEqual(result.symbol, SYMBOL)
        self.assertEqual(result.timeframe, TIMEFRAME)
        self.assertEqual(result.analyzer_name, "MyVolumeAnalyzer")


# ----------------------------------------------------------------------
# Constructor validation
# ----------------------------------------------------------------------
class TestConstructorValidation(unittest.TestCase):
    def test_zero_obv_scale_rejected(self):
        with self.assertRaises(ValueError):
            VolumeAnalyzer(obv_scale=0.0)

    def test_zero_vwap_scale_rejected(self):
        with self.assertRaises(ValueError):
            VolumeAnalyzer(vwap_scale=0.0)

    def test_zero_participation_scale_rejected(self):
        with self.assertRaises(ValueError):
            VolumeAnalyzer(participation_scale=0.0)

    def test_default_name_is_class_name(self):
        analyzer = VolumeAnalyzer()
        self.assertEqual(analyzer.name, "VolumeAnalyzer")

    def test_custom_indicator_names_are_respected(self):
        analyzer = VolumeAnalyzer(
            obv_name="CustomOBV", vwap_name="CustomVWAP", volume_sma_name="CustomVolSMA"
        )
        context = make_context([make_indicator("CustomOBV", {"value": 50.0})])
        result = analyzer.analyze(context)
        self.assertTrue(result.metadata["obv"]["used"])
        self.assertEqual(result.metadata["obv"]["indicator"], "CustomOBV")


# ----------------------------------------------------------------------
# Malformed / malicious upper-lower style edge cases specific to volume
# ----------------------------------------------------------------------
class TestEdgeCases(unittest.TestCase):
    def test_missing_indicator_values_key_is_ignored(self):
        analyzer = VolumeAnalyzer()
        # OBV entry present but without the expected "value" key.
        context = make_context([make_indicator("OBV_1", {"unexpected": 1.0})])
        with self.assertRaises(InsufficientDataError):
            analyzer.analyze(context)

    def test_bool_values_are_not_treated_as_numbers(self):
        analyzer = VolumeAnalyzer()
        context = make_context([make_indicator("OBV_1", {"value": True})])
        with self.assertRaises(InsufficientDataError):
            analyzer.analyze(context)

    def test_flat_candle_direction_is_zero(self):
        analyzer = VolumeAnalyzer()
        candle = make_candle(open_=100.0, close=100.0, volume=2000.0)
        context = make_context([volume_sma(1000.0)], candle)
        result = analyzer.analyze(context)
        self.assertAlmostEqual(result.score, 0.0)
        self.assertEqual(result.metadata["buying_pressure"], 0.0)
        self.assertEqual(result.metadata["selling_pressure"], 0.0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
