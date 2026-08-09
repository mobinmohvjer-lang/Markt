"""
strategies/trend_pullback_smc_strategy.py

Defines `TrendPullbackSMCStrategy`: a concrete `BaseStrategy` implementing
a BTCUSDT-oriented Trend Following + Pullback + Price Action + Smart
Money Concepts (SMC) strategy, built entirely on the existing Strategy
Engine foundation (`BaseStrategy`, `StrategyContext`, `StrategyResult`)
introduced in `strategies/base_strategy.py`/`context.py`/`result.py`.

Scope (Phase 1 -- core strategy layer only)
--------------------------------------------
This module implements *decision logic only*: `decide(context) ->
StrategyResult`. It does **not** implement, and deliberately excludes:
    - An order-execution engine or broker/exchange integration.
    - Live trading / scheduling / any wall-clock-driven behavior.
    - Parameter optimization or fitting of any kind.
    - Any UI, CLI, or reporting surface.
Those remain out of scope, per this milestone's explicit instructions,
for a future `execution/` concrete engine and/or `app/`-layer use case.

Why this strategy is self-sufficient (raw candles in, decision out)
----------------------------------------------------------------------
Every existing concrete strategy (`BasicStrategy`) decides from an
already-computed `analysis.result.AnalysisResult`. That works for a
generic score-threshold strategy, but EMA-stack alignment/slope, RSI
zones, MACD zero-line filtering, ADX/DI, swing-structure (HH/HL/LH/LL,
BOS, CHOCH), and Smart Money concepts (liquidity sweeps, order blocks,
fair value gaps) all require the *raw* OHLCV candle sequence, not a
single pre-scored value -- and neither `StrategyContext` nor
`backtesting.basic_backtester.BasicBacktester` supplies indicator data
today (`BasicBacktester` builds an empty `analysis_results` list by
design; see `PROJECT_STATE.md`). Rather than changing that shared
context/backtester (which would risk breaking every existing strategy
and test), this strategy reads its own raw candle history from
`StrategyContext.metadata` -- the exact extension point `StrategyContext`
already documents as free-form/caller-supplied, and the same mechanism
`backtesting.basic_backtester.BasicBacktester` already uses to expose
the current candle (`metadata["candle"]`) and `strategies.basic_strategy.
BasicStrategy` already uses to opt in to its own indicator-based entry
filters (`metadata["indicators"]`). No existing class's schema changes.

Expected `StrategyContext.metadata` shape (all keys configurable via
the constructor, see `Attributes` below):
    - `metadata[candles_metadata_key]` (default `"candles"`, **required**):
      a chronologically ordered (oldest -> newest) `list[core.entities.
      candle.Candle]` for `context.symbol`/`context.timeframe` -- the
      main/execution timeframe (1H by default for this strategy).
    - `metadata[htf_candles_metadata_key]` (default
      `"higher_timeframe_candles"`, **optional**): the same shape, for
      the higher timeframe (4H by default) used for trend-bias
      confirmation. If absent, this strategy falls back to looking for
      an `AnalysisResult` on `context.analysis_results` whose
      `.timeframe == self.higher_timeframe`; if neither is present,
      the higher-timeframe bias is treated as unavailable, which blocks
      new entries (see "Entry logic" below) without raising -- the same
      "absence only blocks/lowers, never raises" convention every other
      engine in this repository already follows for *optional* inputs.

Only the main-timeframe candle series is a hard requirement: without it
nothing in this module can be computed, so its absence (or having fewer
than `min_candles_required` candles) raises `InsufficientStrategyDataError`,
mirroring `BasicStrategy` raising the same exception when its required
`AnalysisResult` is missing.

What each requirement section maps to (all configurable, see
`__init__`):
    1. Trend       -- `_compute_trend()`: EMA 20/50/100/200 (via
                       `indicators.ema.EMA`, reused as-is), alignment,
                       slope, and EMA200 trend direction.
    2. Momentum    -- `_compute_momentum()`: RSI 14 (`indicators.rsi.RSI`)
                       + zones, MACD 12/26/9 (`indicators.macd.MACD`)
                       + histogram + zero-line filter, ADX 14
                       (`indicators.adx.ADX`) trend-strength filter +
                       +DI/-DI confirmation.
    3. Price action -- `_compute_structure()`/`_confirmation_candle()`:
                       fractal swing-point detection -> HH/HL/LH/LL
                       classification -> BOS/CHOCH, plus a confirmation
                       candle check (engulfing / pin bar / strong body).
    4. Smart Money  -- `_liquidity_sweep()`/`_order_block()`/
                       `_fair_value_gap()`: liquidity-sweep, order-block
                       retest, and fair-value-gap-fill detection.
    5. Entry logic  -- `decide()`: combines all of the above into
                       LONG/SHORT/no-trade per the exact long/short
                       condition sets in the module's requirements.

Every intermediate value is recorded in `StrategyResult.metadata` for
full traceability, the same convention `BasicStrategy` already
establishes. `StrategyResult` itself carries no new fields -- this
strategy reuses it exactly as it already exists.

Determinism
-----------
No randomness, no wall-clock reads, no network/database/broker I/O:
`decide()` is a pure function of `StrategyContext` and this instance's
constructor configuration -- the same determinism guarantee every
other concrete strategy/analyzer/risk-manager in this repository holds.

Boundaries
----------
No AI. No order placement, no position sizing, no stop-loss/take-profit
computation (those remain `strategies.risk_management`'s job -- this
strategy's output is a directional decision only, exactly like
`BasicStrategy`'s). No portfolio management. No optimization. No change
to `strategies.base_strategy`/`context`/`result`/`exceptions`/`utils`,
`strategies.basic_strategy`, `strategies.aggregator`,
`strategies.risk_management`, `strategies.portfolio_management`,
`analysis/`, `signals/`, `backtesting/`, or `core/` -- all consumed
exactly as they already exist. Only `strategies/__init__.py` is
additionally updated (to export this class), the same footprint
`BasicStrategy`'s own introduction left.
"""

from __future__ import annotations

import math
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

from core.entities.candle import Candle
from core.enums import SignalDirection

from indicators.adx import ADX
from indicators.atr import ATR
from indicators.ema import EMA
from indicators.macd import MACD
from indicators.rsi import RSI

