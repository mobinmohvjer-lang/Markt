"""
analysis/technical/momentum_analyzer.py

Defines `MomentumAnalyzer`: the second concrete technical analyzer built
on top of the Analysis Engine foundation (`BaseAnalyzer`,
`AnalysisContext`, `AnalysisResult` -- Part 1). It interprets
*momentum/oscillator* indicators already computed by `indicators/` -- it
never calculates them itself.

Inputs consumed (looked up on `AnalysisContext.indicators` by
`indicator_name`, matching the naming/value-key convention already used
by `indicators/base.py`'s default `IndicatorResult.name` and each
indicator's own output keys):

    - RSI: one entry with ``values = {"value": <float 0..100>}``.
      Default name: ``"RSI_14"``.
    - ROC: one entry with ``values = {"value": <float, percent>}``.
      Default name: ``"ROC_12"``.
    - Stochastic: one entry with ``values = {"k": <float 0..100>,
      "d": <float 0..100>}`` (matching `indicators.stochastic.Stochastic`'s
      output keys). Default name: ``"Stochastic_14_3"``.
    - MACD histogram: one entry with
      ``values = {"macd": ..., "signal": ..., "histogram": ...}``
      (matching `indicators.macd.MACD`'s output keys; only
      ``"histogram"`` is used here). Default name: ``"MACD_12_26_9"``.

All four indicators are optional independently -- `MomentumAnalyzer`
uses whichever are present in the given `AnalysisContext` and lowers its
`confidence` accordingly. `analyze()` raises `InsufficientDataError`
only when *none* of the four are available.

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
    normalize_center,
    normalize_scaled,
    score_label,
    weighted_average,
)

#: Number of independent momentum components this analyzer can use
#: (RSI, ROC, Stochastic, MACD histogram).
_MAX_COMPONENTS = 4


class MomentumAnalyzer(BaseAnalyzer):
    """
    Interprets RSI, ROC, Stochastic, and the MACD histogram into a
    single momentum `AnalysisResult`.

    Parameters:
        rsi_name: `indicator_name` of the RSI `IndicatorResult` entry.
            Default: ``"RSI_14"``.
        roc_name: `indicator_name` of the ROC `IndicatorResult` entry.
            Default: ``"ROC_12"``.
        stochastic_name: `indicator_name` of the Stochastic
            `IndicatorResult` entry. Default: ``"Stochastic_14_3"``.
        macd_name: `indicator_name` of the MACD `IndicatorResult` entry
            (only its ``"histogram"`` output is used here).
            Default: ``"MACD_12_26_9"``.
        roc_scale: The ROC magnitude (in the same percent units ROC is
            expressed in) that counts as a full-strength +/-1.0 reading.
            ROC is unbounded and asset-dependent, so this is
            caller-tunable. Default: ``10.0`` (a +/-10% rate of change is
            treated as maximal momentum).
        macd_hist_scale: Same idea as `roc_scale`, but for the MACD
            histogram, which is expressed in price units and therefore
            even more asset-dependent. Default: ``1.0`` -- callers
            working with assets whose price scale differs meaningfully
            from a $1-ish histogram range should override this.
        name: Analyzer name, forwarded to `BaseAnalyzer`.
    """

    def __init__(
        self,
        *,
        rsi_name: str = "RSI_14",
        roc_name: str = "ROC_12",
        stochastic_name: str = "Stochastic_14_3",
        macd_name: str = "MACD_12_26_9",
        roc_scale: float = 10.0,
        macd_hist_scale: float = 1.0,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(name=name)
        if roc_scale == 0:
            raise ValueError("roc_scale must be non-zero")
        if macd_hist_scale == 0:
            raise ValueError("macd_hist_scale must be non-zero")
        self.rsi_name = rsi_name
        self.roc_name = roc_name
        self.stochastic_name = stochastic_name
        self.macd_name = macd_name
        self.roc_scale = roc_scale
        self.macd_hist_scale = macd_hist_scale

    # ------------------------------------------------------------------
    # BaseAnalyzer API
    # ------------------------------------------------------------------
    def analyze(self, context: AnalysisContext) -> AnalysisResult:
        self.validate_context(context)

        components: dict[str, float] = {}
        detail: dict[str, Any] = {}

        rsi_score = self._rsi_component(context, detail)
        if rsi_score is not None:
            components["rsi"] = rsi_score

        roc_score = self._roc_component(context, detail)
        if roc_score is not None:
            components["roc"] = roc_score

        stoch_score, agreement = self._stochastic_component(context, detail)
        if stoch_score is not None:
            components["stochastic"] = stoch_score

        macd_hist_score = self._macd_histogram_component(context, detail)
        if macd_hist_score is not None:
            components["macd_histogram"] = macd_hist_score

        if not components:
            raise InsufficientDataError(
                f"{self.name} requires at least one of RSI ({self.rsi_name}), "
                f"ROC ({self.roc_name}), Stochastic ({self.stochastic_name}), "
                f"or the MACD histogram ({self.macd_name}) to be present on the "
                f"AnalysisContext; none were found for {context.symbol}/"
                f"{context.timeframe}."
            )

        weighted = [(score, 1.0) for score in components.values()]
        overall_score = clip(weighted_average(weighted))

        conviction = mean_abs(components.values())
        completeness = completeness_ratio(len(components), _MAX_COMPONENTS)
        # Stochastic %K/%D agreement contributes a [0.5, 1.0] multiplier
        # -- when %K and %D are close together the reading is more
        # reliable; when absent, defaults to 0.5 -> a 0.75 modifier, so
        # confidence is only ever halved (never zeroed) by its absence.
        agreement_modifier = 0.5 + 0.5 * agreement
        confidence = clip(completeness * conviction * agreement_modifier, 0.0, 1.0)

        summary = (
            f"Momentum is {score_label(overall_score)} "
            f"(score={overall_score:.2f}, confidence={confidence:.2f}) "
            f"based on {', '.join(sorted(components))}."
        )

        metadata: dict[str, Any] = {
            "components_used": sorted(components),
            "component_scores": components,
            "completeness_ratio": completeness,
            "conviction": conviction,
            "agreement_modifier": agreement_modifier,
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
    def _rsi_component(self, context: AnalysisContext, detail: dict[str, Any]) -> Optional[float]:
        rsi_value = self._value(context, self.rsi_name, "value")
        if rsi_value is None:
            detail["rsi"] = {
                "used": False,
                "reason": "missing RSI indicator",
                "indicator": self.rsi_name,
            }
            return None
        score = normalize_center(rsi_value, center=50.0, scale=50.0)
        detail["rsi"] = {
            "used": True,
            "indicator": self.rsi_name,
            "value": rsi_value,
            "score": score,
            "explanation": (
                "RSI centered on 50 and scaled by 50, clipped to [-1, 1]; "
                "RSI=100 -> +1.0, RSI=0 -> -1.0, RSI=50 -> 0.0."
            ),
        }
        return score

    def _roc_component(self, context: AnalysisContext, detail: dict[str, Any]) -> Optional[float]:
        roc_value = self._value(context, self.roc_name, "value")
        if roc_value is None:
            detail["roc"] = {
                "used": False,
                "reason": "missing ROC indicator",
                "indicator": self.roc_name,
            }
            return None
        score = normalize_scaled(roc_value, self.roc_scale)
        detail["roc"] = {
            "used": True,
            "indicator": self.roc_name,
            "value": roc_value,
            "scale": self.roc_scale,
            "score": score,
            "explanation": (
                f"ROC divided by roc_scale ({self.roc_scale}), clipped to "
                "[-1, 1]; a rate-of-change at or beyond +/-roc_scale is "
                "treated as maximal momentum."
            ),
        }
        return score

    def _stochastic_component(
        self, context: AnalysisContext, detail: dict[str, Any]
    ) -> tuple[Optional[float], float]:
        k_value = self._value(context, self.stochastic_name, "k")
        d_value = self._value(context, self.stochastic_name, "d")
        if k_value is None or d_value is None:
            detail["stochastic"] = {
                "used": False,
                "reason": "missing or incomplete Stochastic indicator (%K/%D)",
                "indicator": self.stochastic_name,
            }
            # Neutral 0.5 agreement default -> a 0.75 confidence modifier.
            return None, 0.5

        average = (k_value + d_value) / 2.0
        score = normalize_center(average, center=50.0, scale=50.0)
        # %K and %D within 0 points apart -> agreement 1.0 (max reliability);
        # 50+ points apart -> agreement 0.0 (min reliability).
        agreement = clip(1.0 - abs(k_value - d_value) / 50.0, 0.0, 1.0)
        detail["stochastic"] = {
            "used": True,
            "indicator": self.stochastic_name,
            "k_value": k_value,
            "d_value": d_value,
            "score": score,
            "agreement": agreement,
            "explanation": (
                "Average of %K and %D centered on 50 and scaled by 50, "
                "clipped to [-1, 1]; agreement = clip(1 - |%K - %D| / 50, "
                "0, 1) measures how closely %K and %D track each other."
            ),
        }
        return score, agreement

    def _macd_histogram_component(
        self, context: AnalysisContext, detail: dict[str, Any]
    ) -> Optional[float]:
        histogram = self._value(context, self.macd_name, "histogram")
        if histogram is None:
            detail["macd_histogram"] = {
                "used": False,
                "reason": "missing MACD indicator or histogram output",
                "indicator": self.macd_name,
            }
            return None
        score = normalize_scaled(histogram, self.macd_hist_scale)
        detail["macd_histogram"] = {
            "used": True,
            "indicator": self.macd_name,
            "value": histogram,
            "scale": self.macd_hist_scale,
            "score": score,
            "explanation": (
                f"MACD histogram divided by macd_hist_scale "
                f"({self.macd_hist_scale}), clipped to [-1, 1]; captures "
                "momentum of the trend itself (MACD accelerating away "
                "from, or converging toward, its signal line)."
            ),
        }
        return score

    @staticmethod
    def _value(context: AnalysisContext, indicator_name: str, key: str) -> Optional[float]:
        indicator = context.get_indicator(indicator_name)
        if indicator is None:
            return None
        value = indicator.values.get(key)
        if not is_finite_number(value):
            return None
        return float(value)
