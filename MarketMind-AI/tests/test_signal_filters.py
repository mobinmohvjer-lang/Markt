"""
test_signal_filters.py
-----------------------
Purpose:
    Unit tests for the Signal Engine Part 4 module: `signals.filters`
    (`BaseSignalFilter`, `FilterOutcome`, `ConfidenceFilter`,
    `DuplicateSignalFilter`, `CooldownFilter`, `ConflictFilter`,
    `SignalFilterPipeline`, `SignalFilterPipelineResult`).

Mirrors the local-factory / assertion style already used by
`tests/test_signals.py` (Part 1), `tests/test_technical_signal_generator.py`
(Part 2), and `tests/test_signal_aggregator.py` (Part 3), all left
untouched by this change. Each filter is tested in isolation first
(accept/reject/modify paths, invalid-input handling, stateful history),
then `SignalFilterPipeline` is tested for sequencing, short-circuiting,
and trace/metadata composition across multiple filters together.

Uses the standard-library ``unittest`` framework, no external
test-runner dependency, no network access.

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest

from core.enums import SignalDirection
from signals import SignalContext, SignalResult, SignalValidationError
from signals.filters import (
    BaseSignalFilter,
    ConfidenceFilter,
    ConflictFilter,
    CooldownFilter,
    DuplicateSignalFilter,
    FilterOutcome,
    SignalFilterPipeline,
    SignalFilterPipelineResult,
)

SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"
OTHER_SYMBOL = "ETHUSDT"


# ----------------------------------------------------------------------
# Local test factories
# ----------------------------------------------------------------------
def make_context(symbol: str = SYMBOL, timeframe: str = TIMEFRAME) -> SignalContext:
    return SignalContext(symbol=symbol, timeframe=timeframe, analysis_results=[])


def make_result(
    *,
    direction: SignalDirection = SignalDirection.BUY,
    strength: float = 0.6,
    confidence: float = 0.7,
    summary: str = "Bullish technical signal.",
    metadata: dict | None = None,
) -> SignalResult:
    return SignalResult(
        direction=direction,
        strength=strength,
        confidence=confidence,
        summary=summary,
        metadata=metadata or {},
    )


class _ClockStub:
    """Simple manually-advanced clock for `CooldownFilter` tests."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def advance(self, seconds: float) -> None:
        self._now += seconds

    def __call__(self) -> float:
        return self._now


# ----------------------------------------------------------------------
# FilterOutcome
# ----------------------------------------------------------------------
class TestFilterOutcome(unittest.TestCase):
    def test_accept_requires_result(self):
        with self.assertRaises(SignalValidationError):
            FilterOutcome(filter_name="X", action="accept", result=None, reason="ok")

    def test_modify_requires_result(self):
        with self.assertRaises(SignalValidationError):
            FilterOutcome(filter_name="X", action="modify", result=None, reason="ok")

    def test_reject_forbids_result(self):
        with self.assertRaises(SignalValidationError):
            FilterOutcome(
                filter_name="X", action="reject", result=make_result(), reason="too weak"
            )

    def test_invalid_action_rejected(self):
        with self.assertRaises(SignalValidationError):
            FilterOutcome(filter_name="X", action="skip", result=None, reason="huh")

    def test_empty_reason_rejected(self):
        with self.assertRaises(SignalValidationError):
            FilterOutcome(filter_name="X", action="accept", result=make_result(), reason="   ")

    def test_as_trace_entry_shape(self):
        outcome = FilterOutcome(
            filter_name="ConfidenceFilter", action="accept", result=make_result(), reason="fine"
        )
        self.assertEqual(
            outcome.as_trace_entry(),
            {"filter": "ConfidenceFilter", "action": "accept", "reason": "fine"},
        )


# ----------------------------------------------------------------------
# BaseSignalFilter (via a minimal concrete subclass)
# ----------------------------------------------------------------------
class _AlwaysAccept(BaseSignalFilter):
    def apply(self, result: SignalResult, context: SignalContext) -> FilterOutcome:
        self._validate_inputs(result, context)
        return self._accept(result, reason="always accepts")


