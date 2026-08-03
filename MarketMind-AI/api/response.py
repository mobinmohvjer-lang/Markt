"""
api/response.py

Defines the **standardized response envelope** every concrete
`BaseAPIHandler` should place in `APIResult.body`, plus the two small
functions that build it (`success_envelope`, `error_envelope`).

Part of **API Layer Part 3 (Response standardization only)** -- see
`api/__init__.py`. Builds directly on the inbound REST API foundation
API Layer Part 1 shipped (`api.result.APIResult`) and the first
concrete handler API Layer Part 2 shipped (`api.routes.signals.
SignalHandler`) -- this module changes neither. It only gives every
handler one shared, consistent shape to put inside `APIResult.body`,
instead of each handler inventing its own ad hoc success/error `dict`
layout (API Layer Part 2's `SignalHandler` previously returned
`{"error": "..."}}` on failure and a bare payload `dict` on success --
two different shapes; this module replaces both with one).

Envelope shape
--------------
Every `dict` this module builds has exactly these four keys, always in
the same order, whether the request succeeded or failed::

    {
        "success": bool,       # True iff 200 <= status_code < 300
        "status_code": int,    # mirrors the enclosing APIResult.status_code
        "data": Any | None,    # the handler's payload on success, else None
        "error": dict | None,  # {"type": str, "message": str} on failure, else None
    }

`data` and `error` are mutually exclusive: exactly one is `None`.
Whether a request was a validation failure, a pipeline failure, or an
unexpected internal failure only changes `status_code`/`error["type"]`
-- the envelope shape itself never changes, which is the point of this
module (see `PROJECT_STATE.md`/task scope: "Every `APIResult` should
have the same structure").

No business logic
------------------
This module computes nothing about trading, signals, or pipelines --
it only shapes already-computed data (a payload `dict` a handler
already built, or an exception's class name/message a handler already
caught) into one consistent container. It does not call `app/`,
`core/`, `data/`, `signals/`, `strategies/`, `services/`, or
`backtesting/`, and it does not itself catch or raise any exception.
"""

from __future__ import annotations

from typing import Any, Optional

from api.utils import validate_non_empty_str, validate_status_code


def success_envelope(*, status_code: int, data: Any = None) -> dict[str, Any]:
    """
    Build the standardized envelope for a successful response.

    Parameters
    ----------
    status_code:
        The HTTP status code this response represents. Validated via
        `api.utils.validate_status_code` -- an `int` within
        `[100, 599]`. `success` is derived from this value (`True` iff
        it falls in `[200, 300)`) rather than being a separate,
        independently-settable flag, so the two can never disagree.
    data:
        The handler's payload, if any (e.g. a serialized
        `signals.result.SignalResult`). Passed through untouched --
        this function does not inspect or reshape it.

    Returns
    -------
    dict
        `{"success": ..., "status_code": ..., "data": data, "error": None}`.
    """
    validated_status = validate_status_code(status_code, name="status_code")
    return {
        "success": 200 <= validated_status < 300,
        "status_code": validated_status,
        "data": data,
        "error": None,
    }


def error_envelope(*, status_code: int, error_type: str, message: str) -> dict[str, Any]:
    """
    Build the standardized envelope for a failed response.

    Parameters
    ----------
    status_code:
        The HTTP status code this response represents. Validated via
        `api.utils.validate_status_code`. Not required to fall outside
        `[200, 300)` -- callers are expected to pass an appropriate
        non-2xx code, but this function does not itself enforce that,
        matching `APIResult`'s own "pure data container" convention.
    error_type:
        A short, stable machine-readable label for what went wrong
        (e.g. `"InsufficientAPIDataError"`, `"PipelineDataError"`,
        `"InternalError"`) -- typically an exception class name, so a
        client can branch on it without parsing `message`.
    message:
        A short, human-readable description of what went wrong.

    Returns
    -------
    dict
        `{"success": False, "status_code": ..., "data": None,
        "error": {"type": error_type, "message": message}}`.
    """
    validated_status = validate_status_code(status_code, name="status_code")
    validated_type = validate_non_empty_str(error_type, name="error_type")
    validated_message = validate_non_empty_str(message, name="message")
    return {
        "success": False,
        "status_code": validated_status,
        "data": None,
        "error": {"type": validated_type, "message": validated_message},
    }


def is_envelope(value: Any) -> bool:
    """
    Whether `value` already has the standardized envelope's exact key
    set -- `{"success", "status_code", "data", "error"}`, no more, no
    fewer. Small helper for tests/consumers that need to confirm a
    given `APIResult.body` follows this module's shape, without
    re-deriving the key set inline.
    """
    return isinstance(value, dict) and set(value.keys()) == {
        "success",
        "status_code",
        "data",
        "error",
    }
