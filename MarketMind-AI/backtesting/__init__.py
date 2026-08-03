"""
backtesting package
---------------------
Purpose:
    The Backtesting Engine: replays historical `core.entities.candle.
    Candle` data through a given `strategies.base_strategy.BaseStrategy`
    instance against a starting `core.entities.portfolio.Portfolio`,
    standardizing the outcome into a single `BacktestResult`. Mirrors
    the role `analysis/`, `signals/`, `strategies.risk_management`, and
    `strategies/` each play for their own predecessor's output: this
    layer consumes what `strategies/` produces without deciding
    anything new about it.

    `backtesting/` is a consumer, never a strategy author (see
    `PROJECT_RULES.md` Section 1, principle 5): it replays whatever
    strategy/signals it is given and reports results; it must never
    define trading rules of its own.

Contents (Backtesting Engine Part 1 -- foundation):
    - `BaseBacktester` (`base.py`): abstract base every concrete
      backtester implements.
    - `BacktestContext` (`context.py`): immutable bundle of historical
      `Candle` data, a `BaseStrategy` instance, and a starting
      `Portfolio` for one symbol/timeframe run.
    - `BacktestResult` (`result.py`): standardized output --
      `final_portfolio`/`summary`/`trades`/`metadata`.
    - `BacktestError` hierarchy (`exceptions.py`).
    - Shared validation helpers (`utils.py`).

Contents (Backtesting Engine Part 2 -- first concrete backtester):
    - `BasicBacktester` (`basic_backtester.py`): the first concrete
      `BaseBacktester`. Replays `BacktestContext.candles` sequentially
      and chronologically through `BacktestContext.strategy`, building
      a minimal `strategies.context.StrategyContext` per candle (no
      `AnalysisResult`/`SignalResult`/`RiskResult` of its own -- the
      current candle is exposed only via `StrategyContext.metadata`)
      and consuming only the resulting `strategies.result.
      StrategyResult.action`. A `BUY` opens one long `Position` with
      the entire available cash at the candle's `close` price (a no-op
      if a position is already open or no cash is available); a `SELL`
      closes an existing open position in full at the candle's `close`
      price (a no-op if none is open); `HOLD` is always a no-op. No
      slippage, no commissions, no leverage, and no performance
      statistics are modeled. A strategy raising `strategies.
      exceptions.InsufficientStrategyDataError` for a given candle is
      treated as "skip this candle" (recorded in
      `metadata["skipped_candles"]`), never as a fatal error for the
      whole run. Never mutates `BacktestContext` or anything reachable
      from it -- `initial_portfolio` is deep-copied before any trade
      is recorded.

Explicitly out of scope for Part 2 (deferred to later Backtesting
Engine parts):
    - PnL calculation beyond a `Position`'s own `realized_pnl` field.
    - Performance statistics (Sharpe ratio, max drawdown, win rate,
      profit factor, etc.).
    - Aggregation across multiple runs.
    - Human-readable report generation.
    - Position sizing/risk management, multiple concurrent positions
      per symbol, short selling, slippage, and commissions/fees.

Contents (Backtesting Engine Part 3 -- portfolio simulation helper):
    - `PortfolioSimulator` (`portfolio_simulator.py`): a standalone,
      deterministic helper that simulates a `Portfolio`'s cash/position
      state -- opening and closing positions, calculating realized and
      unrealized PnL, and keeping `total_equity` current. Factors the
      exact simulation mechanics `BasicBacktester` (Part 2) already
      implements inline into their own reusable, independently-tested
      class, so any current or future `BaseBacktester` can share them
      instead of re-implementing them. Long-only, at most one open
      position per symbol at a time (no pyramiding) -- the same
      execution model Part 2 already uses. No leverage, no margin, no
      slippage, no commissions/fees, no partial fills, no portfolio
      optimization, and no performance metrics/reporting (still
      deferred to `metrics.py`/`report.py`, see "Planned contents"
      below). Purely additive: `BasicBacktester` itself is left
      completely untouched and does not use `PortfolioSimulator`.

Contents (Backtesting Engine Part 4 -- performance statistics):
    - `metrics.py`: performance-statistics calculations for an
      already-produced `BacktestResult`, evaluated against the
      `Portfolio` its run started from.
        - `BacktestMetrics`: standardized, frozen output container
          (trade counts, `win_rate`, gross profit/loss, `profit_factor`,
          average/largest win and loss, initial/final equity, total
          return, an `equity_curve`, `max_drawdown_pct`/`_amount`,
          `sharpe_ratio`, and a traceability `metadata` dict).
        - `calculate_metrics(result, initial_portfolio, ...)`: the
          main entry point, deriving every statistic from the closed
          `Position` entries on `result.final_portfolio` and the
          supplied starting `Portfolio` -- it does not run a backtest
          or simulate any trade itself.
        - Smaller composable building blocks, also usable on their
          own: `win_rate`, `profit_factor`, `compute_equity_curve`,
          `max_drawdown`, `sharpe_ratio`.
    - Purely additive: `base.py`, `context.py`, `result.py`,
      `exceptions.py`, `utils.py`, `basic_backtester.py`, and
      `portfolio_simulator.py` are all left completely untouched, and
      `metrics.py` introduces no new domain concepts or exception
      types -- it reuses `core.entities.portfolio.Portfolio`,
      `core.entities.position.Position`, `core.enums.PositionStatus`,
      `backtesting.result.BacktestResult`, and
      `backtesting.exceptions.BacktestValidationError` exactly as they
      already exist.
    - Deterministic and side-effect free: no randomness, no
      wall-clock reads, no network/database/file I/O, no AI, no
      broker/order-execution integration, no optimization (parameter
      search/tuning), and no report/chart generation -- `report.py`
      (human-readable summaries) remains a separate, still-pending
      milestone.

Contents (Backtesting Engine Part 5 -- report generation):
    - `report.py`: `BacktestReport`, a deterministic summary generator
      wrapping an already-produced `BacktestResult` (Parts 1/2) and an
      already-produced `BacktestMetrics` (Part 4). Exposes `summary()`
      (a short one-paragraph string), `detailed_summary()` (a longer,
      section-based string), `trades_summary()` (a structured dict of
      every recorded `Trade`), `metrics_summary()` (a structured dict
      of every `BacktestMetrics` field), and `full_report()` (all four
      combined into one dict). Every public method returns only a
      `str` or a `dict`. Purely additive and read-only: `base.py`,
      `context.py`, `result.py`, `exceptions.py`, `utils.py`,
      `basic_backtester.py`, `portfolio_simulator.py`, and `metrics.py`
      are all left completely untouched; `report.py` computes nothing
      new -- it only formats what `BacktestResult`/`BacktestMetrics`
      already contain. No charts, no plotting libraries, no HTML, no
      PDF, no CSV export, no file writing, no logging, no AI, no
      broker/order-execution/replay logic.

Planned contents (future Backtesting Engine parts):
    - Additional concrete backtesters (e.g. one that consumes
      `signals.result.SignalResult` directly, or supports multiple
      concurrent positions/short selling/fees).
"""

from __future__ import annotations

from backtesting.base import BaseBacktester
from backtesting.basic_backtester import BasicBacktester
from backtesting.context import BacktestContext
from backtesting.exceptions import (
    BacktestError,
    BacktesterConfigurationError,
    BacktestValidationError,
    InsufficientBacktestDataError,
    InvalidBacktestContextError,
)
from backtesting.metrics import (
    BacktestMetrics,
    calculate_metrics,
    compute_equity_curve,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    win_rate,
)
from backtesting.portfolio_simulator import PortfolioSimulator
from backtesting.report import BacktestReport
from backtesting.result import BacktestResult

__all__ = [
    "BaseBacktester",
    "BasicBacktester",
    "BacktestContext",
    "BacktestResult",
    "PortfolioSimulator",
    "BacktestMetrics",
    "calculate_metrics",
    "win_rate",
    "profit_factor",
    "compute_equity_curve",
    "max_drawdown",
    "sharpe_ratio",
    "BacktestReport",
    "BacktestError",
    "BacktestValidationError",
    "InvalidBacktestContextError",
    "InsufficientBacktestDataError",
    "BacktesterConfigurationError",
]
