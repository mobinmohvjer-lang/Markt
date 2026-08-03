"""
strategies/base_strategy.py

Defines `BaseStrategy`: the abstract base every concrete strategy
implements in later Strategy Engine parts.

Mirrors the role `analysis/base.py`'s `BaseAnalyzer` plays for
`analysis/`, `signals/base.py`'s `BaseSignalGenerator` plays for
`signals/`, and `strategies/risk_management/base.py`'s
`BaseRiskManager` plays for `strategies.risk_management`: it turns the
already-standardized outputs of the Analysis, Signal, and Risk Engines
(`AnalysisResult`/`SignalResult`/`RiskResult`, bundled in a
`StrategyContext`) into a single trading decision (`StrategyResult`),
without executing any order or sizing any position.

This is deliberately a different, smaller contract than
`core.interfaces.strategy.Strategy`: that interface takes a raw
`MarketState` and returns an optional `Signal` directly -- a shape
meant for a strategy that reasons over market data on its own.
`BaseStrategy` instead consumes the already-produced
`AnalysisResult`/`SignalResult`/`RiskResult` triad via `StrategyContext`
and produces a `StrategyResult`, so `BaseStrategy` deliberately does
**not** implement `Strategy`, the same way `strategies.risk_management.
base.BaseRiskManager` does not implement `core.interfaces.
risk_manager.RiskManager`. A future adapter can bridge the two once
that scope is reached.

Framework only -- Strategy Engine Part 1 ships no concrete strategy, no
AI, no order execution, and no broker integration.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from core.enums import SignalDirection

from strategies.context import StrategyContext
from strategies.exceptions import InvalidStrategyContextError
from strategies.result import StrategyResult


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.

    A concrete strategy consumes a `StrategyContext` (existing
    `AnalysisResult`(s), an optional `SignalResult`, and an optional
    `RiskResult` for one symbol/timeframe) and produces a single
    `StrategyResult`. Concrete strategies must not place orders, size
    positions, compute stop-loss/take-profit levels, or call out to an
    AI model/broker -- those remain the responsibility of later
    Strategy Engine parts and/or a future order-execution layer.

    Attributes:
        name: Human-readable name of this strategy instance, used for
            logging/`repr`. Note `StrategyResult` intentionally has no
            `strategy_name` field (mirroring `RiskResult`'s omission of
            `risk_manager_name`) -- a concrete strategy may record
            `name` in its own `metadata` if traceability is needed.
    """

    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name or self.__class__.__name__

    # ------------------------------------------------------------------
    # Abstract API
    # ------------------------------------------------------------------
    @abstractmethod
    def decide(self, context: StrategyContext) -> StrategyResult:
        """
        Evaluate `context` and return a single `StrategyResult`.

        Implementations should call `self.validate_context(context)`
        first, and are expected to raise `strategies.exceptions.
        InsufficientStrategyDataError` when `context` does not carry
        enough data to produce a meaningful decision.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def validate_context(self, context: StrategyContext) -> StrategyContext:
        """
        Validate that `context` is a usable `StrategyContext` for this strategy.

        Raises:
            InvalidStrategyContextError: If `context` is not a
                `StrategyContext` instance.
        """
        if not isinstance(context, StrategyContext):
            raise InvalidStrategyContextError(
                f"{self.name} expected a StrategyContext, got {type(context).__name__}"
            )
        return context

    def _build_result(
        self,
        *,
        action: SignalDirection,
        confidence: float,
        summary: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> StrategyResult:
        """
        Build a `StrategyResult` using this strategy's standard shape.

        Convenience helper so concrete strategies don't repeat
        `StrategyResult(...)` construction on every `decide()`
        implementation.
        """
        return StrategyResult(
            action=action,
            confidence=confidence,
            summary=summary,
            metadata=metadata or {},
        )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(name={self.name!r})"
