"""
test_backtest_runner.py
-------------------------
Purpose:
    Unit tests for the second `app/`-layer use case: `BacktestRunner`
    (`app/backtest_runner.py`), which wires
    Data -> Indicators -> Analysis -> Signals -> Strategy ->
    Backtesting -> Metrics -> Report for one symbol/timeframe.

Uses the standard-library ``unittest`` framework and the shared
`make_fake_client` helper from `tests/helpers.py` (no real network
access), matching every other test suite in this repository.

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import os
import tempfile
import unittest
from decimal import Decimal

from tests.helpers import make_fake_client

from analysis.aggregator import AnalysisAggregator
from analysis.base import BaseAnalyzer
from analysis.context import AnalysisContext
from analysis.exceptions import InsufficientDataError
from analysis.result import AnalysisResult

from core.entities.portfolio import Portfolio
from core.enums import SignalDirection

from data.engine import DataEngine

from signals.aggregator import SignalAggregator
from signals.base import BaseSignalGenerator
from signals.context import SignalContext
from signals.exceptions import InsufficientSignalDataError
from signals.result import SignalResult

from strategies.base_strategy import BaseStrategy
from strategies.basic_strategy import BasicStrategy
from strategies.context import StrategyContext
from strategies.exceptions import InsufficientStrategyDataError
from strategies.result import StrategyResult

from backtesting.base import BaseBacktester
from backtesting.basic_backtester import BasicBacktester
from backtesting.metrics import BacktestMetrics
from backtesting.report import BacktestReport
from backtesting.result import BacktestResult

from app.backtest_runner import (
    DEFAULT_BASE_CURRENCY,
    DEFAULT_INITIAL_CASH_BALANCE,
    BacktestRunner,
    BacktestRunResult,
    StrategyComparisonEntry,
    StrategyComparisonResult,
    WalkForwardResult,
    WalkForwardSummary,
    WalkForwardWindow,
)
from app.exceptions import (
    BacktestRunnerConfigurationError,
    BacktestRunnerDataError,
    BacktestRunnerExecutionError,
)


class _AlwaysBuyStrategy(BaseStrategy):
    """Test double: always decides BUY, regardless of context -- proves real trade execution end-to-end."""

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        return self._build_result(
            action=SignalDirection.BUY,
            confidence=1.0,
            summary="always buy, by design",
        )


class _AlwaysHoldStrategy(BaseStrategy):
    """Test double: always decides HOLD -- zero trades, zero return, used as a comparison baseline."""

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        return self._build_result(
            action=SignalDirection.HOLD,
            confidence=1.0,
            summary="always hold, by design",
        )


class _BuyOnFirstCandleThenSellStrategy(BaseStrategy):
    """
    Test double: BUYs on the very first candle, SELLs on the very next
    one, then HOLDs forever -- against the deterministic, steadily-
    rising synthetic price series `tests.helpers.FakeBinanceClient`
    produces, this closes one profitable round trip, giving this
    strategy a genuinely positive `total_return` distinct from a
    strategy that never trades or that buys and holds (see
    `BasicMetrics.total_return`'s reliance on *closed* positions'
    realized PnL) -- used to prove `compare_strategies()` actually
    sorts by total return rather than just preserving input order.
    """

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        candle_index = context.metadata.get("candle_index")
        if candle_index == 0:
            action = SignalDirection.BUY
        elif candle_index == 1:
            action = SignalDirection.SELL
        else:
            action = SignalDirection.HOLD
        return self._build_result(
            action=action,
            confidence=1.0,
            summary="buy on the first candle, sell on the next, by design",
        )


class _AlwaysFailingStrategy(BaseStrategy):
    """Test double: always raises InsufficientStrategyDataError."""

    def decide(self, context: StrategyContext) -> StrategyResult:
        raise InsufficientStrategyDataError("no data, by design")


class _AlwaysFailingBacktester(BaseBacktester):
    """Test double: always raises a BacktestError subclass from run()."""

    def run(self, context):
        from backtesting.exceptions import InsufficientBacktestDataError

        raise InsufficientBacktestDataError("no data, by design")


class _AlwaysFailingAnalyzer(BaseAnalyzer):
    """Test double: always raises InsufficientDataError -- proves a failed Analysis stage never aborts the whole run."""

    def analyze(self, context: AnalysisContext) -> AnalysisResult:
        raise InsufficientDataError("no data, by design")


class _RequiresAnalysisResultStrategy(BaseStrategy):
    """
    Test double: BUYs only when `StrategyContext.has_analysis_results()`
    is true, otherwise raises `InsufficientStrategyDataError` -- proves
    `BacktestRunner` genuinely runs its own Analysis stage and feeds a
    real `AnalysisResult` into every candle's `StrategyContext`, rather
    than an always-empty one.
    """

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        if not context.has_analysis_results():
            raise InsufficientStrategyDataError("no AnalysisResult available, by design")
        return self._build_result(
            action=SignalDirection.BUY,
            confidence=1.0,
            summary="analysis result was present",
        )


class _RequiresSignalResultStrategy(BaseStrategy):
    """
    Test double: BUYs only when `StrategyContext.has_signal_result()` is
    true, otherwise raises `InsufficientStrategyDataError` -- proves
    `BacktestRunner` genuinely runs its own Signal stage and feeds a
    real `SignalResult` into every candle's `StrategyContext`.
    """

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        if not context.has_signal_result():
            raise InsufficientStrategyDataError("no SignalResult available, by design")
        return self._build_result(
            action=SignalDirection.BUY,
            confidence=1.0,
            summary="signal result was present",
        )


class BaseBacktestRunnerTest(unittest.TestCase):
    """Shared fixture: a DataEngine with 200 candles of BTCUSDT/1h history."""

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
        if os.path.exists(self.db_path):
            os.remove(self.db_path)


class TestBacktestRunnerConstruction(BaseBacktestRunnerTest):
    def test_construction_with_defaults(self):
        runner = BacktestRunner(self.engine)
        self.assertIs(runner.data_engine, self.engine)
        self.assertIsInstance(runner.backtester, BasicBacktester)
        self.assertIsInstance(runner.analyzer, AnalysisAggregator)
        self.assertIsInstance(runner.signal_generator, SignalAggregator)
        self.assertGreater(len(runner.indicator_specs), 0)

    def test_construction_with_injected_backtester(self):
        backtester = BasicBacktester(name="custom")
        runner = BacktestRunner(self.engine, backtester=backtester)
        self.assertIs(runner.backtester, backtester)

    def test_construction_with_injected_analyzer(self):
        analyzer = AnalysisAggregator(name="custom-analyzer")
        runner = BacktestRunner(self.engine, analyzer=analyzer)
        self.assertIs(runner.analyzer, analyzer)

    def test_construction_with_injected_signal_generator(self):
        signal_generator = SignalAggregator(name="custom-signals")
        runner = BacktestRunner(self.engine, signal_generator=signal_generator)
        self.assertIs(runner.signal_generator, signal_generator)

    def test_construction_with_injected_indicator_specs(self):
        runner = BacktestRunner(self.engine, indicator_specs=[])
        self.assertEqual(runner.indicator_specs, [])

    def test_rejects_non_data_engine(self):
        with self.assertRaises(BacktestRunnerConfigurationError):
            BacktestRunner(object())

    def test_rejects_non_base_backtester(self):
        with self.assertRaises(BacktestRunnerConfigurationError):
            BacktestRunner(self.engine, backtester=object())

    def test_rejects_non_base_analyzer(self):
        with self.assertRaises(BacktestRunnerConfigurationError):
            BacktestRunner(self.engine, analyzer=object())

    def test_rejects_non_base_signal_generator(self):
        with self.assertRaises(BacktestRunnerConfigurationError):
            BacktestRunner(self.engine, signal_generator=object())

    def test_rejects_malformed_indicator_specs(self):
        with self.assertRaises(BacktestRunnerConfigurationError):
            BacktestRunner(self.engine, indicator_specs=[(object(), {})])


class TestBacktestRunnerRun(BaseBacktestRunnerTest):
    def test_run_with_defaults_returns_full_result(self):
        runner = BacktestRunner(self.engine)
        run_result = runner.run("BTCUSDT", "1h")

        self.assertIsInstance(run_result, BacktestRunResult)
        self.assertEqual(run_result.symbol, "BTCUSDT")
        self.assertEqual(run_result.timeframe, "1h")
        self.assertEqual(run_result.candle_count, 200)
        self.assertIsInstance(run_result.initial_portfolio, Portfolio)
        self.assertIsInstance(run_result.result, BacktestResult)
        self.assertIsInstance(run_result.metrics, BacktestMetrics)
        self.assertIsInstance(run_result.report, BacktestReport)

    def test_symbol_is_uppercased(self):
        runner = BacktestRunner(self.engine)
        run_result = runner.run("btcusdt", "1h")
        self.assertEqual(run_result.symbol, "BTCUSDT")

    def test_default_strategy_is_basic_strategy(self):
        # Unlike calling BasicBacktester directly (which never supplies
        # an AnalysisResult of its own -- see
        # tests/test_basic_backtester.py's TestRealBasicStrategyIntegration),
        # BacktestRunner now runs its own Analysis -> Signal stages for
        # every historical candle before calling BasicStrategy.decide(),
        # so a real AnalysisResult/SignalResult is genuinely available.
        # BasicStrategy's entry filters (EMA50/EMA200, ADX, ATR expansion)
        # are mandatory for any BUY, and BacktestRunner's pipeline never
        # populates StrategyContext.metadata["indicators"], so every
        # would-be BUY correctly fails closed to HOLD for lack of that
        # data -- zero trades, not zero strategy results.
        runner = BacktestRunner(self.engine)
        run_result = runner.run("BTCUSDT", "1h")
        self.assertEqual(run_result.result.trade_count(), 0)
        self.assertEqual(run_result.result.metadata.get("skipped_candles"), 0)
        self.assertEqual(run_result.metadata["candles_with_strategy_result"], 200)

    def test_injected_strategy_actually_trades(self):
        runner = BacktestRunner(self.engine)
        run_result = runner.run("BTCUSDT", "1h", strategy=_AlwaysBuyStrategy())

        # A BUY on every candle opens exactly one position (no
        # pyramiding, per BasicBacktester's own documented execution
        # model) and leaves it open at the end of the run.
        self.assertEqual(run_result.result.trade_count(), 1)
        self.assertEqual(len(run_result.result.final_portfolio.positions), 1)
        self.assertEqual(run_result.metrics.open_positions_remaining, 1)

    def test_default_initial_portfolio(self):
        runner = BacktestRunner(self.engine)
        run_result = runner.run("BTCUSDT", "1h")
        self.assertEqual(run_result.initial_portfolio.cash_balance, DEFAULT_INITIAL_CASH_BALANCE)
        self.assertEqual(run_result.initial_portfolio.base_currency, DEFAULT_BASE_CURRENCY)

    def test_custom_initial_portfolio_is_used(self):
        portfolio = Portfolio(
            portfolio_id="my-run", base_currency="USDT", cash_balance=Decimal("5000")
        )
        runner = BacktestRunner(self.engine)
        run_result = runner.run("BTCUSDT", "1h", initial_portfolio=portfolio)
        self.assertEqual(run_result.initial_portfolio.cash_balance, Decimal("5000"))
        self.assertEqual(run_result.initial_portfolio.portfolio_id, "my-run")

    def test_custom_initial_portfolio_never_mutated(self):
        portfolio = Portfolio(
            portfolio_id="my-run", base_currency="USDT", cash_balance=Decimal("5000")
        )
        runner = BacktestRunner(self.engine)
        runner.run("BTCUSDT", "1h", strategy=_AlwaysBuyStrategy(), initial_portfolio=portfolio)
        self.assertEqual(portfolio.cash_balance, Decimal("5000"))
        self.assertEqual(portfolio.positions, [])

    def test_limit_is_forwarded_to_data_engine(self):
        runner = BacktestRunner(self.engine)
        run_result = runner.run("BTCUSDT", "1h", limit=50)
        self.assertEqual(run_result.candle_count, 50)

    def test_start_end_time_are_forwarded_to_data_engine(self):
        runner = BacktestRunner(self.engine)
        step_ms = 3_600_000  # 1h in ms
        start = self.fake_client.series_start
        end = start + 10 * step_ms
        run_result = runner.run("BTCUSDT", "1h", start_time=start, end_time=end)
        self.assertLessEqual(run_result.candle_count, 11)
        self.assertGreater(run_result.candle_count, 0)

    def test_metadata_records_requested_bounds(self):
        runner = BacktestRunner(self.engine)
        run_result = runner.run("BTCUSDT", "1h", limit=20)
        self.assertEqual(run_result.metadata["limit"], 20)
        self.assertIsNone(run_result.metadata["start_time"])
        self.assertIsNone(run_result.metadata["end_time"])

    def test_no_data_raises_backtest_runner_data_error(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerDataError):
            runner.run("ETHUSDT", "1h")

    def test_rejects_empty_symbol(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.run("", "1h")

    def test_rejects_empty_timeframe(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.run("BTCUSDT", "")

    def test_rejects_non_base_strategy(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.run("BTCUSDT", "1h", strategy=object())

    def test_rejects_non_portfolio(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.run("BTCUSDT", "1h", initial_portfolio=object())

    def test_backtester_failure_is_wrapped(self):
        runner = BacktestRunner(self.engine, backtester=_AlwaysFailingBacktester())
        with self.assertRaises(BacktestRunnerExecutionError):
            runner.run("BTCUSDT", "1h")

    def test_run_is_deterministic(self):
        runner = BacktestRunner(self.engine)
        first = runner.run("BTCUSDT", "1h", strategy=_AlwaysBuyStrategy())
        second = runner.run("BTCUSDT", "1h", strategy=_AlwaysBuyStrategy())
        self.assertEqual(first.result.trade_count(), second.result.trade_count())
        self.assertEqual(
            first.result.final_portfolio.cash_balance,
            second.result.final_portfolio.cash_balance,
        )

    def test_report_reflects_the_same_run(self):
        runner = BacktestRunner(self.engine)
        run_result = runner.run("BTCUSDT", "1h", strategy=_AlwaysBuyStrategy())
        full_report = run_result.report.full_report()
        self.assertIn("trades", full_report)
        self.assertIn("metrics", full_report)


class TestBacktestRunnerIntegration(BaseBacktestRunnerTest):
    """Proves real, non-fake reuse of BasicStrategy/BasicBacktester/calculate_metrics/BacktestReport."""

    def test_real_basic_strategy_and_basic_backtester_end_to_end(self):
        runner = BacktestRunner(self.engine, backtester=BasicBacktester())
        run_result = runner.run("BTCUSDT", "1h", strategy=BasicStrategy())

        self.assertIsInstance(run_result.result, BacktestResult)
        self.assertIsInstance(run_result.metrics, BacktestMetrics)
        # BasicStrategy's entry filters (EMA50/EMA200, ADX, ATR expansion)
        # are mandatory for any BUY, and BacktestRunner's own Analysis ->
        # Signal stages never populate
        # StrategyContext.metadata["indicators"], so every would-be BUY
        # here correctly fails closed to HOLD for lack of that data --
        # what matters is that this real, non-fake pipeline (BasicStrategy
        # + BasicBacktester + calculate_metrics + BacktestReport) runs
        # end-to-end without error and opens no untested positions.
        self.assertEqual(run_result.result.trade_count(), 0)
        self.assertEqual(run_result.metrics.total_trades, 0)
        self.assertEqual(run_result.metrics.open_positions_remaining, 0)

    def test_scope_boundary_no_ai_no_execution_fields(self):
        runner = BacktestRunner(self.engine)
        run_result = runner.run("BTCUSDT", "1h", strategy=_AlwaysBuyStrategy())
        # BacktestRunResult carries exactly these fields -- no order-id,
        # no broker/exchange identifiers, no AI-derived fields anywhere.
        self.assertEqual(
            set(run_result.__dataclass_fields__.keys()),
            {
                "symbol",
                "timeframe",
                "candle_count",
                "initial_portfolio",
                "result",
                "metrics",
                "report",
                "metadata",
            },
        )


class TestBacktestRunnerAnalysisSignalWiring(BaseBacktestRunnerTest):
    """
    Proves BacktestRunner.run() genuinely runs its own Analysis -> Signal
    stages, once per historical candle, and feeds their real output into
    StrategyContext -- the exact gap Backtesting Part 2 closes (see the
    module docstring's "Feeding StrategyResult into BasicBacktester").
    """

    def test_strategy_receives_a_real_analysis_result(self):
        # _RequiresAnalysisResultStrategy only ever BUYs when a real
        # AnalysisResult was placed on its StrategyContext -- if
        # BacktestRunner still built an empty StrategyContext (as
        # BasicBacktester does on its own), every candle would raise
        # InsufficientStrategyDataError and no trade would ever happen.
        runner = BacktestRunner(self.engine)
        run_result = runner.run("BTCUSDT", "1h", strategy=_RequiresAnalysisResultStrategy())
        self.assertGreaterEqual(run_result.result.trade_count(), 1)

    def test_strategy_receives_a_real_signal_result(self):
        # Same proof, one layer further down the chain: a real
        # SignalResult (produced by the Signal stage from the Analysis
        # stage's own output) must be present on StrategyContext too.
        runner = BacktestRunner(self.engine)
        run_result = runner.run("BTCUSDT", "1h", strategy=_RequiresSignalResultStrategy())
        self.assertGreaterEqual(run_result.result.trade_count(), 1)

    def test_always_failing_strategy_skips_every_candle(self):
        # Every one of this module's own per-candle Strategy-stage calls
        # raises InsufficientStrategyDataError, so no StrategyResult is
        # ever precomputed -- the replay adapter handed to BasicBacktester
        # then raises InsufficientStrategyDataError for every candle it
        # asks about too, and BasicBacktester skips all of them, exactly
        # as it already documents for a real strategy with no usable data.
        runner = BacktestRunner(self.engine)
        run_result = runner.run("BTCUSDT", "1h", strategy=_AlwaysFailingStrategy())
        self.assertEqual(run_result.result.trade_count(), 0)
        self.assertEqual(run_result.result.metadata.get("skipped_candles"), 200)
        self.assertEqual(run_result.metadata["candles_with_strategy_result"], 0)

    def test_always_failing_analyzer_never_aborts_the_run(self):
        # A per-candle Analysis stage failure (InsufficientDataError) is
        # treated as "no AnalysisResult for this candle", never as a
        # reason to abort the whole replay -- BacktestRunner.run() still
        # completes and still produces a full BacktestRunResult.
        runner = BacktestRunner(self.engine, analyzer=_AlwaysFailingAnalyzer())
        run_result = runner.run("BTCUSDT", "1h", strategy=_AlwaysBuyStrategy())
        self.assertIsInstance(run_result.result, BacktestResult)
        # _AlwaysBuyStrategy ignores its StrategyContext entirely, so it
        # still trades even though Analysis never produced a result.
        self.assertEqual(run_result.result.trade_count(), 1)

    def test_always_failing_analyzer_starves_a_context_requiring_strategy(self):
        # Conversely, a strategy that genuinely requires a real
        # AnalysisResult gets none, for any candle, when the injected
        # analyzer always fails -- every candle is skipped.
        runner = BacktestRunner(self.engine, analyzer=_AlwaysFailingAnalyzer())
        run_result = runner.run("BTCUSDT", "1h", strategy=_RequiresAnalysisResultStrategy())
        self.assertEqual(run_result.result.trade_count(), 0)
        self.assertEqual(run_result.metadata["candles_with_strategy_result"], 0)

    def test_empty_indicator_specs_starves_analysis_of_every_candle(self):
        # With no indicators computed at all, the Analysis stage has
        # nothing to interpret for any candle, so a strategy requiring a
        # real AnalysisResult is skipped for the entire run.
        runner = BacktestRunner(self.engine, indicator_specs=[])
        run_result = runner.run("BTCUSDT", "1h", strategy=_RequiresAnalysisResultStrategy())
        self.assertEqual(run_result.result.trade_count(), 0)
        self.assertEqual(run_result.metadata["candles_with_strategy_result"], 0)


class TestBacktestRunnerCompareStrategies(BaseBacktestRunnerTest):
    """
    Tests for `BacktestRunner.compare_strategies()` (Backtesting Part 5
    -- Strategy Comparison): runs the existing pipeline once per
    strategy and returns one `StrategyComparisonResult` carrying a
    full `ranking` (sorted by total return) plus `best_strategy`/
    `worst_strategy`, each `StrategyComparisonEntry` exposing strategy
    name, total return, annual return, win rate, profit factor, Sharpe
    ratio, max drawdown, total trades, and the strategy's own report.
    """

    def test_returns_one_entry_per_strategy(self):
        runner = BacktestRunner(self.engine)
        strategies = [_AlwaysHoldStrategy(name="hold"), _AlwaysBuyStrategy(name="buy")]

        comparison = runner.compare_strategies("BTCUSDT", "1h", strategies)

        self.assertIsInstance(comparison, StrategyComparisonResult)
        self.assertEqual(comparison.symbol, "BTCUSDT")
        self.assertEqual(comparison.timeframe, "1h")
        self.assertEqual(len(comparison.ranking), 2)
        self.assertEqual(
            {entry.strategy_name for entry in comparison.ranking}, {"hold", "buy"}
        )
        self.assertEqual(comparison.metadata["strategy_count"], 2)
        for entry in comparison.ranking:
            self.assertIsInstance(entry, StrategyComparisonEntry)
            self.assertIsInstance(entry.run_result, BacktestRunResult)
            self.assertIsInstance(entry.report, BacktestReport)
            self.assertIsInstance(entry.annual_return, float)

    def test_symbol_is_uppercased(self):
        runner = BacktestRunner(self.engine)
        comparison = runner.compare_strategies(
            "btcusdt", "1h", [_AlwaysHoldStrategy(name="hold")]
        )
        self.assertEqual(comparison.symbol, "BTCUSDT")

    def test_ranked_by_total_return_descending(self):
        runner = BacktestRunner(self.engine)
        strategies = [
            _AlwaysHoldStrategy(name="hold"),
            _BuyOnFirstCandleThenSellStrategy(name="buy-then-sell"),
            _AlwaysBuyStrategy(name="buy-and-hold"),
        ]

        comparison = runner.compare_strategies("BTCUSDT", "1h", strategies)

        returns = [entry.total_return for entry in comparison.ranking]
        self.assertEqual(returns, sorted(returns, reverse=True))
        # The one strategy with a genuinely closed, profitable round
        # trip must rank first on this steadily-rising price series.
        self.assertEqual(comparison.ranking[0].strategy_name, "buy-then-sell")
        self.assertGreater(comparison.ranking[0].total_return, Decimal("0"))
        self.assertEqual(comparison.ranking[0].total_trades, 1)

    def test_best_and_worst_strategy_match_the_ranking_ends(self):
        runner = BacktestRunner(self.engine)
        strategies = [
            _AlwaysHoldStrategy(name="hold"),
            _BuyOnFirstCandleThenSellStrategy(name="buy-then-sell"),
            _AlwaysBuyStrategy(name="buy-and-hold"),
        ]

        comparison = runner.compare_strategies("BTCUSDT", "1h", strategies)

        self.assertEqual(comparison.best_strategy, comparison.ranking[0])
        self.assertEqual(comparison.worst_strategy, comparison.ranking[-1])
        self.assertGreaterEqual(
            comparison.best_strategy.total_return, comparison.worst_strategy.total_return
        )

    def test_best_and_worst_strategy_are_equal_for_a_single_strategy(self):
        runner = BacktestRunner(self.engine)
        comparison = runner.compare_strategies(
            "BTCUSDT", "1h", [_AlwaysHoldStrategy(name="hold")]
        )
        self.assertEqual(comparison.best_strategy, comparison.worst_strategy)
        self.assertEqual(comparison.best_strategy.strategy_name, "hold")

    def test_each_entry_mirrors_its_own_run_result_metrics_and_report(self):
        runner = BacktestRunner(self.engine)
        strategy = _BuyOnFirstCandleThenSellStrategy(name="buy-then-sell")

        comparison = runner.compare_strategies("BTCUSDT", "1h", [strategy])

        entry = comparison.ranking[0]
        run_result = entry.run_result
        metrics = run_result.metrics
        self.assertEqual(entry.strategy_name, "buy-then-sell")
        self.assertEqual(entry.total_return, metrics.total_return)
        self.assertEqual(entry.annual_return, run_result.metadata["annual_return"])
        self.assertEqual(entry.win_rate, metrics.win_rate)
        self.assertEqual(entry.max_drawdown, metrics.max_drawdown_pct)
        self.assertEqual(entry.profit_factor, metrics.profit_factor)
        self.assertEqual(entry.sharpe_ratio, metrics.sharpe_ratio)
        self.assertEqual(entry.total_trades, metrics.total_trades)
        self.assertIs(entry.report, run_result.report)

    def test_annual_return_is_present_on_the_underlying_run_result(self):
        runner = BacktestRunner(self.engine)
        run_result = runner.run("BTCUSDT", "1h", strategy=_AlwaysHoldStrategy(name="hold"))
        self.assertIn("annual_return", run_result.metadata)
        self.assertIn("period_days", run_result.metadata)
        self.assertIsInstance(run_result.metadata["annual_return"], float)
        self.assertGreaterEqual(run_result.metadata["period_days"], 0.0)

    def test_forwards_limit_to_every_strategys_run(self):
        runner = BacktestRunner(self.engine)
        strategies = [_AlwaysHoldStrategy(name="hold"), _AlwaysBuyStrategy(name="buy")]

        comparison = runner.compare_strategies("BTCUSDT", "1h", strategies, limit=50)

        for entry in comparison.ranking:
            self.assertEqual(entry.run_result.candle_count, 50)

    def test_uses_the_same_initial_portfolio_for_every_strategy_without_mutating_it(self):
        runner = BacktestRunner(self.engine)
        starting = Portfolio(
            portfolio_id="shared-comparison-portfolio",
            base_currency="USDT",
            cash_balance=Decimal("5000"),
        )
        strategies = [_AlwaysHoldStrategy(name="hold"), _AlwaysBuyStrategy(name="buy")]

        comparison = runner.compare_strategies(
            "BTCUSDT", "1h", strategies, initial_portfolio=starting
        )

        for entry in comparison.ranking:
            self.assertEqual(entry.run_result.initial_portfolio.cash_balance, Decimal("5000"))
        self.assertEqual(starting.cash_balance, Decimal("5000"))
        self.assertEqual(len(starting.positions), 0)

    def test_backtester_failure_is_wrapped(self):
        runner = BacktestRunner(self.engine, backtester=_AlwaysFailingBacktester())
        with self.assertRaises(BacktestRunnerExecutionError):
            runner.compare_strategies("BTCUSDT", "1h", [_AlwaysHoldStrategy(name="hold")])

    def test_no_data_raises_backtest_runner_data_error(self):
        runner = BacktestRunner(DataEngine(client=make_fake_client(num_candles=1), db_path=self.db_path + ".empty"))
        with self.assertRaises(BacktestRunnerDataError):
            runner.compare_strategies(
                "ETHUSDT", "1h", [_AlwaysHoldStrategy(name="hold")]
            )

    def test_rejects_empty_sequence(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.compare_strategies("BTCUSDT", "1h", [])

    def test_rejects_non_sequence(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.compare_strategies("BTCUSDT", "1h", object())

    def test_rejects_a_string_masquerading_as_a_sequence(self):
        # str/bytes are technically Sequences in Python -- must still
        # be rejected, the same guard `run()`'s own validation implies.
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.compare_strategies("BTCUSDT", "1h", "not-a-list-of-strategies")

    def test_rejects_non_base_strategy_entry(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.compare_strategies("BTCUSDT", "1h", [BasicStrategy(), object()])


class TestBacktestRunnerWalkForwardEvaluate(BaseBacktestRunnerTest):
    """
    Tests for `BacktestRunner.walk_forward_evaluate()` (Backtesting
    Part 4 -- Walk-Forward Evaluation): splits an already-downloaded
    candle series into train/test windows and runs the existing
    pipeline once per window's testing period only.
    """

    def test_returns_windows_and_summary(self):
        # 200 candles, train=50/test=50/step=test_size (default) ->
        # windows at train_start 0, 50, 100 (train_start=150 would need
        # candles up to 250, which don't exist) -- exactly 3 windows.
        runner = BacktestRunner(self.engine)

        result = runner.walk_forward_evaluate("BTCUSDT", "1h", train_size=50, test_size=50)

        self.assertIsInstance(result, WalkForwardResult)
        self.assertEqual(result.symbol, "BTCUSDT")
        self.assertEqual(result.timeframe, "1h")
        self.assertEqual(len(result.windows), 3)
        self.assertIsInstance(result.summary, WalkForwardSummary)
        self.assertEqual(result.metadata["window_count"], 3)
        self.assertEqual(result.metadata["train_size"], 50)
        self.assertEqual(result.metadata["test_size"], 50)
        self.assertEqual(result.metadata["step_size"], 50)
        self.assertEqual(result.metadata["candle_count"], 200)
        for window in result.windows:
            self.assertIsInstance(window, WalkForwardWindow)
            self.assertIsInstance(window.run_result, BacktestRunResult)

    def test_symbol_is_uppercased(self):
        runner = BacktestRunner(self.engine)
        result = runner.walk_forward_evaluate("btcusdt", "1h", train_size=50, test_size=50)
        self.assertEqual(result.symbol, "BTCUSDT")

    def test_windows_are_sequential_and_chronological(self):
        runner = BacktestRunner(self.engine)
        result = runner.walk_forward_evaluate("BTCUSDT", "1h", train_size=50, test_size=50)

        self.assertEqual([w.window_number for w in result.windows], [1, 2, 3])
        for window in result.windows:
            # train period precedes its own test period ...
            self.assertLess(window.train_period[0], window.train_period[1])
            self.assertLess(window.train_period[1], window.test_period[0])
            self.assertLess(window.test_period[0], window.test_period[1])
        # ... and each window's test period starts where the next
        # window's train period begins, for non-overlapping windows
        # (default step_size == test_size).
        for earlier, later in zip(result.windows, result.windows[1:]):
            self.assertEqual(earlier.test_period[0], later.train_period[0])

    def test_step_size_defaults_to_test_size(self):
        runner = BacktestRunner(self.engine)
        result = runner.walk_forward_evaluate("BTCUSDT", "1h", train_size=50, test_size=20)
        self.assertEqual(result.metadata["step_size"], 20)

    def test_custom_step_size_produces_overlapping_windows(self):
        runner = BacktestRunner(self.engine)
        default_step_result = runner.walk_forward_evaluate(
            "BTCUSDT", "1h", train_size=50, test_size=20
        )
        custom_step_result = runner.walk_forward_evaluate(
            "BTCUSDT", "1h", train_size=50, test_size=20, step_size=10
        )
        # A smaller step advances train_start more slowly, producing
        # more (overlapping) windows over the same candle series.
        self.assertGreater(len(custom_step_result.windows), len(default_step_result.windows))

    def test_each_windows_run_only_replays_its_own_test_period(self):
        # The training period is never fed into run() -- each window's
        # own BacktestRunResult must only ever have replayed test_size
        # candles, never train_size + test_size.
        runner = BacktestRunner(self.engine)
        result = runner.walk_forward_evaluate("BTCUSDT", "1h", train_size=50, test_size=20)
        for window in result.windows:
            self.assertEqual(window.run_result.candle_count, 20)

    def test_each_window_mirrors_its_own_run_result_metrics(self):
        runner = BacktestRunner(self.engine)
        result = runner.walk_forward_evaluate("BTCUSDT", "1h", train_size=50, test_size=50)
        for window in result.windows:
            metrics = window.run_result.metrics
            self.assertEqual(window.total_return, metrics.total_return)
            self.assertEqual(window.win_rate, metrics.win_rate)
            self.assertEqual(window.profit_factor, metrics.profit_factor)
            self.assertEqual(window.max_drawdown_pct, metrics.max_drawdown_pct)
            self.assertEqual(window.sharpe_ratio, metrics.sharpe_ratio)
            self.assertEqual(window.number_of_trades, metrics.total_trades)

    def test_summary_matches_manual_aggregation(self):
        runner = BacktestRunner(self.engine)
        result = runner.walk_forward_evaluate(
            "BTCUSDT", "1h", train_size=50, test_size=50, strategy=_AlwaysBuyStrategy()
        )
        windows = result.windows
        summary = result.summary

        expected_avg_return = sum((w.total_return for w in windows), Decimal("0")) / len(windows)
        expected_avg_win_rate = sum(w.win_rate for w in windows) / len(windows)
        expected_avg_drawdown = sum(w.max_drawdown_pct for w in windows) / len(windows)
        expected_avg_sharpe = sum(w.sharpe_ratio for w in windows) / len(windows)

        self.assertEqual(summary.average_return, expected_avg_return)
        self.assertAlmostEqual(summary.average_win_rate, expected_avg_win_rate)
        self.assertAlmostEqual(summary.average_drawdown, expected_avg_drawdown)
        self.assertAlmostEqual(summary.average_sharpe, expected_avg_sharpe)
        self.assertIs(summary.best_window, max(windows, key=lambda w: w.total_return))
        self.assertIs(summary.worst_window, min(windows, key=lambda w: w.total_return))

    def test_uses_the_same_initial_portfolio_for_every_window_without_mutating_it(self):
        runner = BacktestRunner(self.engine)
        starting = Portfolio(
            portfolio_id="shared-walk-forward-portfolio",
            base_currency="USDT",
            cash_balance=Decimal("5000"),
        )

        result = runner.walk_forward_evaluate(
            "BTCUSDT", "1h", train_size=50, test_size=50, initial_portfolio=starting
        )

        for window in result.windows:
            self.assertEqual(window.run_result.initial_portfolio.cash_balance, Decimal("5000"))
        self.assertEqual(starting.cash_balance, Decimal("5000"))
        self.assertEqual(len(starting.positions), 0)

    def test_backtester_failure_is_wrapped(self):
        runner = BacktestRunner(self.engine, backtester=_AlwaysFailingBacktester())
        with self.assertRaises(BacktestRunnerExecutionError):
            runner.walk_forward_evaluate("BTCUSDT", "1h", train_size=50, test_size=50)

    def test_rejects_non_base_strategy(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.walk_forward_evaluate(
                "BTCUSDT", "1h", train_size=50, test_size=50, strategy=object()
            )

    def test_no_data_raises_backtest_runner_data_error(self):
        empty_engine = DataEngine(
            client=make_fake_client(num_candles=1), db_path=self.db_path + ".empty"
        )
        runner = BacktestRunner(empty_engine)
        with self.assertRaises(BacktestRunnerDataError):
            runner.walk_forward_evaluate("ETHUSDT", "1h", train_size=50, test_size=50)

    def test_not_enough_candles_raises_backtest_runner_data_error(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerDataError):
            runner.walk_forward_evaluate("BTCUSDT", "1h", train_size=150, test_size=100)

    def test_rejects_empty_symbol(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.walk_forward_evaluate("", "1h", train_size=50, test_size=50)

    def test_rejects_empty_timeframe(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.walk_forward_evaluate("BTCUSDT", "", train_size=50, test_size=50)

    def test_rejects_non_positive_train_size(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.walk_forward_evaluate("BTCUSDT", "1h", train_size=0, test_size=50)

    def test_rejects_non_positive_test_size(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.walk_forward_evaluate("BTCUSDT", "1h", train_size=50, test_size=-1)

    def test_rejects_non_positive_step_size(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.walk_forward_evaluate(
                "BTCUSDT", "1h", train_size=50, test_size=50, step_size=0
            )

    def test_rejects_non_int_train_size(self):
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.walk_forward_evaluate("BTCUSDT", "1h", train_size=50.5, test_size=50)

    def test_rejects_bool_train_size(self):
        # bool is a subclass of int in Python -- must still be rejected,
        # the same guard this project applies elsewhere (e.g. Services
        # Part 2A's min_confidence validation).
        runner = BacktestRunner(self.engine)
        with self.assertRaises(BacktestRunnerConfigurationError):
            runner.walk_forward_evaluate("BTCUSDT", "1h", train_size=True, test_size=50)


if __name__ == "__main__":
    unittest.main()
