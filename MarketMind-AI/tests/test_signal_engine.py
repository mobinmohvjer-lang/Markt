"""
test_signal_engine.py
-----------------------
Purpose:
    Unit tests for `SignalEngine` (`services/signal_engine.py`) --
    Services Part 2A (construction, dependency injection of an optional
    `EventBus`, configuration validation/merging, and the public
    interfaces `has_event_bus`/`get_configuration`) plus Part 2B
    (`execute()`'s real orchestration: resolving a `core.entities.
    signal.Signal` from `ServiceContext.payload`, applying
    `require_min_confidence`/`min_confidence`, publishing a
    `SignalGenerated` event through `self.event_bus` when one is
    injected, and returning a `ServiceResult` reflecting what actually
    happened).

Uses the standard-library ``unittest`` framework, matching the
`analysis`/`signals`/`strategies`/`strategies.risk_management`/
`strategies.portfolio_management`/`backtesting`/`execution`/`services`
test suites (no external test-runner dependency).

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from core.entities.signal import Signal
from core.enums import SignalDirection

from events.interfaces.event import Event
from events.interfaces.event_bus import EventBus
from events.interfaces.event_handler import EventHandler
from events.event_types.signal_generated import SignalGenerated

from services import ServiceConfigurationError, ServiceContext, SignalEngine
from services.exceptions import InsufficientServiceDataError, InvalidServiceContextError
from services.result import ServiceResult
from services.base import BaseService


def make_signal(*, confidence: float = 0.8) -> Signal:
    return Signal(
        signal_id="signal-1",
        symbol="BTCUSDT",
        direction=SignalDirection.BUY,
        confidence=confidence,
        source="test",
        timeframe="1h",
        generated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


class FakeEventBus(EventBus):
    """Minimal in-memory `EventBus` fake -- no real dispatch needed for these tests."""

    def __init__(self) -> None:
        self.published: list[Event] = []
        self.subscriptions: list[tuple[type, EventHandler]] = []

    def publish(self, event: Event) -> None:
        self.published.append(event)

    def subscribe(self, event_type: type, handler: EventHandler) -> None:
        self.subscriptions.append((event_type, handler))

    def unsubscribe(self, event_type: type, handler: EventHandler) -> None:
        self.subscriptions = [
            (t, h) for (t, h) in self.subscriptions if not (t is event_type and h is handler)
        ]


class TestConstruction(unittest.TestCase):
    def test_is_a_base_service(self):
        engine = SignalEngine()
        self.assertIsInstance(engine, BaseService)

    def test_default_name_is_class_name(self):
        engine = SignalEngine()
        self.assertEqual(engine.name, "SignalEngine")

    def test_custom_name(self):
        engine = SignalEngine(name="primary-signal-engine")
        self.assertEqual(engine.name, "primary-signal-engine")

    def test_no_event_bus_by_default(self):
        engine = SignalEngine()
        self.assertIsNone(engine.event_bus)
        self.assertFalse(engine.has_event_bus())

    def test_repr_contains_name_and_bus_state(self):
        engine = SignalEngine(name="repr-engine")
        text = repr(engine)
        self.assertIn("repr-engine", text)
        self.assertIn("has_event_bus=False", text)


class TestDependencyInjection(unittest.TestCase):
    def test_accepts_injected_event_bus(self):
        bus = FakeEventBus()
        engine = SignalEngine(event_bus=bus)
        self.assertIs(engine.event_bus, bus)
        self.assertTrue(engine.has_event_bus())

    def test_rejects_non_event_bus(self):
        with self.assertRaises(ServiceConfigurationError):
            SignalEngine(event_bus="not-a-bus")

    def test_rejects_non_event_bus_object(self):
        with self.assertRaises(ServiceConfigurationError):
            SignalEngine(event_bus=object())

    def test_two_instances_do_not_share_a_bus(self):
        bus_a = FakeEventBus()
        engine_a = SignalEngine(event_bus=bus_a)
        engine_b = SignalEngine()
        self.assertTrue(engine_a.has_event_bus())
        self.assertFalse(engine_b.has_event_bus())


class TestConfiguration(unittest.TestCase):
    def test_default_configuration(self):
        engine = SignalEngine()
        config = engine.get_configuration()
        self.assertEqual(
            config,
            {
                "auto_generate_signal_metadata": True,
                "require_min_confidence": True,
                "min_confidence": 0.0,
            },
        )

    def test_get_configuration_returns_a_copy(self):
        engine = SignalEngine()
        config = engine.get_configuration()
        config["min_confidence"] = 0.99
        self.assertEqual(engine.config["min_confidence"], 0.0)

    def test_partial_override_merges_with_defaults(self):
        engine = SignalEngine(config={"min_confidence": 0.5})
        config = engine.get_configuration()
        self.assertEqual(config["min_confidence"], 0.5)
        self.assertTrue(config["auto_generate_signal_metadata"])
        self.assertTrue(config["require_min_confidence"])

    def test_full_override(self):
        engine = SignalEngine(
            config={
                "auto_generate_signal_metadata": False,
                "require_min_confidence": False,
                "min_confidence": 0.25,
            }
        )
        config = engine.get_configuration()
        self.assertFalse(config["auto_generate_signal_metadata"])
        self.assertFalse(config["require_min_confidence"])
        self.assertEqual(config["min_confidence"], 0.25)

    def test_min_confidence_boundaries_accepted(self):
        SignalEngine(config={"min_confidence": 0.0})
        SignalEngine(config={"min_confidence": 1.0})

    def test_min_confidence_int_is_coerced_to_float(self):
        engine = SignalEngine(config={"min_confidence": 1})
        self.assertEqual(engine.config["min_confidence"], 1.0)
        self.assertIsInstance(engine.config["min_confidence"], float)

    def test_rejects_non_dict_config(self):
        with self.assertRaises(ServiceConfigurationError):
            SignalEngine(config="not-a-dict")

    def test_rejects_unknown_config_key(self):
        with self.assertRaises(ServiceConfigurationError):
            SignalEngine(config={"unknown_key": True})

    def test_rejects_non_bool_auto_generate_signal_metadata(self):
        with self.assertRaises(ServiceConfigurationError):
            SignalEngine(config={"auto_generate_signal_metadata": "yes"})

    def test_rejects_non_bool_require_min_confidence(self):
        with self.assertRaises(ServiceConfigurationError):
            SignalEngine(config={"require_min_confidence": 1})

    def test_rejects_out_of_range_min_confidence(self):
        with self.assertRaises(ServiceConfigurationError):
            SignalEngine(config={"min_confidence": 1.5})
        with self.assertRaises(ServiceConfigurationError):
            SignalEngine(config={"min_confidence": -0.1})

    def test_rejects_non_finite_min_confidence(self):
        with self.assertRaises(ServiceConfigurationError):
            SignalEngine(config={"min_confidence": float("nan")})
        with self.assertRaises(ServiceConfigurationError):
            SignalEngine(config={"min_confidence": float("inf")})

    def test_rejects_bool_min_confidence(self):
        with self.assertRaises(ServiceConfigurationError):
            SignalEngine(config={"min_confidence": True})

    def test_rejects_non_numeric_min_confidence(self):
        with self.assertRaises(ServiceConfigurationError):
            SignalEngine(config={"min_confidence": "high"})

    def test_default_config_not_mutated_by_instance(self):
        engine = SignalEngine(config={"min_confidence": 0.9})
        self.assertEqual(SignalEngine.DEFAULT_CONFIG["min_confidence"], 0.0)


class TestExecute(unittest.TestCase):
    """Covers `execute()`'s real Part 2B orchestration."""

    def test_execute_validates_context_type_first(self):
        engine = SignalEngine()
        with self.assertRaises(InvalidServiceContextError):
            engine.execute("not-a-context")

    # -- resolving a Signal from payload["signal"] --------------------

    def test_execute_publishes_an_existing_signal_via_the_event_bus(self):
        bus = FakeEventBus()
        engine = SignalEngine(event_bus=bus)
        signal = make_signal(confidence=0.9)
        context = ServiceContext(service_name="signal_engine", payload={"signal": signal})

        result = engine.execute(context)

        self.assertIsInstance(result, ServiceResult)
        self.assertTrue(result.success)
        self.assertEqual(len(bus.published), 1)
        published_event = bus.published[0]
        self.assertIsInstance(published_event, SignalGenerated)
        self.assertEqual(published_event.signal, signal)
        self.assertEqual(result.metadata["signal_id"], signal.signal_id)
        self.assertEqual(result.metadata["symbol"], signal.symbol)
        self.assertEqual(result.metadata["confidence"], signal.confidence)
        self.assertEqual(result.metadata["event_id"], published_event.event_id)
        self.assertTrue(result.metadata["published"])

    def test_execute_rejects_a_non_signal_under_the_signal_key(self):
        engine = SignalEngine()
        context = ServiceContext(service_name="signal_engine", payload={"signal": "not-a-signal"})
        with self.assertRaises(InsufficientServiceDataError):
            engine.execute(context)

    def test_execute_does_not_mutate_the_payload_signal(self):
        bus = FakeEventBus()
        engine = SignalEngine(event_bus=bus)
        signal = make_signal()
        context = ServiceContext(service_name="signal_engine", payload={"signal": signal})
        engine.execute(context)
        self.assertEqual(context.payload["signal"], signal)

    # -- building a Signal from raw payload fields ---------------------

    def test_execute_builds_a_signal_from_raw_payload_fields(self):
        bus = FakeEventBus()
        engine = SignalEngine(event_bus=bus)
        context = ServiceContext(
            service_name="signal_engine",
            payload={
                "symbol": "ETHUSDT",
                "direction": SignalDirection.SELL,
                "confidence": 0.7,
                "source": "test-strategy",
                "timeframe": "4h",
            },
        )

        result = engine.execute(context)

        self.assertTrue(result.success)
        published_signal = bus.published[0].signal
        self.assertEqual(published_signal.symbol, "ETHUSDT")
        self.assertEqual(published_signal.direction, SignalDirection.SELL)
        self.assertEqual(published_signal.confidence, 0.7)
        self.assertEqual(published_signal.source, "test-strategy")
        self.assertEqual(published_signal.timeframe, "4h")

    def test_execute_accepts_direction_as_a_string(self):
        bus = FakeEventBus()
        engine = SignalEngine(event_bus=bus)
        context = ServiceContext(
            service_name="signal_engine",
            payload={
                "symbol": "BTCUSDT",
                "direction": "buy",
                "confidence": 0.5,
                "source": "test-strategy",
                "timeframe": "1h",
            },
        )
        result = engine.execute(context)
        self.assertTrue(result.success)
        self.assertEqual(bus.published[0].signal.direction, SignalDirection.BUY)

    def test_execute_raises_for_missing_required_fields(self):
        engine = SignalEngine()
        context = ServiceContext(service_name="signal_engine", payload={"symbol": "BTCUSDT"})
        with self.assertRaises(InsufficientServiceDataError):
            engine.execute(context)

    def test_execute_raises_for_invalid_direction_string(self):
        engine = SignalEngine()
        context = ServiceContext(
            service_name="signal_engine",
            payload={
                "symbol": "BTCUSDT",
                "direction": "sideways",
                "confidence": 0.5,
                "source": "test-strategy",
                "timeframe": "1h",
            },
        )
        with self.assertRaises(InsufficientServiceDataError):
            engine.execute(context)

    def test_execute_raises_for_non_numeric_confidence(self):
        engine = SignalEngine()
        context = ServiceContext(
            service_name="signal_engine",
            payload={
                "symbol": "BTCUSDT",
                "direction": SignalDirection.BUY,
                "confidence": "high",
                "source": "test-strategy",
                "timeframe": "1h",
            },
        )
        with self.assertRaises(InsufficientServiceDataError):
            engine.execute(context)

    def test_execute_auto_generates_signal_id_and_generated_at_by_default(self):
        bus = FakeEventBus()
        engine = SignalEngine(event_bus=bus)
        context = ServiceContext(
            service_name="signal_engine",
            payload={
                "symbol": "BTCUSDT",
                "direction": SignalDirection.BUY,
                "confidence": 0.5,
                "source": "test-strategy",
                "timeframe": "1h",
            },
        )
        result = engine.execute(context)
        published_signal = bus.published[0].signal
        self.assertTrue(published_signal.signal_id)
        self.assertIsNotNone(published_signal.generated_at)
        self.assertTrue(result.success)

    def test_execute_raises_when_signal_id_missing_and_auto_generate_disabled(self):
        engine = SignalEngine(config={"auto_generate_signal_metadata": False})
        context = ServiceContext(
            service_name="signal_engine",
            payload={
                "symbol": "BTCUSDT",
                "direction": SignalDirection.BUY,
                "confidence": 0.5,
                "source": "test-strategy",
                "timeframe": "1h",
                "generated_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
            },
        )
        with self.assertRaises(InsufficientServiceDataError):
            engine.execute(context)

    def test_execute_raises_when_generated_at_missing_and_auto_generate_disabled(self):
        engine = SignalEngine(config={"auto_generate_signal_metadata": False})
        context = ServiceContext(
            service_name="signal_engine",
            payload={
                "symbol": "BTCUSDT",
                "direction": SignalDirection.BUY,
                "confidence": 0.5,
                "source": "test-strategy",
                "timeframe": "1h",
                "signal_id": "explicit-id",
            },
        )
        with self.assertRaises(InsufficientServiceDataError):
            engine.execute(context)

    def test_execute_message_mentions_engine_name_on_insufficient_data(self):
        engine = SignalEngine(name="my-engine")
        context = ServiceContext(service_name="signal_engine")
        with self.assertRaises(InsufficientServiceDataError) as cm:
            engine.execute(context)
        self.assertIn("my-engine", str(cm.exception))

    # -- min_confidence gating ------------------------------------------

    def test_execute_does_not_publish_below_min_confidence(self):
        bus = FakeEventBus()
        engine = SignalEngine(event_bus=bus, config={"min_confidence": 0.5})
        context = ServiceContext(
            service_name="signal_engine", payload={"signal": make_signal(confidence=0.2)}
        )

        result = engine.execute(context)

        self.assertFalse(result.success)
        self.assertEqual(bus.published, [])
        self.assertFalse(result.metadata["published"])

    def test_execute_publishes_when_confidence_meets_threshold(self):
        bus = FakeEventBus()
        engine = SignalEngine(event_bus=bus, config={"min_confidence": 0.5})
        context = ServiceContext(
            service_name="signal_engine", payload={"signal": make_signal(confidence=0.5)}
        )
        result = engine.execute(context)
        self.assertTrue(result.success)
        self.assertEqual(len(bus.published), 1)

    def test_execute_ignores_min_confidence_when_require_min_confidence_is_false(self):
        bus = FakeEventBus()
        engine = SignalEngine(
            event_bus=bus, config={"require_min_confidence": False, "min_confidence": 0.9}
        )
        context = ServiceContext(
            service_name="signal_engine", payload={"signal": make_signal(confidence=0.0)}
        )
        result = engine.execute(context)
        self.assertTrue(result.success)
        self.assertEqual(len(bus.published), 1)

    # -- no EventBus injected --------------------------------------------

    def test_execute_without_event_bus_does_not_raise_and_reports_failure(self):
        engine = SignalEngine()  # no event_bus
        context = ServiceContext(
            service_name="signal_engine", payload={"signal": make_signal(confidence=0.9)}
        )
        result = engine.execute(context)
        self.assertIsInstance(result, ServiceResult)
        self.assertFalse(result.success)
        self.assertFalse(result.metadata["published"])


