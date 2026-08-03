"""
app package
------------
Purpose:
    This is the "application layer" in Clean Architecture terms.

    It will orchestrate use cases by coordinating `core` (domain logic),
    `data` (market data access), `services` (external integrations),
    `analysis` (technical/news/AI analysis), and `strategies` (trading
    strategies) -- without containing business rules itself.

    Think of this layer as the "conductor": it knows WHEN and in WHAT
    ORDER things happen, but delegates HOW they happen to the
    underlying layers.

Contents:
    - pipeline.py: `MarketPipeline`, the first use case. Wires
      Data -> Indicators -> Analysis -> Signals (in that order) for one
      symbol/timeframe, via dependency-injected `DataEngine`/
      `BaseAnalyzer`/`BaseSignalGenerator`. Adds no calculation/
      interpretation/decision logic of its own -- every stage's actual
      work still happens inside the package that already owns it.
    - main.py: `MainApplication` (Main Application Part 1), the
      application's composition root. Holds one instance of every
      already-implemented top-level engine/service (`DataEngine`,
      `AnalysisAggregator`, `SignalAggregator`, `StrategyAggregator`,
      `BasicRiskManager`, `PortfolioManager`, `BasicBacktester`,
      `services.SignalEngine`), wired together via dependency injection,
      plus configuration loading via `config.settings.get_settings()`.
      Constructor only -- no orchestration, no analysis execution, no
      AI, no broker, no UI, no CLI, and no business logic of any kind;
      sequencing these engines is deferred to a future Main Application
      part.
    - backtest_runner.py: `BacktestRunner`, the second use case. Wires
      Data -> Backtesting -> Metrics -> Report (in that order) for one
      symbol/timeframe, via a dependency-injected `DataEngine`/
      `BaseBacktester`, running a dependency-injected `BaseStrategy`
      (defaulting to `BasicStrategy`) against real historical candles
      and a starting `Portfolio`. Closes the "assemble a
      `BacktestContext` from real historical data and a real strategy
      end-to-end" gap `PROJECT_STATE.md` documents under `backtesting/`.
      Adds no calculation/interpretation/decision logic of its own --
      every stage's actual work still happens inside the package that
      already owns it (`data/`, `backtesting/`).
    - exceptions.py: the `AppError` hierarchy for this layer.

Planned contents (future versions):
    - `MainApplication`'s own orchestration behavior (a future Main
      Application part), extending `pipeline.py`'s flow through
      `strategies/`, risk/portfolio management, and execution.
    - bootstrap.py: application startup/wiring (dependency injection).

No trading logic (decisions, risk, execution) implemented yet --
`pipeline.py` stops at Signals, deliberately, `MainApplication`
(Part 1) only constructs/stores its collaborators, and
`backtest_runner.py` only replays a strategy's own decisions -- it
invents no trading rules of its own.
"""

from __future__ import annotations

from app.backtest_runner import BacktestRunner, BacktestRunResult
from app.exceptions import (
    AppError,
    BacktestRunnerConfigurationError,
    BacktestRunnerDataError,
    BacktestRunnerExecutionError,
    PipelineAnalysisError,
    PipelineConfigurationError,
    PipelineDataError,
    PipelineSignalError,
)
from app.main import MainApplication
from app.pipeline import MarketPipeline, PipelineResult

__all__ = [
    "MarketPipeline",
    "PipelineResult",
    "MainApplication",
    "BacktestRunner",
    "BacktestRunResult",
    "AppError",
    "PipelineConfigurationError",
    "PipelineDataError",
    "PipelineAnalysisError",
    "PipelineSignalError",
    "BacktestRunnerConfigurationError",
    "BacktestRunnerDataError",
    "BacktestRunnerExecutionError",
]

