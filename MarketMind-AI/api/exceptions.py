"""
api/exceptions.py

Custom exception hierarchies for the `api` package's two, unrelated
responsibilities (see `api/__init__.py`):

    1. Outbound HTTP transport (existing) -- `HTTPClientError` and its
       subclasses below, raised by `http_client.py`/`providers/*` when
       a call *to* a third-party API fails. Keeping these separate
       from `http_client.py` lets provider modules (`api/providers/*`)
       depend only on `exceptions.py` without importing the transport
       implementation, which keeps the dependency graph clean and
       makes the exceptions easy to reuse/mock in tests.

    2. Inbound REST API foundation (API Layer Part 1, new) --
       `InboundAPIError`/`APIValidationError` and their subclasses
       below, raised by `base.py`/`context.py`/`result.py`/`utils.py`
       when data describing a request *received by* MarketMind-AI
       itself fails validation. Named `InboundAPIError` (rather than
       `APIError`) specifically to avoid being mistaken for a sibling
       of `APIStatusError`/`HTTPClientError` above -- it is a
       deliberately separate hierarchy. Mirrors the pattern already
       used by `signals/exceptions.py`, `execution/exceptions.py`, and
       `services/exceptions.py` for their own foundations.

These two hierarchies are deliberately unrelated (neither subclasses
the other) so a caller can never confuse an outbound transport failure
with an inbound validation failure.
"""

from __future__ import annotations

from typing import Optional

from requests import Response


class HTTPClientError(Exception):
    """Base class for all errors raised by the API layer."""


class RequestTimeoutError(HTTPClientError):
    """Raised when a request exceeds the configured timeout after all retries."""


class ConnectionFailedError(HTTPClientError):
    """Raised when the client cannot reach the remote host after all retries."""


class RateLimitError(HTTPClientError):
    """Raised when the remote API responds with a rate-limit status (HTTP 429)."""

    def __init__(
        self,
        message: str,
        retry_after: Optional[float] = None,
        response: Optional[Response] = None,
    ) -> None:
        super().__init__(message)
        self.retry_after = retry_after
        self.response = response


class APIStatusError(HTTPClientError):
    """Raised for non-2xx responses that are not rate-limit related."""

    def __init__(
        self,
        message: str,
        status_code: int,
        response: Optional[Response] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class RetriesExhaustedError(HTTPClientError):
    """Raised when every retry attempt has been used without a successful response."""


class InvalidResponseError(HTTPClientError):
    """Raised when a response cannot be decoded/parsed as expected (e.g. bad JSON)."""


# ---------------------------------------------------------------------
# Inbound REST API foundation (API Layer Part 1)
# ---------------------------------------------------------------------
# Everything below is unrelated to HTTPClientError above -- it is the
# exception hierarchy for api/base.py, api/context.py, api/result.py,
# and api/utils.py (the inbound REST API foundation), not for the
# outbound transport role. See this module's docstring.


class InboundAPIError(Exception):
    """Base class for all errors raised by the inbound REST API foundation."""


class APIValidationError(InboundAPIError):
    """Raised when an `APIResult` or `APIRequestContext` field fails validation."""


class InvalidRequestContextError(APIValidationError):
    """Raised when an `APIRequestContext` is missing required data or malformed."""


class InsufficientAPIDataError(InboundAPIError):
    """
    Raised by a `BaseAPIHandler` when the supplied `APIRequestContext`
    does not contain enough data (e.g. a required query parameter or
    body field is missing) to produce a meaningful `APIResult`.
    """


class APIHandlerConfigurationError(InboundAPIError):
    """Raised when an API handler is constructed or used with invalid configuration/parameters."""
