"""
backtesting/base.py

Defines `BaseBacktester`: the abstract base every concrete backtester
implements in later Backtesting Engine parts.

Mirrors the role `analysis/base.py`'s `BaseAnalyzer` plays for
`analysis/`, `signals/base.py`'s `BaseSignalGenerator` plays for
`signals/`, `strategies/risk_management/base.py`'s `BaseRiskManager`
plays for `strategies.risk_management`, and `strategies/base_strategy.
py`'s `BaseStrategy` plays for `strategies/`: it replays a
`BacktestContext` (historical candles, a strategy, and a starting
portfolio) and produces a single standardized `BacktestResult`.

Backtesting is a consumer, never a strategy author (see
`PROJECT_RULES.md` Section 1, principle 5): a concrete backtester
replays historical data through whatever strategy/signals it is given
and reports results; it must never define trading rules of its own.

Framework only -- Backtesting Engine Part 1 ships no concrete
backtester, no trade simulation, no PnL calculation, no performance
statistics, and no aggregation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from core.entities.portfolio import Portfolio

from backtesting.context import BacktestContext
from backtesting.exceptions import InvalidBacktestContextError
from backtesting.result import BacktestResult


class BaseBacktester(ABC):
    """
    Abstract base class for all backtesters.

    A concrete backtester consumes a `BacktestContext` (historical
    `Candle` data, a `BaseStrategy` instance, and a starting
    `Portfolio`) and produces a single `BacktestResult`. Concrete
    backtesters must not define trading rules, place real orders, or
    interpret market data themselves -- they only replay whatever
    strategy/signals they are given against the supplied historical
    data.

    Attributes:
        name: Human-readable name of this backtester instance, used
            for logging/`repr`. Note `BacktestResult` intentionally has
            no `backtester_name` field (mirroring `RiskResult`'s
            omission of `risk_manager_name` and `StrategyResult`'s
            omission of `strategy_name`) -- a concrete backtester may
            record `name` in its own `metadata` if traceability is
            needed.
    """

    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name or self.__class__.__name__

    # ------------------------------------------------------------------
    # Abstract API
    # ------------------------------------------------------------------
    @abstractmethod
    def run(self, context: BacktestContext) -> BacktestResult:
        """
        Replay `context` and return a single `BacktestResult`.

        Implementations should call `self.validate_context(context)`
        first, and are expected to raise `backtesting.exceptions.
        InsufficientBacktestDataError` when `context` does not carry
        enough data to run a meaningful backtest.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def validate_context(self, context: BacktestContext) -> BacktestContext:
        """
        Validate that `context` is a usable `BacktestContext` for this backtester.

        Raises:
            InvalidBacktestContextError: If `context` is not a
                `BacktestContext` instance.
        """
        if not isinstance(context, BacktestContext):
            raise InvalidBacktestContextError(
                f"{self.name} expected a BacktestContext, got {type(context).__name__}"
            )
        return context

    def _build_result(
        self,
        *,
        final_portfolio: Portfolio,
        summary: str,
        trades: Optional[list] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> BacktestResult:
        """
        Build a `BacktestResult` using this backtester's standard shape.

        Convenience helper so concrete backtesters don't repeat
        `BacktestResult(...)` construction on every `run()`
        implementation.
        """
        return BacktestResult(
            final_portfolio=final_portfolio,
            summary=summary,
            trades=trades or [],
            metadata=metadata or {},
        )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(name={self.name!r})"
