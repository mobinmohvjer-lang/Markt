"""
ticker.py
----------
Purpose:
    Defines the `Ticker` domain entity: a real-time snapshot of a
    symbol's current price and best bid/ask, plus basic 24h statistics.

    Pure data container -- no fetching, no calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Ticker:
    """
    A point-in-time price snapshot for a single symbol.

    Attributes:
        symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").
        last_price: Most recent traded price.
        bid_price: Current best bid price, if available.
        ask_price: Current best ask price, if available.
        bid_quantity: Quantity available at the best bid, if available.
        ask_quantity: Quantity available at the best ask, if available.
        high_24h: Highest price over the trailing 24 hours, if available.
        low_24h: Lowest price over the trailing 24 hours, if available.
        volume_24h: Base-asset volume traded over the trailing 24 hours,
            if available.
        price_change_24h: Absolute price change over the trailing 24
            hours, if available.
        price_change_percent_24h: Percentage price change over the
            trailing 24 hours, if available.
        timestamp: When this snapshot was captured/received.
    """

    symbol: str
    last_price: Decimal
    timestamp: datetime
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    bid_quantity: Decimal | None = None
    ask_quantity: Decimal | None = None
    high_24h: Decimal | None = None
    low_24h: Decimal | None = None
    volume_24h: Decimal | None = None
    price_change_24h: Decimal | None = None
    price_change_percent_24h: Decimal | None = None
