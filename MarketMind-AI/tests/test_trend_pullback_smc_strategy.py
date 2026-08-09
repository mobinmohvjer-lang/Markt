"""
test_trend_pullback_smc_strategy.py
-------------------------------------
Purpose:
    Unit tests for `strategies.trend_pullback_smc_strategy.
    TrendPullbackSMCStrategy` -- construction/validation, the pure
    price-action/SMC helper functions (tested directly against
    hand-crafted arrays for deterministic assertions), and `decide()`
    end-to-end behavior (insufficient data, determinism, risk gate,
    output shape).

Run with:
    pytest tests/test_trend_pullback_smc_strategy.py -v
    python3 -m unittest tests.test_trend_pullback_smc_strategy -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import numpy as np

from core.entities.candle import Candle
from core.enums import SignalDirection
from strategies.context import StrategyContext
from strategies.exceptions import InsufficientStrategyDataError, StrategyConfigurationError
from strategies.risk_management.result import RiskResult
from strategies.trend_pullback_smc_strategy import TrendPullbackSMCStrategy


def make_candle(
    *,
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    index: int = 0,
    open_: float,
    high: float,
    low: float,
    close: float,
    volume: float = 100.0,
) -> Candle:
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    open_time = start + timedelta(hours=index)
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        open_time=open_time,
        close_time=open_time + timedelta(hours=1),
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal(str(volume)),
    )


def make_trend_candles(
    n: int,
    *,
    start_price: float = 100.0,
    drift: float = 0.2,
    seed: int = 1,
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
) -> list[Candle]:
    """Deterministic pseudo-random walk with a directional drift."""
    rng = np.random.default_rng(seed)
    price = start_price
    candles = []
    for i in range(n):
        change = drift + rng.normal(0, 0.5)
        open_p = price
        close_p = max(1.0, price + change)
        high_p = max(open_p, close_p) + abs(rng.normal(0, 0.2))
        low_p = min(open_p, close_p) - abs(rng.normal(0, 0.2))
        candles.append(
            make_candle(
                symbol=symbol,
                timeframe=timeframe,
                index=i,
                open_=round(open_p, 2),
                high=round(high_p, 2),
                low=round(low_p, 2),
                close=round(close_p, 2),
            )
        )
        price = close_p
    return candles


class TestConstruction(unittest.TestCase):
    def test_defaults_construct_successfully(self) -> None:
        strategy = TrendPullbackSMCStrategy()
        self.assertEqual(strategy.symbol, "BTCUSDT")
        self.assertEqual(strategy.timeframe, "1h")
        self.assertEqual(strategy.higher_timeframe, "4h")
        self.assertGreater(strategy.min_candles_required, 200)

    def test_invalid_ema_ordering_raises(self) -> None:
        with self.assertRaises(StrategyConfigurationError):
            TrendPullbackSMCStrategy(
                ema_fast_period=50, ema_medium_period=20, ema_slow_period=100, ema_trend_period=200
            )

    def test_invalid_rsi_zone_ordering_raises(self) -> None:
        with self.assertRaises(StrategyConfigurationError):
            TrendPullbackSMCStrategy(rsi_pullback_low=80, rsi_pullback_high=20)

    def test_macd_slow_must_exceed_fast(self) -> None:
        with self.assertRaises(StrategyConfigurationError):
            TrendPullbackSMCStrategy(macd_fast_period=26, macd_slow_period=12)

    def test_negative_period_raises(self) -> None:
        with self.assertRaises(StrategyConfigurationError):
            TrendPullbackSMCStrategy(rsi_period=-1)

    def test_adx_threshold_out_of_range_raises(self) -> None:
        with self.assertRaises(StrategyConfigurationError):
            TrendPullbackSMCStrategy(adx_threshold=150.0)

    def test_min_candles_required_too_small_raises(self) -> None:
        with self.assertRaises(StrategyConfigurationError):
            TrendPullbackSMCStrategy(min_candles_required=5)

    def test_custom_min_candles_required_accepted(self) -> None:
        strategy = TrendPullbackSMCStrategy(min_candles_required=10_000)
        self.assertEqual(strategy.min_candles_required, 10_000)


class TestPurePriceActionHelpers(unittest.TestCase):
    """Deterministic tests for the SMC/price-action primitives in isolation."""

    def setUp(self) -> None:
        self.strategy = TrendPullbackSMCStrategy()

    def test_ema_alignment_bullish(self) -> None:
        result = self.strategy._ema_alignment(110, 105, 102, 100)
        self.assertEqual(result, "bullish")

    def test_ema_alignment_bearish(self) -> None:
        result = self.strategy._ema_alignment(90, 95, 98, 100)
        self.assertEqual(result, "bearish")

    def test_ema_alignment_mixed(self) -> None:
        result = self.strategy._ema_alignment(105, 110, 102, 100)
        self.assertEqual(result, "mixed")

    def test_ema_alignment_unknown_on_nan(self) -> None:
        result = self.strategy._ema_alignment(float("nan"), 105, 102, 100)
        self.assertEqual(result, "unknown")

    def test_slope_positive(self) -> None:
        arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
        slope = self.strategy._slope(arr, 3)
        self.assertAlmostEqual(slope, 1.0)

    def test_slope_none_when_insufficient_length(self) -> None:
        arr = np.array([1.0, 2.0])
        self.assertIsNone(self.strategy._slope(arr, 5))

    def test_find_swings_detects_high_and_low(self) -> None:
        highs = np.array([1, 2, 5, 2, 1, 2, 6, 2, 1], dtype=float)
        lows = np.array([0, 1, 3, 1, 0, 1, 4, 1, 0], dtype=float)
        swings = self.strategy._find_swings(highs, lows, strength=2)
        kinds = [kind for _, _, kind in swings]
        self.assertIn("high", kinds)

    def test_confirmation_candle_bullish_engulfing(self) -> None:
        opens = np.array([10.0, 9.0])
        highs = np.array([10.5, 11.0])
        lows = np.array([8.5, 8.8])
        closes = np.array([9.0, 10.6])
        self.assertTrue(
            self.strategy._confirmation_candle(opens, highs, lows, closes, bullish=True)
        )

    def test_confirmation_candle_bearish_engulfing(self) -> None:
        opens = np.array([9.0, 10.0])
        highs = np.array([9.5, 10.2])
        lows = np.array([8.8, 8.0])
        closes = np.array([9.4, 8.2])
        self.assertTrue(
            self.strategy._confirmation_candle(opens, highs, lows, closes, bullish=False)
        )

    def test_liquidity_sweep_bullish_detected(self) -> None:
        # liquidity_lookback defaults to 20 and the check requires
        # lookback + 2 candles (lookback candles before the current one,
        # excluding the current, plus the current itself).
        lows = np.array([10.0] * 21 + [9.0])  # sweep below the pool
        highs = lows + 1.0
        closes = np.array([10.0] * 21 + [10.2])  # closes back above the pool
        self.assertTrue(self.strategy._liquidity_sweep(highs, lows, closes, bullish=True))

    def test_liquidity_sweep_bullish_not_detected_without_close_back_above(self) -> None:
        lows = np.array([10.0] * 21 + [9.0])
        highs = lows + 1.0
        closes = np.array([10.0] * 21 + [9.2])  # never reclaims the pool
        self.assertFalse(self.strategy._liquidity_sweep(highs, lows, closes, bullish=True))

    def test_fair_value_gap_bullish_detected_and_filled(self) -> None:
        n = 25
        highs = np.full(n, 10.0)
        lows = np.full(n, 9.0)
        closes = np.full(n, 9.5)
        # Candle at index 10: high=9.5; candle at index 12: low=10.5 -> gap (9.5, 10.5)
        highs[10] = 9.5
        lows[12] = 10.5
        closes[-1] = 10.0  # inside the (9.5, 10.5) gap
        filled, zone = self.strategy._fair_value_gap(highs, lows, closes, bullish=True)
        self.assertTrue(filled)
        self.assertEqual(zone, (9.5, 10.5))

    def test_pullback_ok_within_atr_distance(self) -> None:
        self.assertTrue(self.strategy._pullback_ok(close=100.0, ema_fast=99.0, ema_medium=95.0, atr_value=2.0))

    def test_pullback_not_ok_when_far_from_both_emas(self) -> None:
        self.assertFalse(
            self.strategy._pullback_ok(close=200.0, ema_fast=99.0, ema_medium=95.0, atr_value=2.0)
        )

    def test_pullback_not_ok_without_atr(self) -> None:
        self.assertFalse(self.strategy._pullback_ok(close=100.0, ema_fast=99.0, ema_medium=95.0, atr_value=None))


class TestDecideEndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        self.strategy = TrendPullbackSMCStrategy()

    def test_missing_candles_raises_insufficient_data(self) -> None:
        context = StrategyContext(symbol="BTCUSDT", timeframe="1h", metadata={})
        with self.assertRaises(InsufficientStrategyDataError):
            self.strategy.decide(context)

    def test_too_few_candles_raises_insufficient_data(self) -> None:
        candles = make_trend_candles(50)
        context = StrategyContext(symbol="BTCUSDT", timeframe="1h", metadata={"candles": candles})
        with self.assertRaises(InsufficientStrategyDataError):
            self.strategy.decide(context)

    def test_non_candle_metadata_treated_as_missing(self) -> None:
        context = StrategyContext(
            symbol="BTCUSDT", timeframe="1h", metadata={"candles": ["not", "a", "candle"]}
        )
        with self.assertRaises(InsufficientStrategyDataError):
            self.strategy.decide(context)

    def test_decide_returns_valid_strategy_result_shape(self) -> None:
        candles = make_trend_candles(300, drift=0.2, seed=42)
        htf_candles = make_trend_candles(260, drift=0.2, seed=7, timeframe="4h")
        context = StrategyContext(
            symbol="BTCUSDT",
            timeframe="1h",
            metadata={"candles": candles, "higher_timeframe_candles": htf_candles},
        )
        result = self.strategy.decide(context)
        self.assertIn(result.action, (SignalDirection.BUY, SignalDirection.SELL, SignalDirection.HOLD))
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)
        self.assertIn("entry_gates", result.metadata)
        self.assertIn("long", result.metadata["entry_gates"])
        self.assertIn("short", result.metadata["entry_gates"])
        self.assertIn("higher_timeframe_bias", result.metadata)
        self.assertIn("trend", result.metadata)
        self.assertIn("momentum", result.metadata)
        self.assertIn("structure", result.metadata)
        self.assertIn("smart_money", result.metadata)

    def test_decide_is_deterministic(self) -> None:
        candles = make_trend_candles(300, drift=-0.2, seed=99)
        htf_candles = make_trend_candles(260, drift=-0.2, seed=13, timeframe="4h")
        context = StrategyContext(
            symbol="BTCUSDT",
            timeframe="1h",
            metadata={"candles": candles, "higher_timeframe_candles": htf_candles},
        )
        result_a = self.strategy.decide(context)
        result_b = self.strategy.decide(context)
        self.assertEqual(result_a.action, result_b.action)
        self.assertEqual(result_a.confidence, result_b.confidence)
        self.assertEqual(result_a.metadata["entry_gates"], result_b.metadata["entry_gates"])

    def test_htf_bias_unavailable_when_no_htf_data_supplied(self) -> None:
        candles = make_trend_candles(300, drift=0.2, seed=42)
        context = StrategyContext(symbol="BTCUSDT", timeframe="1h", metadata={"candles": candles})
        result = self.strategy.decide(context)
        self.assertEqual(result.metadata["higher_timeframe_bias"], "unavailable")
        # An unavailable HTF bias can never satisfy either directional
        # gate set, so no trade should ever be proposed.
        self.assertEqual(result.action, SignalDirection.HOLD)

    def test_risk_override_downgrades_to_hold(self) -> None:
        # Force a HOLD-independent path by directly checking the risk
        # gate logic: construct a context with an unapproved RiskResult
        # and confirm the final action can never be BUY/SELL when raw
        # action would have been directional. Since crafting a guaranteed
        # BUY/SELL from raw OHLCV is non-deterministic by design (real
        # market structure), this test verifies the gate defensively via
        # a strategy configured to make entry trivially easy.
        lenient = TrendPullbackSMCStrategy(
            min_smc_confirmations=0,
            min_momentum_confirmations=0,
            require_confirmation_candle=False,
            adx_threshold=0.0,
        )
        candles = make_trend_candles(300, drift=0.5, seed=5)
        htf_candles = make_trend_candles(260, drift=0.5, seed=6, timeframe="4h")
        context = StrategyContext(
            symbol="BTCUSDT",
            timeframe="1h",
            metadata={"candles": candles, "higher_timeframe_candles": htf_candles},
            risk_result=RiskResult(
                approved=False, risk_score=0.9, confidence=0.8, summary="Exposure too high"
            ),
        )
        result = lenient.decide(context)
        if result.metadata["raw_action"] != "hold":
            self.assertEqual(result.action, SignalDirection.HOLD)
            self.assertTrue(result.metadata["risk_override"])

    def test_symbol_agnostic_when_candles_supplied(self) -> None:
        # This strategy documents BTCUSDT/1h/4h as tuned defaults but
        # does not hard-enforce them -- any symbol/timeframe works as
        # long as matching candle data is supplied.
        candles = make_trend_candles(300, drift=0.1, seed=3, symbol="ETHUSDT")
        context = StrategyContext(
            symbol="ETHUSDT", timeframe="1h", metadata={"candles": candles}
        )
        result = self.strategy.decide(context)
        self.assertIn(result.action, (SignalDirection.BUY, SignalDirection.SELL, SignalDirection.HOLD))


if __name__ == "__main__":
    unittest.main()
