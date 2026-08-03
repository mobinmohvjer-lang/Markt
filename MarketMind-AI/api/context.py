"""
api/context.py

Defines `APIRequestContext`: the immutable bundle of data every future
`BaseAPIHandler` will need in order to produce an `APIResult` for one
inbound HTTP request.

Part of the **inbound REST API foundation** (API Layer Part 1) -- see
`api/__init__.py` and `api/base.py`. Unrelated to this package's
existing outbound-transport role (`http_client.py`, `providers/`).

Unlike `AnalysisContext`/`SignalContext`/.../`ExecutionContext` one
layer down -- each of which composes specific domain entities for a
trading-decision pipeline -- `APIRequestContext` stays a generic HTTP
transport envelope (`method`, `path`, `query_params`, `headers`,
`body`, `metadata`), the same way `services.context.ServiceContext`
stays a generic `service_name` + `payload` + `metadata` envelope for
heterogeneous external integrations. It introduces no new domain
concepts and requires no routing/schema knowledge -- deciding how a
concrete route parses/validates `body` into a domain-specific shape
belongs to a later API Layer part (`routes/`, `schemas/`), not to this
foundation.

Pure data container -- no routing, no request dispatch, no server, no
authentication, no broker connection, no trading execution, and no AI.
Assembling an `APIRequestContext` from a real inbound HTTP request
remains future work (a `server.py`/`routes/` part of this same
package), the same gap `AnalysisContext`/`SignalContext`/.../
`ServiceContext` already document for their own layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from api.exceptions import APIValidationError, InvalidRequestContextError
from api.utils import validate_dict, validate_http_method, validate_path


@dataclass(frozen=True)
class APIRequestContext:
    """
    Everything a future `BaseAPIHandler` will need to handle one
    inbound HTTP request.

    Attributes:
        method: HTTP method of the request (e.g. `"GET"`, `"POST"`),
            normalized to upper-case. Validated against a fixed set of
            standard HTTP methods -- see `api.utils.VALID_HTTP_METHODS`.
        path: Request path, e.g. `"/signals"`. Must start with `"/"`.
        query_params: Parsed query-string parameters. Free-form (not
            interpreted here) -- a concrete future handler decides
            what it expects.
        headers: Request headers. Free-form (not interpreted here).
        body: Parsed request body, if any (e.g. a decoded JSON `dict`
            or `list`), or `None` when the request carries no body.
            Deliberately untyped/unvalidated beyond that -- defining a
            body *schema* belongs to a future `schemas/` module, not
            to this foundation.
        metadata: Free-form additional context supplied by the caller
            (e.g. a request identifier, provenance), kept for
            traceability. Not interpreted here.
    """

    method: str
    path: str
    query_params: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, Any] = field(default_factory=dict)
    body: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "method", validate_http_method(self.method))
            object.__setattr__(self, "path", validate_path(self.path))
            object.__setattr__(
                self, "query_params", validate_dict(self.query_params, name="query_params")
            )
            object.__setattr__(self, "headers", validate_dict(self.headers, name="headers"))
            object.__setattr__(self, "metadata", validate_dict(self.metadata, name="metadata"))
        except APIValidationError as exc:
            raise InvalidRequestContextError(str(exc)) from exc

    def has_body(self) -> bool:
        """Whether this context carries a (non-`None`) request body."""
        return self.body is not None

    def has_query_params(self) -> bool:
        """Whether this context carries any query-string parameters."""
        return len(self.query_params) > 0

    def get_header(self, name: str, default: Any = None) -> Any:
        """
        Return the value of header `name`, or `default` if absent.

        Performs a case-insensitive lookup, matching HTTP's own
        case-insensitive header-name semantics -- callers should not
        need to know how a given header was cased when it arrived.
        """
        target = name.lower()
        for key, value in self.headers.items():
            if isinstance(key, str) and key.lower() == target:
                return value
        return default