class TestScopeBoundaries(unittest.TestCase):
    """Confirms this module stays within services/'s documented dependency
    rules (core/events only) -- Part 2A's construction/DI/config surface
    plus Part 2B's execute() orchestration, no more."""

    def test_no_signals_package_import(self):
        import services.signal_engine as module

        source = module.__file__
        with open(source, "r", encoding="utf-8") as fh:
            text = fh.read()
        # services/ may only depend on core/events (PROJECT_RULES.md
        # Section 4) -- this module must never import the unrelated
        # `signals/` trading-pipeline package, nor any of `strategies/`
        # (including risk_management/portfolio_management), `analysis/`,
        # or `execution/` -- Signal Engine Part 2B's orchestration
        # (build/validate/publish a Signal) needs none of them.
        self.assertNotIn("import signals", text)
        self.assertNotIn("from signals", text)
        for forbidden in ("strategies", "analysis", "execution", "backtesting"):
            self.assertNotIn(f"import {forbidden}", text)
            self.assertNotIn(f"from {forbidden}", text)

    def test_event_bus_is_optional_at_construction(self):
        # Constructing without an EventBus must not raise -- Part 2A
        # does not require a real bus to exist yet.
        SignalEngine()

    def test_signal_engine_is_concrete_not_abstract(self):
        # Unlike a Part 1 foundation, Part 2A's SignalEngine is already
        # instantiable directly (no fake subclass required).
        engine = SignalEngine()
        self.assertIsInstance(engine, SignalEngine)


