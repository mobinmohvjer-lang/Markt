"""
analysis/technical/trend_analyzer.py

Defines `TrendAnalyzer`: the first concrete technical analyzer built on
top of the Analysis Engine foundation (`BaseAnalyzer`, `AnalysisContext`,
`AnalysisResult` -- Part 1). It interprets *trend-following* indicators
already computed by `indicators/` -- it never calculates them itself.

Inputs consumed (looked up on `AnalysisContext.indicators` by
`indicator_name`, matching the naming/value-key convention already used
by `indicators/base.py`'s default `IndicatorResult.name` --
``f"{ClassName}_{period}"`` -- and each indicator's own output keys):

    - SMA relationships: two `core.entities.indicator_result.IndicatorResult`
      entries (fast/slow), each with ``values = {"value": <float>}``.
      Default names: ``"SMA_20"`` (fast), ``"SMA_50"`` (slow).
    - EMA relationships: same shape as SMA. Default names: ``"EMA_12"``
      (fast), ``"EMA_26"`` (slow).
    - MACD trend: one entry with
      ``values = {"macd": ..., "signal": ..., "histogram": ...}``
      (matching `indicators.macd.MACD`'s output keys). Default name:
      ``"MACD_12_26_9"``.
    - ADX strength: one entry with ``values = {"adx": ..., "plus_di": ...,
      "minus_di": ...}`` (matching `indicators.adx.ADX`'s output keys;
      only ``"adx"`` is used here). Default name: ``"ADX_14"``.

All four indicators are optional independently -- `TrendAnalyzer` uses
whichever are present in the given `AnalysisContext` and lowers its
`confidence` accordingly. `analyze()` raises `InsufficientDataError`
only when *none* of the three directional inputs (SMA pair, EMA pair,
MACD) are available, since ADX alone carries no directional information.

Score: `-1.0` (strong bearish) .. `0.0` (neutral) .. `+1.0` (strong
bullish). Confidence: `0.0` .. `1.0`. See module-level docstrings in
`analysis/technical/utils.py` for the exact normalization formulas used.
"""

from __future__ import annotations

from typing import Any, Optional

from analysis.base import BaseAnalyzer
from analysis.context import AnalysisContext
from analysis.exceptions import InsufficientDataError
from analysis.result import AnalysisResult
from analysis.technical.utils import (
    clip,
    completeness_ratio,
    is_finite_number,
    mean_abs,
    normalize_diff,
    score_label,
    weighted_average,
)

#: Number of independent directional components this analyzer can use
#: (SMA pair, EMA pair, MACD). ADX is excluded: it measures trend
#: *strength*, not *direction*, and is handled separately below.
_MAX_DIRECTIONAL_COMPONENTS = 3


