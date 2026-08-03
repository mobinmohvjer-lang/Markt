"""
services/base.py

Defines `BaseService`: the abstract base every concrete service
implements in later Services parts.

Mirrors the role `analysis/base.py`'s `BaseAnalyzer` plays for
`analysis/`, `signals/base.py`'s `BaseSignalGenerator` plays for
`signals/`, `strategies/base_strategy.py`'s `BaseStrategy` plays for
`strategies/`, `strategies/risk_management/base.py`'s
`BaseRiskManager` plays for `strategies.risk_management`,
`strategies/portfolio_management/base.py`'s `BasePortfolioManager`
plays for `strategies.portfolio_management`, and `execution/base.py`'s
`BaseExecutionEngine` plays for `execution/`: it consumes a
`ServiceContext` and produces a single standardized `ServiceResult`,
without performing any real notification delivery, AI/LLM call,
scheduling, event-bus dispatch, networking, threading, or async I/O
(all of which remain out of scope for this Services part, and belong
to a later Services part).

This is deliberately a small, framework-only contract -- Services Part
1 ships no concrete service (no notification service, no AI/LLM client,
no scheduler, no `EventBus` implementation), no broker integration, no
execution logic, no threading, no async, and no AI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from services.context import ServiceContext
from services.exceptions import InvalidServiceContextError
from services.result import ServiceResult


class BaseService(ABC):
    """
    Abstract base class for all services.

    A concrete service consumes a `ServiceContext` (a `service_name`,
    a free-form `payload`, and `metadata`) and produces a single
    `ServiceResult`. Concrete services are expected to:

        - Interpret `context.payload` for their own purpose (e.g.
          sending a notification, calling an AI/LLM provider,
          scheduling a job, dispatching an event) -- `services/`
          itself defines no such behavior.
        - Determine `success` given the outcome of that call.
        - Record every relevant detail in `ServiceResult.metadata`, so
          a result can always be traced back to the call that produced
          it.

    Concrete services must not place orders, define trading rules, or
    perform any of the responsibilities that belong to `analysis/`,
    `signals/`, `strategies/`, `backtesting/`, or `execution/` -- this
    package only wraps external integrations and cross-cutting
    technical concerns.

    Attributes:
        name: Human-readable name of this service instance, used for
            logging/`repr`. Note `ServiceResult` intentionally has no
            `service_name` field (mirroring `RiskResult`'s omission of
            `risk_manager_name` and `ExecutionResult`'s omission of
            `engine_name`) -- a concrete service may record `name` in
            its own `metadata` if traceability is needed.
    """

    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name or self.__class__.__name__

    # ------------------------------------------------------------------
    # Abstract API
    # ------------------------------------------------------------------
    @abstractmethod
    def execute(self, context: ServiceContext) -> ServiceResult:
        """
        Carry out `context` and return a single `ServiceResult`.

        Implementations should call `self.validate_context(context)`
        first, and are expected to raise `services.exceptions.
        InsufficientServiceDataError` when `context` does not carry
        enough data to perform a meaningful service call.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def validate_context(self, context: ServiceContext) -> ServiceContext:
        """
        Validate that `context` is a usable `ServiceContext` for this service.

        Raises:
            InvalidServiceContextError: If `context` is not a
                `ServiceContext` instance.
        """
        if not isinstance(context, ServiceContext):
            raise InvalidServiceContextError(
                f"{self.name} expected a ServiceContext, got {type(context).__name__}"
            )
        return context

    def _build_result(
        self,
        *,
        success: bool,
        summary: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ServiceResult:
        """
        Build a `ServiceResult` using this service's standard shape.

        Convenience helper so concrete services don't repeat
        `ServiceResult(...)` construction on every `execute()`
        implementation.
        """
        return ServiceResult(
            success=success,
            summary=summary,
            metadata=metadata or {},
        )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(name={self.name!r})"
