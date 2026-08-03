"""
test_analysis.py
-------------------
Purpose:
    Unit tests for the Analysis Engine foundation (Part 1):
    `AnalysisResult`, `AnalysisContext`, `BaseAnalyzer`, and the
    `analysis.exceptions` / `analysis.utils` helpers.

Uses the standard-library ``unittest`` framework, matching the
`indicators`/`data` test suites (no external test-runner dependency).

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from analysis import (
    AnalysisContext,
    AnalysisError,
    AnalysisResult,
    AnalysisValidationError,
    AnalyzerConfigurationError,
    BaseAnalyzer,
    InsufficientDataError,
    InvalidAnalysisContextError,
)
from analysis.utils import merge_metadata, validate_confidence, validate_score
from core.entities.indicator_result import IndicatorResult
from core.entities.market_state import MarketState
from core.entities.news_item import NewsItem

NOW = datetime.now(timezone.utc)


def make_market_state(symbol: str = "BTCUSDT", timeframe: str = "1h") -> MarketState:
    return MarketState(symbol=symbol, timeframe=timeframe, timestamp=NOW)


def make_indicator(name: str = "RSI", *, value: float = 55.0) -> IndicatorResult:
    return IndicatorResult(
        indicator_name=name,
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=NOW,
        values={"value": value},
    )


def make_news(news_id: str = "n1") -> NewsItem:
    return NewsItem(
        news_id=news_id,
        source="TestWire",
        title="Headline",
        url="https://example.com",
        published_at=NOW,
    )


# ----------------------------------------------------------------------
# AnalysisResult
# ----------------------------------------------------------------------
class TestAnalysisResult(unittest.TestCase):
    def test_instantiates_with_required_fields(self):
        result = AnalysisResult(
            analyzer_name="TestAnalyzer",
            symbol="BTCUSDT",
            timeframe="1h",
            score=0.5,
            confidence=0.8,
            summary="Neutral market",
        )
        self.assertEqual(result.analyzer_name, "TestAnalyzer")
        self.assertEqual(result.symbol, "BTCUSDT")
        self.assertEqual(result.timeframe, "1h")
        self.assertEqual(result.score, 0.5)
        self.assertEqual(result.confidence, 0.8)
        self.assertEqual(result.summary, "Neutral market")
        self.assertEqual(result.metadata, {})
        self.assertIsInstance(result.timestamp, datetime)

    def test_metadata_and_timestamp_are_settable(self):
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        result = AnalysisResult(
            analyzer_name="TestAnalyzer",
            symbol="BTCUSDT",
            timeframe="1h",
            score=1.0,
            confidence=1.0,
            summary="Strong bullish",
            timestamp=ts,
            metadata={"rsi": 70},
        )
        self.assertEqual(result.timestamp, ts)
        self.assertEqual(result.metadata, {"rsi": 70})

    def test_is_frozen(self):
        result = AnalysisResult(
            analyzer_name="TestAnalyzer",
            symbol="BTCUSDT",
            timeframe="1h",
            score=0.0,
            confidence=0.5,
            summary="Neutral",
        )
        with self.assertRaises(Exception):
            result.score = 1.0  # type: ignore[misc]

    def test_with_metadata_returns_new_instance(self):
        original = AnalysisResult(
            analyzer_name="TestAnalyzer",
            symbol="BTCUSDT",
            timeframe="1h",
            score=0.0,
            confidence=0.5,
            summary="Neutral",
            metadata={"a": 1},
        )
        updated = original.with_metadata(b=2)
        self.assertEqual(original.metadata, {"a": 1})
        self.assertEqual(updated.metadata, {"a": 1, "b": 2})
        self.assertIsNot(original, updated)

    def test_rejects_empty_analyzer_name(self):
        with self.assertRaises(AnalysisValidationError):
            AnalysisResult(
                analyzer_name="  ",
                symbol="BTCUSDT",
                timeframe="1h",
                score=0.0,
                confidence=0.5,
                summary="Neutral",
            )

    def test_rejects_empty_symbol(self):
        with self.assertRaises(AnalysisValidationError):
            AnalysisResult(
                analyzer_name="TestAnalyzer",
                symbol="",
                timeframe="1h",
                score=0.0,
                confidence=0.5,
                summary="Neutral",
            )

    def test_rejects_empty_summary(self):
        with self.assertRaises(AnalysisValidationError):
            AnalysisResult(
                analyzer_name="TestAnalyzer",
                symbol="BTCUSDT",
                timeframe="1h",
                score=0.0,
                confidence=0.5,
                summary="",
            )

    def test_rejects_non_numeric_score(self):
        with self.assertRaises(AnalysisValidationError):
            AnalysisResult(
                analyzer_name="TestAnalyzer",
                symbol="BTCUSDT",
                timeframe="1h",
                score="high",  # type: ignore[arg-type]
                confidence=0.5,
                summary="Neutral",
            )

    def test_rejects_non_finite_score(self):
        with self.assertRaises(AnalysisValidationError):
            AnalysisResult(
                analyzer_name="TestAnalyzer",
                symbol="BTCUSDT",
                timeframe="1h",
                score=float("nan"),
                confidence=0.5,
                summary="Neutral",
            )

    def test_rejects_confidence_out_of_range(self):
        with self.assertRaises(AnalysisValidationError):
            AnalysisResult(
                analyzer_name="TestAnalyzer",
                symbol="BTCUSDT",
                timeframe="1h",
                score=0.0,
                confidence=1.5,
                summary="Neutral",
            )

    def test_rejects_negative_confidence(self):
        with self.assertRaises(AnalysisValidationError):
            AnalysisResult(
                analyzer_name="TestAnalyzer",
                symbol="BTCUSDT",
                timeframe="1h",
                score=0.0,
                confidence=-0.1,
                summary="Neutral",
            )

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(TypeError):
            AnalysisResult(
                analyzer_name="TestAnalyzer",
                symbol="BTCUSDT",
                timeframe="1h",
                score=0.0,
                confidence=0.5,
                summary="Neutral",
                metadata=["not", "a", "dict"],  # type: ignore[arg-type]
            )


# ----------------------------------------------------------------------
# AnalysisContext
# ----------------------------------------------------------------------
class TestAnalysisContext(unittest.TestCase):
    def test_instantiates_with_minimal_fields(self):
        context = AnalysisContext(
            symbol="BTCUSDT", timeframe="1h", market_state=make_market_state()
        )
        self.assertEqual(context.symbol, "BTCUSDT")
        self.assertEqual(context.timeframe, "1h")
        self.assertEqual(context.indicators, [])
        self.assertEqual(context.news, [])
        self.assertFalse(context.has_news())

    def test_holds_indicators_and_news_collections(self):
        rsi = make_indicator("RSI", value=70.0)
        macd = make_indicator("MACD", value=1.2)
        news_item = make_news()
        context = AnalysisContext(
            symbol="BTCUSDT",
            timeframe="1h",
            market_state=make_market_state(),
            indicators=[rsi, macd],
            news=[news_item],
        )
        self.assertEqual(len(context.indicators), 2)
        self.assertIn(rsi, context.indicators)
        self.assertEqual(context.news, [news_item])
        self.assertTrue(context.has_news())

    def test_get_indicator_returns_match(self):
        rsi = make_indicator("RSI", value=42.0)
        context = AnalysisContext(
            symbol="BTCUSDT",
            timeframe="1h",
            market_state=make_market_state(),
            indicators=[rsi],
        )
        found = context.get_indicator("RSI")
        self.assertIs(found, rsi)

    def test_get_indicator_returns_none_when_missing(self):
        context = AnalysisContext(
            symbol="BTCUSDT", timeframe="1h", market_state=make_market_state()
        )
        self.assertIsNone(context.get_indicator("RSI"))

    def test_rejects_empty_symbol(self):
        with self.assertRaises(InvalidAnalysisContextError):
            AnalysisContext(symbol="", timeframe="1h", market_state=make_market_state())

    def test_rejects_empty_timeframe(self):
        with self.assertRaises(InvalidAnalysisContextError):
            AnalysisContext(symbol="BTCUSDT", timeframe="", market_state=make_market_state())

    def test_rejects_non_market_state(self):
        with self.assertRaises(InvalidAnalysisContextError):
            AnalysisContext(symbol="BTCUSDT", timeframe="1h", market_state="not-a-market-state")  # type: ignore[arg-type]

    def test_rejects_indicators_not_a_list(self):
        with self.assertRaises(InvalidAnalysisContextError):
            AnalysisContext(
                symbol="BTCUSDT",
                timeframe="1h",
                market_state=make_market_state(),
                indicators=make_indicator(),  # type: ignore[arg-type]
            )

    def test_rejects_indicators_with_wrong_item_type(self):
        with self.assertRaises(InvalidAnalysisContextError):
            AnalysisContext(
                symbol="BTCUSDT",
                timeframe="1h",
                market_state=make_market_state(),
                indicators=["not-an-indicator-result"],  # type: ignore[list-item]
            )

    def test_rejects_news_with_wrong_item_type(self):
        with self.assertRaises(InvalidAnalysisContextError):
            AnalysisContext(
                symbol="BTCUSDT",
                timeframe="1h",
                market_state=make_market_state(),
                news=["not-a-news-item"],  # type: ignore[list-item]
            )

    def test_is_frozen(self):
        context = AnalysisContext(
            symbol="BTCUSDT", timeframe="1h", market_state=make_market_state()
        )
        with self.assertRaises(Exception):
            context.symbol = "ETHUSDT"  # type: ignore[misc]


# ----------------------------------------------------------------------
# BaseAnalyzer
# ----------------------------------------------------------------------
class _AlwaysNeutralAnalyzer(BaseAnalyzer):
    """Minimal concrete analyzer used to exercise `BaseAnalyzer`."""

    def analyze(self, context: AnalysisContext) -> AnalysisResult:
        self.validate_context(context)
        rsi = context.get_indicator("RSI")
        if rsi is None:
            raise InsufficientDataError("RSI indicator is required")
        return self._build_result(
            context,
            score=0.0,
            confidence=0.5,
            summary="Neutral (stub analyzer)",
            metadata={"rsi_value": rsi.values.get("value")},
        )


class TestBaseAnalyzer(unittest.TestCase):
    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            BaseAnalyzer()  # type: ignore[abstract]

    def test_default_name_is_class_name(self):
        analyzer = _AlwaysNeutralAnalyzer()
        self.assertEqual(analyzer.name, "_AlwaysNeutralAnalyzer")

    def test_custom_name_is_used(self):
        analyzer = _AlwaysNeutralAnalyzer(name="CustomAnalyzer")
        self.assertEqual(analyzer.name, "CustomAnalyzer")

    def test_analyze_produces_result_bound_to_context(self):
        analyzer = _AlwaysNeutralAnalyzer(name="CustomAnalyzer")
        context = AnalysisContext(
            symbol="BTCUSDT",
            timeframe="1h",
            market_state=make_market_state(),
            indicators=[make_indicator("RSI", value=65.0)],
        )
        result = analyzer.analyze(context)
        self.assertIsInstance(result, AnalysisResult)
        self.assertEqual(result.analyzer_name, "CustomAnalyzer")
        self.assertEqual(result.symbol, "BTCUSDT")
        self.assertEqual(result.timeframe, "1h")
        self.assertEqual(result.metadata, {"rsi_value": 65.0})

    def test_analyze_raises_insufficient_data_when_indicator_missing(self):
        analyzer = _AlwaysNeutralAnalyzer()
        context = AnalysisContext(
            symbol="BTCUSDT", timeframe="1h", market_state=make_market_state()
        )
        with self.assertRaises(InsufficientDataError):
            analyzer.analyze(context)

    def test_validate_context_rejects_non_context(self):
        analyzer = _AlwaysNeutralAnalyzer()
        with self.assertRaises(InvalidAnalysisContextError):
            analyzer.validate_context("not-a-context")  # type: ignore[arg-type]

    def test_repr_contains_name(self):
        analyzer = _AlwaysNeutralAnalyzer(name="CustomAnalyzer")
        self.assertIn("CustomAnalyzer", repr(analyzer))


# ----------------------------------------------------------------------
# analysis.exceptions hierarchy
# ----------------------------------------------------------------------
class TestExceptionHierarchy(unittest.TestCase):
    def test_all_exceptions_derive_from_analysis_error(self):
        for exc_type in (
            AnalysisValidationError,
            InvalidAnalysisContextError,
            InsufficientDataError,
            AnalyzerConfigurationError,
        ):
            self.assertTrue(issubclass(exc_type, AnalysisError))

    def test_invalid_context_error_derives_from_validation_error(self):
        self.assertTrue(issubclass(InvalidAnalysisContextError, AnalysisValidationError))

    def test_analysis_error_derives_from_exception(self):
        self.assertTrue(issubclass(AnalysisError, Exception))


# ----------------------------------------------------------------------
# analysis.utils
# ----------------------------------------------------------------------
class TestUtils(unittest.TestCase):
    def test_validate_score_accepts_int_and_float(self):
        self.assertEqual(validate_score(1), 1.0)
        self.assertEqual(validate_score(-0.75), -0.75)

    def test_validate_score_rejects_bool(self):
        with self.assertRaises(AnalysisValidationError):
            validate_score(True)

    def test_validate_score_rejects_non_numeric(self):
        with self.assertRaises(AnalysisValidationError):
            validate_score("1.0")

    def test_validate_score_rejects_infinite(self):
        with self.assertRaises(AnalysisValidationError):
            validate_score(float("inf"))

    def test_validate_confidence_accepts_bounds(self):
        self.assertEqual(validate_confidence(0.0), 0.0)
        self.assertEqual(validate_confidence(1.0), 1.0)

    def test_validate_confidence_rejects_out_of_bounds(self):
        with self.assertRaises(AnalysisValidationError):
            validate_confidence(1.01)
        with self.assertRaises(AnalysisValidationError):
            validate_confidence(-0.01)

    def test_merge_metadata_merges_left_to_right(self):
        merged = merge_metadata({"a": 1}, {"b": 2}, {"a": 3})
        self.assertEqual(merged, {"a": 3, "b": 2})

    def test_merge_metadata_skips_none(self):
        merged = merge_metadata(None, {"a": 1}, None)
        self.assertEqual(merged, {"a": 1})

    def test_merge_metadata_with_no_sources_returns_empty_dict(self):
        self.assertEqual(merge_metadata(), {})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
