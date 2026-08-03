"""
signals/technical_signal_generator.py

Defines `TechnicalSignalGenerator`: Signal Engine Part 2 -- the first
concrete `BaseSignalGenerator` implementation.

Scope
-----
This generator standardizes exactly one `AnalysisResult` carried on its
`SignalContext` -- the merged output of `analysis.aggregator.
AnalysisAggregator` (identified by `AnalysisResult.analyzer_name`,
default `"AnalysisAggregator"`) -- into a single `SignalResult`. It does
not read the five individual `analysis.technical` analyzer outputs
directly, even when they are also present on the same `SignalContext`;
`AnalysisAggregator` has already combined them, and re-deriving a
signal from the raw components here would duplicate Part 4's merging
logic in a different package.

`AnalysisAggregator.overall_score` is a `-1.0` (strong bearish) ..
`0.0` (neutral) .. `+1.0` (strong bullish) directional score (see
`analysis/aggregator.py`). This generator maps that score onto exactly
three signal directions, reusing `core.enums.SignalDirection` (`signals/`
does not introduce a new direction enum):

    - Bullish -> `SignalDirection.BUY`  (score above `buy_threshold`)
    - Bearish -> `SignalDirection.SELL` (score below `sell_threshold`)
    - Neutral -> `SignalDirection.HOLD` (score between the two)

Boundaries
----------
No AI: only arithmetic thresholding of an already-computed score.
No risk management: this module never sizes a position or evaluates
exposure -- that is `strategies/risk_management/`'s future job.
No strategy/trading decisions: a `SignalResult` is not an order and is
not `core.entities.signal.Signal`; deciding whether/how to act on it
belongs to the future `strategies/` package.
No order execution: nothing here places, cancels, or simulates a trade.
No change to `analysis/`: `AnalysisAggregator`/`analysis.technical` are
only read via their existing public `AnalysisResult` shape.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from core.enums import SignalDirection

from signals.base import BaseSignalGenerator
from signals.context import SignalContext
from signals.exceptions import (
    InsufficientSignalDataError,
    SignalGeneratorConfigurationError,
)
from signals.result import SignalResult
from signals.utils import merge_metadata

#: Default `AnalysisResult.analyzer_name` this generator looks for on a
#: `SignalContext`. Matches `AnalysisAggregator`'s own default `name`
#: (`BaseAnalyzer.__init__`: `name or self.__class__.__name__`).
DEFAULT_AGGREGATOR_NAME = "AnalysisAggregator"

#: Maps this generator's three-way score label onto the existing
#: `core.enums.SignalDirection` members -- no new domain enum introduced.
_DIRECTION_BY_LABEL: dict[str, SignalDirection] = {
    "bullish": SignalDirection.BUY,
    "bearish": SignalDirection.SELL,
    "neutral": SignalDirection.HOLD,
}


class TechnicalSignalGenerator(BaseSignalGenerator):
    """
    Standardizes an `AnalysisAggregator` result into a `SignalResult`.

    Parameters:
        aggregator_name: The `AnalysisResult.analyzer_name` this
            generator looks up via `SignalContext.get_result`. Defaults
            to `"AnalysisAggregator"`; override only if the aggregator
            instance feeding this generator's contexts was constructed
            with a custom `name`.
        buy_threshold: Aggregator `score` strictly above this value is
            Bullish (`SignalDirection.BUY`). Must be a finite number in
            `(0.0, 1.0]`.
        sell_threshold: Aggregator `score` strictly below this value is
            Bearish (`SignalDirection.SELL`). Must be a finite number in
            `[-1.0, 0.0)`. Scores at or between the two thresholds are
            Neutral (`SignalDirection.HOLD`).
        name: Generator name, forwarded to `BaseSignalGenerator`.

    Raises:
        SignalGeneratorConfigurationError: If `aggregator_name` is not a
            non-empty string, or `buy_threshold`/`sell_threshold` are
            not finite numbers within their documented ranges.
    """

    def __init__(
        self,
        *,
        aggregator_name: str = DEFAULT_AGGREGATOR_NAME,
        buy_threshold: float = 0.2,
        sell_threshold: float = -0.2,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(name=name)
        if not isinstance(aggregator_name, str) or not aggregator_name.strip():
            raise SignalGeneratorConfigurationError(
                f"aggregator_name must be a non-empty string, got {aggregator_name!r}"
            )
        self._validate_thresholds(buy_threshold, sell_threshold)
        self.aggregator_name = aggregator_name
        self.buy_threshold = float(buy_threshold)
        self.sell_threshold = float(sell_threshold)

    # ------------------------------------------------------------------
    # BaseSignalGenerator API
    # ------------------------------------------------------------------
    def generate(self, context: SignalContext) -> SignalResult:
        self.validate_context(context)

        aggregator_result = context.get_result(self.aggregator_name)
        if aggregator_result is None:
            raise InsufficientSignalDataError(
                f"{self.name} requires an AnalysisResult with analyzer_name="
                f"{self.aggregator_name!r} on the SignalContext for "
                f"{context.symbol}/{context.timeframe}, but none was found "
                f"among {sorted(r.analyzer_name for r in context.analysis_results)}."
            )

        score = aggregator_result.score
        confidence = aggregator_result.confidence
        label = self._score_label(score)
        direction = _DIRECTION_BY_LABEL[label]
        strength = min(1.0, max(0.0, abs(score)))

        summary = (
            f"{label.capitalize()} signal for {context.symbol}/{context.timeframe} "
            f"from {self.aggregator_name} (score={score:.2f}, confidence={confidence:.2f})."
        )

        metadata = merge_metadata(
            {
                "source_analyzer": self.aggregator_name,
                "source_score": score,
                "source_confidence": confidence,
                "score_label": label,
                "buy_threshold": self.buy_threshold,
                "sell_threshold": self.sell_threshold,
                "aggregator_metadata": aggregator_result.metadata,
            }
        )

        return self._build_result(
            direction=direction,
            strength=strength,
            confidence=confidence,
            summary=summary,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _score_label(self, score: float) -> str:
        """Map an aggregator `-1.0..+1.0` score onto a three-way label."""
        if score > self.buy_threshold:
            return "bullish"
        if score < self.sell_threshold:
            return "bearish"
        return "neutral"

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
