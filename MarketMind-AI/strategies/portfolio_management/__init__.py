"""
strategies/portfolio_management package
------------------------------------------
Purpose:
    Portfolio Management: evaluates the overall portfolio state --
    given a candidate `strategies.result.StrategyResult`, its
    `strategies.risk_management.result.RiskResult`, and the current
    `core.entities.portfolio.Portfolio` -- and decides whether a new
    position is allowed, standardizing that evaluation into a single
    `PortfolioResult`. Mirrors the role `strategies.risk_management`
    plays one layer down: each layer interprets/standardizes its
    predecessor's output without deciding what to do about it.

Contents (Portfolio Management Part 1 -- foundation, new this milestone):
    - `BasePortfolioManager` (`base.py`): abstract base every concrete
      portfolio manager implements. Consumes a `PortfolioContext` and
      produces a `PortfolioResult` via an abstract `evaluate()` method,
      plus shared `validate_context`/`_build_result` helpers --
      mirroring the exact role `analysis.base.BaseAnalyzer`,
      `signals.base.BaseSignalGenerator`, `strategies.base_strategy.
      BaseStrategy`, and `strategies.risk_management.base.
      BaseRiskManager` play one layer down each.
    - `PortfolioContext` (`context.py`): immutable bundle of the
      current `core.entities.portfolio.Portfolio` (required), an
      optional `strategies.result.StrategyResult` (the candidate
      trading decision under consideration), and an optional
      `strategies.risk_management.result.RiskResult` (that decision's
      risk evaluation) for one symbol/timeframe -- no new domain
      concepts introduced.
    - `PortfolioResult` (`result.py`): standardized output --
      `new_positions_allowed` (bool), `confidence`, `summary`,
      `metadata`. Deliberately minimal: no target allocation, no
      rebalancing instructions, no order-id, no
      `portfolio_manager_name` field (mirroring `RiskResult`'s
      omission of `risk_manager_name`).
    - `PortfolioError` hierarchy (`exceptions.py`): `PortfolioError` ->
      `PortfolioValidationError` -> `InvalidPortfolioContextError`,
      plus `InsufficientPortfolioDataError` and
      `PortfolioManagerConfigurationError`.
    - Shared validation helpers (`utils.py`).

    Framework only -- Portfolio Management Part 1 ships no concrete
    portfolio manager, no allocation algorithm, no rebalancing logic,
    and no broker integration. Consumes existing `StrategyResult`,
    `RiskResult`, and `Portfolio`; produces only `PortfolioResult`.
    Imported directly (`from strategies.portfolio_management import
    BasePortfolioManager, PortfolioContext, PortfolioResult, ...`), not
    re-exported through `strategies/__init__.py`, the same convention
    `strategies.risk_management` already uses relative to
    `strategies/`.

Also contains (Portfolio Management Part 2 -- first concrete
implementation):
    - `BasicPortfolioManager` (`basic_portfolio_manager.py`): the
      first concrete `BasePortfolioManager`, mirroring the pattern
      `strategies.risk_management.basic_risk_manager.BasicRiskManager`
      established one layer down. Gates a candidate new position on
      four deterministic checks -- open-position count (against a
      configurable `max_open_positions`), aggregate portfolio exposure
      (against a configurable `max_exposure_ratio`), single-symbol
      concentration (against a configurable
      `max_symbol_exposure_ratio`, independent of the aggregate
      check), and, when available, whether the candidate
      `StrategyResult.action` is directional (not `HOLD`) and whether
      the candidate `RiskResult.approved` is `True` -- with every
      intermediate value recorded in `PortfolioResult.metadata` for
      traceability. `confidence` is derived only from how much of the
      optional `strategy_result`/`risk_result` context was available,
      never from the pass/fail decision itself. No scoring,
      optimization, allocation, sizing, rebalancing, broker
      integration, or AI -- every check is a plain threshold
      comparison.

Also contains (Portfolio Management Part 3 -- composite manager):
    - `PortfolioManager` (`portfolio_manager.py`): itself a concrete
      `BasePortfolioManager` that combines the `PortfolioResult`s of
      one or more injected `BasePortfolioManager` instances (defaulting
      to a single `BasicPortfolioManager()` when none are supplied)
      into one final `PortfolioResult`, mirroring the exact role
      `strategies.aggregator.StrategyAggregator`/`signals.aggregator.
      SignalAggregator`/`analysis.aggregator.AnalysisAggregator`
      already play one, two, and three layers down, respectively.
      Since `PortfolioResult` has no numeric score field (only a
      boolean `new_positions_allowed`), each sub-manager's decision is
      represented as a signed unit vote (`+1.0` allowed, `-1.0`
      blocked), weight-and-confidence-averaged into an
      `aggregate_score` and thresholded via a configurable
      `allow_threshold` (default `0.0`) back onto a final bool. Every
      sub-manager is keyed by its own `.name` (duplicates rejected)
      and may carry a constructor-configurable `weight` (default
      `1.0`, `>= 0.0`). Any sub-manager raising
      `InsufficientPortfolioDataError` is treated as "unavailable"
      (`metadata["managers_missing"]` records which and why);
      `PortfolioManager` itself only raises
      `InsufficientPortfolioDataError` when every sub-manager was
      unavailable. Calculates and records `aggregate_score`,
      `completeness`, `agreement` (1.0/0.0 match scale against the
      final decision -- no `HOLD`-style neutral state exists for a
      boolean), and `confidence` (`completeness x agreement x` average
      confidence, the same shape the three aggregators above already
      use). Fully deterministic -- no AI, no randomness, no wall-clock
      reads, no I/O; never mutates any sub-manager's `PortfolioResult`.
      No allocation, no position-sizing, no rebalancing, no broker
      integration -- only aggregation. Reuses Parts 1-2
      (`BasePortfolioManager`/`PortfolioContext`/`PortfolioResult`/
      exceptions/utils, `BasicPortfolioManager`) exactly as they
      already exist.

Also contains (Portfolio Management Part 4 -- aggregator mirroring
`StrategyAggregator`):
    - `PortfolioAggregator` (`aggregator.py`): itself a concrete
      `BasePortfolioManager`, functionally the same combining role
      `PortfolioManager` (Part 3) plays, but built explicitly to
      mirror `strategies.aggregator.StrategyAggregator`'s naming,
      structure, and documentation conventions one layer up (the
      naming convention `analysis.aggregator.AnalysisAggregator`/
      `signals.aggregator.SignalAggregator`/`strategies.aggregator.
      StrategyAggregator` already use). Combines the `PortfolioResult`s
      of one or more injected `BasePortfolioManager` instances
      (defaulting to a single `BasicPortfolioManager()` when none are
      supplied) into one final `PortfolioResult`. Since `PortfolioResult`
      has no numeric score field (only a boolean
      `new_positions_allowed`), each sub-manager's decision is
      represented as a signed unit vote (`+1.0` allowed, `-1.0`
      blocked), weight-and-confidence-averaged into an
      `aggregate_score` and thresholded via a configurable
      `allow_threshold` (default `0.0`) back onto a final bool. Every
      sub-manager is keyed by its own `.name` (duplicates rejected)
      and may carry a constructor-configurable `weight` (default
      `1.0`, `>= 0.0`). Any sub-manager raising
      `InsufficientPortfolioDataError` is treated as "unavailable"
      (`metadata["managers_missing"]` records which and why);
      `PortfolioAggregator` itself only raises
      `InsufficientPortfolioDataError` when every sub-manager was
      unavailable. Calculates and records `aggregate_score`,
      `completeness`, `agreement` (1.0/0.0 match scale against the
      final decision), and `confidence` (`completeness x agreement x`
      average confidence). Sequential, deterministic execution -- no
      concurrency, no wall-clock reads, no randomness, no I/O; never
      mutates any sub-manager's `PortfolioResult`. No allocation, no
      position-sizing, no rebalancing, no broker integration -- only
      aggregation. Reuses Parts 1-2 (`BasePortfolioManager`/
      `PortfolioContext`/`PortfolioResult`/exceptions/utils,
      `BasicPortfolioManager`) exactly as they already exist; Part 3
      (`portfolio_manager.py`) is left completely untouched and is not
      imported by this module.

Planned contents (future Portfolio Management parts):
    - Allocation/sizing logic across multiple assets and rebalancing
      of existing positions.
"""

from __future__ import annotations

from strategies.portfolio_management.aggregator import PortfolioAggregator
from strategies.portfolio_management.base import BasePortfolioManager
from strategies.portfolio_management.basic_portfolio_manager import BasicPortfolioManager
from strategies.portfolio_management.context import PortfolioContext
from strategies.portfolio_management.exceptions import (
    InsufficientPortfolioDataError,
    InvalidPortfolioContextError,
    PortfolioError,
    PortfolioManagerConfigurationError,
    PortfolioValidationError,
)
from strategies.portfolio_management.portfolio_manager import PortfolioManager
from strategies.portfolio_management.result import PortfolioResult

__all__ = [
    "BasePortfolioManager",
    "BasicPortfolioManager",
    "PortfolioManager",
    "PortfolioAggregator",
    "PortfolioContext",
    "PortfolioResult",
    "PortfolioError",
    "PortfolioValidationError",
    "InvalidPortfolioContextError",
    "InsufficientPortfolioDataError",
    "PortfolioManagerConfigurationError",
]
