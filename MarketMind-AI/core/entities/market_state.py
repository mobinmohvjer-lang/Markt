"""
market_state.py
------------------
Purpose:
    Defines the `MarketState` domain entity: an aggregated, point-in-time
    snapshot of everything known about a symbol, combining the latest
    candle, ticker, order book, recent trades, computed indicators, and
    relevant news.

    `MarketState` is the primary input type that future `Strategy`,
    `SignalGenerator`, and `AIAnalyzer` implementations will consume --
    it lets those components depend on a single, stable shape instead of
    juggling multiple raw inputs.

    Pure data container -- no fetching, no aggregation logic. Assembling
    a `MarketState` from live data sources is the responsibility of
    future `app/` use cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from core.entities.candle import Candle
from core.entities.indicator_result import IndicatorResult
from core.entities.news_item import NewsItem
from core.entities.order_book import OrderBook
from core.entities.ticker import Ticker
from core.entities.trade import Trade


@dataclass(frozen=True)
class MarketState:
    """
    An aggregated, point-in-time snapshot of the market for one symbol.

    Attributes:
        symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").
        timeframe: The primary candle interval this snapshot is framed
            around (e.g. "1h").
        timestamp: When this aggregated snapshot was assembled.
        latest_candle: Most recent completed candle for the symbol, if
            available.
        ticker: Most recent ticker snapshot, if available.
        order_book: Most recent order book snapshot, if available.
        recent_trades: Recent public trades on the symbol, if available.
        indicators: Technical indicator results computed for the symbol,
            if available.
        news: News items considered relevant to the symbol, if available.
    """

    symbol: str
    timeframe: str
    timestamp: datetime
    latest_candle: Candle | None = None
    ticker: Ticker | None = None
    order_book: OrderBook | None = None
    recent_trades: list[Trade] = field(default_factory=list)
    indicators: list[IndicatorResult] = field(default_factory=list)
    news: list[NewsItem] = field(default_factory=list)
