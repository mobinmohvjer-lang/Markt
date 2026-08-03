"""
strategies/portfolio_management/basic_portfolio_manager.py

Defines `BasicPortfolioManager`: the first concrete `BasePortfolioManager`
implementation (Portfolio Management Part 2), built on Part 1's
foundation (`BasePortfolioManager`, `PortfolioContext`, `PortfolioResult`).

`BasicPortfolioManager` evaluates a candidate `PortfolioContext` along
four independent, deliberately simple facets, mirroring the pattern
`strategies.risk_management.basic_risk_manager.BasicRiskManager`
established one layer down:

    - Open position count -- how many currently `PositionStatus.OPEN`
      positions `PortfolioContext.portfolio` already holds, against a
      configurable `max_open_positions` ceiling.
    - Aggregate exposure  -- the fraction of portfolio equity already
      committed to open positions (current price, falling back to
      entry price, times quantity, summed across all open positions),
      against a configurable `max_exposure_ratio` ceiling.
    - Symbol concentration -- the same fraction, narrowed to open
      positions on `PortfolioContext.symbol` only, against a
      configurable `max_symbol_exposure_ratio` ceiling. This is
      deliberately independent of the aggregate check above: a
      portfolio can be under its aggregate exposure limit while still
      being overly concentrated in one symbol.
    - Upstream signal availability -- whether the candidate
      `strategies.result.StrategyResult` (when present) recommends a
      directional action at all (`SignalDirection.BUY`/`SELL`, not
      `HOLD`), and whether the candidate `strategies.risk_management.
      result.RiskResult` (when present) approved the trade.

Each facet is a deterministic threshold/gate check -- there is no
scoring, weighting, or optimization anywhere in this module. All four
gates must pass for `new_positions_allowed` to be `True`; any one
failing is enough to block, and every reason is recorded in
`PortfolioResult.metadata["hard_reject_reasons"]` alongside every
intermediate value that produced the decision, so it can always be
traced back to its inputs.

`confidence` is derived only from how much of the optional context was
actually available (`strategy_result`/`risk_result` presence) and, when
present, their own `confidence` values -- never from the pass/fail
decision itself.

Deliberately out of scope, matching every other Portfolio Management
Part 1/2 boundary already documented in this package:
    - No allocation or position-sizing algorithm.
    - No rebalancing of existing positions.
    - No broker/order-execution integration.
    - No AI-based assessment.

`BasicPortfolioManager` consumes `PortfolioContext`/`PortfolioResult`
and the existing `core.entities.portfolio.Portfolio`/`core.entities.
position.Position`, `strategies.result.StrategyResult`, and
`strategies.risk_management.result.RiskResult` exactly as they already
exist -- no new domain concepts, and nothing in Analysis/Signal/Risk/
Strategy Engines or the Portfolio Management Part 1 foundation is
modified.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from core.entities.portfolio import Portfolio
from core.entities.position import Position
from core.enums import PositionStatus, SignalDirection

from strategies.result import StrategyResult
from strategies.risk_management.result import RiskResult

from strategies.portfolio_management.base import BasePortfolioManager
from strategies.portfolio_management.context import PortfolioContext
from strategies.portfolio_management.exceptions import (
    InsufficientPortfolioDataError,
    PortfolioManagerConfigurationError,
)
from strategies.portfolio_management.result import PortfolioResult
from strategies.portfolio_management.utils import clip

# Default constructor configuration -- see `BasicPortfolioManager.__init__`
# for what each controls.
DEFAULT_MAX_OPEN_POSITIONS = 10
DEFAULT_MAX_EXPOSURE_RATIO = 0.8
DEFAULT_MAX_SYMBOL_EXPOSURE_RATIO = 0.25
DEFAULT_REQUIRE_RISK_APPROVAL = True
DEFAULT_BLOCK_ON_HOLD_ACTION = True


class BasicPortfolioManager(BasePortfolioManager):
    """
    A simple, fully-explainable `BasePortfolioManager` implementation.

    Gates a candidate new position on open-position count, aggregate
    portfolio exposure, single-symbol concentration, and (when
    available) the candidate's own `StrategyResult`/`RiskResult`,
    with every intermediate value preserved in
    `PortfolioResult.metadata` for traceability. Every check is a
    deterministic threshold comparison -- no scoring, optimization,
    allocation, or rebalancing is performed anywhere here.

    Attributes:
        max_open_positions: Maximum number of `PositionStatus.OPEN`
            positions the portfolio may hold at or above which a new
            position is blocked.
        max_exposure_ratio: Maximum fraction (0.0..1.0+) of portfolio
            equity that may already be committed to open positions,
            above which a new position is blocked.
        max_symbol_exposure_ratio: Maximum fraction (0.0..1.0+) of
            portfolio equity that may already be committed to open
            positions on the candidate's own symbol, above which a
            new position is blocked. Independent of
            `max_exposure_ratio`.
        require_risk_approval: When `True` (default) and a
            `RiskResult` is present on the context, a new position is
            blocked unless `RiskResult.approved` is `True`. A missing
            `RiskResult` never blocks by itself -- it only lowers
            `confidence`.
        block_on_hold_action: When `True` (default) and a
            `StrategyResult` is present on the context, a new position
            is blocked when its `action` is `SignalDirection.HOLD`
            (there is no directional trade to allow). A missing
            `StrategyResult` never blocks by itself -- it only lowers
            `confidence`.
    """

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        max_open_positions: int = DEFAULT_MAX_OPEN_POSITIONS,
        max_exposure_ratio: float = DEFAULT_MAX_EXPOSURE_RATIO,
        max_symbol_exposure_ratio: float = DEFAULT_MAX_SYMBOL_EXPOSURE_RATIO,
        require_risk_approval: bool = DEFAULT_REQUIRE_RISK_APPROVAL,
        block_on_hold_action: bool = DEFAULT_BLOCK_ON_HOLD_ACTION,
    ) -> None:
        super().__init__(name=name)

        self.max_open_positions = self._validate_positive_int(
            max_open_positions, name="max_open_positions"
        )
        self.max_exposure_ratio = self._validate_positive_float(
            max_exposure_ratio, name="max_exposure_ratio"
        )
        self.max_symbol_exposure_ratio = self._validate_positive_float(
            max_symbol_exposure_ratio, name="max_symbol_exposure_ratio"
        )

        if not isinstance(require_risk_approval, bool):
            raise PortfolioManagerConfigurationError(
                f"require_risk_approval must be a bool, got {type(require_risk_approval).__name__}"
            )
        self.require_risk_approval = require_risk_approval

        if not isinstance(block_on_hold_action, bool):
            raise PortfolioManagerConfigurationError(
                f"block_on_hold_action must be a bool, got {type(block_on_hold_action).__name__}"
            )
        self.block_on_hold_action = block_on_hold_action

    # ------------------------------------------------------------------
    # Construction-time validation
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_positive_int(value: Any, *, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise PortfolioManagerConfigurationError(
                f"{name} must be an int, got {type(value).__name__}"
            )
        if value <= 0:
            raise PortfolioManagerConfigurationError(f"{name} must be > 0, got {value}")
        return value

    @staticmethod
    def _validate_positive_float(value: Any, *, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise PortfolioManagerConfigurationError(
                f"{name} must be numeric, got {type(value).__name__}"
            )
        numeric_value = float(value)
        if numeric_value != numeric_value or numeric_value in (float("inf"), float("-inf")):
            raise PortfolioManagerConfigurationError(f"{name} must be finite, got {numeric_value}")
        if numeric_value <= 0.0:
            raise PortfolioManagerConfigurationError(f"{name} must be > 0.0, got {numeric_value}")
        return numeric_value

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def evaluate(self, context: PortfolioContext) -> PortfolioResult:
        """
        Evaluate `context` and return a single `PortfolioResult`.

        Never raises `InsufficientPortfolioDataError` for an ordinarily
        thin `PortfolioContext` (a missing `strategy_result` or
        `risk_result` only lowers this result's `confidence`); it is
        only raised when portfolio equity cannot be computed at all
        (i.e. `portfolio.total_equity` is absent and
        `portfolio.cash_balance` cannot be combined with the computed
        open-position value), since no meaningful evaluation can be
        produced from that.
        """
        context = self.validate_context(context)
        portfolio = context.portfolio

        open_positions = self._open_positions(portfolio)
        open_position_count = len(open_positions)

        exposure_ratio, equity_used, position_value = self._compute_exposure(
            open_positions, portfolio
        )
        symbol_exposure_ratio, symbol_position_value = self._compute_symbol_exposure(
            open_positions, context.symbol, equity_used
        )

        strategy_result = context.strategy_result
        risk_result = context.risk_result
        strategy_available = strategy_result is not None
        risk_available = risk_result is not None

        hard_reject_reasons: list[str] = []

        if open_position_count >= self.max_open_positions:
            hard_reject_reasons.append(
                f"open_position_count {open_position_count} at or above maximum "
                f"{self.max_open_positions}"
            )

        if exposure_ratio > self.max_exposure_ratio:
            hard_reject_reasons.append(
                f"exposure_ratio {exposure_ratio:.3f} exceeds maximum "
                f"{self.max_exposure_ratio:.3f}"
            )

        if symbol_exposure_ratio > self.max_symbol_exposure_ratio:
            hard_reject_reasons.append(
                f"symbol_exposure_ratio {symbol_exposure_ratio:.3f} for {context.symbol!r} "
                f"exceeds maximum {self.max_symbol_exposure_ratio:.3f}"
            )

        if (
            self.block_on_hold_action
            and strategy_available
            and strategy_result.action == SignalDirection.HOLD
        ):
            hard_reject_reasons.append(
                "strategy_result.action is HOLD -- no directional trade to allow"
            )

        if self.require_risk_approval and risk_available and not risk_result.approved:
            hard_reject_reasons.append("risk_result.approved is False")

        new_positions_allowed = not hard_reject_reasons

        confidence = self._compute_confidence(strategy_result, risk_result)

        summary = self._build_summary(
            new_positions_allowed=new_positions_allowed,
            hard_reject_reasons=hard_reject_reasons,
        )

        metadata: dict[str, Any] = {
            "portfolio_manager": self.name,
            "symbol": context.symbol,
            "timeframe": context.timeframe,
            "open_position_count": open_position_count,
            "exposure_ratio": exposure_ratio,
            "symbol_exposure_ratio": symbol_exposure_ratio,
            "equity_used": str(equity_used),
            "position_value": str(position_value),
            "symbol_position_value": str(symbol_position_value),
            "strategy_result_available": strategy_available,
            "strategy_action": strategy_result.action.value if strategy_available else None,
            "strategy_confidence": strategy_result.confidence if strategy_available else None,
            "risk_result_available": risk_available,
            "risk_approved": risk_result.approved if risk_available else None,
            "risk_confidence": risk_result.confidence if risk_available else None,
            "limits": {
                "max_open_positions": self.max_open_positions,
                "max_exposure_ratio": self.max_exposure_ratio,
                "max_symbol_exposure_ratio": self.max_symbol_exposure_ratio,
            },
            "options": {
                "require_risk_approval": self.require_risk_approval,
                "block_on_hold_action": self.block_on_hold_action,
            },
            "hard_reject_reasons": hard_reject_reasons,
        }

        return self._build_result(
            new_positions_allowed=new_positions_allowed,
            confidence=confidence,
            summary=summary,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Portfolio-state helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _open_positions(portfolio: Portfolio) -> list[Position]:
        """
        Return only `portfolio.positions` currently `PositionStatus.OPEN`.

        `Portfolio.positions` may hold open and/or closed positions
        depending on how it was populated (see `core.entities.
        portfolio.Portfolio`) -- open-position count and exposure are
        only meaningful over the open subset.
        """
        return [position for position in portfolio.positions if position.status == PositionStatus.OPEN]

    def _position_value(self, position: Position) -> Optional[Decimal]:
        """
        Return this position's current notional value, or `None` if it
        cannot be computed from malformed price/quantity data (skipped
        by callers rather than failing the whole evaluation).
        """
        price = position.current_price if position.current_price is not None else position.entry_price
        try:
            return abs(Decimal(price)) * abs(Decimal(position.quantity))
        except (InvalidOperation, TypeError):
            return None

    def _compute_exposure(
        self, open_positions: list[Position], portfolio: Portfolio
    ) -> tuple[float, Decimal, Decimal]:
        """
        Return `(exposure_ratio, equity_used, position_value)`.

        `exposure_ratio` is the fraction of portfolio equity already
        committed to open positions. If `portfolio.total_equity` is
        not already computed, equity is estimated as
        `cash_balance + position_value` -- a graceful fallback, the
        same convention `strategies.risk_management.
        basic_risk_manager.BasicRiskManager` already uses.

        Raises:
            InsufficientPortfolioDataError: If equity cannot be
                computed at all, i.e. `portfolio.total_equity` is
                absent and `portfolio.cash_balance` cannot be combined
                with the computed `position_value`.
        """
        position_value = Decimal("0")
        for position in open_positions:
            value = self._position_value(position)
            if value is not None:
                position_value += value

        if portfolio.total_equity is not None:
            equity = portfolio.total_equity
        else:
            try:
                equity = portfolio.cash_balance + position_value
            except TypeError as exc:
                raise InsufficientPortfolioDataError(
                    "cannot compute portfolio equity: total_equity is absent and "
                    f"cash_balance is not compatible with the computed position_value ({exc})"
                ) from exc

        if equity <= 0:
            exposure_ratio = 1.0 if position_value > 0 else 0.0
        else:
            exposure_ratio = float(position_value / equity)

        return max(0.0, exposure_ratio), equity, position_value

    def _compute_symbol_exposure(
        self, open_positions: list[Position], symbol: str, equity: Decimal
    ) -> tuple[float, Decimal]:
        """
        Return `(symbol_exposure_ratio, symbol_position_value)` for
        open positions on `symbol` only, against the same `equity`
        already resolved by `_compute_exposure`.
        """
        symbol_value = Decimal("0")
        for position in open_positions:
            if position.symbol != symbol:
                continue
            value = self._position_value(position)
            if value is not None:
                symbol_value += value

        if equity <= 0:
            symbol_exposure_ratio = 1.0 if symbol_value > 0 else 0.0
        else:
            symbol_exposure_ratio = float(symbol_value / equity)

        return max(0.0, symbol_exposure_ratio), symbol_value

    # ------------------------------------------------------------------
    # Confidence / presentation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_confidence(
        strategy_result: Optional[StrategyResult], risk_result: Optional[RiskResult]
    ) -> float:
        """
        Derive `confidence` purely from how much optional context was
        available and, when present, its own reported confidence --
        never from the pass/fail decision itself.

        Mirrors the completeness-weighted approach `BasicRiskManager`
        already uses for its own `confidence`: each optional input
        contributes `1.0` completeness when available, `0.5` when
        absent, averaged into an overall completeness multiplier
        applied to the mean of whichever confidences were available
        (a neutral `0.5` when neither is available).
        """
        strategy_available = strategy_result is not None
        risk_available = risk_result is not None

        completeness = clip(
            (1.0 if strategy_available else 0.5) * 0.5 + (1.0 if risk_available else 0.5) * 0.5
        )

        available_confidences = [
            result.confidence
            for result in (strategy_result, risk_result)
            if result is not None
        ]
        base_confidence = (
            sum(available_confidences) / len(available_confidences)
            if available_confidences
            else 0.5
        )

        return clip(base_confidence * completeness)

    @staticmethod
    def _build_summary(*, new_positions_allowed: bool, hard_reject_reasons: list[str]) -> str:
        decision = "Allowed" if new_positions_allowed else "Blocked"
        summary = f"{decision}: new position evaluation"
        if hard_reject_reasons:
            summary += " (" + "; ".join(hard_reject_reasons) + ")"
        return summary
