"""
backtesting/portfolio_simulator.py

Defines `PortfolioSimulator` (Backtesting Engine Part 3): a small,
standalone, deterministic helper that simulates a `core.entities.
portfolio.Portfolio`'s cash and position state as a historical replay
progresses -- opening and closing positions, tracking realized and
unrealized PnL, and keeping `total_equity` current.

This factors out the exact simulation mechanics `BasicBacktester`
(Backtesting Engine Part 2) already implements inline as private
static helpers, into its own reusable, independently-testable class,
so any current or future `BaseBacktester` can share identical
portfolio-simulation behavior instead of re-implementing it. This is a
purely additive change: `BasicBacktester` itself is left completely
untouched (see `PROJECT_RULES.md` Section 9 -- an additive milestone
must not modify prior modules' source), and `PortfolioSimulator` is not
wired into it.

Reuses only entities/exceptions/utils that already exist:
`core.entities.portfolio.Portfolio`, `core.entities.position.Position`,
`core.entities.trade.Trade`, `core.entities.candle.Candle`,
`core.enums.OrderSide`/`PositionSide`/`PositionStatus`, and
`backtesting.exceptions.BacktestValidationError`/
`backtesting.utils.validate_non_empty_str`. No new domain concepts, no
changes to `backtesting/exceptions.py` or `backtesting/utils.py`.

Deliberately simple and out of scope (mirroring `BasicBacktester`'s own
documented scope boundary, `PROJECT_RULES.md` Section 1 principle 5 --
"Backtesting is a consumer, never a strategy author"): no leverage, no
margin, no slippage, no commissions/fees, no partial fills, no
portfolio optimization, no performance metrics (Sharpe ratio, max
drawdown, profit factor, etc.), no reporting, no AI, and no broker
integration. Long-only, at most one open position per symbol at a time
(no pyramiding) -- the same execution model `BasicBacktester` already
uses, just factored out here.

Fully deterministic: no randomness, no wall-clock reads, no network/
database I/O. Never mutates the `Portfolio` passed to the constructor
(a defensive deep copy is taken immediately and is the only state ever
changed thereafter), and never mutates any market data passed into its
methods -- prices/timestamps are read-only primitives, and the
`Candle`-based convenience methods only ever read `candle.close`/
`candle.close_time`, never assign to a `Candle` (which is a frozen
dataclass in any case).
"""

from __future__ import annotations

import copy
from datetime import datetime
from decimal import Decimal
from typing import Optional

from core.entities.candle import Candle
from core.entities.portfolio import Portfolio
from core.entities.position import Position
from core.entities.trade import Trade
from core.enums import OrderSide, PositionSide, PositionStatus

from backtesting.exceptions import BacktestValidationError
from backtesting.utils import validate_non_empty_str


