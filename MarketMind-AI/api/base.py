"""
api/base.py

Defines `BaseAPIHandler`: the abstract base every concrete inbound
request handler will implement in a later API Layer part, once this
package grows an actual `routes/`/`server.py`.

Part of the **inbound REST API foundation** (API Layer Part 1) -- see
`api/__init__.py`. Mirrors the role `analysis/base.py`'s
`BaseAnalyzer`, `signals/base.py`'s `BaseSignalGenerator`,
`execution/base.py`'s `BaseExecutionEngine`, and `services/base.py`'s
`BaseService` each play for their own layer: it consumes an
`APIRequestContext` and produces a single `APIResult`, without
performing any actual HTTP dispatch, routing, authentication, broker
connection, trading execution, or AI -- all of which remain out of
scope for this part.

This is deliberately a small, framework-only contract -- API Layer
Part 1 ships no concrete handler, no route registration, no server, no
authentication, no broker connection, no trading execution, no AI, and
no UI. Per `PROJECT_RULES.md` Section 4, a future concrete handler
implementing this contract may only call into `app/` use cases -- never
directly into `core`, `data`, `analysis`, `signals`, etc. -- but this
foundation itself imports nothing beyond `api/`'s own modules, so that
rule has nothing to enforce yet.

**API Layer Part 3 (Response standardization)** adds two convenience
helpers alongside the original `_build_result` -- `_build_success_result`
and `_build_error_result` -- which wrap `body` in the standardized
response envelope defined in `api/response.py`. `_build_result` itself
is unchanged (still the older, unwrapped-`body` helper), so any
existing handler relying on it keeps behaving exactly as before.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from api.context import APIRequestContext
from api.exceptions import InvalidRequestContextError
from api.response import error_envelope, success_envelope
from api.result import APIResult


class BaseAPIHandler(ABC):
    """
    Abstract base class for all inbound API request handlers.

    A concrete handler (introduced in a later API Layer part) will
    consume an `APIRequestContext` (method, path, query params,
    headers, body, metadata for one inbound HTTP request) and produce
    a single `APIResult`. Concrete handlers are expected to:

        - Interpret `context` for their own purpose (e.g. calling a
          specific `app/` use case) -- `api/` itself defines no such
          behavior yet.
        - Determine the appropriate `status_code`/`body` given the
          outcome of that call.
        - Record every relevant detail in `APIResult.metadata`, so a
          result can always be traced back to the request that
          produced it.

    Concrete handlers must not place orders, connect to a broker,
    define trading rules, or perform any of the responsibilities that
    belong to `core/`, `analysis/`, `signals/`, `strategies/`,
    `execution/`, or `services/` directly -- per `PROJECT_RULES.md`
    Section 4, the inbound REST role of this package may only call
    into `app/` use cases.

    Attributes:
        name: Human-readable name of this handler instance, used for
            logging/`repr`. Note `APIResult` intentionally has no
            `handler_name` field (mirroring `RiskResult`'s omission of
            `risk_manager_name`) -- a concrete handler may record
            `name` in its own `metadata` if traceability is needed.
    """

    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name or self.__class__.__name__

    # ------------------------------------------------------------------
    # Abstract API
    # ------------------------------------------------------------------
    @abstractmethod
    def handle(self, context: APIRequestContext) -> APIResult:
        """
        Handle `context` and return a single `APIResult`.

        Implementations should call `self.validate_context(context)`
        first, and are expected to raise `api.exceptions.
        InsufficientAPIDataError` when `context` does not carry enough
        data (e.g. a required query parameter or body field is
        missing) to produce a meaningful result.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def validate_context(self, context: APIRequestContext) -> APIRequestContext:
        """
        Validate that `context` is a usable `APIRequestContext` for
        this handler.

        Raises:
            InvalidRequestContextError: If `context` is not an
                `APIRequestContext` instance.
        """
        if not isinstance(context, APIRequestContext):
            raise InvalidRequestContextError(
                f"{self.name} expected an APIRequestContext, got {type(context).__name__}"
            )
        return context

    def _build_result(
        self,
        *,
        status_code: int,
        body: Any = None,
        headers: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> APIResult:
        """
        Build an `APIResult` using this handler's standard shape.

        Convenience helper so concrete handlers don't repeat
        `APIResult(...)` construction on every `handle()`
        implementation.
        """
        return APIResult(
            status_code=status_code,
            body=body,
            headers=headers or {},
            metadata=metadata or {},
        )

    def _build_success_result(
        self,
        *,
        status_code: int = 200,
        data: Any = None,
        headers: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> APIResult:
        """
        Build a successful `APIResult` whose `body` is the standardized
        response envelope (`api.response.success_envelope`).

        Added in **API Layer Part 3 (Response standardization)** so
        every concrete handler's *successful* responses share one
        consistent `body` shape (`{"success", "status_code", "data",
        "error"}`) instead of a bespoke payload `dict` per handler.
        `_build_result` above is untouched and still available for a
        handler that needs the older, unwrapped `body` behavior.

        Parameters
        ----------
        status_code:
            Defaults to `200`. Must fall within `[200, 300)`, since
            this builds a *successful* envelope -- use
            `_build_error_result` for anything else.
        data:
            The handler's payload, passed through untouched into the
            envelope's `"data"` key.
        """
        if not (200 <= status_code < 300):
            raise ValueError(
                f"_build_success_result status_code must be within [200, 300), got {status_code}"
            )
        return self._build_result(
            status_code=status_code,
            body=success_envelope(status_code=status_code, data=data),
            headers=headers,
            metadata=metadata,
        )

    def _build_error_result(
        self,
        *,
        status_code: int,
        error_type: str,
        message: str,
        headers: Optional[dict[str, Any]] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> APIResult:
        """
        Build a failed `APIResult` whose `body` is the standardized
        response envelope (`api.response.error_envelope`).

        Added in **API Layer Part 3 (Response standardization)** --
        see `_build_success_result` above. Covers every failure
        category a concrete handler may need to report through one
        shared shape: validation errors, pipeline errors, and internal
        errors alike -- only `status_code`/`error_type`/`message`
        differ between them.

        Parameters
        ----------
        status_code:
            The HTTP status code this failure represents (e.g. `400`
            for a validation error, `404` for "not found", `500` for
            an internal error).
        error_type:
            A short, stable, machine-readable label for what went
            wrong -- typically the raised exception's class name.
        message:
            A short, human-readable description of what went wrong.
        """
        return self._build_result(
            status_code=status_code,
            body=error_envelope(status_code=status_code, error_type=error_type, message=message),
            headers=headers,
            metadata=metadata,
        )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(name={self.name!r})"