class TestBaseSignalFilter(unittest.TestCase):
    def test_default_name_is_class_name(self):
        self.assertEqual(_AlwaysAccept().name, "_AlwaysAccept")

    def test_custom_name(self):
        self.assertEqual(_AlwaysAccept(name="custom").name, "custom")

    def test_rejects_non_signal_result(self):
        with self.assertRaises(SignalValidationError):
            _AlwaysAccept().apply("not-a-result", make_context())

    def test_rejects_non_signal_context(self):
        with self.assertRaises(SignalValidationError):
            _AlwaysAccept().apply(make_result(), "not-a-context")

    def test_reset_is_a_safe_no_op_by_default(self):
        # Should not raise for a stateless filter.
        _AlwaysAccept().reset()

    def test_repr_contains_class_and_name(self):
        text = repr(_AlwaysAccept(name="foo"))
        self.assertIn("_AlwaysAccept", text)
        self.assertIn("foo", text)


# ----------------------------------------------------------------------
# ConfidenceFilter
# ----------------------------------------------------------------------
class TestConfidenceFilter(unittest.TestCase):
    def test_construction_rejects_out_of_range_threshold(self):
        with self.assertRaises(SignalValidationError):
            ConfidenceFilter(min_confidence=1.5)
        with self.assertRaises(SignalValidationError):
            ConfidenceFilter(min_confidence=-0.1)

    def test_accepts_when_confidence_meets_minimum(self):
        signal_filter = ConfidenceFilter(min_confidence=0.5)
        outcome = signal_filter.apply(make_result(confidence=0.5), make_context())
        self.assertEqual(outcome.action, "accept")
        self.assertEqual(outcome.result.confidence, 0.5)

    def test_accepts_when_confidence_exceeds_minimum(self):
        signal_filter = ConfidenceFilter(min_confidence=0.3)
        outcome = signal_filter.apply(make_result(confidence=0.9), make_context())
        self.assertEqual(outcome.action, "accept")

    def test_rejects_when_confidence_below_minimum(self):
        signal_filter = ConfidenceFilter(min_confidence=0.5)
        outcome = signal_filter.apply(make_result(confidence=0.2), make_context())
        self.assertEqual(outcome.action, "reject")
        self.assertIsNone(outcome.result)
        self.assertIn("0.200", outcome.reason)
        self.assertIn("0.500", outcome.reason)

    def test_never_modifies_result(self):
        signal_filter = ConfidenceFilter(min_confidence=0.1)
        original = make_result(confidence=0.9)
        outcome = signal_filter.apply(original, make_context())
        self.assertIs(outcome.result, original)

    def test_invalid_input_raises(self):
        with self.assertRaises(SignalValidationError):
            ConfidenceFilter().apply(None, make_context())


