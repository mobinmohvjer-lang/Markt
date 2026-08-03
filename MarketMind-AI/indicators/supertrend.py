"""SuperTrend."""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from .atr import ATR
from .base import BaseIndicator, IndicatorResult
from .utils import IndicatorValidationError, get_index, to_numpy_1d, validate_min_length


class SuperTrend(BaseIndicator):
    """
    SuperTrend.

    An ATR-based trend-following overlay: a trailing stop line that
    flips sides whenever price closes through it, commonly used to read
    trend direction at a glance.

    Parameters
    ----------
    period:
        ATR period. Must be >= 1.
    multiplier:
        Number of ATRs the bands are offset from the midpoint.
        Default 3.0.
    """

    def __init__(self, period: int = 10, multiplier: float = 3.0) -> None:
        if multiplier <= 0:
            raise IndicatorValidationError(f"multiplier must be > 0, got {multiplier}")
        self.multiplier = float(multiplier)
        super().__init__(period, min_period=1)

    def _reset_state(self) -> None:
        self._atr = ATR(self.period)
        self._prev_close: Optional[float] = None
        self._final_upper: Optional[float] = None
        self._final_lower: Optional[float] = None
        self._direction: int = 1  # 1 = uptrend, -1 = downtrend
        self._supertrend: Optional[float] = None

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
        Compute the SuperTrend line and trend direction over the full
        high/low/close history.

        Returns
        -------
        IndicatorResult
            Multi-output result with keys ``"supertrend"`` (the trailing
            stop line) and ``"direction"`` (``1`` for uptrend, ``-1`` for
            downtrend). Both are ``NaN``/``0`` for the ATR warm-up.
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
                "SuperTrend.calculate requires either a DataFrame via 'data' or "
                "'high', 'low' and 'close' arrays"
            )

        if not (high_arr.shape[0] == low_arr.shape[0] == close_arr.shape[0]):
            raise IndicatorValidationError("high, low and close must have equal length")

        validate_min_length(high_arr, self.period + 1, name="high/low/close")

        atr_vals = ATR(self.period).calculate(high=high_arr, low=low_arr, close=close_arr).to_numpy()
        hl2 = (high_arr + low_arr) / 2.0
        basic_upper = hl2 + self.multiplier * atr_vals
        basic_lower = hl2 - self.multiplier * atr_vals

        n = high_arr.shape[0]
        final_upper = np.full(n, np.nan, dtype=float)
        final_lower = np.full(n, np.nan, dtype=float)
        supertrend = np.full(n, np.nan, dtype=float)
        direction = np.zeros(n, dtype=int)

        start = self.period  # first index with a valid ATR value
        final_upper[start] = basic_upper[start]
        final_lower[start] = basic_lower[start]
        direction[start] = 1 if close_arr[start] >= final_upper[start] else -1
        supertrend[start] = final_lower[start] if direction[start] == 1 else final_upper[start]

        for i in range(start + 1, n):
            if np.isnan(basic_upper[i]):
                continue
            final_upper[i] = (
                basic_upper[i]
                if (basic_upper[i] < final_upper[i - 1] or close_arr[i - 1] > final_upper[i - 1])
                else final_upper[i - 1]
            )
            final_lower[i] = (
                basic_lower[i]
                if (basic_lower[i] > final_lower[i - 1] or close_arr[i - 1] < final_lower[i - 1])
                else final_lower[i - 1]
            )

            if direction[i - 1] == 1:
                direction[i] = -1 if close_arr[i] < final_lower[i] else 1
            else:
                direction[i] = 1 if close_arr[i] > final_upper[i] else -1

            supertrend[i] = final_lower[i] if direction[i] == 1 else final_upper[i]

        values: Dict[str, np.ndarray] = {
            "supertrend": supertrend,
            "direction": direction.astype(float),
        }
        return self._make_result(
            values, data if isinstance(data, pd.DataFrame) else high, multiplier=self.multiplier
        )

    def update(self, high: float, low: float, close: float) -> Optional[Dict[str, float]]:
        """
        Feed a single new (high, low, close) observation and return the
        current SuperTrend line/direction.

        Returns
        -------
        dict or None
            ``{"supertrend": ..., "direction": ...}`` once the ATR has
            warmed up, otherwise ``None``.
        """
        high, low, close = float(high), float(low), float(close)
        atr_val = self._atr.update(high, low, close)
        if atr_val is None:
            self._prev_close = close
            return None

        hl2 = (high + low) / 2.0
        basic_upper = hl2 + self.multiplier * atr_val
        basic_lower = hl2 - self.multiplier * atr_val

        if self._final_upper is None:
            final_upper = basic_upper
            final_lower = basic_lower
            direction = 1 if close >= final_upper else -1
        else:
            final_upper = (
                basic_upper
                if (basic_upper < self._final_upper or self._prev_close > self._final_upper)
                else self._final_upper
            )
            final_lower = (
                basic_lower
                if (basic_lower > self._final_lower or self._prev_close < self._final_lower)
                else self._final_lower
            )
            if self._direction == 1:
                direction = -1 if close < final_lower else 1
            else:
                direction = 1 if close > final_upper else -1

        self._final_upper = final_upper
        self._final_lower = final_lower
        self._direction = direction
        self._prev_close = close
        self._supertrend = final_lower if direction == 1 else final_upper

        return {"supertrend": self._supertrend, "direction": float(direction)}
