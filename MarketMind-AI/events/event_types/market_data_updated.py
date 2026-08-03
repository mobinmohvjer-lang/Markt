"""
market_data_updated.py
-------------------------
Purpose:
    Defines `MarketDataUpdated`: published whenever fresh, non-candle
    market data arrives for a symbol (e.g. an updated ticker or order
    book). Distinct from `CandleClosed`, which specifically marks the
    completion of a candlestick interval.

    Pure data container -- no fetching, no publishing logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.entities.order_book import OrderBook
from core.entities.ticker import Ticker
from events.interfaces.event import Event


@dataclass(frozen=True)
class MarketDataUpdated(Event):
    """
    Published when a symbol's ticker and/or order book snapshot changes.

    Attributes:
        symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").
        ticker: Updated ticker snapshot, if this update includes one.
        order_book: Updated order book snapshot, if this update includes
            one.
    """

    symbol: str
    ticker: Ticker | None = None
    order_book: OrderBook | None = None

    @property
    def event_type(self) -> str:
        return "MarketDataUpdated"
