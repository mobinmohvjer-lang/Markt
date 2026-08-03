"""
execution package
------------------
Purpose:
    The Execution Engine: evaluates whether a candidate trading
    decision -- given its `strategies.result.StrategyResult`, its
    `strategies.risk_management.result.RiskResult`, its `strategies.
    portfolio_management.result.PortfolioResult`, and the current
    `core.entities.portfolio.Portfolio` -- is cleared to proceed
    toward actual order placement, standardizing that evaluation into
    a single `ExecutionResult`. Mirrors the role `strategies.
    portfolio_management` plays one layer down: each layer interprets/
    standardizes its predecessor's output without deciding what to do
    about it. `execution/` is the last framework-only checkpoint
    before an approved decision would ever reach a broker/exchange --
    it never places that order itself.

Contents (Execution Engine Part 1 -- foundation, new this milestone):
    - `BaseExecutionEngine` (`base.py`): abstract base every concrete
      execution engine implements. Consumes an `ExecutionContext` and
      produces an `ExecutionResult` via an abstract `execute()`
      method, plus shared `validate_context`/`_build_result` helpers
      -- mirroring the exact role `analysis.base.BaseAnalyzer`,
      `signals.base.BaseSignalGenerator`, `strategies.base_strategy.
      BaseStrategy`, `strategies.risk_management.base.
      BaseRiskManager`, and `strategies.portfolio_management.base.
      BasePortfolioManager` play one layer down each.
    - `ExecutionContext` (`context.py`): immutable bundle of the
      current `core.entities.portfolio.Portfolio` (required), an
      optional `strategies.result.StrategyResult` (the candidate
      trading decision under consideration), an optional `strategies.
      risk_management.result.RiskResult` (that decision's risk
      evaluation), and an optional `strategies.portfolio_management.
      result.PortfolioResult` (whether the portfolio has capacity for
      it) for one symbol/timeframe -- no new domain concepts
      introduced.
    - `ExecutionResult` (`result.py`): standardized output --
      `execution_approved` (bool), `confidence`, `summary`,
      `metadata`. Deliberately minimal: no order-id, no fill price/
      quantity, no broker/exchange identifiers, no `engine_name` field
      (mirroring `RiskResult`'s omission of `risk_manager_name` and
      `PortfolioResult`'s omission of `portfolio_manager_name`).
    - `ExecutionError` hierarchy (`exceptions.py`): `ExecutionError` ->
      `ExecutionValidationError` -> `InvalidExecutionContextError`,
      plus `InsufficientExecutionDataError` and
      `ExecutionEngineConfigurationError`.
    - Shared validation helpers (`utils.py`).

    Framework only -- Execution Engine Part 1 ships no concrete
    execution engine, no broker integration, no exchange API, no
    order execution, no networking, no threading, no async, and no
    AI. Consumes existing `StrategyResult`, `RiskResult`,
    `PortfolioResult`, and `Portfolio` exactly as they already exist;
    produces only `ExecutionResult`. Imported directly (`from
    execution import BaseExecutionEngine, ExecutionContext,
    ExecutionResult, ...`), mirroring how `strategies.risk_management`
    and `strategies.portfolio_management` are imported directly rather
    than re-exported through a parent package's `__init__.py` (this
    package has no such parent).

Planned contents (future Execution Engine parts):
    - At least one concrete `BaseExecutionEngine` implementation.
    - Eventually, real order placement/broker integration -- explicitly
      out of scope for every part until that milestone is reached (see
      `PROJECT_RULES.md` Section 1, principle 3: free-first, and the
      "no paid service" constraint any future broker integration must
      still respect).
"""

from __future__ import annotations

from execution.base import BaseExecutionEngine
from execution.context import ExecutionContext
from execution.exceptions import (
    ExecutionEngineConfigurationError,
    ExecutionError,
    ExecutionValidationError,
    InsufficientExecutionDataError,
    InvalidExecutionContextError,
)
from execution.result import ExecutionResult

__all__ = [
    "BaseExecutionEngine",
    "ExecutionContext",
    "ExecutionResult",
    "ExecutionError",
    "ExecutionValidationError",
    "InvalidExecutionContextError",
    "InsufficientExecutionDataError",
    "ExecutionEngineConfigurationError",
]
