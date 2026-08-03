"""
test_services.py
-------------------
Purpose:
    Unit tests for the Services foundation (Part 1): `ServiceResult`,
    `ServiceContext`, `BaseService`, and the `services.exceptions` /
    `services.utils` helpers.

Uses the standard-library ``unittest`` framework, matching the
`analysis`/`signals`/`strategies`/`strategies.risk_management`/
`strategies.portfolio_management`/`backtesting`/`execution` test
suites (no external test-runner dependency).

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest

from services import (
    BaseService,
    InsufficientServiceDataError,
    InvalidServiceContextError,
    ServiceConfigurationError,
    ServiceContext,
    ServiceError,
    ServiceResult,
    ServiceValidationError,
)
from services.utils import (
    clip,
    merge_metadata,
    validate_bool,
    validate_dict,
    validate_non_empty_str,
)


def make_context(*, service_name: str = "notification", payload=None, metadata=None) -> ServiceContext:
    return ServiceContext(
        service_name=service_name,
        payload=payload if payload is not None else {},
        metadata=metadata if metadata is not None else {},
    )


# ----------------------------------------------------------------------
# ServiceResult
# ----------------------------------------------------------------------
class TestServiceResult(unittest.TestCase):
    def test_instantiates_with_required_fields(self):
        result = ServiceResult(success=True, summary="Notification sent")
        self.assertTrue(result.success)
        self.assertEqual(result.summary, "Notification sent")
        self.assertEqual(result.metadata, {})

    def test_only_has_the_three_documented_fields(self):
        result = ServiceResult(success=False, summary="Delivery failed")
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        self.assertEqual(field_names, {"success", "summary", "metadata"})

    def test_is_frozen(self):
        result = ServiceResult(success=True, summary="OK")
        with self.assertRaises(Exception):
            result.success = False  # type: ignore[misc]

    def test_rejects_non_bool_success(self):
        with self.assertRaises(ServiceValidationError):
            ServiceResult(success="yes", summary="OK")  # type: ignore[arg-type]

    def test_rejects_blank_summary(self):
        with self.assertRaises(ServiceValidationError):
            ServiceResult(success=True, summary="   ")

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(ServiceValidationError):
            ServiceResult(success=True, summary="OK", metadata="not-a-dict")  # type: ignore[arg-type]

    def test_with_metadata_returns_new_instance(self):
        original = ServiceResult(success=True, summary="OK", metadata={"a": 1})
        updated = original.with_metadata(b=2)
        self.assertIsNot(updated, original)
        self.assertEqual(original.metadata, {"a": 1})
        self.assertEqual(updated.metadata, {"a": 1, "b": 2})

    def test_with_metadata_overrides_on_conflict(self):
        original = ServiceResult(success=True, summary="OK", metadata={"a": 1})
        updated = original.with_metadata(a=99)
        self.assertEqual(updated.metadata, {"a": 99})

    def test_no_confidence_provider_or_delivery_fields(self):
        # Defensive: ServiceResult must expose exactly the three
        # documented fields -- no confidence field (unlike the
        # trading-decision results one layer down) and no
        # provider/delivery-receipt fields have been introduced by
        # this part.
        result = ServiceResult(success=True, summary="OK")
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        for forbidden in (
            "confidence",
            "service_name",
            "provider",
            "delivery_receipt",
            "order_id",
        ):
            self.assertNotIn(forbidden, field_names)


# ----------------------------------------------------------------------
# ServiceContext
# ----------------------------------------------------------------------
class TestServiceContext(unittest.TestCase):
    def test_instantiates_with_required_fields_only(self):
        context = ServiceContext(service_name="notification")
        self.assertEqual(context.service_name, "notification")
        self.assertEqual(context.payload, {})
        self.assertEqual(context.metadata, {})

    def test_accepts_payload_and_metadata(self):
        context = ServiceContext(
            service_name="ai_commentary",
            payload={"prompt": "Summarize today's market"},
            metadata={"request_id": "req-1"},
        )
        self.assertEqual(context.payload, {"prompt": "Summarize today's market"})
        self.assertEqual(context.metadata, {"request_id": "req-1"})

    def test_has_payload_true_when_present(self):
        context = ServiceContext(service_name="scheduler", payload={"job": "daily_report"})
        self.assertTrue(context.has_payload())

    def test_has_payload_false_when_absent(self):
        context = make_context()
        self.assertFalse(context.has_payload())

    def test_is_frozen(self):
        context = make_context()
        with self.assertRaises(Exception):
            context.service_name = "scheduler"  # type: ignore[misc]

    def test_rejects_blank_service_name(self):
        with self.assertRaises(InvalidServiceContextError):
            ServiceContext(service_name="   ")

    def test_rejects_non_string_service_name(self):
        with self.assertRaises(InvalidServiceContextError):
            ServiceContext(service_name=123)  # type: ignore[arg-type]

    def test_rejects_non_dict_payload(self):
        with self.assertRaises(InvalidServiceContextError):
            ServiceContext(service_name="notification", payload="not-a-dict")  # type: ignore[arg-type]

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(InvalidServiceContextError):
            ServiceContext(service_name="notification", metadata="not-a-dict")  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# services.utils
# ----------------------------------------------------------------------
class TestUtils(unittest.TestCase):
    def test_validate_non_empty_str_accepts_valid_string(self):
        self.assertEqual(validate_non_empty_str("notification", name="service_name"), "notification")

    def test_validate_non_empty_str_rejects_blank(self):
        with self.assertRaises(ServiceValidationError):
            validate_non_empty_str("   ", name="service_name")

    def test_validate_non_empty_str_rejects_non_string(self):
        with self.assertRaises(ServiceValidationError):
            validate_non_empty_str(123, name="service_name")  # type: ignore[arg-type]

    def test_validate_bool_accepts_bool(self):
        self.assertTrue(validate_bool(True, name="success"))
        self.assertFalse(validate_bool(False, name="success"))

    def test_validate_bool_rejects_non_bool(self):
        with self.assertRaises(ServiceValidationError):
            validate_bool(1, name="success")  # type: ignore[arg-type]

    def test_validate_dict_accepts_dict(self):
        self.assertEqual(validate_dict({"a": 1}, name="payload"), {"a": 1})

    def test_validate_dict_rejects_non_dict(self):
        with self.assertRaises(ServiceValidationError):
            validate_dict("not-a-dict", name="payload")  # type: ignore[arg-type]

    def test_clip_clamps_low_and_high(self):
        self.assertEqual(clip(-0.5), 0.0)
        self.assertEqual(clip(1.5), 1.0)
        self.assertEqual(clip(0.5), 0.5)

    def test_clip_respects_custom_bounds(self):
        self.assertEqual(clip(5, low=0, high=10), 5)
        self.assertEqual(clip(-5, low=0, high=10), 0)
        self.assertEqual(clip(15, low=0, high=10), 10)

    def test_merge_metadata_combines_sources(self):
        merged = merge_metadata({"a": 1}, {"b": 2})
        self.assertEqual(merged, {"a": 1, "b": 2})

    def test_merge_metadata_later_source_wins(self):
        merged = merge_metadata({"a": 1}, {"a": 2})
        self.assertEqual(merged, {"a": 2})

    def test_merge_metadata_skips_none(self):
        merged = merge_metadata(None, {"a": 1}, None)
        self.assertEqual(merged, {"a": 1})

    def test_merge_metadata_no_sources_returns_empty_dict(self):
        self.assertEqual(merge_metadata(), {})


# ----------------------------------------------------------------------
# services.exceptions
# ----------------------------------------------------------------------
class TestExceptionHierarchy(unittest.TestCase):
    def test_service_validation_error_is_service_error(self):
        self.assertTrue(issubclass(ServiceValidationError, ServiceError))

    def test_invalid_service_context_error_is_service_validation_error(self):
        self.assertTrue(issubclass(InvalidServiceContextError, ServiceValidationError))

    def test_insufficient_service_data_error_is_service_error(self):
        self.assertTrue(issubclass(InsufficientServiceDataError, ServiceError))
        self.assertFalse(issubclass(InsufficientServiceDataError, ServiceValidationError))

    def test_service_configuration_error_is_service_error(self):
        self.assertTrue(issubclass(ServiceConfigurationError, ServiceError))

    def test_service_error_is_exception(self):
        self.assertTrue(issubclass(ServiceError, Exception))


# ----------------------------------------------------------------------
# BaseService (via a minimal concrete fake, mirroring
# test_execution.py's FakeExecutionEngine pattern)
# ----------------------------------------------------------------------
class FakeService(BaseService):
    """Minimal concrete `BaseService` used only to exercise the base class."""

    def __init__(self, *, name=None, succeed: bool = True):
        super().__init__(name=name)
        self._succeed = succeed

    def execute(self, context: ServiceContext) -> ServiceResult:
        self.validate_context(context)
        if not context.has_payload():
            raise InsufficientServiceDataError("no payload to act on")
        return self._build_result(
            success=self._succeed,
            summary=f"Handled {context.service_name} call",
            metadata={"handled_by": self.name},
        )


class TestBaseService(unittest.TestCase):
    def test_defaults_name_to_class_name(self):
        service = FakeService()
        self.assertEqual(service.name, "FakeService")

    def test_accepts_custom_name(self):
        service = FakeService(name="CustomService")
        self.assertEqual(service.name, "CustomService")

    def test_cannot_instantiate_abstract_base_directly(self):
        with self.assertRaises(TypeError):
            BaseService()  # type: ignore[abstract]

    def test_validate_context_accepts_valid_context(self):
        service = FakeService()
        context = make_context(payload={"message": "hello"})
        self.assertIs(service.validate_context(context), context)

    def test_validate_context_rejects_non_context(self):
        service = FakeService()
        with self.assertRaises(InvalidServiceContextError):
            service.validate_context("not-a-context")  # type: ignore[arg-type]

    def test_execute_returns_service_result(self):
        service = FakeService(succeed=True)
        context = make_context(payload={"message": "hello"})
        result = service.execute(context)
        self.assertIsInstance(result, ServiceResult)
        self.assertTrue(result.success)
        self.assertEqual(result.metadata, {"handled_by": "FakeService"})

    def test_execute_raises_insufficient_data_when_no_payload(self):
        service = FakeService()
        context = make_context()
        with self.assertRaises(InsufficientServiceDataError):
            service.execute(context)

    def test_build_result_defaults_metadata_to_empty_dict(self):
        service = FakeService()
        result = service._build_result(success=False, summary="Rejected")
        self.assertEqual(result.metadata, {})

    def test_repr_includes_class_and_name(self):
        service = FakeService(name="Notifier")
        self.assertEqual(repr(service), "FakeService(name='Notifier')")


# ----------------------------------------------------------------------
# Integration: a realistic ServiceContext carried end-to-end through a
# real BaseService subclass.
# ----------------------------------------------------------------------
class TestIntegration(unittest.TestCase):
    def test_end_to_end_call_with_payload(self):
        service = FakeService(succeed=True)
        context = ServiceContext(
            service_name="notification",
            payload={"message": "Position opened"},
            metadata={"request_id": "req-42"},
        )
        result = service.execute(context)

        self.assertTrue(context.has_payload())
        self.assertTrue(result.success)
        self.assertIn("notification", result.summary)

    def test_unsuccessful_call_still_just_data(self):
        # ServiceContext is a pure data container: it does not itself
        # interpret whether a call will succeed or fail -- that
        # remains a concrete BaseService's job (a future Services
        # part), not this foundation's.
        context = ServiceContext(service_name="ai_commentary", payload={"prompt": "..."})
        service = FakeService(succeed=False)
        result = service.execute(context)
        self.assertFalse(result.success)

    def test_no_ai_broker_or_networking_fields_end_to_end(self):
        service = FakeService()
        context = make_context(payload={"message": "hello"})
        result = service.execute(context)
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        for forbidden in ("order_id", "fill_price", "broker", "exchange", "provider"):
            self.assertNotIn(forbidden, field_names)


if __name__ == "__main__":
    unittest.main()
