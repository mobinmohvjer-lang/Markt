"""
strategies/risk_management/context.py

Defines `RiskContext`: the immutable bundle of data every
`BaseRiskManager` needs in order to produce a `RiskResult` for one
candidate signal against one portfolio.

`RiskContext` only composes entities that already exist in `core/`
(`Signal`, `Portfolio`, `MarketState`) -- it introduces no new domain
concepts, keeping the Dependency Rule intact
(`strategies` -> `core`, `analysis`, `signals`, `events`, never the
reverse).

Pure data container -- no risk calculation, no position sizing, no
stop-loss/take-profit logic. Assembling a `RiskContext` from live data
is the responsibility of a future `app/` use case, mirroring the same
gap `AnalysisContext`/`SignalContext` already document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from core.entities.market_state import MarketState
from core.entities.portfolio import Portfolio
from core.entities.signal import Signal

from strategies.risk_management.exceptions import (
    InvalidRiskContextError,
    RiskValidationError,
)
from strategies.risk_management.utils import validate_non_empty_str


@dataclass(frozen=True)
class RiskContext:
    """
    Everything a `BaseRiskManager` needs to evaluate one candidate
    signal against one portfolio.

    Attributes:
        symbol: Trading pair/instrument identifier the signal applies
            to (e.g. "BTCUSDT").
        timeframe: Candle interval the signal was derived from
            (e.g. "1h").
        signal: The candidate `Signal` being evaluated for risk.
        portfolio: The current portfolio state to evaluate the signal
            against.
        market_state: Optional aggregated, point-in-time market
            snapshot (latest candle, ticker, order book, ...), for risk
            managers that need current-market context. Its absence only
            limits what can be evaluated -- it never invalidates the
            context.
        metadata: Free-form additional context supplied by the caller
            (e.g. an upstream `SignalResult`/`AnalysisResult`'s
            metadata), kept for traceability. Not interpreted here.
    """

    symbol: str
    timeframe: str
    signal: Signal
    portfolio: Portfolio
    market_state: Optional[MarketState] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "symbol", validate_non_empty_str(self.symbol, name="symbol"))
            object.__setattr__(
                self, "timeframe", validate_non_empty_str(self.timeframe, name="timeframe")
            )
        except RiskValidationError as exc:
            raise InvalidRiskContextError(str(exc)) from exc

        if not isinstance(self.signal, Signal):
            raise InvalidRiskContextError(
                f"signal must be a Signal, got {type(self.signal).__name__}"
            )
        if not isinstance(self.portfolio, Portfolio):
            raise InvalidRiskContextError(
                f"portfolio must be a Portfolio, got {type(self.portfolio).__name__}"
            )
        if self.market_state is not None and not isinstance(self.market_state, MarketState):
            raise InvalidRiskContextError(
                f"market_state must be a MarketState or None, "
                f"got {type(self.market_state).__name__}"
            )
        if not isinstance(self.metadata, dict):
            raise InvalidRiskContextError(
                f"metadata must be a dict, got {type(self.metadata).__name__}"
            )

    def has_market_state(self) -> bool:
        """Whether this context carries a `MarketState` snapshot."""
        return self.market_state is not None