# ----------------------------------------------------------------------
# DuplicateSignalFilter
# ----------------------------------------------------------------------
class TestDuplicateSignalFilter(unittest.TestCase):
    def test_first_signal_for_key_is_accepted(self):
        signal_filter = DuplicateSignalFilter()
        outcome = signal_filter.apply(make_result(), make_context())
        self.assertEqual(outcome.action, "accept")

    def test_identical_consecutive_signal_is_rejected(self):
        signal_filter = DuplicateSignalFilter()
        context = make_context()
        signal_filter.apply(make_result(direction=SignalDirection.BUY, strength=0.6), context)
        outcome = signal_filter.apply(
            make_result(direction=SignalDirection.BUY, strength=0.6), context
        )
        self.assertEqual(outcome.action, "reject")
        self.assertIsNone(outcome.result)

    def test_different_strength_is_not_a_duplicate(self):
        signal_filter = DuplicateSignalFilter()
        context = make_context()
        signal_filter.apply(make_result(direction=SignalDirection.BUY, strength=0.6), context)
        outcome = signal_filter.apply(
            make_result(direction=SignalDirection.BUY, strength=0.61), context
        )
        self.assertEqual(outcome.action, "accept")

    def test_different_direction_is_not_a_duplicate(self):
        signal_filter = DuplicateSignalFilter()
        context = make_context()
        signal_filter.apply(make_result(direction=SignalDirection.BUY, strength=0.6), context)
        outcome = signal_filter.apply(
            make_result(direction=SignalDirection.SELL, strength=0.6), context
        )
        self.assertEqual(outcome.action, "accept")

    def test_strength_precision_rounds_negligible_noise(self):
        signal_filter = DuplicateSignalFilter(strength_precision=2)
        context = make_context()
        signal_filter.apply(make_result(strength=0.601), context)
        outcome = signal_filter.apply(make_result(strength=0.6049), context)
        # Both round to 0.60 at 2 decimal places -> duplicate.
        self.assertEqual(outcome.action, "reject")

    def test_different_symbol_is_independent(self):
        signal_filter = DuplicateSignalFilter()
        signal_filter.apply(make_result(), make_context(symbol=SYMBOL))
        outcome = signal_filter.apply(make_result(), make_context(symbol=OTHER_SYMBOL))
        self.assertEqual(outcome.action, "accept")

    def test_different_timeframe_is_independent(self):
        signal_filter = DuplicateSignalFilter()
        signal_filter.apply(make_result(), make_context(timeframe="1h"))
        outcome = signal_filter.apply(make_result(), make_context(timeframe="4h"))
        self.assertEqual(outcome.action, "accept")

    def test_non_duplicate_after_a_different_intervening_signal_is_accepted(self):
        signal_filter = DuplicateSignalFilter()
        context = make_context()
        signal_filter.apply(make_result(direction=SignalDirection.BUY, strength=0.6), context)
        signal_filter.apply(make_result(direction=SignalDirection.SELL, strength=0.4), context)
        outcome = signal_filter.apply(
            make_result(direction=SignalDirection.BUY, strength=0.6), context
        )
        # Not a *consecutive* repeat (SELL happened in between) -> accepted.
        self.assertEqual(outcome.action, "accept")

    def test_reset_clears_history(self):
        signal_filter = DuplicateSignalFilter()
        context = make_context()
        signal_filter.apply(make_result(), context)
        signal_filter.reset()
        outcome = signal_filter.apply(make_result(), context)
        self.assertEqual(outcome.action, "accept")

    def test_construction_rejects_negative_precision(self):
        with self.assertRaises(SignalValidationError):
            DuplicateSignalFilter(strength_precision=-1)

    def test_construction_rejects_non_int_precision(self):
        with self.assertRaises(SignalValidationError):
            DuplicateSignalFilter(strength_precision=1.5)

    def test_invalid_input_raises(self):
        with self.assertRaises(SignalValidationError):
            DuplicateSignalFilter().apply(make_result(), "not-a-context")


