"""
candle.py
----------
Purpose:
    Defines the `Candle` domain entity: a single OHLCV (Open, High, Low,
    Close, Volume) candlestick for a given symbol and timeframe.

    This is a pure data container -- no parsing, no fetching, no
    calculations. Providers in `data/` are responsible for constructing
    `Candle` instances from raw exchange responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class Candle:
    """
    A single OHLCV candlestick.

    Attributes:
        symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").
        timeframe: Candle interval identifier (e.g. "1m", "1h", "1d").
            See `config.config.TimeFrame` for the canonical set of
            values currently supported by the application.
        open_time: Timestamp marking the start of the candle period.
        close_time: Timestamp marking the end of the candle period.
        open: Opening price of the period.
        high: Highest price reached during the period.
        low: Lowest price reached during the period.
        close: Closing price of the period.
        volume: Base-asset volume traded during the period.
        quote_volume: Quote-asset volume traded during the period, if
            provided by the data source.
        number_of_trades: Number of individual trades that occurred
            during the period, if provided by the data source.
    """

    symbol: str
    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal | None = None
    number_of_trades: int | None = None
