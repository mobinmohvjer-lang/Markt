"""Simple Moving Average (SMA)."""

from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

from .base import BaseIndicator, IndicatorResult
from .utils import ArrayLike, to_numpy_1d, validate_min_length


class SMA(BaseIndicator):
    """
    Simple Moving Average.

    The unweighted mean of the last ``period`` observations.

    Parameters
    ----------
    period:
        Number of observations averaged over. Must be >= 1.
    """

    def __init__(self, period: int) -> None:
        super().__init__(period, min_period=1)

    def _reset_state(self) -> None:
        self._buffer: deque = deque(maxlen=self.period)
        self._sum: float = 0.0

    def calculate(self, data: ArrayLike, *, column: Optional[str] = None) -> IndicatorResult:
        """
        Compute the SMA over the full input.

        Parameters
        ----------
        data:
            Price series (list, ndarray, pandas Series, or DataFrame with
            ``column`` specified).
        column:
            Column name when ``data`` is a DataFrame.

        Returns
        -------
        IndicatorResult
            Same length as input; first ``period - 1`` values are ``NaN``.
        """
        arr = to_numpy_1d(data, column=column, name="data")
        validate_min_length(arr, self.period, name="data")

        n = arr.shape[0]
        out = np.full(n, np.nan, dtype=float)

        cumsum = np.cumsum(np.insert(arr, 0, 0.0))
        window_sums = cumsum[self.period:] - cumsum[:-self.period]
        out[self.period - 1:] = window_sums / self.period

        return self._make_result(out, data)

    def update(self, value: float) -> Optional[float]:
        """
        Feed a single new value and return the current SMA.

        Returns
        -------
        float or None
            The SMA once at least ``period`` values have been observed,
            otherwise ``None``.
        """
        value = float(value)
        if len(self._buffer) == self._buffer.maxlen:
            self._sum -= self._buffer[0]
        self._buffer.append(value)
        self._sum += value

        if len(self._buffer) < self.period:
            return None
        return self._sum / self.period
