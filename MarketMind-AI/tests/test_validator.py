import unittest

from tests.helpers import make_candle
from data.validator import DataValidator


class TestDataValidator(unittest.TestCase):
    def setUp(self):
        self.validator = DataValidator()

    def test_valid_candle_passes(self):
        ok, issues = self.validator.validate_candle(make_candle(1000))
        self.assertTrue(ok)
        self.assertEqual(issues, [])

    def test_none_candle_is_invalid(self):
        ok, issues = self.validator.validate_candle(None)
        self.assertFalse(ok)
        self.assertTrue(issues)

    def test_high_less_than_low_is_invalid(self):
        ok, issues = self.validator.validate_candle(make_candle(1000, high=90.0, low=99.0))
        self.assertFalse(ok)
        self.assertTrue(any("high" in i for i in issues))

    def test_negative_volume_is_invalid(self):
        ok, issues = self.validator.validate_candle(make_candle(1000, volume=-5.0))
        self.assertFalse(ok)
        self.assertTrue(any("volume" in i for i in issues))

    def test_negative_price_is_invalid(self):
        ok, _ = self.validator.validate_candle(make_candle(1000, open=-1.0))
        self.assertFalse(ok)

    def test_close_time_before_open_time_is_invalid(self):
        ok, issues = self.validator.validate_candle(make_candle(1000, close_time=500))
        self.assertFalse(ok)
        self.assertTrue(any("close_time" in i for i in issues))

    def test_nan_field_is_invalid(self):
        ok, _ = self.validator.validate_candle(make_candle(1000, open=float("nan")))
        self.assertFalse(ok)

    def test_high_below_open_close_is_invalid(self):
        ok, issues = self.validator.validate_candle(
            make_candle(1000, open=100.0, close=105.0, high=102.0, low=99.0)
        )
        self.assertFalse(ok)
        self.assertTrue(any("high is less than" in i for i in issues))

    def test_low_above_open_close_is_invalid(self):
        ok, issues = self.validator.validate_candle(
            make_candle(1000, open=100.0, close=95.0, low=98.0, high=105.0)
        )
        self.assertFalse(ok)
        self.assertTrue(any("low is greater than" in i for i in issues))

    def test_validate_batch_splits_valid_and_invalid(self):
        good = make_candle(1000)
        bad = make_candle(2000, volume=-1.0)
        valid, invalid = self.validator.validate_batch([good, bad])
        self.assertEqual(valid, [good])
        self.assertEqual(len(invalid), 1)
        self.assertEqual(invalid[0][0], bad)


if __name__ == "__main__":
    unittest.main()
