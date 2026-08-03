"""
Unit tests for the Indicators module (Part 1).

Covers:
    * Batch calculation correctness for SMA, EMA, WMA, HMA, RSI, ATR, MACD
    * Incremental (streaming) calculation matching batch calculation
    * Input support: list, numpy.ndarray, pandas.Series, pandas.DataFrame
    * Input validation errors

Uses the standard-library ``unittest`` framework so the suite has no
external test-runner dependency.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from indicators import (  # noqa: E402
    ATR,
    EMA,
    HMA,
    MACD,
    RSI,
    SMA,
    WMA,
    IndicatorResult,
    IndicatorValidationError,
)

np.random.seed(42)
PRICES = np.cumsum(np.random.normal(0, 1, 200)) + 100
HIGH = PRICES + np.random.uniform(0.1, 1.0, 200)
LOW = PRICES - np.random.uniform(0.1, 1.0, 200)
CLOSE = PRICES


class TestSMA(unittest.TestCase):
    def test_batch_matches_pandas(self):
        result = SMA(10).calculate(PRICES)
        expected = pd.Series(PRICES).rolling(10).mean().to_numpy()
        np.testing.assert_allclose(result.to_numpy(), expected, equal_nan=True)

    def test_warmup_is_nan(self):
        result = SMA(5).calculate(PRICES)
        self.assertTrue(np.isnan(result.to_numpy()[:4]).all())
        self.assertFalse(np.isnan(result.to_numpy()[4]))

    def test_incremental_matches_batch(self):
        batch = SMA(10).calculate(PRICES).to_numpy()
        sma = SMA(10)
        incremental = [sma.update(v) for v in PRICES]
        for b, i in zip(batch, incremental):
            if np.isnan(b):
                self.assertIsNone(i)
            else:
                self.assertAlmostEqual(i, b, places=9)

    def test_accepts_list(self):
        result = SMA(3).calculate([1, 2, 3, 4, 5])
        np.testing.assert_allclose(result.to_numpy()[2:], [2.0, 3.0, 4.0])

    def test_accepts_numpy(self):
        result = SMA(3).calculate(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
        np.testing.assert_allclose(result.to_numpy()[2:], [2.0, 3.0, 4.0])

    def test_accepts_series_and_preserves_index(self):
        idx = pd.date_range("2024-01-01", periods=5)
        s = pd.Series([1, 2, 3, 4, 5], index=idx)
        result = SMA(3).calculate(s)
        series = result.to_series()
        self.assertListEqual(list(series.index), list(idx))

    def test_accepts_dataframe_with_column(self):
        df = pd.DataFrame({"close": [1, 2, 3, 4, 5]})
        result = SMA(3).calculate(df, column="close")
        np.testing.assert_allclose(result.to_numpy()[2:], [2.0, 3.0, 4.0])

    def test_reset(self):
        sma = SMA(3)
        sma.update(1.0)
        sma.update(2.0)
        sma.reset()
        self.assertIsNone(sma.update(5.0))  # warm-up restarted


class TestEMA(unittest.TestCase):
    def test_batch_reasonable_range(self):
        result = EMA(10).calculate(PRICES).to_numpy()
        valid = result[~np.isnan(result)]
        self.assertEqual(valid.shape[0], PRICES.shape[0] - 9)
        self.assertTrue(np.all(np.isfinite(valid)))

    def test_incremental_matches_batch(self):
        batch = EMA(12).calculate(PRICES).to_numpy()
        ema = EMA(12)
        incremental = [ema.update(v) for v in PRICES]
        for b, i in zip(batch, incremental):
            if np.isnan(b):
                self.assertIsNone(i)
            else:
                self.assertAlmostEqual(i, b, places=7)

    def test_invalid_smoothing_raises(self):
        with self.assertRaises(IndicatorValidationError):
            EMA(10, smoothing=-1)

    def test_reset(self):
        ema = EMA(5)
        for v in PRICES[:5]:
            ema.update(v)
        ema.reset()
        for v in PRICES[:4]:
            self.assertIsNone(ema.update(v))


class TestWMA(unittest.TestCase):
    def test_batch_matches_manual_calc(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = WMA(3).calculate(data).to_numpy()
        # weights [1,2,3]; window [3,4,5] -> (3*1+4*2+5*3)/6 = 26/6
        self.assertAlmostEqual(result[4], (3 * 1 + 4 * 2 + 5 * 3) / 6)

    def test_incremental_matches_batch(self):
        batch = WMA(7).calculate(PRICES).to_numpy()
        wma = WMA(7)
        incremental = [wma.update(v) for v in PRICES]
        for b, i in zip(batch, incremental):
            if np.isnan(b):
                self.assertIsNone(i)
            else:
                self.assertAlmostEqual(i, b, places=9)


class TestHMA(unittest.TestCase):
    def test_batch_produces_finite_tail(self):
        result = HMA(16).calculate(PRICES).to_numpy()
        self.assertTrue(np.isfinite(result[-1]))
        self.assertTrue(np.isnan(result[0]))

    def test_incremental_matches_batch_tail(self):
        batch = HMA(16).calculate(PRICES).to_numpy()
        hma = HMA(16)
        incremental = [hma.update(v) for v in PRICES]
        # Compare the tail values where both are defined.
        for b, i in list(zip(batch, incremental))[-20:]:
            self.assertIsNotNone(i)
            self.assertAlmostEqual(i, b, places=5)

    def test_minimum_period(self):
        with self.assertRaises(IndicatorValidationError):
            HMA(1)


class TestRSI(unittest.TestCase):
    def test_batch_bounded_0_100(self):
        result = RSI(14).calculate(PRICES).to_numpy()
        valid = result[~np.isnan(result)]
        self.assertTrue(np.all((valid >= 0) & (valid <= 100)))

    def test_incremental_matches_batch(self):
        batch = RSI(14).calculate(PRICES).to_numpy()
        rsi = RSI(14)
        incremental = [rsi.update(v) for v in PRICES]
        for b, i in zip(batch, incremental):
            if np.isnan(b):
                self.assertIsNone(i)
            else:
                self.assertAlmostEqual(i, b, places=7)

    def test_all_gains_gives_100(self):
        data = np.arange(1, 30, dtype=float)  # strictly increasing
        result = RSI(14).calculate(data).to_numpy()
        self.assertAlmostEqual(result[-1], 100.0)


class TestATR(unittest.TestCase):
    def test_batch_matches_manual_calc(self):
        result = ATR(14).calculate(high=HIGH, low=LOW, close=CLOSE).to_numpy()
        self.assertTrue(np.isnan(result[:13]).all())
        self.assertTrue(np.isfinite(result[13:]).all())
        self.assertTrue(np.all(result[13:] >= 0))

    def test_dataframe_input(self):
        df = pd.DataFrame({"high": HIGH, "low": LOW, "close": CLOSE})
        result = ATR(14).calculate(df)
        self.assertIsInstance(result, IndicatorResult)
        self.assertTrue(np.isfinite(result.to_numpy()[13:]).all())

    def test_incremental_matches_batch(self):
        batch = ATR(14).calculate(high=HIGH, low=LOW, close=CLOSE).to_numpy()
        atr = ATR(14)
        incremental = [atr.update(h, l, c) for h, l, c in zip(HIGH, LOW, CLOSE)]
        for b, i in zip(batch, incremental):
            if np.isnan(b):
                self.assertIsNone(i)
            else:
                self.assertAlmostEqual(i, b, places=7)

    def test_missing_inputs_raises(self):
        with self.assertRaises(IndicatorValidationError):
            ATR(14).calculate()

    def test_mismatched_lengths_raise(self):
        with self.assertRaises(IndicatorValidationError):
            ATR(14).calculate(high=HIGH, low=LOW[:-1], close=CLOSE)


class TestMACD(unittest.TestCase):
    def test_batch_multi_output(self):
        result = MACD(12, 26, 9).calculate(PRICES)
        self.assertTrue(result.is_multi_output)
        self.assertSetEqual(set(result.to_numpy().keys()), {"macd", "signal", "histogram"})
        df = result.to_dataframe()
        self.assertListEqual(list(df.columns), ["macd", "signal", "histogram"])
        valid = df.dropna()
        np.testing.assert_allclose(valid["histogram"], valid["macd"] - valid["signal"])

    def test_incremental_matches_batch(self):
        batch = MACD(12, 26, 9).calculate(PRICES).to_numpy()
        macd = MACD(12, 26, 9)
        incremental = [macd.update(v) for v in PRICES]
        for i, val in enumerate(incremental):
            if val is None:
                self.assertTrue(np.isnan(batch["signal"][i]))
            else:
                self.assertAlmostEqual(val["macd"], batch["macd"][i], places=7)
                self.assertAlmostEqual(val["signal"], batch["signal"][i], places=7)
                self.assertAlmostEqual(val["histogram"], batch["histogram"][i], places=7)

    def test_slow_must_exceed_fast(self):
        with self.assertRaises(IndicatorValidationError):
            MACD(fast_period=26, slow_period=12, signal_period=9)


class TestValidation(unittest.TestCase):
    def test_invalid_period_type_raises(self):
        for cls in (SMA, EMA, WMA, RSI, ATR):
            with self.subTest(cls=cls):
                with self.assertRaises(IndicatorValidationError):
                    cls(period="10")  # type: ignore[arg-type]

    def test_negative_period_raises(self):
        with self.assertRaises(IndicatorValidationError):
            SMA(-1)

    def test_zero_period_raises(self):
        with self.assertRaises(IndicatorValidationError):
            SMA(0)

    def test_empty_input_raises(self):
        with self.assertRaises(IndicatorValidationError):
            SMA(3).calculate([])

    def test_insufficient_length_raises(self):
        with self.assertRaises(IndicatorValidationError):
            SMA(10).calculate([1, 2, 3])

    def test_unsupported_type_raises(self):
        with self.assertRaises(IndicatorValidationError):
            SMA(3).calculate({"a": 1})  # type: ignore[arg-type]

    def test_dataframe_without_column_raises(self):
        df = pd.DataFrame({"close": [1, 2, 3, 4, 5]})
        with self.assertRaises(IndicatorValidationError):
            SMA(3).calculate(df)


if __name__ == "__main__":
    unittest.main(verbosity=2)
