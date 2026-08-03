"""
strategies/portfolio_management/base.py

Defines `BasePortfolioManager`: the abstract base every concrete
portfolio manager implements in later Portfolio Management parts.

Mirrors the role `analysis/base.py`'s `BaseAnalyzer` plays for
`analysis/`, `signals/base.py`'s `BaseSignalGenerator` plays for
`signals/`, `strategies/base_strategy.py`'s `BaseStrategy` plays for
`strategies/`, and `strategies/risk_management/base.py`'s
`BaseRiskManager` plays for `strategies.risk_management`: it evaluates
the overall portfolio state -- given a candidate `StrategyResult` and
its `RiskResult`, plus the current `Portfolio` -- and decides whether a
new position may be opened, without deciding position size, allocation
weights, rebalancing, or actually placing any order (those remain out
of scope for this Portfolio Management part, and ultimately belong to
a later Portfolio Management part and/or a future order-execution
layer).

This is deliberately a small, framework-only contract -- Portfolio
Management Part 1 ships no concrete portfolio manager, no allocation
algorithm, no rebalancing logic, and no broker integration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from strategies.portfolio_management.context import PortfolioContext
from strategies.portfolio_management.exceptions import InvalidPortfolioContextError
from strategies.portfolio_management.result import PortfolioResult


class BasePortfolioManager(ABC):
    """
    Abstract base class for all portfolio managers.

    A concrete portfolio manager consumes a `PortfolioContext` (the
    current `Portfolio`, an optional candidate `StrategyResult`, and an
    optional `RiskResult` for one symbol/timeframe) and produces a
    single `PortfolioResult`. Concrete portfolio managers are expected
    to:

        - Evaluate overall portfolio state (e.g. exposure, open
          position count, concentration) as it stands today, from
          `PortfolioContext.portfolio`.
        - Determine whether a new position is allowed given that
          state and whatever portfolio-level constraints they define.
        - Enforce those portfolio-level constraints (e.g. maximum open
          positions, maximum aggregate exposure) -- without performing
          allocation, position sizing, or rebalancing, all of which
          remain out of scope for this Portfolio Management part.
        - Calculate a `confidence` reflecting how much of the relevant
          data was actually available.
        - Record every intermediate decision/check in
          `PortfolioResult.metadata`, so a decision can always be
          traced back to the inputs and constraints that produced it.

    Concrete portfolio managers must not size positions, choose an
    allocation, rebalance existing positions, place orders, or call
    out to a broker -- those remain the responsibility of a later
    Portfolio Management part and/or a future order-execution layer.

    Attributes:
        name: Human-readable name of this portfolio manager instance,
            used for logging/`repr`. Note `PortfolioResult`
            intentionally has no `portfolio_manager_name` field
            (mirroring `RiskResult`'s omission of `risk_manager_name`)
            -- a concrete portfolio manager may record `name` in its
            own `metadata` if traceability is needed.
    """

    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name or self.__class__.__name__

    # ------------------------------------------------------------------
    # Abstract API
    # ------------------------------------------------------------------
    @abstractmethod
    def evaluate(self, context: PortfolioContext) -> PortfolioResult:
        """
        Evaluate `context` and return a single `PortfolioResult`.

        Implementations should call `self.validate_context(context)`
        first, and are expected to raise `strategies.
        portfolio_management.exceptions.
        InsufficientPortfolioDataError` when `context` does not carry
        enough data to produce a meaningful result.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def validate_context(self, context: PortfolioContext) -> PortfolioContext:
        """
        Validate that `context` is a usable `PortfolioContext` for this
        portfolio manager.

        Raises:
            InvalidPortfolioContextError: If `context` is not a
                `PortfolioContext` instance.
        """
        if not isinstance(context, PortfolioContext):
            raise InvalidPortfolioContextError(
                f"{self.name} expected a PortfolioContext, got {type(context).__name__}"
            )
        return context

    def _build_result(
        self,
        *,
        new_positions_allowed: bool,
        confidence: float,
        summary: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> PortfolioResult:
        """
        Build a `PortfolioResult` using this portfolio manager's
        standard shape.

        Convenience helper so concrete portfolio managers don't repeat
        `PortfolioResult(...)` construction on every `evaluate()`
        implementation.
        """
        return PortfolioResult(
            new_positions_allowed=new_positions_allowed,
            confidence=confidence,
            summary=summary,
            metadata=metadata or {},
        )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(name={self.name!r})"
