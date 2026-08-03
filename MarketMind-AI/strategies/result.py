"""
strategies/result.py

Defines `StrategyResult`: the standardized output produced by every
`BaseStrategy.decide()` call, regardless of which concrete strategy
produced it.

Pure data container -- no decision logic, no position sizing, no
stop-loss/take-profit, no order execution. This lets a future consumer
(`backtesting/`, `app/`'s orchestration layer) depend on one stable
shape instead of a different result type per strategy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.enums import SignalDirection

from strategies.utils import (
    merge_metadata,
    validate_action,
    validate_non_empty_str,
    validate_unit_range,
)


@dataclass(frozen=True)
class StrategyResult:
    """
    The standardized output of a single strategy run.

    Deliberately minimal, mirroring `signals.result.SignalResult` and
    `strategies.risk_management.result.RiskResult`: no `strategy_name`
    field (a concrete strategy may record `name` in its own `metadata`
    if traceability is needed -- the same convention `RiskResult` uses
    for `risk_manager_name`), no position size, no stop-loss/
    take-profit, no order-id. Those remain out of scope for Strategy
    Engine Part 1 (framework only) and ultimately belong to a later
    Strategy Engine part and/or a future order-execution layer.

    Attributes:
        action: The trading decision, reusing `core.enums.
            SignalDirection` (buy/sell/hold) rather than inventing a
            new enum, the same convention `signals.result.
            SignalResult.direction` follows.
        confidence: How confident the strategy is in `action`,
            expressed as a float in the closed range [0.0, 1.0].
        summary: Short, human-readable explanation of the result.
        metadata: Strategy-specific supporting details (e.g. which
            `AnalysisResult`/`SignalResult`/`RiskResult` contributed,
            intermediate values), kept for traceability.
    """

    action: SignalDirection
    confidence: float
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # dataclass is frozen, so field re-assignment goes through
        # object.__setattr__ -- this only normalizes/validates values,
        # it never introduces new state.
        object.__setattr__(self, "action", validate_action(self.action))
        object.__setattr__(
            self, "confidence", validate_unit_range(self.confidence, name="confidence")
        )
        object.__setattr__(self, "summary", validate_non_empty_str(self.summary, name="summary"))
        if not isinstance(self.metadata, dict):
            raise TypeError(f"metadata must be a dict, got {type(self.metadata).__name__}")

    def with_metadata(self, **extra: Any) -> "StrategyResult":
        """
        Return a new `StrategyResult` with `extra` merged into `metadata`.

        Since `StrategyResult` is immutable, this returns a new
        instance rather than mutating the existing one.
        """
        return StrategyResult(
            action=self.action,
            confidence=self.confidence,
            summary=self.summary,
            metadata=merge_metadata(self.metadata, extra),
        )
