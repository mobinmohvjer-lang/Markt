"""
strategies/risk_management/basic_risk_manager.py

Defines `BasicRiskManager`: the first concrete `BaseRiskManager`
implementation (Risk Engine Part 2), built on Part 1's foundation
(`BaseRiskManager`, `RiskContext`, `RiskResult`).

`BasicRiskManager` evaluates a candidate `RiskContext` along four
independent, deliberately simple facets:

    - Signal confidence  -- `RiskContext.signal.confidence`.
    - Signal strength    -- an optional `"strength"` value on
      `RiskContext.signal.metadata` (e.g. as carried through from an
      upstream `signals.result.SignalResult.strength`); `core.entities.
      signal.Signal` itself has no `strength` field, so this is read
      defensively and its absence only lowers confidence, it never
      raises.
    - Portfolio exposure -- the fraction of portfolio equity already
      committed to open positions, derived only from
      `RiskContext.portfolio` (`cash_balance`/`total_equity`/
      `positions`).
    - Market availability -- whether `RiskContext.market_state` is
      present at all (`RiskContext.has_market_state()`); its absence
      only lowers confidence, exactly like the optional facets already
      documented on `RiskContext`.

Each facet is turned into a `0.0..1.0` risk contribution, combined into
a single weighted `risk_score`, and paired with a small set of hard
threshold checks to decide `approved`. Every intermediate value is
recorded in `metadata` so a decision can always be traced back to the
inputs that produced it.

Deliberately out of scope, matching every other Risk Engine Part 1/2
boundary already documented in this package:
    - No position sizing.
    - No stop-loss / take-profit calculation.
    - No AI.
    - No strategy/trading-decision logic.
    - No order execution.

`BasicRiskManager` does not implement `core.interfaces.risk_manager.
RiskManager` for the same reason `BaseRiskManager` does not -- that
interface also requires `calculate_position_size`/`calculate_stop_loss`,
both out of scope here.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from core.entities.portfolio import Portfolio
from core.entities.signal import Signal

from strategies.risk_management.base import BaseRiskManager
from strategies.risk_management.context import RiskContext
from strategies.risk_management.exceptions import (
    InsufficientRiskDataError,
    RiskManagerConfigurationError,
)
from strategies.risk_management.result import RiskResult
from strategies.risk_management.utils import clip

# Default constructor configuration -- see `BasicRiskManager.__init__`
# for what each controls.
DEFAULT_CONFIDENCE_WEIGHT = 0.35
DEFAULT_STRENGTH_WEIGHT = 0.25
DEFAULT_EXPOSURE_WEIGHT = 0.30
DEFAULT_MARKET_WEIGHT = 0.10

DEFAULT_MAX_EXPOSURE_RATIO = 0.5
DEFAULT_MIN_SIGNAL_CONFIDENCE = 0.3
DEFAULT_MIN_SIGNAL_STRENGTH = 0.2
DEFAULT_RISK_SCORE_THRESHOLD = 0.6
DEFAULT_MARKET_UNAVAILABLE_RISK = 0.5
DEFAULT_MISSING_STRENGTH_RISK = 0.5

_WEIGHT_SUM_TOLERANCE = 1e-9


class BasicRiskManager(BaseRiskManager):
    """
    A simple, fully-explainable `BaseRiskManager` implementation.

    Combines signal confidence, signal strength, portfolio exposure,
    and market-data availability into one `risk_score`/`approved`
    decision, with every intermediate value preserved in
    `RiskResult.metadata` for traceability.

    Attributes:
        confidence_weight: Weight applied to the confidence-derived
            risk contribution.
        strength_weight: Weight applied to the strength-derived risk
            contribution.
        exposure_weight: Weight applied to the exposure-derived risk
            contribution.
        market_weight: Weight applied to the market-availability risk
            contribution.
        max_exposure_ratio: Portfolio exposure ratio (0.0..1.0+) at or
            above which exposure risk is treated as maximal (`1.0`)
            and, separately, above which the signal is hard-rejected
            regardless of `risk_score`.
        min_signal_confidence: Minimum `signal.confidence` required for
            approval, regardless of `risk_score`.
        min_signal_strength: Minimum signal strength (when available)
            required for approval, regardless of `risk_score`.
        risk_score_threshold: Maximum combined `risk_score` (inclusive)
            still eligible for approval.
        market_unavailable_risk: Risk contribution used for the market
            facet when no `MarketState` is available on the context.
        missing_strength_risk: Risk contribution used for the strength
            facet when no strength value is available on the signal.
    """

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        confidence_weight: float = DEFAULT_CONFIDENCE_WEIGHT,
        strength_weight: float = DEFAULT_STRENGTH_WEIGHT,
        exposure_weight: float = DEFAULT_EXPOSURE_WEIGHT,
        market_weight: float = DEFAULT_MARKET_WEIGHT,
        max_exposure_ratio: float = DEFAULT_MAX_EXPOSURE_RATIO,
        min_signal_confidence: float = DEFAULT_MIN_SIGNAL_CONFIDENCE,
        min_signal_strength: float = DEFAULT_MIN_SIGNAL_STRENGTH,
        risk_score_threshold: float = DEFAULT_RISK_SCORE_THRESHOLD,
        market_unavailable_risk: float = DEFAULT_MARKET_UNAVAILABLE_RISK,
        missing_strength_risk: float = DEFAULT_MISSING_STRENGTH_RISK,
    ) -> None:
        super().__init__(name=name)

        self.confidence_weight = self._validate_weight(confidence_weight, name="confidence_weight")
        self.strength_weight = self._validate_weight(strength_weight, name="strength_weight")
        self.exposure_weight = self._validate_weight(exposure_weight, name="exposure_weight")
        self.market_weight = self._validate_weight(market_weight, name="market_weight")

        weight_sum = (
            self.confidence_weight
            + self.strength_weight
            + self.exposure_weight
            + self.market_weight
        )
        if abs(weight_sum - 1.0) > _WEIGHT_SUM_TOLERANCE:
            raise RiskManagerConfigurationError(
                "confidence_weight + strength_weight + exposure_weight + "
                f"market_weight must sum to 1.0, got {weight_sum}"
            )

        if not isinstance(max_exposure_ratio, (int, float)) or isinstance(max_exposure_ratio, bool):
            raise RiskManagerConfigurationError(
                f"max_exposure_ratio must be numeric, got {type(max_exposure_ratio).__name__}"
            )
        if max_exposure_ratio <= 0.0:
            raise RiskManagerConfigurationError(
                f"max_exposure_ratio must be > 0.0, got {max_exposure_ratio}"
            )
        self.max_exposure_ratio = float(max_exposure_ratio)

        self.min_signal_confidence = self._validate_weight(
            min_signal_confidence, name="min_signal_confidence"
        )
        self.min_signal_strength = self._validate_weight(
            min_signal_strength, name="min_signal_strength"
        )
        self.risk_score_threshold = self._validate_weight(
            risk_score_threshold, name="risk_score_threshold"
        )
        self.market_unavailable_risk = self._validate_weight(
            market_unavailable_risk, name="market_unavailable_risk"
        )
        self.missing_strength_risk = self._validate_weight(
            missing_strength_risk, name="missing_strength_risk"
        )

    # ------------------------------------------------------------------
    # Construction-time validation
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_weight(value: Any, *, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise RiskManagerConfigurationError(f"{name} must be numeric, got {type(value).__name__}")
        numeric_value = float(value)
        if not (0.0 <= numeric_value <= 1.0):
            raise RiskManagerConfigurationError(
                f"{name} must be within [0.0, 1.0], got {numeric_value}"
            )
        return numeric_value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def evaluate(self, context: RiskContext) -> RiskResult:
        """
        Evaluate `context` and return a single `RiskResult`.

        Never raises `InsufficientRiskDataError` for an ordinarily thin
        `RiskContext` (missing signal strength or a missing
        `MarketState` only lower this result's `confidence`); it is
        only raised when `context.signal.confidence` itself is not a
        usable, finite number, since no meaningful risk assessment can
        be produced from that.
        """
        context = self.validate_context(context)
        signal = context.signal
        portfolio = context.portfolio

        signal_confidence, confidence_clamped = self._extract_signal_confidence(signal)
        signal_strength, strength_available, strength_clamped = self._extract_signal_strength(signal)
        exposure_ratio, equity_used = self._compute_exposure_ratio(portfolio)
        market_available = context.has_market_state()

        confidence_risk = clip(1.0 - signal_confidence)
        strength_risk = (
            clip(1.0 - signal_strength) if strength_available else self.missing_strength_risk
        )
        exposure_risk = clip(exposure_ratio / self.max_exposure_ratio)
        market_risk = 0.0 if market_available else self.market_unavailable_risk

        risk_score = clip(
            self.confidence_weight * confidence_risk
            + self.strength_weight * strength_risk
            + self.exposure_weight * exposure_risk
            + self.market_weight * market_risk
        )

        hard_reject_reasons: list[str] = []
        if signal_confidence < self.min_signal_confidence:
            hard_reject_reasons.append(
                f"signal_confidence {signal_confidence:.3f} below minimum "
                f"{self.min_signal_confidence:.3f}"
            )
        if strength_available and signal_strength < self.min_signal_strength:
            hard_reject_reasons.append(
                f"signal_strength {signal_strength:.3f} below minimum "
                f"{self.min_signal_strength:.3f}"
            )
        if exposure_ratio > self.max_exposure_ratio:
            hard_reject_reasons.append(
                f"exposure_ratio {exposure_ratio:.3f} exceeds maximum "
                f"{self.max_exposure_ratio:.3f}"
            )

        approved = risk_score <= self.risk_score_threshold and not hard_reject_reasons

        completeness = clip(
            (1.0 if strength_available else 0.5) * 0.5
            + (1.0 if market_available else 0.6) * 0.5
        )
        confidence = clip(signal_confidence * completeness)

        summary = self._build_summary(
            approved=approved,
            risk_score=risk_score,
            hard_reject_reasons=hard_reject_reasons,
        )

        metadata: dict[str, Any] = {
            "risk_manager": self.name,
            "signal_confidence": signal_confidence,
            "signal_confidence_clamped": confidence_clamped,
            "signal_strength": signal_strength if strength_available else None,
            "signal_strength_available": strength_available,
            "signal_strength_clamped": strength_clamped,
            "exposure_ratio": exposure_ratio,
            "equity_used_for_exposure": str(equity_used),
            "market_state_available": market_available,
            "components": {
                "confidence_risk": confidence_risk,
                "strength_risk": strength_risk,
                "exposure_risk": exposure_risk,
                "market_risk": market_risk,
            },
            "weights": {
                "confidence_weight": self.confidence_weight,
                "strength_weight": self.strength_weight,
                "exposure_weight": self.exposure_weight,
                "market_weight": self.market_weight,
            },
            "thresholds": {
                "max_exposure_ratio": self.max_exposure_ratio,
                "min_signal_confidence": self.min_signal_confidence,
                "min_signal_strength": self.min_signal_strength,
                "risk_score_threshold": self.risk_score_threshold,
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
                usable, finite number -- no meaningful risk assessment
                can be derived from it.
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

    def _extract_signal_strength(self, signal: Signal) -> tuple[float, bool, bool]:
        """
        Return `(signal_strength, was_available, was_clamped)`.

        `core.entities.signal.Signal` has no dedicated `strength`
        field, so this reads an optional `"strength"` entry from
        `signal.metadata` (e.g. carried through from an upstream
        `signals.result.SignalResult.strength`). Its absence -- or an
        unusable value -- only means strength is treated as
        unavailable; it never raises.
        """
        if not isinstance(signal.metadata, dict) or "strength" not in signal.metadata:
            return 0.0, False, False

        raw_strength = signal.metadata["strength"]
        if isinstance(raw_strength, bool) or not isinstance(raw_strength, (int, float)):
            return 0.0, False, False

        numeric_strength = float(raw_strength)
        if numeric_strength != numeric_strength or numeric_strength in (
            float("inf"),
            float("-inf"),
        ):
            return 0.0, False, False

        clamped_strength = clip(numeric_strength)
        was_clamped = clamped_strength != numeric_strength
        return clamped_strength, True, was_clamped

    def _compute_exposure_ratio(self, portfolio: Portfolio) -> tuple[float, Decimal]:
        """
        Return `(exposure_ratio, equity_used)`.

        `exposure_ratio` is the fraction of portfolio equity already
        committed to open positions (current price, falling back to
        entry price, times quantity). If `portfolio.total_equity` is
        not already computed, equity is estimated as
        `cash_balance + position_value` -- a graceful fallback, never a
        raised error, matching the rest of this package's treatment of
        optional/uncomputed data.
        """
        position_value = Decimal("0")
        for position in portfolio.positions:
            price = position.current_price
            if price is None:
                price = position.entry_price
            try:
                position_value += abs(Decimal(price)) * abs(Decimal(position.quantity))
            except (InvalidOperation, TypeError):
                # Malformed individual position: skip it rather than
                # failing the whole evaluation.
                continue

        if portfolio.total_equity is not None:
            equity = portfolio.total_equity
        else:
            equity = portfolio.cash_balance + position_value

        if equity <= 0:
            exposure_ratio = 1.0 if position_value > 0 else 0.0
        else:
            exposure_ratio = float(position_value / equity)

        return max(0.0, exposure_ratio), equity

    # ------------------------------------------------------------------
    # Presentation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_summary(
        *,
        approved: bool,
        risk_score: float,
        hard_reject_reasons: list[str],
    ) -> str:
        decision = "Approved" if approved else "Rejected"
        summary = f"{decision}: risk_score={risk_score:.3f}"
        if hard_reject_reasons:
            summary += " (" + "; ".join(hard_reject_reasons) + ")"
        return summary
