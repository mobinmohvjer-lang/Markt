"""
Unit tests for the Indicators module (Part 2).

Covers the indicators added in this batch:

* Bollinger Bands, VWAP, Volume SMA, OBV
* ADX, DMI, Stochastic, CCI, ROC
* Keltner Channel, Donchian Channel
* Ichimoku Cloud, SuperTrend

Follows the same conventions as ``test_indicators.py``: stdlib
``unittest``, batch-vs-pandas/manual correctness checks where a simple
reference calculation exists, incremental-matches-batch checks, and
bounds/sanity checks for the more involved multi-output indicators.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from indicators import (  # noqa: E402
    ADX,
    CCI,
    DMI,
    OBV,
    ROC,
    VWAP,
    BollingerBands,
    DonchianChannel,
    Ichimoku,
    IndicatorResult,
    IndicatorValidationError,
    KeltnerChannel,
    Stochastic,
    SuperTrend,
    VolumeSMA,
)

np.random.seed(7)
N = 200
PRICES = np.cumsum(np.random.normal(0, 1, N)) + 100
HIGH = PRICES + np.random.uniform(0.1, 1.0, N)
LOW = PRICES - np.random.uniform(0.1, 1.0, N)
CLOSE = PRICES
VOLUME = np.random.uniform(1000, 5000, N)


class TestBollingerBands(unittest.TestCase):
    def test_batch_matches_pandas(self):
        result = BollingerBands(20, 2.0).calculate(PRICES)
        values = result.to_numpy()
        series = pd.Series(PRICES)
        expected_mid = series.rolling(20).mean()
        expected_std = series.rolling(20).std(ddof=0)
        np.testing.assert_allclose(values["middle"], expected_mid.to_numpy(), equal_nan=True)
        np.testing.assert_allclose(
            values["upper"], (expected_mid + 2.0 * expected_std).to_numpy(), equal_nan=True
        )
        np.testing.assert_allclose(
            values["lower"], (expected_mid - 2.0 * expected_std).to_numpy(), equal_nan=True
        )

    def test_upper_above_lower(self):
        values = BollingerBands(20).calculate(PRICES).to_numpy()
        valid = ~np.isnan(values["upper"])
        self.assertTrue(np.all(values["upper"][valid] >= values["lower"][valid]))

    def test_incremental_matches_batch(self):
        batch = BollingerBands(15, 2.0).calculate(PRICES).to_numpy()
        bb = BollingerBands(15, 2.0)
        incremental = [bb.update(v) for v in PRICES]
        for i, val in enumerate(incremental):
            if val is None:
                self.assertTrue(np.isnan(batch["middle"][i]))
            else:
                self.assertAlmostEqual(val["middle"], batch["middle"][i], places=7)
                self.assertAlmostEqual(val["upper"], batch["upper"][i], places=7)
                self.assertAlmostEqual(val["lower"], batch["lower"][i], places=7)

    def test_invalid_std_dev_raises(self):
        with self.assertRaises(IndicatorValidationError):
            BollingerBands(20, std_dev=0)


class TestVWAP(unittest.TestCase):
    def test_batch_matches_manual_calc(self):
        result = VWAP(10).calculate(high=HIGH, low=LOW, close=CLOSE, volume=VOLUME).to_numpy()
        typical = (HIGH + LOW + CLOSE) / 3.0
        i = 50
        window = slice(i - 9, i + 1)
        expected = np.sum(typical[window] * VOLUME[window]) / np.sum(VOLUME[window])
        self.assertAlmostEqual(result[i], expected, places=7)

    def test_incremental_matches_batch(self):
        batch = VWAP(10).calculate(high=HIGH, low=LOW, close=CLOSE, volume=VOLUME).to_numpy()
        vwap = VWAP(10)
        incremental = [vwap.update(h, l, c, v) for h, l, c, v in zip(HIGH, LOW, CLOSE, VOLUME)]
        for b, i in zip(batch, incremental):
            if np.isnan(b):
                self.assertIsNone(i)
            else:
                self.assertAlmostEqual(i, b, places=7)

    def test_dataframe_input(self):
        df = pd.DataFrame({"high": HIGH, "low": LOW, "close": CLOSE, "volume": VOLUME})
        result = VWAP(10).calculate(df)
        self.assertIsInstance(result, IndicatorResult)

    def test_missing_inputs_raises(self):
        with self.assertRaises(IndicatorValidationError):
            VWAP(10).calculate()


class TestVolumeSMA(unittest.TestCase):
    def test_batch_matches_pandas(self):
        result = VolumeSMA(10).calculate(volume=VOLUME)
        expected = pd.Series(VOLUME).rolling(10).mean().to_numpy()
        np.testing.assert_allclose(result.to_numpy(), expected, equal_nan=True)

    def test_incremental_matches_batch(self):
        batch = VolumeSMA(10).calculate(volume=VOLUME).to_numpy()
        vsma = VolumeSMA(10)
        incremental = [vsma.update(v) for v in VOLUME]
        for b, i in zip(batch, incremental):
            if np.isnan(b):
                self.assertIsNone(i)
            else:
                self.assertAlmostEqual(i, b, places=9)


class TestOBV(unittest.TestCase):
    def test_batch_matches_manual_calc(self):
        close = np.array([10.0, 11.0, 10.5, 10.5, 12.0])
        volume = np.array([100.0, 200.0, 150.0, 90.0, 300.0])
        result = OBV().calculate(close=close, volume=volume).to_numpy()
        expected = [100.0, 300.0, 150.0, 150.0, 450.0]
        np.testing.assert_allclose(result, expected)

    def test_incremental_matches_batch(self):
        batch = OBV().calculate(close=CLOSE, volume=VOLUME).to_numpy()
        obv = OBV()
        incremental = [obv.update(c, v) for c, v in zip(CLOSE, VOLUME)]
        np.testing.assert_allclose(incremental, batch, atol=1e-6)

    def test_mismatched_lengths_raise(self):
        with self.assertRaises(IndicatorValidationError):
            OBV().calculate(close=CLOSE, volume=VOLUME[:-1])


class TestDMI(unittest.TestCase):
    def test_batch_bounded_0_100(self):
        result = DMI(14).calculate(high=HIGH, low=LOW, close=CLOSE).to_numpy()
        for key in ("plus_di", "minus_di"):
            valid = result[key][~np.isnan(result[key])]
            self.assertTrue(np.all((valid >= 0) & (valid <= 100)))

    def test_incremental_matches_batch_tail(self):
        batch = DMI(14).calculate(high=HIGH, low=LOW, close=CLOSE).to_numpy()
        dmi = DMI(14)
        incremental = [dmi.update(h, l, c) for h, l, c in zip(HIGH, LOW, CLOSE)]
        for b_plus, b_minus, val in list(zip(batch["plus_di"], batch["minus_di"], incremental))[-20:]:
            self.assertIsNotNone(val)
            self.assertAlmostEqual(val["plus_di"], b_plus, places=3)
            self.assertAlmostEqual(val["minus_di"], b_minus, places=3)


class TestADX(unittest.TestCase):
    def test_batch_bounded_0_100(self):
        result = ADX(14).calculate(high=HIGH, low=LOW, close=CLOSE).to_numpy()
        valid = result["adx"][~np.isnan(result["adx"])]
        self.assertTrue(valid.shape[0] > 0)
        self.assertTrue(np.all((valid >= 0) & (valid <= 100)))

    def test_incremental_eventually_matches_batch(self):
        batch = ADX(14).calculate(high=HIGH, low=LOW, close=CLOSE).to_numpy()
        adx = ADX(14)
        incremental = [adx.update(h, l, c) for h, l, c in zip(HIGH, LOW, CLOSE)]
        last = incremental[-1]
        self.assertIsNotNone(last)
        self.assertAlmostEqual(last["adx"], batch["adx"][-1], places=2)


class TestStochastic(unittest.TestCase):
    def test_batch_bounded_0_100(self):
        result = Stochastic(14, 3).calculate(high=HIGH, low=LOW, close=CLOSE).to_numpy()
        for key in ("k", "d"):
            valid = result[key][~np.isnan(result[key])]
            self.assertTrue(np.all((valid >= -1e-9) & (valid <= 100 + 1e-9)))

    def test_incremental_matches_batch(self):
        batch = Stochastic(14, 3).calculate(high=HIGH, low=LOW, close=CLOSE).to_numpy()
        stoch = Stochastic(14, 3)
        incremental = [stoch.update(h, l, c) for h, l, c in zip(HIGH, LOW, CLOSE)]
        for i, val in enumerate(incremental):
            if val is None:
                self.assertTrue(np.isnan(batch["k"][i]))
            else:
                self.assertAlmostEqual(val["k"], batch["k"][i], places=6)


class TestCCI(unittest.TestCase):
    def test_batch_matches_manual_calc(self):
        result = CCI(20).calculate(high=HIGH, low=LOW, close=CLOSE).to_numpy()
        typical = (HIGH + LOW + CLOSE) / 3.0
        i = 60
        window = typical[i - 19:i + 1]
        mean = window.mean()
        mean_dev = np.mean(np.abs(window - mean))
        expected = (typical[i] - mean) / (0.015 * mean_dev)
        self.assertAlmostEqual(result[i], expected, places=6)

    def test_incremental_matches_batch(self):
        batch = CCI(20).calculate(high=HIGH, low=LOW, close=CLOSE).to_numpy()
        cci = CCI(20)
        incremental = [cci.update(h, l, c) for h, l, c in zip(HIGH, LOW, CLOSE)]
        for b, i in zip(batch, incremental):
            if np.isnan(b):
                self.assertIsNone(i)
            else:
                self.assertAlmostEqual(i, b, places=6)


class TestROC(unittest.TestCase):
    def test_batch_matches_manual_calc(self):
        data = np.array([10.0, 11.0, 12.0, 9.0, 15.0])
        result = ROC(2).calculate(data).to_numpy()
        expected = [np.nan, np.nan, (12 - 10) / 10 * 100, (9 - 11) / 11 * 100, (15 - 12) / 12 * 100]
        np.testing.assert_allclose(result, expected, equal_nan=True)

    def test_incremental_matches_batch(self):
        batch = ROC(5).calculate(PRICES).to_numpy()
        roc = ROC(5)
        incremental = [roc.update(v) for v in PRICES]
        for b, i in zip(batch, incremental):
            if np.isnan(b):
                self.assertIsNone(i)
            else:
                self.assertAlmostEqual(i, b, places=7)


class TestKeltnerChannel(unittest.TestCase):
    def test_upper_above_lower(self):
        values = KeltnerChannel(20, 10, 2.0).calculate(high=HIGH, low=LOW, close=CLOSE).to_numpy()
        valid = ~np.isnan(values["upper"])
        self.assertTrue(np.all(values["upper"][valid] >= values["lower"][valid]))
        self.assertTrue(np.all(values["middle"][valid] >= values["lower"][valid]))

    def test_incremental_matches_batch_tail(self):
        batch = KeltnerChannel(20, 10, 2.0).calculate(high=HIGH, low=LOW, close=CLOSE).to_numpy()
        kc = KeltnerChannel(20, 10, 2.0)
        incremental = [kc.update(h, l, c) for h, l, c in zip(HIGH, LOW, CLOSE)]
        for b_mid, val in list(zip(batch["middle"], incremental))[-10:]:
            self.assertIsNotNone(val)
            self.assertAlmostEqual(val["middle"], b_mid, places=5)


class TestDonchianChannel(unittest.TestCase):
    def test_batch_matches_pandas(self):
        result = DonchianChannel(20).calculate(high=HIGH, low=LOW).to_numpy()
        expected_upper = pd.Series(HIGH).rolling(20).max().to_numpy()
        expected_lower = pd.Series(LOW).rolling(20).min().to_numpy()
        np.testing.assert_allclose(result["upper"], expected_upper, equal_nan=True)
        np.testing.assert_allclose(result["lower"], expected_lower, equal_nan=True)
        np.testing.assert_allclose(
            result["middle"], (expected_upper + expected_lower) / 2.0, equal_nan=True
        )

    def test_incremental_matches_batch(self):
        batch = DonchianChannel(15).calculate(high=HIGH, low=LOW).to_numpy()
        dc = DonchianChannel(15)
        incremental = [dc.update(h, l) for h, l in zip(HIGH, LOW)]
        for i, val in enumerate(incremental):
            if val is None:
                self.assertTrue(np.isnan(batch["upper"][i]))
            else:
                self.assertAlmostEqual(val["upper"], batch["upper"][i], places=9)
                self.assertAlmostEqual(val["lower"], batch["lower"][i], places=9)


class TestIchimoku(unittest.TestCase):
    def test_batch_output_keys_and_shape(self):
        result = Ichimoku(9, 26, 52, 26).calculate(high=HIGH, low=LOW, close=CLOSE)
        values = result.to_numpy()
        self.assertSetEqual(
            set(values.keys()),
            {"tenkan_sen", "kijun_sen", "senkou_span_a", "senkou_span_b", "chikou_span"},
        )
        for arr in values.values():
            self.assertEqual(arr.shape[0], N)

    def test_tenkan_matches_manual_calc(self):
        result = Ichimoku(9, 26, 52, 26).calculate(high=HIGH, low=LOW, close=CLOSE).to_numpy()
        i = 40
        expected = (HIGH[i - 8:i + 1].max() + LOW[i - 8:i + 1].min()) / 2.0
        self.assertAlmostEqual(result["tenkan_sen"][i], expected, places=7)

    def test_update_returns_none_before_any_window_fills(self):
        ich = Ichimoku(9, 26, 52, 26)
        self.assertIsNone(ich.update(HIGH[0], LOW[0], CLOSE[0]))

    def test_update_tenkan_available_before_kijun(self):
        ich = Ichimoku(9, 26, 52, 26)
        last = None
        for h, l, c in zip(HIGH[:15], LOW[:15], CLOSE[:15]):
            last = ich.update(h, l, c)
        self.assertIsNotNone(last["tenkan_sen"])
        self.assertIsNone(last["kijun_sen"])


class TestSuperTrend(unittest.TestCase):
    def test_direction_is_plus_or_minus_one(self):
        result = SuperTrend(10, 3.0).calculate(high=HIGH, low=LOW, close=CLOSE).to_numpy()
        valid = result["direction"][~np.isnan(result["supertrend"])]
        self.assertTrue(np.all(np.isin(valid, [1.0, -1.0])))

    def test_incremental_matches_batch_tail(self):
        batch = SuperTrend(10, 3.0).calculate(high=HIGH, low=LOW, close=CLOSE).to_numpy()
        st = SuperTrend(10, 3.0)
        incremental = [st.update(h, l, c) for h, l, c in zip(HIGH, LOW, CLOSE)]
        for b_val, b_dir, val in list(zip(batch["supertrend"], batch["direction"], incremental))[-10:]:
            self.assertIsNotNone(val)
            self.assertAlmostEqual(val["supertrend"], b_val, places=3)
            self.assertEqual(val["direction"], b_dir)

    def test_invalid_multiplier_raises(self):
        with self.assertRaises(IndicatorValidationError):
            SuperTrend(10, multiplier=0)


class TestValidationPart2(unittest.TestCase):
    def test_negative_period_raises(self):
        for cls, kwargs in (
            (BollingerBands, {}),
            (VWAP, {}),
            (VolumeSMA, {}),
            (OBV, {}),
            (DMI, {}),
            (ADX, {}),
            (CCI, {}),
            (ROC, {}),
            (DonchianChannel, {}),
        ):
            with self.subTest(cls=cls):
                with self.assertRaises(IndicatorValidationError):
                    cls(-1, **kwargs)

    def test_keltner_invalid_atr_period_raises(self):
        with self.assertRaises(IndicatorValidationError):
            KeltnerChannel(20, atr_period=-1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
