"""
test_signal_handler.py
-------------------------
Purpose:
    Unit tests for `SignalHandler` (`api/routes/signals.py`).

    Originally covered API Layer Part 2 (Signal endpoint only, plain
    per-handler body shapes); now updated for **API Layer Part 3
    (Response standardization only)**: every `APIResult.body`
    `SignalHandler` returns -- success, validation error, pipeline
    error, or internal error -- follows the standardized envelope
    (`api.response`, `{"success", "status_code", "data", "error"}`),
    and `handle()` no longer raises `InvalidRequestContextError`/
    `InsufficientAPIDataError` -- both are now caught and reported as
    a standardized `400` `APIResult` instead. Construction/dependency
    injection and end-to-end pipeline wiring are otherwise unchanged
    from Part 2 and still covered here.

Uses the standard-library ``unittest`` framework and the shared
`FakeBinanceClient`/`make_fake_client` from `tests/helpers.py` (no real
network access), matching every other test suite in this repository.

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import os
import tempfile
import unittest

from tests.helpers import make_fake_client

from analysis.base import BaseAnalyzer
from analysis.exceptions import InsufficientDataError as AnalysisInsufficientDataError
from analysis.result import AnalysisResult

from app.main import MainApplication

from data.engine import DataEngine

from signals.base import BaseSignalGenerator
from signals.exceptions import InsufficientSignalDataError

from api.context import APIRequestContext
from api.exceptions import APIHandlerConfigurationError
from api.response import is_envelope
from api.result import APIResult
from api.routes.signals import SignalHandler


class _AlwaysFailingAnalyzer(BaseAnalyzer):
    """Test double: always raises InsufficientDataError (Analysis stage)."""

    def analyze(self, context) -> AnalysisResult:
        raise AnalysisInsufficientDataError("no data, by design")


class _AlwaysFailingSignalGenerator(BaseSignalGenerator):
    """Test double: always raises InsufficientSignalDataError (Signals stage)."""

    def generate(self, context) -> AnalysisResult:  # pragma: no cover - signature only
        raise InsufficientSignalDataError("no signal, by design")


class _ExplodingSignalGenerator(BaseSignalGenerator):
    """Test double: raises a plain, undocumented exception -- the
    "internal error" catch-all path, not one of `signals.exceptions.
    SignalError`'s documented subclasses."""

    def generate(self, context) -> AnalysisResult:  # pragma: no cover - signature only
        raise RuntimeError("totally unexpected, by design")


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
        query_params=query_params or {},
        headers=headers or {},
        body=body,
        metadata=metadata or {},
    )