class TestIntegration(unittest.TestCase):
    """Builds a realistic ServiceContext carrying a real core.entities.signal.Signal
    and drives it through the real end-to-end execute() orchestration."""

    def test_realistic_context_with_real_signal_and_bus(self):
        bus = FakeEventBus()
        engine = SignalEngine(event_bus=bus, config={"min_confidence": 0.3}, name="integration-engine")
        signal = make_signal(confidence=0.9)
        context = ServiceContext(
            service_name="signal_engine",
            payload={"signal": signal},
            metadata={"request_id": "req-1"},
        )

        self.assertTrue(engine.has_event_bus())
        self.assertEqual(engine.get_configuration()["min_confidence"], 0.3)

        result = engine.execute(context)

        # The signal cleared min_confidence and a bus was injected, so it
        # was actually published, and the context itself was left intact.
        self.assertIsInstance(result, ServiceResult)
        self.assertTrue(result.success)
        self.assertEqual(len(bus.published), 1)
        self.assertEqual(bus.published[0].signal, signal)
        self.assertEqual(context.payload["signal"], signal)
        self.assertEqual(context.metadata["request_id"], "req-1")

    def test_realistic_context_below_threshold_is_not_published(self):
        bus = FakeEventBus()
        engine = SignalEngine(event_bus=bus, config={"min_confidence": 0.95}, name="integration-engine")
        signal = make_signal(confidence=0.4)
        context = ServiceContext(service_name="signal_engine", payload={"signal": signal})

        result = engine.execute(context)

        self.assertFalse(result.success)
        self.assertEqual(bus.published, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
