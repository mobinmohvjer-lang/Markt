"""
strategies/risk_management/position_size_rule.py

Defines `PositionSizeRule`: a concrete `BaseRiskManager` implementation
(Risk Engine Part 3) that recommends how large a position a candidate
`RiskContext` should translate to, using a fixed-fractional risk model.

Independent of `StopLossRule` and `TakeProfitRule` -- it does not import
or depend on either, and computes its own per-unit risk distance
internally, mirroring the independence already established between
`analysis.technical`'s analyzers and `signals/filters.py`'s filters.

Model:
    1. `risk_amount` = portfolio equity x `risk_per_trade` -- the
       quote-currency amount the account is willing to lose if the
       stop-loss (estimated below) is hit.
    2. A per-unit risk distance, expressed as a *ratio* of price
       (never a raw price-unit distance), is estimated from ATR when
       available (`atr_value * atr_multiplier / reference_price`) or
       falls back to a configured `default_stop_distance_pct`. Because
       this is a ratio rather than a raw distance, recommended
       position size can be computed even when no reference price is
       available on the context (see below).
    3. `recommended_position_value` = `risk_amount / stop_distance_ratio`,
       capped at `max_position_fraction` of equity.
    4. `recommended_position_size` (base-asset quantity) is only
       produced when a reference price is available on the context
       (`recommended_position_value / reference_price`); otherwise only
       the quote-currency value is reported and confidence is lowered.

Inputs consumed:
    - `RiskContext.signal.confidence` (required -- see Raises below).
    - `RiskContext.signal.direction`: `SignalDirection.HOLD` short-
      circuits to an explicitly zero, unapproved sizing (nothing to
      size).
    - `RiskContext.portfolio` (`total_equity`, falling back to
      `cash_balance` + position value, matching `BasicRiskManager`'s
      own fallback -- computed independently here, not imported from
      it).
    - Optional: an ATR `IndicatorResult` on
      `RiskContext.market_state.indicators` (default name `"ATR_14"`,
      matching `analysis.technical.volatility_analyzer`'s convention)
      and `RiskContext.market_state.latest_candle.close` as the
      reference price. Both are independently optional -- their
      absence only lowers `confidence` / limits what can be reported,
      it never raises.

No AI, no Strategy Engine, no order execution -- this only recommends
a size; placing an order on it is out of scope.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from core.entities.market_state import MarketState
from core.entities.portfolio import Portfolio
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

# Default constructor configuration -- see `PositionSizeRule.__init__`
# for what each controls.
DEFAULT_RISK_PER_TRADE = 0.01
DEFAULT_MAX_POSITION_FRACTION = 0.25
DEFAULT_STOP_DISTANCE_PCT = 0.02
DEFAULT_ATR_MULTIPLIER = 2.0
DEFAULT_MIN_SIGNAL_CONFIDENCE = 0.3
DEFAULT_ATR_INDICATOR_NAME = "ATR_14"

#: Smallest stop-distance ratio treated as usable, to avoid a
#: division blow-up when ATR/price data implies a near-zero distance.
_MIN_DISTANCE_RATIO = 1e-6


class PositionSizeRule(BaseRiskManager):
    """
    Recommends a position size for a candidate signal via
    fixed-fractional risk sizing.

    Attributes:
        risk_per_trade: Fraction of portfolio equity (0.0, 1.0] the
            account is willing to risk on this single trade.
        max_position_fraction: Maximum fraction of equity (0.0, 1.0]
            a single recommended position may represent, regardless of
            the risk-based calculation.
        default_stop_distance_pct: Fallback per-unit risk distance,
            expressed as a fraction of price, used when no ATR reading
            is available.
        atr_multiplier: Multiplier applied to the ATR reading (when
            available) to derive the per-unit risk distance.
        min_signal_confidence: Minimum `signal.confidence` required for
            a recommended size to be `approved`.
        atr_indicator_name: `indicator_name` of the ATR `IndicatorResult`
            entry looked up on `RiskContext.market_state.indicators`.
    """

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        risk_per_trade: float = DEFAULT_RISK_PER_TRADE,
        max_position_fraction: float = DEFAULT_MAX_POSITION_FRACTION,
        default_stop_distance_pct: float = DEFAULT_STOP_DISTANCE_PCT,
        atr_multiplier: float = DEFAULT_ATR_MULTIPLIER,
        min_signal_confidence: float = DEFAULT_MIN_SIGNAL_CONFIDENCE,
        atr_indicator_name: str = DEFAULT_ATR_INDICATOR_NAME,
    ) -> None:
        super().__init__(name=name)

        self.risk_per_trade = self._validate_fraction(risk_per_trade, name="risk_per_trade")
        self.max_position_fraction = self._validate_fraction(
            max_position_fraction, name="max_position_fraction"
        )
        self.default_stop_distance_pct = self._validate_fraction(
            default_stop_distance_pct, name="default_stop_distance_pct"
        )
        self.min_signal_confidence = self._validate_fraction(
            min_signal_confidence, name="min_signal_confidence"
        )

        if isinstance(atr_multiplier, bool) or not isinstance(atr_multiplier, (int, float)):
            raise RiskManagerConfigurationError(
                f"atr_multiplier must be numeric, got {type(atr_multiplier).__name__}"
            )
        if atr_multiplier <= 0.0:
            raise RiskManagerConfigurationError(
                f"atr_multiplier must be > 0.0, got {atr_multiplier}"
            )
        self.atr_multiplier = float(atr_multiplier)

        if not isinstance(atr_indicator_name, str) or not atr_indicator_name.strip():
            raise RiskManagerConfigurationError(
                f"atr_indicator_name must be a non-empty string, got {atr_indicator_name!r}"
            )
        self.atr_indicator_name = atr_indicator_name

    # ------------------------------------------------------------------
    # Construction-time validation
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_fraction(value: Any, *, name: str) -> float:
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
        position size in `metadata`.

        Raises:
            InsufficientRiskDataError: If `context.signal.confidence`
                is not a usable, finite number, or if portfolio equity
                cannot be resolved to a positive value -- no meaningful
                size can be recommended from either.
        """
        context = self.validate_context(context)
        signal = context.signal
        portfolio = context.portfolio

        signal_confidence, confidence_clamped = self._extract_signal_confidence(signal)
        equity = self._compute_equity(portfolio)

        reference_price, reference_price_source = self._extract_reference_price(context)
        reference_price_available = reference_price is not None

        if signal.direction == SignalDirection.HOLD:
            return self._build_result(
                approved=False,
                risk_score=0.0,
                confidence=signal_confidence,
                summary="No position sized: HOLD signal carries no directional trade to size.",
                metadata={
                    "risk_manager": self.name,
                    "reason": "hold_signal",
                    "signal_direction": signal.direction.value,
                    "signal_confidence": signal_confidence,
                    "recommended_position_size": None,
                    "recommended_position_value": None,
                },
            )

        atr_value = self._find_atr_value(context.market_state)
        atr_available = atr_value is not None

        if atr_available and reference_price_available and reference_price > 0:
            stop_distance_ratio = max(
                _MIN_DISTANCE_RATIO,
                (atr_value * self.atr_multiplier) / reference_price,
            )
            basis = "atr"
        else:
            stop_distance_ratio = self.default_stop_distance_pct
            basis = "default_pct"

        risk_amount = equity * Decimal(str(self.risk_per_trade))
        position_value_from_risk = risk_amount / Decimal(str(stop_distance_ratio))
        max_position_value = equity * Decimal(str(self.max_position_fraction))

        capped_by_max_fraction = position_value_from_risk > max_position_value
        recommended_position_value = min(position_value_from_risk, max_position_value)

        recommended_position_size: Optional[Decimal] = None
        if reference_price_available and reference_price > 0:
            recommended_position_size = recommended_position_value / Decimal(str(reference_price))

        hard_reject_reasons: list[str] = []
        if signal_confidence < self.min_signal_confidence:
            hard_reject_reasons.append(
                f"signal_confidence {signal_confidence:.3f} below minimum "
                f"{self.min_signal_confidence:.3f}"
            )
        if recommended_position_value <= 0:
            hard_reject_reasons.append("computed position value is not positive")

        approved = not hard_reject_reasons

        utilization = (
            float(recommended_position_value / max_position_value)
            if max_position_value > 0
            else 0.0
        )
        risk_score = clip(0.5 * clip(utilization) + 0.5 * clip(1.0 - signal_confidence))

        completeness = clip(
            (1.0 if atr_available else 0.7) * 0.5
            + (1.0 if reference_price_available else 0.6) * 0.5
        )
        confidence = clip(signal_confidence * completeness)

        summary = self._build_summary(
            approved=approved,
            recommended_position_value=recommended_position_value,
            hard_reject_reasons=hard_reject_reasons,
        )

        metadata: dict[str, Any] = {
            "risk_manager": self.name,
            "signal_direction": signal.direction.value,
            "signal_confidence": signal_confidence,
            "signal_confidence_clamped": confidence_clamped,
            "equity_used": str(equity),
            "risk_amount": str(risk_amount),
            "reference_price": reference_price,
            "reference_price_available": reference_price_available,
            "reference_price_source": reference_price_source,
            "atr_available": atr_available,
            "atr_value": atr_value,
            "atr_indicator_name": self.atr_indicator_name,
            "stop_distance_ratio": stop_distance_ratio,
            "basis": basis,
            "recommended_position_value": str(recommended_position_value),
            "recommended_position_size": (
                str(recommended_position_size) if recommended_position_size is not None else None
            ),
            "capped_by_max_fraction": capped_by_max_fraction,
            "config": {
                "risk_per_trade": self.risk_per_trade,
                "max_position_fraction": self.max_position_fraction,
                "default_stop_distance_pct": self.default_stop_distance_pct,
                "atr_multiplier": self.atr_multiplier,
                "min_signal_confidence": self.min_signal_confidence,
            },
            "hard_reject_reasons": hard_reject_reasons,
        }

        return self._build_result(
            approved=approved,
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
    def _compute_equity(portfolio: Portfolio) -> Decimal:
        """
        Return portfolio equity, falling back to
        `cash_balance + position_value` when `total_equity` is not
        already computed -- the same graceful fallback
        `BasicRiskManager` uses, reimplemented independently here.

        Raises:
            InsufficientRiskDataError: If resolved equity is not
                positive -- no meaningful position can be sized against
                a non-positive account.
        """
        position_value = Decimal("0")
        for position in portfolio.positions:
            price = position.current_price
            if price is None:
                price = position.entry_price
            try:
                position_value += abs(Decimal(price)) * abs(Decimal(position.quantity))
            except (InvalidOperation, TypeError):
                continue

        if portfolio.total_equity is not None:
            equity = portfolio.total_equity
        else:
            equity = portfolio.cash_balance + position_value

        if equity <= 0:
            raise InsufficientRiskDataError(
                f"portfolio equity must be positive to size a position, got {equity}"
            )
        return equity

    @staticmethod
    def _extract_reference_price(context: RiskContext) -> tuple[Optional[float], str]:
        """
        Return `(reference_price, source)`.

        Priority: an explicit `"entry_price"` entry on
        `context.signal.metadata`, then
        `context.market_state.latest_candle.close`. Its total absence
        never raises here -- it only means position size can be
        reported as a quote-currency value rather than a base-asset
        quantity, and lowers `confidence`.
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

    # ------------------------------------------------------------------
    # Presentation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_summary(
        *,
        approved: bool,
        recommended_position_value: Decimal,
        hard_reject_reasons: list[str],
    ) -> str:
        decision = "Sized" if approved else "Rejected"
        summary = f"{decision}: recommended_position_value={recommended_position_value:.8f}"
        if hard_reject_reasons:
            summary += " (" + "; ".join(hard_reject_reasons) + ")"
        return summary
