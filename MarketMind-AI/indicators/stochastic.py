"""Stochastic Oscillator (%K / %D)."""

from __future__ import annotations

from collections import deque
from typing import Dict, Optional

import numpy as np
import pandas as pd

from .base import BaseIndicator, IndicatorResult
from .utils import IndicatorValidationError, get_index, to_numpy_1d, validate_min_length


class Stochastic(BaseIndicator):
    """
    Stochastic Oscillator.

    Compares a closing price to its high/low range over ``period`` bars
    (``%K``), then smooths ``%K`` with a simple moving average to get
    ``%D``.

    Parameters
    ----------
    period:
        Lookback window for %K (a.k.a. the "%K period"). Must be >= 1.
    d_period:
        Smoothing period for %D. Must be >= 1. Default 3.
    """

    def __init__(self, period: int = 14, d_period: int = 3) -> None:
        if isinstance(d_period, bool) or not isinstance(d_period, int) or d_period < 1:
            raise IndicatorValidationError(f"d_period must be an int >= 1, got {d_period}")
        self.d_period = d_period
        super().__init__(period, min_period=1)
        self.name = f"Stochastic_{self.period}_{self.d_period}"

    def _reset_state(self) -> None:
        self._highs: deque = deque(maxlen=self.period)
        self._lows: deque = deque(maxlen=self.period)
        self._k_values: deque = deque(maxlen=self.d_period)

    def calculate(
        self,
        data: Optional[pd.DataFrame] = None,
        *,
        high=None,
        low=None,
        close=None,
        high_column: str = "high",
        low_column: str = "low",
        close_column: str = "close",
    ) -> IndicatorResult:
        """
        Compute %K and %D over the full high/low/close history.

        Returns
        -------
        IndicatorResult
            Multi-output result with keys ``"k"`` and ``"d"``.
        """
        if isinstance(data, pd.DataFrame):
            high_arr = to_numpy_1d(data, column=high_column, name="high")
            low_arr = to_numpy_1d(data, column=low_column, name="low")
            close_arr = to_numpy_1d(data, column=close_column, name="close")
            index = get_index(data)
        elif high is not None and low is not None and close is not None:
            high_arr = to_numpy_1d(high, name="high")
            low_arr = to_numpy_1d(low, name="low")
            close_arr = to_numpy_1d(close, name="close")
            index = get_index(high)
        else:
            raise IndicatorValidationError(
                "Stochastic.calculate requires either a DataFrame via 'data' or "
                "'high', 'low' and 'close' arrays"
            )

        if not (high_arr.shape[0] == low_arr.shape[0] == close_arr.shape[0]):
            raise IndicatorValidationError("high, low and close must have equal length")

        validate_min_length(high_arr, self.period, name="high/low/close")

        n = high_arr.shape[0]
        k = np.full(n, np.nan, dtype=float)

        highs_series = pd.Series(high_arr)
        lows_series = pd.Series(low_arr)
        rolling_high = highs_series.rolling(self.period).max().to_numpy()
        rolling_low = lows_series.rolling(self.period).min().to_numpy()
        rng = rolling_high - rolling_low

        with np.errstate(invalid="ignore", divide="ignore"):
            k = np.where(rng != 0, 100 * (close_arr - rolling_low) / rng, 50.0)
        k[: self.period - 1] = np.nan

        d = pd.Series(k).rolling(self.d_period).mean().to_numpy()

        values: Dict[str, np.ndarray] = {"k": k, "d": d}
        return self._make_result(values, data if isinstance(data, pd.DataFrame) else high, d_period=self.d_period)

    def update(self, high: float, low: float, close: float) -> Optional[Dict[str, float]]:
        """
        Feed a single new (high, low, close) observation and return the
        current %K/%D.

        Returns
        -------
        dict or None
            ``{"k": ..., "d": ...}``. ``"d"`` is ``None`` until enough %K
            values have accumulated; the whole result is ``None`` until
            %K itself is available.
        """
        high, low, close = float(high), float(low), float(close)
        self._highs.append(high)
        self._lows.append(low)
        if len(self._highs) < self.period:
            return None

        highest = max(self._highs)
        lowest = min(self._lows)
        rng = highest - lowest
        k = 100 * (close - lowest) / rng if rng != 0 else 50.0

        self._k_values.append(k)
        d = sum(self._k_values) / len(self._k_values) if len(self._k_values) == self.d_period else None

        return {"k": k, "d": d}
