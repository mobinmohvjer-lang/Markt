"""
api package
------------
Purpose:
    Two, unrelated responsibilities coexist in this package (see
    `DEVELOPER_GUIDE.md`'s `api/` entry -- be explicit about which one
    you're extending):

    1. Outbound HTTP transport (existing) -- the "external services"
       boundary for outbound HTTP calls to third-party data sources
       (Binance, CoinGecko, news APIs, ...): `http_client.py` provides
       a resilient, dependency-injection-friendly transport,
       `exceptions.py` defines the `HTTPClientError` hierarchy it
       raises, and `providers/` contains thin, single-responsibility
       wrappers around each external REST API. Contains no trading
       logic, no indicators, no AI/model code, and no signal
       generation.

    2. Inbound REST API foundation (API Layer Part 1, new this
       milestone) -- the framework this project's *own* future HTTP
       interface will be built on, per `PROJECT_RULES.md` Section 1
       principle 6 ("API is the outermost adapter"): `base.py` defines
       `BaseAPIHandler`, the abstract base every concrete inbound
       request handler will implement; `context.py`/`result.py`
       define the `APIRequestContext`/`APIResult` data shapes a
       handler consumes/produces; `exceptions.py` additionally defines
       the separate `InboundAPIError` hierarchy for this role;
       `utils.py` provides shared validation helpers. Framework only
       -- no route registration, no server, no broker connection, no
       trading execution, no AI, no UI, and no authentication.

Contents (API Layer Part 1 -- inbound REST foundation, new this
milestone):
    - `BaseAPIHandler` (`base.py`): abstract base every concrete
      inbound request handler will implement. Consumes an
      `APIRequestContext` and produces an `APIResult` via an abstract
      `handle()` method, plus shared `validate_context`/`_build_result`
      helpers -- mirroring the exact role `analysis.base.BaseAnalyzer`,
      `signals.base.BaseSignalGenerator`, `execution.base.
      BaseExecutionEngine`, and `services.base.BaseService` play for
      their own layers.
    - `APIRequestContext` (`context.py`): immutable bundle of
      `method`, `path`, `query_params`, `headers`, `body`, and
      `metadata` for one inbound HTTP request -- a generic HTTP
      transport envelope, the same way `services.context.
      ServiceContext` stays generic for heterogeneous external
      integrations. No new domain concepts introduced.
    - `APIResult` (`result.py`): standardized output -- `status_code`,
      `body`, `headers`, `metadata`. Deliberately minimal: no
      `handler_name` field (mirroring `RiskResult`'s omission of
      `risk_manager_name`), no actual HTTP wire-format serialization.
    - `InboundAPIError` hierarchy (`exceptions.py`, appended to the
      existing outbound `HTTPClientError` hierarchy in the same file):
      `InboundAPIError` -> `APIValidationError` ->
      `InvalidRequestContextError`, plus `InsufficientAPIDataError`
      and `APIHandlerConfigurationError`. Deliberately unrelated to
      `HTTPClientError` -- neither hierarchy subclasses the other.
    - Shared validation helpers (`utils.py`).

    Framework only -- ships no concrete handler, no route
    registration, no server, no broker connection, no trading
    execution, no AI, no UI, and no authentication.

Contents (API Layer Part 2 -- Signal endpoint only, new this
milestone):
    - `routes/` (`routes/signals.py`): `SignalHandler`, the first
      concrete `BaseAPIHandler` implementation. A thin adapter that
      reads `symbol`/`timeframe` off an `APIRequestContext` and calls
      the existing `app.main.MainApplication.run(symbol, timeframe)`
      (the Data -> Indicators -> Analysis -> Signals pipeline),
      returning the resulting `signals.result.SignalResult` wrapped in
      an `APIResult`. No business logic, no strategy/risk/portfolio/
      execution, no broker connection, no AI, no authentication, and no
      web server framework -- still no route registration or server;
      see `routes/__init__.py` and `routes/signals.py` for the full
      scope boundary.

Contents (API Layer Part 3 -- Response standardization only, new this
milestone):
    - `response.py`: `success_envelope`/`error_envelope`, the two
      functions that build the standardized response envelope --
      `{"success", "status_code", "data", "error"}` -- every concrete
      handler's `APIResult.body` should now use, whether the outcome
      was a success, a validation error, a pipeline error, or an
      internal error. `BaseAPIHandler` (`base.py`) gained two matching
      convenience methods, `_build_success_result`/`_build_error_result`,
      alongside the original (unchanged) `_build_result`. `routes/
      signals.py`'s `SignalHandler` was updated to use them -- no
      other behavior of `SignalHandler` changed; see its module
      docstring, "Response categories". No business logic, no new
      route/server/auth/broker/AI/execution -- this milestone only
      changes how already-computed outcomes are shaped into `body`.

Planned contents (future API Layer parts):
    - schemas/: request/response models used only for serialization at
      the API boundary (what `APIRequestContext.body`/`APIResult.body`
      deliberately leave unvalidated in this foundation).
    - server.py: application/server bootstrap (e.g. FastAPI instance)
      that assembles a real `APIRequestContext` per request and
      dispatches it to the matching `BaseAPIHandler` (e.g.
      `routes.signals.SignalHandler`).
    - dependencies.py: shared FastAPI dependencies (e.g. settings injection).
    - Additional `routes/` handlers for other resources (e.g. market
      data, backtests), each calling into its own `app/` use case.
"""

from __future__ import annotations

from api.base import BaseAPIHandler
from api.context import APIRequestContext
from api.exceptions import (
    APIHandlerConfigurationError,
    APIStatusError,
    APIValidationError,
    ConnectionFailedError,
    HTTPClientError,
    InboundAPIError,
    InsufficientAPIDataError,
    InvalidRequestContextError,
    InvalidResponseError,
    RateLimitError,
    RequestTimeoutError,
    RetriesExhaustedError,
)
from api.http_client import HTTPClient, RateLimiter, RetryConfig
from api.response import error_envelope, is_envelope, success_envelope
from api.result import APIResult
from api.routes import SignalHandler

__all__ = [
    # Outbound HTTP transport (existing)
    "HTTPClient",
    "RateLimiter",
    "RetryConfig",
    "HTTPClientError",
    "RequestTimeoutError",
    "ConnectionFailedError",
    "RateLimitError",
    "APIStatusError",
    "RetriesExhaustedError",
    "InvalidResponseError",
    # Inbound REST API foundation (API Layer Part 1, new)
    "BaseAPIHandler",
    "APIRequestContext",
    "APIResult",
    "InboundAPIError",
    "APIValidationError",
    "InvalidRequestContextError",
    "InsufficientAPIDataError",
    "APIHandlerConfigurationError",
    # Inbound REST API -- Signal endpoint (API Layer Part 2, new)
    "SignalHandler",
    # Inbound REST API -- Response standardization (API Layer Part 3, new)
    "success_envelope",
    "error_envelope",
    "is_envelope",
]
