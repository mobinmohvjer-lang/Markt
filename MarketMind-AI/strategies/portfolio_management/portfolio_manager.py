"""
strategies/portfolio_management/portfolio_manager.py

Defines `PortfolioManager`: Portfolio Management Part 3. Combines
multiple `PortfolioResult`s -- produced by one or more injected
`BasePortfolioManager` instances -- into a single, final
`PortfolioResult` for one `PortfolioContext`.

This module does not add any new constraint-evaluation logic of its
own: it holds an ordered collection of existing `BasePortfolioManager`
instances (constructor-injectable, matching the project's
dependency-injection convention -- defaulting to a single
`BasicPortfolioManager` when none are supplied), runs each against the
given `PortfolioContext` in order, and merges their individual
`PortfolioResult`s. Nothing in `strategies/portfolio_management/base.py`,
`strategies/portfolio_management/context.py`,
`strategies/portfolio_management/result.py`,
`strategies/portfolio_management/exceptions.py`,
`strategies/portfolio_management/utils.py`, or
`strategies/portfolio_management/basic_portfolio_manager.py` (Portfolio
Management Parts 1 and 2) is modified or subclassed differently here.

Why this exists
----------------
`BasicPortfolioManager` (Part 2) turns one `PortfolioContext` into a
single `PortfolioResult`. Once more than one `BasePortfolioManager`
instance is in play -- e.g. several `BasicPortfolioManager`s configured
with different limits, or a future allocation-aware portfolio manager
-- something needs to combine their independent `PortfolioResult`s
into one final decision. `PortfolioManager` is that combiner,
mirroring the role `analysis.aggregator.AnalysisAggregator`,
`signals.aggregator.SignalAggregator`, and `strategies.aggregator.
StrategyAggregator` already play three, two, and one layer(s) down,
respectively.

Weighted vote, not weighted score
----------------------------------
Unlike `StrategyResult`/`SignalResult`/`AnalysisResult`, `PortfolioResult`
carries no numeric score/strength field -- only a boolean
`new_positions_allowed`. To stay consistent with the weighted-average
-and-threshold shape the three aggregators above already use, each
sub-manager's `new_positions_allowed` is represented as a signed unit
vote (`+1.0` allowed, `-1.0` blocked), scaled by a fixed per-manager
`weight` (default `1.0`, keyed by the manager's own `.name`, the same
convention `StrategyAggregator`/`SignalAggregator` use) and further
scaled by that manager's own `confidence` -- a decision a sub-manager
itself trusts less should sway the combined vote less. The resulting
weighted-average `aggregate_score` (`-1.0`..`+1.0`) is thresholded via
a configurable `allow_threshold` (default `0.0`: allowed only when the
weighted vote leans net-positive) back onto a final boolean
`new_positions_allowed`.

Unavailable managers
---------------------
Any of the injected managers may raise `strategies.portfolio_management.
exceptions.InsufficientPortfolioDataError` for a given context (e.g.
portfolio equity cannot be computed at all). `PortfolioManager` catches
that per-manager and treats it as "this manager produced no decision"
rather than failing the whole aggregation --
`metadata["managers_missing"]` records which managers were unavailable
and why. `PortfolioManager` itself only raises
`InsufficientPortfolioDataError` when *none* of the injected managers
produced a usable `PortfolioResult`.

Sequential, deterministic execution
------------------------------------
Sub-managers are run one at a time, in the order they were supplied
(or injected), against the same `PortfolioContext` -- no concurrency,
no wall-clock reads, no randomness, no I/O. The same context and the
same set of sub-managers always produce the same aggregated
`PortfolioResult`. Existing `PortfolioResult` objects returned by
sub-managers are only ever read, never mutated.

Calculated facets
-------------------
Every intermediate value this module computes is recorded in
`PortfolioResult.metadata` for full traceability, in particular:

    - `aggregate_score`: confidence-and-weight-weighted average of
      each contributing sub-manager's signed unit vote, clipped to
      `[-1.0, 1.0]`.
    - `confidence`: `completeness x agreement x average confidence`,
      the same shape `AnalysisAggregator`/`SignalAggregator`/
      `StrategyAggregator` already use, with `agreement` taking the
      role their `conviction`/`agreement` plays.
    - `completeness`: fraction of injected sub-managers that actually
      produced a usable `PortfolioResult`.
    - `agreement`: weighted average of how much each contributing
      sub-manager's own `new_positions_allowed` agrees with the
      aggregate's final decision (`1.0` match, `0.0` mismatch --
      a plain boolean agreement scale, since `new_positions_allowed`
      has no `HOLD`-style neutral third state the way
      `SignalDirection` does one layer up).

Boundaries
----------
No AI: only weighted arithmetic combination of already-computed
decisions. No order execution, no broker integration: nothing here
places, cancels, or simulates a trade. No allocation, no
position-sizing, no rebalancing -- those remain out of scope for
Portfolio Management, same as every other part in this package. No
optimization: `weights`/`allow_threshold` are simple,
caller-configurable constants, never fit or searched over. No new
decision logic of its own beyond merging -- reuses Parts 1-2 exactly
as they exist, without modifying either of them.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Optional, Sequence

from strategies.portfolio_management.base import BasePortfolioManager
from strategies.portfolio_management.basic_portfolio_manager import BasicPortfolioManager
from strategies.portfolio_management.context import PortfolioContext
from strategies.portfolio_management.exceptions import (
    InsufficientPortfolioDataError,
    PortfolioManagerConfigurationError,
)
from strategies.portfolio_management.result import PortfolioResult
from strategies.portfolio_management.utils import clip, merge_metadata


class PortfolioManager(BasePortfolioManager):
    """
    Combines the `PortfolioResult`s of one or more `BasePortfolioManager`
    instances into one final `PortfolioResult`.

    Parameters:
        managers: The `BasePortfolioManager` instances to combine, run
            against the same `PortfolioContext` in the given order.
            Defaults to a single plain `BasicPortfolioManager()`
            instance when omitted, matching the project's
            dependency-injection convention (see `AnalysisAggregator`/
            `SignalAggregator`/`StrategyAggregator`). Each manager must
            have a unique `.name` -- pass a distinct `name=` to any
            manager instances that would otherwise collide (e.g. two
            `BasicPortfolioManager`s with different limits).
        weights: Optional per-manager weight overrides, keyed by each
            manager's `.name`. Missing keys default to `1.0`. Weights
            scale a manager's contribution to both the aggregated vote
            and the aggregated confidence. Must be finite and `>= 0.0`.
        allow_threshold: Aggregated signed vote strictly above this
            value maps to `new_positions_allowed=True`; at or below it
            maps to `False`. Must be a finite number in `[-1.0, 1.0]`.
            Defaults to `0.0` (net-positive weighted vote required).
        name: Portfolio manager name, forwarded to `BasePortfolioManager`.

    Raises:
        PortfolioManagerConfigurationError: If `managers` is an empty
            sequence, contains a non-`BasePortfolioManager` item,
            contains two managers with the same `.name`, if `weights`
            names an unknown manager or a non-numeric/negative/
            non-finite value, or if `allow_threshold` is not a finite
            number within `[-1.0, 1.0]`.
    """

    def __init__(
        self,
        *,
        managers: Optional[Sequence[BasePortfolioManager]] = None,
        weights: Optional[Mapping[str, float]] = None,
        allow_threshold: float = 0.0,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(name=name)
        self._managers: dict[str, BasePortfolioManager] = self._validate_managers(managers)
        self.weights: dict[str, float] = self._validate_weights(weights, self._managers)
        self.allow_threshold = self._validate_allow_threshold(allow_threshold)

    # ------------------------------------------------------------------
    # BasePortfolioManager API
    # ------------------------------------------------------------------
    def evaluate(self, context: PortfolioContext) -> PortfolioResult:
        self.validate_context(context)

        results: dict[str, PortfolioResult] = {}
        missing: dict[str, str] = {}

        # Executed sequentially, in injection order -- no concurrency.
        for key, manager in self._managers.items():
            try:
                results[key] = manager.evaluate(context)
            except InsufficientPortfolioDataError as exc:
                missing[key] = str(exc)

        if not results:
            raise InsufficientPortfolioDataError(
                f"{self.name} requires at least one usable portfolio-manager decision "
                f"for {context.symbol}/{context.timeframe}, but all "
                f"{len(self._managers)} manager(s) were unavailable: {sorted(missing)}."
            )

        aggregate_score = self._aggregate_score(results)
        new_positions_allowed = aggregate_score > self.allow_threshold
        completeness = _completeness_ratio(len(results), len(self._managers))
        agreement = self._aggregate_agreement(results, new_positions_allowed)
        confidence = self._aggregate_confidence(results, completeness, agreement)

        contributing = sorted(results)
        decision = "Allowed" if new_positions_allowed else "Blocked"
        summary = (
            f"{decision}: aggregated portfolio-manager decision for "
            f"{context.symbol}/{context.timeframe} "
            f"(aggregate_score={aggregate_score:.2f}, confidence={confidence:.2f}, "
            f"completeness={completeness:.2f}, agreement={agreement:.2f}) "
            f"combining {', '.join(contributing)}"
            + (f"; missing: {', '.join(sorted(missing))}" if missing else "")
            + "."
        )

        metadata = self._build_metadata(
            results=results,
            missing=missing,
            aggregate_score=aggregate_score,
            new_positions_allowed=new_positions_allowed,
            completeness=completeness,
            agreement=agreement,
            confidence=confidence,
        )

        return self._build_result(
            new_positions_allowed=new_positions_allowed,
            confidence=confidence,
            summary=summary,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Score / completeness / agreement / confidence merging
    # ------------------------------------------------------------------
    def _aggregate_score(self, results: Mapping[str, PortfolioResult]) -> float:
        # Each contributing manager's own confidence scales its
        # contribution on top of its fixed `weights` entry: a decision
        # the manager itself trusts less should sway the combined vote
        # less -- mirrors `StrategyAggregator._aggregate_score`.
        components = [
            (1.0 if result.new_positions_allowed else -1.0, self.weights[key] * result.confidence)
            for key, result in results.items()
        ]
        return _clip(_weighted_average(components))

    def _aggregate_agreement(
        self, results: Mapping[str, PortfolioResult], final_decision: bool
    ) -> float:
        # How much each contributing decision agrees with the final
        # aggregated decision, weighted the same way the score is.
        # `new_positions_allowed` has no neutral third state (unlike
        # `SignalDirection.HOLD` one layer up), so this is a plain
        # 1.0/0.0 match scale rather than StrategyAggregator's
        # 1.0/0.5/0.0 one.
        components = [
            (1.0 if result.new_positions_allowed == final_decision else 0.0, self.weights[key])
            for key, result in results.items()
        ]
        return _clip(_weighted_average(components), 0.0, 1.0)

    def _aggregate_confidence(
        self,
        results: Mapping[str, PortfolioResult],
        completeness: float,
        agreement: float,
    ) -> float:
        if not results:
            return 0.0
        confidence_components = [
            (result.confidence, self.weights[key]) for key, result in results.items()
        ]
        avg_confidence = _weighted_average(confidence_components)
        # Mirrors `AnalysisAggregator`/`SignalAggregator`/
        # `StrategyAggregator`'s completeness x agreement/conviction x
        # confidence shape: a single missing manager alone never
        # zeroes out confidence, but contributing managers that
        # disagree with each other legitimately produce a low one.
        return clip(completeness * agreement * avg_confidence, 0.0, 1.0)

    # ------------------------------------------------------------------
    # Metadata assembly
    # ------------------------------------------------------------------
    def _build_metadata(
        self,
        *,
        results: Mapping[str, PortfolioResult],
        missing: Mapping[str, str],
        aggregate_score: float,
        new_positions_allowed: bool,
        completeness: float,
        agreement: float,
        confidence: float,
    ) -> dict[str, Any]:
        components: dict[str, Any] = {}
        for key in self._managers:
            if key in results:
                result = results[key]
                components[key] = {
                    "available": True,
                    "new_positions_allowed": result.new_positions_allowed,
                    "confidence": result.confidence,
                    "summary": result.summary,
                    "metadata": result.metadata,
                    "weight": self.weights[key],
                    "agreement_with_final": (
                        1.0 if result.new_positions_allowed == new_positions_allowed else 0.0
                    ),
                }
            else:
                components[key] = {
                    "available": False,
                    "reason": missing.get(key, "no decision produced"),
                    "weight": self.weights[key],
                }

        aggregation_details = {
            "method": (
                "confidence-and-weight-weighted vote of each component manager's "
                "signed new_positions_allowed decision, thresholded into a final bool"
            ),
            "aggregate_score": aggregate_score,
            "final_new_positions_allowed": new_positions_allowed,
            "allow_threshold": self.allow_threshold,
            "completeness": completeness,
            "agreement": agreement,
        }

        return merge_metadata(
            {
                "score_scale": "-1.0 (unanimous block) .. 0.0 (split) .. +1.0 (unanimous allow)",
                "confidence_scale": "0.0 (no confidence) .. 1.0 (full confidence)",
                "aggregate_score": aggregate_score,
                "completeness": completeness,
                "agreement": agreement,
                "weights": dict(self.weights),
                "managers_available": sorted(results),
                "managers_missing": sorted(missing),
                "aggregation_details": aggregation_details,
                "components": components,
            }
        )

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_managers(
        managers: Optional[Sequence[BasePortfolioManager]],
    ) -> dict[str, BasePortfolioManager]:
        items: list[BasePortfolioManager] = (
            list(managers) if managers is not None else [BasicPortfolioManager()]
        )
        if not items:
            raise PortfolioManagerConfigurationError(
                "PortfolioManager requires at least one manager; got an empty sequence."
            )
        ordered: dict[str, BasePortfolioManager] = {}
        for index, manager in enumerate(items):
            if not isinstance(manager, BasePortfolioManager):
                raise PortfolioManagerConfigurationError(
                    f"managers[{index}] must be a BasePortfolioManager, "
                    f"got {type(manager).__name__}"
                )
            if manager.name in ordered:
                raise PortfolioManagerConfigurationError(
                    f"Duplicate manager name {manager.name!r}; every manager combined "
                    "by PortfolioManager must have a unique name (pass a distinct "
                    "name= to disambiguate multiple instances of the same manager "
                    "class)."
                )
            ordered[manager.name] = manager
        return ordered

    @staticmethod
    def _validate_weights(
        weights: Optional[Mapping[str, float]],
        managers: Mapping[str, BasePortfolioManager],
    ) -> dict[str, float]:
        merged: dict[str, float] = {key: 1.0 for key in managers}
        if weights is None:
            return merged
        for key, value in weights.items():
            if key not in managers:
                raise PortfolioManagerConfigurationError(
                    f"Unknown weight key {key!r}; expected one of {sorted(managers)}"
                )
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PortfolioManagerConfigurationError(
                    f"weights[{key!r}] must be numeric, got {type(value).__name__}"
                )
            numeric_value = float(value)
            if not math.isfinite(numeric_value) or numeric_value < 0.0:
                raise PortfolioManagerConfigurationError(
                    f"weights[{key!r}] must be a finite number >= 0.0, got {value!r}"
                )
            merged[key] = numeric_value
        return merged

    @staticmethod
    def _validate_allow_threshold(value: Any) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PortfolioManagerConfigurationError(
                f"allow_threshold must be numeric, got {type(value).__name__}"
            )
        numeric_value = float(value)
        if not math.isfinite(numeric_value):
            raise PortfolioManagerConfigurationError(
                f"allow_threshold must be finite, got {numeric_value}"
            )
        if not (-1.0 <= numeric_value <= 1.0):
            raise PortfolioManagerConfigurationError(
                f"allow_threshold must be within [-1.0, 1.0], got {numeric_value}"
            )
        return numeric_value


# ----------------------------------------------------------------------
# Module-level numeric helpers
# ----------------------------------------------------------------------
# Deliberately local to this module rather than added to
# `strategies/portfolio_management/utils.py` (Portfolio Management
# Part 1, left unmodified): these mirror the small, pure helpers
# `strategies/aggregator.py`/`signals/aggregator.py`/
# `analysis/technical/utils.py` provide for their own aggregators, but
# nothing in `strategies/portfolio_management/` needed a
# weighted-average/completeness helper before this module existed.
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
    Fraction of expected managers that actually produced a usable
    decision, clipped to `[0.0, 1.0]`. Returns `0.0` if `expected <= 0`.
    """
    if expected <= 0:
        return 0.0
    return _clip(available / expected, 0.0, 1.0)
