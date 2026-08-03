"""
DataEngine: a thin facade over the Data Engine components, exposing the
main entry points a caller needs:

    - download_history()
    - update_latest()
    - load_history()
    - load_last_candle()
    - clear_cache()

This class wires together MarketDataStorage, CandleCache,
HistoricalDataDownloader and IncrementalDataUpdater. It does not add any
new business logic of its own.
"""

from typing import List, Optional

from .cache import CandleCache
from .client import BinanceClientInterface
from .cleaner import DataCleaner
from .downloader import HistoricalDataDownloader
from .models import Candle
from .normalizer import DataNormalizer
from .storage import MarketDataStorage
from .updater import IncrementalDataUpdater
from .validator import DataValidator


class DataEngine:
    def __init__(
        self,
        client: BinanceClientInterface,
        db_path: str = "market_data.sqlite3",
        cache_max_keys: int = 256,
        cache_max_candles_per_key: int = 5000,
    ):
        self.client = client
        self.storage = MarketDataStorage(db_path=db_path)
        self.cache = CandleCache(
            max_keys=cache_max_keys, max_candles_per_key=cache_max_candles_per_key
        )
        self.validator = DataValidator()
        self.cleaner = DataCleaner(self.validator)
        self.normalizer = DataNormalizer()

        self.downloader = HistoricalDataDownloader(
            client=self.client,
            storage=self.storage,
            validator=self.validator,
            cleaner=self.cleaner,
            normalizer=self.normalizer,
            cache=self.cache,
        )
        self.updater = IncrementalDataUpdater(
            downloader=self.downloader, storage=self.storage
        )

    def download_history(
        self,
        symbol: str,
        timeframe: str,
        start_time: int,
        end_time: Optional[int] = None,
        batch_limit: int = 1000,
    ) -> int:
        return self.downloader.download_history(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            batch_limit=batch_limit,
        )

    def update_latest(
        self,
        symbol: str,
        timeframe: str,
        default_start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        batch_limit: int = 1000,
    ) -> int:
        return self.updater.update_latest(
            symbol=symbol,
            timeframe=timeframe,
            default_start_time=default_start_time,
            end_time=end_time,
            batch_limit=batch_limit,
        )

    def load_history(
        self,
        symbol: str,
        timeframe: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
        use_cache: bool = True,
    ) -> List[Candle]:
        """
        Load candles for a symbol/timeframe. When no time bounds/limit are
        given and a cached series exists, serve straight from cache;
        otherwise fall back to SQLite (and refresh the cache with the
        result of an unbounded load).
        """
        symbol = symbol.upper()

        if use_cache and start_time is None and end_time is None and limit is None:
            cached = self.cache.get(symbol, timeframe)
            if cached is not None:
                return cached

        candles = self.storage.load_history(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

        if use_cache and start_time is None and end_time is None and limit is None:
            self.cache.put(symbol, timeframe, candles)

        return candles

    def load_last_candle(self, symbol: str, timeframe: str) -> Optional[Candle]:
        return self.storage.load_last_candle(symbol.upper(), timeframe)

    def clear_cache(
        self, symbol: Optional[str] = None, timeframe: Optional[str] = None
    ) -> None:
        self.cache.clear_cache(symbol=symbol, timeframe=timeframe)

    def close(self) -> None:
        self.storage.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
