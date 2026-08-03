"""
strategies/risk_management/base.py

Defines `BaseRiskManager`: the abstract base every concrete risk
manager implements in later Risk Engine parts.

Mirrors the role `analysis/base.py`'s `BaseAnalyzer` plays for
`analysis/` and `signals/base.py`'s `BaseSignalGenerator` plays for
`signals/`: `signals/` standardizes analysis into a `SignalResult`,
`strategies.risk_management` evaluates whether a candidate `Signal` is
safe to act on against a `Portfolio`, without deciding position size,
protective levels, or whether to actually place an order (those remain
out of scope for this Risk Engine part, and ultimately belong to a
later Risk Engine part and/or `strategies/`'s own trading-decision
logic and `core.interfaces.risk_manager.RiskManager` implementers).

This is deliberately a smaller contract than
`core.interfaces.risk_manager.RiskManager`: that interface also
requires `calculate_position_size`/`calculate_stop_loss`, which are
explicitly out of scope for Risk Engine Part 1 (no position sizing, no
stop loss, no take profit, no order execution). A future Risk Engine
part -- or a concrete adapter -- can implement `RiskManager` on top of
`BaseRiskManager` once that scope is reached, the same way
`signals/base.py`'s `BaseSignalGenerator` does not itself implement
`core.interfaces.signal_generator.SignalGenerator`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from strategies.risk_management.context import RiskContext
from strategies.risk_management.exceptions import InvalidRiskContextError
from strategies.risk_management.result import RiskResult


class BaseRiskManager(ABC):
    """
    Abstract base class for all risk managers.

    A concrete risk manager consumes a `RiskContext` (a candidate
    `Signal`, the current `Portfolio`, and optional `MarketState`) and
    produces a single `RiskResult`. Concrete risk managers must not
    size positions, compute stop-loss/take-profit levels, place orders,
    or make trading/strategy decisions -- those remain the
    responsibility of a later Risk Engine part and/or the future
    `strategies/` trading-decision logic.

    Attributes:
        name: Human-readable name of this risk manager instance, used
            for logging/`repr`. Note `RiskResult` intentionally has no
            `risk_manager_name` field (mirroring `SignalResult`'s
            omission of `generator_name`) -- a concrete risk manager
            may record `name` in its own `metadata` if traceability is
            needed.
    """

    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name or self.__class__.__name__

    # ------------------------------------------------------------------
    # Abstract API
    # ------------------------------------------------------------------
    @abstractmethod
    def evaluate(self, context: RiskContext) -> RiskResult:
        """
        Evaluate `context` and return a single `RiskResult`.

        Implementations should call `self.validate_context(context)`
        first, and are expected to raise `strategies.risk_management.
        exceptions.InsufficientRiskDataError` when `context` does not
        carry enough data to produce a meaningful result.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def validate_context(self, context: RiskContext) -> RiskContext:
        """
        Validate that `context` is a usable `RiskContext` for this risk manager.

        Raises:
            InvalidRiskContextError: If `context` is not a
                `RiskContext` instance.
        """
        if not isinstance(context, RiskContext):
            raise InvalidRiskContextError(
                f"{self.name} expected a RiskContext, got {type(context).__name__}"
            )
        return context

    def _build_result(
        self,
        *,
        approved: bool,
        risk_score: float,
        confidence: float,
        summary: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> RiskResult:
        """
        Build a `RiskResult` using this risk manager's standard shape.

        Convenience helper so concrete risk managers don't repeat
        `RiskResult(...)` construction on every `evaluate()`
        implementation.
        """
        return RiskResult(
            approved=approved,
            risk_score=risk_score,
            confidence=confidence,
            summary=summary,
            metadata=metadata or {},
        )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(name={self.name!r})"
