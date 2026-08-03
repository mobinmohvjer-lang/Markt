"""
strategies/aggregator.py

Defines `StrategyAggregator`: Strategy Engine Part 3. Combines multiple
`StrategyResult`s -- produced by one or more injected `BaseStrategy`
instances -- into a single, final `StrategyResult` for one
`StrategyContext`.

This module does not add any new decision logic of its own: it holds
an ordered collection of existing `BaseStrategy` instances
(constructor-injectable, matching the project's dependency-injection
convention -- defaulting to a single `BasicStrategy` when none are
supplied), runs each against the given `StrategyContext` in order, and
merges their individual `StrategyResult`s. Nothing in
`strategies/base_strategy.py`, `strategies/context.py`,
`strategies/result.py`, `strategies/exceptions.py`, `strategies/
utils.py`, or `strategies/basic_strategy.py` (Strategy Engine Parts 1
and 2) is modified or subclassed differently here.

Why this exists
----------------
`BasicStrategy` (Part 2) turns one `StrategyContext` into a single
`StrategyResult`. Once more than one `BaseStrategy` instance is in
play -- e.g. several `BasicStrategy`s configured with different
thresholds, or a future trend-following/mean-reversion strategy --
something needs to combine their independent `StrategyResult`s into
one final decision. `StrategyAggregator` is that combiner, mirroring
the role `analysis.aggregator.AnalysisAggregator` and `signals.
aggregator.SignalAggregator` already play one and two layers down,
respectively.

Weighted aggregation
---------------------
Each sub-strategy is identified by its own `.name` (the same value
`BaseStrategy.__init__` already assigns/accepts) and may be assigned a
`weight` (default `1.0`, must be finite and `>= 0.0`) via the
`weights` constructor parameter, keyed by that name. A sub-strategy's
own `confidence` further scales its contribution on top of its fixed
weight, the same "fixed weight x own confidence" shape `SignalAggregator`
already uses one layer down.

Since `StrategyResult` deliberately carries no numeric score/strength
field (only a categorical `action` and a `confidence`), each
sub-strategy's contribution is represented as a signed unit value
(`+1.0` BUY, `-1.0` SELL, `0.0` HOLD) rather than a signed magnitude --
`confidence` is what scales how much that unit value counts, both in
the aggregated score and in the aggregated confidence.

Unavailable strategies
-----------------------
Any of the injected strategies may raise `strategies.exceptions.
InsufficientStrategyDataError` for a given context (e.g. the specific
`AnalysisResult` it looks for is absent from the `StrategyContext`).
`StrategyAggregator` catches that per-strategy and treats it as "this
strategy produced no decision" rather than failing the whole
aggregation -- `metadata["strategies_missing"]` records which
strategies were unavailable and why. `StrategyAggregator` itself only
raises `InsufficientStrategyDataError` when *none* of the injected
strategies produced a usable `StrategyResult`.

Sequential, deterministic execution
------------------------------------
Sub-strategies are run one at a time, in the order they were supplied
(or injected), against the same `StrategyContext` -- no concurrency,
no wall-clock reads, no randomness, no I/O. The same context and the
same set of sub-strategies always produce the same aggregated
`StrategyResult`. Existing `StrategyResult` objects returned by
sub-strategies are only ever read, never mutated.

Calculated facets
-------------------
Every intermediate value this module computes is recorded in
`StrategyResult.metadata` for full traceability, in particular:

    - `overall_score`: confidence-and-weight-weighted average of each
      contributing sub-strategy's signed unit action, clipped to
      `[-1.0, 1.0]`.
    - `confidence`: `completeness x agreement x average confidence`,
      the same shape `AnalysisAggregator`/`SignalAggregator` already
      use one and two layers down, with `agreement` (see below) taking
      the role their `conviction` plays.
    - `completeness`: fraction of injected sub-strategies that
      actually produced a usable `StrategyResult`.
    - `agreement`: weighted average of how much each contributing
      sub-strategy's own `action` agrees with the aggregate's final
      `action` (`1.0` exact match, `0.5` one side is `HOLD`, `0.0`
      direct opposition) -- the same 1.0/0.5/0.0 agreement scale
      `BasicStrategy._agreement` already uses one layer down.

Boundaries
----------
No AI: only weighted arithmetic combination of already-computed
decisions. No order execution, no broker integration: nothing here
places, cancels, or simulates a trade. No portfolio management: this
module never reads a `Portfolio` or sizes anything. No optimization:
thresholds/weights are simple, caller-configurable constants, never
fit or searched over. No new decision logic of its own beyond merging
-- reuses Parts 1-2 exactly as they exist, without modifying either of
them.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Optional, Sequence

from core.enums import SignalDirection

from strategies.base_strategy import BaseStrategy
from strategies.basic_strategy import BasicStrategy
from strategies.context import StrategyContext
from strategies.exceptions import (
    InsufficientStrategyDataError,
    StrategyConfigurationError,
)
from strategies.result import StrategyResult
from strategies.utils import merge_metadata

#: Maps a `core.enums.SignalDirection` onto a signed unit multiplier --
#: `StrategyResult` intentionally has no numeric score/strength field
#: (unlike `signals.result.SignalResult.strength`), so this mapping
#: exists only internally to this module, purely to combine several
#: `StrategyResult.action` values (each scaled by that result's own
#: `confidence`) into one comparable aggregate value.
_ACTION_SIGN: dict[SignalDirection, float] = {
    SignalDirection.BUY: 1.0,
    SignalDirection.SELL: -1.0,
    SignalDirection.HOLD: 0.0,
}


class StrategyAggregator(BaseStrategy):
    """
    Combines the `StrategyResult`s of one or more `BaseStrategy`
    instances into one final `StrategyResult`.

    Parameters:
        strategies: The `BaseStrategy` instances to combine, run
            against the same `StrategyContext` in the given order.
            Defaults to a single plain `BasicStrategy()` instance when
            omitted, matching the project's dependency-injection
            convention (see `AnalysisAggregator`/`SignalAggregator`).
            Each strategy must have a unique `.name` -- pass a
            distinct `name=` to any strategy instances that would
            otherwise collide (e.g. two `BasicStrategy`s with
            different thresholds).
        weights: Optional per-strategy weight overrides, keyed by each
            strategy's `.name`. Missing keys default to `1.0`. Weights
            scale a strategy's contribution to both the aggregated
            score and the aggregated confidence. Must be finite and
            `>= 0.0`.
        buy_threshold: Aggregated signed score strictly above this
            value maps to `SignalDirection.BUY`. Must be a finite
            number in `(0.0, 1.0]`.
        sell_threshold: Aggregated signed score strictly below this
            value maps to `SignalDirection.SELL`. Must be a finite
            number in `[-1.0, 0.0)`. Scores at or between the two
            thresholds map to `SignalDirection.HOLD`.
        name: Strategy name, forwarded to `BaseStrategy`.

    Raises:
        StrategyConfigurationError: If `strategies` is an empty
            sequence, contains a non-`BaseStrategy` item, contains two
            strategies with the same `.name`, if `weights` names an
            unknown strategy or a non-numeric/negative/non-finite
            value, or if `buy_threshold`/`sell_threshold` are not
            finite numbers within their documented ranges.
    """

    def __init__(
        self,
        *,
        strategies: Optional[Sequence[BaseStrategy]] = None,
        weights: Optional[Mapping[str, float]] = None,
        buy_threshold: float = 0.2,
        sell_threshold: float = -0.2,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(name=name)
        self._strategies: dict[str, BaseStrategy] = self._validate_strategies(strategies)
        self.weights: dict[str, float] = self._validate_weights(weights, self._strategies)
        self._validate_thresholds(buy_threshold, sell_threshold)
        self.buy_threshold = float(buy_threshold)
        self.sell_threshold = float(sell_threshold)

    # ------------------------------------------------------------------
    # BaseStrategy API
    # ------------------------------------------------------------------
    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)

        results: dict[str, StrategyResult] = {}
        missing: dict[str, str] = {}

        # Executed sequentially, in injection order -- no concurrency.
        for key, strategy in self._strategies.items():
            try:
                results[key] = strategy.decide(context)
            except InsufficientStrategyDataError as exc:
                missing[key] = str(exc)

        if not results:
            raise InsufficientStrategyDataError(
                f"{self.name} requires at least one usable strategy decision for "
                f"{context.symbol}/{context.timeframe}, but all "
                f"{len(self._strategies)} strategy(ies) were unavailable: "
                f"{sorted(missing)}."
            )

        overall_score = self._aggregate_score(results)
        final_action = self._action_for_score(overall_score)
        completeness = _completeness_ratio(len(results), len(self._strategies))
        agreement = self._aggregate_agreement(results, final_action)
        confidence = self._aggregate_confidence(results, completeness, agreement)

        contributing = sorted(results)
        summary = (
            f"{final_action.value.upper()} aggregated strategy decision for "
            f"{context.symbol}/{context.timeframe} "
            f"(overall_score={overall_score:.2f}, confidence={confidence:.2f}, "
            f"completeness={completeness:.2f}, agreement={agreement:.2f}) "
            f"combining {', '.join(contributing)}"
            + (f"; missing: {', '.join(sorted(missing))}" if missing else "")
            + "."
        )

        metadata = self._build_metadata(
            results=results,
            missing=missing,
            overall_score=overall_score,
            final_action=final_action,
            completeness=completeness,
            agreement=agreement,
            confidence=confidence,
        )

        return self._build_result(
            action=final_action,
            confidence=confidence,
            summary=summary,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Score / completeness / agreement / confidence merging
    # ------------------------------------------------------------------
    def _aggregate_score(self, results: Mapping[str, StrategyResult]) -> float:
        # Each contributing strategy's own confidence scales its
        # contribution on top of its fixed `weights` entry: a decision
        # the strategy itself trusts less should sway the combined
        # score less -- mirrors `SignalAggregator._aggregate_score`.
        components = [
            (_ACTION_SIGN[result.action], self.weights[key] * result.confidence)
            for key, result in results.items()
        ]
        return _clip(_weighted_average(components))

    def _aggregate_agreement(
        self, results: Mapping[str, StrategyResult], final_action: SignalDirection
    ) -> float:
        # How much each contributing decision agrees with the final
        # aggregated action, weighted the same way the score is --
        # mirrors `BasicStrategy._agreement`'s 1.0/0.5/0.0 scale one
        # layer down, applied across every contributing strategy here
        # rather than between just two inputs.
        components = [
            (_agreement(result.action, final_action), self.weights[key])
            for key, result in results.items()
        ]
        return _clip(_weighted_average(components), 0.0, 1.0)

    def _aggregate_confidence(
        self,
        results: Mapping[str, StrategyResult],
        completeness: float,
        agreement: float,
    ) -> float:
        if not results:
            return 0.0
        confidence_components = [
            (result.confidence, self.weights[key]) for key, result in results.items()
        ]
        avg_confidence = _weighted_average(confidence_components)
        # Mirrors `AnalysisAggregator`/`SignalAggregator`'s
        # completeness x conviction x confidence shape, with
        # `agreement` (an explicit, separately-reported facet here)
        # taking the role their `conviction` plays: a single missing
        # strategy alone never zeroes out confidence, but contributing
        # strategies that disagree with each other legitimately
        # produce a low one.
        return _clip(completeness * agreement * avg_confidence, 0.0, 1.0)

    def _action_for_score(self, score: float) -> SignalDirection:
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
        results: Mapping[str, StrategyResult],
        missing: Mapping[str, str],
        overall_score: float,
        final_action: SignalDirection,
        completeness: float,
        agreement: float,
        confidence: float,
    ) -> dict[str, Any]:
        components: dict[str, Any] = {}
        for key in self._strategies:
            if key in results:
                result = results[key]
                components[key] = {
                    "available": True,
                    "action": result.action.value,
                    "confidence": result.confidence,
                    "summary": result.summary,
                    "metadata": result.metadata,
                    "weight": self.weights[key],
                    "agreement_with_final": _agreement(result.action, final_action),
                }
            else:
                components[key] = {
                    "available": False,
                    "reason": missing.get(key, "no decision produced"),
                    "weight": self.weights[key],
                }

        aggregation_details = {
            "method": (
                "confidence-and-weight-weighted average of each component strategy's "
                "signed unit action, thresholded into BUY/SELL/HOLD"
            ),
            "overall_score": overall_score,
            "score_label": _score_label(overall_score),
            "final_action": final_action.value,
            "buy_threshold": self.buy_threshold,
            "sell_threshold": self.sell_threshold,
            "completeness": completeness,
            "agreement": agreement,
        }

        return merge_metadata(
            {
                "score_scale": "-1.0 (strong bearish) .. 0.0 (neutral) .. +1.0 (strong bullish)",
                "confidence_scale": "0.0 (no confidence) .. 1.0 (full confidence)",
                "overall_score": overall_score,
                "completeness": completeness,
                "agreement": agreement,
                "weights": dict(self.weights),
                "strategies_available": sorted(results),
                "strategies_missing": sorted(missing),
                "aggregation_details": aggregation_details,
                "components": components,
            }
        )

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_strategies(
        strategies: Optional[Sequence[BaseStrategy]],
    ) -> dict[str, BaseStrategy]:
        items: list[BaseStrategy] = list(strategies) if strategies is not None else [BasicStrategy()]
        if not items:
            raise StrategyConfigurationError(
                "StrategyAggregator requires at least one strategy; got an empty sequence."
            )
        ordered: dict[str, BaseStrategy] = {}
        for index, strategy in enumerate(items):
            if not isinstance(strategy, BaseStrategy):
                raise StrategyConfigurationError(
                    f"strategies[{index}] must be a BaseStrategy, got {type(strategy).__name__}"
                )
            if strategy.name in ordered:
                raise StrategyConfigurationError(
                    f"Duplicate strategy name {strategy.name!r}; every strategy "
                    "combined by StrategyAggregator must have a unique name (pass a "
                    "distinct name= to disambiguate multiple instances of the same "
                    "strategy class)."
                )
            ordered[strategy.name] = strategy
        return ordered

    @staticmethod
    def _validate_weights(
        weights: Optional[Mapping[str, float]],
        strategies: Mapping[str, BaseStrategy],
    ) -> dict[str, float]:
        merged: dict[str, float] = {key: 1.0 for key in strategies}
        if weights is None:
            return merged
        for key, value in weights.items():
            if key not in strategies:
                raise StrategyConfigurationError(
                    f"Unknown weight key {key!r}; expected one of {sorted(strategies)}"
                )
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise StrategyConfigurationError(
                    f"weights[{key!r}] must be numeric, got {type(value).__name__}"
                )
            numeric_value = float(value)
            if not math.isfinite(numeric_value) or numeric_value < 0.0:
                raise StrategyConfigurationError(
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
                raise StrategyConfigurationError(
                    f"{label} must be numeric, got {type(value).__name__}"
                )
            numeric_value = float(value)
            if not math.isfinite(numeric_value):
                raise StrategyConfigurationError(f"{label} must be finite, got {numeric_value}")
            if not (lo <= numeric_value <= hi):
                raise StrategyConfigurationError(
                    f"{label} must be within [{lo}, {hi}], got {numeric_value}"
                )
        if float(buy_threshold) <= 0.0:
            raise StrategyConfigurationError(f"buy_threshold must be > 0.0, got {buy_threshold}")
        if float(sell_threshold) >= 0.0:
            raise StrategyConfigurationError(f"sell_threshold must be < 0.0, got {sell_threshold}")


# ----------------------------------------------------------------------
# Module-level numeric helpers
# ----------------------------------------------------------------------
# Deliberately local to this module rather than added to
# `strategies/utils.py` (Strategy Engine Parts 1-2, left unmodified):
# these mirror the small, pure helpers `signals/aggregator.py` and
# `analysis/technical/utils.py` provide for their own aggregators, but
# nothing in `strategies/` needed a weighted-average/agreement helper
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


def _completeness_ratio(available: int, expected: int) -> float:
    """
    Fraction of expected strategies that actually produced a usable
    decision, clipped to `[0.0, 1.0]`. Returns `0.0` if `expected <= 0`.
    """
    if expected <= 0:
        return 0.0
    return _clip(available / expected, 0.0, 1.0)


def _agreement(action_a: SignalDirection, action_b: SignalDirection) -> float:
    """
    Score how much two actions agree, on `0.0`..`1.0`.

    `1.0` when they match exactly, `0.5` when one is `HOLD` and the
    other is `BUY`/`SELL` (partial disagreement), `0.0` when they are
    directly opposed (`BUY` vs `SELL`) -- the same scale
    `BasicStrategy._agreement` already uses one layer down.
    """
    if action_a == action_b:
        return 1.0
    if SignalDirection.HOLD in (action_a, action_b):
        return 0.5
    return 0.0


def _score_label(score: float) -> str:
    """
    Translate a signed aggregated `[-1.0, 1.0]` score into a short,
    human-readable label for `StrategyResult.summary` text. Thresholds
    match `analysis.technical.utils.score_label`'s / `signals.
    aggregator._score_label`'s bands for consistency across the
    codebase.
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


def _mean_abs(values: Iterable[float]) -> float:
    """
    Return the mean of the absolute values in `values`: how far, on
    average, a set of signed values lean away from neutral, regardless
    of direction. Returns `0.0` for an empty input.

    Not used in the current confidence shape (`agreement` takes that
    role instead, per Strategy Engine Part 3's requirements), but kept
    for parity with `signals.aggregator._mean_abs` should a future
    consumer of this module want a conviction-style figure directly.
    """
    values = list(values)
    if not values:
        return 0.0
    return sum(abs(v) for v in values) / len(values)
