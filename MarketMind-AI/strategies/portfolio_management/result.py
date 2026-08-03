"""
strategies/portfolio_management/result.py

Defines `PortfolioResult`: the standardized output produced by every
`BasePortfolioManager.evaluate()` call, regardless of which concrete
portfolio manager produced it.

Pure data container -- no allocation logic, no rebalancing, no
optimization, no order execution. This lets a future consumer (later
Portfolio Management parts, `backtesting/`, `app/`) depend on one
stable shape instead of a different result type per portfolio manager.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from strategies.portfolio_management.utils import (
    merge_metadata,
    validate_bool,
    validate_non_empty_str,
    validate_unit_range,
)


@dataclass(frozen=True)
class PortfolioResult:
    """
    The standardized output of a single portfolio-manager run.

    Deliberately minimal, mirroring `strategies.result.StrategyResult`
    and `strategies.risk_management.result.RiskResult`: no
    `portfolio_manager_name` field (a concrete portfolio manager may
    record `name` in its own `metadata` if traceability is needed --
    the same convention `RiskResult` uses for `risk_manager_name`), no
    target allocation, no rebalancing instructions, no order-id. Those
    remain out of scope for Portfolio Management Part 1 (framework
    only) and ultimately belong to a later Portfolio Management part.

    Attributes:
        new_positions_allowed: Whether a new position may be opened
            for the candidate trade under evaluation, per this
            portfolio manager's constraints. Deliberately just a
            `bool` -- *how much* to allocate, whether to rebalance
            existing positions, and whether to actually place an order
            are all out of scope for this result type (a later
            Portfolio Management part / a future order-execution
            layer, not this one).
        confidence: How confident the portfolio manager is in
            `new_positions_allowed`, expressed as a float in the
            closed range [0.0, 1.0].
        summary: Short, human-readable explanation of the result.
        metadata: Portfolio-manager-specific supporting details (e.g.
            which constraints were checked, intermediate values), kept
            for traceability.
    """

    new_positions_allowed: bool
    confidence: float
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # dataclass is frozen, so field re-assignment goes through
        # object.__setattr__ -- this only normalizes/validates values,
        # it never introduces new state.
        object.__setattr__(
            self,
            "new_positions_allowed",
            validate_bool(self.new_positions_allowed, name="new_positions_allowed"),
        )
        object.__setattr__(
            self, "confidence", validate_unit_range(self.confidence, name="confidence")
        )
        object.__setattr__(self, "summary", validate_non_empty_str(self.summary, name="summary"))
        if not isinstance(self.metadata, dict):
            raise TypeError(f"metadata must be a dict, got {type(self.metadata).__name__}")

    def with_metadata(self, **extra: Any) -> "PortfolioResult":
        """
        Return a new `PortfolioResult` with `extra` merged into `metadata`.

        Since `PortfolioResult` is immutable, this returns a new
        instance rather than mutating the existing one.
        """
        return PortfolioResult(
            new_positions_allowed=self.new_positions_allowed,
            confidence=self.confidence,
            summary=self.summary,
            metadata=merge_metadata(self.metadata, extra),
        )
