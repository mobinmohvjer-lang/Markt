"""
strategies/risk_management/result.py

Defines `RiskResult`: the standardized output produced by every
`BaseRiskManager.evaluate()` call, regardless of which concrete risk
manager produced it.

Pure data container -- no calculation, no position sizing, no
stop-loss/take-profit logic, no order execution. This lets a future
consumer (`strategies/`'s own trading-decision logic, or a later Risk
Engine part) depend on one stable shape instead of a different result
type per risk manager.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from strategies.risk_management.utils import (
    merge_metadata,
    validate_bool,
    validate_non_empty_str,
    validate_unit_range,
)


@dataclass(frozen=True)
class RiskResult:
    """
    The standardized output of a single risk manager run.

    Attributes:
        approved: Whether the evaluated signal is safe/allowed to act
            on, per this risk manager's checks. Deliberately just a
            `bool` -- *how much* to trade, where to place protective
            levels, and whether to actually place an order are all out
            of scope for this result type (later Risk Engine parts / a
            future `Strategy`/order-execution layer, not this one).
        risk_score: Numeric risk assessment in the closed range
            [0.0, 1.0] (`0.0` = no risk, `1.0` = maximum risk).
        confidence: How confident the risk manager is in `risk_score`/
            `approved`, expressed as a float in the closed range
            [0.0, 1.0].
        summary: Short, human-readable explanation of the result.
        metadata: Risk-manager-specific supporting details (e.g. which
            checks ran, intermediate values), kept for traceability.
    """

    approved: bool
    risk_score: float
    confidence: float
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # dataclass is frozen, so field re-assignment goes through
        # object.__setattr__ -- this only normalizes/validates values,
        # it never introduces new state.
        object.__setattr__(self, "approved", validate_bool(self.approved, name="approved"))
        object.__setattr__(
            self, "risk_score", validate_unit_range(self.risk_score, name="risk_score")
        )
        object.__setattr__(
            self, "confidence", validate_unit_range(self.confidence, name="confidence")
        )
        object.__setattr__(self, "summary", validate_non_empty_str(self.summary, name="summary"))
        if not isinstance(self.metadata, dict):
            raise TypeError(f"metadata must be a dict, got {type(self.metadata).__name__}")

    def with_metadata(self, **extra: Any) -> "RiskResult":
        """
        Return a new `RiskResult` with `extra` merged into `metadata`.

        Since `RiskResult` is immutable, this returns a new instance
        rather than mutating the existing one.
        """
        return RiskResult(
            approved=self.approved,
            risk_score=self.risk_score,
            confidence=self.confidence,
            summary=self.summary,
            metadata=merge_metadata(self.metadata, extra),
        )
