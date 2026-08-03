"""
services/context.py

Defines `ServiceContext`: the immutable bundle of data every
`BaseService` needs in order to produce a `ServiceResult` for one
service call.

Unlike `AnalysisContext`/`SignalContext`/`StrategyContext`/
`RiskContext`/`PortfolioContext`/`BacktestContext`/`ExecutionContext`
one layer down -- each of which composes specific domain entities
(`Candle`, `Portfolio`, `StrategyResult`, ...) for a trading-decision
pipeline -- `services/` wraps external integrations and cross-cutting
technical concerns (notifications, an AI/LLM client wrapper,
scheduling, a concrete `EventBus`) that are heterogeneous by nature.
`ServiceContext` therefore introduces no new domain concepts either:
it stays a generic, free-form envelope (`service_name` + `payload` +
`metadata`) that any concrete service can interpret for its own
purposes, the same way `metadata` already does one layer down.

Pure data container -- no notification delivery, no AI/LLM calls, no
scheduling logic, no event-bus implementation, no networking, no
threading, no async. Assembling a `ServiceContext` from a real request
remains a future `app/` (or concrete-service) responsibility, the same
gap `AnalysisContext`/`SignalContext`/`RiskContext`/`StrategyContext`/
`PortfolioContext`/`BacktestContext`/`ExecutionContext` already
document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.exceptions import InvalidServiceContextError, ServiceValidationError
from services.utils import validate_dict, validate_non_empty_str


@dataclass(frozen=True)
class ServiceContext:
    """
    Everything a `BaseService` needs to carry out one service call.

    Attributes:
        service_name: Identifier of the target service/operation this
            call is for (e.g. "notification", "ai_commentary",
            "scheduler"). Concrete services use this the way a
            dispatcher would -- `ServiceContext` itself does not
            interpret it.
        payload: Free-form request data for the call (e.g. a
            notification message, a prompt, a job schedule). Its
            shape is entirely up to the concrete service that
            interprets it -- not interpreted here.
        metadata: Free-form additional context supplied by the caller
            (e.g. request identifiers, provenance), kept for
            traceability. Not interpreted here.
    """

    service_name: str
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self, "service_name", validate_non_empty_str(self.service_name, name="service_name")
            )
            object.__setattr__(self, "payload", validate_dict(self.payload, name="payload"))
            object.__setattr__(self, "metadata", validate_dict(self.metadata, name="metadata"))
        except ServiceValidationError as exc:
            raise InvalidServiceContextError(str(exc)) from exc

    def has_payload(self) -> bool:
        """Whether this context carries any payload data."""
        return bool(self.payload)
