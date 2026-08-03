"""
Core data model for the Data Engine: the Candle.
"""

from dataclasses import dataclass, astuple
from typing import Optional


@dataclass(frozen=True)
class Candle:
    """
    A single OHLCV candlestick for a given symbol/timeframe.

    Timestamps are stored as integer milliseconds since epoch (Binance format).
    """

    symbol: str
    timeframe: str
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int
    quote_volume: float = 0.0
    trades: int = 0
    taker_buy_base: float = 0.0
    taker_buy_quote: float = 0.0

    def as_tuple(self):
        return astuple(self)

    @staticmethod
    def columns():
        return (
            "symbol",
            "timeframe",
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_buy_base",
            "taker_buy_quote",
        )

    @classmethod
    def from_row(cls, row) -> "Candle":
        """Build a Candle from a sqlite3.Row or plain tuple in `columns()` order."""
        return cls(
            symbol=row[0],
            timeframe=row[1],
            open_time=int(row[2]),
            open=float(row[3]),
            high=float(row[4]),
            low=float(row[5]),
            close=float(row[6]),
            volume=float(row[7]),
            close_time=int(row[8]),
            quote_volume=float(row[9]) if row[9] is not None else 0.0,
            trades=int(row[10]) if row[10] is not None else 0,
            taker_buy_base=float(row[11]) if row[11] is not None else 0.0,
            taker_buy_quote=float(row[12]) if row[12] is not None else 0.0,
        )

    @classmethod
    def from_raw_kline(cls, symbol: str, timeframe: str, raw) -> Optional["Candle"]:
        """
        Parse a raw Binance kline array:

        [
          open_time, open, high, low, close, volume, close_time,
          quote_asset_volume, number_of_trades,
          taker_buy_base_asset_volume, taker_buy_quote_asset_volume, ignore
        ]
        """
        if raw is None or len(raw) < 11:
            return None
        try:
            return cls(
                symbol=symbol,
                timeframe=timeframe,
                open_time=int(raw[0]),
                open=float(raw[1]),
                high=float(raw[2]),
                low=float(raw[3]),
                close=float(raw[4]),
                volume=float(raw[5]),
                close_time=int(raw[6]),
                quote_volume=float(raw[7]),
                trades=int(raw[8]),
                taker_buy_base=float(raw[9]),
                taker_buy_quote=float(raw[10]),
            )
        except (TypeError, ValueError):
            return None