# ----------------------------------------------------------------------
# CooldownFilter
# ----------------------------------------------------------------------
class TestCooldownFilter(unittest.TestCase):
    def test_construction_rejects_negative_cooldown(self):
        with self.assertRaises(SignalValidationError):
            CooldownFilter(cooldown_seconds=-1.0)

    def test_construction_rejects_non_numeric_cooldown(self):
        with self.assertRaises(SignalValidationError):
            CooldownFilter(cooldown_seconds="60")

    def test_construction_rejects_non_callable_clock(self):
        with self.assertRaises(SignalValidationError):
            CooldownFilter(cooldown_seconds=60.0, clock="not-callable")

    def test_first_signal_for_key_is_accepted(self):
        clock = _ClockStub()
        signal_filter = CooldownFilter(cooldown_seconds=60.0, clock=clock)
        outcome = signal_filter.apply(make_result(), make_context())
        self.assertEqual(outcome.action, "accept")

    def test_second_signal_within_cooldown_is_rejected(self):
        clock = _ClockStub()
        signal_filter = CooldownFilter(cooldown_seconds=60.0, clock=clock)
        context = make_context()
        signal_filter.apply(make_result(), context)
        clock.advance(30.0)
        outcome = signal_filter.apply(make_result(), context)
        self.assertEqual(outcome.action, "reject")
        self.assertIn("remaining", outcome.reason)

    def test_second_signal_after_cooldown_elapses_is_accepted(self):
        clock = _ClockStub()
        signal_filter = CooldownFilter(cooldown_seconds=60.0, clock=clock)
        context = make_context()
        signal_filter.apply(make_result(), context)
        clock.advance(60.0)
        outcome = signal_filter.apply(make_result(), context)
        self.assertEqual(outcome.action, "accept")

    def test_rejects_regardless_of_direction(self):
        clock = _ClockStub()
        signal_filter = CooldownFilter(cooldown_seconds=60.0, clock=clock)
        context = make_context()
        signal_filter.apply(make_result(direction=SignalDirection.BUY), context)
        clock.advance(1.0)
        outcome = signal_filter.apply(make_result(direction=SignalDirection.SELL), context)
        self.assertEqual(outcome.action, "reject")

    def test_different_symbol_is_independent(self):
        clock = _ClockStub()
        signal_filter = CooldownFilter(cooldown_seconds=60.0, clock=clock)
        signal_filter.apply(make_result(), make_context(symbol=SYMBOL))
        outcome = signal_filter.apply(make_result(), make_context(symbol=OTHER_SYMBOL))
        self.assertEqual(outcome.action, "accept")

    def test_zero_cooldown_never_rejects(self):
        clock = _ClockStub()
        signal_filter = CooldownFilter(cooldown_seconds=0.0, clock=clock)
        context = make_context()
        signal_filter.apply(make_result(), context)
        outcome = signal_filter.apply(make_result(), context)
        self.assertEqual(outcome.action, "accept")

    def test_default_clock_is_time_monotonic(self):
        # No clock injected -> should not raise and should behave sanely
        # (accept the very first signal for a fresh key).
        signal_filter = CooldownFilter(cooldown_seconds=1.0)
        outcome = signal_filter.apply(make_result(), make_context())
        self.assertEqual(outcome.action, "accept")

    def test_reset_clears_history(self):
        clock = _ClockStub()
        signal_filter = CooldownFilter(cooldown_seconds=60.0, clock=clock)
        context = make_context()
        signal_filter.apply(make_result(), context)
        signal_filter.reset()
        outcome = signal_filter.apply(make_result(), context)
        self.assertEqual(outcome.action, "accept")

    def test_invalid_input_raises(self):
        with self.assertRaises(SignalValidationError):
            CooldownFilter(cooldown_seconds=1.0).apply(None, make_context())


# ----------------------------------------------------------------------
# ConflictFilter
# ----------------------------------------------------------------------
class TestConflictFilter(unittest.TestCase):
    def test_construction_rejects_out_of_range_dampening(self):
        with self.assertRaises(SignalValidationError):
            ConflictFilter(dampening=1.5)

    def test_first_signal_for_key_is_accepted(self):
        signal_filter = ConflictFilter()
        outcome = signal_filter.apply(make_result(direction=SignalDirection.BUY), make_context())
        self.assertEqual(outcome.action, "accept")

    def test_same_direction_twice_is_accepted(self):
        signal_filter = ConflictFilter()
        context = make_context()
        signal_filter.apply(make_result(direction=SignalDirection.BUY), context)
        outcome = signal_filter.apply(make_result(direction=SignalDirection.BUY), context)
        self.assertEqual(outcome.action, "accept")

    def test_direct_reversal_is_downgraded_to_hold(self):
        signal_filter = ConflictFilter(dampening=0.5)
        context = make_context()
        signal_filter.apply(
            make_result(direction=SignalDirection.SELL, strength=0.8, confidence=0.9), context
        )
        outcome = signal_filter.apply(
            make_result(direction=SignalDirection.BUY, strength=0.6, confidence=0.7), context
        )
        self.assertEqual(outcome.action, "modify")
        self.assertEqual(outcome.result.direction, SignalDirection.HOLD)
        self.assertAlmostEqual(outcome.result.strength, 0.3)
        self.assertAlmostEqual(outcome.result.confidence, 0.35)

    def test_downgraded_result_is_a_new_object(self):
        signal_filter = ConflictFilter()
        context = make_context()
        original = make_result(direction=SignalDirection.SELL)
        signal_filter.apply(original, context)
        conflicting = make_result(direction=SignalDirection.BUY)
        outcome = signal_filter.apply(conflicting, context)
        self.assertIsNot(outcome.result, conflicting)

    def test_hold_after_directional_signal_is_accepted_unchanged(self):
        signal_filter = ConflictFilter()
        context = make_context()
        signal_filter.apply(make_result(direction=SignalDirection.BUY), context)
        outcome = signal_filter.apply(make_result(direction=SignalDirection.HOLD), context)
        self.assertEqual(outcome.action, "accept")

    def test_directional_signal_after_hold_is_accepted(self):
        signal_filter = ConflictFilter()
        context = make_context()
        signal_filter.apply(make_result(direction=SignalDirection.HOLD, strength=0.0), context)
        outcome = signal_filter.apply(make_result(direction=SignalDirection.BUY), context)
        self.assertEqual(outcome.action, "accept")

    def test_standing_direction_persists_through_a_downgrade(self):
        # SELL, then a conflicting BUY (downgraded to HOLD, doesn't
        # update standing direction), then another BUY should still be
        # treated as conflicting with the original SELL.
        signal_filter = ConflictFilter()
        context = make_context()
        signal_filter.apply(make_result(direction=SignalDirection.SELL), context)
        first = signal_filter.apply(make_result(direction=SignalDirection.BUY), context)
        second = signal_filter.apply(make_result(direction=SignalDirection.BUY), context)
        self.assertEqual(first.action, "modify")
        self.assertEqual(second.action, "modify")

    def test_different_symbol_is_independent(self):
        signal_filter = ConflictFilter()
        signal_filter.apply(make_result(direction=SignalDirection.SELL), make_context(symbol=SYMBOL))
        outcome = signal_filter.apply(
            make_result(direction=SignalDirection.BUY), make_context(symbol=OTHER_SYMBOL)
        )
        self.assertEqual(outcome.action, "accept")

    def test_reset_clears_history(self):
        signal_filter = ConflictFilter()
        context = make_context()
        signal_filter.apply(make_result(direction=SignalDirection.SELL), context)
        signal_filter.reset()
        outcome = signal_filter.apply(make_result(direction=SignalDirection.BUY), context)
        self.assertEqual(outcome.action, "accept")

    def test_invalid_input_raises(self):
        with self.assertRaises(SignalValidationError):
            ConflictFilter().apply(make_result(), "not-a-context")


