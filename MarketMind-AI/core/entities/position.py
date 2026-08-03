"""
position.py
-------------
Purpose:
    Defines the `Position` domain entity: a trading position held (or
    previously held) on a given symbol.

    Unlike the immutable snapshot entities (`Candle`, `Ticker`, ...), a
    `Position` represents evolving state -- its current price, P&L, and
    status change over its lifetime -- so this dataclass is mutable
    (not frozen). No calculations are performed here: updating fields
    like `current_price` or `unrealized_pnl` is the responsibility of
    future service/strategy code, not this entity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from core.enums import PositionSide, PositionStatus


@dataclass
class Position:
    """
    A trading position (open or closed) on a single symbol.

    Attributes:
        position_id: Unique identifier for this position.
        symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").
        side: Direction of the position (long or short).
        entry_price: Average price at which the position was entered.
        quantity: Size of the position (base asset).
        opened_at: Timestamp when the position was opened.
        status: Current lifecycle status (open or closed).
        current_price: Latest known market price, used for computing
            unrealized P&L elsewhere (not computed here).
        stop_loss: Configured stop-loss price, if any.
        take_profit: Configured take-profit price, if any.
        realized_pnl: Realized profit/loss once (partially) closed.
        unrealized_pnl: Unrealized profit/loss while still open.
        closed_at: Timestamp when the position was fully closed, if
            applicable.
    """

    position_id: str
    symbol: str
    side: PositionSide
    entry_price: Decimal
    quantity: Decimal
    opened_at: datetime
    status: PositionStatus = PositionStatus.OPEN
    current_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    closed_at: datetime | None = None
