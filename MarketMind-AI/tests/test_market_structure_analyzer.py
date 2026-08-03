"""
test_market_structure_analyzer.py
-----------------------------------
Purpose:
    Unit tests for the Analysis Engine Part 3C concrete analyzer:
    `analysis.technical.MarketStructureAnalyzer`.

Mirrors the local-factory / assertion style already used by
`tests/test_analysis_technical.py` (Part 2), `tests/test_volatility_analyzer.py`
(Part 3A), and `tests/test_volume_analyzer.py` (Part 3B), all left
untouched by this change. Uses the standard-library ``unittest``
framework, no external test-runner dependency, no network access.

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from analysis import AnalysisContext, AnalysisResult, InsufficientDataError, InvalidAnalysisContextError
from analysis.technical import MarketStructureAnalyzer
from core.entities.candle import Candle
from core.entities.indicator_result import IndicatorResult
from core.entities.market_state import MarketState

NOW = datetime.now(timezone.utc)
SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"


# ----------------------------------------------------------------------
# Local test factories (mirrors tests/test_volume_analyzer.py -- no
# changes made to tests/helpers.py, which is scoped to Data Engine
# tests, nor to any existing analysis test file).
# ----------------------------------------------------------------------
def make_candle(*, close: float = 100.0) -> Candle:
    return Candle(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        open_time=NOW,
        close_time=NOW,
        open=Decimal(str(close)),
        high=Decimal(str(close + 1)),
        low=Decimal(str(close - 1)),
        close=Decimal(str(close)),
        volume=Decimal("1000"),
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


def swing_points(
    *,
    high_1: float | None = None,
    high_2: float | None = None,
    low_1: float | None = None,
    low_2: float | None = None,
    name: str = "SwingPoints_1",
) -> IndicatorResult:
    values: dict[str, float] = {}
    if high_1 is not None:
        values["swing_high_1"] = high_1
    if high_2 is not None:
        values["swing_high_2"] = high_2
    if low_1 is not None:
        values["swing_low_1"] = low_1
    if low_2 is not None:
        values["swing_low_2"] = low_2
    return make_indicator(name, values)


# ----------------------------------------------------------------------
# analyze() -- context validation / insufficient data
# ----------------------------------------------------------------------
class TestAnalyzeValidation(unittest.TestCase):
    def setUp(self):
        self.analyzer = MarketStructureAnalyzer()

    def test_rejects_non_context(self):
        with self.assertRaises(InvalidAnalysisContextError):
            self.analyzer.analyze("not a context")  # type: ignore[arg-type]

    def test_raises_insufficient_data_when_no_indicators(self):
        context = make_context([])
        with self.assertRaises(InsufficientDataError):
            self.analyzer.analyze(context)

    def test_raises_insufficient_data_when_swing_points_all_missing(self):
        context = make_context([swing_points()])
        with self.assertRaises(InsufficientDataError):
            self.analyzer.analyze(context)

    def test_raises_insufficient_data_when_values_non_finite(self):
        context = make_context(
            [swing_points(high_1=float("nan"), high_2=100.0, low_1=float("nan"), low_2=90.0)]
        )
        with self.assertRaises(InsufficientDataError):
            self.analyzer.analyze(context)

    def test_returns_analysis_result_when_only_high_pair_present(self):
        context = make_context([swing_points(high_1=110.0, high_2=100.0)])
        result = self.analyzer.analyze(context)
        self.assertIsInstance(result, AnalysisResult)

    def test_returns_analysis_result_when_only_low_pair_present(self):
        context = make_context([swing_points(low_1=95.0, low_2=90.0)])
        result = self.analyzer.analyze(context)
        self.assertIsInstance(result, AnalysisResult)


# ----------------------------------------------------------------------
# HH / HL / LH / LL classification
# ----------------------------------------------------------------------
class TestClassification(unittest.TestCase):
    def setUp(self):
        self.analyzer = MarketStructureAnalyzer()

    def test_higher_high_and_higher_low_is_bullish_uptrend(self):
        context = make_context(
            [swing_points(high_1=110.0, high_2=100.0, low_1=95.0, low_2=90.0)]
        )
        result = self.analyzer.analyze(context)
        self.assertEqual(result.metadata["swing_high"]["classification"], "HH")
        self.assertEqual(result.metadata["swing_low"]["classification"], "HL")
        self.assertEqual(result.metadata["structure_bias"], "bullish")
        self.assertEqual(result.metadata["market_regime"], "uptrend")
        self.assertGreater(result.score, 0.0)

    def test_lower_high_and_lower_low_is_bearish_downtrend(self):
        context = make_context(
            [swing_points(high_1=95.0, high_2=100.0, low_1=80.0, low_2=90.0)]
        )
        result = self.analyzer.analyze(context)
        self.assertEqual(result.metadata["swing_high"]["classification"], "LH")
        self.assertEqual(result.metadata["swing_low"]["classification"], "LL")
        self.assertEqual(result.metadata["structure_bias"], "bearish")
        self.assertEqual(result.metadata["market_regime"], "downtrend")
        self.assertLess(result.score, 0.0)

    def test_mixed_structure_is_ranging(self):
        context = make_context(
            [swing_points(high_1=110.0, high_2=100.0, low_1=80.0, low_2=90.0)]
        )
        result = self.analyzer.analyze(context)
        self.assertEqual(result.metadata["swing_high"]["classification"], "HH")
        self.assertEqual(result.metadata["swing_low"]["classification"], "LL")
        self.assertEqual(result.metadata["structure_bias"], "mixed")
        self.assertEqual(result.metadata["market_regime"], "ranging")

    def test_equal_swing_high_is_equal_high(self):
        context = make_context(
            [swing_points(high_1=100.0, high_2=100.0, low_1=95.0, low_2=90.0)]
        )
        result = self.analyzer.analyze(context)
        self.assertEqual(result.metadata["swing_high"]["classification"], "equal_high")

    def test_equal_swing_low_is_equal_low(self):
        context = make_context(
            [swing_points(high_1=110.0, high_2=100.0, low_1=90.0, low_2=90.0)]
        )
        result = self.analyzer.analyze(context)
        self.assertEqual(result.metadata["swing_low"]["classification"], "equal_low")

    def test_swing_high_and_low_values_reported_in_metadata(self):
        context = make_context(
            [swing_points(high_1=110.0, high_2=100.0, low_1=95.0, low_2=90.0)]
        )
        result = self.analyzer.analyze(context)
        self.assertEqual(result.metadata["swing_high"]["value"], 110.0)
        self.assertEqual(result.metadata["swing_high"]["previous"], 100.0)
        self.assertEqual(result.metadata["swing_low"]["value"], 95.0)
        self.assertEqual(result.metadata["swing_low"]["previous"], 90.0)


# ----------------------------------------------------------------------
# BOS / CHOCH
# ----------------------------------------------------------------------
class TestStructureBreak(unittest.TestCase):
    def setUp(self):
        self.analyzer = MarketStructureAnalyzer()

    def test_bullish_bos_when_bullish_bias_and_price_breaks_above_swing_high(self):
        context = make_context(
            [swing_points(high_1=110.0, high_2=100.0, low_1=95.0, low_2=90.0)],
            make_candle(close=115.0),
        )
        result = self.analyzer.analyze(context)
        self.assertTrue(result.metadata["bos"]["detected"])
        self.assertEqual(result.metadata["bos"]["direction"], "bullish")
        self.assertFalse(result.metadata["choch"]["detected"])
        self.assertEqual(result.metadata["trend_continuation"], 1.0)
        self.assertEqual(result.metadata["trend_reversal"], 0.0)
        self.assertAlmostEqual(result.score, 1.0)

    def test_bearish_bos_when_bearish_bias_and_price_breaks_below_swing_low(self):
        context = make_context(
            [swing_points(high_1=95.0, high_2=100.0, low_1=80.0, low_2=90.0)],
            make_candle(close=70.0),
        )
        result = self.analyzer.analyze(context)
        self.assertTrue(result.metadata["bos"]["detected"])
        self.assertEqual(result.metadata["bos"]["direction"], "bearish")
        self.assertFalse(result.metadata["choch"]["detected"])
        self.assertEqual(result.metadata["trend_continuation"], 1.0)
        self.assertAlmostEqual(result.score, -1.0)

    def test_bullish_choch_when_bearish_bias_and_price_breaks_above_swing_high(self):
        context = make_context(
            [swing_points(high_1=95.0, high_2=100.0, low_1=80.0, low_2=90.0)],
            make_candle(close=99.0),
        )
        result = self.analyzer.analyze(context)
        self.assertFalse(result.metadata["bos"]["detected"])
        self.assertTrue(result.metadata["choch"]["detected"])
        self.assertEqual(result.metadata["choch"]["direction"], "bullish")
        self.assertEqual(result.metadata["trend_continuation"], 0.0)
        self.assertEqual(result.metadata["trend_reversal"], 1.0)
        self.assertGreater(result.score, 0.0)

    def test_bearish_choch_when_bullish_bias_and_price_breaks_below_swing_low(self):
        context = make_context(
            [swing_points(high_1=110.0, high_2=100.0, low_1=95.0, low_2=90.0)],
            make_candle(close=80.0),
        )
        result = self.analyzer.analyze(context)
        self.assertFalse(result.metadata["bos"]["detected"])
        self.assertTrue(result.metadata["choch"]["detected"])
        self.assertEqual(result.metadata["choch"]["direction"], "bearish")
        self.assertEqual(result.metadata["trend_reversal"], 1.0)
        self.assertLess(result.score, 0.0)

    def test_no_break_when_price_within_swing_range(self):
        context = make_context(
            [swing_points(high_1=110.0, high_2=100.0, low_1=95.0, low_2=90.0)],
            make_candle(close=105.0),
        )
        result = self.analyzer.analyze(context)
        self.assertFalse(result.metadata["bos"]["detected"])
        self.assertFalse(result.metadata["choch"]["detected"])
        self.assertEqual(result.metadata["trend_continuation"], 0.6)
        self.assertEqual(result.metadata["trend_reversal"], 0.2)

    def test_no_break_without_candle(self):
        context = make_context(
            [swing_points(high_1=110.0, high_2=100.0, low_1=95.0, low_2=90.0)]
        )
        result = self.analyzer.analyze(context)
        self.assertFalse(result.metadata["bos"]["detected"])
        self.assertFalse(result.metadata["choch"]["detected"])

    def test_mixed_bias_without_break_leans_toward_reversal(self):
        context = make_context(
            [swing_points(high_1=110.0, high_2=100.0, low_1=80.0, low_2=90.0)],
            make_candle(close=100.0),
        )
        result = self.analyzer.analyze(context)
        self.assertEqual(result.metadata["trend_continuation"], 0.2)
        self.assertEqual(result.metadata["trend_reversal"], 0.5)


# ----------------------------------------------------------------------
# Confidence / completeness
# ----------------------------------------------------------------------
class TestConfidence(unittest.TestCase):
    def setUp(self):
        self.analyzer = MarketStructureAnalyzer()

    def test_confidence_lower_with_only_one_pair_present(self):
        full_context = make_context(
            [swing_points(high_1=110.0, high_2=100.0, low_1=95.0, low_2=90.0)],
            make_candle(close=115.0),
        )
        partial_context = make_context([swing_points(high_1=110.0, high_2=100.0)])
        full_result = self.analyzer.analyze(full_context)
        partial_result = self.analyzer.analyze(partial_context)
        self.assertLess(partial_result.confidence, full_result.confidence)

    def test_mixed_bias_reduces_confidence_via_bias_clarity(self):
        clean_context = make_context(
            [swing_points(high_1=110.0, high_2=100.0, low_1=95.0, low_2=90.0)]
        )
        mixed_context = make_context(
            [swing_points(high_1=110.0, high_2=100.0, low_1=80.0, low_2=90.0)]
        )
        clean_result = self.analyzer.analyze(clean_context)
        mixed_result = self.analyzer.analyze(mixed_context)
        self.assertEqual(mixed_result.metadata["bias_clarity"], 0.5)
        self.assertEqual(clean_result.metadata["bias_clarity"], 1.0)
        self.assertLess(mixed_result.confidence, clean_result.confidence)

    def test_components_used_lists_only_computed_components(self):
        context = make_context([swing_points(high_1=110.0, high_2=100.0)])
        result = self.analyzer.analyze(context)
        self.assertEqual(result.metadata["components_used"], ["high_structure"])


# ----------------------------------------------------------------------
# Custom indicator name / constructor
# ----------------------------------------------------------------------
class TestConfiguration(unittest.TestCase):
    def test_custom_swing_points_name_is_used(self):
        analyzer = MarketStructureAnalyzer(swing_points_name="CustomSwingPoints")
        context = make_context(
            [swing_points(high_1=110.0, high_2=100.0, low_1=95.0, low_2=90.0, name="CustomSwingPoints")]
        )
        result = analyzer.analyze(context)
        self.assertEqual(result.metadata["structure_bias"], "bullish")

    def test_custom_swing_points_name_ignores_default_named_indicator(self):
        analyzer = MarketStructureAnalyzer(swing_points_name="CustomSwingPoints")
        context = make_context(
            [swing_points(high_1=110.0, high_2=100.0, low_1=95.0, low_2=90.0)]  # default name
        )
        with self.assertRaises(InsufficientDataError):
            analyzer.analyze(context)

    def test_default_name_is_class_name(self):
        analyzer = MarketStructureAnalyzer()
        self.assertEqual(analyzer.name, "MarketStructureAnalyzer")

    def test_custom_name_is_used_in_result(self):
        analyzer = MarketStructureAnalyzer(name="CustomStructure")
        context = make_context([swing_points(high_1=110.0, high_2=100.0)])
        result = analyzer.analyze(context)
        self.assertEqual(result.analyzer_name, "CustomStructure")


if __name__ == "__main__":
    unittest.main()
