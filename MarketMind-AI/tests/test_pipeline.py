"""
test_pipeline.py
-------------------
Purpose:
    Unit tests for the first `app/`-layer use case: `MarketPipeline`
    (`app/pipeline.py`), which wires Data -> Indicators -> Analysis ->
    Signals for one symbol/timeframe.

Uses the standard-library ``unittest`` framework and the shared
`FakeBinanceClient` from `tests/helpers.py` (no real network access),
matching every other test suite in this repository.

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import os
import tempfile
import unittest

from tests.helpers import make_fake_client

from analysis.aggregator import AnalysisAggregator
from analysis.base import BaseAnalyzer
from analysis.exceptions import InsufficientDataError
from analysis.result import AnalysisResult

from core.entities.indicator_result import IndicatorResult
from core.entities.market_state import MarketState

from data.engine import DataEngine

from signals.base import BaseSignalGenerator
from signals.context import SignalContext
from signals.exceptions import InsufficientSignalDataError
from signals.result import SignalResult
from signals.aggregator import SignalAggregator

from core.enums import SignalDirection

from app.exceptions import (
    PipelineAnalysisError,
    PipelineConfigurationError,
    PipelineDataError,
    PipelineSignalError,
)
from app.pipeline import MarketPipeline, PipelineResult


class _AlwaysFailingAnalyzer(BaseAnalyzer):
    """Test double: always raises InsufficientDataError."""

    def analyze(self, context) -> AnalysisResult:
        raise InsufficientDataError("no data, by design")


class _AlwaysFailingSignalGenerator(BaseSignalGenerator):
    """Test double: always raises InsufficientSignalDataError."""

    def generate(self, context: SignalContext) -> SignalResult:
        raise InsufficientSignalDataError("no signal, by design")


class TestMarketPipeline(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.remove(self.db_path)
        self.fake_client = make_fake_client(num_candles=200, timeframe="1h")
        self.engine = DataEngine(client=self.fake_client, db_path=self.db_path)
        self.engine.download_history(
            symbol="BTCUSDT",
            timeframe="1h",
            start_time=self.fake_client.series_start,
            batch_limit=200,
        )

    def tearDown(self):
        self.engine.close()
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                os.remove(path)

    # ------------------------------------------------------------------
    # Construction / dependency injection
    # ------------------------------------------------------------------
    def test_construction_defaults(self):
        pipeline = MarketPipeline(self.engine)
        self.assertIsInstance(pipeline.analyzer, AnalysisAggregator)
        self.assertIsInstance(pipeline.signal_generator, SignalAggregator)
        self.assertTrue(len(pipeline.indicator_specs) > 0)

    def test_construction_rejects_non_data_engine(self):
        with self.assertRaises(PipelineConfigurationError):
            MarketPipeline(data_engine="not-an-engine")

    def test_construction_rejects_non_analyzer(self):
        with self.assertRaises(PipelineConfigurationError):
            MarketPipeline(self.engine, analyzer=object())

    def test_construction_rejects_non_signal_generator(self):
        with self.assertRaises(PipelineConfigurationError):
            MarketPipeline(self.engine, signal_generator=object())

    def test_construction_rejects_bad_indicator_specs(self):
        with self.assertRaises(PipelineConfigurationError):
            MarketPipeline(self.engine, indicator_specs=[(object(), {})])

    def test_construction_accepts_injected_analyzer_and_generator(self):
        analyzer = AnalysisAggregator()
        generator = SignalAggregator()
        pipeline = MarketPipeline(self.engine, analyzer=analyzer, signal_generator=generator)
        self.assertIs(pipeline.analyzer, analyzer)
        self.assertIs(pipeline.signal_generator, generator)

    # ------------------------------------------------------------------
    # run() input validation
    # ------------------------------------------------------------------
    def test_run_rejects_empty_symbol(self):
        pipeline = MarketPipeline(self.engine)
        with self.assertRaises(PipelineConfigurationError):
            pipeline.run("", "1h")

    def test_run_rejects_empty_timeframe(self):
        pipeline = MarketPipeline(self.engine)
        with self.assertRaises(PipelineConfigurationError):
            pipeline.run("BTCUSDT", "")

    def test_run_raises_pipeline_data_error_when_no_history(self):
        pipeline = MarketPipeline(self.engine)
        with self.assertRaises(PipelineDataError):
            pipeline.run("ETHUSDT", "1h")

    # ------------------------------------------------------------------
    # End-to-end happy path
    # ------------------------------------------------------------------
    def test_run_end_to_end(self):
        pipeline = MarketPipeline(self.engine)
        result = pipeline.run("btcusdt", "1h")

        self.assertIsInstance(result, PipelineResult)
        self.assertEqual(result.symbol, "BTCUSDT")
        self.assertEqual(result.timeframe, "1h")
        self.assertEqual(result.candle_count, 200)

        # Data stage
        self.assertIsInstance(result.market_state, MarketState)
        self.assertIsNotNone(result.market_state.latest_candle)

        # Indicators stage: with 200 candles every default indicator
        # (max warm-up requirement: SMA_50) should compute cleanly.
        self.assertEqual(result.indicator_errors, {})
        self.assertGreater(len(result.indicator_results), 0)
        for indicator_result in result.indicator_results:
            self.assertIsInstance(indicator_result, IndicatorResult)
            self.assertEqual(indicator_result.symbol, "BTCUSDT")
            self.assertEqual(indicator_result.timeframe, "1h")
        names = {ir.indicator_name for ir in result.indicator_results}
        self.assertIn("SMA_20", names)
        self.assertIn("SMA_50", names)
        self.assertIn("MACD_12_26_9", names)
        self.assertIn("RSI_14", names)

        # Analysis stage
        self.assertIsInstance(result.analysis_result, AnalysisResult)
        self.assertEqual(result.analysis_result.symbol, "BTCUSDT")

        # Signals stage
        self.assertIsInstance(result.signal_result, SignalResult)
        self.assertIn(
            result.signal_result.direction,
            (SignalDirection.BUY, SignalDirection.SELL, SignalDirection.HOLD),
        )

    def test_run_respects_limit(self):
        pipeline = MarketPipeline(self.engine)
        result = pipeline.run("BTCUSDT", "1h", limit=60)
        self.assertEqual(result.candle_count, 60)

    def test_run_records_indicator_errors_without_failing_pipeline(self):
        # Too little history for SMA_50 (needs >= 50 points) but enough
        # for shorter-period indicators -- the pipeline should still
        # reach Analysis/Signals, recording the failure instead of
        # raising.
        fd, db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.remove(db_path)
        client = make_fake_client(num_candles=30, timeframe="1h")
        engine = DataEngine(client=client, db_path=db_path)
        try:
            engine.download_history(
                symbol="BTCUSDT", timeframe="1h", start_time=client.series_start, batch_limit=30
            )
            pipeline = MarketPipeline(engine)
            result = pipeline.run("BTCUSDT", "1h")
            self.assertIn("SMA_50", result.indicator_errors)
            self.assertIsInstance(result.analysis_result, AnalysisResult)
        finally:
            engine.close()
            for suffix in ("", "-wal", "-shm"):
                path = db_path + suffix
                if os.path.exists(path):
                    os.remove(path)

    # ------------------------------------------------------------------
    # Stage failure propagation
    # ------------------------------------------------------------------
    def test_run_wraps_analysis_failure(self):
        pipeline = MarketPipeline(self.engine, analyzer=_AlwaysFailingAnalyzer())
        with self.assertRaises(PipelineAnalysisError):
            pipeline.run("BTCUSDT", "1h")

    def test_run_wraps_signal_failure(self):
        pipeline = MarketPipeline(self.engine, signal_generator=_AlwaysFailingSignalGenerator())
        with self.assertRaises(PipelineSignalError):
            pipeline.run("BTCUSDT", "1h")


if __name__ == "__main__":
    unittest.main()
