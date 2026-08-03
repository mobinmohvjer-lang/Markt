import unittest


from data.config import TIMEFRAMES, TIMEFRAME_MS, assert_valid_timeframe
from data.models import Candle


class TestConfig(unittest.TestCase):
    def test_all_required_timeframes_supported(self):
        expected = {"1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"}
        self.assertTrue(expected.issubset(set(TIMEFRAMES)))
        for tf in expected:
            self.assertIn(tf, TIMEFRAME_MS)
            self.assertGreater(TIMEFRAME_MS[tf], 0)

    def test_assert_valid_timeframe_raises_on_bad_input(self):
        with self.assertRaises(ValueError):
            assert_valid_timeframe("2m")

    def test_assert_valid_timeframe_passes_on_good_input(self):
        assert_valid_timeframe("1h")  # should not raise


class TestCandleModel(unittest.TestCase):
    def test_candle_from_raw_kline_parses_correctly(self):
        raw = [
            1000, "100.5", "101.5", "99.5", "100.75", "12.34",
            1999, "1234.5", 42, "6.0", "600.0", "0",
        ]
        candle = Candle.from_raw_kline("BTCUSDT", "1m", raw)
        self.assertEqual(candle.symbol, "BTCUSDT")
        self.assertEqual(candle.open_time, 1000)
        self.assertEqual(candle.open, 100.5)
        self.assertEqual(candle.close, 100.75)
        self.assertEqual(candle.trades, 42)

    def test_candle_from_raw_kline_handles_malformed_input(self):
        self.assertIsNone(Candle.from_raw_kline("BTCUSDT", "1m", None))
        self.assertIsNone(Candle.from_raw_kline("BTCUSDT", "1m", [1, 2]))
        self.assertIsNone(Candle.from_raw_kline("BTCUSDT", "1m", ["bad"] * 12))

    def test_candle_roundtrip_through_row(self):
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1m",
            open_time=1000,
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=10.0,
            close_time=1999,
        )
        row = candle.as_tuple()
        rebuilt = Candle.from_row(row)
        self.assertEqual(rebuilt, candle)


if __name__ == "__main__":
    unittest.main()
