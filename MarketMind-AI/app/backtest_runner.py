"""
app/backtest_runner.py

Defines `BacktestRunner`: the second `app/`-layer use case (after
`app.pipeline.MarketPipeline`). It wires already-implemented layers
together, in this fixed order, for one symbol/timeframe, to run a real
historical backtest:

    1. Data        -- `data.engine.DataEngine.load_history()` loads
                       already-downloaded candles for a symbol/timeframe
                       (optionally bounded by `start_time`/`end_time`/
                       `limit`).
    2. Indicators   -- the same configurable set of `indicators.
                       BaseIndicator` instances `app.pipeline.
                       MarketPipeline` already defaults to (see
                       `_default_indicator_specs`), each run once, in
                       batch, over the whole replay window.
    3. Analysis -> Signal -> Strategy, replayed once per historical
                       candle (see "Point-in-time replay" below): a
                       `core.entities.market_state.MarketState` snapshot
                       for that candle plus its indicator readings
                       becomes an `analysis.context.AnalysisContext`,
                       run through an injected `analysis.base.
                       BaseAnalyzer` (defaults to `analysis.aggregator.
                       AnalysisAggregator`); its `analysis.result.
                       AnalysisResult` becomes a `signals.context.
                       SignalContext`, run through an injected
                       `signals.base.BaseSignalGenerator` (defaults to
                       `signals.aggregator.SignalAggregator`); both
                       become a `strategies.context.StrategyContext`,
                       run through the caller's `strategies.
                       base_strategy.BaseStrategy`, producing one
                       `strategies.result.StrategyResult` for that
                       candle.
    4. Backtesting  -- those per-candle `StrategyResult`s, the historical
                       candles, and a starting `core.entities.portfolio.
                       Portfolio` are assembled into a `backtesting.
                       context.BacktestContext` and replayed through an
                       injected `backtesting.base.BaseBacktester`
                       (defaults to `backtesting.basic_backtester.
                       BasicBacktester`), producing a `backtesting.
                       result.BacktestResult` (see "Feeding StrategyResult
                       into BasicBacktester" below).
    5. Metrics      -- `backtesting.metrics.calculate_metrics()` derives
                       a `backtesting.metrics.BacktestMetrics` from that
                       result.
    6. Report       -- `backtesting.report.BacktestReport` wraps the
                       result and metrics into human-readable/structured
                       summaries.

This closes the exact gap `PROJECT_STATE.md` documents under
`backtesting/`'s "what's missing" column: "Nothing currently assembles
a `BacktestContext` from real historical data (via `data/`) and a real
strategy end-to-end outside of tests" -- extended, in this second part,
to also assemble the real Analysis -> Signal -> Strategy chain for
every historical candle, the same gap `tests/test_basic_backtester.py`'s
`TestRealBasicStrategyIntegration` documents: "`BasicBacktester` never
supplies an `AnalysisResult` on the per-candle `StrategyContext`, so a
real `BasicStrategy` ... raises `InsufficientStrategyDataError` for
every candle." This module is what supplies that missing `AnalysisResult`
(and `SignalResult`), for every candle, from genuine historical data.

Scope (deliberately bounded)
-----------------------------
Only the stages above are wired. No AI, no machine learning, no
broker/exchange connection, no live trading, no order-execution engine,
no UI, no server, and no automatic/parameter optimization. This module
adds no new calculation/interpretation/decision logic of its own:
every stage's actual work still happens inside the package that
already owns it (`data/`, `indicators/`, `analysis/`, `signals/`,
`strategies/`, `backtesting/`); this only sequences the existing
calls, matching the "conductor" role `app/__init__.py` already
documents. `backtesting` remains a consumer, never a strategy author
(`PROJECT_RULES.md` Section 1, principle 5) -- this module does not
change that; it only assembles the inputs a `BaseBacktester`/
`BaseStrategy` already know how to consume.

Point-in-time replay (no look-ahead)
--------------------------------------
Every indicator this module defaults to (see `_default_indicator_specs`
in `app/pipeline.py`) computes a backward-looking, causal value at each
row -- a rolling/EWM window over data up to and including that row (see
e.g. `indicators/sma.py`: "first `period - 1` values are `NaN`"). That
means running one indicator's `calculate()` once over the *entire*
replay window and then reading off its value at historical row `i`
(`_to_core_indicator_result_at_index`, below) is exactly the value a
live, incremental calculation would have produced after candle `i` --
no future candle's data ever leaks into an earlier candle's reading.
This lets Indicators run once per backtest (matching `app.pipeline.
MarketPipeline`'s own single batch `calculate()` call per indicator)
instead of once per candle, while still feeding Analysis/Signal/Strategy
a strictly point-in-time view for every candle. A row where an indicator
has not yet warmed up (`NaN`) is treated as that indicator being absent
for that candle -- the same "absence only lowers confidence, never
invalidates the result" convention `analysis.aggregator.
AnalysisAggregator`/`signals.aggregator.SignalAggregator` already use
for a sub-component that raised an error instead.

Feeding StrategyResult into BasicBacktester
----------------------------------------------
`backtesting.basic_backtester.BasicBacktester.run()` (never modified --
see `PROJECT_RULES.md` Section 4's dependency table, which does not let
`backtesting` import `analysis`/`signals`) builds its own minimal
`StrategyContext` per candle, carrying no `AnalysisResult`/
`SignalResult` of its own, and calls `context.strategy.decide(...)`
directly (see its module docstring). To let `BasicBacktester` genuinely
replay the `StrategyResult`s this module's own Analysis -> Signal ->
Strategy stages already produced -- rather than reimplementing any part
of `BasicBacktester`'s replay loop, execution model, or trade
bookkeeping here -- `run()` precomputes one `StrategyResult` per candle
index up front, then wraps the caller's real `strategy` in a small
internal adapter (`_PrecomputedStrategyReplay`, a genuine `BaseStrategy`)
that simply looks up and returns the `StrategyResult` already decided
for whichever `candle_index` `BasicBacktester` asks about.
`BasicBacktester` is given this adapter as `BacktestContext.strategy`;
from its perspective nothing changed -- it still just calls
`strategy.decide(...)` once per candle, exactly as documented, and
still treats an `InsufficientStrategyDataError` (raised by the adapter
whenever this module's own Strategy stage could not produce a result
for that candle, e.g. because Analysis/Signal had insufficient data
yet) as "skip this candle" (see `backtesting/basic_backtester.py`'s
module docstring). The adapter invents no decisions of its own -- it
only replays what the real `strategy`, `analyzer`, and
`signal_generator` already decided.

Placement note -- why `app/`, not `services/` or `backtesting/`
------------------------------------------------------------------
`PROJECT_RULES.md` Section 4's dependency table does not allow
`backtesting/` to import `analysis/`, `signals/`, or `data/`'s concrete
`DataEngine` wiring beyond what it already depends on for `Candle`, and
does not allow `services/` to import `data/`/`analysis/`/`signals/`/
`strategies/`/`backtesting/` at all. `app/` is the one layer explicitly
allowed to import all of the above, and its documented role
(`app/__init__.py`) is exactly this "when and in what order" wiring --
the same reasoning `app/pipeline.py`'s own module docstring already
gives for living in `app/`.

Reuse, not duplication
------------------------
`_to_core_candle`, `_candles_to_dataframe`, and `_default_indicator_specs`
are imported directly from `app.pipeline` and reused as-is -- exactly
the translation/defaulting `MarketPipeline` already performs for its own
Data/Indicators stages -- rather than duplicated here. `app/pipeline.py`
itself is left completely untouched. The one genuinely new piece of
translation this module adds, `_to_core_indicator_result_at_index`, is
a strict generalization of `app.pipeline._to_core_indicator_result`
("take a historical row" instead of "take only the latest row"), needed
because `MarketPipeline` only ever looks at the most recent candle while
`BacktestRunner` must look at every one -- it is not an alternative
implementation of the same thing, it is the thing `MarketPipeline`
never needed.

Backtesting Part 3 -- Strategy Comparison
-------------------------------------------
`BacktestRunner.compare_strategies()` (new, this part) runs the exact
same pipeline `run()` already performs -- Data -> Indicators ->
Analysis -> Signal -> Strategy -> Backtesting -> Metrics -> Report --
once per strategy in a caller-supplied sequence, against the same
symbol/timeframe/historical window/starting portfolio, and returns one
`StrategyComparisonResult` bundling every strategy's `BacktestRunResult`
alongside a compact `StrategyComparisonEntry` (strategy name, total
return, win rate, max drawdown, profit factor, Sharpe ratio, and trade
count), sorted by total return (highest first).

This adds no new calculation, interpretation, or trading logic of its
own: every number in a `StrategyComparisonEntry` is read directly off
the `BacktestMetrics` that `run()` (and, underneath it, `backtesting.
metrics.calculate_metrics`) already computed for that strategy's own
run -- `compare_strategies()` only calls `run()` once per strategy and
sorts the results. No parameter optimization, no automatic strategy
tuning, no new strategy/backtester/report logic, and no AI -- it
remains, exactly like `run()`, a consumer of whatever strategies it is
given (`PROJECT_RULES.md` Section 1, principle 5).

Backtesting Part 5 -- Strategy Comparison (extended)
-------------------------------------------------------
This part extends `compare_strategies()` (introduced in Part 3, above)
so its comparison object carries every figure this milestone's own
requirements call for -- strategy name, total return, *annual return*
(new), win rate, profit factor, Sharpe ratio, max drawdown, total
trades, and the strategy's own `BacktestReport` -- directly on each
`StrategyComparisonEntry`, and so the overall `StrategyComparisonResult`
also exposes `best_strategy`/`worst_strategy` (in addition to the full
`ranking`, sorted by total return, highest first) rather than making a
caller re-derive them from `entries[0]`/`entries[-1]`.

No new calculation beyond one addition: `annual_return`, an
annualized-return figure derived from `BacktestMetrics.total_return_pct`
(already computed by `calculate_metrics()`) and the replayed period's
elapsed wall-clock time (`core.entities.candle.Candle.open_time`/
`close_time` on the first/last historical candle `run()` already
loaded) -- a compound-annual-growth-rate (CAGR) style calculation,
`(1 + total_return_pct) ** (365.25 / period_days) - 1`, falling back to
the plain `total_return_pct` itself when the replayed period is under a
day or the compounding base would be non-positive (an extreme loss).
This is computed once, inside `run()` (alongside `metrics`/`report`,
its two existing siblings) and recorded on `BacktestRunResult.metadata`
(`period_days`/`annual_return`) so it is available to `run()`'s own
callers too, not only to `compare_strategies()`. Every other figure on
a `StrategyComparisonEntry` is still read directly off that strategy's
own `BacktestMetrics`/`BacktestReport` -- never recomputed, never
re-derived from a different strategy's run, and never fit/optimized.

`compare_strategies()` itself still only calls `run()` once per
strategy (unchanged from Part 3) and now also picks `best_strategy`
(the entry with the highest `total_return`) and `worst_strategy` (the
lowest) from the same already-sorted `ranking` -- no new backtester, no
new strategy/report/metrics logic, no parameter optimization, and no
AI, exactly as Part 3 already documented (`PROJECT_RULES.md` Section 1,
principle 5).

Backtesting Part 4 -- Walk-Forward Evaluation
-----------------------------------------------
`BacktestRunner.walk_forward_evaluate()` (new, this part) splits an
already-downloaded candle series into a sequence of non-overlapping
train/test windows -- each training period immediately followed by its
own testing period -- and calls the exact same `run()` pipeline once
per window, bounded to that window's *testing* period only (via
`start_time`/`end_time`, the same bounds `run()` already forwards to
`DataEngine.load_history`). One `WalkForwardWindow` is recorded per
window (window number, train period, test period, and that window's
`BacktestMetrics` figures, plus the full `BacktestRunResult` for
traceability), and a single `WalkForwardSummary` aggregates
average return/win rate/drawdown/Sharpe ratio across every window
alongside the best- and worst-performing window by total return.

The *training* period is deliberately never fed into `run()`, into any
strategy, or into any calculation here -- there is no parameter
fitting, tuning, or optimization step in this repository
(`PROJECT_RULES.md` Section 1; this milestone's own explicit scope).
Each training period exists only to determine where its immediately
following testing period begins, matching how a genuine walk-forward
evaluation is defined; the whole point of only ever backtesting the
testing period is to prove a strategy's decisions hold up on data that
period's own window boundaries were not derived from adapting to.

`_summarize_walk_forward_windows()`, the small aggregation used to
build `WalkForwardSummary`, contains no calculation `backtesting.
metrics` doesn't already own the definition of (`total_return`,
`win_rate`, `max_drawdown_pct`, `sharpe_ratio`) -- it only averages
values `calculate_metrics()` already computed per window and picks the
best/worst by `total_return`, mirroring `compare_strategies()`'s own
"sort by total return" convention one method up. No new backtester, no
new strategy, no broker/execution, and no AI.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional, Sequence

from analysis.aggregator import AnalysisAggregator
from analysis.base import BaseAnalyzer
from analysis.context import AnalysisContext
from analysis.exceptions import AnalysisError

from core.entities.candle import Candle as CoreCandle
from core.entities.indicator_result import IndicatorResult as CoreIndicatorResult
from core.entities.market_state import MarketState
from core.entities.portfolio import Portfolio

from data.engine import DataEngine

from indicators.base import BaseIndicator

from signals.aggregator import SignalAggregator
from signals.base import BaseSignalGenerator
from signals.context import SignalContext
from signals.exceptions import SignalError

from strategies.base_strategy import BaseStrategy
from strategies.basic_strategy import BasicStrategy
from strategies.context import StrategyContext
from strategies.exceptions import InsufficientStrategyDataError
from strategies.result import StrategyResult

from backtesting.base import BaseBacktester
from backtesting.basic_backtester import BasicBacktester
from backtesting.context import BacktestContext
from backtesting.exceptions import BacktestError
from backtesting.metrics import BacktestMetrics, calculate_metrics
from backtesting.report import BacktestReport
from backtesting.result import BacktestResult

from app.exceptions import (
    BacktestRunnerConfigurationError,
    BacktestRunnerDataError,
    BacktestRunnerExecutionError,
)
from app.pipeline import _candles_to_dataframe, _default_indicator_specs, _to_core_candle

#: Default starting cash balance for a run's `initial_portfolio` when
#: the caller does not supply one.
DEFAULT_INITIAL_CASH_BALANCE = Decimal("10000")

#: Default `base_currency`/`portfolio_id` for a run's `initial_portfolio`
#: when the caller does not supply one.
DEFAULT_BASE_CURRENCY = "USDT"
DEFAULT_PORTFOLIO_ID = "backtest-portfolio"


def _default_initial_portfolio() -> Portfolio:
    """Build a fresh, cash-only starting `Portfolio` for a run (never shared/reused across runs)."""
    return Portfolio(
        portfolio_id=DEFAULT_PORTFOLIO_ID,
        base_currency=DEFAULT_BASE_CURRENCY,
        cash_balance=DEFAULT_INITIAL_CASH_BALANCE,
    )


def _to_core_indicator_result_at_index(
    raw_result: Any, index: int, *, symbol: str, timeframe: str, timestamp: datetime
) -> Optional[CoreIndicatorResult]:
    """
    Translate one historical row (`index`) of an already-computed,
    whole-history `indicators.base.IndicatorResult` into a single
    `core.entities.indicator_result.IndicatorResult` -- the same
    translation `app.pipeline._to_core_indicator_result` performs for
    only the *latest* row (see the module docstring's "Point-in-time
    replay" section for why reading off a historical row this way never
    introduces look-ahead).

    Returns `None` when this indicator's value at `index` is not yet
    available (`NaN` warm-up rows, e.g. fewer than `period` observations
    have accumulated by this candle) -- treated as "this indicator is
    absent for this candle", never as an error, mirroring how `app.
    pipeline.MarketPipeline` treats a whole indicator failing to
    compute at all.
    """
    if raw_result.is_multi_output:
        raw_values = {key: float(arr[index]) for key, arr in raw_result.values.items()}
        if any(math.isnan(v) for v in raw_values.values()):
            return None
        values = raw_values
    else:
        value = float(raw_result.values[index])
        if math.isnan(value):
            return None
        values = {"value": value}

    return CoreIndicatorResult(
        indicator_name=raw_result.name,
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        values=values,
        parameters=dict(raw_result.metadata),
    )


class _PrecomputedStrategyReplay(BaseStrategy):
    """
    Internal adapter: replays already-decided `StrategyResult`s, one per
    `candle_index`, back to `BasicBacktester` (or any other
    `BaseBacktester`) exactly as it asks for them.

    Never constructed directly by a caller -- `BacktestRunner.run()`
    builds one per run, after running this module's own Analysis ->
    Signal -> Strategy stages for every historical candle, purely so an
    unmodified `BasicBacktester` (which supplies no `AnalysisResult`/
    `SignalResult` of its own -- see the module docstring's "Feeding
    StrategyResult into BasicBacktester" section) can still replay a
    real strategy's genuine, data-driven decisions. This adapter makes
    no decisions of its own: it only looks up and returns what the real
    `strategy` already decided.
    """

    def __init__(self, *, name: str, results_by_candle_index: dict[int, StrategyResult]) -> None:
        super().__init__(name=name)
        self._results_by_candle_index = results_by_candle_index

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        candle_index = context.metadata.get("candle_index")
        result = self._results_by_candle_index.get(candle_index)
        if result is None:
            raise InsufficientStrategyDataError(
                f"{self.name} has no precomputed StrategyResult for "
                f"candle_index={candle_index!r} (Analysis/Signal/Strategy had "
                "insufficient data at that point in the replay)."
            )
        return result


@dataclass(frozen=True)
class BacktestRunResult:
    """
    Everything produced by one `BacktestRunner.run()` call, one entry
    per stage, for traceability -- mirrors the role
    `app.pipeline.PipelineResult` plays for `MarketPipeline`.

    Attributes:
        symbol: Trading pair/instrument the backtest ran for.
        timeframe: Candle interval the backtest ran on.
        candle_count: Number of historical candles the Data stage
            loaded and replayed.
        initial_portfolio: The starting `Portfolio` state the run
            began from.
        result: The Backtesting stage's `BacktestResult` (final
            portfolio, trades, summary).
        metrics: The Metrics stage's `BacktestMetrics` (win rate,
            profit factor, drawdown, Sharpe ratio, etc.).
        report: The Report stage's `BacktestReport`, wrapping `result`
            and `metrics` into human-readable/structured summaries.
        metadata: Free-form additional traceability details (e.g. the
            requested `start_time`/`end_time`/`limit`, and how many
            candles the Analysis/Signal/Strategy replay actually
            produced a `StrategyResult` for).
    """

    symbol: str
    timeframe: str
    candle_count: int
    initial_portfolio: Portfolio
    result: BacktestResult
    metrics: BacktestMetrics
    report: BacktestReport
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyComparisonEntry:
    """
    One strategy's summarized performance within a `compare_strategies()`
    run -- every value is read directly off that strategy's own
    `BacktestRunResult.metrics`/`.report`/`.metadata` (`backtesting.
    metrics.BacktestMetrics`, `backtesting.report.BacktestReport`),
    never recomputed here (see the module docstring's "Backtesting
    Part 5" section for `annual_return`'s one exception -- itself
    already computed once inside `run()`, not here).

    Attributes:
        strategy_name: The `BaseStrategy.name` this entry summarizes.
        total_return: `BacktestMetrics.total_return` (final equity minus
            initial equity, in the portfolio's base currency).
        annual_return: `BacktestRunResult.metadata["annual_return"]`,
            an annualized-return figure derived from `total_return_pct`
            and the replayed period's elapsed wall-clock time.
        win_rate: `BacktestMetrics.win_rate`.
        profit_factor: `BacktestMetrics.profit_factor` (`None` when
            there were no losing trades -- the ratio is undefined).
        sharpe_ratio: `BacktestMetrics.sharpe_ratio`.
        max_drawdown: `BacktestMetrics.max_drawdown_pct`.
        total_trades: `BacktestMetrics.total_trades`.
        report: `BacktestRunResult.report` -- this strategy's own
            `backtesting.report.BacktestReport` (human-readable/
            structured summaries), so a caller never has to reach into
            `run_result` just to read it.
        run_result: The full `BacktestRunResult` this entry summarizes,
            kept for full traceability (final portfolio, trades,
            metrics, report, etc.).
    """

    strategy_name: str
    total_return: Decimal
    annual_return: float
    win_rate: float
    profit_factor: Optional[float]
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    report: BacktestReport
    run_result: BacktestRunResult


@dataclass(frozen=True)
class StrategyComparisonResult:
    """
    Everything produced by one `BacktestRunner.compare_strategies()`
    call: one `StrategyComparisonEntry` per strategy, ranked by
    `total_return` (highest first), plus the best- and
    worst-performing strategy picked out directly.

    Attributes:
        symbol: Trading pair/instrument every strategy was compared on.
        timeframe: Candle interval every strategy was compared on.
        ranking: One `StrategyComparisonEntry` per strategy, sorted by
            `total_return` descending (the best-performing strategy by
            total return first).
        best_strategy: The `StrategyComparisonEntry` with the highest
            `total_return` -- `ranking[0]`.
        worst_strategy: The `StrategyComparisonEntry` with the lowest
            `total_return` -- `ranking[-1]`.
        metadata: Free-form additional traceability details (e.g. how
            many strategies were compared).
    """

    symbol: str
    timeframe: str
    ranking: list[StrategyComparisonEntry]
    best_strategy: StrategyComparisonEntry
    worst_strategy: StrategyComparisonEntry
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WalkForwardWindow:
    """
    One walk-forward window's train/test split and its resulting
    test-period performance -- every performance value is read
    directly off that window's own `BacktestRunResult.metrics`
    (`backtesting.metrics.BacktestMetrics`), never recomputed here,
    mirroring `StrategyComparisonEntry`'s same convention one method
    up.

    Attributes:
        window_number: 1-based position of this window in the walk-
            forward sequence (chronological, not sorted by
            performance).
        train_period: `(train_start_time, train_end_time)` -- the
            inclusive `Candle.open_time` bounds of this window's
            training period. Never fed into `run()`, a strategy, or
            any calculation here -- recorded purely to show where the
            immediately-following testing period was derived from (see
            the module docstring's "Walk-Forward Evaluation" section).
        test_period: `(test_start_time, test_end_time)` -- the
            inclusive `Candle.open_time` bounds of this window's
            testing period, the only data this window's `run()` call
            actually replayed.
        total_return: `BacktestMetrics.total_return` for this window's
            testing period.
        win_rate: `BacktestMetrics.win_rate` for this window.
        profit_factor: `BacktestMetrics.profit_factor` for this window
            (`None` when there were no losing trades).
        max_drawdown_pct: `BacktestMetrics.max_drawdown_pct` for this
            window.
        sharpe_ratio: `BacktestMetrics.sharpe_ratio` for this window.
        number_of_trades: `BacktestMetrics.total_trades` for this
            window.
        run_result: The full `BacktestRunResult` for this window's
            testing-period run, kept for full traceability.
    """

    window_number: int
    train_period: tuple[int, int]
    test_period: tuple[int, int]
    total_return: Decimal
    win_rate: float
    profit_factor: Optional[float]
    max_drawdown_pct: float
    sharpe_ratio: float
    number_of_trades: int
    run_result: BacktestRunResult


@dataclass(frozen=True)
class WalkForwardSummary:
    """
    Aggregate performance across every `WalkForwardWindow` in one
    `walk_forward_evaluate()` call.

    Attributes:
        average_return: Mean `WalkForwardWindow.total_return` across
            every window.
        average_win_rate: Mean `WalkForwardWindow.win_rate` across
            every window.
        average_drawdown: Mean `WalkForwardWindow.max_drawdown_pct`
            across every window.
        average_sharpe: Mean `WalkForwardWindow.sharpe_ratio` across
            every window.
        best_window: The `WalkForwardWindow` with the highest
            `total_return`.
        worst_window: The `WalkForwardWindow` with the lowest
            `total_return`.
    """

    average_return: Decimal
    average_win_rate: float
    average_drawdown: float
    average_sharpe: float
    best_window: WalkForwardWindow
    worst_window: WalkForwardWindow


@dataclass(frozen=True)
class WalkForwardResult:
    """
    Everything produced by one `BacktestRunner.walk_forward_evaluate()`
    call: one `WalkForwardWindow` per train/test split (in chronological
    order), plus one aggregate `WalkForwardSummary`.

    Attributes:
        symbol: Trading pair/instrument the walk-forward evaluation ran
            for.
        timeframe: Candle interval the walk-forward evaluation ran on.
        windows: One `WalkForwardWindow` per train/test split, in
            chronological order.
        summary: The aggregate `WalkForwardSummary` across every
            window.
        metadata: Free-form additional traceability details (e.g.
            `train_size`/`test_size`/`step_size` and the resulting
            window count).
    """

    symbol: str
    timeframe: str
    windows: list[WalkForwardWindow]
    summary: WalkForwardSummary
    metadata: dict[str, Any] = field(default_factory=dict)


def _summarize_walk_forward_windows(windows: Sequence[WalkForwardWindow]) -> WalkForwardSummary:
    """
    Build a `WalkForwardSummary` from an already-produced, non-empty
    sequence of `WalkForwardWindow`s -- pure aggregation only (mean
    return/win rate/drawdown/Sharpe ratio, plus the best/worst window
    by `total_return`, the same primary metric `compare_strategies()`
    already sorts by). Every value summarized here was already computed
    by `backtesting.metrics.calculate_metrics()` for that window's own
    run -- this function invents no new metric definition.
    """
    count = len(windows)
    average_return = sum((window.total_return for window in windows), Decimal("0")) / count
    average_win_rate = sum(window.win_rate for window in windows) / count
    average_drawdown = sum(window.max_drawdown_pct for window in windows) / count
    average_sharpe = sum(window.sharpe_ratio for window in windows) / count
    best_window = max(windows, key=lambda window: window.total_return)
    worst_window = min(windows, key=lambda window: window.total_return)
    return WalkForwardSummary(
        average_return=average_return,
        average_win_rate=average_win_rate,
        average_drawdown=average_drawdown,
        average_sharpe=average_sharpe,
        best_window=best_window,
        worst_window=worst_window,
    )


class BacktestRunner:
    """
    Runs Data -> Indicators -> Analysis -> Signals -> Strategy ->
    Backtesting -> Metrics -> Report for one symbol/timeframe, using
    dependency injection for every stage (matching this project's DI
    convention -- see `PROJECT_RULES.md` Section 5), the same
    convention `app.pipeline.MarketPipeline` already follows.
    """

    def __init__(
        self,
        data_engine: DataEngine,
        *,
        indicator_specs: Optional[Sequence[tuple[BaseIndicator, dict[str, str]]]] = None,
        analyzer: Optional[BaseAnalyzer] = None,
        signal_generator: Optional[BaseSignalGenerator] = None,
        backtester: Optional[BaseBacktester] = None,
    ) -> None:
        if not isinstance(data_engine, DataEngine):
            raise BacktestRunnerConfigurationError(
                f"data_engine must be a DataEngine, got {type(data_engine).__name__}"
            )
        self.data_engine = data_engine

        specs = list(indicator_specs) if indicator_specs is not None else _default_indicator_specs()
        for indicator, kwargs in specs:
            if not isinstance(indicator, BaseIndicator):
                raise BacktestRunnerConfigurationError(
                    f"indicator_specs entries must wrap a BaseIndicator, got {type(indicator).__name__}"
                )
            if not isinstance(kwargs, dict):
                raise BacktestRunnerConfigurationError(
                    f"indicator_specs kwargs must be a dict, got {type(kwargs).__name__}"
                )
        self.indicator_specs = specs

        self.analyzer = analyzer if analyzer is not None else AnalysisAggregator()
        if not isinstance(self.analyzer, BaseAnalyzer):
            raise BacktestRunnerConfigurationError(
                f"analyzer must be a BaseAnalyzer, got {type(self.analyzer).__name__}"
            )

        self.signal_generator = signal_generator if signal_generator is not None else SignalAggregator()
        if not isinstance(self.signal_generator, BaseSignalGenerator):
            raise BacktestRunnerConfigurationError(
                f"signal_generator must be a BaseSignalGenerator, got {type(self.signal_generator).__name__}"
            )

        self.backtester = backtester if backtester is not None else BasicBacktester()
        if not isinstance(self.backtester, BaseBacktester):
            raise BacktestRunnerConfigurationError(
                f"backtester must be a BaseBacktester, got {type(self.backtester).__name__}"
            )

    def run(
        self,
        symbol: str,
        timeframe: str,
        *,
        strategy: Optional[BaseStrategy] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
        initial_portfolio: Optional[Portfolio] = None,
        risk_free_rate: float = 0.0,
        annualization_factor: float = 1.0,
    ) -> BacktestRunResult:
        """
        Execute one full historical backtest for one symbol/timeframe.

        Parameters
        ----------
        symbol, timeframe:
            Identify which already-downloaded candle series to replay
            (see `DataEngine.download_history`/`update_latest`).
        strategy:
            The `BaseStrategy` whose decisions are replayed, once per
            historical candle, against a genuine `strategies.context.
            StrategyContext` built from this run's own Analysis and
            Signal stages (see the module docstring). Defaults to a
            plain `strategies.basic_strategy.BasicStrategy()` when
            omitted -- `backtesting` (and this module) remain a
            consumer of whatever strategy it is given; this module
            invents no trading rules of its own.
        start_time, end_time, limit:
            Optional bounds forwarded to `DataEngine.load_history` to
            select a specific historical window to replay.
        initial_portfolio:
            The starting `Portfolio` (cash and positions) the backtest
            begins from. Defaults to a fresh cash-only portfolio
            (`DEFAULT_INITIAL_CASH_BALANCE` in `DEFAULT_BASE_CURRENCY`)
            when omitted.
        risk_free_rate, annualization_factor:
            Forwarded to `backtesting.metrics.calculate_metrics`'s
            Sharpe-ratio calculation.

        Returns
        -------
        BacktestRunResult

        Raises
        ------
        BacktestRunnerConfigurationError
            `symbol`/`timeframe` is not a non-empty string, or
            `strategy`/`initial_portfolio` is supplied but not the
            expected type.
        BacktestRunnerDataError
            No candle history is available for `symbol`/`timeframe`;
            download/update it via `DataEngine` first.
        BacktestRunnerExecutionError
            The backtest replay itself failed (wraps the underlying
            `backtesting.exceptions.BacktestError`).
        """
        if not isinstance(symbol, str) or not symbol.strip():
            raise BacktestRunnerConfigurationError(f"symbol must be a non-empty str, got {symbol!r}")
        if not isinstance(timeframe, str) or not timeframe.strip():
            raise BacktestRunnerConfigurationError(
                f"timeframe must be a non-empty str, got {timeframe!r}"
            )
        symbol = symbol.upper()

        strategy = strategy if strategy is not None else BasicStrategy()
        if not isinstance(strategy, BaseStrategy):
            raise BacktestRunnerConfigurationError(
                f"strategy must be a BaseStrategy, got {type(strategy).__name__}"
            )

        portfolio = initial_portfolio if initial_portfolio is not None else _default_initial_portfolio()
        if not isinstance(portfolio, Portfolio):
            raise BacktestRunnerConfigurationError(
                f"initial_portfolio must be a Portfolio, got {type(portfolio).__name__}"
            )

        # 1. Data
        candles = self.data_engine.load_history(
            symbol, timeframe, start_time=start_time, end_time=end_time, limit=limit
        )
        if not candles:
            raise BacktestRunnerDataError(
                f"No candle history available for {symbol}/{timeframe}; "
                "download/update it via DataEngine first."
            )
        core_candles: list[CoreCandle] = [_to_core_candle(candle) for candle in candles]

        # 2. Indicators -- each computed once, in batch, over the whole
        # replay window (see "Point-in-time replay" in the module
        # docstring for why this never introduces look-ahead). One bad
        # indicator (e.g. not enough candles for its period) must not
        # sink the whole run -- it is simply absent from every candle's
        # Analysis stage, the same "absence only lowers confidence"
        # convention `app.pipeline.MarketPipeline` already applies.
        frame = _candles_to_dataframe(candles)
        raw_indicator_results: list[Any] = []
        for indicator, extra_kwargs in self.indicator_specs:
            try:
                raw_indicator_results.append(indicator.calculate(frame, **extra_kwargs))
            except Exception:  # noqa: BLE001 - one bad indicator must not sink the run
                continue

        # 3-5. Analysis -> Signal -> Strategy, replayed once per
        # historical candle, in strict chronological order.
        strategy_results_by_candle_index: dict[int, StrategyResult] = {}
        for index, core_candle in enumerate(core_candles):
            indicator_results: list[CoreIndicatorResult] = []
            for raw_result in raw_indicator_results:
                translated = _to_core_indicator_result_at_index(
                    raw_result,
                    index,
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=core_candle.close_time,
                )
                if translated is not None:
                    indicator_results.append(translated)

            market_state = MarketState(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=core_candle.close_time,
                latest_candle=core_candle,
                indicators=indicator_results,
            )

            analysis_context = AnalysisContext(
                symbol=symbol,
                timeframe=timeframe,
                market_state=market_state,
                indicators=indicator_results,
            )
            try:
                analysis_results = [self.analyzer.analyze(analysis_context)]
            except AnalysisError:
                analysis_results = []

            signal_context = SignalContext(
                symbol=symbol, timeframe=timeframe, analysis_results=analysis_results
            )
            try:
                signal_result = self.signal_generator.generate(signal_context)
            except SignalError:
                signal_result = None

            strategy_context = StrategyContext(
                symbol=symbol,
                timeframe=timeframe,
                analysis_results=analysis_results,
                signal_result=signal_result,
                metadata={"candle_index": index},
            )
            try:
                strategy_results_by_candle_index[index] = strategy.decide(strategy_context)
            except InsufficientStrategyDataError:
                continue

        replay_strategy = _PrecomputedStrategyReplay(
            name=strategy.name, results_by_candle_index=strategy_results_by_candle_index
        )

        # 6. Backtesting
        try:
            context = BacktestContext(
                symbol=symbol,
                timeframe=timeframe,
                candles=core_candles,
                strategy=replay_strategy,
                initial_portfolio=portfolio,
                metadata={"start_time": start_time, "end_time": end_time, "limit": limit},
            )
            result = self.backtester.run(context)
        except BacktestError as exc:
            raise BacktestRunnerExecutionError(str(exc)) from exc

        # 7. Metrics
        metrics = calculate_metrics(
            result,
            portfolio,
            risk_free_rate=risk_free_rate,
            annualization_factor=annualization_factor,
        )

        # 8. Report
        report = BacktestReport(result, metrics)

        # Annualized return (Backtesting Part 5) -- derived purely from
        # `metrics.total_return_pct` (already computed above) and the
        # elapsed wall-clock time between the first and last replayed
        # candle; see the module docstring's "Backtesting Part 5"
        # section for the exact CAGR-style formula and its fallback.
        period_seconds = (
            core_candles[-1].close_time - core_candles[0].open_time
        ).total_seconds()
        period_days = period_seconds / 86400.0 if period_seconds > 0 else 0.0
        compounding_base = 1.0 + metrics.total_return_pct
        if period_days > 0 and compounding_base > 0:
            annual_return = compounding_base ** (365.25 / period_days) - 1.0
        else:
            annual_return = metrics.total_return_pct

        return BacktestRunResult(
            symbol=symbol,
            timeframe=timeframe,
            candle_count=len(core_candles),
            initial_portfolio=portfolio,
            result=result,
            metrics=metrics,
            report=report,
            metadata={
                "start_time": start_time,
                "end_time": end_time,
                "limit": limit,
                "candles_with_strategy_result": len(strategy_results_by_candle_index),
                "period_days": period_days,
                "annual_return": annual_return,
            },
        )

    def compare_strategies(
        self,
        symbol: str,
        timeframe: str,
        strategies: Sequence[BaseStrategy],
        *,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
        initial_portfolio: Optional[Portfolio] = None,
        risk_free_rate: float = 0.0,
        annualization_factor: float = 1.0,
    ) -> StrategyComparisonResult:
        """
        Run the exact same pipeline `run()` already performs -- Data ->
        Indicators -> Analysis -> Signal -> Strategy -> Backtesting ->
        Metrics -> Report -- once per strategy in `strategies`, against
        the same symbol/timeframe/historical window/starting portfolio,
        and return one `StrategyComparisonResult` with every strategy's
        performance ranked by total return (highest first), plus the
        best- and worst-performing strategy picked out directly.

        Adds no new calculation/interpretation/decision logic of its
        own: every stage's actual work still happens exactly as it
        already does inside `run()` (and, beneath it, `data/`,
        `analysis/`, `signals/`, `strategies/`, `backtesting/`) -- this
        method only calls `run()` once per strategy and sorts the
        resulting metrics. No automatic/parameter optimization, no AI,
        and no change to any strategy's own decision logic.

        Parameters
        ----------
        symbol, timeframe:
            Identify which already-downloaded candle series to replay
            for every strategy (see `DataEngine.download_history`/
            `update_latest`).
        strategies:
            A non-empty sequence of `BaseStrategy` instances to compare.
            Each is run independently, in the order given, against the
            same historical data and starting portfolio -- one
            strategy's run never affects another's.
        start_time, end_time, limit:
            Optional bounds forwarded to `DataEngine.load_history` (via
            `run()`) to select a specific historical window to replay
            for every strategy.
        initial_portfolio:
            The starting `Portfolio` every strategy's run begins from.
            Defaults to a fresh cash-only portfolio when omitted (see
            `run()`). The same starting state is used for every
            strategy so their results are directly comparable; it is
            never mutated or shared as live state between runs (each
            `run()`/`BaseBacktester.run()` call deep-copies it before
            touching any position/cash state).
        risk_free_rate, annualization_factor:
            Forwarded to `backtesting.metrics.calculate_metrics`'s
            Sharpe-ratio calculation for every strategy's run.

        Returns
        -------
        StrategyComparisonResult

        Raises
        ------
        BacktestRunnerConfigurationError
            `strategies` is not a non-empty sequence of `BaseStrategy`
            instances, or any of `run()`'s own configuration
            validation fails (`symbol`/`timeframe`/`initial_portfolio`).
        BacktestRunnerDataError
            No candle history is available for `symbol`/`timeframe`;
            download/update it via `DataEngine` first.
        BacktestRunnerExecutionError
            Any individual strategy's backtest replay failed (wraps the
            underlying `backtesting.exceptions.BacktestError`).
        """
        if isinstance(strategies, (str, bytes)) or not isinstance(strategies, Sequence):
            raise BacktestRunnerConfigurationError(
                f"strategies must be a non-empty sequence of BaseStrategy instances, got {type(strategies).__name__}"
            )
        if len(strategies) == 0:
            raise BacktestRunnerConfigurationError("strategies must be a non-empty sequence")
        for strategy in strategies:
            if not isinstance(strategy, BaseStrategy):
                raise BacktestRunnerConfigurationError(
                    f"every entry in strategies must be a BaseStrategy, got {type(strategy).__name__}"
                )

        entries: list[StrategyComparisonEntry] = []
        resolved_symbol = symbol
        for strategy in strategies:
            run_result = self.run(
                symbol,
                timeframe,
                strategy=strategy,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
                initial_portfolio=initial_portfolio,
                risk_free_rate=risk_free_rate,
                annualization_factor=annualization_factor,
            )
            resolved_symbol = run_result.symbol
            entries.append(
                StrategyComparisonEntry(
                    strategy_name=strategy.name,
                    total_return=run_result.metrics.total_return,
                    annual_return=run_result.metadata["annual_return"],
                    win_rate=run_result.metrics.win_rate,
                    profit_factor=run_result.metrics.profit_factor,
                    sharpe_ratio=run_result.metrics.sharpe_ratio,
                    max_drawdown=run_result.metrics.max_drawdown_pct,
                    total_trades=run_result.metrics.total_trades,
                    report=run_result.report,
                    run_result=run_result,
                )
            )

        # Rank by total return, highest first -- the same primary
        # metric `walk_forward_evaluate()`'s own best/worst-window pick
        # (`_summarize_walk_forward_windows`) already uses one method
        # up, kept consistent here.
        entries.sort(key=lambda entry: entry.total_return, reverse=True)

        return StrategyComparisonResult(
            symbol=resolved_symbol,
            timeframe=timeframe,
            ranking=entries,
            best_strategy=entries[0],
            worst_strategy=entries[-1],
            metadata={"strategy_count": len(entries)},
        )

    def walk_forward_evaluate(
        self,
        symbol: str,
        timeframe: str,
        *,
        train_size: int,
        test_size: int,
        step_size: Optional[int] = None,
        strategy: Optional[BaseStrategy] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
        initial_portfolio: Optional[Portfolio] = None,
        risk_free_rate: float = 0.0,
        annualization_factor: float = 1.0,
    ) -> WalkForwardResult:
        """
        Split an already-downloaded candle series into a sequence of
        non-overlapping train/test windows and run the exact same
        `run()` pipeline once per window, bounded to that window's
        testing period only -- see the module docstring's "Walk-Forward
        Evaluation" section for why the training period itself is never
        fed into `run()`/a strategy/any calculation here.

        Adds no new calculation/interpretation/decision logic of its
        own: every stage's actual work still happens exactly as it
        already does inside `run()` (and, beneath it, `data/`,
        `analysis/`, `signals/`, `strategies/`, `backtesting/`) -- this
        method only slices the already-loaded candle series into
        windows, calls `run()` once per window's testing period, and
        aggregates the resulting metrics. No parameter optimization, no
        strategy fitting/tuning, no AI, and no change to any strategy's
        own decision logic.

        Parameters
        ----------
        symbol, timeframe:
            Identify which already-downloaded candle series to split
            into windows and replay (see `DataEngine.download_history`/
            `update_latest`).
        train_size, test_size:
            Number of candles in each window's training and testing
            period, respectively. Both must be positive integers.
        step_size:
            Number of candles to advance `train_start` by between
            windows. Defaults to `test_size` (fully non-overlapping,
            back-to-back windows) when omitted. Must be a positive
            integer when given.
        strategy:
            The `BaseStrategy` evaluated in every window's testing
            period (forwarded to `run()` unchanged for each window).
            Defaults to a plain `strategies.basic_strategy.BasicStrategy()`
            when omitted, matching `run()`'s own default -- this method
            invents no trading rules of its own and never adapts the
            strategy between windows.
        start_time, end_time, limit:
            Optional bounds forwarded to `DataEngine.load_history` to
            select the specific historical series that gets split into
            windows (the same bounds `run()` itself accepts).
        initial_portfolio:
            The starting `Portfolio` every window's testing-period run
            begins from. Defaults to a fresh cash-only portfolio when
            omitted (see `run()`). The same starting state is used for
            every window so their results are directly comparable; it
            is never mutated or shared as live state between windows.
        risk_free_rate, annualization_factor:
            Forwarded to `backtesting.metrics.calculate_metrics`'s
            Sharpe-ratio calculation for every window's run.

        Returns
        -------
        WalkForwardResult

        Raises
        ------
        BacktestRunnerConfigurationError
            `symbol`/`timeframe` is not a non-empty string, or
            `train_size`/`test_size`/`step_size` is not a positive
            integer, or any of `run()`'s own configuration validation
            fails for a given window (`strategy`/`initial_portfolio`).
        BacktestRunnerDataError
            No candle history is available for `symbol`/`timeframe`, or
            there are not enough candles to build even one full
            train/test window.
        BacktestRunnerExecutionError
            Any individual window's backtest replay failed (wraps the
            underlying `backtesting.exceptions.BacktestError`).
        """
        if not isinstance(symbol, str) or not symbol.strip():
            raise BacktestRunnerConfigurationError(f"symbol must be a non-empty str, got {symbol!r}")
        if not isinstance(timeframe, str) or not timeframe.strip():
            raise BacktestRunnerConfigurationError(
                f"timeframe must be a non-empty str, got {timeframe!r}"
            )
        upper_symbol = symbol.upper()

        if isinstance(train_size, bool) or not isinstance(train_size, int) or train_size <= 0:
            raise BacktestRunnerConfigurationError(
                f"train_size must be a positive int, got {train_size!r}"
            )
        if isinstance(test_size, bool) or not isinstance(test_size, int) or test_size <= 0:
            raise BacktestRunnerConfigurationError(
                f"test_size must be a positive int, got {test_size!r}"
            )
        resolved_step_size = step_size if step_size is not None else test_size
        if (
            isinstance(resolved_step_size, bool)
            or not isinstance(resolved_step_size, int)
            or resolved_step_size <= 0
        ):
            raise BacktestRunnerConfigurationError(
                f"step_size must be a positive int, got {step_size!r}"
            )

        # Load the full candle series once, purely to compute each
        # window's train/test time boundaries -- the actual backtest
        # replay for each window still only ever happens inside run()
        # below, bounded to that window's own testing period.
        candles = self.data_engine.load_history(
            upper_symbol, timeframe, start_time=start_time, end_time=end_time, limit=limit
        )
        if not candles:
            raise BacktestRunnerDataError(
                f"No candle history available for {upper_symbol}/{timeframe}; "
                "download/update it via DataEngine first."
            )

        windows: list[WalkForwardWindow] = []
        window_number = 1
        train_start_idx = 0
        while True:
            train_end_idx = train_start_idx + train_size  # exclusive
            test_end_idx = train_end_idx + test_size  # exclusive
            if test_end_idx > len(candles):
                break

            train_period = (
                candles[train_start_idx].open_time,
                candles[train_end_idx - 1].open_time,
            )
            test_period = (
                candles[train_end_idx].open_time,
                candles[test_end_idx - 1].open_time,
            )

            run_result = self.run(
                upper_symbol,
                timeframe,
                strategy=strategy,
                start_time=test_period[0],
                end_time=test_period[1],
                initial_portfolio=initial_portfolio,
                risk_free_rate=risk_free_rate,
                annualization_factor=annualization_factor,
            )

            windows.append(
                WalkForwardWindow(
                    window_number=window_number,
                    train_period=train_period,
                    test_period=test_period,
                    total_return=run_result.metrics.total_return,
                    win_rate=run_result.metrics.win_rate,
                    profit_factor=run_result.metrics.profit_factor,
                    max_drawdown_pct=run_result.metrics.max_drawdown_pct,
                    sharpe_ratio=run_result.metrics.sharpe_ratio,
                    number_of_trades=run_result.metrics.total_trades,
                    run_result=run_result,
                )
            )

            window_number += 1
            train_start_idx += resolved_step_size

        if not windows:
            raise BacktestRunnerDataError(
                f"Not enough candle history for {upper_symbol}/{timeframe} to build even one "
                f"walk-forward window (train_size={train_size}, test_size={test_size}); "
                f"only {len(candles)} candles are available."
            )

        summary = _summarize_walk_forward_windows(windows)

        return WalkForwardResult(
            symbol=upper_symbol,
            timeframe=timeframe,
            windows=windows,
            summary=summary,
            metadata={
                "window_count": len(windows),
                "train_size": train_size,
                "test_size": test_size,
                "step_size": resolved_step_size,
                "candle_count": len(candles),
            },
        )
