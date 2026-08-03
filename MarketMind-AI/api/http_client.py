"""
api/http_client.py

Production-ready HTTP transport layer used as the foundation for all
external API providers (Binance, CoinGecko, News, ...).

Design goals
------------
- Single responsibility: transport only. No trading logic, no
  indicators, no AI, no domain parsing beyond generic JSON decoding.
- Dependency-injection friendly: the `requests.Session`, the
  `logging.Logger`, and the rate limiter can all be supplied by the
  caller, which makes this class trivial to unit test and to reuse
  across providers with different configurations.
- Resilient: configurable timeouts, retries with exponential backoff
  (+ optional jitter), and predictable custom exceptions instead of
  leaking raw `requests` exceptions to callers.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Protocol, Tuple

import requests
from requests import Response, Session

from api.exceptions import (
    APIStatusError,
    ConnectionFailedError,
    HTTPClientError,
    InvalidResponseError,
    RateLimitError,
    RequestTimeoutError,
    RetriesExhaustedError,
)

__all__ = [
    "RetryConfig",
    "RateLimiter",
    "RateLimiterProtocol",
    "HTTPClient",
]


# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------

@dataclass
class RetryConfig:
    """Configuration for the retry/backoff behavior of HTTPClient."""

    total: int = 3
    backoff_factor: float = 0.5
    max_backoff: float = 30.0
    jitter: bool = True
    retry_on_status: Tuple[int, ...] = (429, 500, 502, 503, 504)

    def backoff_seconds(self, attempt: int) -> float:
        """Exponential backoff: backoff_factor * 2**attempt, capped and jittered."""
        delay = self.backoff_factor * (2 ** attempt)
        delay = min(delay, self.max_backoff)
        if self.jitter:
            delay = random.uniform(0, delay)
        return delay


# ---------------------------------------------------------------------------
# Rate limiting hooks
# ---------------------------------------------------------------------------

class RateLimiterProtocol(Protocol):
    """Any object with an `acquire()` method can be injected as a rate limiter."""

    def acquire(self) -> None:
        ...


class RateLimiter:
    """
    Minimal thread-safe rate limiter enforcing a fixed minimum interval
    between calls. This is intentionally simple (not a full token
    bucket) so it stays dependency-free; providers needing a more
    elaborate policy can inject their own object satisfying
    RateLimiterProtocol instead.
    """

    def __init__(self, min_interval: float = 0.0) -> None:
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last_call: float = 0.0

    def acquire(self) -> None:
        if self.min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            wait = self.min_interval - (now - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class HTTPClient:
    """
    Thin, resilient wrapper around `requests.Session`.

    All dependencies (session, logger, rate limiter, retry config) are
    injectable via the constructor so this class -- and anything built
    on top of it -- is easy to unit test with fakes/mocks.
    """

    def __init__(
        self,
        base_url: str = "",
        timeout: float = 10.0,
        retry_config: Optional[RetryConfig] = None,
        session: Optional[Session] = None,
        rate_limiter: Optional[RateLimiterProtocol] = None,
        logger: Optional[logging.Logger] = None,
        default_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retry_config = retry_config or RetryConfig()
        self.session = session or requests.Session()
        self.rate_limiter = rate_limiter
        self.logger = logger or logging.getLogger(__name__)

        if default_headers:
            self.session.headers.update(default_headers)

    # -- public API ---------------------------------------------------

    def get(self, path: str, *, params: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Any:
        return self.request_json("GET", path, params=params, **kwargs)

    def post(self, path: str, *, json: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Any:
        return self.request_json("POST", path, json=json, **kwargs)

    def request_json(self, method: str, path: str, **kwargs: Any) -> Any:
        """Perform a request and decode the response body as JSON."""
        response = self.request(method, path, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise InvalidResponseError(
                f"Response from {response.url} was not valid JSON"
            ) from exc

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        json: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> Response:
        """
        Perform an HTTP request with retry + exponential backoff.

        Raises
        ------
        RequestTimeoutError, ConnectionFailedError, RateLimitError,
        APIStatusError, RetriesExhaustedError, HTTPClientError
        """
        url = self._full_url(path)
        cfg = self.retry_config
        last_exc: Optional[Exception] = None

        attempt = 0
        while attempt <= cfg.total:
            if self.rate_limiter is not None:
                self.rate_limiter.acquire()

            self.logger.debug(
                "HTTP %s %s (attempt %d/%d) params=%s",
                method, url, attempt + 1, cfg.total + 1, params,
            )

            try:
                response = self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    json=json,
                    headers=headers,
                    timeout=timeout if timeout is not None else self.timeout,
                )
            except requests.exceptions.Timeout as exc:
                last_exc = exc
                self.logger.warning("Timeout on %s %s (attempt %d): %s", method, url, attempt, exc)
                if not self._should_retry(attempt):
                    raise RequestTimeoutError(f"Timeout calling {url}") from exc
                self._sleep_backoff(attempt)
                attempt += 1
                continue
            except requests.exceptions.ConnectionError as exc:
                last_exc = exc
                self.logger.warning("Connection error on %s %s (attempt %d): %s", method, url, attempt, exc)
                if not self._should_retry(attempt):
                    raise ConnectionFailedError(f"Connection failed calling {url}") from exc
                self._sleep_backoff(attempt)
                attempt += 1
                continue
            except requests.exceptions.RequestException as exc:
                self.logger.error("Unrecoverable request exception on %s %s: %s", method, url, exc)
                raise HTTPClientError(f"Request failed calling {url}: {exc}") from exc

            if response.status_code == 429:
                retry_after = self._parse_retry_after(response)
                self.logger.warning(
                    "Rate limited (429) on %s %s (attempt %d), retry_after=%s",
                    method, url, attempt, retry_after,
                )
                if not self._should_retry(attempt):
                    raise RateLimitError(
                        f"Rate limited calling {url}", retry_after=retry_after, response=response
                    )
                self._sleep_backoff(attempt, override=retry_after)
                attempt += 1
                continue

            if response.status_code in cfg.retry_on_status:
                self.logger.warning(
                    "Retryable status %d on %s %s (attempt %d)",
                    response.status_code, method, url, attempt,
                )
                if not self._should_retry(attempt):
                    raise APIStatusError(
                        f"Status {response.status_code} calling {url}",
                        status_code=response.status_code,
                        response=response,
                    )
                self._sleep_backoff(attempt)
                attempt += 1
                continue

            if not response.ok:
                raise APIStatusError(
                    f"Status {response.status_code} calling {url}",
                    status_code=response.status_code,
                    response=response,
                )

            return response

        raise RetriesExhaustedError(
            f"All {cfg.total + 1} attempts exhausted for {url}"
        ) from last_exc

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "HTTPClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    # -- internals ------------------------------------------------------

    def _full_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not self.base_url:
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def _should_retry(self, attempt: int) -> bool:
        return attempt < self.retry_config.total

    def _sleep_backoff(self, attempt: int, override: Optional[float] = None) -> None:
        delay = override if override is not None else self.retry_config.backoff_seconds(attempt)
        if delay > 0:
            self.logger.debug("Sleeping %.3fs before retry (attempt %d)", delay, attempt + 1)
            time.sleep(delay)

    @staticmethod
    def _parse_retry_after(response: Response) -> Optional[float]:
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            return float(value)
        except ValueError:
            return None
