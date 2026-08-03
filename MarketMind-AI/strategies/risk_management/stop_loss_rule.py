"""
strategies/risk_management/stop_loss_rule.py

Defines `StopLossRule`: a concrete `BaseRiskManager` implementation
(Risk Engine Part 3) that computes a protective stop-loss price for a
candidate `RiskContext`, direction-aware (below the reference price for
a `BUY` signal, above it for a `SELL` signal).

Independent of `PositionSizeRule` and `TakeProfitRule` -- it does not
import or depend on either, and computes its own per-unit risk distance
internally rather than being handed one, mirroring the independence
already established between `analysis.technical`'s analyzers and
`signals/filters.py`'s filters.

Model:
    1. A reference (entry) price is resolved from
       `RiskContext.signal.metadata["entry_price"]` (explicit override)
       or `RiskContext.market_state.latest_candle.close`. Unlike ATR
       (see below), this is *required* -- a stop-loss is a price, and
       no price data on the context means no price can be produced.
    2. A stop distance, expressed as a fraction of the reference price,
       is estimated from ATR when available (`atr_value *
       atr_multiplier / reference_price`) or falls back to a
       configured `default_stop_distance_pct`. The distance is clamped
       to `[min_stop_distance_pct, max_stop_distance_pct]`.
    3. The stop-loss price is `reference_price - distance` for a `BUY`
       signal, `reference_price + distance` for a `SELL` signal, and
       not applicable at all for `HOLD`.

Inputs consumed:
    - `RiskContext.signal.confidence` (required -- see Raises below).
    - `RiskContext.signal.direction`: `SignalDirection.HOLD`
      short-circuits to an explicit "not applicable" result.
    - A reference price (required -- see Raises below), from
      `RiskContext.signal.metadata["entry_price"]` or
      `RiskContext.market_state.latest_candle.close`.
    - Optional: an ATR `IndicatorResult` on
      `RiskContext.market_state.indicators` (default name `"ATR_14"`,
      matching `analysis.technical.volatility_analyzer`'s convention).
      Its absence only falls back to the percentage-based distance and
      lowers `confidence`, it never raises.

No AI, no Strategy Engine, no order execution, and no writing to
`core.entities.position.Position.stop_loss` -- this only recommends a
price via `RiskResult.metadata`; acting on it is out of scope.
"""

from __future__ import annotations

from typing import Any, Optional

from core.entities.market_state import MarketState
from core.entities.signal import Signal
from core.enums import SignalDirection

from strategies.risk_management.base import BaseRiskManager
from strategies.risk_management.context import RiskContext
from strategies.risk_management.exceptions import (
    InsufficientRiskDataError,
    RiskManagerConfigurationError,
)
from strategies.risk_management.result import RiskResult
from strategies.risk_management.utils import clip

# Default constructor configuration -- see `StopLossRule.__init__` for
# what each controls.
DEFAULT_ATR_MULTIPLIER = 2.0
DEFAULT_STOP_DISTANCE_PCT = 0.02
DEFAULT_MIN_STOP_DISTANCE_PCT = 0.001
DEFAULT_MAX_STOP_DISTANCE_PCT = 0.2
DEFAULT_ATR_INDICATOR_NAME = "ATR_14"

#: Smallest positive price a computed stop-loss is allowed to floor to,
#: so a wide distance on a low-priced instrument never produces a
#: non-positive price.
_MIN_PRICE_FLOOR = 1e-8


