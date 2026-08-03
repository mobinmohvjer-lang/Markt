"""
execution/base.py

Defines `BaseExecutionEngine`: the abstract base every concrete
execution engine implements in later Execution Engine parts.

Mirrors the role `analysis/base.py`'s `BaseAnalyzer` plays for
`analysis/`, `signals/base.py`'s `BaseSignalGenerator` plays for
`signals/`, `strategies/base_strategy.py`'s `BaseStrategy` plays for
`strategies/`, `strategies/risk_management/base.py`'s
`BaseRiskManager` plays for `strategies.risk_management`, and
`strategies/portfolio_management/base.py`'s `BasePortfolioManager`
plays for `strategies.portfolio_management`: it evaluates whether a
candidate trading decision -- given its `StrategyResult`, `RiskResult`,
and `PortfolioResult`, plus the current `Portfolio` -- is cleared to
proceed toward actual order placement, without placing any order,
calling out to a broker/exchange, or performing any networking,
threading, or async I/O (all of which remain out of scope for this
Execution Engine part, and ultimately belong to a later Execution
Engine part and/or `services/`).

This is deliberately a small, framework-only contract -- Execution
Engine Part 1 ships no concrete execution engine, no broker
integration, no exchange API, no order execution, no networking, no
threading, no async, and no AI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from execution.context import ExecutionContext
from execution.exceptions import InvalidExecutionContextError
from execution.result import ExecutionResult


class BaseExecutionEngine(ABC):
    """
    Abstract base class for all execution engines.

    A concrete execution engine consumes an `ExecutionContext` (the
    current `Portfolio`, an optional candidate `StrategyResult`, an
    optional `RiskResult`, and an optional `PortfolioResult` for one
    symbol/timeframe) and produces a single `ExecutionResult`. Concrete
    execution engines are expected to:

        - Evaluate whether the candidate decision, its risk
          evaluation, and its portfolio-capacity evaluation together
          justify proceeding toward execution.
        - Determine `execution_approved` given that evaluation --
          without placing an order, sizing a position, choosing a
          venue, or calling out to a broker/exchange, all of which
          remain out of scope for this Execution Engine part.
        - Calculate a `confidence` reflecting how much of the relevant
          data was actually available.
        - Record every intermediate decision/check in
          `ExecutionResult.metadata`, so a decision can always be
          traced back to the inputs that produced it.

    Concrete execution engines must not place orders, call out to a
    broker/exchange, perform networking/threading/async I/O, or use
    AI -- those remain the responsibility of a later Execution Engine
    part and/or `services/`.

    Attributes:
        name: Human-readable name of this execution engine instance,
            used for logging/`repr`. Note `ExecutionResult`
            intentionally has no `engine_name` field (mirroring
            `RiskResult`'s omission of `risk_manager_name` and
            `PortfolioResult`'s omission of `portfolio_manager_name`)
            -- a concrete execution engine may record `name` in its
            own `metadata` if traceability is needed.
    """

    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name or self.__class__.__name__

    # ------------------------------------------------------------------
    # Abstract API
    # ------------------------------------------------------------------
    @abstractmethod
    def execute(self, context: ExecutionContext) -> ExecutionResult:
        """
        Evaluate `context` and return a single `ExecutionResult`.

        Implementations should call `self.validate_context(context)`
        first, and are expected to raise `execution.exceptions.
        InsufficientExecutionDataError` when `context` does not carry
        enough data to produce a meaningful result.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def validate_context(self, context: ExecutionContext) -> ExecutionContext:
        """
        Validate that `context` is a usable `ExecutionContext` for this
        execution engine.

        Raises:
            InvalidExecutionContextError: If `context` is not an
                `ExecutionContext` instance.
        """
        if not isinstance(context, ExecutionContext):
            raise InvalidExecutionContextError(
                f"{self.name} expected an ExecutionContext, got {type(context).__name__}"
            )
        return context

    def _build_result(
        self,
        *,
        execution_approved: bool,
        confidence: float,
        summary: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ExecutionResult:
        """
        Build an `ExecutionResult` using this execution engine's
        standard shape.

        Convenience helper so concrete execution engines don't repeat
        `ExecutionResult(...)` construction on every `execute()`
        implementation.
        """
        return ExecutionResult(
            execution_approved=execution_approved,
            confidence=confidence,
            summary=summary,
            metadata=metadata or {},
        )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(name={self.name!r})"
