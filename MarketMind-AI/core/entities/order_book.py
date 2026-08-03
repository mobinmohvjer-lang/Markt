"""
order_book.py
---------------
Purpose:
    Defines the `OrderBook` domain entity and its supporting
    `OrderBookLevel` value object, representing the current bid/ask
    depth for a symbol.

    Pure data container -- no fetching, no aggregation, no calculations
    (e.g. no spread or imbalance computation here).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class OrderBookLevel:
    """
    A single price level within an order book side (bid or ask).

    Attributes:
        price: Price of this level.
        quantity: Total quantity available at this price level.
    """

    price: Decimal
    quantity: Decimal


@dataclass(frozen=True)
class OrderBook:
    """
    A snapshot of order book depth for a single symbol.

    Attributes:
        symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").
        timestamp: When this snapshot was captured/received.
        bids: Buy-side price levels, conventionally ordered from best
            (highest) to worst (lowest) price.
        asks: Sell-side price levels, conventionally ordered from best
            (lowest) to worst (highest) price.
    """

    symbol: str
    timestamp: datetime
    bids: list[OrderBookLevel] = field(default_factory=list)
    asks: list[OrderBookLevel] = field(default_factory=list)