class StopLossRule(BaseRiskManager):
    """
    Computes a direction-aware, protective stop-loss price for a
    candidate signal.

    Attributes:
        atr_multiplier: Multiplier applied to the ATR reading (when
            available) to derive the stop distance.
        default_stop_distance_pct: Fallback stop distance, expressed as
            a fraction of the reference price, used when no ATR
            reading is available.
        min_stop_distance_pct: Minimum stop distance (as a fraction of
            price) the computed distance is clamped to.
        max_stop_distance_pct: Maximum stop distance (as a fraction of
            price) the computed distance is clamped to.
        atr_indicator_name: `indicator_name` of the ATR `IndicatorResult`
            entry looked up on `RiskContext.market_state.indicators`.
    """

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
        default_stop_distance_pct: float = DEFAULT_STOP_DISTANCE_PCT,
        min_stop_distance_pct: float = DEFAULT_MIN_STOP_DISTANCE_PCT,
        max_stop_distance_pct: float = DEFAULT_MAX_STOP_DISTANCE_PCT,
        atr_indicator_name: str = DEFAULT_ATR_INDICATOR_NAME,
    ) -> None:
        super().__init__(name=name)

        if isinstance(atr_multiplier, bool) or not isinstance(atr_multiplier, (int, float)):
            raise RiskManagerConfigurationError(
                f"atr_multiplier must be numeric, got {type(atr_multiplier).__name__}"
            )
        if atr_multiplier <= 0.0:
            raise RiskManagerConfigurationError(
                f"atr_multiplier must be > 0.0, got {atr_multiplier}"
            )
        self.atr_multiplier = float(atr_multiplier)

        self.min_stop_distance_pct = self._validate_positive_fraction(
            min_stop_distance_pct, name="min_stop_distance_pct"
        )
        self.max_stop_distance_pct = self._validate_positive_fraction(
            max_stop_distance_pct, name="max_stop_distance_pct"
        )
        if self.min_stop_distance_pct >= self.max_stop_distance_pct:
            raise RiskManagerConfigurationError(
                "min_stop_distance_pct must be < max_stop_distance_pct, got "
                f"{self.min_stop_distance_pct} >= {self.max_stop_distance_pct}"
            )

        self.default_stop_distance_pct = self._validate_positive_fraction(
            default_stop_distance_pct, name="default_stop_distance_pct"
        )
        if not (
            self.min_stop_distance_pct <= self.default_stop_distance_pct <= self.max_stop_distance_pct
        ):
            raise RiskManagerConfigurationError(
                "default_stop_distance_pct must be within "
                f"[min_stop_distance_pct, max_stop_distance_pct], got "
                f"{self.default_stop_distance_pct} outside "
                f"[{self.min_stop_distance_pct}, {self.max_stop_distance_pct}]"
            )

        if not isinstance(atr_indicator_name, str) or not atr_indicator_name.strip():
            raise RiskManagerConfigurationError(
                f"atr_indicator_name must be a non-empty string, got {atr_indicator_name!r}"
            )
        self.atr_indicator_name = atr_indicator_name

    # ------------------------------------------------------------------
    # Construction-time validation
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_positive_fraction(value: Any, *, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RiskManagerConfigurationError(f"{name} must be numeric, got {type(value).__name__}")
        numeric_value = float(value)
        if not (0.0 < numeric_value <= 1.0):
            raise RiskManagerConfigurationError(
                f"{name} must be within (0.0, 1.0], got {numeric_value}"
            )
        return numeric_value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def evaluate(self, context: RiskContext) -> RiskResult:
        """
        Evaluate `context` and return a `RiskResult` recommending a
        stop-loss price in `metadata`.

        Raises:
            InsufficientRiskDataError: If `context.signal.confidence`
                is not a usable, finite number, or if no reference
                price is available at all (neither an explicit
                `signal.metadata["entry_price"]` override nor
                `context.market_state.latest_candle.close`) -- a
                stop-loss is a price, and no price data means none can
                be computed.
        """
        context = self.validate_context(context)
        signal = context.signal

        signal_confidence, confidence_clamped = self._extract_signal_confidence(signal)

        if signal.direction == SignalDirection.HOLD:
            return self._build_result(
                approved=False,
                risk_score=0.0,
                confidence=signal_confidence,
                summary="No stop-loss computed: HOLD signal has no position to protect.",
                metadata={
                    "risk_manager": self.name,
                    "reason": "hold_signal",
                    "signal_direction": signal.direction.value,
                    "signal_confidence": signal_confidence,
                    "stop_loss_price": None,
                },
            )

        reference_price, reference_price_source = self._extract_reference_price(context)
        if reference_price is None:
            raise InsufficientRiskDataError(
                "no usable reference price available (neither "
                "signal.metadata['entry_price'] nor "
                "market_state.latest_candle.close) -- cannot compute a stop-loss"
            )

        atr_value = self._find_atr_value(context.market_state)
        atr_available = atr_value is not None

        if atr_available:
            raw_distance_pct = (atr_value * self.atr_multiplier) / reference_price
            basis = "atr"
        else:
            raw_distance_pct = self.default_stop_distance_pct
            basis = "default_pct"

        distance_pct = clip(
            raw_distance_pct, self.min_stop_distance_pct, self.max_stop_distance_pct
        )
        distance_clamped = distance_pct != raw_distance_pct
        distance = reference_price * distance_pct

        if signal.direction == SignalDirection.BUY:
            stop_loss_price = reference_price - distance
        else:  # SignalDirection.SELL
            stop_loss_price = reference_price + distance

        floored_to_min_price = stop_loss_price < _MIN_PRICE_FLOOR
        if floored_to_min_price:
            stop_loss_price = _MIN_PRICE_FLOOR

        risk_score = clip(distance_pct / self.max_stop_distance_pct)
        completeness = 1.0 if atr_available else 0.7
        confidence = clip(signal_confidence * completeness)

        summary = (
            f"Stop-loss set at {stop_loss_price:.8f} "
            f"({distance_pct * 100:.3f}% {('below' if signal.direction == SignalDirection.BUY else 'above')} "
            f"reference price {reference_price:.8f}, basis={basis})"
        )

        metadata: dict[str, Any] = {
            "risk_manager": self.name,
            "signal_direction": signal.direction.value,
            "signal_confidence": signal_confidence,
            "signal_confidence_clamped": confidence_clamped,
            "reference_price": reference_price,
            "reference_price_source": reference_price_source,
            "atr_available": atr_available,
            "atr_value": atr_value,
            "atr_indicator_name": self.atr_indicator_name,
            "basis": basis,
            "raw_distance_pct": raw_distance_pct,
            "distance_pct": distance_pct,
            "distance_clamped": distance_clamped,
            "distance": distance,
            "stop_loss_price": stop_loss_price,
            "floored_to_min_price": floored_to_min_price,
            "config": {
                "atr_multiplier": self.atr_multiplier,
                "default_stop_distance_pct": self.default_stop_distance_pct,
                "min_stop_distance_pct": self.min_stop_distance_pct,
                "max_stop_distance_pct": self.max_stop_distance_pct,
            },
        }

        return self._build_result(
            approved=True,
            risk_score=risk_score,
            confidence=confidence,
            summary=summary,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Facet extraction helpers
    # ------------------------------------------------------------------
    def _extract_signal_confidence(self, signal: Signal) -> tuple[float, bool]:
        """
        Return `(signal_confidence, was_clamped)`.

        Raises:
            InsufficientRiskDataError: If `signal.confidence` is not a
                usable, finite number.
        """
        raw_confidence = signal.confidence
        if isinstance(raw_confidence, bool) or not isinstance(raw_confidence, (int, float)):
            raise InsufficientRiskDataError(
                f"signal.confidence must be numeric, got {type(raw_confidence).__name__}"
            )
        numeric_confidence = float(raw_confidence)
        if numeric_confidence != numeric_confidence or numeric_confidence in (
            float("inf"),
            float("-inf"),
        ):
            raise InsufficientRiskDataError(
                f"signal.confidence must be finite, got {numeric_confidence}"
            )
        clamped_confidence = clip(numeric_confidence)
        was_clamped = clamped_confidence != numeric_confidence
        return clamped_confidence, was_clamped

    @staticmethod
    def _extract_reference_price(context: RiskContext) -> tuple[Optional[float], str]:
        """
        Return `(reference_price, source)`.

        Priority: an explicit `"entry_price"` entry on
        `context.signal.metadata`, then
        `context.market_state.latest_candle.close`. Unlike ATR, this is
        a required input for this rule -- see `evaluate`'s `Raises`.
        """
        metadata = context.signal.metadata
        if isinstance(metadata, dict) and "entry_price" in metadata:
            raw = metadata["entry_price"]
            try:
                numeric = float(raw)
            except (TypeError, ValueError):
                numeric = None
            if (
                numeric is not None
                and numeric == numeric
                and numeric not in (float("inf"), float("-inf"))
                and numeric > 0
            ):
                return numeric, "signal_metadata_entry_price"

        if context.market_state is not None and context.market_state.latest_candle is not None:
            try:
                numeric = float(context.market_state.latest_candle.close)
            except (TypeError, ValueError):
                numeric = None
            if numeric is not None and numeric > 0:
                return numeric, "market_state_latest_candle_close"

        return None, "unavailable"

    def _find_atr_value(self, market_state: Optional[MarketState]) -> Optional[float]:
        """
        Look up this rule's configured ATR indicator on
        `market_state.indicators` by name.

        Returns `None` (never raises) if `market_state` is absent, the
        indicator is not present, or its value is not a usable finite
        number -- ATR is an optional input for this rule.
        """
        if market_state is None:
            return None
        for indicator in market_state.indicators:
            if indicator.indicator_name != self.atr_indicator_name:
                continue
            raw = indicator.values.get("value")
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                return None
            numeric = float(raw)
            if numeric != numeric or numeric in (float("inf"), float("-inf")) or numeric < 0:
                return None
            return numeric
        return None
