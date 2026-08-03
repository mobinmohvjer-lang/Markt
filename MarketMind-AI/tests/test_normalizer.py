import unittest

from tests.helpers import make_candle
from data.normalizer import DataNormalizer


class TestDataNormalizer(unittest.TestCase):
    def setUp(self):
        self.normalizer = DataNormalizer()

    def test_normalize_uppercases_symbol(self):
        c = self.normalizer.normalize_candle(make_candle(1000, symbol="btcusdt"))
        self.assertEqual(c.symbol, "BTCUSDT")

    def test_normalize_rounds_prices(self):
        c = self.normalizer.normalize_candle(make_candle(1000, open=100.123456789, high=101.987654321))
        self.assertEqual(c.open, round(100.123456789, 8))
        self.assertEqual(c.high, round(101.987654321, 8))

    def test_normalize_casts_types(self):
        c = self.normalizer.normalize_candle(make_candle(1000, trades="5"))
        self.assertIsInstance(c.open_time, int)
        self.assertIsInstance(c.trades, int)
        self.assertIsInstance(c.open, float)

    def test_normalize_batch(self):
        candles = [make_candle(1000, symbol="btcusdt"), make_candle(2000, symbol="ethusdt")]
        result = self.normalizer.normalize_batch(candles)
        self.assertEqual(result[0].symbol, "BTCUSDT")
        self.assertEqual(result[1].symbol, "ETHUSDT")
        self.assertEqual(len(result), 2)

    def test_custom_precision(self):
        n = DataNormalizer(price_precision=2, volume_precision=1)
        c = n.normalize_candle(make_candle(1000, open=100.123456789, volume=10.999999999))
        self.assertEqual(c.open, round(100.123456789, 2))
        self.assertEqual(c.volume, round(10.999999999, 1))


if __name__ == "__main__":
    unittest.main()