from strategies.base_strategy import BaseStrategy
from strategies.context import StrategyContext
from strategies.exceptions import (
    InsufficientStrategyDataError,
    StrategyConfigurationError,
)
from strategies.result import StrategyResult
from strategies.utils import clip

# ----------------------------------------------------------------------
# Defaults -- every one of these is a constructor parameter below; the
# module-level constants only document/centralize the out-of-the-box
# configuration (mirroring `strategies/basic_strategy.py`'s convention).
# ----------------------------------------------------------------------

DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_TIMEFRAME = "1h"
DEFAULT_HIGHER_TIMEFRAME = "4h"

DEFAULT_CANDLES_METADATA_KEY = "candles"
DEFAULT_HTF_CANDLES_METADATA_KEY = "higher_timeframe_candles"

# -- Trend (EMA stack) --
DEFAULT_EMA_FAST = 20
DEFAULT_EMA_MEDIUM = 50
DEFAULT_EMA_SLOW = 100
DEFAULT_EMA_TREND = 200
DEFAULT_EMA_SLOPE_LOOKBACK = 5
DEFAULT_HTF_EMA_TREND = 200

# -- Momentum --
DEFAULT_RSI_PERIOD = 14
DEFAULT_RSI_OVERSOLD = 30.0
DEFAULT_RSI_OVERBOUGHT = 70.0
DEFAULT_RSI_PULLBACK_LOW = 40.0
DEFAULT_RSI_PULLBACK_HIGH = 60.0
DEFAULT_MACD_FAST = 12
DEFAULT_MACD_SLOW = 26
DEFAULT_MACD_SIGNAL = 9
DEFAULT_ADX_PERIOD = 14
DEFAULT_ADX_THRESHOLD = 25.0
DEFAULT_MIN_MOMENTUM_CONFIRMATIONS = 1  # of {rsi_zone, macd_zero_line}

# -- Price action (swing structure) --
DEFAULT_SWING_STRENGTH = 2
DEFAULT_STRUCTURE_LOOKBACK = 60
DEFAULT_REQUIRE_CONFIRMATION_CANDLE = True
DEFAULT_CONFIRMATION_BODY_RATIO = 0.5
DEFAULT_CONFIRMATION_WICK_RATIO = 0.5

# -- Smart Money Concepts --
DEFAULT_ATR_PERIOD = 14
DEFAULT_LIQUIDITY_LOOKBACK = 20
DEFAULT_ORDER_BLOCK_LOOKBACK = 20
DEFAULT_ORDER_BLOCK_IMPULSE_ATR_MULTIPLIER = 1.0
DEFAULT_FVG_LOOKBACK = 20
DEFAULT_MIN_SMC_CONFIRMATIONS = 1  # of {liquidity_sweep, order_block, fvg}

# -- Pullback --
DEFAULT_PULLBACK_MAX_ATR_DISTANCE = 1.5

# -- Higher-timeframe bias --
DEFAULT_HTF_SCORE_THRESHOLD = 0.15  # used only for the AnalysisResult fallback

#: Buffer of extra candles required on top of the largest single lookback,
#: so slope/structure calculations always have valid (non-NaN) inputs.
_WARMUP_BUFFER = 10


