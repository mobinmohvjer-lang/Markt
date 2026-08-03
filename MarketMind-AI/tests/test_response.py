"""
test_response.py
-------------------
Purpose:
    Unit tests for **API Layer Part 3 (Response standardization
    only)**: `api.response.success_envelope`/`error_envelope`/
    `is_envelope`, plus `api.base.BaseAPIHandler`'s two new
    convenience methods, `_build_success_result`/`_build_error_result`,
    that wrap them into an `APIResult`.

    Deliberately does NOT re-test `BaseAPIHandler`'s original
    `_build_result`/`validate_context`/abstract `handle()` contract --
    those are already covered by `tests/test_api_foundation.py`
    (API Layer Part 1), unchanged and unaffected by this milestone.

Uses the standard-library ``unittest`` framework, matching every other
test suite in this repository.

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest

from api.base import BaseAPIHandler
from api.context import APIRequestContext
from api.exceptions import APIValidationError
from api.response import error_envelope, is_envelope, success_envelope
from api.result import APIResult


# ----------------------------------------------------------------------
# success_envelope / error_envelope / is_envelope
# ----------------------------------------------------------------------
class TestSuccessEnvelope(unittest.TestCase):
    def test_default_shape(self):
        envelope = success_envelope(status_code=200, data={"a": 1})
        self.assertEqual(
            envelope,
            {"success": True, "status_code": 200, "data": {"a": 1}, "error": None},
        )

    def test_data_defaults_to_none(self):
        envelope = success_envelope(status_code=204)
        self.assertIsNone(envelope["data"])

    def test_success_true_for_every_2xx_status(self):
        for status in (200, 201, 204, 250, 299):
            self.assertTrue(success_envelope(status_code=status)["success"])

    def test_success_false_for_a_non_2xx_status(self):
        # success_envelope does not itself forbid a non-2xx status --
        # it only derives `success` honestly from whatever is passed.
        self.assertFalse(success_envelope(status_code=404)["success"])

    def test_rejects_invalid_status_code(self):
        with self.assertRaises(APIValidationError):
            success_envelope(status_code=999)

    def test_data_is_passed_through_untouched(self):
        payload = {"direction": "buy", "nested": {"x": 1}}
        envelope = success_envelope(status_code=200, data=payload)
        self.assertIs(envelope["data"], payload)


class TestErrorEnvelope(unittest.TestCase):
    def test_default_shape(self):
        envelope = error_envelope(status_code=404, error_type="NotFound", message="no data")
        self.assertEqual(
            envelope,
            {
                "success": False,
                "status_code": 404,
                "data": None,
                "error": {"type": "NotFound", "message": "no data"},
            },
        )

    def test_success_is_always_false(self):
        envelope = error_envelope(status_code=200, error_type="X", message="y")
        self.assertFalse(envelope["success"])

    def test_data_is_always_none(self):
        envelope = error_envelope(status_code=500, error_type="X", message="y")
        self.assertIsNone(envelope["data"])

    def test_rejects_invalid_status_code(self):
        with self.assertRaises(APIValidationError):
            error_envelope(status_code=999, error_type="X", message="y")

    def test_rejects_empty_error_type(self):
        with self.assertRaises(APIValidationError):
            error_envelope(status_code=400, error_type="  ", message="y")

    def test_rejects_empty_message(self):
        with self.assertRaises(APIValidationError):
            error_envelope(status_code=400, error_type="X", message="")


class TestIsEnvelope(unittest.TestCase):
    def test_true_for_a_success_envelope(self):
        self.assertTrue(is_envelope(success_envelope(status_code=200)))

    def test_true_for_an_error_envelope(self):
        self.assertTrue(is_envelope(error_envelope(status_code=400, error_type="X", message="y")))

    def test_false_for_a_plain_dict(self):
        self.assertFalse(is_envelope({"error": "nope"}))

    def test_false_for_a_dict_missing_a_key(self):
        envelope = success_envelope(status_code=200)
        del envelope["error"]
        self.assertFalse(is_envelope(envelope))

    def test_false_for_a_dict_with_an_extra_key(self):
        envelope = success_envelope(status_code=200)
        envelope["extra"] = True
        self.assertFalse(is_envelope(envelope))

    def test_false_for_a_non_dict(self):
        self.assertFalse(is_envelope("not-a-dict"))
        self.assertFalse(is_envelope(None))
        self.assertFalse(is_envelope(["success"]))


# ----------------------------------------------------------------------
# BaseAPIHandler._build_success_result / _build_error_result
# ----------------------------------------------------------------------
class _FakeEnvelopeHandler(BaseAPIHandler):
    """Minimal concrete handler exercising the new Part 3 helpers only."""

    def handle(self, context: APIRequestContext) -> APIResult:  # pragma: no cover - unused
        raise NotImplementedError


class TestBuildSuccessResult(unittest.TestCase):
    def setUp(self):
        self.handler = _FakeEnvelopeHandler()

    def test_returns_an_api_result(self):
        result = self.handler._build_success_result(data={"x": 1})
        self.assertIsInstance(result, APIResult)

    def test_defaults_status_code_to_200(self):
        result = self.handler._build_success_result(data={"x": 1})
        self.assertEqual(result.status_code, 200)

    def test_body_is_a_standardized_success_envelope(self):
        result = self.handler._build_success_result(status_code=201, data={"x": 1})
        self.assertTrue(is_envelope(result.body))
        self.assertTrue(result.body["success"])
        self.assertEqual(result.body["status_code"], 201)
        self.assertEqual(result.body["data"], {"x": 1})
        self.assertIsNone(result.body["error"])

    def test_metadata_and_headers_are_forwarded(self):
        result = self.handler._build_success_result(
            data=None, headers={"X-Test": "1"}, metadata={"symbol": "BTCUSDT"}
        )
        self.assertEqual(result.headers, {"X-Test": "1"})
        self.assertEqual(result.metadata, {"symbol": "BTCUSDT"})

    def test_rejects_a_non_2xx_status_code(self):
        with self.assertRaises(ValueError):
            self.handler._build_success_result(status_code=404, data=None)


class TestBuildErrorResult(unittest.TestCase):
    def setUp(self):
        self.handler = _FakeEnvelopeHandler()

    def test_returns_an_api_result(self):
        result = self.handler._build_error_result(
            status_code=400, error_type="ValidationError", message="bad input"
        )
        self.assertIsInstance(result, APIResult)

    def test_body_is_a_standardized_error_envelope(self):
        result = self.handler._build_error_result(
            status_code=404, error_type="NotFound", message="missing"
        )
        self.assertTrue(is_envelope(result.body))
        self.assertFalse(result.body["success"])
        self.assertEqual(result.body["status_code"], 404)
        self.assertIsNone(result.body["data"])
        self.assertEqual(result.body["error"], {"type": "NotFound", "message": "missing"})

    def test_status_code_matches_the_enclosing_api_result(self):
        result = self.handler._build_error_result(
            status_code=500, error_type="InternalError", message="oops"
        )
        self.assertEqual(result.status_code, 500)
        self.assertEqual(result.body["status_code"], 500)

    def test_metadata_and_headers_are_forwarded(self):
        result = self.handler._build_error_result(
            status_code=400,
            error_type="X",
            message="y",
            headers={"X-Test": "1"},
            metadata={"stage": "validation"},
        )
        self.assertEqual(result.headers, {"X-Test": "1"})
        self.assertEqual(result.metadata, {"stage": "validation"})


class TestBuildResultStillWorksUnchanged(unittest.TestCase):
    """Confirms Part 3 did not touch `_build_result`'s original, raw behavior."""

    def test_build_result_body_is_not_wrapped(self):
        handler = _FakeEnvelopeHandler()
        result = handler._build_result(status_code=200, body={"raw": True})
        self.assertEqual(result.body, {"raw": True})
        self.assertFalse(is_envelope(result.body))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
