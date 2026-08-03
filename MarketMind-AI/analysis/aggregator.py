"""
analysis/aggregator.py

Defines `AnalysisAggregator`: Analysis Engine Part 4. Combines the five
independent `analysis.technical` analyzer outputs -- `TrendAnalyzer`,
`MomentumAnalyzer`, `VolatilityAnalyzer`, `VolumeAnalyzer`, and
`MarketStructureAnalyzer` -- into a single final `analysis.AnalysisResult`
for one `AnalysisContext`.

This module does not add any new analytical logic of its own: it holds
one instance of each of the five existing analyzers (constructor-
injectable, matching the project's dependency-injection convention),
runs each against the given `AnalysisContext`, and merges their
individual `AnalysisResult`s. Parts 1, 2, 3A, 3B, and 3C are consumed
exactly as they already exist -- nothing in `analysis/base.py`,
`analysis/context.py`, `analysis/result.py`, `analysis/exceptions.py`,
`analysis/utils.py`, or any file under `analysis/technical/` is
modified or subclassed differently here.

Directional vs. regime scores
------------------------------
Four of the five sub-analyzers produce a *directional* score on
`-1.0` (bearish) .. `0.0` (neutral) .. `+1.0` (bullish): `TrendAnalyzer`,
`MomentumAnalyzer`, `VolumeAnalyzer`, `MarketStructureAnalyzer`.
`VolatilityAnalyzer` (Part 3A) is documented as producing a direction-
*free* volatility-regime score instead (`-1.0` contraction/range-bound
.. `0.0` normal .. `+1.0` expansion/breakout-prone) -- see
`analysis/technical/volatility_analyzer.py` and `PROJECT_STATE.md`.

Averaging a regime score into a directional score would silently
misrepresent both, so `AnalysisAggregator` keeps them separate:

    - `overall_score` (the final directional verdict) is a
      confidence-weighted average of only the four directional
      sub-scores that were actually available.
    - `VolatilityAnalyzer`'s output is still fully merged into
      `confidence` (its own confidence counts like any other analyzer's)
      and into `metadata` (under `"volatility"`, with an explicit
      `"contributes_to_directional_score": False` flag) -- it is simply
      never averaged into `overall_score` itself.

Missing analyzers
------------------
Any of the five sub-analyzers may raise
`analysis.exceptions.InsufficientDataError` for a given context (e.g. a
required indicator is absent). `AnalysisAggregator` catches that
per-analyzer and treats it as "this analyzer had no result" rather than
failing the whole aggregation -- `overall_score`/`confidence` are
computed from whichever subset remains, and `metadata["missing"]`
records which analyzers were unavailable and why. `AnalysisAggregator`
itself only raises `InsufficientDataError` when *none* of the four
directional analyzers produced a result (a volatility-only result
carries no directional information to aggregate).

No AI, no news, no signal generation, no trading decisions: this stays
strictly at the "combine existing interpretations into one interpretation"
level, the same boundary every `analysis/` module respects.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from analysis.base import BaseAnalyzer
from analysis.context import AnalysisContext
from analysis.exceptions import AnalyzerConfigurationError, InsufficientDataError
from analysis.result import AnalysisResult
from analysis.technical import (
    MarketStructureAnalyzer,
    MomentumAnalyzer,
    TrendAnalyzer,
    VolatilityAnalyzer,
    VolumeAnalyzer,
)
from analysis.technical.utils import (
    clip,
    completeness_ratio,
    is_finite_number,
    mean_abs,
    score_label,
    weighted_average,
)

#: The four sub-analyzer keys whose scores are directional
#: (bearish/bullish) and therefore eligible for `overall_score` averaging.
_DIRECTIONAL_KEYS: tuple[str, ...] = ("trend", "momentum", "volume", "market_structure")

#: All five sub-analyzer keys this aggregator combines, in a fixed,
#: documented order used for iteration and metadata output.
_ALL_KEYS: tuple[str, ...] = (
    "trend",
    "momentum",
    "volatility",
    "volume",
    "market_structure",
)

#: Equal-weight default -- no sub-analyzer is treated as inherently more
#: important than another out of the box. Callers can override via the
#: `weights` constructor parameter.
_DEFAULT_WEIGHTS: dict[str, float] = {key: 1.0 for key in _ALL_KEYS}


class AnalysisAggregator(BaseAnalyzer):
    """
    Combines `TrendAnalyzer`, `MomentumAnalyzer`, `VolatilityAnalyzer`,
    `VolumeAnalyzer`, and `MarketStructureAnalyzer` into one final
    `AnalysisResult`.

    Parameters:
        trend_analyzer / momentum_analyzer / volatility_analyzer /
            volume_analyzer / market_structure_analyzer: Sub-analyzer
            instances to use. Each defaults to a plain instance of the
            corresponding `analysis.technical` class, but can be
            injected (e.g. a fake, or one configured with non-default
            indicator names) -- matching the project's constructor-
            injection convention.
        weights: Optional per-analyzer weight overrides, keyed by
            `"trend"`, `"momentum"`, `"volatility"`, `"volume"`,
            `"market_structure"`. Missing keys default to `1.0`.
            Weights scale both a sub-analyzer's contribution to
            `overall_score` (directional analyzers only) and to
            `confidence` (all five). Must be finite and `>= 0.0`.
        name: Analyzer name, forwarded to `BaseAnalyzer`.

    Raises:
        AnalyzerConfigurationError: If `weights` contains a key outside
            the five recognized analyzer names, or a non-numeric/
            negative/non-finite weight value.
    """

    def __init__(
        self,
        *,
        trend_analyzer: Optional[BaseAnalyzer] = None,
        momentum_analyzer: Optional[BaseAnalyzer] = None,
        volatility_analyzer: Optional[BaseAnalyzer] = None,
        volume_analyzer: Optional[BaseAnalyzer] = None,
        market_structure_analyzer: Optional[BaseAnalyzer] = None,
        weights: Optional[Mapping[str, float]] = None,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(name=name)
        self._analyzers: dict[str, BaseAnalyzer] = {
            "trend": trend_analyzer or TrendAnalyzer(),
            "momentum": momentum_analyzer or MomentumAnalyzer(),
            "volatility": volatility_analyzer or VolatilityAnalyzer(),
            "volume": volume_analyzer or VolumeAnalyzer(),
            "market_structure": market_structure_analyzer or MarketStructureAnalyzer(),
        }
        self.weights = self._validate_weights(weights)

    # ------------------------------------------------------------------
    # BaseAnalyzer API
    # ------------------------------------------------------------------
    def analyze(self, context: AnalysisContext) -> AnalysisResult:
        self.validate_context(context)

        sub_results: dict[str, AnalysisResult] = {}
        missing: dict[str, str] = {}

        for key, analyzer in self._analyzers.items():
            try:
                sub_results[key] = analyzer.analyze(context)
            except InsufficientDataError as exc:
                missing[key] = str(exc)

        directional_available = {
            key: sub_results[key] for key in _DIRECTIONAL_KEYS if key in sub_results
        }
        if not directional_available:
            raise InsufficientDataError(
                f"{self.name} requires at least one of the directional analyzers "
                f"({', '.join(_DIRECTIONAL_KEYS)}) to produce a result; all were "
                f"unavailable for {context.symbol}/{context.timeframe}."
            )

        overall_score = self._overall_score(directional_available)
        confidence = self._overall_confidence(sub_results, directional_available)

        contributing = sorted(directional_available)
        summary = (
            f"Overall market view is {score_label(overall_score)} "
            f"(score={overall_score:.2f}, confidence={confidence:.2f}) "
            f"combining {', '.join(contributing)}"
            + (f"; missing: {', '.join(sorted(missing))}" if missing else "")
            + "."
        )

        metadata = self._build_metadata(
            sub_results=sub_results,
            missing=missing,
            directional_available=directional_available,
            overall_score=overall_score,
            confidence=confidence,
        )

        return self._build_result(
            context,
            score=overall_score,
            confidence=confidence,
            summary=summary,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Score / confidence merging
    # ------------------------------------------------------------------
    def _overall_score(self, directional_available: Mapping[str, AnalysisResult]) -> float:
        # Each directional sub-analyzer's own confidence further scales
        # its contribution: a directional result the sub-analyzer itself
        # trusts less should sway the combined score less, on top of the
        # fixed per-analyzer `weights`.
        components = [
            (result.score, self.weights[key] * result.confidence)
            for key, result in directional_available.items()
        ]
        return clip(weighted_average(components))

    def _overall_confidence(
        self,
        sub_results: Mapping[str, AnalysisResult],
        directional_available: Mapping[str, AnalysisResult],
    ) -> float:
        if not sub_results:
            return 0.0
        confidence_components = [
            (result.confidence, self.weights[key]) for key, result in sub_results.items()
        ]
        avg_confidence = weighted_average(confidence_components)
        completeness = completeness_ratio(len(sub_results), len(_ALL_KEYS))
        conviction = mean_abs(result.score for result in directional_available.values())
        # Mirrors the shape used by the individual technical analyzers
        # (e.g. TrendAnalyzer): completeness * conviction * a confidence
        # factor, never letting a single missing input alone zero out
        # confidence, but letting *no direction at all* (conviction=0,
        # handled by the InsufficientDataError guard above for the
        # fully-empty case) legitimately produce a low score.
        return clip(completeness * conviction * avg_confidence, 0.0, 1.0)

    # ------------------------------------------------------------------
    # Metadata assembly
    # ------------------------------------------------------------------
    def _build_metadata(
        self,
        *,
        sub_results: Mapping[str, AnalysisResult],
        missing: Mapping[str, str],
        directional_available: Mapping[str, AnalysisResult],
        overall_score: float,
        confidence: float,
    ) -> dict[str, Any]:
        components: dict[str, Any] = {}
        for key in _ALL_KEYS:
            if key in sub_results:
                result = sub_results[key]
                components[key] = {
                    "available": True,
                    "analyzer_name": result.analyzer_name,
                    "score": result.score,
                    "confidence": result.confidence,
                    "summary": result.summary,
                    "metadata": result.metadata,
                    "weight": self.weights[key],
                    "contributes_to_directional_score": key in _DIRECTIONAL_KEYS,
                }
            else:
                components[key] = {
                    "available": False,
                    "reason": missing.get(key, "no result produced"),
                    "weight": self.weights[key],
                    "contributes_to_directional_score": key in _DIRECTIONAL_KEYS,
                }

        return {
            "score_scale": "-1.0 (strong bearish) .. 0.0 (neutral) .. +1.0 (strong bullish)",
            "confidence_scale": "0.0 (no confidence) .. 1.0 (full confidence)",
            "directional_components_used": sorted(directional_available),
            "components_available": sorted(sub_results),
            "components_missing": sorted(missing),
            "weights": dict(self.weights),
            "completeness_ratio": completeness_ratio(len(sub_results), len(_ALL_KEYS)),
            "conviction": mean_abs(result.score for result in directional_available.values()),
            "components": components,
            "volatility": components["volatility"],
        }

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_weights(weights: Optional[Mapping[str, float]]) -> dict[str, float]:
        merged = dict(_DEFAULT_WEIGHTS)
        if weights is None:
            return merged
        for key, value in weights.items():
            if key not in _ALL_KEYS:
                raise AnalyzerConfigurationError(
                    f"Unknown weight key {key!r}; expected one of {sorted(_ALL_KEYS)}"
                )
            if not is_finite_number(value) or float(value) < 0.0:
                raise AnalyzerConfigurationError(
                    f"weights[{key!r}] must be a finite number >= 0.0, got {value!r}"
                )
            merged[key] = float(value)
        return merged
