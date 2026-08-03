"""
execution/result.py

Defines `ExecutionResult`: the standardized output produced by every
`BaseExecutionEngine.execute()` call, regardless of which concrete
execution engine produced it.

Pure data container -- no order placement, no broker/exchange
integration, no networking. This lets a future consumer (later
Execution Engine parts, `app/`'s orchestration layer) depend on one
stable shape instead of a different result type per execution engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from execution.utils import (
    merge_metadata,
    validate_bool,
    validate_non_empty_str,
    validate_unit_range,
)


@dataclass(frozen=True)
class ExecutionResult:
    """
    The standardized output of a single execution-engine run.

    Deliberately minimal, mirroring `strategies.result.StrategyResult`,
    `strategies.risk_management.result.RiskResult`, and `strategies.
    portfolio_management.result.PortfolioResult`: no `engine_name`
    field (a concrete execution engine may record `name` in its own
    `metadata` if traceability is needed -- the same convention
    `RiskResult` uses for `risk_manager_name`), no order-id, no fill
    price/quantity, no broker/exchange identifiers. Those remain out
    of scope for Execution Engine Part 1 (framework only) -- no
    broker integration, no exchange API, no order execution, no
    networking, no threading, no async, no AI.

    Attributes:
        execution_approved: Whether the candidate trading decision
            under evaluation is cleared to proceed toward actual order
            placement, per this execution engine's checks. Deliberately
            just a `bool` -- *how* an order would be placed (routing,
            order type, broker/exchange call) is entirely out of scope
            for this result type, exactly as `RiskResult.approved` and
            `PortfolioResult.new_positions_allowed` do not decide *how*
            to size or allocate a trade one layer down each.
        confidence: How confident the execution engine is in
            `execution_approved`, expressed as a float in the closed
            range [0.0, 1.0].
        summary: Short, human-readable explanation of the result.
        metadata: Engine-specific supporting details (e.g. which
            upstream results were available, intermediate values),
            kept for traceability.
    """

    execution_approved: bool
    confidence: float
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # dataclass is frozen, so field re-assignment goes through
        # object.__setattr__ -- this only normalizes/validates values,
        # it never introduces new state.
        object.__setattr__(
            self,
            "execution_approved",
            validate_bool(self.execution_approved, name="execution_approved"),
        )
        object.__setattr__(
            self, "confidence", validate_unit_range(self.confidence, name="confidence")
        )
        object.__setattr__(self, "summary", validate_non_empty_str(self.summary, name="summary"))
        if not isinstance(self.metadata, dict):
            raise TypeError(f"metadata must be a dict, got {type(self.metadata).__name__}")

    def with_metadata(self, **extra: Any) -> "ExecutionResult":
        """
        Return a new `ExecutionResult` with `extra` merged into `metadata`.

        Since `ExecutionResult` is immutable, this returns a new
        instance rather than mutating the existing one.
        """
        return ExecutionResult(
            execution_approved=self.execution_approved,
            confidence=self.confidence,
            summary=self.summary,
            metadata=merge_metadata(self.metadata, extra),
        )
