import os
import tempfile
import unittest

from tests.helpers import make_candle
from data.storage import MarketDataStorage


class TestMarketDataStorage(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.remove(self.db_path)  # let sqlite create it fresh
        self.storage = MarketDataStorage(db_path=self.db_path)

    def tearDown(self):
        self.storage.close()
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                os.remove(path)

    def test_insert_and_load_history(self):
        candles = [make_candle(t) for t in range(0, 5000, 1000)]
        stored = self.storage.insert_candles(candles)
        self.assertEqual(stored, 5)

        loaded = self.storage.load_history("BTCUSDT", "1m")
        self.assertEqual(len(loaded), 5)
        self.assertEqual([c.open_time for c in loaded], [0, 1000, 2000, 3000, 4000])

    def test_insert_ignores_duplicates(self):
        candles = [make_candle(1000)]
        first = self.storage.insert_candles(candles)
        second = self.storage.insert_candles(candles)
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        self.assertEqual(self.storage.count("BTCUSDT", "1m"), 1)

    def test_load_history_time_bounds(self):
        candles = [make_candle(t) for t in range(0, 10000, 1000)]
        self.storage.insert_candles(candles)

        loaded = self.storage.load_history("BTCUSDT", "1m", start_time=2000, end_time=5000)
        self.assertEqual([c.open_time for c in loaded], [2000, 3000, 4000, 5000])

    def test_load_history_limit(self):
        candles = [make_candle(t) for t in range(0, 10000, 1000)]
        self.storage.insert_candles(candles)

        loaded = self.storage.load_history("BTCUSDT", "1m", limit=3)
        self.assertEqual(len(loaded), 3)
        self.assertEqual([c.open_time for c in loaded], [0, 1000, 2000])

    def test_load_last_candle(self):
        candles = [make_candle(t) for t in range(0, 5000, 1000)]
        self.storage.insert_candles(candles)

        last = self.storage.load_last_candle("BTCUSDT", "1m")
        self.assertEqual(last.open_time, 4000)

    def test_load_last_candle_empty_returns_none(self):
        self.assertIsNone(self.storage.load_last_candle("BTCUSDT", "1m"))

    def test_symbol_and_timeframe_isolation(self):
        self.storage.insert_candles([make_candle(1000, symbol="BTCUSDT", timeframe="1m")])
        self.storage.insert_candles([make_candle(1000, symbol="ETHUSDT", timeframe="1m")])
        self.storage.insert_candles([make_candle(1000, symbol="BTCUSDT", timeframe="5m")])

        self.assertEqual(self.storage.count("BTCUSDT", "1m"), 1)
        self.assertEqual(self.storage.count("ETHUSDT", "1m"), 1)
        self.assertEqual(self.storage.count("BTCUSDT", "5m"), 1)

    def test_lowercase_symbol_normalized_on_query(self):
        self.storage.insert_candles([make_candle(1000, symbol="BTCUSDT")])
        loaded = self.storage.load_history("btcusdt", "1m")
        self.assertEqual(len(loaded), 1)

    def test_persistence_across_connections(self):
        self.storage.insert_candles([make_candle(1000)])
        self.storage.close()

        reopened = MarketDataStorage(db_path=self.db_path)
        self.assertEqual(reopened.count("BTCUSDT", "1m"), 1)
        reopened.close()
        self.storage = MarketDataStorage(db_path=self.db_path)  # for tearDown


if __name__ == "__main__":
    unittest.main()
