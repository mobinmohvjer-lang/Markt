"""
test_api_foundation.py
-------------------------
Purpose:
    Unit tests for the **inbound REST API foundation** (API Layer
    Part 1): `APIRequestContext`, `APIResult`, `BaseAPIHandler`, and
    the `api.exceptions.InboundAPIError` hierarchy / `api.utils`
    helpers that support them.

    Deliberately does NOT test `api`'s existing outbound-transport
    role (`HTTPClient`, `RateLimiter`, `RetryConfig`, `providers/`) --
    that is already covered by `tests/test_http_client.py`,
    `tests/test_binance_provider.py`, `tests/test_coingecko_provider.py`,
    and `tests/test_news_provider.py`, none of which this file touches.

Uses the standard-library ``unittest`` framework, matching the
`services`/`execution`/`signals`/... test suites (no external
test-runner dependency).

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest

from api import (
    APIHandlerConfigurationError,
    APIRequestContext,
    APIResult,
    APIValidationError,
    BaseAPIHandler,
    InboundAPIError,
    InsufficientAPIDataError,
    InvalidRequestContextError,
)
from api.exceptions import APIStatusError, HTTPClientError
from api.utils import (
    VALID_HTTP_METHODS,
    merge_metadata,
    validate_dict,
    validate_http_method,
    validate_non_empty_str,
    validate_path,
    validate_status_code,
)


def make_context(
    *,
    method: str = "GET",
    path: str = "/signals",
    query_params=None,
    headers=None,
    body=None,
    metadata=None,
) -> APIRequestContext:
    return APIRequestContext(
        method=method,
        path=path,
        query_params=query_params if query_params is not None else {},
        headers=headers if headers is not None else {},
        body=body,
        metadata=metadata if metadata is not None else {},
    )


# ----------------------------------------------------------------------
# APIRequestContext
# ----------------------------------------------------------------------
class TestAPIRequestContext(unittest.TestCase):
    def test_instantiates_with_required_fields_only(self):
        context = APIRequestContext(method="GET", path="/health")
        self.assertEqual(context.method, "GET")
        self.assertEqual(context.path, "/health")
        self.assertEqual(context.query_params, {})
        self.assertEqual(context.headers, {})
        self.assertIsNone(context.body)
        self.assertEqual(context.metadata, {})

    def test_normalizes_method_case(self):
        context = APIRequestContext(method="get", path="/health")
        self.assertEqual(context.method, "GET")

    def test_accepts_full_fields(self):
        context = make_context(
            method="post",
            path="/signals",
            query_params={"symbol": "BTCUSDT"},
            headers={"Content-Type": "application/json"},
            body={"timeframe": "1h"},
            metadata={"request_id": "req-1"},
        )
        self.assertEqual(context.method, "POST")
        self.assertEqual(context.query_params, {"symbol": "BTCUSDT"})
        self.assertEqual(context.headers, {"Content-Type": "application/json"})
        self.assertEqual(context.body, {"timeframe": "1h"})
        self.assertEqual(context.metadata, {"request_id": "req-1"})

    def test_is_frozen(self):
        context = make_context()
        with self.assertRaises(Exception):
            context.method = "POST"  # type: ignore[misc]

    def test_rejects_blank_path(self):
        with self.assertRaises(InvalidRequestContextError):
            APIRequestContext(method="GET", path="   ")

    def test_rejects_path_without_leading_slash(self):
        with self.assertRaises(InvalidRequestContextError):
            APIRequestContext(method="GET", path="signals")

    def test_rejects_unsupported_method(self):
        with self.assertRaises(InvalidRequestContextError):
            APIRequestContext(method="TRACE", path="/signals")

    def test_rejects_non_string_method(self):
        with self.assertRaises(InvalidRequestContextError):
            APIRequestContext(method=123, path="/signals")  # type: ignore[arg-type]

    def test_rejects_non_dict_query_params(self):
        with self.assertRaises(InvalidRequestContextError):
            APIRequestContext(method="GET", path="/signals", query_params="not-a-dict")  # type: ignore[arg-type]

    def test_rejects_non_dict_headers(self):
        with self.assertRaises(InvalidRequestContextError):
            APIRequestContext(method="GET", path="/signals", headers="not-a-dict")  # type: ignore[arg-type]

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(InvalidRequestContextError):
            APIRequestContext(method="GET", path="/signals", metadata="not-a-dict")  # type: ignore[arg-type]

    def test_has_body_true_when_present(self):
        context = make_context(body={"a": 1})
        self.assertTrue(context.has_body())

    def test_has_body_false_when_absent(self):
        context = make_context()
        self.assertFalse(context.has_body())

    def test_has_query_params_true_when_present(self):
        context = make_context(query_params={"symbol": "BTCUSDT"})
        self.assertTrue(context.has_query_params())

    def test_has_query_params_false_when_absent(self):
        context = make_context()
        self.assertFalse(context.has_query_params())

    def test_get_header_case_insensitive(self):
        context = make_context(headers={"Content-Type": "application/json"})
        self.assertEqual(context.get_header("content-type"), "application/json")
        self.assertEqual(context.get_header("CONTENT-TYPE"), "application/json")

    def test_get_header_returns_default_when_absent(self):
        context = make_context()
        self.assertIsNone(context.get_header("X-Missing"))
        self.assertEqual(context.get_header("X-Missing", default="fallback"), "fallback")

    def test_body_accepts_non_dict_values(self):
        # Deliberately unvalidated beyond presence -- schema validation
        # is future work (a `schemas/` module), not this foundation's.
        context = make_context(body=[1, 2, 3])
        self.assertEqual(context.body, [1, 2, 3])
        context2 = make_context(body="raw text")
        self.assertEqual(context2.body, "raw text")


# ----------------------------------------------------------------------
# APIResult
# ----------------------------------------------------------------------
class TestAPIResult(unittest.TestCase):
    def test_instantiates_with_required_fields(self):
        result = APIResult(status_code=200)
        self.assertEqual(result.status_code, 200)
        self.assertIsNone(result.body)
        self.assertEqual(result.headers, {})
        self.assertEqual(result.metadata, {})

    def test_only_has_the_four_documented_fields(self):
        result = APIResult(status_code=200)
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        self.assertEqual(field_names, {"status_code", "body", "headers", "metadata"})

    def test_is_frozen(self):
        result = APIResult(status_code=200)
        with self.assertRaises(Exception):
            result.status_code = 500  # type: ignore[misc]

    def test_rejects_non_int_status_code(self):
        with self.assertRaises(APIValidationError):
            APIResult(status_code="200")  # type: ignore[arg-type]

    def test_rejects_bool_status_code(self):
        with self.assertRaises(APIValidationError):
            APIResult(status_code=True)  # type: ignore[arg-type]

    def test_rejects_out_of_range_status_code(self):
        with self.assertRaises(APIValidationError):
            APIResult(status_code=999)
        with self.assertRaises(APIValidationError):
            APIResult(status_code=99)

    def test_rejects_non_dict_headers(self):
        with self.assertRaises(APIValidationError):
            APIResult(status_code=200, headers="not-a-dict")  # type: ignore[arg-type]

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(APIValidationError):
            APIResult(status_code=200, metadata="not-a-dict")  # type: ignore[arg-type]

    def test_is_success_true_for_2xx(self):
        self.assertTrue(APIResult(status_code=200).is_success())
        self.assertTrue(APIResult(status_code=201).is_success())
        self.assertTrue(APIResult(status_code=299).is_success())

    def test_is_success_false_outside_2xx(self):
        self.assertFalse(APIResult(status_code=404).is_success())
        self.assertFalse(APIResult(status_code=500).is_success())
        self.assertFalse(APIResult(status_code=199).is_success())

    def test_with_metadata_returns_new_instance(self):
        original = APIResult(status_code=200, metadata={"a": 1})
        updated = original.with_metadata(b=2)
        self.assertIsNot(updated, original)
        self.assertEqual(original.metadata, {"a": 1})
        self.assertEqual(updated.metadata, {"a": 1, "b": 2})

    def test_with_metadata_overrides_on_conflict(self):
        original = APIResult(status_code=200, metadata={"a": 1})
        updated = original.with_metadata(a=99)
        self.assertEqual(updated.metadata, {"a": 99})

    def test_no_wire_format_or_domain_fields(self):
        # Defensive: APIResult must expose exactly the four documented
        # fields -- no wire-format/serialization fields and no
        # trading-domain fields have been introduced by this part.
        result = APIResult(status_code=200)
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        for forbidden in (
            "handler_name",
            "order_id",
            "signal",
            "reason_phrase",
            "raw_response",
        ):
            self.assertNotIn(forbidden, field_names)


# ----------------------------------------------------------------------
# api.utils
# ----------------------------------------------------------------------
class TestUtils(unittest.TestCase):
    def test_validate_non_empty_str_accepts_valid_string(self):
        self.assertEqual(validate_non_empty_str("GET", name="method"), "GET")

    def test_validate_non_empty_str_rejects_blank(self):
        with self.assertRaises(APIValidationError):
            validate_non_empty_str("   ", name="method")

    def test_validate_non_empty_str_rejects_non_string(self):
        with self.assertRaises(APIValidationError):
            validate_non_empty_str(123, name="method")  # type: ignore[arg-type]

    def test_validate_http_method_normalizes_case(self):
        self.assertEqual(validate_http_method("post"), "POST")
        self.assertEqual(validate_http_method("Get"), "GET")

    def test_validate_http_method_accepts_every_documented_method(self):
        for method in VALID_HTTP_METHODS:
            self.assertEqual(validate_http_method(method.lower()), method)

    def test_validate_http_method_rejects_unsupported(self):
        with self.assertRaises(APIValidationError):
            validate_http_method("CONNECT")

    def test_validate_path_accepts_leading_slash(self):
        self.assertEqual(validate_path("/signals"), "/signals")

    def test_validate_path_rejects_missing_leading_slash(self):
        with self.assertRaises(APIValidationError):
            validate_path("signals")

    def test_validate_status_code_accepts_valid_int(self):
        self.assertEqual(validate_status_code(200), 200)
        self.assertEqual(validate_status_code(100), 100)
        self.assertEqual(validate_status_code(599), 599)

    def test_validate_status_code_rejects_out_of_range(self):
        with self.assertRaises(APIValidationError):
            validate_status_code(99)
        with self.assertRaises(APIValidationError):
            validate_status_code(600)

    def test_validate_status_code_rejects_bool(self):
        with self.assertRaises(APIValidationError):
            validate_status_code(True)

    def test_validate_status_code_rejects_non_int(self):
        with self.assertRaises(APIValidationError):
            validate_status_code("200")  # type: ignore[arg-type]

    def test_validate_dict_accepts_dict(self):
        self.assertEqual(validate_dict({"a": 1}, name="headers"), {"a": 1})

    def test_validate_dict_rejects_non_dict(self):
        with self.assertRaises(APIValidationError):
            validate_dict("not-a-dict", name="headers")  # type: ignore[arg-type]

    def test_merge_metadata_combines_sources(self):
        self.assertEqual(merge_metadata({"a": 1}, {"b": 2}), {"a": 1, "b": 2})

    def test_merge_metadata_later_source_wins(self):
        self.assertEqual(merge_metadata({"a": 1}, {"a": 2}), {"a": 2})

    def test_merge_metadata_skips_none(self):
        self.assertEqual(merge_metadata(None, {"a": 1}, None), {"a": 1})

    def test_merge_metadata_no_sources_returns_empty_dict(self):
        self.assertEqual(merge_metadata(), {})


# ----------------------------------------------------------------------
# api.exceptions -- InboundAPIError hierarchy (kept unrelated to the
# existing outbound HTTPClientError hierarchy)
# ----------------------------------------------------------------------
class TestExceptionHierarchy(unittest.TestCase):
    def test_api_validation_error_is_inbound_api_error(self):
        self.assertTrue(issubclass(APIValidationError, InboundAPIError))

    def test_invalid_request_context_error_is_api_validation_error(self):
        self.assertTrue(issubclass(InvalidRequestContextError, APIValidationError))

    def test_insufficient_api_data_error_is_inbound_api_error(self):
        self.assertTrue(issubclass(InsufficientAPIDataError, InboundAPIError))
        self.assertFalse(issubclass(InsufficientAPIDataError, APIValidationError))

    def test_api_handler_configuration_error_is_inbound_api_error(self):
        self.assertTrue(issubclass(APIHandlerConfigurationError, InboundAPIError))

    def test_inbound_api_error_is_exception(self):
        self.assertTrue(issubclass(InboundAPIError, Exception))

    def test_inbound_hierarchy_is_unrelated_to_outbound_hierarchy(self):
        # The two exception hierarchies in api/exceptions.py must never
        # be confused with one another.
        self.assertFalse(issubclass(InboundAPIError, HTTPClientError))
        self.assertFalse(issubclass(HTTPClientError, InboundAPIError))
        self.assertFalse(issubclass(APIStatusError, InboundAPIError))
        self.assertFalse(issubclass(APIValidationError, HTTPClientError))


# ----------------------------------------------------------------------
# BaseAPIHandler (via a minimal concrete fake, mirroring
# test_execution.py's/test_services.py's Fake*/Base* pattern)
# ----------------------------------------------------------------------
class FakeAPIHandler(BaseAPIHandler):
    """Minimal concrete `BaseAPIHandler` used only to exercise the base class."""

    def __init__(self, *, name=None, succeed: bool = True):
        super().__init__(name=name)
        self._succeed = succeed

    def handle(self, context: APIRequestContext) -> APIResult:
        self.validate_context(context)
        if not context.has_query_params():
            raise InsufficientAPIDataError("no query parameters to act on")
        return self._build_result(
            status_code=200 if self._succeed else 400,
            body={"path": context.path},
            metadata={"handled_by": self.name},
        )


class TestBaseAPIHandler(unittest.TestCase):
    def test_defaults_name_to_class_name(self):
        handler = FakeAPIHandler()
        self.assertEqual(handler.name, "FakeAPIHandler")

    def test_accepts_custom_name(self):
        handler = FakeAPIHandler(name="CustomHandler")
        self.assertEqual(handler.name, "CustomHandler")

    def test_cannot_instantiate_abstract_base_directly(self):
        with self.assertRaises(TypeError):
            BaseAPIHandler()  # type: ignore[abstract]

    def test_validate_context_accepts_valid_context(self):
        handler = FakeAPIHandler()
        context = make_context(query_params={"symbol": "BTCUSDT"})
        self.assertIs(handler.validate_context(context), context)

    def test_validate_context_rejects_non_context(self):
        handler = FakeAPIHandler()
        with self.assertRaises(InvalidRequestContextError):
            handler.validate_context("not-a-context")  # type: ignore[arg-type]

    def test_handle_returns_api_result(self):
        handler = FakeAPIHandler(succeed=True)
        context = make_context(query_params={"symbol": "BTCUSDT"})
        result = handler.handle(context)
        self.assertIsInstance(result, APIResult)
        self.assertTrue(result.is_success())
        self.assertEqual(result.metadata, {"handled_by": "FakeAPIHandler"})

    def test_handle_raises_insufficient_data_when_no_query_params(self):
        handler = FakeAPIHandler()
        context = make_context()
        with self.assertRaises(InsufficientAPIDataError):
            handler.handle(context)

    def test_build_result_defaults_headers_and_metadata_to_empty_dict(self):
        handler = FakeAPIHandler()
        result = handler._build_result(status_code=204)
        self.assertEqual(result.headers, {})
        self.assertEqual(result.metadata, {})

    def test_repr_includes_class_and_name(self):
        handler = FakeAPIHandler(name="SignalsHandler")
        self.assertEqual(repr(handler), "FakeAPIHandler(name='SignalsHandler')")


# ----------------------------------------------------------------------
# Integration: a realistic APIRequestContext carried end-to-end through
# a real BaseAPIHandler subclass.
# ----------------------------------------------------------------------
class TestIntegration(unittest.TestCase):
    def test_end_to_end_call_with_query_params(self):
        handler = FakeAPIHandler(succeed=True)
        context = APIRequestContext(
            method="GET",
            path="/signals",
            query_params={"symbol": "BTCUSDT", "timeframe": "1h"},
            metadata={"request_id": "req-42"},
        )
        result = handler.handle(context)

        self.assertTrue(context.has_query_params())
        self.assertTrue(result.is_success())
        self.assertEqual(result.body, {"path": "/signals"})

    def test_unsuccessful_call_still_just_data(self):
        # APIRequestContext is a pure data container: it does not
        # itself interpret whether a call will succeed or fail -- that
        # remains a concrete BaseAPIHandler's job (a future API Layer
        # part), not this foundation's.
        context = APIRequestContext(
            method="GET", path="/signals", query_params={"symbol": "BTCUSDT"}
        )
        handler = FakeAPIHandler(succeed=False)
        result = handler.handle(context)
        self.assertFalse(result.is_success())
        self.assertEqual(result.status_code, 400)

    def test_no_broker_ai_or_auth_fields_end_to_end(self):
        handler = FakeAPIHandler()
        context = make_context(query_params={"symbol": "BTCUSDT"})
        result = handler.handle(context)
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        for forbidden in ("api_key", "token", "broker", "exchange", "order_id"):
            self.assertNotIn(forbidden, field_names)


if __name__ == "__main__":
    unittest.main()
