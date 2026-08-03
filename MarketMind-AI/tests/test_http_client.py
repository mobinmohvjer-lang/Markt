"""
tests/test_http_client.py

Unit tests for api/http_client.py.

All network calls are mocked -- no real HTTP requests are made.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import requests

from api.exceptions import (
    APIStatusError,
    ConnectionFailedError,
    RateLimitError,
    RequestTimeoutError,
    RetriesExhaustedError,
)
from api.http_client import HTTPClient, RateLimiter, RetryConfig


def make_response(status_code=200, json_data=None, headers=None):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.ok = 200 <= status_code < 300
    resp.headers = headers or {}
    resp.url = "https://example.test/mock"
    resp.json.return_value = json_data if json_data is not None else {}
    return resp


class TestHTTPClientSuccess(unittest.TestCase):
    def test_get_returns_json_on_success(self):
        session = MagicMock()
        session.request.return_value = make_response(200, {"ok": True})
        client = HTTPClient(base_url="https://example.test", session=session, retry_config=RetryConfig(total=0))

        result = client.get("/foo")

        self.assertEqual(result, {"ok": True})
        session.request.assert_called_once()
        _, kwargs = session.request.call_args
        self.assertEqual(kwargs["method"], "GET")
        self.assertEqual(kwargs["url"], "https://example.test/foo")

    def test_full_url_passthrough(self):
        session = MagicMock()
        session.request.return_value = make_response(200, {"ok": True})
        client = HTTPClient(base_url="https://example.test", session=session)

        client.get("https://other.test/bar")

        _, kwargs = session.request.call_args
        self.assertEqual(kwargs["url"], "https://other.test/bar")


class TestHTTPClientRetryBehavior(unittest.TestCase):
    @patch("api.http_client.time.sleep", return_value=None)
    def test_retries_on_500_then_succeeds(self, _sleep):
        session = MagicMock()
        session.request.side_effect = [
            make_response(500),
            make_response(500),
            make_response(200, {"ok": True}),
        ]
        client = HTTPClient(
            base_url="https://example.test",
            session=session,
            retry_config=RetryConfig(total=3, backoff_factor=0.01),
        )

        result = client.get("/foo")

        self.assertEqual(result, {"ok": True})
        self.assertEqual(session.request.call_count, 3)

    @patch("api.http_client.time.sleep", return_value=None)
    def test_raises_retries_exhausted_after_repeated_500(self, _sleep):
        session = MagicMock()
        session.request.return_value = make_response(500)
        client = HTTPClient(
            base_url="https://example.test",
            session=session,
            retry_config=RetryConfig(total=2, backoff_factor=0.01),
        )

        with self.assertRaises(APIStatusError):
            client.get("/foo")
        # attempt 0,1,2 -> 3 calls, last one raises APIStatusError not RetriesExhausted
        self.assertEqual(session.request.call_count, 3)

    @patch("api.http_client.time.sleep", return_value=None)
    def test_raises_api_status_error_on_non_retryable_status(self, _sleep):
        session = MagicMock()
        session.request.return_value = make_response(404)
        client = HTTPClient(base_url="https://example.test", session=session, retry_config=RetryConfig(total=3))

        with self.assertRaises(APIStatusError) as ctx:
            client.get("/missing")

        self.assertEqual(ctx.exception.status_code, 404)
        session.request.assert_called_once()

    @patch("api.http_client.time.sleep", return_value=None)
    def test_rate_limit_retries_then_raises(self, _sleep):
        session = MagicMock()
        session.request.return_value = make_response(429, headers={"Retry-After": "1"})
        client = HTTPClient(
            base_url="https://example.test",
            session=session,
            retry_config=RetryConfig(total=1, backoff_factor=0.01),
        )

        with self.assertRaises(RateLimitError) as ctx:
            client.get("/foo")

        self.assertEqual(ctx.exception.retry_after, 1.0)
        self.assertEqual(session.request.call_count, 2)

    @patch("api.http_client.time.sleep", return_value=None)
    def test_timeout_raises_request_timeout_error(self, _sleep):
        session = MagicMock()
        session.request.side_effect = requests.exceptions.Timeout("timed out")
        client = HTTPClient(base_url="https://example.test", session=session, retry_config=RetryConfig(total=1, backoff_factor=0.01))

        with self.assertRaises(RequestTimeoutError):
            client.get("/foo")
        self.assertEqual(session.request.call_count, 2)

    @patch("api.http_client.time.sleep", return_value=None)
    def test_connection_error_raises_connection_failed_error(self, _sleep):
        session = MagicMock()
        session.request.side_effect = requests.exceptions.ConnectionError("refused")
        client = HTTPClient(base_url="https://example.test", session=session, retry_config=RetryConfig(total=0))

        with self.assertRaises(ConnectionFailedError):
            client.get("/foo")
        self.assertEqual(session.request.call_count, 1)


class TestRateLimiterHook(unittest.TestCase):
    def test_rate_limiter_acquire_is_called_per_request(self):
        session = MagicMock()
        session.request.return_value = make_response(200, {"ok": True})
        limiter = MagicMock(spec=RateLimiter)

        client = HTTPClient(base_url="https://example.test", session=session, rate_limiter=limiter)
        client.get("/a")
        client.get("/b")

        self.assertEqual(limiter.acquire.call_count, 2)

    @patch("api.http_client.time.monotonic")
    @patch("api.http_client.time.sleep", return_value=None)
    def test_real_rate_limiter_enforces_min_interval(self, mock_sleep, mock_monotonic):
        # Each acquire() reads time.monotonic() twice: once to compute the
        # wait, once to record _last_call after sleeping.
        mock_monotonic.side_effect = [0.0, 0.0, 0.05, 0.05]
        limiter = RateLimiter(min_interval=0.1)

        limiter.acquire()  # now=0.0, last_call=0.0 -> wait=0.1, sleeps 0.1
        limiter.acquire()  # now=0.05, last_call=0.0 -> wait=0.05, sleeps 0.05

        self.assertEqual(mock_sleep.call_count, 2)
        first_wait, second_wait = (c.args[0] for c in mock_sleep.call_args_list)
        self.assertAlmostEqual(first_wait, 0.1, places=3)
        self.assertAlmostEqual(second_wait, 0.05, places=3)


class TestBackoffCalculation(unittest.TestCase):
    def test_backoff_seconds_grows_exponentially_and_caps(self):
        cfg = RetryConfig(backoff_factor=1.0, max_backoff=5.0, jitter=False)
        self.assertEqual(cfg.backoff_seconds(0), 1.0)
        self.assertEqual(cfg.backoff_seconds(1), 2.0)
        self.assertEqual(cfg.backoff_seconds(2), 4.0)
        self.assertEqual(cfg.backoff_seconds(3), 5.0)  # capped


if __name__ == "__main__":
    unittest.main()
