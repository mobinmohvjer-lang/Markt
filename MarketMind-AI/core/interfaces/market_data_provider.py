"""
market_data_provider.py
--------------------------
Purpose:
    Defines the `MarketDataProvider` interface: the contract any market
    data source (Binance, another exchange, a CSV replay for testing,
    etc.) must implement to supply candles, tickers, order books, and
    recent trades to the rest of the application.

    No implementation, no API calls -- concrete providers will live in
    the future `data/` package (e.g. `data/providers/binance_provider.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from core.entities.candle import Candle
from core.entities.order_book import OrderBook
from core.entities.ticker import Ticker
from core.entities.trade import Trade


class MarketDataProvider(ABC):
    """Abstract contract for any source of market data."""

    @abstractmethod
    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int | None = None,
    ) -> list[Candle]:
        """
        Return historical candlesticks for a symbol/timeframe.

        Args:
            symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").
            timeframe: Candle interval identifier (e.g. "1h").
            start: Optional start of the requested time range.
            end: Optional end of the requested time range.
            limit: Optional maximum number of candles to return.

        Returns:
            A list of `Candle` entities.
        """
        raise NotImplementedError

    @abstractmethod
    def get_ticker(self, symbol: str) -> Ticker:
        """
        Return the current ticker snapshot for a symbol.

        Args:
            symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").

        Returns:
            A `Ticker` entity.
        """
        raise NotImplementedError

    @abstractmethod
    def get_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        """
        Return the current order book snapshot for a symbol.

        Args:
            symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").
            depth: Number of price levels to retrieve per side.

        Returns:
            An `OrderBook` entity.
        """
        raise NotImplementedError

    @abstractmethod
    def get_recent_trades(self, symbol: str, limit: int = 100) -> list[Trade]:
        """
        Return the most recent public trades for a symbol.

        Args:
            symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").
            limit: Maximum number of trades to return.

        Returns:
            A list of `Trade` entities.
        """
        raise NotImplementedError
