"""
backtesting/basic_backtester.py

Defines `BasicBacktester`, the first concrete `BaseBacktester`
implementation (Backtesting Engine Part 2), built entirely on Part 1's
foundation (`BaseBacktester`, `BacktestContext`, `BacktestResult`, the
`BacktestError` hierarchy, `backtesting.utils`).

`BasicBacktester` replays `BacktestContext.candles` sequentially, oldest
to newest, against `BacktestContext.strategy` (any `BaseStrategy`
instance). For each candle it builds a minimal `strategies.context.
StrategyContext` for the context's symbol/timeframe -- carrying no
`AnalysisResult`/`SignalResult`/`RiskResult` of its own (`backtesting`
does not depend on `analysis`/produce signals -- see the dependency
table in `PROJECT_RULES.md` Section 4) and exposing the current candle
only via `StrategyContext.metadata` for traceability/strategy use --
and calls `context.strategy.decide(...)`. `BasicBacktester` consumes
only the resulting `strategies.result.StrategyResult.action`
(`core.enums.SignalDirection.BUY`/`SELL`/`HOLD`); it never inspects any
`AnalysisResult`/`SignalResult`/`RiskResult` directly and never decides
*why* to buy or sell -- that reasoning belongs entirely to the injected
strategy (`PROJECT_RULES.md` Section 1, principle 5: "Backtesting is a
consumer, never a strategy author").

Execution model (deliberately the simplest deterministic one that
satisfies "record trades" without inventing trading rules):

    - `BUY` while no open position is held on `context.symbol`: spend
      the entire current cash balance to open one long `Position` at
      the candle's `close` price, and record one `Trade`. A `BUY`
      while a position is already open, or with zero/negative cash
      available, is a no-op (no pyramiding, no margin/leverage).
    - `SELL` while an open position is held on `context.symbol`: close
      the entire position at the candle's `close` price, credit the
      proceeds back to cash, and record one `Trade`. A `SELL` with no
      open position is a no-op.
    - `HOLD` is always a no-op.

No slippage, no commissions/fees, and no leverage are modeled (trades
always fill exactly at the candle's `close` price, for the position's
full quantity, using only cash already on hand) -- those, along with
performance statistics (Sharpe ratio, max drawdown, win rate, profit
factor) and any cross-run aggregation, remain out of scope for this
part and belong to later Backtesting Engine parts (see
`backtesting/__init__.py`'s "Planned contents").

A strategy raising `strategies.exceptions.InsufficientStrategyDataError`
for a given candle is treated the same way every other engine in this
repository treats a per-item "unavailable" result: that candle is
skipped (no trade, `metadata["skipped_candles"]` records the count) and
replay continues with the next candle -- it never aborts the whole run.
Any other exception raised by the strategy propagates unchanged, since
that indicates a genuine bug in the injected strategy, not an ordinary
"insufficient data" outcome.

Fully deterministic -- no randomness, no wall-clock reads, no network/
database I/O, no AI. Never mutates `context` or anything reachable from
it: `context.initial_portfolio` is copied before any positions/cash are
touched, and `context.candles` (a `list` of frozen `Candle` instances)
is only ever read, never written to.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Optional

from core.entities.candle import Candle
from core.entities.portfolio import Portfolio
from core.entities.position import Position
from core.entities.trade import Trade
from core.enums import OrderSide, PositionSide, PositionStatus, SignalDirection

from strategies.context import StrategyContext
from strategies.exceptions import InsufficientStrategyDataError

from backtesting.base import BaseBacktester
from backtesting.context import BacktestContext
from backtesting.exceptions import InsufficientBacktestDataError
from backtesting.result import BacktestResult
from backtesting.utils import merge_metadata


class BasicBacktester(BaseBacktester):
    """
    The first concrete `BaseBacktester`: a straightforward, deterministic
    sequential replay of one strategy against one candle series.

    Consumes only `strategies.result.StrategyResult.action` from the
    injected `BacktestContext.strategy` -- no position sizing algorithm,
    no risk management, no portfolio optimization, no leverage, no
    slippage, no commissions, and no performance-metric calculation
    (Sharpe ratio, max drawdown, win rate, profit factor, etc.) are
    performed here; see the module docstring for the exact execution
    model and `backtesting/__init__.py`'s "Planned contents" for where
    those eventually belong.
    """

    def run(self, context: BacktestContext) -> BacktestResult:
        """
        Replay `context.candles` through `context.strategy`, sequentially
        and chronologically, and return the resulting `BacktestResult`.

        Parameters
        ----------
        context : BacktestContext
            The historical candles, strategy, and starting portfolio to
            replay. Never mutated by this call.

        Returns
        -------
        BacktestResult
            The final portfolio state, recorded trades, a human-readable
            summary, and traceability `metadata`.

        Raises
        ------
        InvalidBacktestContextError
            If `context` is not a `BacktestContext` instance (via
            `self.validate_context`).
        InsufficientBacktestDataError
            If `context` carries no candles to replay. In practice this
            cannot happen for an already-constructed `BacktestContext`
            (its own validation already rejects an empty candle list),
            but this check is kept as a defensive, self-contained
            guarantee of this method's own documented contract.
        """
        self.validate_context(context)

        if not context.candles:
            raise InsufficientBacktestDataError(
                f"{self.name} requires at least one candle to replay, got none"
            )

        # Never mutate the caller's starting portfolio -- work on a deep
        # copy for the whole run instead.
        portfolio = copy.deepcopy(context.initial_portfolio)
        trades: list[Trade] = []
        skipped_candles = 0
        trade_sequence = 0

        for index, candle in enumerate(context.candles):
            strategy_context = StrategyContext(
                symbol=context.symbol,
                timeframe=context.timeframe,
                metadata={"candle": candle, "candle_index": index},
            )

            try:
                decision = context.strategy.decide(strategy_context)
            except InsufficientStrategyDataError:
                skipped_candles += 1
                continue

            open_position = self._find_open_position(portfolio, context.symbol)

            if decision.action == SignalDirection.BUY and open_position is None:
                trade_sequence = self._open_position(
                    portfolio=portfolio,
                    symbol=context.symbol,
                    candle=candle,
                    trades=trades,
                    trade_sequence=trade_sequence,
                )
            elif decision.action == SignalDirection.SELL and open_position is not None:
                trade_sequence = self._close_position(
                    portfolio=portfolio,
                    position=open_position,
                    candle=candle,
                    trades=trades,
                    trade_sequence=trade_sequence,
                )
            # SignalDirection.HOLD, or a BUY/SELL that does not apply
            # given current position state, is always a no-op.

        portfolio.updated_at = context.candles[-1].close_time

        summary = self._build_summary(
            context=context,
            trades=trades,
            skipped_candles=skipped_candles,
            final_portfolio=portfolio,
        )
        metadata = merge_metadata(
            context.metadata,
            {
                "backtester": self.name,
                "strategy_name": context.strategy.name,
                "symbol": context.symbol,
                "timeframe": context.timeframe,
                "candles_replayed": len(context.candles),
                "skipped_candles": skipped_candles,
                "trades_executed": len(trades),
                "open_positions_remaining": sum(
                    1 for p in portfolio.positions if p.status == PositionStatus.OPEN
                ),
            },
        )

        return self._build_result(
            final_portfolio=portfolio,
            summary=summary,
            trades=trades,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _find_open_position(portfolio: Portfolio, symbol: str) -> Optional[Position]:
        """Return the first open `Position` on `symbol`, or `None`."""
        for position in portfolio.positions:
            if position.symbol == symbol and position.status == PositionStatus.OPEN:
                return position
        return None

    @staticmethod
    def _open_position(
        *,
        portfolio: Portfolio,
        symbol: str,
        candle: Candle,
        trades: list[Trade],
        trade_sequence: int,
    ) -> int:
        """
        Open one long `Position` on `symbol` using the entire current
        cash balance, at `candle.close`, and record the corresponding
        `Trade`. A no-op (returns `trade_sequence` unchanged) when there
        is no positive cash available to spend.

        Returns the updated `trade_sequence` counter.
        """
        if portfolio.cash_balance <= 0:
            return trade_sequence

        price = candle.close
        quantity = portfolio.cash_balance / price
        trade_sequence += 1

        position = Position(
            position_id=f"{symbol}-{trade_sequence}",
            symbol=symbol,
            side=PositionSide.LONG,
            entry_price=price,
            quantity=quantity,
            opened_at=candle.open_time,
            status=PositionStatus.OPEN,
            current_price=price,
        )
        portfolio.positions.append(position)
        portfolio.cash_balance = Decimal("0")

        trades.append(
            Trade(
                trade_id=f"{symbol}-{trade_sequence}-buy",
                symbol=symbol,
                side=OrderSide.BUY,
                price=price,
                quantity=quantity,
                executed_at=candle.close_time,
            )
        )
        return trade_sequence

    @staticmethod
    def _close_position(
        *,
        portfolio: Portfolio,
        position: Position,
        candle: Candle,
        trades: list[Trade],
        trade_sequence: int,
    ) -> int:
        """
        Close `position` in full at `candle.close`, credit the proceeds
        back to `portfolio.cash_balance`, and record the corresponding
        `Trade`.

        Returns the updated `trade_sequence` counter.
        """
        price = candle.close
        quantity = position.quantity
        proceeds = quantity * price

        position.current_price = price
        position.realized_pnl = (price - position.entry_price) * quantity
        position.status = PositionStatus.CLOSED
        position.closed_at = candle.close_time

        portfolio.cash_balance += proceeds
        trade_sequence += 1

        trades.append(
            Trade(
                trade_id=f"{position.symbol}-{trade_sequence}-sell",
                symbol=position.symbol,
                side=OrderSide.SELL,
                price=price,
                quantity=quantity,
                executed_at=candle.close_time,
            )
        )
        return trade_sequence

    @staticmethod
    def _build_summary(
        *,
        context: BacktestContext,
        trades: list[Trade],
        skipped_candles: int,
        final_portfolio: Portfolio,
    ) -> str:
        """Build a short, human-readable summary of the completed run."""
        open_count = sum(1 for p in final_portfolio.positions if p.status == PositionStatus.OPEN)
        parts = [
            f"Replayed {len(context.candles)} candle(s) for "
            f"{context.symbol}/{context.timeframe} using strategy "
            f"'{context.strategy.name}': executed {len(trades)} trade(s), "
            f"ending with {open_count} open position(s) and cash balance "
            f"{final_portfolio.cash_balance}.",
        ]
        if skipped_candles:
            parts.append(
                f"{skipped_candles} candle(s) were skipped because the "
                f"strategy raised InsufficientStrategyDataError."
            )
        return " ".join(parts)
