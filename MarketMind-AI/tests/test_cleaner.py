import unittest

from tests.helpers import make_candle
from data.cleaner import DataCleaner
from data.validator import DataValidator


class TestDataCleaner(unittest.TestCase):
    def setUp(self):
        self.cleaner = DataCleaner(DataValidator())

    def test_remove_duplicates_keeps_last(self):
        c1 = make_candle(1000, volume=1.0)
        c2 = make_candle(1000, volume=2.0)
        result = self.cleaner.remove_duplicates([c1, c2])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].volume, 2.0)

    def test_sort_candles_orders_ascending(self):
        c1 = make_candle(3000)
        c2 = make_candle(1000)
        c3 = make_candle(2000)
        result = self.cleaner.sort_candles([c1, c2, c3])
        self.assertEqual([c.open_time for c in result], [1000, 2000, 3000])

    def test_drop_invalid_removes_bad_candles(self):
        good = make_candle(1000)
        bad = make_candle(2000, volume=-1.0)
        result = self.cleaner.drop_invalid([good, bad])
        self.assertEqual(result, [good])

    def test_clean_full_pipeline(self):
        good1 = make_candle(2000)
        good2 = make_candle(1000)
        dup = make_candle(1000, volume=99.0)
        bad = make_candle(3000, volume=-5.0)

        result = self.cleaner.clean([good1, good2, dup, bad])

        self.assertEqual([c.open_time for c in result], [1000, 2000])
        self.assertEqual(result[0].volume, 99.0)

    def test_clean_ignores_none_entries(self):
        good = make_candle(1000)
        result = self.cleaner.clean([good, None])
        self.assertEqual(result, [good])


if __name__ == "__main__":
    unittest.main()
