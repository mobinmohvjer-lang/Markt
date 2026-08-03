import os
import tempfile
import unittest

from tests.helpers import make_fake_client
from data.config import TIMEFRAME_MS
from data.downloader import HistoricalDataDownloader
from data.storage import MarketDataStorage
from data.updater import IncrementalDataUpdater


class TestIncrementalDataUpdater(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.remove(self.db_path)
        self.storage = MarketDataStorage(db_path=self.db_path)
        self.fake_client = make_fake_client(num_candles=1000, timeframe="1m")
        self.downloader = HistoricalDataDownloader(client=self.fake_client, storage=self.storage)
        self.updater = IncrementalDataUpdater(downloader=self.downloader, storage=self.storage)

    def tearDown(self):
        self.storage.close()
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                os.remove(path)

    def test_update_latest_requires_default_start_when_empty(self):
        with self.assertRaises(ValueError):
            self.updater.update_latest(symbol="BTCUSDT", timeframe="1m")

    def test_update_latest_uses_default_start_when_empty(self):
        stored = self.updater.update_latest(
            symbol="BTCUSDT",
            timeframe="1m",
            default_start_time=self.fake_client.series_start,
            batch_limit=200,
        )
        self.assertEqual(stored, 1000)
        self.assertEqual(self.storage.count("BTCUSDT", "1m"), 1000)

    def test_update_latest_continues_from_last_candle(self):
        end_time = self.fake_client.series_start + 300 * TIMEFRAME_MS["1m"] - 1
        self.downloader.download_history(
            symbol="BTCUSDT",
            timeframe="1m",
            start_time=self.fake_client.series_start,
            end_time=end_time,
            batch_limit=100,
        )
        self.assertEqual(self.storage.count("BTCUSDT", "1m"), 300)

        stored = self.updater.update_latest(symbol="BTCUSDT", timeframe="1m", batch_limit=200)
        self.assertEqual(stored, 700)
        self.assertEqual(self.storage.count("BTCUSDT", "1m"), 1000)

        last = self.storage.load_last_candle("BTCUSDT", "1m")
        self.assertEqual(last.open_time, self.fake_client.series_start + 999 * TIMEFRAME_MS["1m"])

    def test_update_latest_no_new_data_returns_zero(self):
        self.updater.update_latest(
            symbol="BTCUSDT", timeframe="1m", default_start_time=self.fake_client.series_start
        )
        stored_again = self.updater.update_latest(symbol="BTCUSDT", timeframe="1m")
        self.assertEqual(stored_again, 0)


if __name__ == "__main__":
    unittest.main()
