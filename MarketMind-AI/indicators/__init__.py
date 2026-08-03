"""
indicators package
---------------------
Purpose:
    Contains pure, reusable technical indicator calculations (e.g. moving
    averages, RSI, MACD, Bollinger Bands, ATR). Each indicator is a small,
    testable, stateless class that takes market data (e.g. a list,
    numpy.ndarray, pandas Series/DataFrame of OHLCV candles) and returns
    computed values -- with no knowledge of strategies, signals, or
    trading decisions.

    This package is intentionally separate from `analysis/`: `indicators`
    provides the raw building blocks (the "how to calculate"), while
    `analysis/technical/` (a consumer of this package) interprets those
    values into higher-level insights (the "what it means").

Contents:
    - base.py: shared `BaseIndicator` / `IndicatorResult` abstractions and
      input validation/array-conversion utilities (utils.py).
    - Trend/momentum: SMA, EMA, WMA, HMA, MACD, RSI, ADX, DMI, ROC,
      Stochastic, CCI, Ichimoku, SuperTrend.
    - Volatility: ATR, Bollinger Bands, Keltner Channel, Donchian Channel.
    - Volume: OBV, VWAP, Volume SMA.

Every indicator supports both batch calculation (`calculate`) over a
list/ndarray/pandas Series/DataFrame, and incremental/streaming
calculation (`update`) for one observation at a time.
"""

from __future__ import annotations

from .base import BaseIndicator, IndicatorResult
from .utils import IndicatorValidationError

# --- Trend / momentum ---
from .sma import SMA
from .ema import EMA
from .wma import WMA
from .hma import HMA
from .macd import MACD
from .rsi import RSI
from .adx import ADX
from .dmi import DMI
from .roc import ROC
from .cci import CCI
from .stochastic import Stochastic
from .ichimoku import Ichimoku
from .supertrend import SuperTrend

# --- Volatility ---
from .atr import ATR
from .bollinger_bands import BollingerBands
from .keltner_channel import KeltnerChannel
from .donchian_channel import DonchianChannel

# --- Volume ---
from .obv import OBV
from .vwap import VWAP
from .volume_sma import VolumeSMA

__all__ = [
    "BaseIndicator",
    "IndicatorResult",
    "IndicatorValidationError",
    "SMA",
    "EMA",
    "WMA",
    "HMA",
    "MACD",
    "RSI",
    "ADX",
    "DMI",
    "ROC",
    "CCI",
    "Stochastic",
    "Ichimoku",
    "SuperTrend",
    "ATR",
    "BollingerBands",
    "KeltnerChannel",
    "DonchianChannel",
    "OBV",
    "VWAP",
    "VolumeSMA",
]
