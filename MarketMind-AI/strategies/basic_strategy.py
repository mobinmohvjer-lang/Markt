"""
strategies/basic_strategy.py

Defines `BasicStrategy`: Strategy Engine Part 2 -- the first concrete
`BaseStrategy` implementation, built directly on Part 1's foundation
(`BaseStrategy`, `StrategyContext`, `StrategyResult`).

Scope
-----
`BasicStrategy` turns one `StrategyContext` -- an `AnalysisResult`
(matched by `analyzer_name`, default `"AnalysisAggregator"`, the same
lookup convention `signals.technical_signal_generator.
TechnicalSignalGenerator` already uses), an optional `signals.result.
SignalResult`, and an optional `strategies.risk_management.result.
RiskResult` -- into a single `StrategyResult`. It does this in three
deterministic, fully-explained steps:

    1. **Directional scoring.** The `AnalysisResult.score` (assumed
       `-1.0`..`+1.0`, the scale `analysis.aggregator.
       AnalysisAggregator` and every `analysis.technical` analyzer
       already document) and, when available, the `SignalResult`'s
       signed score (`direction` sign x `strength`, the same
       convention `signals.aggregator.SignalAggregator` uses) are
       combined into one confidence-weighted `overall_score`, then
       mapped onto `core.enums.SignalDirection` (`BUY`/`SELL`/`HOLD`)
       via configurable `buy_threshold`/`sell_threshold` -- the exact
       thresholding convention `TechnicalSignalGenerator` already
       established one layer down.
    2. **Consistency evaluation.** How much the inputs agree is scored
       on `0.0`..`1.0`: whether the analysis-derived direction and the
       signal's own direction agree (when a signal is present), and
       whether the tentative action is actually approved by the risk
       evaluation (when one is present). A signal or risk evaluation
       that is simply absent is never treated as a disagreement -- it
       only lowers how complete the picture is (see `completeness`
       below), the same "absence only lowers confidence, it never
       raises" convention every prior engine part in this repository
       follows.
    3. **Risk gate.** If a `RiskResult` is present and `approved` is
       `False`, a would-be `BUY`/`SELL` action is downgraded to `HOLD`
       (`metadata["risk_override"] = True`) -- mirroring how `signals.
       filters.ConflictFilter` downgrades a conflicting signal to
       `HOLD` rather than silently ignoring the conflict. A `HOLD`
       action is never overridden -- there is nothing for risk to
       approve or reject when no trade is being proposed.

`confidence` combines each contributing result's own `confidence`
(weighted the same way `overall_score` is), the consistency score from
step 2, and a completeness ratio (`analysis` is required, so it always
counts; `signal`/`risk` each add to completeness only when present) --
mirroring the `completeness * conviction * confidence` shape `analysis.
aggregator.AnalysisAggregator` and `signals.aggregator.SignalAggregator`
both already use one layer down.

Every intermediate value (the analysis/signal/risk facets used, the
combined score, the consistency components, the confidence breakdown,
whether a risk override happened) is recorded in `StrategyResult.
metadata` for full traceability -- `StrategyResult` itself carries no
`score` field (mirroring `RiskResult`'s minimalism), so the required
"overall strategy score" lives at `metadata["overall_score"]`.

Determinism
-----------
No randomness, no wall-clock reads, no network/database I/O: `decide()`
is a pure function of its `StrategyContext` and this strategy's
constructor configuration. The same context always produces the same
`StrategyResult`.

Boundaries
----------
No AI: only arithmetic combination of already-computed scores/results.
No order execution, no broker integration: nothing here places,
cancels, or simulates a trade.
No portfolio management: `BasicStrategy` never reads a `Portfolio` or
sizes anything -- `RiskResult.approved`/`risk_score` are consumed
exactly as already computed by `strategies.risk_management`.
No optimization: thresholds/weights are simple, caller-configurable
constants, never fit or searched over.
No parallel strategy variants: this module implements exactly one
concrete strategy, `BasicStrategy`; additional strategies remain future
Strategy Engine parts.
No change to `strategies.base_strategy`/`context`/`result`/
`exceptions`/`utils`, `strategies.risk_management`, `analysis/`, or
`signals/` -- all consumed exactly as they already exist.
"""

from __future__ import annotations

from typing import Any, Optional

from core.enums import SignalDirection

from strategies.base_strategy import BaseStrategy
from strategies.context import StrategyContext
from strategies.exceptions import (
    InsufficientStrategyDataError,
    StrategyConfigurationError,
)
from strategies.result import StrategyResult
from strategies.utils import clip

