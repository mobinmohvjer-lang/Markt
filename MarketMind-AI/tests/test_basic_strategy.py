"""
test_basic_strategy.py
-------------------------
Purpose:
    Unit tests for `BasicStrategy` (Strategy Engine Part 2), the first
    concrete `strategies.base_strategy.BaseStrategy` implementation.
    Complements `tests/test_strategies.py`, which covers the Part 1
    foundation (`StrategyResult`, `StrategyContext`, `BaseStrategy`,
    exceptions, utils) and is left untouched here.

Uses the standard-library ``unittest`` framework, matching every other
test file in this suite (no external test-runner dependency).

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from analysis.result import AnalysisResult
from core.enums import SignalDirection
from signals.result import SignalResult
from strategies import BasicStrategy, InsufficientStrategyDataError, StrategyContext
from strategies.exceptions import StrategyConfigurationError
from strategies.risk_management.result import RiskResult

NOW = datetime.now(timezone.utc)


def make_analysis_result(
    *, analyzer_name: str = "AnalysisAggregator", score: float = 0.6, confidence: float = 0.8
) -> AnalysisResult:
    return AnalysisResult(
        analyzer_name=analyzer_name,
        symbol="BTCUSDT",
        timeframe="1h",
        score=score,
        confidence=confidence,
        summary="Bullish confluence across trend/momentum",
        timestamp=NOW,
    )


def make_signal_result(
    *,
    direction: SignalDirection = SignalDirection.BUY,
    strength: float = 0.7,
    confidence: float = 0.8,
) -> SignalResult:
    return SignalResult(
        direction=direction,
        strength=strength,
        confidence=confidence,
        summary="Technical signal generator produced a signal",
    )


def make_risk_result(*, approved: bool = True, risk_score: float = 0.2) -> RiskResult:
    return RiskResult(
        approved=approved,
        risk_score=risk_score,
        confidence=0.75,
        summary="Signal within acceptable risk tolerance",
    )


def make_context(
    *,
    analysis_results=None,
    signal_result=None,
    risk_result=None,
) -> StrategyContext:
    return StrategyContext(
        symbol="BTCUSDT",
        timeframe="1h",
        analysis_results=analysis_results if analysis_results is not None else [make_analysis_result()],
        signal_result=signal_result,
        risk_result=risk_result,
    )


# ----------------------------------------------------------------------
# Construction / configuration validation
# ----------------------------------------------------------------------
class TestConstruction(unittest.TestCase):
    def test_default_construction(self):
        strategy = BasicStrategy()
        self.assertEqual(strategy.name, "BasicStrategy")
        self.assertEqual(strategy.analysis_analyzer_name, "AnalysisAggregator")
        self.assertAlmostEqual(strategy.buy_threshold, 0.2)
        self.assertAlmostEqual(strategy.sell_threshold, -0.2)

    def test_custom_name(self):
        strategy = BasicStrategy(name="MyBasicStrategy")
        self.assertEqual(strategy.name, "MyBasicStrategy")

    def test_rejects_empty_analyzer_name(self):
        with self.assertRaises(StrategyConfigurationError):
            BasicStrategy(analysis_analyzer_name="   ")

    def test_rejects_non_string_analyzer_name(self):
        with self.assertRaises(StrategyConfigurationError):
            BasicStrategy(analysis_analyzer_name=123)

    def test_rejects_buy_threshold_out_of_range(self):
        with self.assertRaises(StrategyConfigurationError):
            BasicStrategy(buy_threshold=0.0)
        with self.assertRaises(StrategyConfigurationError):
            BasicStrategy(buy_threshold=1.5)

    def test_rejects_sell_threshold_out_of_range(self):
        with self.assertRaises(StrategyConfigurationError):
            BasicStrategy(sell_threshold=0.0)
        with self.assertRaises(StrategyConfigurationError):
            BasicStrategy(sell_threshold=-1.5)

    def test_rejects_non_numeric_threshold(self):
        with self.assertRaises(StrategyConfigurationError):
            BasicStrategy(buy_threshold="high")

    def test_rejects_negative_weight(self):
        with self.assertRaises(StrategyConfigurationError):
            BasicStrategy(analysis_weight=-0.1)
        with self.assertRaises(StrategyConfigurationError):
            BasicStrategy(signal_weight=-0.1)

    def test_rejects_non_numeric_weight(self):
        with self.assertRaises(StrategyConfigurationError):
            BasicStrategy(analysis_weight="lots")

    def test_zero_weight_allowed(self):
        # Zero is a valid (if degenerate) weight -- must not raise.
        strategy = BasicStrategy(signal_weight=0.0)
        self.assertEqual(strategy.signal_weight, 0.0)


# ----------------------------------------------------------------------
# Required input handling
# ----------------------------------------------------------------------
class TestRequiredInputs(unittest.TestCase):
    def test_raises_when_no_matching_analysis_result(self):
        strategy = BasicStrategy()
        context = make_context(analysis_results=[])
        with self.assertRaises(InsufficientStrategyDataError):
            strategy.decide(context)

    def test_raises_when_analyzer_name_does_not_match(self):
        strategy = BasicStrategy(analysis_analyzer_name="AnalysisAggregator")
        context = make_context(analysis_results=[make_analysis_result(analyzer_name="TrendAnalyzer")])
        with self.assertRaises(InsufficientStrategyDataError):
            strategy.decide(context)

    def test_custom_analyzer_name_is_used(self):
        strategy = BasicStrategy(analysis_analyzer_name="TrendAnalyzer")
        context = make_context(analysis_results=[make_analysis_result(analyzer_name="TrendAnalyzer")])
        result = strategy.decide(context)
        self.assertIsInstance(result.action, SignalDirection)

    def test_decide_rejects_non_context(self):
        strategy = BasicStrategy()
        with self.assertRaises(Exception):
            strategy.decide("not a context")


# ----------------------------------------------------------------------
# Directional decisions from analysis alone
# ----------------------------------------------------------------------
class TestAnalysisOnlyDecisions(unittest.TestCase):
    def test_strong_bullish_analysis_produces_buy(self):
        strategy = BasicStrategy()
        context = make_context(analysis_results=[make_analysis_result(score=0.8, confidence=0.9)])
        result = strategy.decide(context)
        self.assertEqual(result.action, SignalDirection.BUY)

    def test_strong_bearish_analysis_produces_sell(self):
        strategy = BasicStrategy()
        context = make_context(analysis_results=[make_analysis_result(score=-0.8, confidence=0.9)])
        result = strategy.decide(context)
        self.assertEqual(result.action, SignalDirection.SELL)

    def test_neutral_analysis_produces_hold(self):
        strategy = BasicStrategy()
        context = make_context(analysis_results=[make_analysis_result(score=0.05, confidence=0.9)])
        result = strategy.decide(context)
        self.assertEqual(result.action, SignalDirection.HOLD)

    def test_missing_signal_and_risk_lowers_confidence_but_does_not_raise(self):
        strategy = BasicStrategy()
        context = make_context(analysis_results=[make_analysis_result(score=0.8, confidence=1.0)])
        result = strategy.decide(context)
        # completeness = 1/3 (only analysis available)
        self.assertAlmostEqual(result.confidence, 1.0 * 1.0 * (1 / 3), places=6)
        self.assertFalse(result.metadata["inputs_available"]["signal"])
        self.assertFalse(result.metadata["inputs_available"]["risk"])


# ----------------------------------------------------------------------
# Consistency between Analysis / Signal / Risk
# ----------------------------------------------------------------------
class TestConsistency(unittest.TestCase):
    def test_agreeing_analysis_and_signal_full_consistency(self):
        strategy = BasicStrategy()
        context = make_context(
            analysis_results=[make_analysis_result(score=0.6, confidence=0.8)],
            signal_result=make_signal_result(direction=SignalDirection.BUY, strength=0.7),
        )
        result = strategy.decide(context)
        self.assertEqual(result.action, SignalDirection.BUY)
        self.assertAlmostEqual(result.metadata["consistency"]["analysis_signal_agreement"], 1.0)

    def test_conflicting_analysis_and_signal_zero_agreement(self):
        strategy = BasicStrategy()
        context = make_context(
            analysis_results=[make_analysis_result(score=0.6, confidence=0.8)],
            signal_result=make_signal_result(direction=SignalDirection.SELL, strength=0.7),
        )
        result = strategy.decide(context)
        self.assertAlmostEqual(result.metadata["consistency"]["analysis_signal_agreement"], 0.0)

    def test_hold_signal_partial_agreement_with_directional_analysis(self):
        strategy = BasicStrategy()
        context = make_context(
            analysis_results=[make_analysis_result(score=0.6, confidence=0.8)],
            signal_result=make_signal_result(direction=SignalDirection.HOLD, strength=0.0),
        )
        result = strategy.decide(context)
        self.assertAlmostEqual(result.metadata["consistency"]["analysis_signal_agreement"], 0.5)

    def test_risk_approved_and_directional_action_full_alignment(self):
        strategy = BasicStrategy()
        context = make_context(
            analysis_results=[make_analysis_result(score=0.6, confidence=0.8)],
            signal_result=make_signal_result(direction=SignalDirection.BUY),
            risk_result=make_risk_result(approved=True),
        )
        result = strategy.decide(context)
        self.assertEqual(result.metadata["consistency"]["risk_alignment"], 1.0)
        self.assertFalse(result.metadata["risk_override"])

    def test_no_signal_or_risk_treated_as_fully_consistent(self):
        strategy = BasicStrategy()
        context = make_context(analysis_results=[make_analysis_result(score=0.6, confidence=0.8)])
        result = strategy.decide(context)
        self.assertEqual(result.metadata["consistency"]["consistency_score"], 1.0)


# ----------------------------------------------------------------------
# Risk gate
# ----------------------------------------------------------------------
class TestRiskGate(unittest.TestCase):
    def test_unapproved_risk_downgrades_buy_to_hold(self):
        strategy = BasicStrategy()
        context = make_context(
            analysis_results=[make_analysis_result(score=0.8, confidence=0.9)],
            signal_result=make_signal_result(direction=SignalDirection.BUY, strength=0.8),
            risk_result=make_risk_result(approved=False),
        )
        result = strategy.decide(context)
        self.assertEqual(result.action, SignalDirection.HOLD)
        self.assertTrue(result.metadata["risk_override"])
        self.assertEqual(result.metadata["raw_action"], "buy")
        self.assertEqual(result.metadata["final_action"], "hold")

    def test_unapproved_risk_downgrades_sell_to_hold(self):
        strategy = BasicStrategy()
        context = make_context(
            analysis_results=[make_analysis_result(score=-0.8, confidence=0.9)],
            signal_result=make_signal_result(direction=SignalDirection.SELL, strength=0.8),
            risk_result=make_risk_result(approved=False),
        )
        result = strategy.decide(context)
        self.assertEqual(result.action, SignalDirection.HOLD)
        self.assertTrue(result.metadata["risk_override"])

    def test_unapproved_risk_does_not_override_an_already_hold_decision(self):
        strategy = BasicStrategy()
        context = make_context(
            analysis_results=[make_analysis_result(score=0.05, confidence=0.9)],
            risk_result=make_risk_result(approved=False),
        )
        result = strategy.decide(context)
        self.assertEqual(result.action, SignalDirection.HOLD)
        self.assertFalse(result.metadata["risk_override"])

    def test_approved_risk_never_overrides(self):
        strategy = BasicStrategy()
        context = make_context(
            analysis_results=[make_analysis_result(score=0.8, confidence=0.9)],
            signal_result=make_signal_result(direction=SignalDirection.BUY, strength=0.8),
            risk_result=make_risk_result(approved=True),
        )
        result = strategy.decide(context)
        self.assertEqual(result.action, SignalDirection.BUY)
        self.assertFalse(result.metadata["risk_override"])


# ----------------------------------------------------------------------
# Metadata / summary traceability
# ----------------------------------------------------------------------
class TestExplainability(unittest.TestCase):
    def test_metadata_contains_overall_score(self):
        strategy = BasicStrategy()
        context = make_context(analysis_results=[make_analysis_result(score=0.6, confidence=0.8)])
        result = strategy.decide(context)
        self.assertIn("overall_score", result.metadata)
        self.assertIsInstance(result.metadata["overall_score"], float)

    def test_metadata_records_every_input_facet(self):
        strategy = BasicStrategy()
        context = make_context(
            analysis_results=[make_analysis_result(score=0.6, confidence=0.8)],
            signal_result=make_signal_result(),
            risk_result=make_risk_result(),
        )
        result = strategy.decide(context)
        for key in (
            "analysis",
            "signal",
            "risk",
            "consistency",
            "confidence_breakdown",
            "thresholds",
            "weights",
            "inputs_available",
        ):
            self.assertIn(key, result.metadata)
        self.assertTrue(result.metadata["analysis"]["available"])
        self.assertTrue(result.metadata["signal"]["available"])
        self.assertTrue(result.metadata["risk"]["available"])

    def test_metadata_marks_unavailable_inputs(self):
        strategy = BasicStrategy()
        context = make_context(analysis_results=[make_analysis_result(score=0.6, confidence=0.8)])
        result = strategy.decide(context)
        self.assertFalse(result.metadata["signal"]["available"])
        self.assertFalse(result.metadata["risk"]["available"])

    def test_summary_mentions_symbol_and_timeframe(self):
        strategy = BasicStrategy()
        context = make_context(analysis_results=[make_analysis_result(score=0.6, confidence=0.8)])
        result = strategy.decide(context)
        self.assertIn("BTCUSDT", result.summary)
        self.assertIn("1h", result.summary)

    def test_summary_notes_missing_inputs(self):
        strategy = BasicStrategy()
        context = make_context(analysis_results=[make_analysis_result(score=0.6, confidence=0.8)])
        result = strategy.decide(context)
        self.assertIn("no signal available", result.summary)
        self.assertIn("no risk evaluation available", result.summary)

    def test_summary_notes_risk_override(self):
        strategy = BasicStrategy()
        context = make_context(
            analysis_results=[make_analysis_result(score=0.8, confidence=0.9)],
            signal_result=make_signal_result(direction=SignalDirection.BUY, strength=0.8),
            risk_result=make_risk_result(approved=False),
        )
        result = strategy.decide(context)
        self.assertIn("downgraded", result.summary)


# ----------------------------------------------------------------------
# Determinism
# ----------------------------------------------------------------------
class TestDeterminism(unittest.TestCase):
    def test_same_context_produces_identical_result(self):
        strategy = BasicStrategy()
        context = make_context(
            analysis_results=[make_analysis_result(score=0.4, confidence=0.7)],
            signal_result=make_signal_result(direction=SignalDirection.BUY, strength=0.5),
            risk_result=make_risk_result(approved=True),
        )
        first = strategy.decide(context)
        second = strategy.decide(context)
        self.assertEqual(first, second)

    def test_repeated_calls_across_many_contexts_are_stable(self):
        strategy = BasicStrategy()
        for score in (-0.9, -0.3, 0.0, 0.15, 0.5, 0.95):
            context = make_context(analysis_results=[make_analysis_result(score=score, confidence=0.6)])
            first = strategy.decide(context)
            second = strategy.decide(context)
            self.assertEqual(first.action, second.action)
            self.assertEqual(first.confidence, second.confidence)
            self.assertEqual(first.metadata["overall_score"], second.metadata["overall_score"])


# ----------------------------------------------------------------------
# Deliberate scope boundaries (no AI, no order execution, one strategy)
# ----------------------------------------------------------------------
class TestScopeBoundaries(unittest.TestCase):
    def test_result_type_is_strategy_result_only(self):
        strategy = BasicStrategy()
        context = make_context(analysis_results=[make_analysis_result()])
        result = strategy.decide(context)
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        self.assertEqual(field_names, {"action", "confidence", "summary", "metadata"})
        for forbidden in ("order_id", "broker", "ai_model", "position_size", "execution_status"):
            self.assertNotIn(forbidden, field_names)

    def test_confidence_and_overall_score_are_within_bounds(self):
        strategy = BasicStrategy()
        for score in (-1.0, -0.5, 0.0, 0.5, 1.0):
            context = make_context(analysis_results=[make_analysis_result(score=score, confidence=0.9)])
            result = strategy.decide(context)
            self.assertGreaterEqual(result.confidence, 0.0)
            self.assertLessEqual(result.confidence, 1.0)
            self.assertGreaterEqual(result.metadata["overall_score"], -1.0)
            self.assertLessEqual(result.metadata["overall_score"], 1.0)


# ----------------------------------------------------------------------
# Integration: a realistic StrategyContext decided end-to-end
# ----------------------------------------------------------------------
class TestIntegration(unittest.TestCase):
    def test_end_to_end_bullish_confluence(self):
        strategy = BasicStrategy()
        context = StrategyContext(
            symbol="ETHUSDT",
            timeframe="4h",
            analysis_results=[make_analysis_result(score=0.7, confidence=0.85)],
            signal_result=make_signal_result(direction=SignalDirection.BUY, strength=0.75, confidence=0.8),
            risk_result=make_risk_result(approved=True, risk_score=0.25),
        )
        result = strategy.decide(context)
        self.assertEqual(result.action, SignalDirection.BUY)
        self.assertGreater(result.confidence, 0.5)
        self.assertFalse(result.metadata["risk_override"])
        self.assertEqual(result.metadata["symbol"], "ETHUSDT")
        self.assertEqual(result.metadata["timeframe"], "4h")

    def test_end_to_end_conflicting_inputs_favors_weighted_combination(self):
        strategy = BasicStrategy()
        context = StrategyContext(
            symbol="BTCUSDT",
            timeframe="1h",
            analysis_results=[make_analysis_result(score=0.1, confidence=0.5)],
            signal_result=make_signal_result(direction=SignalDirection.SELL, strength=0.2, confidence=0.3),
            risk_result=make_risk_result(approved=True),
        )
        result = strategy.decide(context)
        # Weak, conflicting inputs -- expect HOLD and reduced confidence.
        self.assertEqual(result.action, SignalDirection.HOLD)
        self.assertLess(result.confidence, 0.5)


if __name__ == "__main__":
    unittest.main()