class TrendAnalyzer(BaseAnalyzer):
    """
    Interprets moving-average relationships, MACD, and ADX into a single
    trend `AnalysisResult`.

    Parameters:
        sma_fast_name / sma_slow_name: `indicator_name` of the fast/slow
            SMA `IndicatorResult` entries expected on the context.
            Defaults: ``"SMA_20"`` / ``"SMA_50"``.
        ema_fast_name / ema_slow_name: Same, for EMA. Defaults:
            ``"EMA_12"`` / ``"EMA_26"``.
        macd_name: `indicator_name` of the MACD `IndicatorResult` entry.
            Default: ``"MACD_12_26_9"``.
        adx_name: `indicator_name` of the ADX `IndicatorResult` entry.
            Default: ``"ADX_14"``.
        name: Analyzer name, forwarded to `BaseAnalyzer`.
    """

    def __init__(
        self,
        *,
        sma_fast_name: str = "SMA_20",
        sma_slow_name: str = "SMA_50",
        ema_fast_name: str = "EMA_12",
        ema_slow_name: str = "EMA_26",
        macd_name: str = "MACD_12_26_9",
        adx_name: str = "ADX_14",
        name: Optional[str] = None,
    ) -> None:
        super().__init__(name=name)
        self.sma_fast_name = sma_fast_name
        self.sma_slow_name = sma_slow_name
        self.ema_fast_name = ema_fast_name
        self.ema_slow_name = ema_slow_name
        self.macd_name = macd_name
        self.adx_name = adx_name

    # ------------------------------------------------------------------
    # BaseAnalyzer API
    # ------------------------------------------------------------------
    def analyze(self, context: AnalysisContext) -> AnalysisResult:
        self.validate_context(context)

        components: dict[str, float] = {}
        detail: dict[str, Any] = {}

        sma_score = self._sma_component(context, detail)
        if sma_score is not None:
            components["sma"] = sma_score

        ema_score = self._ema_component(context, detail)
        if ema_score is not None:
            components["ema"] = ema_score

        macd_score = self._macd_component(context, detail)
        if macd_score is not None:
            components["macd"] = macd_score

        if not components:
            raise InsufficientDataError(
                f"{self.name} requires at least one of SMA ({self.sma_fast_name}/"
                f"{self.sma_slow_name}), EMA ({self.ema_fast_name}/{self.ema_slow_name}), "
                f"or MACD ({self.macd_name}) to be present on the AnalysisContext; "
                f"none were found for {context.symbol}/{context.timeframe}."
            )

        adx_strength, adx_detail = self._adx_strength(context)
        detail["adx"] = adx_detail

        weighted = [(score, 1.0) for score in components.values()]
        overall_score = clip(weighted_average(weighted))

        conviction = mean_abs(components.values())
        completeness = completeness_ratio(len(components), _MAX_DIRECTIONAL_COMPONENTS)
        # ADX contributes a [0.5, 1.0] multiplier: even with no trend
        # strength data at all (adx_strength defaults to 0.5, see
        # `_adx_strength`), confidence is only halved, never zeroed --
        # ADX alone should never be the sole reason confidence collapses.
        strength_modifier = 0.5 + 0.5 * adx_strength
        confidence = clip(completeness * conviction * strength_modifier, 0.0, 1.0)

        summary = (
            f"Trend is {score_label(overall_score)} "
            f"(score={overall_score:.2f}, confidence={confidence:.2f}) "
            f"based on {', '.join(sorted(components))}."
        )

        metadata: dict[str, Any] = {
            "components_used": sorted(components),
            "component_scores": components,
            "completeness_ratio": completeness,
            "conviction": conviction,
            "strength_modifier": strength_modifier,
            "score_scale": "-1.0 (strong bearish) .. 0.0 (neutral) .. +1.0 (strong bullish)",
            "confidence_scale": "0.0 (no confidence) .. 1.0 (full confidence)",
            **detail,
        }

        return self._build_result(
            context,
            score=overall_score,
            confidence=confidence,
            summary=summary,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Component extraction
    # ------------------------------------------------------------------
    def _sma_component(self, context: AnalysisContext, detail: dict[str, Any]) -> Optional[float]:
        fast = self._value(context, self.sma_fast_name, "value")
        slow = self._value(context, self.sma_slow_name, "value")
        if fast is None or slow is None:
            detail["sma"] = {
                "used": False,
                "reason": "missing or incomplete SMA fast/slow indicators",
                "fast_indicator": self.sma_fast_name,
                "slow_indicator": self.sma_slow_name,
            }
            return None
        score = normalize_diff(fast, slow)
        detail["sma"] = {
            "used": True,
            "fast_indicator": self.sma_fast_name,
            "slow_indicator": self.sma_slow_name,
            "fast_value": fast,
            "slow_value": slow,
            "score": score,
            "explanation": (
                "Relative difference between fast and slow SMA, clipped to "
                "[-1, 1]; positive means the fast SMA is above the slow SMA "
                "(bullish crossover relationship)."
            ),
        }
        return score

    def _ema_component(self, context: AnalysisContext, detail: dict[str, Any]) -> Optional[float]:
        fast = self._value(context, self.ema_fast_name, "value")
        slow = self._value(context, self.ema_slow_name, "value")
        if fast is None or slow is None:
            detail["ema"] = {
                "used": False,
                "reason": "missing or incomplete EMA fast/slow indicators",
                "fast_indicator": self.ema_fast_name,
                "slow_indicator": self.ema_slow_name,
            }
            return None
        score = normalize_diff(fast, slow)
        detail["ema"] = {
            "used": True,
            "fast_indicator": self.ema_fast_name,
            "slow_indicator": self.ema_slow_name,
            "fast_value": fast,
            "slow_value": slow,
            "score": score,
            "explanation": (
                "Relative difference between fast and slow EMA, clipped to "
                "[-1, 1]; positive means the fast EMA is above the slow EMA "
                "(bullish crossover relationship)."
            ),
        }
        return score

    def _macd_component(self, context: AnalysisContext, detail: dict[str, Any]) -> Optional[float]:
        macd_line = self._value(context, self.macd_name, "macd")
        signal_line = self._value(context, self.macd_name, "signal")
        if macd_line is None or signal_line is None:
            detail["macd"] = {
                "used": False,
                "reason": "missing or incomplete MACD indicator",
                "indicator": self.macd_name,
            }
            return None
        score = normalize_diff(macd_line, signal_line)
        detail["macd"] = {
            "used": True,
            "indicator": self.macd_name,
            "macd_value": macd_line,
            "signal_value": signal_line,
            "score": score,
            "explanation": (
                "Relative difference between the MACD line and its signal "
                "line, clipped to [-1, 1]; positive means MACD is above its "
                "signal line (bullish momentum-of-trend)."
            ),
        }
        return score

    def _adx_strength(self, context: AnalysisContext) -> tuple[float, dict[str, Any]]:
        adx_value = self._value(context, self.adx_name, "adx")
        if adx_value is None:
            return 0.5, {
                "used": False,
                "reason": "missing ADX indicator; defaulting to a neutral 0.5 strength factor",
                "indicator": self.adx_name,
            }
        # ADX is conventionally read on a 0..100 scale where >= 25 is
        # considered a "trending" market and >= 50 a strong trend.
        # /50 gives ADX=25 -> 0.5 and ADX>=50 -> 1.0, a reasonable
        # continuous approximation of that convention.
        strength = clip(adx_value / 50.0, 0.0, 1.0)
        return strength, {
            "used": True,
            "indicator": self.adx_name,
            "adx_value": adx_value,
            "strength_factor": strength,
            "explanation": (
                "ADX measures trend strength, not direction, so it never "
                "contributes to the directional score -- only to how "
                "confident the analyzer is in the direction found above. "
                "ADX >= 25 is conventionally 'trending'; strength_factor = "
                "clip(adx / 50, 0, 1)."
            ),
        }

    @staticmethod
    def _value(context: AnalysisContext, indicator_name: str, key: str) -> Optional[float]:
        indicator = context.get_indicator(indicator_name)
        if indicator is None:
            return None
        value = indicator.values.get(key)
        if not is_finite_number(value):
            return None
        return float(value)