#: Default `AnalysisResult.analyzer_name` this strategy looks for on a
#: `StrategyContext`. Matches `AnalysisAggregator`'s own default `name`
#: and `TechnicalSignalGenerator`'s `DEFAULT_AGGREGATOR_NAME`.
DEFAULT_ANALYSIS_ANALYZER_NAME = "AnalysisAggregator"

#: Combined score strictly above this value is `SignalDirection.BUY`.
DEFAULT_SELL_THRESHOLD = -0.2                             
DEFAULT_BUY_THRESHOLD = 0.2
#: Default relative weights for combining the analysis-derived score
#: and the signal-derived score into `overall_score`. Analysis is
#: weighted higher by default since it is the one required input;
#: `signal` is corroborating evidence when present.
DEFAULT_ANALYSIS_WEIGHT = 0.6
DEFAULT_SIGNAL_WEIGHT = 0.4

#: Maps `core.enums.SignalDirection` onto a signed multiplier, used to
#: turn a `SignalResult`'s categorical `direction` + `strength` into a
#: single signed score comparable to `AnalysisResult.score`, the same
#: "direction sign x strength" convention `signals.aggregator.
#: SignalAggregator` already uses.
_DIRECTION_SIGN: dict[SignalDirection, float] = {
    SignalDirection.BUY: 1.0,
    SignalDirection.SELL: -1.0,
    SignalDirection.HOLD: 0.0,
}


