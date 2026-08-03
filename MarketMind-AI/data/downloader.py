"""
HistoricalDataDownloader: paginates through Binance Spot klines and stores
them, running every batch through clean -> validate -> normalize before
persisting.
"""

from typing import Optional

from .cache import CandleCache
from .cleaner import DataCleaner
from .client import BinanceClientInterface
from .config import TIMEFRAME_MS, assert_valid_timeframe
from .models import Candle
from .normalizer import DataNormalizer
from .storage import MarketDataStorage
from .validator import DataValidator


class HistoricalDataDownloader:
    def __init__(
        self,
        client: BinanceClientInterface,
        storage: MarketDataStorage,
        validator: Optional[DataValidator] = None,
        cleaner: Optional[DataCleaner] = None,
        normalizer: Optional[DataNormalizer] = None,
        cache: Optional[CandleCache] = None,
    ):
        self.client = client
        self.storage = storage
        self.validator = validator or DataValidator()
        self.cleaner = cleaner or DataCleaner(self.validator)
        self.normalizer = normalizer or DataNormalizer()
        self.cache = cache

    def download_history(
        self,
        symbol: str,
        timeframe: str,
        start_time: int,
        end_time: Optional[int] = None,
        batch_limit: int = 1000,
        max_batches: Optional[int] = None,
    ) -> int:
        """
        Download and store historical candles for [start_time, end_time].

        If `end_time` is None, downloads up through "now" as determined by
        stopping once a batch returns fewer than `batch_limit` candles
        (Binance's signal that we've caught up).

        Returns the total number of NEW candles stored (duplicates ignored).
        """
        assert_valid_timeframe(timeframe)
        symbol = symbol.upper()

        cursor = int(start_time)
        total_stored = 0
        batches = 0

        while True:
            if end_time is not None and cursor > end_time:
                break
            if max_batches is not None and batches >= max_batches:
                break

            raw_klines = self.client.get_klines(
                symbol=symbol,
                interval=timeframe,
                start_time=cursor,
                end_time=end_time,
                limit=batch_limit,
            )
            batches += 1

            if not raw_klines:
                break

            candles = [
                Candle.from_raw_kline(symbol, timeframe, raw) for raw in raw_klines
            ]
            candles = [c for c in candles if c is not None]
            if not candles:
                break

            candles = self.cleaner.clean(candles)
            candles = self.normalizer.normalize_batch(candles)

            if candles:
                stored = self.storage.insert_candles(candles)
                total_stored += stored
                if self.cache is not None:
                    for candle in candles:
                        self.cache.append_candle(symbol, timeframe, candle)

            last_open_time = candles[-1].open_time if candles else raw_klines[-1][0]
            next_cursor = int(last_open_time) + TIMEFRAME_MS[timeframe]

            if next_cursor <= cursor:
                # Safety net against infinite loops if the API returns stale data.
                break
            cursor = next_cursor

            if len(raw_klines) < batch_limit:
                # Fewer than requested => we've reached the end of available data.
                break

        return total_stored
