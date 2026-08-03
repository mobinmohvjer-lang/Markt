"""
signals/aggregator.py

Defines `SignalAggregator`: Signal Engine Part 3. Combines multiple
`SignalResult`s -- produced by one or more injected `BaseSignalGenerator`
instances -- into a single, final `SignalResult` for one `SignalContext`.

This module does not add any new signal-generation logic of its own: it
holds an ordered collection of existing `BaseSignalGenerator` instances
(constructor-injectable, matching the project's dependency-injection
convention -- defaulting to a single `TechnicalSignalGenerator` when
none are supplied), runs each against the given `SignalContext`, and
merges their individual `SignalResult`s. Nothing in `signals/base.py`,
`signals/context.py`, `signals/result.py`, `signals/exceptions.py`,
`signals/utils.py`, or `signals/technical_signal_generator.py` (Signal
Engine Parts 1 and 2) is modified or subclassed differently here.

Why this exists
----------------
`TechnicalSignalGenerator` (Part 2) standardizes exactly one
`AnalysisResult` into a `SignalResult`. Once more than one
`BaseSignalGenerator` instance is in play -- e.g. several
`TechnicalSignalGenerator`s configured with different
`buy_threshold`/`sell_threshold` pairs, or a future non-technical
generator -- something needs to combine their independent
`SignalResult`s into one usable verdict. `SignalAggregator` is that
combiner, mirroring the role `analysis.aggregator.AnalysisAggregator`
already plays one layer down for `analysis.technical`'s five analyzers.

Weighted aggregation
---------------------
Each sub-generator is identified by its own `.name` (the same value
`BaseSignalGenerator.__init__` already assigns/accepts) and may be
assigned a `weight` (default `1.0`, must be finite and `>= 0.0`) via the
`weights` constructor parameter, keyed by that name. A sub-generator's
own `confidence` further scales its contribution on top of its fixed
weight, mirroring `AnalysisAggregator._overall_score`: a generator that
is itself unsure should sway the combined result less, independent of
how much weight it was configured with.

Unavailable generators
-----------------------
Any of the injected generators may raise `signals.exceptions.
InsufficientSignalDataError` for a given context (e.g. the specific
`AnalysisResult` it looks for is absent). `SignalAggregator` catches
that per-generator and treats it as "this generator produced no
signal" rather than failing the whole aggregation --
`metadata["generators_missing"]` records which generators were
unavailable and why. `SignalAggregator` itself only raises
`InsufficientSignalDataError` when *none* of the injected generators
produced a usable `SignalResult`.

Boundaries
----------
No AI: only weighted arithmetic combination of already-computed
signals. No Risk Engine: nothing here sizes a position or evaluates
exposure. No Strategy Engine: a combined `SignalResult` is not an order
and is not `core.entities.signal.Signal`; deciding whether/how to act
on it remains the future `strategies/` package's job. No Order
Execution: nothing here places, cancels, or simulates a trade. No
trading decisions of any kind are made or implied by this module.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Optional, Sequence

from core.enums import SignalDirection

from signals.base import BaseSignalGenerator
from signals.context import SignalContext
from signals.exceptions import (
    InsufficientSignalDataError,
    SignalGeneratorConfigurationError,
)
from signals.result import SignalResult
from signals.technical_signal_generator import TechnicalSignalGenerator
from signals.utils import merge_metadata

#: Maps a `SignalDirection` onto a signed multiplier for aggregation --
#: `signals/` intentionally has no numeric score type of its own (unlike
#: `analysis.result.AnalysisResult.score`), so this mapping exists only
#: internally to this module, purely to combine `direction` + `strength`
#: pairs from multiple `SignalResult`s into one comparable value.
_DIRECTION_SIGN: dict[SignalDirection, float] = {
    SignalDirection.BUY: 1.0,
    SignalDirection.SELL: -1.0,
    SignalDirection.HOLD: 0.0,
}


class SignalAggregator(BaseSignalGenerator):
    """
    Combines the `SignalResult`s of one or more `BaseSignalGenerator`
    instances into one final `SignalResult`.

    Parameters:
        generators: The `BaseSignalGenerator` instances to combine, run
            against the same `SignalContext` in the given order.
            Defaults to a single plain `TechnicalSignalGenerator()`
            instance when omitted, matching the project's
            dependency-injection convention (see `AnalysisAggregator`).
            Each generator must have a unique `.name` -- pass a
            distinct `name=` to any generator instances that would
            otherwise collide (e.g. two `TechnicalSignalGenerator`s with
            different thresholds).
        weights: Optional per-generator weight overrides, keyed by each
            generator's `.name`. Missing keys default to `1.0`. Weights
            scale a generator's contribution to both the aggregated
            direction/strength and to the aggregated confidence. Must be
            finite and `>= 0.0`.
        buy_threshold: Aggregated signed score strictly above this value
            maps to `SignalDirection.BUY`. Must be a finite number in
            `(0.0, 1.0]`.
        sell_threshold: Aggregated signed score strictly below this
            value maps to `SignalDirection.SELL`. Must be a finite
            number in `[-1.0, 0.0)`. Scores at or between the two
            thresholds map to `SignalDirection.HOLD`.
        name: Generator name, forwarded to `BaseSignalGenerator`.

    Raises:
        SignalGeneratorConfigurationError: If `generators` is an empty
            sequence, contains a non-`BaseSignalGenerator` item, contains
            two generators with the same `.name`, if `weights` names an
            unknown generator or a non-numeric/negative/non-finite
            value, or if `buy_threshold`/`sell_threshold` are not finite
            numbers within their documented ranges.
    """

    def __init__(
        self,
        *,
        generators: Optional[Sequence[BaseSignalGenerator]] = None,
        weights: Optional[Mapping[str, float]] = None,
        buy_threshold: float = 0.2,
        sell_threshold: float = -0.2,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(name=name)
        self._generators: dict[str, BaseSignalGenerator] = self._validate_generators(generators)
        self.weights: dict[str, float] = self._validate_weights(weights, self._generators)
        self._validate_thresholds(buy_threshold, sell_threshold)
        self.buy_threshold = float(buy_threshold)
        self.sell_threshold = float(sell_threshold)

    # ------------------------------------------------------------------
    # BaseSignalGenerator API
    # ------------------------------------------------------------------
    def generate(self, context: SignalContext) -> SignalResult:
        self.validate_context(context)

        results: dict[str, SignalResult] = {}
        missing: dict[str, str] = {}

        for key, generator in self._generators.items():
            try:
                results[key] = generator.generate(context)
            except InsufficientSignalDataError as exc:
                missing[key] = str(exc)

        if not results:
            raise InsufficientSignalDataError(
                f"{self.name} requires at least one usable signal for "
                f"{context.symbol}/{context.timeframe}, but all "
                f"{len(self._generators)} generator(s) were unavailable: "
                f"{sorted(missing)}."
            )

        score = self._aggregate_score(results)
        confidence = self._aggregate_confidence(results)
        direction = self._direction_for_score(score)
        strength = _clip(abs(score), 0.0, 1.0)

        contributing = sorted(results)
        summary = (
            f"{_score_label(score).capitalize()} aggregated signal for "
            f"{context.symbol}/{context.timeframe} "
            f"(score={score:.2f}, confidence={confidence:.2f}) "
            f"combining {', '.join(contributing)}"
            + (f"; missing: {', '.join(sorted(missing))}" if missing else "")
            + "."
        )

        metadata = self._build_metadata(
            results=results,
            missing=missing,
            score=score,
            confidence=confidence,
        )

        return self._build_result(
            direction=direction,
            strength=strength,
            confidence=confidence,
            summary=summary,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Score / confidence merging
    # ------------------------------------------------------------------
    def _aggregate_score(self, results: Mapping[str, SignalResult]) -> float:
        # Each contributing generator's own confidence further scales
        # its contribution: a signal the generator itself trusts less
        # should sway the combined score less, on top of the fixed
        # per-generator `weights` -- mirrors `AnalysisAggregator._overall_score`.
        components = [
            (_signed_strength(result), self.weights[key] * result.confidence)
            for key, result in results.items()
        ]
        return _clip(_weighted_average(components))

    def _aggregate_confidence(self, results: Mapping[str, SignalResult]) -> float:
        if not results:
            return 0.0
        confidence_components = [
            (result.confidence, self.weights[key]) for key, result in results.items()
        ]
        avg_confidence = _weighted_average(confidence_components)
        completeness = _completeness_ratio(len(results), len(self._generators))
        conviction = _mean_abs(_signed_strength(result) for result in results.values())
        # Mirrors `AnalysisAggregator._overall_confidence`'s shape:
        # completeness * conviction * average confidence, so a single
        # missing generator alone never zeroes out confidence, but no
        # directional agreement at all legitimately produces a low one.
        return _clip(completeness * conviction * avg_confidence, 0.0, 1.0)

    def _direction_for_score(self, score: float) -> SignalDirection:
        if score > self.buy_threshold:
            return SignalDirection.BUY
        if score < self.sell_threshold:
            return SignalDirection.SELL
        return SignalDirection.HOLD

    # ------------------------------------------------------------------
    # Metadata assembly
    # ------------------------------------------------------------------
    def _build_metadata(
        self,
        *,
        results: Mapping[str, SignalResult],
        missing: Mapping[str, str],
        score: float,
        confidence: float,
    ) -> dict[str, Any]:
        components: dict[str, Any] = {}
        for key in self._generators:
            if key in results:
                result = results[key]
                components[key] = {
                    "available": True,
                    "direction": result.direction.value,
                    "strength": result.strength,
                    "confidence": result.confidence,
                    "summary": result.summary,
                    "metadata": result.metadata,
                    "weight": self.weights[key],
                }
            else:
                components[key] = {
                    "available": False,
                    "reason": missing.get(key, "no signal produced"),
                    "weight": self.weights[key],
                }

        aggregation_details = {
            "method": (
                "confidence-and-weight-weighted average of each component signal's "
                "signed (direction * strength) value, thresholded into "
                "Bullish/Bearish/Neutral"
            ),
            "aggregate_score": score,
            "score_label": _score_label(score),
            "buy_threshold": self.buy_threshold,
            "sell_threshold": self.sell_threshold,
            "completeness_ratio": _completeness_ratio(len(results), len(self._generators)),
            "conviction": _mean_abs(_signed_strength(result) for result in results.values()),
        }

        return merge_metadata(
            {
                "score_scale": "-1.0 (strong bearish) .. 0.0 (neutral) .. +1.0 (strong bullish)",
                "confidence_scale": "0.0 (no confidence) .. 1.0 (full confidence)",
                "weights": dict(self.weights),
                "generators_available": sorted(results),
                "generators_missing": sorted(missing),
                "aggregation_details": aggregation_details,
                "components": components,
            }
        )

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_generators(
        generators: Optional[Sequence[BaseSignalGenerator]],
    ) -> dict[str, BaseSignalGenerator]:
        items: list[BaseSignalGenerator] = (
            list(generators) if generators is not None else [TechnicalSignalGenerator()]
        )
        if not items:
            raise SignalGeneratorConfigurationError(
                "SignalAggregator requires at least one generator; got an empty sequence."
            )
        ordered: dict[str, BaseSignalGenerator] = {}
        for index, generator in enumerate(items):
            if not isinstance(generator, BaseSignalGenerator):
                raise SignalGeneratorConfigurationError(
                    f"generators[{index}] must be a BaseSignalGenerator, "
                    f"got {type(generator).__name__}"
                )
            if generator.name in ordered:
                raise SignalGeneratorConfigurationError(
                    f"Duplicate generator name {generator.name!r}; every generator "
                    "combined by SignalAggregator must have a unique name (pass a "
                    "distinct name= to disambiguate multiple instances of the same "
                    "generator class)."
                )
            ordered[generator.name] = generator
        return ordered

    @staticmethod
    def _validate_weights(
        weights: Optional[Mapping[str, float]],
        generators: Mapping[str, BaseSignalGenerator],
    ) -> dict[str, float]:
        merged: dict[str, float] = {key: 1.0 for key in generators}
        if weights is None:
            return merged
        for key, value in weights.items():
            if key not in generators:
                raise SignalGeneratorConfigurationError(
                    f"Unknown weight key {key!r}; expected one of {sorted(generators)}"
                )
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise SignalGeneratorConfigurationError(
                    f"weights[{key!r}] must be numeric, got {type(value).__name__}"
                )
            numeric_value = float(value)
            if not math.isfinite(numeric_value) or numeric_value < 0.0:
                raise SignalGeneratorConfigurationError(
                    f"weights[{key!r}] must be a finite number >= 0.0, got {value!r}"
                )
            merged[key] = numeric_value
        return merged

    @staticmethod
    def _validate_thresholds(buy_threshold: Any, sell_threshold: Any) -> None:
        for value, label, lo, hi in (
            (buy_threshold, "buy_threshold", 0.0, 1.0),
            (sell_threshold, "sell_threshold", -1.0, 0.0),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise SignalGeneratorConfigurationError(
                    f"{label} must be numeric, got {type(value).__name__}"
                )
            numeric_value = float(value)
            if not math.isfinite(numeric_value):
                raise SignalGeneratorConfigurationError(
                    f"{label} must be finite, got {numeric_value}"
                )
            if not (lo <= numeric_value <= hi):
                raise SignalGeneratorConfigurationError(
                    f"{label} must be within [{lo}, {hi}], got {numeric_value}"
                )
        if float(buy_threshold) <= 0.0:
            raise SignalGeneratorConfigurationError(
                f"buy_threshold must be > 0.0, got {buy_threshold}"
            )
        if float(sell_threshold) >= 0.0:
            raise SignalGeneratorConfigurationError(
                f"sell_threshold must be < 0.0, got {sell_threshold}"
            )


# ----------------------------------------------------------------------
# Module-level numeric helpers
# ----------------------------------------------------------------------
# Deliberately local to this module rather than added to `signals/utils.py`
# (Signal Engine Part 1, left unmodified): these mirror the small, pure
# helpers `analysis/technical/utils.py` provides for `AnalysisAggregator`,
# but nothing in `signals/` needed a weighted-average/conviction helper
# before this module existed.
def _clip(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    """Clamp `value` to the closed range `[lo, hi]`."""
    return max(lo, min(hi, float(value)))


def _weighted_average(components: Sequence[tuple[float, float]]) -> float:
    """
    Combine `(value, weight)` pairs into a single weighted average.

    Returns `0.0` if `components` is empty or every weight is `0.0`,
    rather than raising a division-by-zero error.
    """
    total_weight = sum(weight for _, weight in components)
    if total_weight == 0:
        return 0.0
    return sum(value * weight for value, weight in components) / total_weight


def _mean_abs(values: Iterable[float]) -> float:
    """
    Return the mean of the absolute values in `values` ("conviction"):
    how far, on average, a set of signed `[-1.0, 1.0]` component values
    lean away from neutral, regardless of direction.

    Returns `0.0` for an empty input.
    """
    values = list(values)
    if not values:
        return 0.0
    return sum(abs(v) for v in values) / len(values)


def _completeness_ratio(available: int, expected: int) -> float:
    """
    Fraction of expected generators that actually produced a usable
    signal, clipped to `[0.0, 1.0]`. Returns `0.0` if `expected <= 0`.
    """
    if expected <= 0:
        return 0.0
    return _clip(available / expected, 0.0, 1.0)


def _score_label(score: float) -> str:
    """
    Translate a signed aggregated `[-1.0, 1.0]` score into a short,
    human-readable label for `SignalResult.summary` text. Thresholds
    match `analysis.technical.utils.score_label`'s bands for consistency
    across the codebase.
    """
    if score >= 0.5:
        return "strong bullish"
    if score >= 0.15:
        return "mild bullish"
    if score > -0.15:
        return "neutral"
    if score > -0.5:
        return "mild bearish"
    return "strong bearish"


def _signed_strength(result: SignalResult) -> float:
    """Combine a `SignalResult`'s `direction` and `strength` into one signed `[-1.0, 1.0]` value."""
    return _DIRECTION_SIGN[result.direction] * result.strength
