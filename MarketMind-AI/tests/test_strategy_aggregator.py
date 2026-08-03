"""
test_strategy_aggregator.py
-----------------------------
Purpose:
    Unit tests for the Strategy Engine Part 3 concrete module:
    `strategies.aggregator.StrategyAggregator`.

Mirrors the local-factory / assertion style already used by
`tests/test_strategies.py` (Part 1) and `tests/test_basic_strategy.py`
(Part 2), both left untouched by this change, and the fake-sub-component
injection style of `tests/test_signal_aggregator.py`
(`signals.aggregator.SignalAggregator`) one layer down.

Most tests inject fake `BaseStrategy` sub-strategies (constructor-
injected, matching the project's dependency-injection convention) so
the aggregation/merging logic itself can be exercised precisely,
without needing to hand-construct a full analysis/signal/risk chain
for every test. A dedicated integration section at the bottom combines
two real `BasicStrategy` instances to prove the module actually reuses
Strategy Engine Part 2 end-to-end, as required.

Uses the standard-library ``unittest`` framework, no external
test-runner dependency, no network access.

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest

from analysis.result import AnalysisResult
from core.enums import SignalDirection
from strategies import (
    BaseStrategy,
    BasicStrategy,
    InsufficientStrategyDataError,
    InvalidStrategyContextError,
    StrategyAggregator,
    StrategyConfigurationError,
    StrategyContext,
    StrategyResult,
)
from strategies.basic_strategy import DEFAULT_ANALYSIS_ANALYZER_NAME

SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"


# ----------------------------------------------------------------------
# Local test factories
# ----------------------------------------------------------------------
def make_strategy_context(analysis_results: list | None = None) -> StrategyContext:
    return StrategyContext(
        symbol=SYMBOL, timeframe=TIMEFRAME, analysis_results=analysis_results or []
    )


def make_analysis_result(
    *,
    score: float = 0.5,
    confidence: float = 0.8,
    analyzer_name: str = DEFAULT_ANALYSIS_ANALYZER_NAME,
) -> AnalysisResult:
    return AnalysisResult(
        analyzer_name=analyzer_name,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        score=score,
        confidence=confidence,
        summary="fake analysis result",
        metadata={},
    )


class _FakeStrategy(BaseStrategy):
    """
    Test double for a sub-strategy: returns a fixed `StrategyResult`,
    or raises `InsufficientStrategyDataError` if configured to be
    "unavailable". Lets aggregation logic be tested independently of
    any real `AnalysisResult`/`BasicStrategy` machinery.
    """

    def __init__(
        self,
        *,
        action: SignalDirection = SignalDirection.HOLD,
        confidence: float = 1.0,
        unavailable: bool = False,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        self.action = action
        self.confidence = confidence
        self.unavailable = unavailable

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        if self.unavailable:
            raise InsufficientStrategyDataError(f"{self.name} has no data")
        return self._build_result(
            action=self.action,
            confidence=self.confidence,
            summary=f"fake decision from {self.name}",
            metadata={"fake": True},
        )


# ----------------------------------------------------------------------
# Construction / configuration validation
# ----------------------------------------------------------------------
class TestConstruction(unittest.TestCase):
    def test_defaults_to_single_basic_strategy(self):
        aggregator = StrategyAggregator()
        self.assertEqual(list(aggregator._strategies), ["BasicStrategy"])
        self.assertIsInstance(aggregator._strategies["BasicStrategy"], BasicStrategy)
        self.assertEqual(aggregator.weights, {"BasicStrategy": 1.0})
        self.assertEqual(aggregator.buy_threshold, 0.2)
        self.assertEqual(aggregator.sell_threshold, -0.2)
        self.assertEqual(aggregator.name, "StrategyAggregator")

    def test_is_a_base_strategy(self):
        self.assertIsInstance(StrategyAggregator(), BaseStrategy)

    def test_custom_strategies_and_name(self):
        strat_a = _FakeStrategy(name="A")
        strat_b = _FakeStrategy(name="B")
        aggregator = StrategyAggregator(strategies=[strat_a, strat_b], name="Custom")
        self.assertEqual(list(aggregator._strategies), ["A", "B"])
        self.assertEqual(aggregator.name, "Custom")

    def test_rejects_empty_strategy_list(self):
        with self.assertRaises(StrategyConfigurationError):
            StrategyAggregator(strategies=[])

    def test_rejects_non_strategy_item(self):
        with self.assertRaises(StrategyConfigurationError):
            StrategyAggregator(strategies=["not a strategy"])  # type: ignore[list-item]

    def test_rejects_duplicate_strategy_names(self):
        with self.assertRaises(StrategyConfigurationError):
            StrategyAggregator(strategies=[_FakeStrategy(name="A"), _FakeStrategy(name="A")])

    def test_custom_weights(self):
        strat_a = _FakeStrategy(name="A")
        strat_b = _FakeStrategy(name="B")
        aggregator = StrategyAggregator(
            strategies=[strat_a, strat_b], weights={"A": 2.0, "B": 0.5}
        )
        self.assertEqual(aggregator.weights, {"A": 2.0, "B": 0.5})

    def test_weights_default_to_one_when_unspecified(self):
        strat_a = _FakeStrategy(name="A")
        strat_b = _FakeStrategy(name="B")
        aggregator = StrategyAggregator(strategies=[strat_a, strat_b], weights={"A": 3.0})
        self.assertEqual(aggregator.weights, {"A": 3.0, "B": 1.0})

    def test_rejects_unknown_weight_key(self):
        with self.assertRaises(StrategyConfigurationError):
            StrategyAggregator(strategies=[_FakeStrategy(name="A")], weights={"Unknown": 1.0})

    def test_rejects_negative_weight(self):
        with self.assertRaises(StrategyConfigurationError):
            StrategyAggregator(strategies=[_FakeStrategy(name="A")], weights={"A": -1.0})

    def test_rejects_non_numeric_weight(self):
        with self.assertRaises(StrategyConfigurationError):
            StrategyAggregator(
                strategies=[_FakeStrategy(name="A")], weights={"A": "high"}  # type: ignore[dict-item]
            )

    def test_rejects_boolean_weight(self):
        with self.assertRaises(StrategyConfigurationError):
            StrategyAggregator(
                strategies=[_FakeStrategy(name="A")], weights={"A": True}  # type: ignore[dict-item]
            )

    def test_rejects_non_finite_weight(self):
        with self.assertRaises(StrategyConfigurationError):
            StrategyAggregator(
                strategies=[_FakeStrategy(name="A")], weights={"A": float("nan")}
            )

    def test_accepts_zero_weight(self):
        aggregator = StrategyAggregator(strategies=[_FakeStrategy(name="A")], weights={"A": 0.0})
        self.assertEqual(aggregator.weights["A"], 0.0)

    def test_rejects_non_numeric_thresholds(self):
        with self.assertRaises(StrategyConfigurationError):
            StrategyAggregator(buy_threshold="high")  # type: ignore[arg-type]
        with self.assertRaises(StrategyConfigurationError):
            StrategyAggregator(sell_threshold=None)  # type: ignore[arg-type]

    def test_rejects_thresholds_out_of_range(self):
        with self.assertRaises(StrategyConfigurationError):
            StrategyAggregator(buy_threshold=0.0)
        with self.assertRaises(StrategyConfigurationError):
            StrategyAggregator(sell_threshold=0.0)
        with self.assertRaises(StrategyConfigurationError):
            StrategyAggregator(buy_threshold=1.5)
        with self.assertRaises(StrategyConfigurationError):
            StrategyAggregator(sell_threshold=-1.5)


# ----------------------------------------------------------------------
# decide() -- context validation and unavailable-strategy handling
# ----------------------------------------------------------------------
class TestDecideValidation(unittest.TestCase):
    def test_rejects_non_strategy_context(self):
        aggregator = StrategyAggregator(strategies=[_FakeStrategy(name="A")])
        with self.assertRaises(InvalidStrategyContextError):
            aggregator.decide("not a context")  # type: ignore[arg-type]

    def test_raises_when_all_strategies_unavailable(self):
        aggregator = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", unavailable=True),
                _FakeStrategy(name="B", unavailable=True),
            ]
        )
        with self.assertRaises(InsufficientStrategyDataError):
            aggregator.decide(make_strategy_context())

    def test_ignores_a_single_unavailable_strategy(self):
        aggregator = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", unavailable=True),
                _FakeStrategy(name="B", action=SignalDirection.BUY, confidence=0.9),
            ]
        )
        result = aggregator.decide(make_strategy_context())
        self.assertEqual(result.action, SignalDirection.BUY)
        self.assertIn("A", result.metadata["strategies_missing"])
        self.assertIn("B", result.metadata["strategies_available"])

    def test_missing_reason_is_recorded(self):
        aggregator = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", unavailable=True),
                _FakeStrategy(name="B", action=SignalDirection.BUY, confidence=0.5),
            ]
        )
        result = aggregator.decide(make_strategy_context())
        self.assertIn("A has no data", result.metadata["components"]["A"]["reason"])

    def test_never_mutates_sub_strategy_results(self):
        # Calling decide() twice must not change what the sub-strategy
        # itself would independently produce -- StrategyResult is
        # frozen, but this also confirms the aggregator never rebuilds
        # a sub-result in place.
        strat = _FakeStrategy(name="A", action=SignalDirection.BUY, confidence=0.7)
        aggregator = StrategyAggregator(strategies=[strat])
        ctx = make_strategy_context()
        first = strat.decide(ctx)
        aggregator.decide(ctx)
        second = strat.decide(ctx)
        self.assertEqual(first, second)


# ----------------------------------------------------------------------
# decide() -- weighted aggregation / action mapping
# ----------------------------------------------------------------------
class TestDecideAggregation(unittest.TestCase):
    def test_agreeing_bullish_strategies_yield_buy(self):
        aggregator = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", action=SignalDirection.BUY, confidence=0.9),
                _FakeStrategy(name="B", action=SignalDirection.BUY, confidence=0.8),
            ]
        )
        result = aggregator.decide(make_strategy_context())
        self.assertEqual(result.action, SignalDirection.BUY)
        self.assertGreater(result.confidence, 0.0)
        self.assertEqual(result.metadata["overall_score"], 1.0)
        self.assertEqual(result.metadata["agreement"], 1.0)
        self.assertEqual(result.metadata["completeness"], 1.0)

    def test_agreeing_bearish_strategies_yield_sell(self):
        aggregator = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", action=SignalDirection.SELL, confidence=0.9),
                _FakeStrategy(name="B", action=SignalDirection.SELL, confidence=0.8),
            ]
        )
        result = aggregator.decide(make_strategy_context())
        self.assertEqual(result.action, SignalDirection.SELL)
        self.assertEqual(result.metadata["overall_score"], -1.0)

    def test_conflicting_strategies_cancel_toward_hold(self):
        aggregator = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", action=SignalDirection.BUY, confidence=1.0),
                _FakeStrategy(name="B", action=SignalDirection.SELL, confidence=1.0),
            ]
        )
        result = aggregator.decide(make_strategy_context())
        self.assertEqual(result.action, SignalDirection.HOLD)
        self.assertAlmostEqual(result.metadata["overall_score"], 0.0)
        # Directly opposed decisions should drag agreement down, not
        # leave it at a false 1.0.
        self.assertLess(result.metadata["agreement"], 1.0)

    def test_weights_change_outcome(self):
        aggregator = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", action=SignalDirection.BUY, confidence=1.0),
                _FakeStrategy(name="B", action=SignalDirection.SELL, confidence=1.0),
            ],
            weights={"A": 5.0, "B": 1.0},
        )
        result = aggregator.decide(make_strategy_context())
        self.assertEqual(result.action, SignalDirection.BUY)

    def test_all_hold_strategies_yield_hold(self):
        aggregator = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", action=SignalDirection.HOLD),
                _FakeStrategy(name="B", action=SignalDirection.HOLD),
            ]
        )
        result = aggregator.decide(make_strategy_context())
        self.assertEqual(result.action, SignalDirection.HOLD)
        self.assertEqual(result.metadata["overall_score"], 0.0)
        self.assertEqual(result.metadata["agreement"], 1.0)

    def test_threshold_above_unit_score_forces_hold(self):
        # buy_threshold must stay within (0.0, 1.0], so 1.0 itself is
        # the tightest legal ceiling; a lone BUY's signed unit score
        # of +1.0 is not strictly greater than 1.0, so it maps to HOLD.
        aggregator = StrategyAggregator(
            strategies=[_FakeStrategy(name="A", action=SignalDirection.BUY, confidence=1.0)],
            buy_threshold=1.0,
        )
        result = aggregator.decide(make_strategy_context())
        self.assertEqual(result.action, SignalDirection.HOLD)

    def test_zero_weight_strategy_does_not_affect_action(self):
        aggregator = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", action=SignalDirection.BUY, confidence=1.0),
                _FakeStrategy(name="B", action=SignalDirection.SELL, confidence=1.0),
            ],
            weights={"A": 1.0, "B": 0.0},
        )
        result = aggregator.decide(make_strategy_context())
        self.assertEqual(result.action, SignalDirection.BUY)

    def test_low_confidence_strategy_contributes_less(self):
        aggregator = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", action=SignalDirection.BUY, confidence=1.0),
                _FakeStrategy(name="B", action=SignalDirection.SELL, confidence=0.01),
            ]
        )
        result = aggregator.decide(make_strategy_context())
        self.assertEqual(result.action, SignalDirection.BUY)


# ----------------------------------------------------------------------
# decide() -- completeness / agreement / confidence shape
# ----------------------------------------------------------------------
class TestDecideCompletenessAgreementConfidence(unittest.TestCase):
    def test_completeness_reflects_missing_strategies(self):
        aggregator = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", action=SignalDirection.BUY, confidence=1.0),
                _FakeStrategy(name="B", unavailable=True),
            ]
        )
        result = aggregator.decide(make_strategy_context())
        self.assertAlmostEqual(result.metadata["completeness"], 0.5)

    def test_full_completeness_when_all_available(self):
        aggregator = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", action=SignalDirection.BUY, confidence=1.0),
                _FakeStrategy(name="B", action=SignalDirection.BUY, confidence=1.0),
            ]
        )
        result = aggregator.decide(make_strategy_context())
        self.assertEqual(result.metadata["completeness"], 1.0)

    def test_partial_agreement_between_hold_and_buy(self):
        aggregator = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", action=SignalDirection.HOLD, confidence=1.0),
                _FakeStrategy(name="B", action=SignalDirection.HOLD, confidence=1.0),
            ],
            buy_threshold=0.99,
        )
        # Both HOLD -> overall_score 0.0 -> final action HOLD -> full
        # agreement, sanity-checking the baseline before perturbing it.
        result = aggregator.decide(make_strategy_context())
        self.assertEqual(result.metadata["agreement"], 1.0)

    def test_confidence_never_exceeds_component_confidences(self):
        aggregator = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", action=SignalDirection.BUY, confidence=0.4),
                _FakeStrategy(name="B", action=SignalDirection.BUY, confidence=0.6),
            ]
        )
        result = aggregator.decide(make_strategy_context())
        self.assertLessEqual(result.confidence, 0.6)

    def test_missing_strategy_lowers_confidence_via_completeness(self):
        base = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", action=SignalDirection.BUY, confidence=0.9),
                _FakeStrategy(name="B", action=SignalDirection.BUY, confidence=0.9),
            ]
        )
        degraded = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", action=SignalDirection.BUY, confidence=0.9),
                _FakeStrategy(name="B", unavailable=True),
            ]
        )
        base_result = base.decide(make_strategy_context())
        degraded_result = degraded.decide(make_strategy_context())
        self.assertLess(degraded_result.confidence, base_result.confidence)

    def test_disagreement_lowers_confidence_via_agreement(self):
        agreeing = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", action=SignalDirection.BUY, confidence=0.9),
                _FakeStrategy(name="B", action=SignalDirection.BUY, confidence=0.9),
            ]
        )
        disagreeing = StrategyAggregator(
            strategies=[
                _FakeStrategy(name="A", action=SignalDirection.BUY, confidence=0.9),
                _FakeStrategy(name="B", action=SignalDirection.HOLD, confidence=0.9),
            ]
        )
        agreeing_result = agreeing.decide(make_strategy_context())
        disagreeing_result = disagreeing.decide(make_strategy_context())
        self.assertLess(disagreeing_result.confidence, agreeing_result.confidence)

    def test_confidence_is_zero_to_one(self):
        aggregator = StrategyAggregator(
            strategies=[_FakeStrategy(name="A", action=SignalDirection.BUY, confidence=1.0)]
        )
        result = aggregator.decide(make_strategy_context())
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)


# ----------------------------------------------------------------------
# decide() -- output shape (metadata / summary content / determinism)
# ----------------------------------------------------------------------
class TestDecideOutputShape(unittest.TestCase):
    def setUp(self):
        self.strat_a = _FakeStrategy(name="A", action=SignalDirection.BUY, confidence=0.9)
        self.strat_b = _FakeStrategy(name="B", action=SignalDirection.BUY, confidence=0.6)
        self.aggregator = StrategyAggregator(
            strategies=[self.strat_a, self.strat_b], weights={"A": 2.0, "B": 1.0}
        )

    def test_result_is_a_valid_strategy_result_with_four_fields(self):
        result = self.aggregator.decide(make_strategy_context())
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        self.assertEqual(field_names, {"action", "confidence", "summary", "metadata"})

    def test_result_has_no_order_broker_or_ai_fields(self):
        result = self.aggregator.decide(make_strategy_context())
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        for forbidden in (
            "order_id",
            "position_size",
            "stop_loss",
            "take_profit",
            "score",
            "strategy_name",
        ):
            self.assertNotIn(forbidden, field_names)

    def test_metadata_contains_every_component_strategy(self):
        result = self.aggregator.decide(make_strategy_context())
        components = result.metadata["components"]
        self.assertIn("A", components)
        self.assertIn("B", components)
        self.assertTrue(components["A"]["available"])
        self.assertEqual(components["A"]["action"], "buy")
        self.assertEqual(components["A"]["confidence"], 0.9)
        self.assertEqual(components["A"]["weight"], 2.0)
        self.assertEqual(components["A"]["metadata"], {"fake": True})
        self.assertIn("agreement_with_final", components["A"])

    def test_metadata_contains_weights(self):
        result = self.aggregator.decide(make_strategy_context())
        self.assertEqual(result.metadata["weights"], {"A": 2.0, "B": 1.0})

    def test_metadata_contains_aggregation_details(self):
        result = self.aggregator.decide(make_strategy_context())
        details = result.metadata["aggregation_details"]
        self.assertIn("method", details)
        self.assertIn("overall_score", details)
        self.assertIn("score_label", details)
        self.assertIn("final_action", details)
        self.assertIn("completeness", details)
        self.assertIn("agreement", details)
        self.assertEqual(details["buy_threshold"], self.aggregator.buy_threshold)
        self.assertEqual(details["sell_threshold"], self.aggregator.sell_threshold)

    def test_metadata_contains_top_level_required_facets(self):
        result = self.aggregator.decide(make_strategy_context())
        for key in ("overall_score", "completeness", "agreement"):
            self.assertIn(key, result.metadata)

    def test_summary_mentions_action_and_contributing_strategies(self):
        result = self.aggregator.decide(make_strategy_context())
        self.assertIn(result.action.value.upper(), result.summary)
        self.assertIn("A", result.summary)
        self.assertIn("B", result.summary)

    def test_determinism_repeated_calls_produce_identical_results(self):
        ctx = make_strategy_context()
        first = self.aggregator.decide(ctx)
        second = self.aggregator.decide(ctx)
        self.assertEqual(first.action, second.action)
        self.assertEqual(first.confidence, second.confidence)
        self.assertEqual(first.summary, second.summary)
        self.assertEqual(first.metadata, second.metadata)

    def test_sequential_order_preserved_in_metadata(self):
        result = self.aggregator.decide(make_strategy_context())
        self.assertEqual(list(result.metadata["components"]), ["A", "B"])


# ----------------------------------------------------------------------
# Integration -- real BasicStrategy instances (Strategy Engine Part 2)
# ----------------------------------------------------------------------
class TestRealBasicStrategyIntegration(unittest.TestCase):
    def test_two_agreeing_basic_strategies_yield_buy(self):
        analysis = make_analysis_result(score=0.7, confidence=0.85)
        ctx = make_strategy_context(analysis_results=[analysis])

        aggregator = StrategyAggregator(
            strategies=[
                BasicStrategy(name="Conservative", buy_threshold=0.4),
                BasicStrategy(name="Aggressive", buy_threshold=0.1),
            ]
        )
        result = aggregator.decide(ctx)
        self.assertIsInstance(result, StrategyResult)
        self.assertEqual(result.action, SignalDirection.BUY)
        self.assertGreater(result.confidence, 0.0)
        self.assertIn("Conservative", result.metadata["strategies_available"])
        self.assertIn("Aggressive", result.metadata["strategies_available"])

    def test_disagreeing_basic_strategies_reduce_agreement(self):
        # A weak-but-positive analysis score is BUY under a low
        # threshold and HOLD under a high one, so the two real
        # BasicStrategy instances genuinely disagree.
        analysis = make_analysis_result(score=0.25, confidence=0.9)
        ctx = make_strategy_context(analysis_results=[analysis])

        aggregator = StrategyAggregator(
            strategies=[
                BasicStrategy(name="Loose", buy_threshold=0.1),
                BasicStrategy(name="Strict", buy_threshold=0.6),
            ]
        )
        result = aggregator.decide(ctx)
        self.assertLess(result.metadata["agreement"], 1.0)

    def test_missing_expected_analysis_result_is_unavailable_not_fatal(self):
        # BasicStrategy raises InsufficientStrategyDataError when it
        # can't find its expected AnalysisResult; StrategyAggregator
        # must treat that as "unavailable" for that sub-strategy, not
        # fail the whole aggregation, as long as at least one other
        # sub-strategy can still decide.
        analysis = make_analysis_result(score=0.5, confidence=0.8, analyzer_name="Other")
        ctx = make_strategy_context(analysis_results=[analysis])

        aggregator = StrategyAggregator(
            strategies=[
                BasicStrategy(name="ExpectsAggregator"),  # looks for "AnalysisAggregator"
                BasicStrategy(name="ExpectsOther", analysis_analyzer_name="Other"),
            ]
        )
        result = aggregator.decide(ctx)
        self.assertIn("ExpectsAggregator", result.metadata["strategies_missing"])
        self.assertIn("ExpectsOther", result.metadata["strategies_available"])

    def test_all_basic_strategies_missing_expected_analysis_raises(self):
        analysis = make_analysis_result(score=0.5, confidence=0.8, analyzer_name="Other")
        ctx = make_strategy_context(analysis_results=[analysis])

        aggregator = StrategyAggregator(strategies=[BasicStrategy()])
        with self.assertRaises(InsufficientStrategyDataError):
            aggregator.decide(ctx)

    def test_default_construction_uses_real_basic_strategy(self):
        analysis = make_analysis_result(score=0.6, confidence=0.8)
        ctx = make_strategy_context(analysis_results=[analysis])
        result = StrategyAggregator().decide(ctx)
        self.assertEqual(result.action, SignalDirection.BUY)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