# ----------------------------------------------------------------------
# SignalFilterPipeline
# ----------------------------------------------------------------------
class TestSignalFilterPipeline(unittest.TestCase):
    def test_empty_pipeline_accepts_unchanged(self):
        pipeline = SignalFilterPipeline()
        original = make_result()
        outcome = pipeline.run(original, make_context())
        self.assertIsInstance(outcome, SignalFilterPipelineResult)
        self.assertTrue(outcome.accepted)
        self.assertIs(outcome.result, original)
        self.assertEqual(outcome.trace, [])
        self.assertIsNone(outcome.rejected_by)

    def test_construction_rejects_non_filter_items(self):
        with self.assertRaises(SignalValidationError):
            SignalFilterPipeline(filters=[ConfidenceFilter(), "not-a-filter"])

    def test_all_filters_pass_produces_accepted_result_with_trace(self):
        pipeline = SignalFilterPipeline(
            filters=[ConfidenceFilter(min_confidence=0.1), DuplicateSignalFilter()]
        )
        outcome = pipeline.run(make_result(confidence=0.9), make_context())
        self.assertTrue(outcome.accepted)
        self.assertEqual(len(outcome.trace), 2)
        self.assertEqual(outcome.trace[0]["action"], "accept")
        self.assertEqual(outcome.trace[1]["action"], "accept")
        self.assertEqual(
            outcome.result.metadata["filter_pipeline_trace"], outcome.trace
        )

    def test_rejection_short_circuits_remaining_filters(self):
        rejecting = ConfidenceFilter(min_confidence=0.9)
        never_run = ConfidenceFilter(min_confidence=0.0, name="NeverRun")
        pipeline = SignalFilterPipeline(filters=[rejecting, never_run])

        outcome = pipeline.run(make_result(confidence=0.2), make_context())

        self.assertFalse(outcome.accepted)
        self.assertIsNone(outcome.result)
        self.assertEqual(outcome.rejected_by, "ConfidenceFilter")
        self.assertEqual(len(outcome.trace), 1)

    def test_modification_flows_into_subsequent_filters(self):
        # ConflictFilter downgrades BUY -> HOLD; a subsequent
        # ConfidenceFilter must see the *downgraded* (lower) confidence,
        # proving filters run sequentially against the evolving result.
        context = make_context()
        conflict = ConflictFilter(dampening=0.1)
        confidence = ConfidenceFilter(min_confidence=0.5)
        pipeline = SignalFilterPipeline(filters=[conflict, confidence])

        # Seed a standing SELL direction directly on the ConflictFilter.
        conflict.apply(make_result(direction=SignalDirection.SELL, confidence=0.9), context)

        outcome = pipeline.run(
            make_result(direction=SignalDirection.BUY, confidence=0.9), context
        )

        self.assertFalse(outcome.accepted)
        self.assertEqual(outcome.rejected_by, "ConfidenceFilter")
        self.assertEqual(outcome.trace[0]["action"], "modify")
        self.assertEqual(outcome.trace[1]["action"], "reject")

    def test_pipeline_reset_resets_every_stateful_filter(self):
        duplicate = DuplicateSignalFilter()
        pipeline = SignalFilterPipeline(filters=[duplicate])
        context = make_context()

        pipeline.run(make_result(), context)
        pipeline.reset()
        outcome = pipeline.run(make_result(), context)

        self.assertTrue(outcome.accepted)

    def test_invalid_input_raises(self):
        pipeline = SignalFilterPipeline(filters=[ConfidenceFilter()])
        with self.assertRaises(SignalValidationError):
            pipeline.run("not-a-result", make_context())
        with self.assertRaises(SignalValidationError):
            pipeline.run(make_result(), "not-a-context")

    def test_default_name_is_class_name(self):
        self.assertEqual(SignalFilterPipeline().name, "SignalFilterPipeline")

    def test_repr_contains_filters(self):
        pipeline = SignalFilterPipeline(filters=[ConfidenceFilter(name="conf")])
        self.assertIn("conf", repr(pipeline))


