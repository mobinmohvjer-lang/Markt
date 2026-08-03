"""
analysis/technical/market_structure_analyzer.py

Defines `MarketStructureAnalyzer`: the fifth concrete technical
analyzer built on top of the Analysis Engine foundation (`BaseAnalyzer`,
`AnalysisContext`, `AnalysisResult` -- Part 1), joining `TrendAnalyzer`/
`MomentumAnalyzer` (Part 2), `VolatilityAnalyzer` (Part 3A), and
`VolumeAnalyzer` (Part 3B). It interprets *price-structure* (swing
point) data already computed elsewhere -- it never detects swing
points from raw candle history itself, keeping the same calculation-
vs-interpretation split every other analyzer in this package follows
(`indicators/` -- or here, a future swing-point detector living
alongside it -- calculates; `analysis/` interprets).

Inputs consumed (looked up on `AnalysisContext.indicators` by
`indicator_name`, matching the naming/value-key convention already used
by `indicators/base.py`'s default `IndicatorResult.name` --
``f"{ClassName}_{period}"``):

    - Swing points: one entry with
      ``values = {"swing_high_1": <float>, "swing_high_2": <float>,
      "swing_low_1": <float>, "swing_low_2": <float>}`` -- the two most
      recently confirmed swing highs and swing lows, each ordered most
      recent first (``_1``) to previous (``_2``). Default name:
      ``"SwingPoints_1"``. No concrete swing-point-detection indicator
      exists in `indicators/` yet (it is not part of the 17 indicators
      listed in `PROJECT_STATE.md`); this analyzer documents the exact
      shape it expects so that a future indicator (or an `app/`-layer
      pivot detector) can supply it, exactly as `TrendAnalyzer` already
      documents the `SMA_20`/`EMA_12`/... shapes it expects.

The **high** pair (`swing_high_1`/`swing_high_2`) and **low** pair
(`swing_low_1`/`swing_low_2`) are optional independently -- either can
be used on its own. `analyze()` raises `InsufficientDataError` only
when *neither* pair is usable.

Like `VolumeAnalyzer`, this analyzer also reads the latest candle
already carried on `AnalysisContext.market_state.latest_candle` (close
price only) -- data that already exists on the context passed to every
analyzer, not a new indicator, new fetch, or new domain concept. It is
used only to test whether price has broken past the most recent swing
point (for **BOS**/**CHOCH** below); its absence never raises, it only
means BOS/CHOCH cannot be evaluated for this call.

Score semantics (directional, like `TrendAnalyzer`/`MomentumAnalyzer`/
`VolumeAnalyzer`, unlike `VolatilityAnalyzer`'s direction-free regime
score): `-1.0` (strong bearish structure) .. `0.0` (neutral/mixed
structure) .. `+1.0` (strong bullish structure). Confidence: `0.0` ..
`1.0`.

This analyzer covers exactly the eleven facets called out by its
design brief, and no more (no AI, no signals, no strategies, no trading
decisions -- only a scored, fully-explained `AnalysisResult`):

    - **HH** / **HL** / **LH** / **LL**: classification of the latest
      swing high against the previous swing high (`HH` higher-high /
      `LH` lower-high) and the latest swing low against the previous
      swing low (`HL` higher-low / `LL` lower-low).
    - **Swing High** / **Swing Low**: the raw swing-point values behind
      that classification, exposed in `metadata`.
    - **BOS** (Break of Structure): price breaking past the most recent
      swing point *in the direction of* the structure bias already
      established by HH/HL or LH/LL -- a continuation signal.
    - **CHOCH** (Change of Character): price breaking past the most
      recent swing point *against* the established structure bias -- a
      reversal signal.
    - **Trend continuation** / **Trend reversal**: `0.0`..`1.0`
      confidence-style readings on which of the two (BOS-like
      continuation vs. CHOCH-like reversal) the current structure
      favors.
    - **Market regime**: a single label -- `"uptrend"`, `"downtrend"`,
      or `"ranging"` (mixed/mismatched structure) -- summarizing the
      structure bias.

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
    score_label,
    weighted_average,
)

#: Number of independent structural components this analyzer can use
#: (high-pair classification, low-pair classification, structure break).
_MAX_COMPONENTS = 3

#: Weight applied to the structure-break component's contribution to
#: the overall weighted-average score. A confirmed break is live price
#: action breaking past a swing point -- more decisive than the
#: two-point HH/HL/LH/LL comparison alone -- so both a BOS and a CHOCH
#: are weighted heavily enough to move (and, for a CHOCH, flip) the
#: overall score toward the break's own direction. A CHOCH is still
#: given slightly less weight than a BOS: it is a single-event first
#: sign of reversal, working against an already-established bias,
#: rather than a break confirming a bias already agreed on by both the
#: high and low components. Magnitude (the component's own +/-1.0
#: score) is unaffected -- only its weight in the blend.
_CHOCH_WEIGHT = 2.5
_BOS_WEIGHT = 3.0


class MarketStructureAnalyzer(BaseAnalyzer):
    """
    Interprets swing-point structure (HH/HL/LH/LL, BOS, CHOCH) -- plus
    the latest candle already carried on `AnalysisContext.market_state`
    -- into a single market-structure `AnalysisResult`.

    Parameters:
        swing_points_name: `indicator_name` of the swing-points
            `IndicatorResult` entry expected on the context. Default:
            ``"SwingPoints_1"``.
        name: Analyzer name, forwarded to `BaseAnalyzer`.
    """

    def __init__(
        self,
        *,
        swing_points_name: str = "SwingPoints_1",
        name: Optional[str] = None,
    ) -> None:
        super().__init__(name=name)
        self.swing_points_name = swing_points_name

    # ------------------------------------------------------------------
    # BaseAnalyzer API
    # ------------------------------------------------------------------
    def analyze(self, context: AnalysisContext) -> AnalysisResult:
        self.validate_context(context)

        swing_high_1, swing_high_2, swing_low_1, swing_low_2 = self._swing_points(context)

        components: dict[str, float] = {}
        weights: dict[str, float] = {}
        detail: dict[str, Any] = {}

        high_classification, high_score = self._classify_pair(swing_high_1, swing_high_2, "H")
        if high_score is not None:
            components["high_structure"] = high_score
            weights["high_structure"] = 1.0
        detail["swing_high"] = {
            "computable": high_score is not None,
            "value": swing_high_1,
            "previous": swing_high_2,
            "classification": high_classification,
        }

        low_classification, low_score = self._classify_pair(swing_low_1, swing_low_2, "L")
        if low_score is not None:
            components["low_structure"] = low_score
            weights["low_structure"] = 1.0
        detail["swing_low"] = {
            "computable": low_score is not None,
            "value": swing_low_1,
            "previous": swing_low_2,
            "classification": low_classification,
        }

        if not components:
            raise InsufficientDataError(
                f"{self.name} requires at least one of a swing-high pair or a "
                f"swing-low pair on indicator '{self.swing_points_name}' "
                f"(keys 'swing_high_1'/'swing_high_2' or 'swing_low_1'/"
                f"'swing_low_2'); none were usable for {context.symbol}/"
                f"{context.timeframe}."
            )

        bias = self._structure_bias(high_classification, low_classification)

        current_price = self._current_price(context)
        bos, choch = self._structure_break(
            current_price, swing_high_1, swing_low_1, bias
        )
        break_score, break_weight, break_detail = self._break_component(bos, choch)
        if break_score is not None:
            components["structure_break"] = break_score
            weights["structure_break"] = break_weight
        detail["bos"] = break_detail["bos"]
        detail["choch"] = break_detail["choch"]

        weighted = [(components[key], weights[key]) for key in components]
        overall_score = clip(weighted_average(weighted))
        conviction = mean_abs(components.values())
        completeness = completeness_ratio(len(components), _MAX_COMPONENTS)
        bias_clarity = 1.0 if bias in ("bullish", "bearish") else 0.5
        confidence = clip(completeness * conviction * bias_clarity, 0.0, 1.0)

        trend_continuation, trend_reversal = self._continuation_vs_reversal(bos, choch, bias)
        market_regime = self._market_regime(bias)

        summary = (
            f"Market structure is {score_label(overall_score)} "
            f"(score={overall_score:.2f}, confidence={confidence:.2f}); "
            f"regime={market_regime}, high={high_classification}, "
            f"low={low_classification}."
        )

        metadata: dict[str, Any] = {
            "components_used": sorted(components),
            "component_scores": components,
            "completeness_ratio": completeness,
            "conviction": conviction,
            "bias_clarity": bias_clarity,
            "structure_bias": bias,
            "market_regime": market_regime,
            "trend_continuation": trend_continuation,
            "trend_reversal": trend_reversal,
            "swing_high": detail["swing_high"],
            "swing_low": detail["swing_low"],
            "bos": detail["bos"],
            "choch": detail["choch"],
            "score_scale": "-1.0 (strong bearish structure) .. 0.0 (neutral/mixed) .. +1.0 (strong bullish structure)",
            "confidence_scale": "0.0 (no confidence) .. 1.0 (full confidence)",
        }

        return self._build_result(
            context,
            score=overall_score,
            confidence=confidence,
            summary=summary,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # HH / HL / LH / LL classification
    # ------------------------------------------------------------------
    @staticmethod
    def _classify_pair(
        latest: Optional[float], previous: Optional[float], kind: str
    ) -> tuple[Optional[str], Optional[float]]:
        """
        Classify a (latest, previous) swing-point pair.

        `kind` is ``"H"`` for a swing-high pair (returns ``"HH"``/``"LH"``)
        or ``"L"`` for a swing-low pair (returns ``"HL"``/``"LL"``).
        Returns `(None, None)` if either value is missing/non-finite.
        Returns a score of `1.0` for a higher reading, `-1.0` for a
        lower reading, and `0.0` for an exactly equal reading (no new
        higher or lower point yet formed).
        """
        if not is_finite_number(latest) or not is_finite_number(previous):
            return None, None
        latest = float(latest)
        previous = float(previous)
        higher_label = "HH" if kind == "H" else "HL"
        lower_label = "LH" if kind == "H" else "LL"
        if latest > previous:
            return higher_label, 1.0
        if latest < previous:
            return lower_label, -1.0
        return f"equal_{'high' if kind == 'H' else 'low'}", 0.0

    @staticmethod
    def _structure_bias(
        high_classification: Optional[str], low_classification: Optional[str]
    ) -> str:
        """
        Combine the high/low classifications into an overall structure
        bias: ``"bullish"`` (HH + HL), ``"bearish"`` (LH + LL), or
        ``"mixed"`` (anything else, including a missing pair -- e.g.
        HH without a low reading, or a clean HH + LL mismatch).
        """
        if high_classification == "HH" and low_classification == "HL":
            return "bullish"
        if high_classification == "LH" and low_classification == "LL":
            return "bearish"
        return "mixed"

    @staticmethod
    def _market_regime(bias: str) -> str:
        """Translate `bias` into a human-readable market-regime label."""
        if bias == "bullish":
            return "uptrend"
        if bias == "bearish":
            return "downtrend"
        return "ranging"

    # ------------------------------------------------------------------
    # BOS / CHOCH
    # ------------------------------------------------------------------
    @staticmethod
    def _structure_break(
        current_price: Optional[float],
        swing_high_1: Optional[float],
        swing_low_1: Optional[float],
        bias: str,
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Determine whether `current_price` breaks past the most recent
        swing high or swing low, and whether that break is a BOS
        (continuation, matching `bias`) or a CHOCH (reversal, against
        `bias`).

        Returns `(bos_direction, choch_direction)`, each one of
        `"bullish"`/`"bearish"`/`None`. At most one of the two pairs is
        non-`None` at a time (a single break is either a BOS or a
        CHOCH, never both). Returns `(None, None)` if `current_price`
        or the relevant swing point is unavailable, or if price has not
        broken past either swing point.
        """
        if not is_finite_number(current_price):
            return None, None
        current_price = float(current_price)

        if is_finite_number(swing_high_1) and current_price > float(swing_high_1):
            if bias == "bullish":
                return "bullish", None
            return None, "bullish"

        if is_finite_number(swing_low_1) and current_price < float(swing_low_1):
            if bias == "bearish":
                return "bearish", None
            return None, "bearish"

        return None, None

    @staticmethod
    def _break_component(
        bos: Optional[str], choch: Optional[str]
    ) -> tuple[Optional[float], float, dict[str, Any]]:
        """
        Turn `bos`/`choch` into a `(score, weight, detail)` triple for
        the `structure_break` component. `score` is `None` (component
        not computable) when neither a BOS nor a CHOCH was detected.
        """
        bos_detail = {"detected": bos is not None, "direction": bos}
        choch_detail = {"detected": choch is not None, "direction": choch}
        detail = {"bos": bos_detail, "choch": choch_detail}

        if bos is not None:
            score = 1.0 if bos == "bullish" else -1.0
            return score, _BOS_WEIGHT, detail
        if choch is not None:
            score = 1.0 if choch == "bullish" else -1.0
            return score, _CHOCH_WEIGHT, detail
        return None, 0.0, detail

    @staticmethod
    def _continuation_vs_reversal(
        bos: Optional[str], choch: Optional[str], bias: str
    ) -> tuple[float, float]:
        """
        `(trend_continuation, trend_reversal)`, each `0.0`..`1.0`.

        A confirmed BOS is the strongest continuation signal available
        here (`1.0`/`0.0`); a confirmed CHOCH is the strongest reversal
        signal (`0.0`/`1.0`). Absent either, an already-clean bullish/
        bearish bias still leans toward continuation (structure intact,
        no break yet), while a mixed bias leans toward reversal (the
        structure itself is already contradictory).
        """
        if bos is not None:
            return 1.0, 0.0
        if choch is not None:
            return 0.0, 1.0
        if bias in ("bullish", "bearish"):
            return 0.6, 0.2
        return 0.2, 0.5

    # ------------------------------------------------------------------
    # Context access helpers
    # ------------------------------------------------------------------
    def _swing_points(
        self, context: AnalysisContext
    ) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """
        Return `(swing_high_1, swing_high_2, swing_low_1, swing_low_2)`
        from the `swing_points_name` indicator, as floats, or `None`
        per-value if unavailable/non-finite.
        """
        return (
            self._value(context, "swing_high_1"),
            self._value(context, "swing_high_2"),
            self._value(context, "swing_low_1"),
            self._value(context, "swing_low_2"),
        )

    def _value(self, context: AnalysisContext, key: str) -> Optional[float]:
        indicator = context.get_indicator(self.swing_points_name)
        if indicator is None:
            return None
        value = indicator.values.get(key)
        if not is_finite_number(value):
            return None
        return float(value)

    @staticmethod
    def _current_price(context: AnalysisContext) -> Optional[float]:
        """`close` of `context.market_state.latest_candle`, or `None`."""
        candle = context.market_state.latest_candle
        if candle is None:
            return None
        close_price = float(candle.close)
        if not is_finite_number(close_price):
            return None
        return close_price
