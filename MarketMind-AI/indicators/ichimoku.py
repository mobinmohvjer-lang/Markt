"""Ichimoku Cloud (Ichimoku Kinko Hyo)."""

from __future__ import annotations

from collections import deque
from typing import Dict, Optional

import numpy as np
import pandas as pd

from .base import BaseIndicator, IndicatorResult
from .utils import IndicatorValidationError, get_index, to_numpy_1d, validate_min_length, validate_period


class Ichimoku(BaseIndicator):
    """
    Ichimoku Cloud.

    Computes the five classic Ichimoku lines:

    * ``tenkan_sen`` (conversion line): midpoint of the high/low range
      over ``tenkan_period`` bars.
    * ``kijun_sen`` (base line): midpoint of the high/low range over
      ``kijun_period`` bars.
    * ``senkou_span_a`` (leading span A): midpoint of tenkan/kijun,
      plotted ``displacement`` bars ahead.
    * ``senkou_span_b`` (leading span B): midpoint of the high/low range
      over ``senkou_b_period`` bars, plotted ``displacement`` bars ahead.
    * ``chikou_span`` (lagging span): the closing price, plotted
      ``displacement`` bars behind.

    Parameters
    ----------
    tenkan_period:
        Conversion line period. Default 9.
    kijun_period:
        Base line period. Default 26.
    senkou_b_period:
        Leading span B period. Default 52.
    displacement:
        Forward/backward shift applied to the leading/lagging spans.
        Default 26.
    """

    def __init__(
        self,
        tenkan_period: int = 9,
        kijun_period: int = 26,
        senkou_b_period: int = 52,
        displacement: int = 26,
    ) -> None:
        self.tenkan_period = validate_period(tenkan_period, min_period=1, name="tenkan_period")
        self.kijun_period = validate_period(kijun_period, min_period=1, name="kijun_period")
        self.senkou_b_period = validate_period(senkou_b_period, min_period=1, name="senkou_b_period")
        self.displacement = validate_period(displacement, min_period=1, name="displacement")
        # `period` on the base class represents the largest lookback involved.
        super().__init__(max(tenkan_period, kijun_period, senkou_b_period), min_period=1)
        self.name = (
            f"Ichimoku_{self.tenkan_period}_{self.kijun_period}_"
            f"{self.senkou_b_period}_{self.displacement}"
        )

    def _reset_state(self) -> None:
        max_period = max(self.tenkan_period, self.kijun_period, self.senkou_b_period)
        self._highs: deque = deque(maxlen=max_period)
        self._lows: deque = deque(maxlen=max_period)

    @staticmethod
    def _midpoint(highs, lows, period: int) -> Optional[float]:
        if len(highs) < period:
            return None
        recent_high = list(highs)[-period:]
        recent_low = list(lows)[-period:]
        return (max(recent_high) + min(recent_low)) / 2.0

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
        Compute all five Ichimoku lines over the full high/low/close
        history.

        Returns
        -------
        IndicatorResult
            Multi-output result with keys ``"tenkan_sen"``,
            ``"kijun_sen"``, ``"senkou_span_a"``, ``"senkou_span_b"`` and
            ``"chikou_span"``, each the same length as the input.
            ``senkou_span_a``/``senkou_span_b`` are shifted forward and
            ``chikou_span`` is shifted backward by ``displacement``
            bars, so the extremes of the arrays contain ``NaN``.
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
                "Ichimoku.calculate requires either a DataFrame via 'data' or "
                "'high', 'low' and 'close' arrays"
            )

        if not (high_arr.shape[0] == low_arr.shape[0] == close_arr.shape[0]):
            raise IndicatorValidationError("high, low and close must have equal length")

        validate_min_length(high_arr, self.senkou_b_period, name="high/low/close")

        high_s = pd.Series(high_arr)
        low_s = pd.Series(low_arr)

        def rolling_midpoint(period: int) -> np.ndarray:
            roll_high = high_s.rolling(period).max()
            roll_low = low_s.rolling(period).min()
            return ((roll_high + roll_low) / 2.0).to_numpy()

        tenkan_sen = rolling_midpoint(self.tenkan_period)
        kijun_sen = rolling_midpoint(self.kijun_period)
        senkou_b_raw = rolling_midpoint(self.senkou_b_period)
        senkou_a_raw = (tenkan_sen + kijun_sen) / 2.0

        n = high_arr.shape[0]

        def shift_forward(arr: np.ndarray, shift: int) -> np.ndarray:
            out = np.full(n, np.nan, dtype=float)
            if shift < n:
                out[shift:] = arr[: n - shift]
            return out

        def shift_backward(arr: np.ndarray, shift: int) -> np.ndarray:
            out = np.full(n, np.nan, dtype=float)
            if shift < n:
                out[: n - shift] = arr[shift:]
            return out

        senkou_span_a = shift_forward(senkou_a_raw, self.displacement)
        senkou_span_b = shift_forward(senkou_b_raw, self.displacement)
        chikou_span = shift_backward(close_arr, self.displacement)

        values: Dict[str, np.ndarray] = {
            "tenkan_sen": tenkan_sen,
            "kijun_sen": kijun_sen,
            "senkou_span_a": senkou_span_a,
            "senkou_span_b": senkou_span_b,
            "chikou_span": chikou_span,
        }
        return self._make_result(
            values, data if isinstance(data, pd.DataFrame) else high,
            tenkan_period=self.tenkan_period, kijun_period=self.kijun_period,
            senkou_b_period=self.senkou_b_period, displacement=self.displacement,
        )

    def update(self, high: float, low: float, close: float) -> Optional[Dict[str, Optional[float]]]:
        """
        Feed a single new (high, low, close) observation and return the
        current (undisplaced) line values.

        Returns
        -------
        dict or None
            ``{"tenkan_sen", "kijun_sen", "senkou_span_a", "senkou_span_b",
            "chikou_span"}``. Individual keys are ``None`` until their
            respective lookback windows have filled. ``chikou_span`` is
            simply the current close (its displacement is a plotting
            concern for the caller, since streaming has no "future" to
            shift into). Returns ``None`` only while every window is
            still empty.
        """
        high, low, close = float(high), float(low), float(close)
        self._highs.append(high)
        self._lows.append(low)

        tenkan = self._midpoint(self._highs, self._lows, self.tenkan_period)
        kijun = self._midpoint(self._highs, self._lows, self.kijun_period)
        senkou_b = self._midpoint(self._highs, self._lows, self.senkou_b_period)
        senkou_a = (tenkan + kijun) / 2.0 if (tenkan is not None and kijun is not None) else None

        if tenkan is None and kijun is None and senkou_b is None:
            return None

        return {
            "tenkan_sen": tenkan,
            "kijun_sen": kijun,
            "senkou_span_a": senkou_a,
            "senkou_span_b": senkou_b,
            "chikou_span": close,
        }
