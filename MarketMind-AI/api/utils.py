"""
api/utils.py

Shared, dependency-light validation helpers for the **inbound REST API
foundation** (API Layer Part 1) -- `api/base.py`'s `BaseAPIHandler`,
`api/context.py`'s `APIRequestContext`, and `api/result.py`'s
`APIResult` all validate/normalize their fields through this module,
mirroring the role `services/utils.py` plays for `services`,
`execution/utils.py` plays for `execution`, and `signals/utils.py`
plays for `signals`.

Distinct from this package's *existing* outbound-transport role
(`http_client.py`, `providers/`): those modules make requests to
third-party APIs and raise `api.exceptions.HTTPClientError` (and its
subclasses); this module supports the inbound side -- validating data
describing a request MarketMind-AI itself has received -- and raises
`api.exceptions.APIValidationError` (and its subclasses) instead. The
two hierarchies never mix.

No routing, no server, no broker connection, no trading execution, no
AI, no UI, and no authentication logic lives here -- only generic
validation and small pure helpers.
"""

from __future__ import annotations

from typing import Any, Optional

from api.exceptions import APIValidationError

#: HTTP methods accepted by `validate_http_method`. Deliberately the
#: standard REST-relevant subset -- no server exists yet to route any
#: of these, so this is only a normalization/validation vocabulary.
VALID_HTTP_METHODS = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
)


def validate_non_empty_str(value: str, *, name: str) -> str:
    """
    Validate that `value` is a non-empty (non-whitespace-only) string.

    Raises:
        APIValidationError: If `value` is not a `str`, or is empty
            after stripping whitespace.
    """
    if not isinstance(value, str) or not value.strip():
        raise APIValidationError(f"{name} must be a non-empty string, got {value!r}")
    return value


def validate_http_method(value: str, *, name: str = "method") -> str:
    """
    Validate and normalize an HTTP method string.

    Accepts any case (e.g. `"get"`, `"Get"`, `"GET"`) and returns the
    upper-cased form. This is validation/normalization only -- it does
    not imply any method is actually routable, since no server/routes
    exist yet in this foundation.

    Raises:
        APIValidationError: If `value` is not a non-empty string, or
            does not normalize to one of `VALID_HTTP_METHODS`.
    """
    normalized = validate_non_empty_str(value, name=name).upper()
    if normalized not in VALID_HTTP_METHODS:
        raise APIValidationError(
            f"{name} must be one of {sorted(VALID_HTTP_METHODS)}, got {value!r}"
        )
    return normalized


def validate_path(value: str, *, name: str = "path") -> str:
    """
    Validate that `value` is a non-empty string representing a
    leading-slash request path (e.g. `"/signals"`, `"/health"`).

    Raises:
        APIValidationError: If `value` is not a non-empty string, or
            does not start with `"/"`.
    """
    non_empty = validate_non_empty_str(value, name=name)
    if not non_empty.startswith("/"):
        raise APIValidationError(f"{name} must start with '/', got {value!r}")
    return non_empty


def validate_status_code(value: Any, *, name: str = "status_code") -> int:
    """
    Validate that `value` is a genuine `int` HTTP status code within
    the valid `[100, 599]` range.

    Raises:
        APIValidationError: If `value` is not an `int` (booleans are
            rejected even though `bool` is an `int` subclass), or is
            outside `[100, 599]`.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise APIValidationError(f"{name} must be an int, got {type(value).__name__}")
    if not (100 <= value <= 599):
        raise APIValidationError(f"{name} must be within [100, 599], got {value}")
    return value


def validate_dict(value: Any, *, name: str) -> dict:
    """
    Validate that `value` is a `dict`.

    Shared by `APIRequestContext.query_params`/`headers`/`metadata`
    and `APIResult.headers`/`metadata`, the same free-form
    supporting-data shape every other package's context/result types
    already use.

    Raises:
        APIValidationError: If `value` is not a `dict`.
    """
    if not isinstance(value, dict):
        raise APIValidationError(f"{name} must be a dict, got {type(value).__name__}")
    return value


def merge_metadata(*sources: Optional[dict[str, Any]]) -> dict[str, Any]:
    """
    Merge any number of metadata dicts into a new dict.

    Later sources take precedence over earlier ones on key conflicts.
    `None` entries are silently skipped, so callers can pass optional
    metadata dicts directly (e.g. `merge_metadata(base_meta, extra_meta)`).
    """
    merged: dict[str, Any] = {}
    for source in sources:
        if source:
            merged.update(source)
    return merged
