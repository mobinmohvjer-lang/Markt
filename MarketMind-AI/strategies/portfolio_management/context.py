"""
strategies/portfolio_management/context.py

Defines `PortfolioContext`: the immutable bundle of data every
`BasePortfolioManager` needs in order to produce a `PortfolioResult`
for one candidate trade evaluated against the overall portfolio.

`PortfolioContext` only composes entities/results that already exist --
`core.entities.portfolio.Portfolio` (required), an optional
`strategies.result.StrategyResult` (the candidate trading decision
under consideration), and an optional `strategies.risk_management.
result.RiskResult` (that decision's risk evaluation) -- for one
symbol/timeframe. It introduces no new domain concepts, keeping the
Dependency Rule intact (`strategies` -> `core`, `analysis`, `signals`,
`events`; its own `risk_management`/`portfolio_management`
subpackages are siblings within the same top-level package, not
outer-layer imports).

Pure data container -- no portfolio evaluation logic, no constraint
enforcement, no allocation/rebalancing. Assembling a `PortfolioContext`
from real, end-to-end engine output remains a future `app/` use case,
the same gap `AnalysisContext`/`SignalContext`/`RiskContext`/
`StrategyContext` already document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from core.entities.portfolio import Portfolio

from strategies.result import StrategyResult
from strategies.risk_management.result import RiskResult

from strategies.portfolio_management.exceptions import (
    InvalidPortfolioContextError,
    PortfolioValidationError,
)
from strategies.portfolio_management.utils import validate_non_empty_str


@dataclass(frozen=True)
class PortfolioContext:
    """
    Everything a `BasePortfolioManager` needs to evaluate one candidate
    trade against the current portfolio.

    Attributes:
        symbol: Trading pair/instrument identifier the candidate trade
            applies to (e.g. "BTCUSDT").
        timeframe: Candle interval the candidate trade was derived from
            (e.g. "1h").
        portfolio: The current portfolio state to evaluate against.
            Required -- a portfolio manager cannot evaluate constraints
            (exposure, position count, ...) without it.
        strategy_result: The candidate `StrategyResult` (trading
            decision) under consideration, if available. Its absence
            only limits what a portfolio manager can evaluate -- it
            never invalidates the context.
        risk_result: The `RiskResult` produced by the Risk Engine for
            this candidate trade, if available. Its absence only
            limits what a portfolio manager can evaluate -- it never
            invalidates the context.
        metadata: Free-form additional context supplied by the caller,
            kept for traceability. Not interpreted here.
    """

    symbol: str
    timeframe: str
    portfolio: Portfolio
    strategy_result: Optional[StrategyResult] = None
    risk_result: Optional[RiskResult] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "symbol", validate_non_empty_str(self.symbol, name="symbol"))
            object.__setattr__(
                self, "timeframe", validate_non_empty_str(self.timeframe, name="timeframe")
            )
        except PortfolioValidationError as exc:
            raise InvalidPortfolioContextError(str(exc)) from exc

        if not isinstance(self.portfolio, Portfolio):
            raise InvalidPortfolioContextError(
                f"portfolio must be a Portfolio, got {type(self.portfolio).__name__}"
            )
        if self.strategy_result is not None and not isinstance(
            self.strategy_result, StrategyResult
        ):
            raise InvalidPortfolioContextError(
                f"strategy_result must be a StrategyResult or None, "
                f"got {type(self.strategy_result).__name__}"
            )
        if self.risk_result is not None and not isinstance(self.risk_result, RiskResult):
            raise InvalidPortfolioContextError(
                f"risk_result must be a RiskResult or None, got {type(self.risk_result).__name__}"
            )
        if not isinstance(self.metadata, dict):
            raise InvalidPortfolioContextError(
                f"metadata must be a dict, got {type(self.metadata).__name__}"
            )

    def has_strategy_result(self) -> bool:
        """Whether this context carries a candidate `StrategyResult`."""
        return self.strategy_result is not None

    def has_risk_result(self) -> bool:
        """Whether this context carries a `RiskResult`."""
        return self.risk_result is not None
