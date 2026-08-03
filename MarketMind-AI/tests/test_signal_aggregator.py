"""
test_signal_aggregator.py
---------------------------
Purpose:
    Unit tests for the Signal Engine Part 3 concrete module:
    `signals.aggregator.SignalAggregator`.

Mirrors the local-factory / assertion style already used by
`tests/test_signals.py` (Part 1) and `tests/test_technical_signal_generator.py`
(Part 2), both left untouched by this change, and the fake-sub-component
injection style of `tests/test_aggregator.py`
(`analysis.aggregator.AnalysisAggregator`) one layer down.

Most tests inject fake `BaseSignalGenerator` sub-generators (constructor-
injected, matching the project's dependency-injection convention) so the
aggregation/merging logic itself can be exercised precisely, without
needing to hand-construct a valid `AnalysisAggregator` result chain for
every test. A dedicated integration section at the bottom combines two
real `TechnicalSignalGenerator` instances to prove the module actually
reuses Signal Engine Part 2 end-to-end, as required.

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
from signals import (
    BaseSignalGenerator,
    InsufficientSignalDataError,
    InvalidSignalContextError,
    SignalAggregator,
    SignalContext,
    SignalGeneratorConfigurationError,
    SignalResult,
    TechnicalSignalGenerator,
)
from signals.technical_signal_generator import DEFAULT_AGGREGATOR_NAME

SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"


# ----------------------------------------------------------------------
# Local test factories
# ----------------------------------------------------------------------
def make_signal_context(results: list | None = None) -> SignalContext:
    return SignalContext(symbol=SYMBOL, timeframe=TIMEFRAME, analysis_results=results or [])


def make_aggregator_result(
    *, score: float = 0.5, confidence: float = 0.8, analyzer_name: str = DEFAULT_AGGREGATOR_NAME
) -> AnalysisResult:
    return AnalysisResult(
        analyzer_name=analyzer_name,
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        score=score,
        confidence=confidence,
        summary="fake aggregator result",
        metadata={},
    )


class _FakeGenerator(BaseSignalGenerator):
    """
    Test double for a sub-generator: returns a fixed `SignalResult`, or
    raises `InsufficientSignalDataError` if configured to be
    "unavailable". Lets aggregation logic be tested independently of any
    real `AnalysisResult`/`TechnicalSignalGenerator` machinery.
    """

    def __init__(
        self,
        *,
        direction: SignalDirection = SignalDirection.HOLD,
        strength: float = 0.0,
        confidence: float = 1.0,
        unavailable: bool = False,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        self.direction = direction
        self.strength = strength
        self.confidence = confidence
        self.unavailable = unavailable

    def generate(self, context: SignalContext) -> SignalResult:
        self.validate_context(context)
        if self.unavailable:
            raise InsufficientSignalDataError(f"{self.name} has no data")
        return self._build_result(
            direction=self.direction,
            strength=self.strength,
            confidence=self.confidence,
            summary=f"fake signal from {self.name}",
            metadata={"fake": True},
        )


# ----------------------------------------------------------------------
# Construction / configuration validation
# ----------------------------------------------------------------------
class TestConstruction(unittest.TestCase):
    def test_defaults_to_single_technical_signal_generator(self):
        aggregator = SignalAggregator()
        self.assertEqual(list(aggregator._generators), ["TechnicalSignalGenerator"])
        self.assertIsInstance(
            aggregator._generators["TechnicalSignalGenerator"], TechnicalSignalGenerator
        )
        self.assertEqual(aggregator.weights, {"TechnicalSignalGenerator": 1.0})
        self.assertEqual(aggregator.buy_threshold, 0.2)
        self.assertEqual(aggregator.sell_threshold, -0.2)
        self.assertEqual(aggregator.name, "SignalAggregator")

    def test_is_a_base_signal_generator(self):
        self.assertIsInstance(SignalAggregator(), BaseSignalGenerator)

    def test_custom_generators_and_name(self):
        gen_a = _FakeGenerator(name="A")
        gen_b = _FakeGenerator(name="B")
        aggregator = SignalAggregator(generators=[gen_a, gen_b], name="Custom")
        self.assertEqual(list(aggregator._generators), ["A", "B"])
        self.assertEqual(aggregator.name, "Custom")

    def test_rejects_empty_generator_list(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            SignalAggregator(generators=[])

    def test_rejects_non_generator_item(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            SignalAggregator(generators=["not a generator"])  # type: ignore[list-item]

    def test_rejects_duplicate_generator_names(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            SignalAggregator(generators=[_FakeGenerator(name="A"), _FakeGenerator(name="A")])

    def test_custom_weights(self):
        gen_a = _FakeGenerator(name="A")
        gen_b = _FakeGenerator(name="B")
        aggregator = SignalAggregator(generators=[gen_a, gen_b], weights={"A": 2.0, "B": 0.5})
        self.assertEqual(aggregator.weights, {"A": 2.0, "B": 0.5})

    def test_weights_default_to_one_when_unspecified(self):
        gen_a = _FakeGenerator(name="A")
        gen_b = _FakeGenerator(name="B")
        aggregator = SignalAggregator(generators=[gen_a, gen_b], weights={"A": 3.0})
        self.assertEqual(aggregator.weights, {"A": 3.0, "B": 1.0})

    def test_rejects_unknown_weight_key(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            SignalAggregator(generators=[_FakeGenerator(name="A")], weights={"Unknown": 1.0})

    def test_rejects_negative_weight(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            SignalAggregator(generators=[_FakeGenerator(name="A")], weights={"A": -1.0})

    def test_rejects_non_numeric_weight(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            SignalAggregator(generators=[_FakeGenerator(name="A")], weights={"A": "high"})  # type: ignore[dict-item]

    def test_rejects_boolean_weight(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            SignalAggregator(generators=[_FakeGenerator(name="A")], weights={"A": True})  # type: ignore[dict-item]

    def test_rejects_non_finite_weight(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            SignalAggregator(generators=[_FakeGenerator(name="A")], weights={"A": float("nan")})

    def test_accepts_zero_weight(self):
        aggregator = SignalAggregator(generators=[_FakeGenerator(name="A")], weights={"A": 0.0})
        self.assertEqual(aggregator.weights["A"], 0.0)

    def test_rejects_non_numeric_thresholds(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            SignalAggregator(buy_threshold="high")  # type: ignore[arg-type]
        with self.assertRaises(SignalGeneratorConfigurationError):
            SignalAggregator(sell_threshold=None)  # type: ignore[arg-type]

    def test_rejects_thresholds_out_of_range(self):
        with self.assertRaises(SignalGeneratorConfigurationError):
            SignalAggregator(buy_threshold=0.0)
        with self.assertRaises(SignalGeneratorConfigurationError):
            SignalAggregator(sell_threshold=0.0)
        with self.assertRaises(SignalGeneratorConfigurationError):
            SignalAggregator(buy_threshold=1.5)
        with self.assertRaises(SignalGeneratorConfigurationError):
            SignalAggregator(sell_threshold=-1.5)


# ----------------------------------------------------------------------
# generate() -- context validation and unavailable-generator handling
# ----------------------------------------------------------------------
class TestGenerateValidation(unittest.TestCase):
    def test_rejects_non_signal_context(self):
        aggregator = SignalAggregator(generators=[_FakeGenerator(name="A")])
        with self.assertRaises(InvalidSignalContextError):
            aggregator.generate("not a context")  # type: ignore[arg-type]

    def test_raises_when_all_generators_unavailable(self):
        aggregator = SignalAggregator(
            generators=[
                _FakeGenerator(name="A", unavailable=True),
                _FakeGenerator(name="B", unavailable=True),
            ]
        )
        with self.assertRaises(InsufficientSignalDataError):
            aggregator.generate(make_signal_context())

    def test_ignores_a_single_unavailable_generator(self):
        aggregator = SignalAggregator(
            generators=[
                _FakeGenerator(name="A", unavailable=True),
                _FakeGenerator(
                    name="B", direction=SignalDirection.BUY, strength=0.8, confidence=0.9
                ),
            ]
        )
        result = aggregator.generate(make_signal_context())
        self.assertEqual(result.direction, SignalDirection.BUY)
        self.assertIn("A", result.metadata["generators_missing"])
        self.assertIn("B", result.metadata["generators_available"])

    def test_missing_reason_is_recorded(self):
        aggregator = SignalAggregator(generators=[_FakeGenerator(name="A", unavailable=True)])
        try:
            aggregator.generate(make_signal_context())
        except InsufficientSignalDataError:
            pass
        # Re-run with a second, available generator so we can inspect
        # the "missing" branch of the metadata directly.
        aggregator = SignalAggregator(
            generators=[
                _FakeGenerator(name="A", unavailable=True),
                _FakeGenerator(name="B", direction=SignalDirection.BUY, strength=0.5),
            ]
        )
        result = aggregator.generate(make_signal_context())
        self.assertIn("A has no data", result.metadata["components"]["A"]["reason"])


# ----------------------------------------------------------------------
# generate() -- weighted aggregation / direction mapping
# ----------------------------------------------------------------------
class TestGenerateAggregation(unittest.TestCase):
    def test_agreeing_bullish_generators_yield_bullish_signal(self):
        aggregator = SignalAggregator(
            generators=[
                _FakeGenerator(
                    name="A", direction=SignalDirection.BUY, strength=0.8, confidence=0.9
                ),
                _FakeGenerator(
                    name="B", direction=SignalDirection.BUY, strength=0.6, confidence=0.8
                ),
            ]
        )
        result = aggregator.generate(make_signal_context())
        self.assertEqual(result.direction, SignalDirection.BUY)
        self.assertGreater(result.strength, 0.0)
        self.assertGreater(result.confidence, 0.0)

    def test_agreeing_bearish_generators_yield_bearish_signal(self):
        aggregator = SignalAggregator(
            generators=[
                _FakeGenerator(
                    name="A", direction=SignalDirection.SELL, strength=0.7, confidence=0.9
                ),
                _FakeGenerator(
                    name="B", direction=SignalDirection.SELL, strength=0.5, confidence=0.8
                ),
            ]
        )
        result = aggregator.generate(make_signal_context())
        self.assertEqual(result.direction, SignalDirection.SELL)

    def test_conflicting_generators_cancel_toward_neutral(self):
        aggregator = SignalAggregator(
            generators=[
                _FakeGenerator(
                    name="A", direction=SignalDirection.BUY, strength=0.8, confidence=1.0
                ),
                _FakeGenerator(
                    name="B", direction=SignalDirection.SELL, strength=0.8, confidence=1.0
                ),
            ]
        )
        result = aggregator.generate(make_signal_context())
        self.assertEqual(result.direction, SignalDirection.HOLD)
        self.assertAlmostEqual(result.strength, 0.0)

    def test_weights_change_outcome(self):
        # Without weighting, a strong SELL and a strong BUY of equal
        # confidence would roughly cancel; heavily weighting the BUY
        # side should tip the aggregate toward Bullish.
        aggregator = SignalAggregator(
            generators=[
                _FakeGenerator(
                    name="A", direction=SignalDirection.BUY, strength=0.8, confidence=1.0
                ),
                _FakeGenerator(
                    name="B", direction=SignalDirection.SELL, strength=0.8, confidence=1.0
                ),
            ],
            weights={"A": 5.0, "B": 1.0},
        )
        result = aggregator.generate(make_signal_context())
        self.assertEqual(result.direction, SignalDirection.BUY)

    def test_all_hold_generators_yield_hold_with_zero_strength(self):
        aggregator = SignalAggregator(
            generators=[
                _FakeGenerator(name="A", direction=SignalDirection.HOLD, strength=0.0),
                _FakeGenerator(name="B", direction=SignalDirection.HOLD, strength=0.0),
            ]
        )
        result = aggregator.generate(make_signal_context())
        self.assertEqual(result.direction, SignalDirection.HOLD)
        self.assertEqual(result.strength, 0.0)

    def test_custom_thresholds_change_classification(self):
        aggregator = SignalAggregator(
            generators=[
                _FakeGenerator(
                    name="A", direction=SignalDirection.BUY, strength=0.3, confidence=1.0
                )
            ],
            buy_threshold=0.5,
            sell_threshold=-0.5,
        )
        result = aggregator.generate(make_signal_context())
        # strength 0.3 is Bullish under default thresholds (0.2) but
        # Neutral once buy_threshold is raised to 0.5.
        self.assertEqual(result.direction, SignalDirection.HOLD)

    def test_zero_weight_generator_does_not_affect_direction(self):
        aggregator = SignalAggregator(
            generators=[
                _FakeGenerator(
                    name="A", direction=SignalDirection.BUY, strength=0.9, confidence=1.0
                ),
                _FakeGenerator(
                    name="B", direction=SignalDirection.SELL, strength=0.9, confidence=1.0
                ),
            ],
            weights={"A": 1.0, "B": 0.0},
        )
        result = aggregator.generate(make_signal_context())
        self.assertEqual(result.direction, SignalDirection.BUY)


# ----------------------------------------------------------------------
# generate() -- output shape (metadata / summary content)
# ----------------------------------------------------------------------
class TestGenerateOutputShape(unittest.TestCase):
    def setUp(self):
        self.gen_a = _FakeGenerator(
            name="A", direction=SignalDirection.BUY, strength=0.7, confidence=0.9
        )
        self.gen_b = _FakeGenerator(
            name="B", direction=SignalDirection.BUY, strength=0.4, confidence=0.6
        )
        self.aggregator = SignalAggregator(
            generators=[self.gen_a, self.gen_b], weights={"A": 2.0, "B": 1.0}
        )

    def test_result_is_a_valid_signal_result_with_five_fields(self):
        result = self.aggregator.generate(make_signal_context())
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        self.assertEqual(
            field_names, {"direction", "strength", "confidence", "summary", "metadata"}
        )

    def test_metadata_contains_every_component_signal(self):
        result = self.aggregator.generate(make_signal_context())
        components = result.metadata["components"]
        self.assertIn("A", components)
        self.assertIn("B", components)
        self.assertTrue(components["A"]["available"])
        self.assertEqual(components["A"]["direction"], "buy")
        self.assertEqual(components["A"]["strength"], 0.7)
        self.assertEqual(components["A"]["confidence"], 0.9)
        self.assertEqual(components["A"]["weight"], 2.0)
        self.assertEqual(components["A"]["metadata"], {"fake": True})

    def test_metadata_contains_weights(self):
        result = self.aggregator.generate(make_signal_context())
        self.assertEqual(result.metadata["weights"], {"A": 2.0, "B": 1.0})

    def test_metadata_contains_aggregation_details(self):
        result = self.aggregator.generate(make_signal_context())
        details = result.metadata["aggregation_details"]
        self.assertIn("method", details)
        self.assertIn("aggregate_score", details)
        self.assertIn("score_label", details)
        self.assertEqual(details["buy_threshold"], 0.2)
        self.assertEqual(details["sell_threshold"], -0.2)
        self.assertIn("completeness_ratio", details)
        self.assertIn("conviction", details)

    def test_metadata_contains_missing_generators_list(self):
        aggregator = SignalAggregator(
            generators=[
                _FakeGenerator(name="A", unavailable=True),
                _FakeGenerator(name="B", direction=SignalDirection.BUY, strength=0.5),
            ]
        )
        result = aggregator.generate(make_signal_context())
        self.assertEqual(result.metadata["generators_missing"], ["A"])
        self.assertEqual(result.metadata["generators_available"], ["B"])
        self.assertFalse(result.metadata["components"]["A"]["available"])

    def test_summary_mentions_symbol_and_timeframe(self):
        result = self.aggregator.generate(make_signal_context())
        self.assertIn(SYMBOL, result.summary)
        self.assertIn(TIMEFRAME, result.summary)

    def test_summary_mentions_missing_generators_when_present(self):
        aggregator = SignalAggregator(
            generators=[
                _FakeGenerator(name="A", unavailable=True),
                _FakeGenerator(name="B", direction=SignalDirection.BUY, strength=0.5),
            ]
        )
        result = aggregator.generate(make_signal_context())
        self.assertIn("missing", result.summary)
        self.assertIn("A", result.summary)


# ----------------------------------------------------------------------
# Real TechnicalSignalGenerator integration
# ----------------------------------------------------------------------
class TestRealGeneratorIntegration(unittest.TestCase):
    def test_combines_two_real_technical_signal_generators(self):
        # Two differently-thresholded TechnicalSignalGenerator instances
        # reading the same underlying AnalysisAggregator-shaped result,
        # proving SignalAggregator actually reuses Signal Engine Part 2
        # end-to-end rather than a hand-built fake.
        lenient = TechnicalSignalGenerator(buy_threshold=0.1, sell_threshold=-0.1, name="lenient")
        strict = TechnicalSignalGenerator(buy_threshold=0.6, sell_threshold=-0.6, name="strict")
        aggregator = SignalAggregator(generators=[lenient, strict])

        context = make_signal_context([make_aggregator_result(score=0.3, confidence=0.8)])
        result = aggregator.generate(context)

        # lenient reads 0.3 as Bullish; strict reads 0.3 as Neutral.
        self.assertIn("lenient", result.metadata["generators_available"])
        self.assertIn("strict", result.metadata["generators_available"])
        self.assertEqual(result.metadata["components"]["lenient"]["direction"], "buy")
        self.assertEqual(result.metadata["components"]["strict"]["direction"], "hold")
        # Overall verdict should still lean Bullish since one real
        # contributing generator called it Bullish and the other Neutral
        # (not Bearish).
        self.assertIn(result.direction, (SignalDirection.BUY, SignalDirection.HOLD))

    def test_raises_when_no_aggregator_result_present_for_either_generator(self):
        lenient = TechnicalSignalGenerator(name="lenient")
        strict = TechnicalSignalGenerator(name="strict")
        aggregator = SignalAggregator(generators=[lenient, strict])

        context = make_signal_context([])
        with self.assertRaises(InsufficientSignalDataError):
            aggregator.generate(context)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
