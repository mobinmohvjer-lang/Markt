"""
analysis/technical/volatility_analyzer.py

Defines `VolatilityAnalyzer`: the third concrete technical analyzer
built on top of the Analysis Engine foundation (`BaseAnalyzer`,
`AnalysisContext`, `AnalysisResult` -- Part 1), alongside `TrendAnalyzer`
and `MomentumAnalyzer` (Part 2). It interprets *volatility* indicators
already computed by `indicators/` -- it never calculates them itself.

Inputs consumed (looked up on `AnalysisContext.indicators` by
`indicator_name`, matching the naming/value-key convention already used
by `indicators/base.py`'s default `IndicatorResult.name` --
``f"{ClassName}_{period}"`` -- and each indicator's own output keys):

    - ATR: one entry with ``values = {"value": <float, price units>}``
      (matching `indicators.atr.ATR`'s output). Default name:
      ``"ATR_14"``.
    - Bollinger Bands: one entry with
      ``values = {"middle": ..., "upper": ..., "lower": ...}``
      (matching `indicators.bollinger_bands.BollingerBands`'s output
      keys). Default name: ``"BollingerBands_20"``.
    - Keltner Channel: one entry with the same
      ``{"middle": ..., "upper": ..., "lower": ...}`` shape (matching
      `indicators.keltner_channel.KeltnerChannel`'s output keys).
      Default name: ``"KeltnerChannel_20"``.
    - Donchian Channel: one entry with the same
      ``{"middle": ..., "upper": ..., "lower": ...}`` shape (matching
      `indicators.donchian_channel.DonchianChannel`'s output keys).
      Default name: ``"DonchianChannel_20"``.

All four indicators are optional independently -- `VolatilityAnalyzer`
uses whichever are present in the given `AnalysisContext` and lowers its
`confidence` accordingly. `analyze()` raises `InsufficientDataError`
only when *none* of the four are available.

Score semantics (distinct from `TrendAnalyzer`/`MomentumAnalyzer`, which
score bullish/bearish *direction*): volatility has no inherent
direction, so `score` here measures the *volatility regime* --
`-1.0` (strong contraction / tight, range-bound market) .. `0.0`
(normal/stable volatility) .. `+1.0` (strong expansion / breakout-prone
market). Confidence: `0.0` .. `1.0`.

Per-indicator scores are produced by centering an observed value (or, for
the three band-style indicators, a price-scale-independent band-width
ratio) on a caller-tunable "normal" baseline and scaling by a
caller-tunable range, exactly mirroring the `normalize_center`/
`normalize_scaled` pattern already used by `TrendAnalyzer`/
`MomentumAnalyzer` (see `analysis/technical/utils.py`). ATR is an
unbounded, price-unit value (like the MACD histogram in
`MomentumAnalyzer`), so its baseline/scale are asset-dependent and must
be tuned by the caller for the instrument being analyzed. Bollinger,
Keltner, and Donchian band widths are computed as
``(upper - lower) / abs(middle)`` -- a ratio already normalized by price
level, so their default baselines are reasonable starting points across
assets but remain tunable.

Beyond the single combined `score`, `metadata` additionally explains the
five facets called out by this analyzer's design brief, each derived
from the per-indicator components above (none of these feed into
`score` directly except where noted):

    - ``volatility_expansion`` / ``volatility_contraction``: degree
      (`0.0`..`1.0`) to which the combined `score` leans positive/
      negative -- i.e. `clip(score, 0, 1)` and `clip(-score, 0, 1)`.
    - ``range_compression``: `0.0`..`1.0` measure of how tight the
      current range is relative to each indicator's configured normal
      baseline, blended with the classic "squeeze" heuristic (Bollinger
      Bands narrower than the Keltner Channel) when both are available.
    - ``breakout_probability``: `0.0`..`1.0`, derived from
      `range_compression` (tighter ranges precede breakouts) with a
      boost when a Bollinger/Keltner squeeze is detected.
    - ``trend_strength_contribution``: `0.0`..`1.0`, quantifying how
      much *confidence* this volatility reading could lend to a
      trend-strength read performed elsewhere (mirroring how
      `TrendAnalyzer` turns ADX into a confidence-only "strength
      factor"). This analyzer never determines trend *direction* --
      that remains `TrendAnalyzer`'s responsibility.

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
    weighted_average,
)

#: Number of independent volatility components this analyzer can use
#: (ATR, Bollinger Bands, Keltner Channel, Donchian Channel).
_MAX_COMPONENTS = 4

#: Flat bonus added to `breakout_probability` when a classic
#: Bollinger-inside-Keltner "squeeze" is detected.
_SQUEEZE_BREAKOUT_BONUS = 0.15


def _volatility_label(score: float) -> str:
    """
    Translate a `[-1.0, 1.0]` volatility score into a short,
    human-readable label for use in `AnalysisResult.summary` text.

    Distinct from `analysis.technical.utils.score_label`, which labels
    bullish/bearish *direction* -- volatility has no direction, so this
    labels the *regime* instead. Thresholds mirror `score_label`'s for
    consistency: `>= 0.5` strong expansion, `>= 0.15` mild expansion,
    `> -0.15` stable, `> -0.5` mild contraction, otherwise strong
    contraction.
    """
    if score >= 0.5:
        return "strong expansion"
    if score >= 0.15:
        return "mild expansion"
    if score > -0.15:
        return "stable"
    if score > -0.5:
        return "mild contraction"
    return "strong contraction"


class VolatilityAnalyzer(BaseAnalyzer):
    """
    Interprets ATR, Bollinger Bands, Keltner Channel, and Donchian
    Channel into a single volatility-regime `AnalysisResult`.

    Parameters:
        atr_name: `indicator_name` of the ATR `IndicatorResult` entry.
            Default: ``"ATR_14"``.
        bollinger_name: `indicator_name` of the Bollinger Bands
            `IndicatorResult` entry. Default: ``"BollingerBands_20"``.
        keltner_name: `indicator_name` of the Keltner Channel
            `IndicatorResult` entry. Default: ``"KeltnerChannel_20"``.
        donchian_name: `indicator_name` of the Donchian Channel
            `IndicatorResult` entry. Default: ``"DonchianChannel_20"``.
        atr_normal: The ATR value (in the instrument's own price units)
            treated as "normal" volatility -- maps to a `0.0` component
            score. Asset-dependent and caller-tunable, mirroring
            `MomentumAnalyzer.macd_hist_scale`. Default: ``1.0``.
        atr_scale: The distance (in the same price units as `atr_normal`)
            above/below `atr_normal` that counts as a full-strength
            `+/-1.0` reading. Default: ``1.0``.
        bollinger_width_normal / bollinger_width_scale: "Normal" band
            width and scale for Bollinger Bands, expressed as a
            `(upper - lower) / abs(middle)` ratio. Defaults: ``0.04`` /
            ``0.04`` (a ~4% band width is treated as the neutral
            baseline).
        keltner_width_normal / keltner_width_scale: Same idea, for the
            Keltner Channel. Defaults: ``0.03`` / ``0.03``.
        donchian_width_normal / donchian_width_scale: Same idea, for the
            Donchian Channel. Defaults: ``0.05`` / ``0.05``.
        name: Analyzer name, forwarded to `BaseAnalyzer`.

    Raises:
        ValueError: If any `*_scale` parameter is `0`.
    """

    def __init__(
        self,
        *,
        atr_name: str = "ATR_14",
        bollinger_name: str = "BollingerBands_20",
        keltner_name: str = "KeltnerChannel_20",
        donchian_name: str = "DonchianChannel_20",
        atr_normal: float = 1.0,
        atr_scale: float = 1.0,
        bollinger_width_normal: float = 0.04,
        bollinger_width_scale: float = 0.04,
        keltner_width_normal: float = 0.03,
        keltner_width_scale: float = 0.03,
        donchian_width_normal: float = 0.05,
        donchian_width_scale: float = 0.05,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(name=name)
        for label, scale in (
            ("atr_scale", atr_scale),
            ("bollinger_width_scale", bollinger_width_scale),
            ("keltner_width_scale", keltner_width_scale),
            ("donchian_width_scale", donchian_width_scale),
        ):
            if scale == 0:
                raise ValueError(f"{label} must be non-zero")

        self.atr_name = atr_name
        self.bollinger_name = bollinger_name
        self.keltner_name = keltner_name
        self.donchian_name = donchian_name

        self.atr_normal = atr_normal
        self.atr_scale = atr_scale
        self.bollinger_width_normal = bollinger_width_normal
        self.bollinger_width_scale = bollinger_width_scale
        self.keltner_width_normal = keltner_width_normal
        self.keltner_width_scale = keltner_width_scale
        self.donchian_width_normal = donchian_width_normal
        self.donchian_width_scale = donchian_width_scale

    # ------------------------------------------------------------------
    # BaseAnalyzer API
    # ------------------------------------------------------------------
    def analyze(self, context: AnalysisContext) -> AnalysisResult:
        self.validate_context(context)

        components: dict[str, float] = {}
        widths: dict[str, float] = {}
        detail: dict[str, Any] = {}

        atr_score = self._atr_component(context, detail)
        if atr_score is not None:
            components["atr"] = atr_score

        bb_score, bb_width = self._band_component(
            context,
            detail,
            key="bollinger",
            indicator_name=self.bollinger_name,
            normal=self.bollinger_width_normal,
            scale=self.bollinger_width_scale,
        )
        if bb_score is not None:
            components["bollinger"] = bb_score
            widths["bollinger"] = bb_width  # type: ignore[assignment]

        kc_score, kc_width = self._band_component(
            context,
            detail,
            key="keltner",
            indicator_name=self.keltner_name,
            normal=self.keltner_width_normal,
            scale=self.keltner_width_scale,
        )
        if kc_score is not None:
            components["keltner"] = kc_score
            widths["keltner"] = kc_width  # type: ignore[assignment]

        dc_score, dc_width = self._band_component(
            context,
            detail,
            key="donchian",
            indicator_name=self.donchian_name,
            normal=self.donchian_width_normal,
            scale=self.donchian_width_scale,
        )
        if dc_score is not None:
            components["donchian"] = dc_score
            widths["donchian"] = dc_width  # type: ignore[assignment]

        if not components:
            raise InsufficientDataError(
                f"{self.name} requires at least one of ATR ({self.atr_name}), "
                f"Bollinger Bands ({self.bollinger_name}), Keltner Channel "
                f"({self.keltner_name}), or Donchian Channel "
                f"({self.donchian_name}) to be present on the AnalysisContext; "
                f"none were found for {context.symbol}/{context.timeframe}."
            )

        weighted = [(score, 1.0) for score in components.values()]
        overall_score = clip(weighted_average(weighted))

        conviction = mean_abs(components.values())
        completeness = completeness_ratio(len(components), _MAX_COMPONENTS)
        # How tightly the present components cluster together: a small
        # spread between the most expansionary and most contractionary
        # reading means the indicators agree, which is more reliable
        # than one indicator screaming "expansion" while another says
        # "contraction". Max possible spread is 2.0 (scores in [-1, 1]).
        spread = max(components.values()) - min(components.values())
        agreement = clip(1.0 - spread / 2.0, 0.0, 1.0)
        agreement_modifier = 0.5 + 0.5 * agreement
        confidence = clip(completeness * conviction * agreement_modifier, 0.0, 1.0)

        expansion_degree = clip(overall_score, 0.0, 1.0)
        contraction_degree = clip(-overall_score, 0.0, 1.0)

        range_compression, squeeze_info = self._range_compression(components, widths)
        breakout_probability = self._breakout_probability(range_compression, squeeze_info)
        trend_strength_contribution = clip(conviction * completeness * agreement, 0.0, 1.0)

        summary = (
            f"Volatility is {_volatility_label(overall_score)} "
            f"(score={overall_score:.2f}, confidence={confidence:.2f}) "
            f"based on {', '.join(sorted(components))}; "
            f"breakout_probability={breakout_probability:.2f}, "
            f"range_compression={range_compression:.2f}."
        )

        metadata: dict[str, Any] = {
            "components_used": sorted(components),
            "component_scores": components,
            "completeness_ratio": completeness,
            "conviction": conviction,
            "agreement_modifier": agreement_modifier,
            "score_scale": (
                "-1.0 (strong contraction / range-bound) .. 0.0 (normal/stable) "
                ".. +1.0 (strong expansion / breakout-prone)"
            ),
            "confidence_scale": "0.0 (no confidence) .. 1.0 (full confidence)",
            "volatility_expansion": expansion_degree,
            "volatility_contraction": contraction_degree,
            "range_compression": range_compression,
            "breakout_probability": breakout_probability,
            "trend_strength_contribution": {
                "value": trend_strength_contribution,
                "explanation": (
                    "How much confidence this volatility reading could lend "
                    "to a trend-strength read performed elsewhere (mirrors "
                    "how TrendAnalyzer turns ADX into a confidence-only "
                    "'strength factor'). This analyzer never determines "
                    "trend direction -- that remains TrendAnalyzer's "
                    "responsibility; this value is descriptive context "
                    "only and does not feed into `score`."
                ),
            },
            "squeeze": squeeze_info,
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
    def _atr_component(self, context: AnalysisContext, detail: dict[str, Any]) -> Optional[float]:
        atr_value = self._value(context, self.atr_name, "value")
        if atr_value is None:
            detail["atr"] = {
                "used": False,
                "reason": "missing ATR indicator",
                "indicator": self.atr_name,
            }
            return None
        if atr_value < 0:
            detail["atr"] = {
                "used": False,
                "reason": "ATR value is negative, which is not a valid reading",
                "indicator": self.atr_name,
                "value": atr_value,
            }
            return None
        score = normalize_center(atr_value, center=self.atr_normal, scale=self.atr_scale)
        detail["atr"] = {
            "used": True,
            "indicator": self.atr_name,
            "value": atr_value,
            "normal": self.atr_normal,
            "scale": self.atr_scale,
            "score": score,
            "explanation": (
                "ATR centered on atr_normal and scaled by atr_scale, clipped "
                "to [-1, 1]; positive = volatility above the configured "
                "normal baseline (expansion), negative = below it "
                "(contraction). ATR is a raw price-unit value, so "
                "atr_normal/atr_scale are asset-scale-dependent and must be "
                "tuned per instrument."
            ),
        }
        return score

    def _band_component(
        self,
        context: AnalysisContext,
        detail: dict[str, Any],
        *,
        key: str,
        indicator_name: str,
        normal: float,
        scale: float,
    ) -> tuple[Optional[float], Optional[float]]:
        upper = self._value(context, indicator_name, "upper")
        lower = self._value(context, indicator_name, "lower")
        middle = self._value(context, indicator_name, "middle")

        if upper is None or lower is None or middle is None:
            detail[key] = {
                "used": False,
                "reason": "missing or incomplete indicator (upper/lower/middle)",
                "indicator": indicator_name,
            }
            return None, None
        if middle == 0:
            detail[key] = {
                "used": False,
                "reason": "middle value is zero; cannot compute a relative band width",
                "indicator": indicator_name,
            }
            return None, None
        if upper < lower:
            detail[key] = {
                "used": False,
                "reason": "upper is below lower; malformed band data",
                "indicator": indicator_name,
            }
            return None, None

        width = (upper - lower) / abs(middle)
        score = normalize_center(width, center=normal, scale=scale)
        detail[key] = {
            "used": True,
            "indicator": indicator_name,
            "upper": upper,
            "lower": lower,
            "middle": middle,
            "width_ratio": width,
            "normal": normal,
            "scale": scale,
            "score": score,
            "explanation": (
                "Band width computed as (upper - lower) / abs(middle), a "
                f"price-scale-independent ratio; centered on {key}_width_"
                f"normal ({normal}) and scaled by {key}_width_scale "
                f"({scale}), clipped to [-1, 1]. Positive = wider-than-"
                "normal band (expansion), negative = narrower-than-normal "
                "band (contraction / compression)."
            ),
        }
        return score, width

    # ------------------------------------------------------------------
    # Derived interpretive metrics
    # ------------------------------------------------------------------
    @staticmethod
    def _range_compression(
        components: dict[str, float], widths: dict[str, float]
    ) -> tuple[float, dict[str, Any]]:
        """
        Blend per-component contraction magnitude with the classic
        Bollinger-inside-Keltner "squeeze" heuristic (when both band
        indicators are available) into a single `0.0`..`1.0`
        range-compression measure.
        """
        contraction_magnitudes = [clip(-score, 0.0, 1.0) for score in components.values()]
        base_compression = sum(contraction_magnitudes) / len(contraction_magnitudes)

        squeeze_info: dict[str, Any] = {
            "computable": False,
            "reason": "requires both Bollinger Bands and Keltner Channel widths",
        }
        squeeze_ratio: Optional[float] = None
        squeeze_on: Optional[bool] = None

        if "bollinger" in widths and "keltner" in widths and widths["keltner"] > 0:
            squeeze_ratio = widths["bollinger"] / widths["keltner"]
            squeeze_on = squeeze_ratio < 1.0
            squeeze_info = {
                "computable": True,
                "bollinger_width_ratio": widths["bollinger"],
                "keltner_width_ratio": widths["keltner"],
                "squeeze_ratio": squeeze_ratio,
                "squeeze_on": squeeze_on,
                "explanation": (
                    "squeeze_ratio = Bollinger width / Keltner width. When "
                    "< 1.0, Bollinger Bands sit inside the Keltner Channel "
                    "(a classic 'squeeze'), a pattern commonly associated "
                    "with an impending volatility breakout."
                ),
            }
            squeeze_component = clip(1.0 - squeeze_ratio, 0.0, 1.0)
            range_compression = clip(0.5 * base_compression + 0.5 * squeeze_component, 0.0, 1.0)
        else:
            range_compression = base_compression

        return range_compression, squeeze_info

    @staticmethod
    def _breakout_probability(range_compression: float, squeeze_info: dict[str, Any]) -> float:
        """
        Tighter ranges tend to precede breakouts, so `breakout_probability`
        starts from `range_compression` and receives a flat bonus when a
        Bollinger/Keltner squeeze is actively on.
        """
        probability = range_compression
        if squeeze_info.get("squeeze_on"):
            probability += _SQUEEZE_BREAKOUT_BONUS
        return clip(probability, 0.0, 1.0)

    @staticmethod
    def _value(context: AnalysisContext, indicator_name: str, key: str) -> Optional[float]:
        indicator = context.get_indicator(indicator_name)
        if indicator is None:
            return None
        value = indicator.values.get(key)
        if not is_finite_number(value):
            return None
        return float(value)