class SignalHandlerTestCase(unittest.TestCase):
    """Shared setUp/tearDown: a MainApplication backed by a fake, preloaded DataEngine."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.remove(self.db_path)
        self.fake_client = make_fake_client(num_candles=200, timeframe="1h")
        self.data_engine = DataEngine(client=self.fake_client, db_path=self.db_path)
        self.data_engine.download_history(
            symbol="BTCUSDT",
            timeframe="1h",
            start_time=self.fake_client.series_start,
            batch_limit=200,
        )
        self.app = MainApplication(data_engine=self.data_engine)

    def tearDown(self):
        self.data_engine.close()
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                os.remove(path)


class TestSignalHandlerConstruction(SignalHandlerTestCase):
    def test_injected_app_is_stored_as_is(self):
        handler = SignalHandler(self.app)
        self.assertIs(handler.app, self.app)

    def test_default_app_is_constructed_when_omitted(self):
        handler = SignalHandler()
        self.assertIsInstance(handler.app, MainApplication)
        handler.app.data_engine.close()

    def test_name_defaults_to_class_name(self):
        handler = SignalHandler(self.app)
        self.assertEqual(handler.name, "SignalHandler")

    def test_custom_name_is_stored(self):
        handler = SignalHandler(self.app, name="CustomSignalHandler")
        self.assertEqual(handler.name, "CustomSignalHandler")

    def test_invalid_app_is_rejected(self):
        with self.assertRaises(APIHandlerConfigurationError):
            SignalHandler(app=object())

    def test_none_app_uses_default(self):
        handler = SignalHandler(app=None)
        self.assertIsInstance(handler.app, MainApplication)
        handler.app.data_engine.close()

    def test_is_a_base_api_handler(self):
        from api.base import BaseAPIHandler

        self.assertIsInstance(SignalHandler(self.app), BaseAPIHandler)


class TestSignalHandlerContextValidation(SignalHandlerTestCase):
    """Part 3: validation failures are now returned, not raised."""

    def test_non_context_argument_returns_standardized_400(self):
        handler = SignalHandler(self.app)
        result = handler.handle("not-a-context")  # type: ignore[arg-type]
        self.assertIsInstance(result, APIResult)
        self.assertEqual(result.status_code, 400)
        self.assertTrue(is_envelope(result.body))
        self.assertEqual(result.body["error"]["type"], "InvalidRequestContextError")
        self.assertEqual(result.metadata["stage"], "validation")

    def test_missing_symbol_returns_standardized_400(self):
        handler = SignalHandler(self.app)
        context = make_context(query_params={"timeframe": "1h"})
        result = handler.handle(context)
        self.assertEqual(result.status_code, 400)
        self.assertTrue(is_envelope(result.body))
        self.assertEqual(result.body["error"]["type"], "InsufficientAPIDataError")

    def test_missing_timeframe_returns_standardized_400(self):
        handler = SignalHandler(self.app)
        context = make_context(query_params={"symbol": "BTCUSDT"})
        result = handler.handle(context)
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.body["error"]["type"], "InsufficientAPIDataError")

    def test_empty_symbol_returns_standardized_400(self):
        handler = SignalHandler(self.app)
        context = make_context(query_params={"symbol": "  ", "timeframe": "1h"})
        result = handler.handle(context)
        self.assertEqual(result.status_code, 400)
        self.assertEqual(result.body["success"], False)

    def test_non_string_symbol_returns_standardized_400(self):
        handler = SignalHandler(self.app)
        context = make_context(query_params={"symbol": 123, "timeframe": "1h"})
        result = handler.handle(context)
        self.assertEqual(result.status_code, 400)
        self.assertIsNone(result.body["data"])

    def test_fields_fall_back_to_body_when_absent_from_query_params(self):
        handler = SignalHandler(self.app)
        context = make_context(
            method="POST", body={"symbol": "BTCUSDT", "timeframe": "1h"}
        )
        result = handler.handle(context)
        self.assertEqual(result.status_code, 200)

    def test_query_params_take_precedence_over_body(self):
        handler = SignalHandler(self.app)
        context = make_context(
            query_params={"symbol": "BTCUSDT", "timeframe": "1h"},
            body={"symbol": "ETHUSDT", "timeframe": "1d"},
        )
        result = handler.handle(context)
        self.assertEqual(result.metadata["symbol"], "BTCUSDT")
        self.assertEqual(result.metadata["timeframe"], "1h")


class TestSignalHandlerHappyPath(SignalHandlerTestCase):
    def setUp(self):
        super().setUp()
        self.handler = SignalHandler(self.app)
        self.context = make_context(query_params={"symbol": "btcusdt", "timeframe": "1h"})
        self.result = self.handler.handle(self.context)

    def test_returns_an_api_result(self):
        self.assertIsInstance(self.result, APIResult)

    def test_status_code_is_200(self):
        self.assertEqual(self.result.status_code, 200)
        self.assertTrue(self.result.is_success())

    def test_body_follows_standardized_envelope(self):
        self.assertTrue(is_envelope(self.result.body))
        self.assertTrue(self.result.body["success"])
        self.assertEqual(self.result.body["status_code"], 200)
        self.assertIsNone(self.result.body["error"])

    def test_data_contains_signal_result_fields(self):
        data = self.result.body["data"]
        self.assertIsInstance(data, dict)
        self.assertIn(data["direction"], {"buy", "sell", "hold"})
        self.assertIsInstance(data["strength"], float)
        self.assertIsInstance(data["confidence"], float)
        self.assertIsInstance(data["summary"], str)
        self.assertIsInstance(data["metadata"], dict)

    def test_data_matches_direct_pipeline_call(self):
        direct = self.app.run("BTCUSDT", "1h")
        self.assertEqual(self.result.body["data"]["direction"], direct.direction.value)
        self.assertEqual(self.result.body["data"]["summary"], direct.summary)

    def test_metadata_records_symbol_and_timeframe(self):
        self.assertEqual(self.result.metadata["symbol"], "btcusdt")
        self.assertEqual(self.result.metadata["timeframe"], "1h")

    def test_no_business_logic_object_leaks_into_data(self):
        # The API layer must not modify/return core/domain objects
        # directly -- data is a plain, JSON-shaped dict.
        for value in self.result.body["data"].values():
            self.assertIsInstance(value, (str, float, int, dict, type(None)))


class TestSignalHandlerFailureMapping(SignalHandlerTestCase):
    """Pipeline errors and internal errors, both standardized."""

    def test_no_candle_history_returns_standardized_404(self):
        handler = SignalHandler(self.app)
        context = make_context(query_params={"symbol": "ETHUSDT", "timeframe": "1h"})
        result = handler.handle(context)
        self.assertEqual(result.status_code, 404)
        self.assertFalse(result.is_success())
        self.assertTrue(is_envelope(result.body))
        self.assertFalse(result.body["success"])
        self.assertIsNone(result.body["data"])
        self.assertEqual(result.body["error"]["type"], "PipelineDataError")
        self.assertEqual(result.metadata["stage"], "data")

    def test_analysis_failure_returns_standardized_500(self):
        app = MainApplication(
            data_engine=self.data_engine, analyzer=_AlwaysFailingAnalyzer()
        )
        handler = SignalHandler(app)
        context = make_context(query_params={"symbol": "BTCUSDT", "timeframe": "1h"})
        result = handler.handle(context)
        self.assertEqual(result.status_code, 500)
        self.assertTrue(is_envelope(result.body))
        self.assertEqual(result.body["error"]["type"], "PipelineAnalysisError")
        self.assertEqual(result.metadata["stage"], "analysis")

    def test_signal_failure_returns_standardized_500(self):
        app = MainApplication(
            data_engine=self.data_engine, signal_generator=_AlwaysFailingSignalGenerator()
        )
        handler = SignalHandler(app)
        context = make_context(query_params={"symbol": "BTCUSDT", "timeframe": "1h"})
        result = handler.handle(context)
        self.assertEqual(result.status_code, 500)
        self.assertTrue(is_envelope(result.body))
        self.assertEqual(result.body["error"]["type"], "PipelineSignalError")
        self.assertEqual(result.metadata["stage"], "signal")

    def test_unexpected_exception_returns_standardized_internal_error(self):
        app = MainApplication(
            data_engine=self.data_engine, signal_generator=_ExplodingSignalGenerator()
        )
        handler = SignalHandler(app)
        context = make_context(query_params={"symbol": "BTCUSDT", "timeframe": "1h"})
        result = handler.handle(context)
        self.assertEqual(result.status_code, 500)
        self.assertTrue(is_envelope(result.body))
        self.assertEqual(result.body["error"]["type"], "InternalError")
        # The generic exception's own message is never echoed back --
        # only its class name, recorded in metadata for traceability.
        self.assertNotIn("totally unexpected", result.body["error"]["message"])
        self.assertEqual(result.metadata["exception_type"], "RuntimeError")
        self.assertEqual(result.metadata["stage"], "internal")


class TestSignalHandlerResponseConsistency(SignalHandlerTestCase):
    """Every outcome -- success, validation, pipeline, internal -- shares one shape."""

    def _all_outcomes(self):
        handler = SignalHandler(self.app)
        outcomes = [
            handler.handle(make_context(query_params={"symbol": "btcusdt", "timeframe": "1h"})),
            handler.handle("not-a-context"),  # type: ignore[arg-type]
            handler.handle(make_context(query_params={"timeframe": "1h"})),
            handler.handle(make_context(query_params={"symbol": "ETHUSDT", "timeframe": "1h"})),
        ]
        analysis_app = MainApplication(
            data_engine=self.data_engine, analyzer=_AlwaysFailingAnalyzer()
        )
        outcomes.append(
            SignalHandler(analysis_app).handle(
                make_context(query_params={"symbol": "BTCUSDT", "timeframe": "1h"})
            )
        )
        return outcomes

    def test_every_outcome_is_an_api_result_with_envelope_body(self):
        for result in self._all_outcomes():
            self.assertIsInstance(result, APIResult)
            self.assertTrue(is_envelope(result.body))

    def test_every_envelope_has_exactly_the_same_key_set(self):
        key_sets = {frozenset(result.body.keys()) for result in self._all_outcomes()}
        self.assertEqual(len(key_sets), 1)
        self.assertEqual(
            key_sets.pop(), frozenset({"success", "status_code", "data", "error"})
        )

    def test_success_and_error_are_mutually_exclusive(self):
        for result in self._all_outcomes():
            body = result.body
            if body["success"]:
                self.assertIsNone(body["error"])
                self.assertIsNotNone(body["data"])
            else:
                self.assertIsNone(body["data"])
                self.assertIsNotNone(body["error"])
                self.assertIn("type", body["error"])
                self.assertIn("message", body["error"])


class TestSignalHandlerNoBusinessLogic(SignalHandlerTestCase):
    """Confirms the handler stays a thin adapter -- no extra public surface."""

    def test_only_documented_public_attributes_exist(self):
        handler = SignalHandler(self.app)
        expected = {"name", "app"}
        actual = {name for name in vars(handler) if not name.startswith("_")}
        self.assertEqual(actual, expected)

    def test_handle_is_the_only_public_method_besides_inherited_helpers(self):
        # SignalHandler adds no public method beyond what BaseAPIHandler
        # already defines (handle, validate_context) -- no
        # strategy/risk/portfolio/execution/broker/AI/auth method exists.
        from api.base import BaseAPIHandler

        base_public = {
            name
            for name in vars(BaseAPIHandler)
            if not name.startswith("_") and callable(getattr(BaseAPIHandler, name))
        }
        own_public = {
            name
            for name in vars(SignalHandler)
            if not name.startswith("_") and callable(getattr(SignalHandler, name))
        }
        self.assertEqual(own_public - base_public, set())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
