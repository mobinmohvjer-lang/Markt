import unittest

from tests.helpers import make_candle
from data.cache import CandleCache


class TestCandleCache(unittest.TestCase):
    def setUp(self):
        self.cache = CandleCache(max_keys=8, max_candles_per_key=1000)

    def test_put_and_get(self):
        candles = [make_candle(t) for t in range(0, 3000, 1000)]
        self.cache.put("BTCUSDT", "1m", candles)
        result = self.cache.get("BTCUSDT", "1m")
        self.assertEqual([c.open_time for c in result], [0, 1000, 2000])

    def test_get_missing_key_returns_none(self):
        self.assertIsNone(self.cache.get("BTCUSDT", "1m"))

    def test_case_insensitive_symbol(self):
        self.cache.put("btcusdt", "1m", [make_candle(0)])
        self.assertIsNotNone(self.cache.get("BTCUSDT", "1m"))

    def test_append_candle_adds_new(self):
        self.cache.put("BTCUSDT", "1m", [make_candle(0)])
        self.cache.append_candle("BTCUSDT", "1m", make_candle(1000))
        result = self.cache.get("BTCUSDT", "1m")
        self.assertEqual([c.open_time for c in result], [0, 1000])

    def test_append_candle_updates_existing(self):
        self.cache.put("BTCUSDT", "1m", [make_candle(0, close=100.5)])
        self.cache.append_candle("BTCUSDT", "1m", make_candle(0, close=999.0))
        result = self.cache.get("BTCUSDT", "1m")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].close, 999.0)

    def test_clear_cache_all(self):
        self.cache.put("BTCUSDT", "1m", [make_candle(0)])
        self.cache.put("ETHUSDT", "1m", [make_candle(0)])
        self.cache.clear_cache()
        self.assertIsNone(self.cache.get("BTCUSDT", "1m"))
        self.assertIsNone(self.cache.get("ETHUSDT", "1m"))

    def test_clear_cache_single_key(self):
        self.cache.put("BTCUSDT", "1m", [make_candle(0)])
        self.cache.put("ETHUSDT", "1m", [make_candle(0)])
        self.cache.clear_cache(symbol="BTCUSDT", timeframe="1m")
        self.assertIsNone(self.cache.get("BTCUSDT", "1m"))
        self.assertIsNotNone(self.cache.get("ETHUSDT", "1m"))

    def test_lru_eviction_by_max_keys(self):
        small_cache = CandleCache(max_keys=2, max_candles_per_key=100)
        small_cache.put("A", "1m", [make_candle(0, symbol="A")])
        small_cache.put("B", "1m", [make_candle(0, symbol="B")])
        small_cache.put("C", "1m", [make_candle(0, symbol="C")])  # evicts A (LRU)

        self.assertIsNone(small_cache.get("A", "1m"))
        self.assertIsNotNone(small_cache.get("B", "1m"))
        self.assertIsNotNone(small_cache.get("C", "1m"))

    def test_max_candles_per_key_trims_oldest(self):
        small_cache = CandleCache(max_keys=8, max_candles_per_key=3)
        candles = [make_candle(t) for t in range(0, 5000, 1000)]
        small_cache.put("BTCUSDT", "1m", candles)
        result = small_cache.get("BTCUSDT", "1m")
        self.assertEqual(len(result), 3)
        self.assertEqual([c.open_time for c in result], [2000, 3000, 4000])


if __name__ == "__main__":
    unittest.main()