class TrendPullbackSMCStrategy(BaseStrategy):
    """
    Trend Following + Pullback + Price Action + Smart Money `BaseStrategy`.

    See the module docstring for the full requirement -> implementation
    mapping and the expected `StrategyContext.metadata` shape. All
    thresholds/periods below are configurable at construction time;
    defaults are tuned for BTCUSDT on a 1H main timeframe with a 4H
    higher-timeframe bias filter, per this strategy's design brief.

    Attributes (all keyword-only, all validated at construction time):
        name: Human-readable strategy name (see `BaseStrategy`).
        symbol / timeframe: Documented default trading pair/timeframe
            this instance is tuned for. Not enforced against
            `StrategyContext.symbol`/`.timeframe` (a caller may still
            run this strategy against any symbol/timeframe whose candle
            data it supplies) -- purely descriptive/traceability, the
            same non-enforcing role `config.config.DEFAULT_SYMBOL`/
            `DEFAULT_TIMEFRAME` already play elsewhere in this project.
        higher_timeframe: Timeframe identifier (e.g. `"4h"`) this
            strategy looks for higher-timeframe bias data under, either
            via `metadata[htf_candles_metadata_key]` or a matching
            `AnalysisResult.timeframe` in `context.analysis_results`.
        candles_metadata_key / htf_candles_metadata_key: `StrategyContext.
            metadata` keys this strategy reads candle lists from. See
            module docstring.
        ema_fast_period / ema_medium_period / ema_slow_period /
            ema_trend_period: The four EMA periods forming the trend
            stack (default 20/50/100/200).
        ema_slope_lookback: Number of candles back used to measure
            EMA200 slope (`(now - lookback_ago) / lookback`).
        htf_ema_trend_period: EMA period used for the higher-timeframe
            candle-based bias check (default 200, same as the main
            timeframe's trend EMA).
        rsi_period / rsi_oversold / rsi_overbought / rsi_pullback_low /
            rsi_pullback_high: RSI 14 configuration and zone
            boundaries.
        macd_fast_period / macd_slow_period / macd_signal_period: MACD
            12/26/9 configuration.
        adx_period / adx_threshold: ADX 14 configuration and the
            trend-strength filter threshold (`ADX >= adx_threshold`).
        min_momentum_confirmations: Minimum number, out of
            {RSI zone, MACD zero-line + histogram}, required in
            addition to the hard ADX/DI gate (default 1 of 2).
        swing_strength: Fractal half-window size for swing-point
            detection (a candle is a swing high/low if it is the
            extreme of `2 * swing_strength + 1` candles centered on it).
        structure_lookback: How many recent candles are scanned for
            swing points when classifying HH/HL/LH/LL and BOS/CHOCH.
        require_confirmation_candle: Whether a confirmation candle
            (engulfing / pin bar / strong body) is a hard entry
            requirement (default `True`).
        confirmation_body_ratio / confirmation_wick_ratio: Thresholds
            (fraction of candle range) used by the confirmation-candle
            check.
        atr_period: ATR period used both for the pullback distance
            check and the order-block impulsive-move check.
        liquidity_lookback: Candles scanned for a liquidity pool
            (recent swing low/high) when detecting a liquidity sweep.
        order_block_lookback / order_block_impulse_atr_multiplier:
            Candles scanned for a qualifying order block, and how large
            (in ATR multiples) the following impulsive move must be.
        fvg_lookback: Candles scanned for an unfilled fair value gap.
        min_smc_confirmations: Minimum number, out of {liquidity sweep,
            order-block retest, FVG fill}, required for SMC confirmation
            (default 1 of 3).
        pullback_max_atr_distance: Maximum distance (in ATR multiples)
            from EMA20 or EMA50 for price to still count as "in the
            pullback zone".
        htf_score_threshold: Only used for the `AnalysisResult`-fallback
            higher-timeframe bias (see module docstring); an
            `AnalysisResult.score` beyond `+/- htf_score_threshold`
            counts as bullish/bearish bias.
        min_candles_required: Minimum main-timeframe candle count this
            strategy needs; computed automatically from the configured
            periods/lookbacks if not supplied.

    Raises:
        StrategyConfigurationError: If any parameter is not a valid
            type or falls outside its documented range.
    """

    def __init__(
        self,
        *,
        name: Optional[str] = None,
        symbol: str = DEFAULT_SYMBOL,
        timeframe: str = DEFAULT_TIMEFRAME,
        higher_timeframe: str = DEFAULT_HIGHER_TIMEFRAME,
        candles_metadata_key: str = DEFAULT_CANDLES_METADATA_KEY,
        htf_candles_metadata_key: str = DEFAULT_HTF_CANDLES_METADATA_KEY,
        # Trend
        ema_fast_period: int = DEFAULT_EMA_FAST,
        ema_medium_period: int = DEFAULT_EMA_MEDIUM,
        ema_slow_period: int = DEFAULT_EMA_SLOW,
        ema_trend_period: int = DEFAULT_EMA_TREND,
        ema_slope_lookback: int = DEFAULT_EMA_SLOPE_LOOKBACK,
        htf_ema_trend_period: int = DEFAULT_HTF_EMA_TREND,
        # Momentum
        rsi_period: int = DEFAULT_RSI_PERIOD,
        rsi_oversold: float = DEFAULT_RSI_OVERSOLD,
        rsi_overbought: float = DEFAULT_RSI_OVERBOUGHT,
        rsi_pullback_low: float = DEFAULT_RSI_PULLBACK_LOW,
        rsi_pullback_high: float = DEFAULT_RSI_PULLBACK_HIGH,
        macd_fast_period: int = DEFAULT_MACD_FAST,
        macd_slow_period: int = DEFAULT_MACD_SLOW,
        macd_signal_period: int = DEFAULT_MACD_SIGNAL,
        adx_period: int = DEFAULT_ADX_PERIOD,
        adx_threshold: float = DEFAULT_ADX_THRESHOLD,
        min_momentum_confirmations: int = DEFAULT_MIN_MOMENTUM_CONFIRMATIONS,
        # Price action
        swing_strength: int = DEFAULT_SWING_STRENGTH,
        structure_lookback: int = DEFAULT_STRUCTURE_LOOKBACK,
        require_confirmation_candle: bool = DEFAULT_REQUIRE_CONFIRMATION_CANDLE,
        confirmation_body_ratio: float = DEFAULT_CONFIRMATION_BODY_RATIO,
        confirmation_wick_ratio: float = DEFAULT_CONFIRMATION_WICK_RATIO,
        # Smart Money
        atr_period: int = DEFAULT_ATR_PERIOD,
        liquidity_lookback: int = DEFAULT_LIQUIDITY_LOOKBACK,
        order_block_lookback: int = DEFAULT_ORDER_BLOCK_LOOKBACK,
        order_block_impulse_atr_multiplier: float = DEFAULT_ORDER_BLOCK_IMPULSE_ATR_MULTIPLIER,
        fvg_lookback: int = DEFAULT_FVG_LOOKBACK,
        min_smc_confirmations: int = DEFAULT_MIN_SMC_CONFIRMATIONS,
        # Pullback
        pullback_max_atr_distance: float = DEFAULT_PULLBACK_MAX_ATR_DISTANCE,
        # Higher-timeframe bias fallback
        htf_score_threshold: float = DEFAULT_HTF_SCORE_THRESHOLD,
        # Data sufficiency
        min_candles_required: Optional[int] = None,
    ) -> None:
        super().__init__(name=name)

        self.symbol = self._validate_str(symbol, name="symbol")
        self.timeframe = self._validate_str(timeframe, name="timeframe")
        self.higher_timeframe = self._validate_str(higher_timeframe, name="higher_timeframe")
        self.candles_metadata_key = self._validate_str(
            candles_metadata_key, name="candles_metadata_key"
        )
        self.htf_candles_metadata_key = self._validate_str(
            htf_candles_metadata_key, name="htf_candles_metadata_key"
        )

        self.ema_fast_period = self._validate_pos_int(ema_fast_period, name="ema_fast_period")
        self.ema_medium_period = self._validate_pos_int(ema_medium_period, name="ema_medium_period")
        self.ema_slow_period = self._validate_pos_int(ema_slow_period, name="ema_slow_period")
        self.ema_trend_period = self._validate_pos_int(ema_trend_period, name="ema_trend_period")
        if not (
            self.ema_fast_period < self.ema_medium_period < self.ema_slow_period < self.ema_trend_period
        ):
            raise StrategyConfigurationError(
                "EMA periods must satisfy ema_fast_period < ema_medium_period < "
                f"ema_slow_period < ema_trend_period, got {self.ema_fast_period}, "
                f"{self.ema_medium_period}, {self.ema_slow_period}, {self.ema_trend_period}"
            )
        self.ema_slope_lookback = self._validate_pos_int(
            ema_slope_lookback, name="ema_slope_lookback"
        )
        self.htf_ema_trend_period = self._validate_pos_int(
            htf_ema_trend_period, name="htf_ema_trend_period"
        )

        self.rsi_period = self._validate_pos_int(rsi_period, name="rsi_period")
        self.rsi_oversold = self._validate_range(rsi_oversold, name="rsi_oversold", low=0.0, high=100.0)
        self.rsi_overbought = self._validate_range(
            rsi_overbought, name="rsi_overbought", low=0.0, high=100.0
        )
        self.rsi_pullback_low = self._validate_range(
            rsi_pullback_low, name="rsi_pullback_low", low=0.0, high=100.0
        )
        self.rsi_pullback_high = self._validate_range(
            rsi_pullback_high, name="rsi_pullback_high", low=0.0, high=100.0
        )
        if not (self.rsi_oversold < self.rsi_pullback_low <= self.rsi_pullback_high < self.rsi_overbought):
            raise StrategyConfigurationError(
                "RSI zones must satisfy rsi_oversold < rsi_pullback_low <= "
                "rsi_pullback_high < rsi_overbought, got "
                f"{self.rsi_oversold}, {self.rsi_pullback_low}, "
                f"{self.rsi_pullback_high}, {self.rsi_overbought}"
            )

        self.macd_fast_period = self._validate_pos_int(macd_fast_period, name="macd_fast_period")
        self.macd_slow_period = self._validate_pos_int(macd_slow_period, name="macd_slow_period")
        self.macd_signal_period = self._validate_pos_int(
            macd_signal_period, name="macd_signal_period"
        )
        if self.macd_slow_period <= self.macd_fast_period:
            raise StrategyConfigurationError(
                f"macd_slow_period ({self.macd_slow_period}) must be greater than "
                f"macd_fast_period ({self.macd_fast_period})"
            )

        self.adx_period = self._validate_pos_int(adx_period, name="adx_period")
        self.adx_threshold = self._validate_range(
            adx_threshold, name="adx_threshold", low=0.0, high=100.0
        )
        self.min_momentum_confirmations = self._validate_range_int(
            min_momentum_confirmations, name="min_momentum_confirmations", low=0, high=2
        )

        self.swing_strength = self._validate_pos_int(swing_strength, name="swing_strength")
        self.structure_lookback = self._validate_pos_int(
            structure_lookback, name="structure_lookback"
        )
        self.require_confirmation_candle = bool(require_confirmation_candle)
        self.confirmation_body_ratio = self._validate_range(
            confirmation_body_ratio, name="confirmation_body_ratio", low=0.0, high=1.0
        )
        self.confirmation_wick_ratio = self._validate_range(
            confirmation_wick_ratio, name="confirmation_wick_ratio", low=0.0, high=1.0
        )

        self.atr_period = self._validate_pos_int(atr_period, name="atr_period")
        self.liquidity_lookback = self._validate_pos_int(
            liquidity_lookback, name="liquidity_lookback"
        )
        self.order_block_lookback = self._validate_pos_int(
            order_block_lookback, name="order_block_lookback"
        )
        self.order_block_impulse_atr_multiplier = self._validate_positive_number(
            order_block_impulse_atr_multiplier, name="order_block_impulse_atr_multiplier"
        )
        self.fvg_lookback = self._validate_pos_int(fvg_lookback, name="fvg_lookback")
        self.min_smc_confirmations = self._validate_range_int(
            min_smc_confirmations, name="min_smc_confirmations", low=0, high=3
        )

        self.pullback_max_atr_distance = self._validate_positive_number(
            pullback_max_atr_distance, name="pullback_max_atr_distance"
        )

        self.htf_score_threshold = self._validate_range(
            htf_score_threshold, name="htf_score_threshold", low=0.0, high=1.0
        )

        computed_min = (
            max(
                self.ema_trend_period,
                self.macd_slow_period + self.macd_signal_period,
                self.adx_period * 2,
                self.structure_lookback,
                self.liquidity_lookback,
                self.order_block_lookback,
                self.fvg_lookback,
            )
            + self.ema_slope_lookback
            + _WARMUP_BUFFER
        )
        if min_candles_required is None:
            self.min_candles_required = computed_min
        else:
            self.min_candles_required = self._validate_pos_int(
                min_candles_required, name="min_candles_required"
            )
            if self.min_candles_required < computed_min:
                raise StrategyConfigurationError(
                    f"min_candles_required ({self.min_candles_required}) is too small for the "
                    f"configured periods/lookbacks; must be >= {computed_min}"
                )

    # ------------------------------------------------------------------
    # Construction-time validation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_str(value: Any, *, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise StrategyConfigurationError(f"{name} must be a non-empty string, got {value!r}")
        return value

    @staticmethod
    def _validate_pos_int(value: Any, *, name: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise StrategyConfigurationError(f"{name} must be a positive int, got {value!r}")
        return value

    @staticmethod
    def _validate_range_int(value: Any, *, name: str, low: int, high: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not (low <= value <= high):
            raise StrategyConfigurationError(
                f"{name} must be an int within [{low}, {high}], got {value!r}"
            )
        return value

    @staticmethod
    def _validate_range(value: Any, *, name: str, low: float, high: float) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise StrategyConfigurationError(f"{name} must be numeric, got {type(value).__name__}")
        numeric_value = float(value)
        if not math.isfinite(numeric_value) or not (low <= numeric_value <= high):
            raise StrategyConfigurationError(
                f"{name} must be within [{low}, {high}], got {numeric_value}"
            )
        return numeric_value

    @staticmethod
    def _validate_positive_number(value: Any, *, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise StrategyConfigurationError(f"{name} must be numeric, got {type(value).__name__}")
        numeric_value = float(value)
        if not math.isfinite(numeric_value) or numeric_value <= 0.0:
            raise StrategyConfigurationError(f"{name} must be > 0.0, got {numeric_value}")
        return numeric_value

    # ------------------------------------------------------------------
    # BaseStrategy API
    # ------------------------------------------------------------------
    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)

        candles = self._extract_candles(context, self.candles_metadata_key)
        if candles is None or len(candles) < self.min_candles_required:
            raise InsufficientStrategyDataError(
                f"{self.name} requires at least {self.min_candles_required} chronologically "
                f"ordered candles under StrategyContext.metadata[{self.candles_metadata_key!r}] "
                f"for {context.symbol}/{context.timeframe}, got "
                f"{0 if candles is None else len(candles)}."
            )

        opens, highs, lows, closes, _volumes = self._candles_to_arrays(candles)
        frame = pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes})

        trend = self._compute_trend(frame, closes)
        momentum = self._compute_momentum(frame)
        atr_value = self._latest_atr(frame)
        structure = self._compute_structure(highs, lows, closes)
        confirmation_candle_bullish = self._confirmation_candle(opens, highs, lows, closes, bullish=True)
        confirmation_candle_bearish = self._confirmation_candle(opens, highs, lows, closes, bullish=False)
        pullback_bullish = self._pullback_ok(
            closes[-1], trend["ema_fast"], trend["ema_medium"], atr_value
        )
        # Pullback is a symmetric distance-from-EMA check -- the same
        # zone serves both directions, direction is decided elsewhere.
        pullback_bearish = pullback_bullish

        smc_bullish = self._compute_smc(opens, highs, lows, closes, atr_value, bullish=True)
        smc_bearish = self._compute_smc(opens, highs, lows, closes, atr_value, bullish=False)

        htf_bias, htf_detail = self._resolve_htf_bias(context)

        long_gates = self._evaluate_gates(
            direction="long",
            trend=trend,
            momentum=momentum,
            structure=structure,
            pullback_ok=pullback_bullish,
            confirmation_candle_ok=confirmation_candle_bullish,
            smc=smc_bullish,
            htf_bias=htf_bias,
        )
        short_gates = self._evaluate_gates(
            direction="short",
            trend=trend,
            momentum=momentum,
            structure=structure,
            pullback_ok=pullback_bearish,
            confirmation_candle_ok=confirmation_candle_bearish,
            smc=smc_bearish,
            htf_bias=htf_bias,
        )

        long_ready = all(long_gates.values())
        short_ready = all(short_gates.values())

        if long_ready and not short_ready:
            raw_action = SignalDirection.BUY
        elif short_ready and not long_ready:
            raw_action = SignalDirection.SELL
        else:
            # Neither side fully qualifies, or (structurally impossible
            # in practice, since long/short gates are mutually
            # exclusive on trend direction, but handled defensively
            # regardless) both do -- no trade either way.
            raw_action = SignalDirection.HOLD

        # -------- risk gate (same convention as BasicStrategy) --------
        risk_result = context.risk_result
        risk_available = context.has_risk_result()
        risk_override = False
        final_action = raw_action
        if risk_available and raw_action != SignalDirection.HOLD and not risk_result.approved:
            risk_override = True
            final_action = SignalDirection.HOLD

        confidence = self._compute_confidence(
            final_action=final_action,
            gates=long_gates if raw_action == SignalDirection.BUY else short_gates,
            trend=trend,
            momentum=momentum,
            smc=smc_bullish if raw_action == SignalDirection.BUY else smc_bearish,
            htf_detail=htf_detail,
            risk_available=risk_available,
            risk_result=risk_result,
        )

        summary = self._build_summary(
            context=context,
            final_action=final_action,
            raw_action=raw_action,
            confidence=confidence,
            risk_override=risk_override,
            htf_bias=htf_bias,
        )

        metadata = self._build_metadata(
            context=context,
            trend=trend,
            momentum=momentum,
            structure=structure,
            atr_value=atr_value,
            pullback_bullish=pullback_bullish,
            confirmation_candle_bullish=confirmation_candle_bullish,
            confirmation_candle_bearish=confirmation_candle_bearish,
            smc_bullish=smc_bullish,
            smc_bearish=smc_bearish,
            htf_bias=htf_bias,
            htf_detail=htf_detail,
            long_gates=long_gates,
            short_gates=short_gates,
            raw_action=raw_action,
            final_action=final_action,
            risk_override=risk_override,
            risk_available=risk_available,
            confidence=confidence,
        )

        return self._build_result(
            action=final_action,
            confidence=confidence,
            summary=summary,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Data extraction
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_candles(context: StrategyContext, key: str) -> Optional[Sequence[Candle]]:
        raw = context.metadata.get(key)
        if not isinstance(raw, list) or not raw:
            return None
        if not all(isinstance(item, Candle) for item in raw):
            return None
        return raw

    @staticmethod
    def _candles_to_arrays(candles: Sequence[Candle]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        opens = np.array([float(c.open) for c in candles], dtype=float)
        highs = np.array([float(c.high) for c in candles], dtype=float)
        lows = np.array([float(c.low) for c in candles], dtype=float)
        closes = np.array([float(c.close) for c in candles], dtype=float)
        volumes = np.array([float(c.volume) for c in candles], dtype=float)
        return opens, highs, lows, closes, volumes

    # ------------------------------------------------------------------
    # 1. Trend (EMA 20/50/100/200, alignment, slope, EMA200 direction)
    # ------------------------------------------------------------------
    def _compute_trend(self, frame: pd.DataFrame, closes: np.ndarray) -> dict[str, Any]:
        ema_fast_arr = EMA(self.ema_fast_period).calculate(frame, column="close").values
        ema_medium_arr = EMA(self.ema_medium_period).calculate(frame, column="close").values
        ema_slow_arr = EMA(self.ema_slow_period).calculate(frame, column="close").values
        ema_trend_arr = EMA(self.ema_trend_period).calculate(frame, column="close").values

        ema_fast, ema_medium, ema_slow, ema_trend = (
            ema_fast_arr[-1],
            ema_medium_arr[-1],
            ema_slow_arr[-1],
            ema_trend_arr[-1],
        )

        alignment = self._ema_alignment(ema_fast, ema_medium, ema_slow, ema_trend)
        slope = self._slope(ema_trend_arr, self.ema_slope_lookback)
        price_above_trend = np.isfinite(ema_trend) and closes[-1] > ema_trend
        price_below_trend = np.isfinite(ema_trend) and closes[-1] < ema_trend

        return {
            "ema_fast": ema_fast,
            "ema_medium": ema_medium,
            "ema_slow": ema_slow,
            "ema_trend": ema_trend,
            "alignment": alignment,
            "slope": slope,
            "slope_bullish": slope is not None and slope > 0,
            "slope_bearish": slope is not None and slope < 0,
            "price_above_trend": price_above_trend,
            "price_below_trend": price_below_trend,
            "bullish": alignment == "bullish" and price_above_trend and (slope is not None and slope > 0),
            "bearish": alignment == "bearish" and price_below_trend and (slope is not None and slope < 0),
        }

    @staticmethod
    def _ema_alignment(ema_fast: float, ema_medium: float, ema_slow: float, ema_trend: float) -> str:
        values = (ema_fast, ema_medium, ema_slow, ema_trend)
        if not all(np.isfinite(v) for v in values):
            return "unknown"
        if ema_fast > ema_medium > ema_slow > ema_trend:
            return "bullish"
        if ema_fast < ema_medium < ema_slow < ema_trend:
            return "bearish"
        return "mixed"

    @staticmethod
    def _slope(arr: np.ndarray, lookback: int) -> Optional[float]:
        if len(arr) <= lookback:
            return None
        now, prior = arr[-1], arr[-1 - lookback]
        if not (np.isfinite(now) and np.isfinite(prior)):
            return None
        return float((now - prior) / lookback)

    # ------------------------------------------------------------------
    # 2. Momentum (RSI zones, MACD + zero line, ADX + DI)
    # ------------------------------------------------------------------
    def _compute_momentum(self, frame: pd.DataFrame) -> dict[str, Any]:
        rsi_arr = RSI(self.rsi_period).calculate(frame, column="close").values
        rsi = rsi_arr[-1]
        rsi_zone_bullish = np.isfinite(rsi) and self.rsi_pullback_low <= rsi <= self.rsi_pullback_high
        rsi_overbought = np.isfinite(rsi) and rsi >= self.rsi_overbought
        rsi_oversold = np.isfinite(rsi) and rsi <= self.rsi_oversold

        macd_result = MACD(
            fast_period=self.macd_fast_period,
            slow_period=self.macd_slow_period,
            signal_period=self.macd_signal_period,
        ).calculate(frame, column="close")
        macd_line = macd_result.values["macd"]
        histogram = macd_result.values["histogram"]
        macd_now, macd_prior = macd_line[-1], macd_line[-2] if len(macd_line) > 1 else np.nan
        hist_now, hist_prior = histogram[-1], histogram[-2] if len(histogram) > 1 else np.nan

        macd_above_zero = np.isfinite(macd_now) and macd_now > 0.0
        macd_below_zero = np.isfinite(macd_now) and macd_now < 0.0
        histogram_rising = np.isfinite(hist_now) and np.isfinite(hist_prior) and hist_now > hist_prior
        histogram_falling = np.isfinite(hist_now) and np.isfinite(hist_prior) and hist_now < hist_prior

        macd_bullish = macd_above_zero and histogram_rising
        macd_bearish = macd_below_zero and histogram_falling

        adx_result = ADX(self.adx_period).calculate(frame)
        adx = adx_result.values["adx"][-1]
        plus_di = adx_result.values["plus_di"][-1]
        minus_di = adx_result.values["minus_di"][-1]

        adx_ok = np.isfinite(adx) and adx >= self.adx_threshold
        di_bullish = np.isfinite(plus_di) and np.isfinite(minus_di) and plus_di > minus_di
        di_bearish = np.isfinite(plus_di) and np.isfinite(minus_di) and minus_di > plus_di

        bullish_confirmations = sum([rsi_zone_bullish, macd_bullish])
        bearish_confirmations = sum([rsi_zone_bullish, macd_bearish])  # rsi zone is symmetric

        return {
            "rsi": rsi,
            "rsi_zone_bullish": rsi_zone_bullish,
            "rsi_overbought": rsi_overbought,
            "rsi_oversold": rsi_oversold,
            "macd": macd_now,
            "macd_signal": macd_result.values["signal"][-1],
            "histogram": hist_now,
            "macd_above_zero": macd_above_zero,
            "macd_below_zero": macd_below_zero,
            "histogram_rising": histogram_rising,
            "histogram_falling": histogram_falling,
            "macd_bullish": macd_bullish,
            "macd_bearish": macd_bearish,
            "adx": adx,
            "plus_di": plus_di,
            "minus_di": minus_di,
            "adx_ok": adx_ok,
            "di_bullish": di_bullish,
            "di_bearish": di_bearish,
            "bullish_confirmation_count": bullish_confirmations,
            "bearish_confirmation_count": bearish_confirmations,
            "bullish": adx_ok and di_bullish and bullish_confirmations >= self.min_momentum_confirmations,
            "bearish": adx_ok and di_bearish and bearish_confirmations >= self.min_momentum_confirmations,
        }

    def _latest_atr(self, frame: pd.DataFrame) -> Optional[float]:
        atr_arr = ATR(self.atr_period).calculate(frame).values
        value = atr_arr[-1]
        return float(value) if np.isfinite(value) and value > 0 else None

    # ------------------------------------------------------------------
    # 3. Price action (HH/HL/LH/LL, BOS, CHOCH, confirmation candle)
    # ------------------------------------------------------------------
    def _compute_structure(
        self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray
    ) -> dict[str, Any]:
        window = min(len(highs), self.structure_lookback)
        h = highs[-window:]
        l = lows[-window:]
        offset = len(highs) - window

        swings = self._find_swings(h, l, self.swing_strength)
        swing_highs = [(offset + idx, price) for idx, price, kind in swings if kind == "high"]
        swing_lows = [(offset + idx, price) for idx, price, kind in swings if kind == "low"]

        high_labels = [
            "HH" if swing_highs[i][1] > swing_highs[i - 1][1] else "LH"
            for i in range(1, len(swing_highs))
        ]
        low_labels = [
            "HL" if swing_lows[i][1] > swing_lows[i - 1][1] else "LL"
            for i in range(1, len(swing_lows))
        ]

        last_high_label = high_labels[-1] if high_labels else None
        last_low_label = low_labels[-1] if low_labels else None

        if last_high_label == "HH" and last_low_label == "HL":
            structure_bias = "bullish"
        elif last_high_label == "LH" and last_low_label == "LL":
            structure_bias = "bearish"
        else:
            structure_bias = "mixed"

        last_swing_high = swing_highs[-1][1] if swing_highs else None
        last_swing_low = swing_lows[-1][1] if swing_lows else None
        current_close = closes[-1]

        bos_bullish = (
            structure_bias == "bullish"
            and last_swing_high is not None
            and current_close > last_swing_high
        )
        bos_bearish = (
            structure_bias == "bearish"
            and last_swing_low is not None
            and current_close < last_swing_low
        )
        choch_bullish = (
            structure_bias == "bearish"
            and last_swing_high is not None
            and current_close > last_swing_high
        )
        choch_bearish = (
            structure_bias == "bullish"
            and last_swing_low is not None
            and current_close < last_swing_low
        )

        return {
            "swing_highs": swing_highs,
            "swing_lows": swing_lows,
            "high_labels": high_labels,
            "low_labels": low_labels,
            "last_high_label": last_high_label,
            "last_low_label": last_low_label,
            "structure_bias": structure_bias,
            "last_swing_high": last_swing_high,
            "last_swing_low": last_swing_low,
            "bos_bullish": bos_bullish,
            "bos_bearish": bos_bearish,
            "choch_bullish": choch_bullish,
            "choch_bearish": choch_bearish,
            "bullish": structure_bias == "bullish" or bos_bullish or choch_bullish,
            "bearish": structure_bias == "bearish" or bos_bearish or choch_bearish,
        }

    @staticmethod
    def _find_swings(
        highs: np.ndarray, lows: np.ndarray, strength: int
    ) -> list[tuple[int, float, str]]:
        """
        Fractal swing-point detection: index `i` is a swing high/low if
        it is the strict extreme of the `2 * strength + 1`-candle window
        centered on it.
        """
        n = len(highs)
        swings: list[tuple[int, float, str]] = []
        for i in range(strength, n - strength):
            high_window = highs[i - strength : i + strength + 1]
            if highs[i] == high_window.max() and np.argmax(high_window) == strength:
                swings.append((i, float(highs[i]), "high"))
            low_window = lows[i - strength : i + strength + 1]
            if lows[i] == low_window.min() and np.argmin(low_window) == strength:
                swings.append((i, float(lows[i]), "low"))
        swings.sort(key=lambda item: item[0])
        return swings

    def _confirmation_candle(
        self, opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, *, bullish: bool
    ) -> bool:
        if len(closes) < 2:
            return False
        o, h, l, c = opens[-1], highs[-1], lows[-1], closes[-1]
        po, pc = opens[-2], closes[-2]
        candle_range = h - l if h > l else 1e-9
        body = abs(c - o)

        if bullish:
            strong_body = c > o and (body / candle_range) >= self.confirmation_body_ratio
            engulfing = c > o and pc < po and c >= po and o <= pc
            lower_wick = min(o, c) - l
            pin_bar = (lower_wick / candle_range) >= self.confirmation_wick_ratio and c >= o
            return bool(strong_body or engulfing or pin_bar)

        strong_body = c < o and (body / candle_range) >= self.confirmation_body_ratio
        engulfing = c < o and pc > po and c <= po and o >= pc
        upper_wick = h - max(o, c)
        pin_bar = (upper_wick / candle_range) >= self.confirmation_wick_ratio and c <= o
        return bool(strong_body or engulfing or pin_bar)

    # ------------------------------------------------------------------
    # 4. Smart Money Concepts
    # ------------------------------------------------------------------
    def _compute_smc(
        self,
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        atr_value: Optional[float],
        *,
        bullish: bool,
    ) -> dict[str, Any]:
        liquidity_sweep = self._liquidity_sweep(highs, lows, closes, bullish=bullish)
        order_block_retest, order_block_zone = self._order_block(
            opens, highs, lows, closes, atr_value, bullish=bullish
        )
        fvg_filled, fvg_zone = self._fair_value_gap(highs, lows, closes, bullish=bullish)

        count = sum([liquidity_sweep, order_block_retest, fvg_filled])
        return {
            "liquidity_sweep": liquidity_sweep,
            "order_block_retest": order_block_retest,
            "order_block_zone": order_block_zone,
            "fvg_filled": fvg_filled,
            "fvg_zone": fvg_zone,
            "confirmation_count": count,
            "confirmed": count >= self.min_smc_confirmations,
        }

    def _liquidity_sweep(
        self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, *, bullish: bool
    ) -> bool:
        lookback = self.liquidity_lookback
        if len(lows) < lookback + 2:
            return False
        if bullish:
            pool = lows[-(lookback + 1) : -1].min()
            return bool(lows[-1] < pool and closes[-1] > pool)
        pool = highs[-(lookback + 1) : -1].max()
        return bool(highs[-1] > pool and closes[-1] < pool)

    def _order_block(
        self,
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        atr_value: Optional[float],
        *,
        bullish: bool,
    ) -> tuple[bool, Optional[tuple[float, float]]]:
        if atr_value is None:
            return False, None
        n = len(closes)
        start = max(1, n - self.order_block_lookback)
        zone: Optional[tuple[float, float]] = None
        impulse_threshold = self.order_block_impulse_atr_multiplier * atr_value

        for i in range(start, n - 1):
            if bullish:
                is_down_candle = closes[i] < opens[i]
                impulse = closes[i + 1] - opens[i + 1]
                if is_down_candle and impulse > impulse_threshold:
                    zone = (float(lows[i]), float(highs[i]))
            else:
                is_up_candle = closes[i] > opens[i]
                impulse = opens[i + 1] - closes[i + 1]
                if is_up_candle and impulse > impulse_threshold:
                    zone = (float(lows[i]), float(highs[i]))

        if zone is None:
            return False, None
        low_z, high_z = zone
        retested = low_z <= closes[-1] <= high_z
        return retested, zone

    def _fair_value_gap(
        self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, *, bullish: bool
    ) -> tuple[bool, Optional[tuple[float, float]]]:
        n = len(closes)
        start = max(1, n - self.fvg_lookback)
        zone: Optional[tuple[float, float]] = None

        for i in range(start, n - 2):
            if bullish:
                if highs[i] < lows[i + 2]:
                    zone = (float(highs[i]), float(lows[i + 2]))
            else:
                if lows[i] > highs[i + 2]:
                    zone = (float(highs[i + 2]), float(lows[i]))

        if zone is None:
            return False, None
        low_z, high_z = zone
        filled = low_z <= closes[-1] <= high_z
        return filled, zone

    # ------------------------------------------------------------------
    # Pullback (shared distance-from-EMA zone check)
    # ------------------------------------------------------------------
    def _pullback_ok(
        self, close: float, ema_fast: float, ema_medium: float, atr_value: Optional[float]
    ) -> bool:
        if atr_value is None:
            return False
        max_distance = self.pullback_max_atr_distance * atr_value
        near_fast = np.isfinite(ema_fast) and abs(close - ema_fast) <= max_distance
        near_medium = np.isfinite(ema_medium) and abs(close - ema_medium) <= max_distance
        return bool(near_fast or near_medium)

    # ------------------------------------------------------------------
    # Higher-timeframe bias
    # ------------------------------------------------------------------
    def _resolve_htf_bias(self, context: StrategyContext) -> tuple[str, dict[str, Any]]:
        htf_candles = self._extract_candles(context, self.htf_candles_metadata_key)
        min_htf_needed = self.htf_ema_trend_period + self.ema_slope_lookback + _WARMUP_BUFFER
        if htf_candles is not None and len(htf_candles) >= min_htf_needed:
            _o, _h, _l, closes, _v = self._candles_to_arrays(htf_candles)
            frame = pd.DataFrame({"close": closes})
            ema_arr = EMA(self.htf_ema_trend_period).calculate(frame, column="close").values
            ema_now = ema_arr[-1]
            if np.isfinite(ema_now):
                bias = "bullish" if closes[-1] > ema_now else "bearish" if closes[-1] < ema_now else "neutral"
                return bias, {
                    "source": "candles",
                    "timeframe": self.higher_timeframe,
                    "ema_period": self.htf_ema_trend_period,
                    "ema_value": float(ema_now),
                    "close": float(closes[-1]),
                }

        for result in context.analysis_results:
            if result.timeframe == self.higher_timeframe:
                if result.score > self.htf_score_threshold:
                    bias = "bullish"
                elif result.score < -self.htf_score_threshold:
                    bias = "bearish"
                else:
                    bias = "neutral"
                return bias, {
                    "source": "analysis_result",
                    "timeframe": self.higher_timeframe,
                    "analyzer_name": result.analyzer_name,
                    "score": result.score,
                    "confidence": result.confidence,
                }

        return "unavailable", {"source": None, "timeframe": self.higher_timeframe}

    # ------------------------------------------------------------------
    # 5. Entry logic (gate combination)
    # ------------------------------------------------------------------
    def _evaluate_gates(
        self,
        *,
        direction: str,
        trend: dict[str, Any],
        momentum: dict[str, Any],
        structure: dict[str, Any],
        pullback_ok: bool,
        confirmation_candle_ok: bool,
        smc: dict[str, Any],
        htf_bias: str,
    ) -> dict[str, bool]:
        bullish = direction == "long"
        gates = {
            "higher_timeframe_bias": htf_bias == ("bullish" if bullish else "bearish"),
            "ema_alignment_and_direction": trend["bullish"] if bullish else trend["bearish"],
            "momentum_confirmation": momentum["bullish"] if bullish else momentum["bearish"],
            "pullback": pullback_ok,
            "structure_confirmation": structure["bullish"] if bullish else structure["bearish"],
            "smc_confirmation": smc["confirmed"],
        }
        if self.require_confirmation_candle:
            gates["confirmation_candle"] = confirmation_candle_ok
        return {key: bool(value) for key, value in gates.items()}

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------
    def _compute_confidence(
        self,
        *,
        final_action: SignalDirection,
        gates: dict[str, bool],
        trend: dict[str, Any],
        momentum: dict[str, Any],
        smc: dict[str, Any],
        htf_detail: dict[str, Any],
        risk_available: bool,
        risk_result: Any,
    ) -> float:
        gate_ratio = (sum(1 for passed in gates.values() if passed) / len(gates)) if gates else 0.0

        if final_action == SignalDirection.HOLD:
            # Partial confluence still informs how close the setup was,
            # scaled well below a full entry's confidence range.
            return clip(gate_ratio * 0.4)

        adx = momentum.get("adx")
        adx_strength = clip(adx / 50.0) if adx is not None and np.isfinite(adx) else 0.0
        smc_strength = clip(smc.get("confirmation_count", 0) / 3.0)
        htf_confidence = htf_detail.get("confidence", 0.7) if htf_detail.get("source") else 0.5

        base = 0.5 * gate_ratio + 0.2 * adx_strength + 0.15 * smc_strength + 0.15 * htf_confidence
        confidence = clip(base)

        if risk_available and not risk_result.approved:
            # Should not normally reach here (risk override already
            # forces HOLD before this is called), but kept defensive.
            confidence = clip(confidence * 0.5)

        return confidence

    # ------------------------------------------------------------------
    # Presentation helpers
    # ------------------------------------------------------------------
    def _build_summary(
        self,
        *,
        context: StrategyContext,
        final_action: SignalDirection,
        raw_action: SignalDirection,
        confidence: float,
        risk_override: bool,
        htf_bias: str,
    ) -> str:
        summary = (
            f"{final_action.value.upper()} decision for {context.symbol}/{context.timeframe} "
            f"(htf_bias={htf_bias}, confidence={confidence:.2f})"
        )
        if risk_override:
            summary += (
                f" [downgraded from {raw_action.value.upper()} because the risk "
                f"evaluation did not approve it]"
            )
        return summary + "."

    def _build_metadata(
        self,
        *,
        context: StrategyContext,
        trend: dict[str, Any],
        momentum: dict[str, Any],
        structure: dict[str, Any],
        atr_value: Optional[float],
        pullback_bullish: bool,
        confirmation_candle_bullish: bool,
        confirmation_candle_bearish: bool,
        smc_bullish: dict[str, Any],
        smc_bearish: dict[str, Any],
        htf_bias: str,
        htf_detail: dict[str, Any],
        long_gates: dict[str, bool],
        short_gates: dict[str, bool],
        raw_action: SignalDirection,
        final_action: SignalDirection,
        risk_override: bool,
        risk_available: bool,
        confidence: float,
    ) -> dict[str, Any]:
        return {
            "strategy": self.name,
            "symbol": context.symbol,
            "timeframe": context.timeframe,
            "higher_timeframe": self.higher_timeframe,
            "higher_timeframe_bias": htf_bias,
            "higher_timeframe_detail": htf_detail,
            "trend": trend,
            "momentum": momentum,
            "structure": structure,
            "atr": atr_value,
            "pullback": pullback_bullish,
            "confirmation_candle": {
                "bullish": confirmation_candle_bullish,
                "bearish": confirmation_candle_bearish,
            },
            "smart_money": {"bullish": smc_bullish, "bearish": smc_bearish},
            "entry_gates": {"long": long_gates, "short": short_gates},
            "raw_action": raw_action.value,
            "final_action": final_action.value,
            "risk_override": risk_override,
            "risk_available": risk_available,
            "confidence": confidence,
        }
