"""
analysis/technical/volume_analyzer.py

Defines `VolumeAnalyzer`: the fourth concrete technical analyzer built
on top of the Analysis Engine foundation (`BaseAnalyzer`,
`AnalysisContext`, `AnalysisResult` -- Part 1), joining `TrendAnalyzer`
and `MomentumAnalyzer` (Part 2) and `VolatilityAnalyzer` (Part 3A). It
interprets *volume* indicators already computed by `indicators/` -- it
never calculates them itself.

Inputs consumed (looked up on `AnalysisContext.indicators` by
`indicator_name`, matching the naming/value-key convention already used
by `indicators/base.py`'s default `IndicatorResult.name` --
``f"{ClassName}_{period}"`` -- and each indicator's own output keys):

    - OBV (On-Balance Volume): one entry with
      ``values = {"value": <float, cumulative volume-flow units>}``
      (matching `indicators.obv.OBV`'s output). Default name:
      ``"OBV_1"``.
    - VWAP (Volume Weighted Average Price): one entry with
      ``values = {"value": <float, price units>}`` (matching
      `indicators.vwap.VWAP`'s output). Default name: ``"VWAP_14"``.
    - Volume SMA: one entry with
      ``values = {"value": <float, volume units>}`` (matching
      `indicators.volume_sma.VolumeSMA`'s output). Default name:
      ``"VolumeSMA_20"``.

All three indicators are optional independently -- `VolumeAnalyzer`
uses whichever are present in the given `AnalysisContext` and lowers its
`confidence` accordingly. `analyze()` raises `InsufficientDataError`
only when *none* of the three are usable.

Unlike the other three analyzers, none of OBV/VWAP/Volume SMA on their
own carry a directly comparable "current price" or "current period
volume" figure to react to -- OBV is a running cumulative total, VWAP is
a price-scale value with nothing to compare itself against, and Volume
SMA is an average with nothing to measure the *current* volume against.
`VolumeAnalyzer` therefore also reads the latest candle already carried
on `AnalysisContext.market_state.latest_candle` (open/close/volume) --
data that already exists on the context passed to every analyzer, not a
new indicator, new fetch, or new domain concept. This is used only to
give the three volume indicators something concrete to react to
(current price for VWAP, current-period volume for Volume SMA, and
last-candle direction for OBV agreement); it is optional exactly like
the indicators, and its absence only reduces `confidence`, never raises.

Score semantics (direction-based, like `TrendAnalyzer`/
`MomentumAnalyzer`, unlike `VolatilityAnalyzer`'s regime score):
`-1.0` (strong bearish volume flow / selling pressure) .. `0.0`
(neutral) .. `+1.0` (strong bullish volume flow / buying pressure).
Confidence: `0.0` .. `1.0`.

Per-indicator scores follow the same `analysis/technical/utils.py`
normalization helpers already used by the sibling analyzers
(`normalize_center`, `normalize_scaled`/ratio-based scaling), with
caller-tunable baselines documented per component below. Beyond the
combined `score`, `metadata` additionally explains every facet called
out by this analyzer's design brief:

    - ``volume_confirmation`` / ``volume_divergence``: `0.0`..`1.0`
      measures of whether the latest candle's price direction agrees
      (confirmation) or disagrees (divergence) with the OBV-implied
      volume-flow direction.
    - ``buying_pressure`` / ``selling_pressure``: `0.0`..`1.0`,
      derived from current-period volume (relative to its Volume SMA
      baseline) weighted by the latest candle's direction.
    - ``volume_trend``: `-1.0`..`1.0`, whether current-period volume is
      running above (expanding) or below (contracting) its Volume SMA
      baseline.
    - ``participation_strength``: `0.0`..`1.0`, the magnitude of that
      same deviation, direction-free.
    - ``price_vs_vwap``: the current price's position relative to VWAP
      (above/at/below, with the relative distance and the score it
      produced).

No AI, no signals, no strategies, no trading decisions are produced --
only a scored, fully-explained `AnalysisResult`.
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

#: Number of independent volume components this analyzer can use
#: (OBV, VWAP, volume participation).
_MAX_COMPONENTS = 3


class VolumeAnalyzer(BaseAnalyzer):
    """
    Interprets OBV, VWAP, and Volume SMA (plus the latest candle already
    carried on `AnalysisContext.market_state`) into a single volume
    `AnalysisResult`.

    Parameters:
        obv_name: `indicator_name` of the OBV `IndicatorResult` entry.
            Default: ``"OBV_1"``.
        vwap_name: `indicator_name` of the VWAP `IndicatorResult` entry.
            Default: ``"VWAP_14"``.
        volume_sma_name: `indicator_name` of the Volume SMA
            `IndicatorResult` entry. Default: ``"VolumeSMA_20"``.
        obv_normal: The OBV value treated as "normal" / neutral volume
            flow -- maps to a `0.0` component score. OBV is a raw,
            unbounded cumulative value whose scale depends on the
            asset and the lookback window it was accumulated over, so
            this is caller-tunable, exactly like `VolatilityAnalyzer`'s
            `atr_normal`. Default: ``0.0``.
        obv_scale: The distance above/below `obv_normal` that counts as
            a full-strength `+/-1.0` reading. Same asset/window-
            dependent caveat as `obv_normal`. Default: ``1.0``.
        vwap_scale: The relative distance `(price - vwap) / abs(vwap)`
            that counts as a full-strength `+/-1.0` reading. Already a
            price-scale-independent ratio (mirrors
            `VolatilityAnalyzer`'s band-width-ratio scales), so the
            default is a reasonable starting point across assets.
            Default: ``0.02`` (a 2% deviation from VWAP is treated as a
            maximal reading).
        participation_scale: The `(current_volume / volume_sma) - 1.0`
            deviation that counts as a full-strength `+/-1.0` /
            `1.0` reading. Also a ratio, so self-normalizing across
            assets. Default: ``1.0`` (current volume at 2x its Volume
            SMA baseline is treated as maximal participation).
        name: Analyzer name, forwarded to `BaseAnalyzer`.

    Raises:
        ValueError: If `obv_scale`, `vwap_scale`, or
            `participation_scale` is `0`.
    """

    def __init__(
        self,
        *,
        obv_name: str = "OBV_1",
        vwap_name: str = "VWAP_14",
        volume_sma_name: str = "VolumeSMA_20",
        obv_normal: float = 0.0,
        obv_scale: float = 1.0,
        vwap_scale: float = 0.02,
        participation_scale: float = 1.0,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(name=name)
        for label, scale in (
            ("obv_scale", obv_scale),
            ("vwap_scale", vwap_scale),
            ("participation_scale", participation_scale),
        ):
            if scale == 0:
                raise ValueError(f"{label} must be non-zero")

        self.obv_name = obv_name
        self.vwap_name = vwap_name
        self.volume_sma_name = volume_sma_name

        self.obv_normal = obv_normal
        self.obv_scale = obv_scale
        self.vwap_scale = vwap_scale
        self.participation_scale = participation_scale

    # ------------------------------------------------------------------
    # BaseAnalyzer API
    # ------------------------------------------------------------------
    def analyze(self, context: AnalysisContext) -> AnalysisResult:
        self.validate_context(context)

        components: dict[str, float] = {}
        detail: dict[str, Any] = {}

        open_price, close_price, current_volume = self._candle_values(context)

        obv_score = self._obv_component(context, detail)
        if obv_score is not None:
            components["obv"] = obv_score

        vwap_score = self._vwap_component(context, detail, close_price)
        if vwap_score is not None:
            components["vwap"] = vwap_score

        participation_score, volume_ratio = self._participation_component(
            context, detail, open_price, close_price, current_volume
        )
        if participation_score is not None:
            components["volume_participation"] = participation_score

        if not components:
            raise InsufficientDataError(
                f"{self.name} requires at least one of OBV ({self.obv_name}), "
                f"VWAP ({self.vwap_name}), or Volume SMA ({self.volume_sma_name}) "
                f"to be usable from the AnalysisContext; none were found for "
                f"{context.symbol}/{context.timeframe}."
            )

        weighted = [(score, 1.0) for score in components.values()]
        overall_score = clip(weighted_average(weighted))

        conviction = mean_abs(components.values())
        completeness = completeness_ratio(len(components), _MAX_COMPONENTS)
        # How tightly the present components agree: a small spread
        # between the most bullish and most bearish reading means the
        # indicators agree, which is more reliable than one screaming
        # "buying" while another says "selling". Max possible spread is
        # 2.0 (scores in [-1, 1]). Mirrors VolatilityAnalyzer's
        # agreement_modifier.
        spread = max(components.values()) - min(components.values())
        agreement = clip(1.0 - spread / 2.0, 0.0, 1.0)
        agreement_modifier = 0.5 + 0.5 * agreement
        confidence = clip(completeness * conviction * agreement_modifier, 0.0, 1.0)

        candle_direction = self._candle_direction(open_price, close_price)

        confirmation, divergence, confirmation_detail = self._confirmation_and_divergence(
            candle_direction, components.get("obv")
        )
        buying_pressure, selling_pressure, pressure_detail = self._pressure(
            candle_direction, volume_ratio
        )
        volume_trend, participation_strength, trend_detail = self._volume_trend(volume_ratio)
        price_vs_vwap = self._price_vs_vwap_metadata(detail.get("vwap"))

        summary = (
            f"Volume flow is {score_label(overall_score)} "
            f"(score={overall_score:.2f}, confidence={confidence:.2f}) "
            f"based on {', '.join(sorted(components))}; "
            f"buying_pressure={buying_pressure:.2f}, "
            f"selling_pressure={selling_pressure:.2f}, "
            f"volume_confirmation={confirmation:.2f}."
        )

        metadata: dict[str, Any] = {
            "components_used": sorted(components),
            "component_scores": components,
            "completeness_ratio": completeness,
            "conviction": conviction,
            "agreement_modifier": agreement_modifier,
            "score_scale": "-1.0 (strong bearish/selling) .. 0.0 (neutral) .. +1.0 (strong bullish/buying)",
            "confidence_scale": "0.0 (no confidence) .. 1.0 (full confidence)",
            "volume_confirmation": confirmation,
            "volume_divergence": divergence,
            "buying_pressure": buying_pressure,
            "selling_pressure": selling_pressure,
            "volume_trend": volume_trend,
            "participation_strength": participation_strength,
            "price_vs_vwap": price_vs_vwap,
            "confirmation_detail": confirmation_detail,
            "pressure_detail": pressure_detail,
            "volume_trend_detail": trend_detail,
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
    def _obv_component(self, context: AnalysisContext, detail: dict[str, Any]) -> Optional[float]:
        obv_value = self._value(context, self.obv_name, "value")
        if obv_value is None:
            detail["obv"] = {
                "used": False,
                "reason": "missing OBV indicator",
                "indicator": self.obv_name,
            }
            return None
        score = normalize_center(obv_value, center=self.obv_normal, scale=self.obv_scale)
        detail["obv"] = {
            "used": True,
            "indicator": self.obv_name,
            "value": obv_value,
            "normal": self.obv_normal,
            "scale": self.obv_scale,
            "score": score,
            "explanation": (
                "OBV centered on obv_normal and scaled by obv_scale, clipped "
                "to [-1, 1]; positive = cumulative volume flow above the "
                "configured normal baseline (net accumulation/buying), "
                "negative = below it (net distribution/selling). OBV is a "
                "raw cumulative value, so obv_normal/obv_scale are asset- "
                "and window-scale-dependent and must be tuned per "
                "instrument, mirroring VolatilityAnalyzer's atr_normal/"
                "atr_scale."
            ),
        }
        return score

    def _vwap_component(
        self, context: AnalysisContext, detail: dict[str, Any], close_price: Optional[float]
    ) -> Optional[float]:
        vwap_value = self._value(context, self.vwap_name, "value")
        if vwap_value is None:
            detail["vwap"] = {
                "used": False,
                "reason": "missing VWAP indicator",
                "indicator": self.vwap_name,
            }
            return None
        if vwap_value <= 0:
            detail["vwap"] = {
                "used": False,
                "reason": "VWAP value is not positive, which is not a valid price reading",
                "indicator": self.vwap_name,
                "value": vwap_value,
            }
            return None
        if close_price is None:
            detail["vwap"] = {
                "used": False,
                "reason": (
                    "VWAP indicator present but no current price is available "
                    "on context.market_state.latest_candle to compare it against"
                ),
                "indicator": self.vwap_name,
                "value": vwap_value,
            }
            return None

        relative_distance = (close_price - vwap_value) / abs(vwap_value)
        score = normalize_scaled(relative_distance, self.vwap_scale)
        if relative_distance > 0:
            relation = "above"
        elif relative_distance < 0:
            relation = "below"
        else:
            relation = "at"
        detail["vwap"] = {
            "used": True,
            "indicator": self.vwap_name,
            "vwap_value": vwap_value,
            "price": close_price,
            "relative_distance": relative_distance,
            "scale": self.vwap_scale,
            "score": score,
            "relation": relation,
            "explanation": (
                "Relative distance of the latest close price from VWAP -- "
                "(price - vwap) / abs(vwap) -- scaled by vwap_scale and "
                "clipped to [-1, 1]; positive means price is trading above "
                "VWAP (bullish positioning), negative means below "
                "(bearish positioning)."
            ),
        }
        return score

    def _participation_component(
        self,
        context: AnalysisContext,
        detail: dict[str, Any],
        open_price: Optional[float],
        close_price: Optional[float],
        current_volume: Optional[float],
    ) -> tuple[Optional[float], Optional[float]]:
        volume_sma_value = self._value(context, self.volume_sma_name, "value")
        if volume_sma_value is None:
            detail["volume_participation"] = {
                "used": False,
                "reason": "missing Volume SMA indicator",
                "indicator": self.volume_sma_name,
            }
            return None, None
        if volume_sma_value <= 0:
            detail["volume_participation"] = {
                "used": False,
                "reason": "Volume SMA value is not positive, which is not a valid baseline",
                "indicator": self.volume_sma_name,
                "value": volume_sma_value,
            }
            return None, None
        if current_volume is None:
            detail["volume_participation"] = {
                "used": False,
                "reason": (
                    "Volume SMA indicator present but no current-period volume "
                    "is available on context.market_state.latest_candle to "
                    "compare it against"
                ),
                "indicator": self.volume_sma_name,
                "value": volume_sma_value,
            }
            return None, None
        if current_volume < 0:
            detail["volume_participation"] = {
                "used": False,
                "reason": "current-period volume is negative, which is not a valid reading",
                "indicator": self.volume_sma_name,
                "current_volume": current_volume,
            }
            return None, None

        volume_ratio = current_volume / volume_sma_value
        magnitude = clip((volume_ratio - 1.0) / self.participation_scale, 0.0, 1.0)
        candle_direction = self._candle_direction(open_price, close_price)
        score = candle_direction * magnitude
        detail["volume_participation"] = {
            "used": True,
            "indicator": self.volume_sma_name,
            "volume_sma_value": volume_sma_value,
            "current_volume": current_volume,
            "volume_ratio": volume_ratio,
            "candle_direction": candle_direction,
            "participation_magnitude": magnitude,
            "scale": self.participation_scale,
            "score": score,
            "explanation": (
                "current_volume / volume_sma gives volume_ratio; how far "
                "that ratio sits above 1.0 (scaled by participation_scale, "
                "clipped to [0, 1]) gives participation_magnitude. The "
                "directional score signs that magnitude by the latest "
                "candle's close-vs-open direction: above-average volume on "
                "an up candle is bullish (buying pressure), on a down "
                "candle is bearish (selling pressure); below-average volume "
                "pulls the score toward neutral regardless of direction."
            ),
        }
        return score, volume_ratio

    # ------------------------------------------------------------------
    # Derived interpretive metrics
    # ------------------------------------------------------------------
    @staticmethod
    def _confirmation_and_divergence(
        candle_direction: float, obv_score: Optional[float]
    ) -> tuple[float, float, dict[str, Any]]:
        """
        Whether the latest candle's price direction agrees
        (`volume_confirmation`) or disagrees (`volume_divergence`) with
        the OBV-implied volume-flow direction.
        """
        if obv_score is None or candle_direction == 0.0:
            reason = (
                "missing OBV component" if obv_score is None else "latest candle has no net direction"
            )
            return (
                0.0,
                0.0,
                {"computable": False, "reason": reason},
            )
        agreement = candle_direction * obv_score
        confirmation = clip(agreement, 0.0, 1.0)
        divergence = clip(-agreement, 0.0, 1.0)
        return (
            confirmation,
            divergence,
            {
                "computable": True,
                "candle_direction": candle_direction,
                "obv_score": obv_score,
                "explanation": (
                    "volume_confirmation is high when the latest candle's "
                    "direction (close vs open) agrees with the sign of the "
                    "OBV component score; volume_divergence is high when "
                    "they disagree -- price moving one way while cumulative "
                    "volume flow leans the other way."
                ),
            },
        )

    @staticmethod
    def _pressure(
        candle_direction: float, volume_ratio: Optional[float]
    ) -> tuple[float, float, dict[str, Any]]:
        """`buying_pressure` / `selling_pressure`, `0.0`..`1.0` each."""
        if volume_ratio is None:
            return (
                0.0,
                0.0,
                {"computable": False, "reason": "missing volume participation component"},
            )
        magnitude = clip(volume_ratio - 1.0, 0.0, 1.0)
        pressure_score = candle_direction * magnitude
        buying_pressure = clip(pressure_score, 0.0, 1.0)
        selling_pressure = clip(-pressure_score, 0.0, 1.0)
        return (
            buying_pressure,
            selling_pressure,
            {
                "computable": True,
                "volume_ratio": volume_ratio,
                "candle_direction": candle_direction,
                "explanation": (
                    "buying_pressure/selling_pressure split how far current "
                    "volume sits above its Volume SMA baseline by the "
                    "latest candle's direction: an up candle on above-"
                    "average volume contributes to buying_pressure, a down "
                    "candle on above-average volume contributes to "
                    "selling_pressure. Below-average volume yields both at "
                    "or near 0.0."
                ),
            },
        )

    @staticmethod
    def _volume_trend(volume_ratio: Optional[float]) -> tuple[float, float, dict[str, Any]]:
        """`volume_trend` (`-1.0`..`1.0`) and `participation_strength` (`0.0`..`1.0`)."""
        if volume_ratio is None:
            return (
                0.0,
                0.0,
                {"computable": False, "reason": "missing volume participation component"},
            )
        trend = clip(volume_ratio - 1.0, -1.0, 1.0)
        strength = clip(abs(trend), 0.0, 1.0)
        return (
            trend,
            strength,
            {
                "computable": True,
                "volume_ratio": volume_ratio,
                "explanation": (
                    "volume_trend is (volume_ratio - 1.0) clipped to "
                    "[-1, 1]: positive means current-period volume is "
                    "running above its Volume SMA baseline (expanding "
                    "participation), negative means below it (contracting "
                    "participation). participation_strength is the "
                    "direction-free magnitude of the same deviation."
                ),
            },
        )

    @staticmethod
    def _price_vs_vwap_metadata(vwap_detail: Optional[dict[str, Any]]) -> dict[str, Any]:
        """
        Summarize the `price` vs `VWAP` relationship for `metadata`, drawn
        from the `vwap` component's own `detail` entry so this is never
        computed twice.
        """
        if not vwap_detail or not vwap_detail.get("used"):
            reason = (
                vwap_detail.get("reason") if vwap_detail else "missing VWAP indicator"
            )
            return {"computable": False, "reason": reason}
        return {
            "computable": True,
            "price": vwap_detail["price"],
            "vwap": vwap_detail["vwap_value"],
            "relative_distance": vwap_detail["relative_distance"],
            "relation": vwap_detail["relation"],
            "score": vwap_detail["score"],
        }

    # ------------------------------------------------------------------
    # Context access helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _candle_values(
        context: AnalysisContext,
    ) -> tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Return `(open, close, volume)` from `context.market_state.latest_candle`
        as floats, or `(None, None, None)` if unavailable/non-finite.
        """
        candle = context.market_state.latest_candle
        if candle is None:
            return None, None, None
        open_price = float(candle.open) if is_finite_number(float(candle.open)) else None
        close_price = float(candle.close) if is_finite_number(float(candle.close)) else None
        volume = float(candle.volume) if is_finite_number(float(candle.volume)) else None
        return open_price, close_price, volume

    @staticmethod
    def _candle_direction(open_price: Optional[float], close_price: Optional[float]) -> float:
        """`1.0` if close > open, `-1.0` if close < open, `0.0` otherwise/unavailable."""
        if open_price is None or close_price is None:
            return 0.0
        if close_price > open_price:
            return 1.0
        if close_price < open_price:
            return -1.0
        return 0.0

    @staticmethod
    def _value(context: AnalysisContext, indicator_name: str, key: str) -> Optional[float]:
        indicator = context.get_indicator(indicator_name)
        if indicator is None:
            return None
        value = indicator.values.get(key)
        if not is_finite_number(value):
            return None
        return float(value)
