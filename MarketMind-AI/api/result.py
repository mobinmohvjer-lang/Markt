"""
api/result.py

Defines `APIResult`: the standardized output produced by every future
`BaseAPIHandler.handle()` call, regardless of which concrete handler
produced it.

Part of the **inbound REST API foundation** (API Layer Part 1) -- see
`api/__init__.py` and `api/base.py`. Unrelated to this package's
existing outbound-transport role (`http_client.py`, `providers/`);
in particular, `APIResult` is not the response received *from* a
third-party API call (that lives in `http_client.HTTPClient`) -- it is
the response MarketMind-AI itself will produce *for* an inbound
request.

Pure data container -- no serialization to an actual HTTP response, no
routing, no server. This lets a future consumer (a concrete handler, a
future `server.py`) depend on one stable shape instead of a different
result type per handler.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from api.utils import merge_metadata, validate_dict, validate_status_code


@dataclass(frozen=True)
class APIResult:
    """
    The standardized output of a single (future) API handler run.

    Deliberately minimal, mirroring the results other foundation-only
    packages already produce (`ServiceResult`, `ExecutionResult`): no
    `handler_name` field (a concrete handler may record its own `name`
    in `metadata` if traceability is needed -- the same convention
    `RiskResult` uses for `risk_manager_name`), and no actual HTTP
    wire-format serialization -- that remains out of scope for API
    Layer Part 1 (framework only).

    Attributes:
        status_code: HTTP status code this result represents, as an
            `int` within `[100, 599]`.
        body: Response payload, if any (e.g. a `dict` to later be
            serialized as JSON), or `None` for a body-less response.
            Deliberately untyped/unvalidated beyond that -- defining a
            response *schema* belongs to a future `schemas/` module.
        headers: Response headers to include, if any. Free-form (not
            interpreted here).
        metadata: Handler-specific supporting details (e.g. which
            upstream result this was derived from, intermediate
            values), kept for traceability. Never serialized as part
            of the actual HTTP response -- that remains `body`'s role.
    """

    status_code: int
    body: Any = None
    headers: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # dataclass is frozen, so field re-assignment goes through
        # object.__setattr__ -- this only normalizes/validates values,
        # it never introduces new state.
        object.__setattr__(
            self, "status_code", validate_status_code(self.status_code, name="status_code")
        )
        object.__setattr__(self, "headers", validate_dict(self.headers, name="headers"))
        object.__setattr__(self, "metadata", validate_dict(self.metadata, name="metadata"))

    def is_success(self) -> bool:
        """Whether `status_code` falls within the `2xx` range."""
        return 200 <= self.status_code < 300

    def with_metadata(self, **extra: Any) -> "APIResult":
        """
        Return a new `APIResult` with `extra` merged into `metadata`.

        Since `APIResult` is immutable, this returns a new instance
        rather than mutating the existing one.
        """
        return APIResult(
            status_code=self.status_code,
            body=self.body,
            headers=self.headers,
            metadata=merge_metadata(self.metadata, extra),
        )
