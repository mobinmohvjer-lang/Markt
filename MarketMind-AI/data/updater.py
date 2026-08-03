"""
IncrementalDataUpdater: continues downloading from the last stored candle,
so callers don't have to track cursors themselves.
"""

from typing import Optional

from .config import TIMEFRAME_MS, assert_valid_timeframe
from .downloader import HistoricalDataDownloader
from .storage import MarketDataStorage


class IncrementalDataUpdater:
    def __init__(self, downloader: HistoricalDataDownloader, storage: MarketDataStorage):
        self.downloader = downloader
        self.storage = storage

    def update_latest(
        self,
        symbol: str,
        timeframe: str,
        default_start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        batch_limit: int = 1000,
    ) -> int:
        """
        Fetch and store any candles newer than what's already in storage.

        If nothing is stored yet for this symbol/timeframe, `default_start_time`
        is used as the starting point (required in that case).

        Returns the number of NEW candles stored.
        """
        assert_valid_timeframe(timeframe)
        symbol = symbol.upper()

        last_candle = self.storage.load_last_candle(symbol, timeframe)

        if last_candle is not None:
            start_time = last_candle.open_time + TIMEFRAME_MS[timeframe]
        elif default_start_time is not None:
            start_time = int(default_start_time)
        else:
            raise ValueError(
                "No stored candles found and no default_start_time provided; "
                "cannot determine where to start updating from."
            )

        return self.downloader.download_history(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            batch_limit=batch_limit,
        )
