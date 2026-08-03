"""
execution/context.py

Defines `ExecutionContext`: the immutable bundle of data every
`BaseExecutionEngine` needs in order to produce an `ExecutionResult`
for one candidate trading decision.

`ExecutionContext` only composes entities/results that already exist --
`core.entities.portfolio.Portfolio` (required), an optional
`strategies.result.StrategyResult` (the candidate trading decision
under consideration), an optional `strategies.risk_management.result.
RiskResult` (that decision's risk evaluation), and an optional
`strategies.portfolio_management.result.PortfolioResult` (whether the
portfolio has capacity for it) -- for one symbol/timeframe. It
introduces no new domain concepts, mirroring the exact composition
pattern `strategies.portfolio_management.context.PortfolioContext`
already established one layer down.

Pure data container -- no order-readiness evaluation logic, no broker/
exchange integration, no networking. Assembling an `ExecutionContext`
from real, end-to-end engine output remains a future `app/` use case,
the same gap `AnalysisContext`/`SignalContext`/`RiskContext`/
`StrategyContext`/`PortfolioContext` already document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from core.entities.portfolio import Portfolio

from strategies.result import StrategyResult
from strategies.risk_management.result import RiskResult
from strategies.portfolio_management.result import PortfolioResult

from execution.exceptions import ExecutionValidationError, InvalidExecutionContextError
from execution.utils import validate_non_empty_str


@dataclass(frozen=True)
class ExecutionContext:
    """
    Everything a `BaseExecutionEngine` needs to evaluate one candidate
    trading decision for execution readiness.

    Attributes:
        symbol: Trading pair/instrument identifier the candidate
            decision applies to (e.g. "BTCUSDT").
        timeframe: Candle interval the candidate decision was derived
            from (e.g. "1h").
        portfolio: The current portfolio state to evaluate against.
            Required -- an execution engine cannot reason about
            capacity/state without it.
        strategy_result: The candidate `StrategyResult` (trading
            decision) under consideration, if available. Its absence
            only limits what an execution engine can evaluate -- it
            never invalidates the context.
        risk_result: The `RiskResult` produced by the Risk Engine for
            this candidate decision, if available. Its absence only
            limits what an execution engine can evaluate -- it never
            invalidates the context.
        portfolio_result: The `PortfolioResult` produced by Portfolio
            Management for this candidate decision, if available. Its
            absence only limits what an execution engine can evaluate
            -- it never invalidates the context.
        metadata: Free-form additional context supplied by the caller,
            kept for traceability. Not interpreted here.
    """

    symbol: str
    timeframe: str
    portfolio: Portfolio
    strategy_result: Optional[StrategyResult] = None
    risk_result: Optional[RiskResult] = None
    portfolio_result: Optional[PortfolioResult] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "symbol", validate_non_empty_str(self.symbol, name="symbol"))
            object.__setattr__(
                self, "timeframe", validate_non_empty_str(self.timeframe, name="timeframe")
            )
        except ExecutionValidationError as exc:
            raise InvalidExecutionContextError(str(exc)) from exc

        if not isinstance(self.portfolio, Portfolio):
            raise InvalidExecutionContextError(
                f"portfolio must be a Portfolio, got {type(self.portfolio).__name__}"
            )
        if self.strategy_result is not None and not isinstance(
            self.strategy_result, StrategyResult
        ):
            raise InvalidExecutionContextError(
                f"strategy_result must be a StrategyResult or None, "
                f"got {type(self.strategy_result).__name__}"
            )
        if self.risk_result is not None and not isinstance(self.risk_result, RiskResult):
            raise InvalidExecutionContextError(
                f"risk_result must be a RiskResult or None, got {type(self.risk_result).__name__}"
            )
        if self.portfolio_result is not None and not isinstance(
            self.portfolio_result, PortfolioResult
        ):
            raise InvalidExecutionContextError(
                f"portfolio_result must be a PortfolioResult or None, "
                f"got {type(self.portfolio_result).__name__}"
            )
        if not isinstance(self.metadata, dict):
            raise InvalidExecutionContextError(
                f"metadata must be a dict, got {type(self.metadata).__name__}"
            )

    def has_strategy_result(self) -> bool:
        """Whether this context carries a candidate `StrategyResult`."""
        return self.strategy_result is not None

    def has_risk_result(self) -> bool:
        """Whether this context carries a `RiskResult`."""
        return self.risk_result is not None

    def has_portfolio_result(self) -> bool:
        """Whether this context carries a `PortfolioResult`."""
        return self.portfolio_result is not None
