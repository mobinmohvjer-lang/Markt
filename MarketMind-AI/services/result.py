"""
services/result.py

Defines `ServiceResult`: the standardized output produced by every
`BaseService.execute()` call, regardless of which concrete service
produced it.

Pure data container -- no notification delivery, no AI/LLM calls, no
scheduling logic, no event-bus implementation, no networking, no
threading, no async. This lets a future consumer (a concrete service,
or `app/`'s orchestration layer) depend on one stable shape instead of
a different result type per service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.utils import merge_metadata, validate_bool, validate_dict, validate_non_empty_str


@dataclass(frozen=True)
class ServiceResult:
    """
    The standardized output of a single service call.

    Deliberately minimal, mirroring the results one layer down
    (`AnalysisResult`, `SignalResult`, `StrategyResult`, `RiskResult`,
    `PortfolioResult`, `BacktestResult`, `ExecutionResult`): no
    `service_name` field (a concrete service may record its own `name`
    in `metadata` if traceability is needed -- the same convention
    `RiskResult` uses for `risk_manager_name`), no delivery receipt, no
    provider/vendor identifiers. Those remain out of scope for Services
    Part 1 (framework only) -- no AI, no broker, no execution logic, no
    threading, no async.

    Unlike the trading-decision results one layer down, `ServiceResult`
    has no `confidence` field: a service call either succeeded or it
    did not -- there is no probabilistic evaluation to express here.

    Attributes:
        success: Whether the service call completed successfully, per
            this service's own definition of success. Deliberately
            just a `bool` -- *how* the call was carried out (which
            provider, which transport) is entirely out of scope for
            this result type.
        summary: Short, human-readable explanation of the result.
        metadata: Service-specific supporting details (e.g. which
            provider handled the call, intermediate values), kept for
            traceability.
    """

    success: bool
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # dataclass is frozen, so field re-assignment goes through
        # object.__setattr__ -- this only normalizes/validates values,
        # it never introduces new state.
        object.__setattr__(self, "success", validate_bool(self.success, name="success"))
        object.__setattr__(self, "summary", validate_non_empty_str(self.summary, name="summary"))
        object.__setattr__(self, "metadata", validate_dict(self.metadata, name="metadata"))

    def with_metadata(self, **extra: Any) -> "ServiceResult":
        """
        Return a new `ServiceResult` with `extra` merged into `metadata`.

        Since `ServiceResult` is immutable, this returns a new instance
        rather than mutating the existing one.
        """
        return ServiceResult(
            success=self.success,
            summary=self.summary,
            metadata=merge_metadata(self.metadata, extra),
        )
