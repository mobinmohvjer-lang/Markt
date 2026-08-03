"""
strategies package
--------------------
Purpose:
    Contains trading strategy implementations: logic that consumes the
    outputs of `analysis`/`signals` (technical, news, AI) and produces
    concrete trading signals or decisions (e.g. BUY / SELL / HOLD).

    Strategies should be small, composable, and testable in isolation.
    Each strategy should implement a common interface defined in `core`
    so that new strategies can be plugged in without changing the rest
    of the application (Open/Closed Principle).

Contents (Strategy Engine Part 1 -- foundation, new this milestone):
    - `BaseStrategy` (`base_strategy.py`): abstract base every concrete
      strategy implements. Consumes a `StrategyContext` and produces a
      `StrategyResult` via an abstract `decide()` method, plus shared
      `validate_context`/`_build_result` helpers -- mirroring the exact
      role `analysis.base.BaseAnalyzer`, `signals.base.
      BaseSignalGenerator`, and `strategies.risk_management.base.
      BaseRiskManager` play one layer down each. Deliberately does not
      implement `core.interfaces.strategy.Strategy` (a different,
      MarketState-in/Signal-out contract) -- see `base_strategy.py` for
      why, the same reasoning `BaseRiskManager` documents relative to
      `core.interfaces.risk_manager.RiskManager`.
    - `StrategyContext` (`context.py`): immutable bundle of existing
      `analysis.result.AnalysisResult`(s), an optional `signals.result.
      SignalResult`, and an optional `strategies.risk_management.
      result.RiskResult` for one symbol/timeframe -- no new domain
      concepts introduced.
    - `StrategyResult` (`result.py`): standardized output --
      `action` (reusing `core.enums.SignalDirection`), `confidence`,
      `summary`, `metadata`. Deliberately minimal: no position size, no
      stop-loss/take-profit, no order-id, no `strategy_name` field
      (mirroring `RiskResult`'s omission of `risk_manager_name`).
    - `StrategyError` hierarchy (`exceptions.py`): `StrategyError` ->
      `StrategyValidationError` -> `InvalidStrategyContextError`, plus
      `InsufficientStrategyDataError` and
      `StrategyConfigurationError`.
    - Shared validation helpers (`utils.py`).

    Framework only -- Strategy Engine Part 1 ships no concrete
    strategy, no AI, no order execution, and no broker integration.
    Consumes existing Analysis/Signal/Risk Engine output; produces only
    `StrategyResult`. Imported and re-exported through this
    `strategies/__init__.py` (unlike `strategies.risk_management`,
    which is imported directly), the same convention `analysis.
    aggregator.AnalysisAggregator` uses relative to `analysis/technical/`.

Also contains (Risk Engine Parts 1-3):
    - risk_management/: the Risk Engine. Part 1 (foundation):
      `BaseRiskManager`, `RiskContext`, `RiskResult`, the `RiskError`
      hierarchy, and shared validation helpers (`utils.py`), mirroring
      the role `analysis/`'s and `signals/`'s own Part 1 foundations
      played. Part 2 (first concrete implementation): `BasicRiskManager`,
      which evaluates signal confidence, signal strength, portfolio
      exposure, and market-data availability into one `RiskResult`.
      Part 3: `PositionSizeRule`, `StopLossRule`, `TakeProfitRule` --
      three independent concrete risk managers recommending position
      size, stop-loss, and take-profit levels via `RiskResult.metadata`.
      Still no order execution, no strategy/trading decisions, no AI;
      see `strategies/risk_management/__init__.py` for full detail.
      Imported directly (`from strategies.risk_management import
      BaseRiskManager, BasicRiskManager, ...`), not re-exported here,
      the same convention `analysis/technical/` uses relative to
      `analysis/`.

Contents (Strategy Engine Part 2 -- first concrete strategy, new this milestone):
    - `BasicStrategy` (`basic_strategy.py`): the first concrete
      `BaseStrategy`. Consumes one `AnalysisResult` (matched by
      `analyzer_name`, default `"AnalysisAggregator"`), an optional
      `signals.result.SignalResult`, and an optional `strategies.
      risk_management.result.RiskResult` from a `StrategyContext`, and
      combines them into a single `StrategyResult`: a confidence-
      weighted directional score (analysis + signal, mapped to
      BUY/SELL/HOLD via configurable thresholds -- the same convention
      `signals.technical_signal_generator.TechnicalSignalGenerator`
      uses), an agreement-based consistency score between the inputs,
      and a risk gate that downgrades an unapproved BUY/SELL to HOLD.
      `StrategyResult` has no `score` field, so the required overall
      strategy score is recorded at `metadata["overall_score"]`, along
      with every other intermediate value, for full traceability.
      Deterministic: no AI, no randomness, no wall-clock reads. No
      order execution, no broker integration, no portfolio management,
      no optimization -- only this one concrete strategy ships in this
      part. Reuses Part 1 (`BaseStrategy`/`StrategyContext`/
      `StrategyResult`/exceptions/utils) and Risk Engine's `RiskResult`
      exactly as they already exist; nothing under `strategies/
      risk_management/`, `analysis/`, or `signals/` was modified. Only
      this `strategies/__init__.py` (to export `BasicStrategy` and
      document Part 2) was updated among existing files. See
      `basic_strategy.py` for the full scoring/consistency/confidence
      shape.

Contents (Strategy Engine Part 3 -- aggregation, new this milestone):
    - `StrategyAggregator` (`aggregator.py`): combines the
      `StrategyResult`s of one or more injected `BaseStrategy`
      instances (defaulting to a single plain `BasicStrategy()` when
      none are supplied) into one final `StrategyResult`, mirroring
      the role `analysis.aggregator.AnalysisAggregator` and `signals.
      aggregator.SignalAggregator` already play one and two layers
      down, respectively. Each sub-strategy is keyed by its own
      `.name` (duplicates rejected) and may carry a constructor-
      configurable `weight` (default `1.0`, `>= 0.0`); a sub-strategy's
      own `confidence` further scales its contribution. Since
      `StrategyResult` has no numeric score/strength field, each
      sub-strategy's `action` is represented as a signed unit value
      (`+1.0`/`-1.0`/`0.0`) scaled by its `confidence`, weight-averaged
      into an aggregate score and thresholded back onto BUY/SELL/HOLD
      via configurable `buy_threshold`/`sell_threshold` (same
      defaults/validation as `BasicStrategy`/`SignalAggregator`). Runs
      every sub-strategy sequentially against the same
      `StrategyContext`; any sub-strategy raising
      `InsufficientStrategyDataError` is treated as "unavailable"
      (`metadata["strategies_missing"]` records which and why) --
      `StrategyAggregator` itself only raises
      `InsufficientStrategyDataError` when every sub-strategy was
      unavailable. Calculates and records, in full, four traceable
      facets: `overall_score`, `confidence`, `completeness` (fraction
      of sub-strategies that produced a usable decision), and
      `agreement` (weighted agreement between each contributing
      decision and the final aggregated action, `1.0`/`0.5`/`0.0`
      scale) -- `confidence` itself is `completeness x agreement x`
      average confidence, the same shape the two engines below already
      use. Fully deterministic: no AI, no randomness, no wall-clock
      reads, no I/O; never mutates any sub-strategy's `StrategyResult`.
      No order execution, no broker integration, no portfolio
      management, no optimization -- only aggregation. Reuses Parts 1-2
      (`BaseStrategy`/`StrategyContext`/`StrategyResult`/exceptions/
      utils, `BasicStrategy`) exactly as they already exist;
      `strategies/risk_management/`, `analysis/`, and `signals/` were
      left completely untouched. Only this `strategies/__init__.py`
      (to export `StrategyAggregator` and document Part 3) was updated
      among existing files. See `aggregator.py` for the full
      scoring/completeness/agreement/confidence shape.

Also contains (Portfolio Management Part 1 -- foundation, new this milestone):
    - portfolio_management/: the Portfolio Management layer. Part 1
      (foundation): `BasePortfolioManager`, `PortfolioContext`,
      `PortfolioResult`, the `PortfolioError` hierarchy, and shared
      validation helpers (`utils.py`), mirroring the role
      `strategies/`'s and `strategies.risk_management`'s own Part 1
      foundations played. `PortfolioContext` composes the current
      `core.entities.portfolio.Portfolio` (required), an optional
      candidate `StrategyResult`, and an optional `RiskResult` for one
      symbol/timeframe; `PortfolioResult` is deliberately minimal --
      `new_positions_allowed` (bool), `confidence`, `summary`,
      `metadata`. Framework only: no concrete portfolio manager ships
      in this part, no allocation algorithm, no rebalancing logic, no
      broker integration. Consumes existing `StrategyResult`,
      `RiskResult`, and `Portfolio` exactly as they already exist;
      `strategies/risk_management/`, `strategies/`'s own foundation/
      `BasicStrategy`/`StrategyAggregator`, `analysis/`, and `signals/`
      were left completely untouched. Only this `strategies/__init__.py`
      (to document Part 1's existence) was updated among existing
      files. Imported directly (`from strategies.portfolio_management
      import BasePortfolioManager, PortfolioContext, PortfolioResult,
      ...`), not re-exported here, the same convention
      `strategies.risk_management` already uses relative to
      `strategies/`; see `strategies/portfolio_management/__init__.py`
      for full detail.

Planned contents (future Strategy Engine / Portfolio Management parts):
    - Additional concrete strategies (e.g. trend_following_strategy.py,
      mean_reversion_strategy.py) subclassing `BaseStrategy`.
    - A first concrete `BasePortfolioManager` implementation and,
      eventually, allocation/sizing/rebalancing logic across multiple
      assets -- all out of scope for Portfolio Management Part 1.

`BasicStrategy` is the first trading decision this package actually
produces; `risk_management` still only evaluates whether a candidate
signal is safe to act on -- `BasicStrategy` is what decides what to do
with that evaluation. `StrategyAggregator` is what combines multiple
such decisions -- from several `BasicStrategy` configurations today,
or a mix of concrete strategies once more exist -- into one.
"""

from __future__ import annotations

from strategies.aggregator import StrategyAggregator
from strategies.base_strategy import BaseStrategy
from strategies.basic_strategy import BasicStrategy
from strategies.context import StrategyContext
from strategies.exceptions import (
    InsufficientStrategyDataError,
    InvalidStrategyContextError,
    StrategyConfigurationError,
    StrategyError,
    StrategyValidationError,
)
from strategies.result import StrategyResult

__all__ = [
    "BaseStrategy",
    "BasicStrategy",
    "StrategyAggregator",
    "StrategyContext",
    "StrategyResult",
    "StrategyError",
    "StrategyValidationError",
    "InvalidStrategyContextError",
    "InsufficientStrategyDataError",
    "StrategyConfigurationError",
]
