"""
backtesting/context.py

Defines `BacktestContext`: the immutable bundle of data every
`BaseBacktester` needs in order to produce a `BacktestResult` for one
symbol/timeframe run.

`BacktestContext` only composes entities/abstractions that already
exist (`core.entities.candle.Candle`, `core.entities.portfolio.
Portfolio`, `strategies.base_strategy.BaseStrategy`) -- it introduces no
new domain concepts, keeping the Dependency Rule intact
(`backtesting` -> `core`, `data`, `strategies`, `signals`, never the
reverse).

Pure data container -- no trade simulation, no PnL calculation, no
performance-statistics logic. Assembling a `BacktestContext` from real
historical data (via `data/`) is the responsibility of a future `app/`
use case, mirroring the same gap `AnalysisContext`/`RiskContext`/
`StrategyContext` already document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.entities.candle import Candle
from core.entities.portfolio import Portfolio

from strategies.base_strategy import BaseStrategy

from backtesting.exceptions import BacktestValidationError, InvalidBacktestContextError
from backtesting.utils import validate_chronological_candles, validate_non_empty_str


@dataclass(frozen=True)
class BacktestContext:
    """
    Everything a `BaseBacktester` needs to run one backtest.

    Attributes:
        symbol: Trading pair/instrument identifier the backtest applies
            to (e.g. "BTCUSDT").
        timeframe: Candle interval the historical data was sampled at
            (e.g. "1h").
        candles: Historical `Candle` data to replay, ordered
            chronologically from oldest to newest. Sourcing, cleaning,
            and normalizing this data is entirely the responsibility of
            `data/` -- this context only carries the already-prepared
            sequence.
        strategy: The `BaseStrategy` instance whose decisions are being
            replayed. `backtesting` is a consumer of whatever
            strategy/signals it is given -- it must never define
            trading rules itself.
        initial_portfolio: The starting `Portfolio` state (cash and
            positions) the backtest begins from.
        metadata: Free-form additional context supplied by the caller
            (e.g. run identifiers, data-source provenance), kept for
            traceability. Not interpreted here.
    """

    symbol: str
    timeframe: str
    candles: list[Candle]
    strategy: BaseStrategy
    initial_portfolio: Portfolio
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "symbol", validate_non_empty_str(self.symbol, name="symbol"))
            object.__setattr__(
                self, "timeframe", validate_non_empty_str(self.timeframe, name="timeframe")
            )
            object.__setattr__(
                self, "candles", validate_chronological_candles(self.candles, name="candles")
            )
        except BacktestValidationError as exc:
            raise InvalidBacktestContextError(str(exc)) from exc

        if not isinstance(self.strategy, BaseStrategy):
            raise InvalidBacktestContextError(
                f"strategy must be a BaseStrategy, got {type(self.strategy).__name__}"
            )
        if not isinstance(self.initial_portfolio, Portfolio):
            raise InvalidBacktestContextError(
                f"initial_portfolio must be a Portfolio, "
                f"got {type(self.initial_portfolio).__name__}"
            )
        if not isinstance(self.metadata, dict):
            raise InvalidBacktestContextError(
                f"metadata must be a dict, got {type(self.metadata).__name__}"
            )

    def candle_count(self) -> int:
        """Number of historical candles this context carries."""
        return len(self.candles)