class BasicStrategy(BaseStrategy):
    """
    A simple, fully-explainable `BaseStrategy` implementation.

    Combines one `AnalysisResult`, an optional `SignalResult`, and an
    optional `RiskResult` into a single `StrategyResult`, evaluating
    how consistent the inputs are with each other and gating the final
    action on risk approval. See the module docstring for the full
    scoring/consistency/confidence shape.

    Attributes:
        analysis_analyzer_name: The `AnalysisResult.analyzer_name` this
            strategy looks up via `StrategyContext.get_analysis_result`.
        buy_threshold: Combined score strictly above this value is
            `SignalDirection.BUY`. Must be a finite number in
            `(0.0, 1.0]`.
        sell_threshold: Combined score strictly below this value is
            `SignalDirection.SELL`. Must be a finite number in
            `[-1.0, 0.0)`.
        analysis_weight: Relative weight given to the analysis-derived
            score/confidence when combining with the signal-derived
            score/confidence. Must be finite and `>= 0.0`.
        signal_weight: Relative weight given to the signal-derived
            score/confidence, used only when a `SignalResult` is
            present. Must be finite and `>= 0.0`.

    Raises:
        StrategyConfigurationError: If `analysis_analyzer_name` is not
            a non-empty string, `buy_threshold`/`sell_threshold` are
            not finite numbers within their documented ranges, or
            `analysis_weight`/`signal_weight` are not finite,
            non-negative numbers.
    """

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        analysis_analyzer_name: str = DEFAULT_ANALYSIS_ANALYZER_NAME,
        buy_threshold: float = DEFAULT_BUY_THRESHOLD,
        sell_threshold: float = DEFAULT_SELL_THRESHOLD,
        analysis_weight: float = DEFAULT_ANALYSIS_WEIGHT,
        signal_weight: float = DEFAULT_SIGNAL_WEIGHT,
    ) -> None:
        super().__init__(name=name)

        if not isinstance(analysis_analyzer_name, str) or not analysis_analyzer_name.strip():
            raise StrategyConfigurationError(
                f"analysis_analyzer_name must be a non-empty string, "
                f"got {analysis_analyzer_name!r}"
            )
        self.analysis_analyzer_name = analysis_analyzer_name

        self.buy_threshold = self._validate_threshold(
            buy_threshold, name="buy_threshold", low=0.0, high=1.0, low_inclusive=False
        )
        self.sell_threshold = self._validate_threshold(
            sell_threshold, name="sell_threshold", low=-1.0, high=0.0, high_inclusive=False
        )

        self.analysis_weight = self._validate_weight(analysis_weight, name="analysis_weight")
        self.signal_weight = self._validate_weight(signal_weight, name="signal_weight")

    # ------------------------------------------------------------------
    # Construction-time validation
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_threshold(
        value: Any,
        *,
        name: str,
        low: float,
        high: float,
        low_inclusive: bool = True,
        high_inclusive: bool = True,
    ) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise StrategyConfigurationError(f"{name} must be numeric, got {type(value).__name__}")
        numeric_value = float(value)
        lower_ok = numeric_value >= low if low_inclusive else numeric_value > low
        upper_ok = numeric_value <= high if high_inclusive else numeric_value < high
        if not (lower_ok and upper_ok):
            raise StrategyConfigurationError(
                f"{name} must be within "
                f"{'[' if low_inclusive else '('}{low}, {high}"
                f"{']' if high_inclusive else ')'}, got {numeric_value}"
            )
        return numeric_value

    @staticmethod
    def _validate_weight(value: Any, *, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise StrategyConfigurationError(f"{name} must be numeric, got {type(value).__name__}")
        numeric_value = float(value)
        if numeric_value < 0.0:
            raise StrategyConfigurationError(f"{name} must be >= 0.0, got {numeric_value}")
        return numeric_value

    # ------------------------------------------------------------------
    # BaseStrategy API
    # ------------------------------------------------------------------
    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)

        analysis_result = context.get_analysis_result(self.analysis_analyzer_name)
        if analysis_result is None:
            raise InsufficientStrategyDataError(
                f"{self.name} requires an AnalysisResult with analyzer_name="
                f"{self.analysis_analyzer_name!r} on the StrategyContext for "
                f"{context.symbol}/{context.timeframe}, but none was found among "
                f"{sorted(result.analyzer_name for result in context.analysis_results)}."
            )

        analysis_score = clip(analysis_result.score, -1.0, 1.0)
        analysis_direction = self._direction_from_score(analysis_score)

        signal_result = context.signal_result
        signal_available = context.has_signal_result()
        signal_score: Optional[float] = None
        if signal_available:
            signal_score = clip(
                _DIRECTION_SIGN[signal_result.direction] * signal_result.strength, -1.0, 1.0
            )

        risk_result = context.risk_result
        risk_available = context.has_risk_result()

        # -------- combined directional score + tentative action --------
        score_components: list[tuple[float, float]] = [
            (analysis_score, self.analysis_weight * analysis_result.confidence)
        ]
        if signal_available:
            score_components.append((signal_score, self.signal_weight * signal_result.confidence))
        overall_score = clip(self._weighted_average(score_components), -1.0, 1.0)
        raw_action = self._direction_from_score(overall_score)

        # -------- consistency evaluation --------
        analysis_signal_agreement: Optional[float] = None
        if signal_available:
            analysis_signal_agreement = self._agreement(analysis_direction, signal_result.direction)

        risk_alignment: Optional[float] = None
        risk_override = False
        if risk_available:
            # Risk only has something to approve/reject when a trade is
            # actually being proposed -- a HOLD is always "aligned".
            if raw_action == SignalDirection.HOLD or risk_result.approved:
                risk_alignment = 1.0
            else:
                risk_alignment = 0.0
                risk_override = True

        consistency_values = [
            value for value in (analysis_signal_agreement, risk_alignment) if value is not None
        ]
        # Nothing to disagree with (no signal, no risk evaluation) is
        # treated as fully consistent -- absence never manufactures a
        # conflict, it only lowers `completeness` below.
        consistency_score = (
            sum(consistency_values) / len(consistency_values) if consistency_values else 1.0
        )

        final_action = SignalDirection.HOLD if risk_override else raw_action

        # -------- confidence --------
        confidence_components: list[tuple[float, float]] = [
            (analysis_result.confidence, self.analysis_weight)
        ]
        if signal_available:
            confidence_components.append((signal_result.confidence, self.signal_weight))
        base_confidence = self._weighted_average(confidence_components)

        inputs_available = 1 + (1 if signal_available else 0) + (1 if risk_available else 0)
        completeness = inputs_available / 3.0

        confidence = clip(base_confidence * consistency_score * completeness)

        summary = self._build_summary(
            context=context,
            final_action=final_action,
            raw_action=raw_action,
            overall_score=overall_score,
            confidence=confidence,
            consistency_score=consistency_score,
            risk_override=risk_override,
            signal_available=signal_available,
            risk_available=risk_available,
        )

        metadata = self._build_metadata(
            context=context,
            analysis_result=analysis_result,
            analysis_score=analysis_score,
            analysis_direction=analysis_direction,
            signal_result=signal_result,
            signal_available=signal_available,
            signal_score=signal_score,
            risk_result=risk_result,
            risk_available=risk_available,
            overall_score=overall_score,
            raw_action=raw_action,
            final_action=final_action,
            risk_override=risk_override,
            analysis_signal_agreement=analysis_signal_agreement,
            risk_alignment=risk_alignment,
            consistency_score=consistency_score,
            base_confidence=base_confidence,
            completeness=completeness,
            confidence=confidence,
        )

        return self._build_result(
            action=final_action,
            confidence=confidence,
            summary=summary,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Deterministic scoring helpers
    # ------------------------------------------------------------------
    def _direction_from_score(self, score: float) -> SignalDirection:
        """Map a `-1.0..+1.0` score onto BUY/SELL/HOLD via this strategy's thresholds."""
        if score > self.buy_threshold:
            return SignalDirection.BUY
        if score < self.sell_threshold:
            return SignalDirection.SELL
        return SignalDirection.HOLD

    @staticmethod
    def _agreement(direction_a: SignalDirection, direction_b: SignalDirection) -> float:
        """
        Score how much two directions agree, on `0.0`..`1.0`.

        `1.0` when they match exactly, `0.5` when one is `HOLD` and the
        other is `BUY`/`SELL` (partial disagreement -- one input sees
        no clear direction while the other does), `0.0` when they are
        directly opposed (`BUY` vs `SELL`).
        """
        if direction_a == direction_b:
            return 1.0
        if SignalDirection.HOLD in (direction_a, direction_b):
            return 0.5
        return 0.0

    @staticmethod
    def _weighted_average(components: list[tuple[float, float]]) -> float:
        """
        Weighted average of `(value, weight)` pairs.

        Falls back to a plain, unweighted average when every weight is
        `0.0` (e.g. every contributing confidence was `0.0`), so a
        deterministic value is always returned rather than dividing by
        zero.
        """
        total_weight = sum(weight for _, weight in components)
        if total_weight <= 0.0:
            values = [value for value, _ in components]
            return sum(values) / len(values) if values else 0.0
        return sum(value * weight for value, weight in components) / total_weight

    # ------------------------------------------------------------------
    # Presentation helpers
    # ------------------------------------------------------------------
    def _build_summary(
        self,
        *,
        context: StrategyContext,
        final_action: SignalDirection,
        raw_action: SignalDirection,
        overall_score: float,
        confidence: float,
        consistency_score: float,
        risk_override: bool,
        signal_available: bool,
        risk_available: bool,
    ) -> str:
        summary = (
            f"{final_action.value.upper()} decision for {context.symbol}/{context.timeframe} "
            f"(overall_score={overall_score:.2f}, confidence={confidence:.2f}, "
            f"consistency={consistency_score:.2f})"
        )
        notes: list[str] = []
        if not signal_available:
            notes.append("no signal available")
        if not risk_available:
            notes.append("no risk evaluation available")
        if risk_override:
            notes.append(
                f"downgraded from {raw_action.value.upper()} because the risk "
                f"evaluation did not approve it"
            )
        if notes:
            summary += " [" + "; ".join(notes) + "]"
        return summary + "."

    def _build_metadata(
        self,
        *,
        context: StrategyContext,
        analysis_result: Any,
        analysis_score: float,
        analysis_direction: SignalDirection,
        signal_result: Any,
        signal_available: bool,
        signal_score: Optional[float],
        risk_result: Any,
        risk_available: bool,
        overall_score: float,
        raw_action: SignalDirection,
        final_action: SignalDirection,
        risk_override: bool,
        analysis_signal_agreement: Optional[float],
        risk_alignment: Optional[float],
        consistency_score: float,
        base_confidence: float,
        completeness: float,
        confidence: float,
    ) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "symbol": context.symbol,
            "timeframe": context.timeframe,
            "score_scale": "-1.0 (strong bearish) .. 0.0 (neutral) .. +1.0 (strong bullish)",
            "overall_score": overall_score,
            "raw_action": raw_action.value,
            "final_action": final_action.value,
            "risk_override": risk_override,
            "analysis": {
                "available": True,
                "analyzer_name": analysis_result.analyzer_name,
                "score": analysis_result.score,
                "score_used": analysis_score,
                "confidence": analysis_result.confidence,
                "direction": analysis_direction.value,
                "summary": analysis_result.summary,
                "weight": self.analysis_weight,
            },
            "signal": (
                {
                    "available": True,
                    "direction": signal_result.direction.value,
                    "strength": signal_result.strength,
                    "confidence": signal_result.confidence,
                    "signed_score": signal_score,
                    "summary": signal_result.summary,
                    "weight": self.signal_weight,
                }
                if signal_available
                else {"available": False, "weight": self.signal_weight}
            ),
            "risk": (
                {
                    "available": True,
                    "approved": risk_result.approved,
                    "risk_score": risk_result.risk_score,
                    "confidence": risk_result.confidence,
                    "summary": risk_result.summary,
                }
                if risk_available
                else {"available": False}
            ),
            "consistency": {
                "analysis_signal_agreement": analysis_signal_agreement,
                "risk_alignment": risk_alignment,
                "consistency_score": consistency_score,
            },
            "confidence_breakdown": {
                "base_confidence": base_confidence,
                "completeness": completeness,
                "consistency_score": consistency_score,
                "final_confidence": confidence,
            },
            "thresholds": {
                "buy_threshold": self.buy_threshold,
                "sell_threshold": self.sell_threshold,
            },
            "weights": {
                "analysis_weight": self.analysis_weight,
                "signal_weight": self.signal_weight,
            },
            "inputs_available": {
                "analysis": True,
                "signal": signal_available,
                "risk": risk_available,
            },
        }
