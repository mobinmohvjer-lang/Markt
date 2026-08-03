import os
import tempfile
import unittest

from tests.helpers import make_fake_client
from data.config import TIMEFRAME_MS
from data.engine import DataEngine


class TestDataEngine(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.remove(self.db_path)
        self.fake_client = make_fake_client(num_candles=1000, timeframe="1m")
        self.engine = DataEngine(client=self.fake_client, db_path=self.db_path)

    def tearDown(self):
        self.engine.close()
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                os.remove(path)

    def test_engine_download_and_load_history(self):
        stored = self.engine.download_history(
            symbol="BTCUSDT", timeframe="1m", start_time=self.fake_client.series_start, batch_limit=250
        )
        self.assertEqual(stored, 1000)

        history = self.engine.load_history("BTCUSDT", "1m", limit=10)
        self.assertEqual(len(history), 10)
        self.assertEqual(history[0].open_time, self.fake_client.series_start)

    def test_engine_load_last_candle(self):
        self.engine.download_history(
            symbol="BTCUSDT", timeframe="1m", start_time=self.fake_client.series_start, batch_limit=250
        )
        last = self.engine.load_last_candle("BTCUSDT", "1m")
        self.assertEqual(last.open_time, self.fake_client.series_start + 999 * TIMEFRAME_MS["1m"])

    def test_engine_update_latest(self):
        end_time = self.fake_client.series_start + 500 * TIMEFRAME_MS["1m"] - 1
        self.engine.download_history(
            symbol="BTCUSDT", timeframe="1m", start_time=self.fake_client.series_start, end_time=end_time
        )
        stored = self.engine.update_latest(symbol="BTCUSDT", timeframe="1m")
        self.assertEqual(stored, 500)

        all_history = self.engine.load_history("BTCUSDT", "1m")
        self.assertEqual(len(all_history), 1000)

    def test_engine_cache_hit_on_unbounded_load(self):
        self.engine.download_history(
            symbol="BTCUSDT", timeframe="1m", start_time=self.fake_client.series_start, batch_limit=1000
        )
        first = self.engine.load_history("BTCUSDT", "1m")
        second = self.engine.load_history("BTCUSDT", "1m")
        self.assertEqual([c.open_time for c in first], [c.open_time for c in second])

    def test_engine_clear_cache(self):
        self.engine.download_history(
            symbol="BTCUSDT", timeframe="1m", start_time=self.fake_client.series_start, batch_limit=1000
        )
        self.engine.load_history("BTCUSDT", "1m")
        self.assertIsNotNone(self.engine.cache.get("BTCUSDT", "1m"))

        self.engine.clear_cache()
        self.assertIsNone(self.engine.cache.get("BTCUSDT", "1m"))

        history = self.engine.load_history("BTCUSDT", "1m")
        self.assertEqual(len(history), 1000)

    def test_engine_bounded_load_bypasses_cache_population(self):
        self.engine.download_history(
            symbol="BTCUSDT", timeframe="1m", start_time=self.fake_client.series_start, batch_limit=1000
        )
        self.engine.clear_cache()
        bounded = self.engine.load_history("BTCUSDT", "1m", limit=5)
        self.assertEqual(len(bounded), 5)
        self.assertIsNone(self.engine.cache.get("BTCUSDT", "1m"))


if __name__ == "__main__":
    unittest.main()
