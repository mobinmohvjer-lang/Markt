"""Commodity Channel Index (CCI)."""

from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np
import pandas as pd

from .base import BaseIndicator, IndicatorResult
from .utils import IndicatorValidationError, get_index, to_numpy_1d, validate_min_length


class CCI(BaseIndicator):
    """
    Commodity Channel Index.

    Measures how far the typical price ``(high + low + close) / 3`` has
    deviated from its moving average, relative to the average absolute
    deviation over the window.

    Parameters
    ----------
    period:
        Lookback period. Must be >= 1.
    constant:
        Scaling constant (Lambert's original value is 0.015, chosen so
        that roughly 70-80% of values fall between -100 and +100).
    """

    def __init__(self, period: int = 20, constant: float = 0.015) -> None:
        if constant <= 0:
            raise IndicatorValidationError(f"constant must be > 0, got {constant}")
        self.constant = float(constant)
        super().__init__(period, min_period=1)

    def _reset_state(self) -> None:
        self._buffer: deque = deque(maxlen=self.period)

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
        Compute the CCI over the full high/low/close history.

        Returns
        -------
        IndicatorResult
            Same length as input; first ``period - 1`` values are ``NaN``.
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
                "CCI.calculate requires either a DataFrame via 'data' or 'high', 'low' and 'close' arrays"
            )

        if not (high_arr.shape[0] == low_arr.shape[0] == close_arr.shape[0]):
            raise IndicatorValidationError("high, low and close must have equal length")

        validate_min_length(high_arr, self.period, name="high/low/close")

        typical = (high_arr + low_arr + close_arr) / 3.0
        tp_series = pd.Series(typical)
        sma_tp = tp_series.rolling(self.period).mean()
        mean_dev = tp_series.rolling(self.period).apply(
            lambda w: np.mean(np.abs(w - w.mean())), raw=True
        )

        with np.errstate(invalid="ignore", divide="ignore"):
            cci = (tp_series - sma_tp) / (self.constant * mean_dev)
        out = cci.to_numpy()

        return self._make_result(out, data if isinstance(data, pd.DataFrame) else high, constant=self.constant)

    def update(self, high: float, low: float, close: float) -> Optional[float]:
        """
        Feed a single new (high, low, close) observation and return the
        current CCI.

        Returns
        -------
        float or None
            ``None`` until ``period`` observations have been accumulated.
        """
        high, low, close = float(high), float(low), float(close)
        typical = (high + low + close) / 3.0
        self._buffer.append(typical)
        if len(self._buffer) < self.period:
            return None

        window = np.fromiter(self._buffer, dtype=float, count=len(self._buffer))
        mean = window.mean()
        mean_dev = np.mean(np.abs(window - mean))
        if mean_dev == 0:
            return 0.0
        return (typical - mean) / (self.constant * mean_dev)
