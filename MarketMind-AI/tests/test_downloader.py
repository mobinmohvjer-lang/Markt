import os
import tempfile
import unittest

from tests.helpers import make_fake_client
from data.cache import CandleCache
from data.cleaner import DataCleaner
from data.downloader import HistoricalDataDownloader
from data.normalizer import DataNormalizer
from data.storage import MarketDataStorage
from data.validator import DataValidator


class TestHistoricalDataDownloader(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        os.remove(self.db_path)
        self.storage = MarketDataStorage(db_path=self.db_path)
        self.cache = CandleCache(max_keys=8, max_candles_per_key=5000)
        self.fake_client = make_fake_client(num_candles=1000, timeframe="1m")
        self.downloader = HistoricalDataDownloader(
            client=self.fake_client,
            storage=self.storage,
            validator=DataValidator(),
            cleaner=DataCleaner(),
            normalizer=DataNormalizer(),
            cache=self.cache,
        )

    def tearDown(self):
        self.storage.close()
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                os.remove(path)

    def test_download_history_stores_all_candles(self):
        stored = self.downloader.download_history(
            symbol="BTCUSDT",
            timeframe="1m",
            start_time=self.fake_client.series_start,
            batch_limit=200,
        )
        self.assertEqual(stored, 1000)
        self.assertEqual(self.storage.count("BTCUSDT", "1m"), 1000)

    def test_download_history_no_duplicates_on_rerun(self):
        self.downloader.download_history(
            symbol="BTCUSDT", timeframe="1m", start_time=self.fake_client.series_start, batch_limit=200
        )
        second_run_stored = self.downloader.download_history(
            symbol="BTCUSDT", timeframe="1m", start_time=self.fake_client.series_start, batch_limit=200
        )
        self.assertEqual(second_run_stored, 0)
        self.assertEqual(self.storage.count("BTCUSDT", "1m"), 1000)

    def test_download_history_respects_end_time(self):
        from data.config import TIMEFRAME_MS

        end_time = self.fake_client.series_start + 100 * TIMEFRAME_MS["1m"] - 1
        stored = self.downloader.download_history(
            symbol="BTCUSDT",
            timeframe="1m",
            start_time=self.fake_client.series_start,
            end_time=end_time,
            batch_limit=50,
        )
        self.assertEqual(stored, 100)
        self.assertEqual(self.storage.count("BTCUSDT", "1m"), 100)

    def test_download_history_populates_cache(self):
        self.downloader.download_history(
            symbol="BTCUSDT", timeframe="1m", start_time=self.fake_client.series_start, batch_limit=500
        )
        cached = self.cache.get("BTCUSDT", "1m")
        self.assertIsNotNone(cached)
        self.assertGreater(len(cached), 0)

    def test_download_history_paginates_multiple_batches(self):
        self.downloader.download_history(
            symbol="BTCUSDT", timeframe="1m", start_time=self.fake_client.series_start, batch_limit=100
        )
        self.assertGreaterEqual(len(self.fake_client.calls), 10)

    def test_download_history_empty_series_returns_zero(self):
        stored = self.downloader.download_history(
            symbol="BTCUSDT",
            timeframe="1m",
            start_time=self.fake_client.series_end + 1_000_000,
        )
        self.assertEqual(stored, 0)

    def test_download_history_all_supported_timeframes(self):
        from data.config import TIMEFRAMES

        for tf in TIMEFRAMES:
            client = make_fake_client(num_candles=20, timeframe=tf)
            downloader = HistoricalDataDownloader(client=client, storage=self.storage)
            stored = downloader.download_history(
                symbol="ETHUSDT", timeframe=tf, start_time=client.series_start, batch_limit=10
            )
            self.assertEqual(stored, 20, f"timeframe {tf} did not store all candles")
            self.assertEqual(self.storage.count("ETHUSDT", tf), 20)


if __name__ == "__main__":
    unittest.main()