class PortfolioSimulator:
    """
    Simulates one `Portfolio`'s cash/position state during a
    deterministic historical replay.

    Long-only, at most one open position per symbol at a time (no
    pyramiding, no leverage/margin/slippage/commissions/partial
    fills) -- the exact execution model `BasicBacktester`
    (Backtesting Engine Part 2) already documents, factored out here
    so it can be reused without duplicating the mechanics.

    Attributes
    ----------
    portfolio : Portfolio
        The simulator's own working copy of portfolio state -- never
        the same object passed to the constructor.
    trades : list[Trade]
        All `Trade`\\ s recorded so far, in execution order.
    """

    def __init__(self, initial_portfolio: Portfolio) -> None:
        """
        Parameters
        ----------
        initial_portfolio : Portfolio
            The starting portfolio state. Deep-copied immediately --
            the caller's instance is never read again after
            construction and is never mutated by this simulator.

        Raises
        ------
        BacktestValidationError
            If `initial_portfolio` is not a `Portfolio` instance.
        """
        if not isinstance(initial_portfolio, Portfolio):
            raise BacktestValidationError(
                f"initial_portfolio must be a Portfolio, "
                f"got {type(initial_portfolio).__name__}"
            )
        self._portfolio: Portfolio = copy.deepcopy(initial_portfolio)
        self._trades: list[Trade] = []
        self._trade_sequence = 0

    @property
    def portfolio(self) -> Portfolio:
        """The simulator's current working copy of portfolio state."""
        return self._portfolio

    @property
    def cash_balance(self) -> Decimal:
        """The portfolio's current available cash balance."""
        return self._portfolio.cash_balance

    @property
    def trades(self) -> list[Trade]:
        """A copy of all `Trade`\\ s recorded so far, in execution order."""
        return list(self._trades)

    # ------------------------------------------------------------------
    # Position lookup
    # ------------------------------------------------------------------
    def get_open_position(self, symbol: str) -> Optional[Position]:
        """
        Return the open `Position` on `symbol`, or `None` if none is
        currently open.

        Raises
        ------
        BacktestValidationError
            If `symbol` is not a non-empty string.
        """
        validate_non_empty_str(symbol, name="symbol")
        for position in self._portfolio.positions:
            if position.symbol == symbol and position.status == PositionStatus.OPEN:
                return position
        return None

    def get_open_positions(self) -> list[Position]:
        """Return all currently open positions, across every symbol."""
        return [p for p in self._portfolio.positions if p.status == PositionStatus.OPEN]

    def has_open_position(self, symbol: str) -> bool:
        """Return whether a position is currently open on `symbol`."""
        return self.get_open_position(symbol) is not None

    # ------------------------------------------------------------------
    # Opening / closing positions
    # ------------------------------------------------------------------
    def open_position(
        self,
        *,
        symbol: str,
        price: Decimal,
        timestamp: datetime,
        side: PositionSide = PositionSide.LONG,
    ) -> Optional[Trade]:
        """
        Open one position on `symbol` at `price`, spending the entire
        current cash balance, and record the corresponding `Trade`.

        A no-op (returns `None`, no state changed) if a position is
        already open on `symbol`, or if `cash_balance` is not strictly
        positive -- matching `BasicBacktester`'s own no-pyramiding /
        no-margin rule.

        Parameters
        ----------
        symbol : str
            The symbol to open a position on.
        price : Decimal
            Execution price (e.g. a candle's `close`). Must be a
            strictly positive `Decimal`.
        timestamp : datetime
            Execution timestamp, used for both `Position.opened_at`
            and the recorded `Trade.executed_at`.
        side : PositionSide, default PositionSide.LONG
            Direction of the new position.

        Returns
        -------
        Trade or None
            The recorded trade, or `None` if this call was a no-op.

        Raises
        ------
        BacktestValidationError
            If `symbol` is not a non-empty string, `price` is not a
            strictly positive `Decimal`, or `timestamp` is not a
            `datetime`.
        """
        validate_non_empty_str(symbol, name="symbol")
        price = self._validate_price(price)
        self._validate_timestamp(timestamp)

        if self.get_open_position(symbol) is not None:
            return None
        if self._portfolio.cash_balance <= 0:
            return None

        quantity = self._portfolio.cash_balance / price
        self._trade_sequence += 1

        position = Position(
            position_id=f"{symbol}-{self._trade_sequence}",
            symbol=symbol,
            side=side,
            entry_price=price,
            quantity=quantity,
            opened_at=timestamp,
            status=PositionStatus.OPEN,
            current_price=price,
            unrealized_pnl=Decimal("0"),
        )
        self._portfolio.positions.append(position)
        self._portfolio.cash_balance = Decimal("0")
        self._refresh_total_equity()

        trade = Trade(
            trade_id=f"{symbol}-{self._trade_sequence}-buy",
            symbol=symbol,
            side=OrderSide.BUY,
            price=price,
            quantity=quantity,
            executed_at=timestamp,
        )
        self._trades.append(trade)
        return trade

    def close_position(
        self,
        *,
        symbol: str,
        price: Decimal,
        timestamp: datetime,
    ) -> Optional[Trade]:
        """
        Close the open position on `symbol` in full at `price`, credit
        the proceeds back to cash, calculate realized PnL, and record
        the corresponding `Trade`.

        A no-op (returns `None`, no state changed) if no position is
        currently open on `symbol`.

        Parameters
        ----------
        symbol : str
            The symbol whose open position should be closed.
        price : Decimal
            Execution price (e.g. a candle's `close`). Must be a
            strictly positive `Decimal`.
        timestamp : datetime
            Execution timestamp, used for both `Position.closed_at`
            and the recorded `Trade.executed_at`.

        Returns
        -------
        Trade or None
            The recorded trade, or `None` if this call was a no-op.

        Raises
        ------
        BacktestValidationError
            If `symbol` is not a non-empty string, `price` is not a
            strictly positive `Decimal`, or `timestamp` is not a
            `datetime`.
        """
        validate_non_empty_str(symbol, name="symbol")
        price = self._validate_price(price)
        self._validate_timestamp(timestamp)

        position = self.get_open_position(symbol)
        if position is None:
            return None

        quantity = position.quantity
        proceeds = quantity * price

        position.current_price = price
        position.realized_pnl = self._calculate_pnl(position, price)
        position.unrealized_pnl = Decimal("0")
        position.status = PositionStatus.CLOSED
        position.closed_at = timestamp

        self._portfolio.cash_balance += proceeds
        self._trade_sequence += 1
        self._refresh_total_equity()

        trade = Trade(
            trade_id=f"{symbol}-{self._trade_sequence}-sell",
            symbol=symbol,
            side=OrderSide.SELL,
            price=price,
            quantity=quantity,
            executed_at=timestamp,
        )
        self._trades.append(trade)
        return trade

    # ------------------------------------------------------------------
    # Marking to market / portfolio value
    # ------------------------------------------------------------------
    def update_market_price(self, *, symbol: str, price: Decimal) -> None:
        """
        Mark the open position on `symbol` (if any) to `price`:
        updates its `current_price`/`unrealized_pnl` and refreshes
        `portfolio.total_equity`.

        A no-op if no position is currently open on `symbol`.

        Raises
        ------
        BacktestValidationError
            If `symbol` is not a non-empty string, or `price` is not a
            strictly positive `Decimal`.
        """
        validate_non_empty_str(symbol, name="symbol")
        price = self._validate_price(price)

        position = self.get_open_position(symbol)
        if position is None:
            return None

        position.current_price = price
        position.unrealized_pnl = self._calculate_pnl(position, price)
        self._refresh_total_equity()
        return None

    def total_equity(self) -> Decimal:
        """
        Calculate the portfolio's total equity: cash balance plus the
        current mark-to-market value of every open position (using
        each position's `current_price` if set, otherwise its
        `entry_price`).

        This is a pure calculation -- it does not mutate
        `portfolio.total_equity` itself (see `update_market_price`,
        `open_position`, `close_position`, which each refresh it).
        """
        equity = self._portfolio.cash_balance
        for position in self._portfolio.positions:
            if position.status == PositionStatus.OPEN:
                mark_price = (
                    position.current_price
                    if position.current_price is not None
                    else position.entry_price
                )
                equity += position.quantity * mark_price
        return equity

    # ------------------------------------------------------------------
    # Candle-based convenience wrappers
    # ------------------------------------------------------------------
    def open_position_from_candle(
        self,
        *,
        symbol: str,
        candle: Candle,
        side: PositionSide = PositionSide.LONG,
    ) -> Optional[Trade]:
        """
        Convenience wrapper around `open_position` that reads
        execution price/timestamp from `candle.close`/
        `candle.close_time`. `candle` is only ever read, never
        mutated (it is a frozen `Candle` in any case).
        """
        self._validate_candle(candle)
        return self.open_position(
            symbol=symbol, price=candle.close, timestamp=candle.close_time, side=side
        )

    def close_position_from_candle(self, *, symbol: str, candle: Candle) -> Optional[Trade]:
        """
        Convenience wrapper around `close_position` that reads
        execution price/timestamp from `candle.close`/
        `candle.close_time`. `candle` is only ever read, never
        mutated.
        """
        self._validate_candle(candle)
        return self.close_position(symbol=symbol, price=candle.close, timestamp=candle.close_time)

    def update_market_price_from_candle(self, *, symbol: str, candle: Candle) -> None:
        """
        Convenience wrapper around `update_market_price` that reads
        the mark price from `candle.close`. `candle` is only ever
        read, never mutated.
        """
        self._validate_candle(candle)
        self.update_market_price(symbol=symbol, price=candle.close)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_price(price: Decimal) -> Decimal:
        if not isinstance(price, Decimal):
            raise BacktestValidationError(f"price must be a Decimal, got {type(price).__name__}")
        if price <= 0:
            raise BacktestValidationError(f"price must be strictly positive, got {price}")
        return price

    @staticmethod
    def _validate_timestamp(timestamp: datetime) -> datetime:
        if not isinstance(timestamp, datetime):
            raise BacktestValidationError(
                f"timestamp must be a datetime, got {type(timestamp).__name__}"
            )
        return timestamp

    @staticmethod
    def _validate_candle(candle: Candle) -> Candle:
        if not isinstance(candle, Candle):
            raise BacktestValidationError(f"candle must be a Candle, got {type(candle).__name__}")
        return candle

    @staticmethod
    def _calculate_pnl(position: Position, price: Decimal) -> Decimal:
        """
        Signed PnL for `position` marked at `price`, given its side.
        Used for both realized PnL (at close) and unrealized PnL
        (while open) -- the formula is identical; only which
        `Position` field the caller stores the result into differs.
        """
        if position.side == PositionSide.SHORT:
            return (position.entry_price - price) * position.quantity
        return (price - position.entry_price) * position.quantity

    def _refresh_total_equity(self) -> None:
        self._portfolio.total_equity = self.total_equity()
