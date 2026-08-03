"""
test_signal_validation.py
--------------------------
Purpose:
    Unit tests for the Signal Engine Part 5 module: `signals.validation`
    (`ValidationRule`, `RuleOutcome`, `SummaryContentRule`,
    `RangeConsistencyRule`, `DirectionStrengthConsistencyRule`,
    `ConfidenceThresholdRule`, `MetadataPresenceRule`,
    `SignalValidationPipeline`, `SignalValidationReport`,
    `SignalValidator`).

Mirrors the local-factory / assertion style already used by
`tests/test_signal_filters.py` (Part 4) and earlier Signal Engine test
files, all left untouched by this change. Each rule is tested in
isolation first (pass/warn/error paths, invalid-input handling), then
`SignalValidationPipeline` is tested for sequencing (no short-circuit),
configurable reordering, and report composition, then `SignalValidator`
is tested as the facade (default rule set, custom rules/pipeline,
metadata annotation).

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
from signals.validation import (
    ConfidenceThresholdRule,
    DirectionStrengthConsistencyRule,
    MetadataPresenceRule,
    RangeConsistencyRule,
    RuleOutcome,
    SignalValidationPipeline,
    SignalValidationReport,
    SignalValidator,
    SummaryContentRule,
    ValidationRule,
)

SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"


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
    summary: str = "Bullish technical signal detected.",
    metadata: dict | None = None,
) -> SignalResult:
    return SignalResult(
        direction=direction,
        strength=strength,
        confidence=confidence,
        summary=summary,
        metadata=metadata if metadata is not None else {"source": "test"},
    )


class _MinimalRule(ValidationRule):
    """Minimal concrete ValidationRule for exercising the shared base class."""

    def __init__(self, outcome_kind: str = "pass", *, name=None):
        super().__init__(name=name)
        self.outcome_kind = outcome_kind
        self.evaluate_calls = 0

    def evaluate(self, result: SignalResult, context: SignalContext) -> RuleOutcome:
        self._validate_inputs(result, context)
        self.evaluate_calls += 1
        if self.outcome_kind == "pass":
            return self._pass(message="ok")
        if self.outcome_kind == "warn":
            return self._warn(message="warning finding")
        return self._fail(message="error finding")


# ----------------------------------------------------------------------
# RuleOutcome
# ----------------------------------------------------------------------
class TestRuleOutcome(unittest.TestCase):
    def test_pass_outcome_requires_no_severity(self):
        outcome = RuleOutcome(rule_name="R", passed=True, severity=None, message="fine")
        self.assertTrue(outcome.passed)
        self.assertIsNone(outcome.severity)

    def test_pass_outcome_rejects_severity(self):
        with self.assertRaises(SignalValidationError):
            RuleOutcome(rule_name="R", passed=True, severity="warning", message="fine")

    def test_fail_outcome_requires_valid_severity(self):
        with self.assertRaises(SignalValidationError):
            RuleOutcome(rule_name="R", passed=False, severity=None, message="bad")
        with self.assertRaises(SignalValidationError):
            RuleOutcome(rule_name="R", passed=False, severity="critical", message="bad")

    def test_message_must_be_non_empty(self):
        with self.assertRaises(SignalValidationError):
            RuleOutcome(rule_name="R", passed=True, severity=None, message="   ")

    def test_as_trace_entry(self):
        outcome = RuleOutcome(rule_name="R", passed=False, severity="error", message="bad")
        entry = outcome.as_trace_entry()
        self.assertEqual(entry, {"rule": "R", "passed": False, "severity": "error", "message": "bad"})


# ----------------------------------------------------------------------
# ValidationRule (base class, via _MinimalRule)
# ----------------------------------------------------------------------
class TestValidationRuleBase(unittest.TestCase):
    def setUp(self):
        self.context = make_context()
        self.result = make_result()

    def test_default_name_is_class_name(self):
        rule = _MinimalRule()
        self.assertEqual(rule.name, "_MinimalRule")

    def test_custom_name(self):
        rule = _MinimalRule(name="custom")
        self.assertEqual(rule.name, "custom")

    def test_pass_helper(self):
        rule = _MinimalRule("pass")
        outcome = rule.evaluate(self.result, self.context)
        self.assertTrue(outcome.passed)
        self.assertIsNone(outcome.severity)

    def test_warn_helper(self):
        rule = _MinimalRule("warn")
        outcome = rule.evaluate(self.result, self.context)
        self.assertFalse(outcome.passed)
        self.assertEqual(outcome.severity, "warning")

    def test_fail_helper(self):
        rule = _MinimalRule("fail")
        outcome = rule.evaluate(self.result, self.context)
        self.assertFalse(outcome.passed)
        self.assertEqual(outcome.severity, "error")

    def test_invalid_result_type_raises(self):
        rule = _MinimalRule()
        with self.assertRaises(SignalValidationError):
            rule.evaluate("not a result", self.context)

    def test_invalid_context_type_raises(self):
        rule = _MinimalRule()
        with self.assertRaises(SignalValidationError):
            rule.evaluate(self.result, "not a context")

    def test_reset_is_noop_by_default(self):
        rule = _MinimalRule()
        self.assertIsNone(rule.reset())

    def test_repr(self):
        rule = _MinimalRule(name="r1")
        self.assertIn("r1", repr(rule))


# ----------------------------------------------------------------------
# SummaryContentRule
# ----------------------------------------------------------------------
class TestSummaryContentRule(unittest.TestCase):
    def setUp(self):
        self.context = make_context()

    def test_adequate_summary_passes(self):
        rule = SummaryContentRule()
        result = make_result(summary="A perfectly adequate summary of the signal.")
        outcome = rule.evaluate(result, self.context)
        self.assertTrue(outcome.passed)

    def test_short_summary_warns(self):
        rule = SummaryContentRule(min_length=20)
        result = make_result(summary="short")
        outcome = rule.evaluate(result, self.context)
        self.assertFalse(outcome.passed)
        self.assertEqual(outcome.severity, "warning")

    def test_blank_summary_is_defensive_error(self):
        # SignalResult itself disallows a blank summary, so construct a
        # valid result then bypass immutability to simulate a
        # maliciously/incorrectly constructed object reaching the rule.
        rule = SummaryContentRule()
        result = make_result(summary="valid for now")
        object.__setattr__(result, "summary", "   ")
        outcome = rule.evaluate(result, self.context)
        self.assertFalse(outcome.passed)
        self.assertEqual(outcome.severity, "error")

    def test_invalid_min_length_raises(self):
        with self.assertRaises(SignalValidationError):
            SummaryContentRule(min_length=-1)
        with self.assertRaises(SignalValidationError):
            SummaryContentRule(min_length=1.5)


# ----------------------------------------------------------------------
# RangeConsistencyRule
# ----------------------------------------------------------------------
class TestRangeConsistencyRule(unittest.TestCase):
    def setUp(self):
        self.context = make_context()
        self.rule = RangeConsistencyRule()

    def test_normal_values_pass(self):
        result = make_result(strength=0.5, confidence=0.5)
        outcome = self.rule.evaluate(result, self.context)
        self.assertTrue(outcome.passed)

    def test_zero_confidence_warns(self):
        result = make_result(direction=SignalDirection.HOLD, strength=0.0, confidence=0.0)
        outcome = self.rule.evaluate(result, self.context)
        self.assertFalse(outcome.passed)
        self.assertEqual(outcome.severity, "warning")

    def test_out_of_range_strength_is_defensive_error(self):
        result = make_result(strength=0.5)
        object.__setattr__(result, "strength", 1.5)
        outcome = self.rule.evaluate(result, self.context)
        self.assertFalse(outcome.passed)
        self.assertEqual(outcome.severity, "error")

    def test_non_numeric_confidence_is_defensive_error(self):
        result = make_result()
        object.__setattr__(result, "confidence", "high")
        outcome = self.rule.evaluate(result, self.context)
        self.assertFalse(outcome.passed)
        self.assertEqual(outcome.severity, "error")


# ----------------------------------------------------------------------
# DirectionStrengthConsistencyRule
# ----------------------------------------------------------------------
class TestDirectionStrengthConsistencyRule(unittest.TestCase):
    def setUp(self):
        self.context = make_context()
        self.rule = DirectionStrengthConsistencyRule()

    def test_directional_signal_with_strength_passes(self):
        result = make_result(direction=SignalDirection.BUY, strength=0.6)
        outcome = self.rule.evaluate(result, self.context)
        self.assertTrue(outcome.passed)

    def test_buy_with_zero_strength_errors(self):
        result = make_result(direction=SignalDirection.BUY, strength=0.0)
        outcome = self.rule.evaluate(result, self.context)
        self.assertFalse(outcome.passed)
        self.assertEqual(outcome.severity, "error")

    def test_sell_with_zero_strength_errors(self):
        result = make_result(direction=SignalDirection.SELL, strength=0.0)
        outcome = self.rule.evaluate(result, self.context)
        self.assertFalse(outcome.passed)
        self.assertEqual(outcome.severity, "error")

    def test_hold_with_low_strength_passes(self):
        result = make_result(direction=SignalDirection.HOLD, strength=0.1)
        outcome = self.rule.evaluate(result, self.context)
        self.assertTrue(outcome.passed)

    def test_hold_with_high_strength_warns(self):
        result = make_result(direction=SignalDirection.HOLD, strength=0.9)
        outcome = self.rule.evaluate(result, self.context)
        self.assertFalse(outcome.passed)
        self.assertEqual(outcome.severity, "warning")

    def test_hold_threshold_is_configurable(self):
        rule = DirectionStrengthConsistencyRule(hold_strength_warn_threshold=0.1)
        result = make_result(direction=SignalDirection.HOLD, strength=0.2)
        outcome = rule.evaluate(result, self.context)
        self.assertFalse(outcome.passed)
        self.assertEqual(outcome.severity, "warning")

    def test_invalid_threshold_raises(self):
        with self.assertRaises(SignalValidationError):
            DirectionStrengthConsistencyRule(hold_strength_warn_threshold=1.5)


# ----------------------------------------------------------------------
# ConfidenceThresholdRule
# ----------------------------------------------------------------------
class TestConfidenceThresholdRule(unittest.TestCase):
    def setUp(self):
        self.context = make_context()

    def test_confidence_at_or_above_minimum_passes(self):
        rule = ConfidenceThresholdRule(min_confidence=0.3)
        result = make_result(confidence=0.3)
        outcome = rule.evaluate(result, self.context)
        self.assertTrue(outcome.passed)

    def test_confidence_below_minimum_warns(self):
        rule = ConfidenceThresholdRule(min_confidence=0.5)
        result = make_result(confidence=0.2)
        outcome = rule.evaluate(result, self.context)
        self.assertFalse(outcome.passed)
        self.assertEqual(outcome.severity, "warning")

    def test_never_errors(self):
        rule = ConfidenceThresholdRule(min_confidence=0.9)
        result = make_result(confidence=0.0)
        outcome = rule.evaluate(result, self.context)
        self.assertEqual(outcome.severity, "warning")

    def test_invalid_min_confidence_raises(self):
        with self.assertRaises(SignalValidationError):
            ConfidenceThresholdRule(min_confidence=1.1)
        with self.assertRaises(SignalValidationError):
            ConfidenceThresholdRule(min_confidence=-0.1)


# ----------------------------------------------------------------------
# MetadataPresenceRule
# ----------------------------------------------------------------------
class TestMetadataPresenceRule(unittest.TestCase):
    def setUp(self):
        self.context = make_context()
        self.rule = MetadataPresenceRule()

    def test_non_empty_metadata_passes(self):
        result = make_result(metadata={"source": "test"})
        outcome = self.rule.evaluate(result, self.context)
        self.assertTrue(outcome.passed)

    def test_empty_metadata_warns(self):
        result = make_result(metadata={})
        outcome = self.rule.evaluate(result, self.context)
        self.assertFalse(outcome.passed)
        self.assertEqual(outcome.severity, "warning")


# ----------------------------------------------------------------------
# SignalValidationPipeline
# ----------------------------------------------------------------------
class TestSignalValidationPipeline(unittest.TestCase):
    def setUp(self):
        self.context = make_context()

    def test_empty_pipeline_is_valid_with_empty_trace(self):
        pipeline = SignalValidationPipeline([])
        report = pipeline.run(make_result(), self.context)
        self.assertTrue(report.is_valid)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])
        self.assertEqual(report.trace, [])

    def test_all_rules_always_run_no_short_circuit(self):
        rule_a = _MinimalRule("fail", name="a")
        rule_b = _MinimalRule("warn", name="b")
        rule_c = _MinimalRule("pass", name="c")
        pipeline = SignalValidationPipeline([rule_a, rule_b, rule_c])

        report = pipeline.run(make_result(), self.context)

        self.assertEqual(rule_a.evaluate_calls, 1)
        self.assertEqual(rule_b.evaluate_calls, 1)
        self.assertEqual(rule_c.evaluate_calls, 1)
        self.assertEqual(len(report.trace), 3)

    def test_errors_and_warnings_collected_separately(self):
        rule_a = _MinimalRule("fail", name="a")
        rule_b = _MinimalRule("warn", name="b")
        pipeline = SignalValidationPipeline([rule_a, rule_b])

        report = pipeline.run(make_result(), self.context)

        self.assertFalse(report.is_valid)
        self.assertEqual(report.errors, ["error finding"])
        self.assertEqual(report.warnings, ["warning finding"])

    def test_warnings_only_do_not_invalidate(self):
        rule_b = _MinimalRule("warn", name="b")
        pipeline = SignalValidationPipeline([rule_b])

        report = pipeline.run(make_result(), self.context)

        self.assertTrue(report.is_valid)
        self.assertEqual(report.warnings, ["warning finding"])

    def test_trace_order_matches_rule_order(self):
        rule_a = _MinimalRule("pass", name="a")
        rule_b = _MinimalRule("warn", name="b")
        pipeline = SignalValidationPipeline([rule_a, rule_b])

        report = pipeline.run(make_result(), self.context)

        self.assertEqual([entry["rule"] for entry in report.trace], ["a", "b"])

    def test_reorder_changes_execution_order(self):
        rule_a = _MinimalRule("pass", name="a")
        rule_b = _MinimalRule("pass", name="b")
        pipeline = SignalValidationPipeline([rule_a, rule_b])

        pipeline.reorder(["b", "a"])
        report = pipeline.run(make_result(), self.context)

        self.assertEqual([entry["rule"] for entry in report.trace], ["b", "a"])

    def test_reorder_rejects_missing_or_extra_names(self):
        rule_a = _MinimalRule("pass", name="a")
        rule_b = _MinimalRule("pass", name="b")
        pipeline = SignalValidationPipeline([rule_a, rule_b])

        with self.assertRaises(SignalValidationError):
            pipeline.reorder(["a"])
        with self.assertRaises(SignalValidationError):
            pipeline.reorder(["a", "b", "c"])
        with self.assertRaises(SignalValidationError):
            pipeline.reorder(["a", "a"])

    def test_duplicate_rule_names_rejected_at_construction(self):
        with self.assertRaises(SignalValidationError):
            SignalValidationPipeline(
                [_MinimalRule("pass", name="dup"), _MinimalRule("pass", name="dup")]
            )

    def test_non_rule_item_rejected(self):
        with self.assertRaises(SignalValidationError):
            SignalValidationPipeline([object()])

    def test_invalid_result_or_context_raises(self):
        pipeline = SignalValidationPipeline([_MinimalRule()])
        with self.assertRaises(SignalValidationError):
            pipeline.run("not a result", self.context)
        with self.assertRaises(SignalValidationError):
            pipeline.run(make_result(), "not a context")

    def test_reset_resets_every_rule(self):
        class _StatefulRule(_MinimalRule):
            def __init__(self, name=None):
                super().__init__("pass", name=name)
                self.was_reset = False

            def reset(self):
                self.was_reset = True

        rule = _StatefulRule(name="stateful")
        pipeline = SignalValidationPipeline([rule])
        pipeline.reset()
        self.assertTrue(rule.was_reset)

    def test_repr(self):
        pipeline = SignalValidationPipeline([], name="my_pipeline")
        self.assertIn("my_pipeline", repr(pipeline))


# ----------------------------------------------------------------------
# SignalValidationReport
# ----------------------------------------------------------------------
class TestSignalValidationReport(unittest.TestCase):
    def test_as_metadata_shape(self):
        report = SignalValidationReport(
            is_valid=False,
            errors=["e1"],
            warnings=["w1"],
            trace=[{"rule": "a", "passed": False, "severity": "error", "message": "e1"}],
        )
        meta = report.as_metadata()
        self.assertEqual(
            meta,
            {
                "is_valid": False,
                "errors": ["e1"],
                "warnings": ["w1"],
                "trace": [{"rule": "a", "passed": False, "severity": "error", "message": "e1"}],
            },
        )

    def test_as_metadata_returns_copies(self):
        report = SignalValidationReport(is_valid=True, errors=[], warnings=[], trace=[])
        meta = report.as_metadata()
        meta["errors"].append("mutated")
        self.assertEqual(report.errors, [])


# ----------------------------------------------------------------------
# SignalValidator
# ----------------------------------------------------------------------
class TestSignalValidator(unittest.TestCase):
    def setUp(self):
        self.context = make_context()

    def test_default_rule_set_flags_low_quality_signal(self):
        validator = SignalValidator()
        result = make_result(
            direction=SignalDirection.HOLD,
            strength=0.0,
            confidence=0.1,
            summary="ok",
            metadata={},
        )
        report = validator.validate(result, self.context)
        # confidence below default 0.3 threshold, empty metadata, short
        # summary -> at least these warnings should surface.
        self.assertFalse(report.is_valid is False and len(report.errors) == 0)
        self.assertTrue(report.is_valid)  # only warnings for this input
        self.assertGreaterEqual(len(report.warnings), 2)

    def test_default_rule_set_flags_directional_zero_strength_as_error(self):
        validator = SignalValidator()
        result = make_result(direction=SignalDirection.BUY, strength=0.0, confidence=0.6)
        report = validator.validate(result, self.context)
        self.assertFalse(report.is_valid)
        self.assertTrue(any("strength" in e for e in report.errors))

    def test_healthy_signal_is_valid_with_no_warnings(self):
        validator = SignalValidator()
        result = make_result(
            direction=SignalDirection.BUY,
            strength=0.7,
            confidence=0.8,
            summary="Strong bullish technical signal with high conviction.",
            metadata={"source_analyzer": "AnalysisAggregator", "source_score": 0.65},
        )
        report = validator.validate(result, self.context)
        self.assertTrue(report.is_valid)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_custom_rules_are_used_instead_of_defaults(self):
        rule = _MinimalRule("fail", name="only_rule")
        validator = SignalValidator(rules=[rule])
        report = validator.validate(make_result(), self.context)
        self.assertEqual(len(report.trace), 1)
        self.assertEqual(report.trace[0]["rule"], "only_rule")

    def test_custom_pipeline_takes_precedence_over_rules(self):
        pipeline_rule = _MinimalRule("pass", name="pipeline_rule")
        ignored_rule = _MinimalRule("fail", name="ignored")
        pipeline = SignalValidationPipeline([pipeline_rule])
        validator = SignalValidator(rules=[ignored_rule], pipeline=pipeline)

        report = validator.validate(make_result(), self.context)

        self.assertEqual([entry["rule"] for entry in report.trace], ["pipeline_rule"])

    def test_validate_and_annotate_merges_metadata_without_mutating_original(self):
        validator = SignalValidator()
        original = make_result(
            direction=SignalDirection.BUY, strength=0.7, confidence=0.8, metadata={"k": "v"}
        )
        annotated = validator.validate_and_annotate(original, self.context)

        self.assertIsNot(annotated, original)
        self.assertNotIn("signal_validation", original.metadata)
        self.assertIn("signal_validation", annotated.metadata)
        self.assertIn("k", annotated.metadata)
        self.assertIn("is_valid", annotated.metadata["signal_validation"])
        self.assertIn("errors", annotated.metadata["signal_validation"])
        self.assertIn("warnings", annotated.metadata["signal_validation"])
        self.assertIn("trace", annotated.metadata["signal_validation"])

    def test_validate_and_annotate_never_raises_for_invalid_signal(self):
        # Even a signal that fails validation (errors present) is still
        # annotated and returned -- SignalValidator never rejects.
        validator = SignalValidator()
        result = make_result(direction=SignalDirection.SELL, strength=0.0, confidence=0.9)
        annotated = validator.validate_and_annotate(result, self.context)
        self.assertFalse(annotated.metadata["signal_validation"]["is_valid"])

    def test_reset_delegates_to_pipeline(self):
        class _StatefulRule(_MinimalRule):
            def __init__(self, name=None):
                super().__init__("pass", name=name)
                self.was_reset = False

            def reset(self):
                self.was_reset = True

        rule = _StatefulRule(name="stateful")
        validator = SignalValidator(rules=[rule])
        validator.reset()
        self.assertTrue(rule.was_reset)

    def test_default_name_and_repr(self):
        validator = SignalValidator()
        self.assertEqual(validator.name, "SignalValidator")
        self.assertIn("SignalValidator", repr(validator))


# ----------------------------------------------------------------------
# End-to-end integration
# ----------------------------------------------------------------------
class TestSignalValidationIntegration(unittest.TestCase):
    """
    Exercises the full Signal Engine chain up through validation: a
    hand-built `SignalResult` (standing in for one produced by
    `TechnicalSignalGenerator`/`SignalAggregator` and possibly filtered
    by `SignalFilterPipeline`) run through a real `SignalValidator`
    with its default rule set, mirroring how a future `strategies/`
    consumer might use this module without deciding anything itself.
    """

    def test_full_chain_default_rules_on_realistic_signal(self):
        context = make_context(symbol="ETHUSDT", timeframe="4h")
        result = SignalResult(
            direction=SignalDirection.SELL,
            strength=0.42,
            confidence=0.55,
            summary="Bearish technical signal: trend and momentum both negative.",
            metadata={
                "source_analyzer": "AnalysisAggregator",
                "source_score": -0.35,
                "source_confidence": 0.55,
                "filter_pipeline_trace": [
                    {"filter": "ConfidenceFilter", "action": "accept", "reason": "ok"}
                ],
            },
        )

        validator = SignalValidator()
        report = validator.validate(result, context)
        annotated = validator.validate_and_annotate(result, context)

        self.assertTrue(report.is_valid)
        self.assertEqual(report.errors, [])
        # original filter trace preserved alongside new validation metadata
        self.assertIn("filter_pipeline_trace", annotated.metadata)
        self.assertIn("signal_validation", annotated.metadata)
        self.assertEqual(annotated.metadata["signal_validation"]["is_valid"], True)

    def test_reordering_rules_does_not_change_findings_only_trace_order(self):
        context = make_context()
        result = make_result(direction=SignalDirection.HOLD, strength=0.9, confidence=0.9)
        validator = SignalValidator()

        report_before = validator.validate(result, context)
        order_before = [entry["rule"] for entry in report_before.trace]

        reversed_order = list(reversed(order_before))
        validator.pipeline.reorder(reversed_order)
        report_after = validator.validate(result, context)
        order_after = [entry["rule"] for entry in report_after.trace]

        self.assertEqual(order_after, reversed_order)
        self.assertEqual(sorted(report_before.warnings), sorted(report_after.warnings))
        self.assertEqual(report_before.is_valid, report_after.is_valid)


if __name__ == "__main__":
    unittest.main()
