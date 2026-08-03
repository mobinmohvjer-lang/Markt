"""
services package
------------------
Purpose:
    Wraps external integrations and cross-cutting technical concerns that
    are not pure market data (that belongs in `data`) and not business
    rules (that belongs in `core`). Mirrors the role `execution/` plays
    one layer down: each layer interprets/standardizes its predecessor's
    output without deciding what to do about it -- `services/` is where
    the rest of the application reaches out to the outside world (an
    alert, an AI/LLM call, a scheduled job, an event-bus dispatch)
    through one stable, standardized contract instead of a different
    shape per integration.

    Examples of what belongs here: notification services (e.g. Telegram
    or email alerts), a free AI/LLM client wrapper for AI-based analysis,
    scheduling/orchestration helpers, and any other "plumbing" service
    used by the application.

Contents (Services Part 1 -- foundation, new this milestone):
    - `BaseService` (`base.py`): abstract base every concrete service
      implements. Consumes a `ServiceContext` and produces a
      `ServiceResult` via an abstract `execute()` method, plus shared
      `validate_context`/`_build_result` helpers -- mirroring the exact
      role `analysis.base.BaseAnalyzer`, `signals.base.
      BaseSignalGenerator`, `strategies.base_strategy.BaseStrategy`,
      `strategies.risk_management.base.BaseRiskManager`, `strategies.
      portfolio_management.base.BasePortfolioManager`, and
      `execution.base.BaseExecutionEngine` play one layer down each.
    - `ServiceContext` (`context.py`): immutable bundle of a
      `service_name`, a free-form `payload`, and `metadata` -- no new
      domain concepts introduced. Unlike the contexts one layer down,
      it composes no domain entities: concrete services (notifications,
      AI/LLM calls, scheduling, event-bus dispatch) are heterogeneous by
      nature, so `payload` stays generic for each concrete service to
      interpret for itself.
    - `ServiceResult` (`result.py`): standardized output -- `success`
      (bool), `summary`, `metadata`. Deliberately minimal: no
      `service_name` field (mirroring `RiskResult`'s omission of
      `risk_manager_name` and `ExecutionResult`'s omission of
      `engine_name`), no delivery receipt, no provider/vendor
      identifiers, and -- unlike the trading-decision results one layer
      down -- no `confidence` field, since a service call either
      succeeded or it did not.
    - `ServiceError` hierarchy (`exceptions.py`): `ServiceError` ->
      `ServiceValidationError` -> `InvalidServiceContextError`, plus
      `InsufficientServiceDataError` and `ServiceConfigurationError`.
    - Shared validation helpers (`utils.py`).

    Framework only -- Services Part 1 ships no concrete service (no
    notification service, no AI/LLM client, no scheduler, no concrete
    `EventBus` implementation), no broker integration, no execution
    logic, no networking, no threading, no async, and no AI. Imported
    directly (`from services import BaseService, ServiceContext,
    ServiceResult, ...`), mirroring how `execution/` is imported
    directly rather than re-exported through a parent package's
    `__init__.py` (this package has no such parent).

Contents (Services Part 2A -- first concrete service, new this
milestone):
    - `SignalEngine` (`signal_engine.py`): the first concrete
      `BaseService` in this package. Will, in a future Services part
      (2B), publish an already-produced `core.entities.signal.Signal`
      as a `SignalGenerated` event via an injected
      `events.interfaces.event_bus.EventBus`. Despite the name, it is
      unrelated to (and does not import) the `signals/` package --
      `services/` may only depend on `core`/`events` (`PROJECT_RULES.md`
      Section 4). Part 2A ships only its public interfaces --
      constructor, dependency injection (an optional `EventBus`),
      validation (of that dependency and of engine configuration), and
      engine configuration (`SignalEngine.config`, merged with
      `SignalEngine.DEFAULT_CONFIG`) -- no orchestration logic:
      `execute()` validates its `ServiceContext` and then raises
      `NotImplementedError`, deferring the real
      build-Signal/publish-event/return-ServiceResult flow to Part 2B.
      See `signal_engine.py`'s own module docstring for full detail.

Planned contents (future Services parts):
    - `signal_engine.py`'s Part 2B: the orchestration logic
      `SignalEngine.execute()` currently defers -- interpreting
      `context.payload` as (or building) a `Signal`, applying
      `SignalEngine.config` (e.g. `min_confidence`), publishing it via
      `self.event_bus` when one is injected, and returning a
      `ServiceResult` reflecting what actually happened.
    - `notification_service.py`: sends alerts (e.g. Telegram bot, free
      tier).
    - `ai_service.py`: wrapper around a free/self-hosted AI model used
      for AI-driven market commentary or signal explanation.
    - `scheduler_service.py`: periodic job runner (e.g. APScheduler) to
      trigger analysis at fixed intervals.
    - A concrete `EventBus` implementation (see `events/interfaces/`).
"""

from __future__ import annotations

from services.base import BaseService
from services.context import ServiceContext
from services.exceptions import (
    InsufficientServiceDataError,
    InvalidServiceContextError,
    ServiceConfigurationError,
    ServiceError,
    ServiceValidationError,
)
from services.result import ServiceResult
from services.signal_engine import SignalEngine

__all__ = [
    "BaseService",
    "ServiceContext",
    "ServiceResult",
    "ServiceError",
    "ServiceValidationError",
    "InvalidServiceContextError",
    "InsufficientServiceDataError",
    "ServiceConfigurationError",
    "SignalEngine",
]
