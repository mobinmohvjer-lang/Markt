"""
backtesting/result.py

Defines `BacktestResult`: the standardized output produced by every
`BaseBacktester.run()` call, regardless of which concrete backtester
produced it.

Pure data container -- no trade simulation, no PnL calculation, no
performance-statistics logic (Sharpe ratio, max drawdown, win rate,
profit factor, etc.), no aggregation. This lets a future consumer
(a later Backtesting Engine part, or `app/`'s orchestration layer)
depend on one stable shape instead of a different result type per
backtester.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.entities.portfolio import Portfolio
from core.entities.trade import Trade

from backtesting.utils import (
    merge_metadata,
    validate_instance_list,
    validate_non_empty_str,
)


@dataclass(frozen=True)
class BacktestResult:
    """
    The standardized output of a single backtest run.

    Deliberately minimal, mirroring `strategies.risk_management.result.
    RiskResult` and `strategies.result.StrategyResult`: no computed
    performance statistics (Sharpe ratio, max drawdown, win rate, profit
    factor -- see `backtesting/__init__.py`'s "Planned contents" for
    where those eventually belong), no report formatting. Those remain
    out of scope for Backtesting Engine Part 1 (framework only) and
    ultimately belong to a later Backtesting Engine part.

    Attributes:
        final_portfolio: The `Portfolio` state at the end of the
            backtest run.
        summary: Short, human-readable explanation of the result.
        trades: `Trade` entries executed during the run, in the order
            they occurred. Empty for a backtester that does not yet
            simulate trades -- its absence never invalidates the
            result.
        metadata: Backtester-specific supporting details (e.g. how many
            candles were replayed, which strategy ran), kept for
            traceability.
    """

    final_portfolio: Portfolio
    summary: str
    trades: list[Trade] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # dataclass is frozen, so field re-assignment goes through
        # object.__setattr__ -- this only normalizes/validates values,
        # it never introduces new state.
        if not isinstance(self.final_portfolio, Portfolio):
            raise TypeError(
                f"final_portfolio must be a Portfolio, got {type(self.final_portfolio).__name__}"
            )
        object.__setattr__(self, "trades", validate_instance_list(self.trades, Trade, name="trades"))
        object.__setattr__(self, "summary", validate_non_empty_str(self.summary, name="summary"))
        if not isinstance(self.metadata, dict):
            raise TypeError(f"metadata must be a dict, got {type(self.metadata).__name__}")

    def with_metadata(self, **extra: Any) -> "BacktestResult":
        """
        Return a new `BacktestResult` with `extra` merged into `metadata`.

        Since `BacktestResult` is immutable, this returns a new instance
        rather than mutating the existing one.
        """
        return BacktestResult(
            final_portfolio=self.final_portfolio,
            trades=self.trades,
            summary=self.summary,
            metadata=merge_metadata(self.metadata, extra),
        )

    def trade_count(self) -> int:
        """Number of trades recorded in this result."""
        return len(self.trades)
