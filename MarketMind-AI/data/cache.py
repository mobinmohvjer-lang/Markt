"""
CandleCache: simple in-memory LRU cache keyed by (symbol, timeframe),
caching the most recently used candle lists so repeated `load_history`
calls for hot symbols don't have to hit SQLite every time.
"""

from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from .models import Candle

CacheKey = Tuple[str, str]


class CandleCache:
    def __init__(self, max_keys: int = 256, max_candles_per_key: int = 5000):
        """
        max_keys: how many distinct (symbol, timeframe) series to keep.
        max_candles_per_key: cap on candles stored per series (keeps the most
        recent ones when a series grows past this size).
        """
        self.max_keys = max_keys
        self.max_candles_per_key = max_candles_per_key
        self._store: "OrderedDict[CacheKey, List[Candle]]" = OrderedDict()

    def _key(self, symbol: str, timeframe: str) -> CacheKey:
        return (symbol.upper(), timeframe)

    def get(self, symbol: str, timeframe: str) -> Optional[List[Candle]]:
        key = self._key(symbol, timeframe)
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return list(self._store[key])

    def put(self, symbol: str, timeframe: str, candles: List[Candle]) -> None:
        key = self._key(symbol, timeframe)
        trimmed = sorted(candles, key=lambda c: c.open_time)
        if len(trimmed) > self.max_candles_per_key:
            trimmed = trimmed[-self.max_candles_per_key:]
        self._store[key] = trimmed
        self._store.move_to_end(key)
        self._evict_if_needed()

    def append_candle(self, symbol: str, timeframe: str, candle: Candle) -> None:
        """Incrementally update the cache with a single new/updated candle."""
        key = self._key(symbol, timeframe)
        series = self._store.get(key, [])
        if series and series[-1].open_time == candle.open_time:
            series[-1] = candle
        elif series and candle.open_time < series[-1].open_time:
            # Out-of-order update to an existing candle -- replace if present.
            replaced = False
            for i, existing in enumerate(series):
                if existing.open_time == candle.open_time:
                    series[i] = candle
                    replaced = True
                    break
            if not replaced:
                series.append(candle)
                series.sort(key=lambda c: c.open_time)
        else:
            series.append(candle)

        if len(series) > self.max_candles_per_key:
            series = series[-self.max_candles_per_key:]

        self._store[key] = series
        self._store.move_to_end(key)
        self._evict_if_needed()

    def _evict_if_needed(self) -> None:
        while len(self._store) > self.max_keys:
            self._store.popitem(last=False)

    def clear_cache(self, symbol: Optional[str] = None, timeframe: Optional[str] = None) -> None:
        """
        Clear the entire cache, or just one (symbol, timeframe) series if both
        are provided.
        """
        if symbol is not None and timeframe is not None:
            self._store.pop(self._key(symbol, timeframe), None)
        else:
            self._store.clear()

    def __len__(self) -> int:
        return len(self._store)