# ----------------------------------------------------------------------
# End-to-end: all four filters combined
# ----------------------------------------------------------------------
class TestFullPipelineIntegration(unittest.TestCase):
    def test_realistic_pipeline_combining_all_four_filters(self):
        clock = _ClockStub()
        pipeline = SignalFilterPipeline(
            filters=[
                ConfidenceFilter(min_confidence=0.4),
                DuplicateSignalFilter(),
                CooldownFilter(cooldown_seconds=30.0, clock=clock),
                ConflictFilter(dampening=0.5),
            ]
        )
        context = make_context()

        # 1) A solid bullish signal: passes every filter.
        first = pipeline.run(
            make_result(direction=SignalDirection.BUY, strength=0.7, confidence=0.8), context
        )
        self.assertTrue(first.accepted)
        self.assertEqual(first.result.direction, SignalDirection.BUY)

        # 2) Immediate identical repeat: caught by DuplicateSignalFilter
        #    before cooldown/conflict even get a chance to run.
        clock.advance(31.0)  # clear the cooldown window first
        second = pipeline.run(
            make_result(direction=SignalDirection.BUY, strength=0.7, confidence=0.8), context
        )
        self.assertFalse(second.accepted)
        self.assertEqual(second.rejected_by, "DuplicateSignalFilter")

        # 3) A different, low-confidence signal within the cooldown
        #    window: caught by ConfidenceFilter first (it runs before
        #    CooldownFilter in this pipeline).
        third = pipeline.run(
            make_result(direction=SignalDirection.SELL, strength=0.5, confidence=0.1), context
        )
        self.assertFalse(third.accepted)
        self.assertEqual(third.rejected_by, "ConfidenceFilter")

        # 4) A different, high-confidence bearish signal after the
        #    cooldown window: passes Confidence/Duplicate, updates
        #    Cooldown, and conflicts with the standing BUY direction ->
        #    downgraded to HOLD by ConflictFilter.
        clock.advance(31.0)
        fourth = pipeline.run(
            make_result(direction=SignalDirection.SELL, strength=0.6, confidence=0.9), context
        )
        self.assertTrue(fourth.accepted)
        self.assertEqual(fourth.result.direction, SignalDirection.HOLD)
        self.assertEqual(fourth.trace[-1]["action"], "modify")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
