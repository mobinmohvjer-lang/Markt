"""Weighted Moving Average (WMA)."""

from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

from .base import BaseIndicator, IndicatorResult
from .utils import ArrayLike, rolling_window_view, to_numpy_1d, validate_min_length


class WMA(BaseIndicator):
    """
    Weighted Moving Average.

    Applies linearly increasing weights (1, 2, ..., ``period``) to the
    window, so the most recent observation has the largest weight.

    Parameters
    ----------
    period:
        Size of the weighting window.
    """

    def __init__(self, period: int) -> None:
        super().__init__(period, min_period=1)

    def _reset_state(self) -> None:
        self._weights = np.arange(1, self.period + 1, dtype=float)
        self._weight_sum = self._weights.sum()
        self._buffer: deque = deque(maxlen=self.period)

    def calculate(self, data: ArrayLike, *, column: Optional[str] = None) -> IndicatorResult:
        """
        Compute the WMA over the full input.

        Returns
        -------
        IndicatorResult
            Same length as input; first ``period - 1`` values are ``NaN``.
        """
        arr = to_numpy_1d(data, column=column, name="data")
        validate_min_length(arr, self.period, name="data")

        n = arr.shape[0]
        out = np.full(n, np.nan, dtype=float)

        windows = rolling_window_view(arr, self.period)  # shape (n-period+1, period)
        out[self.period - 1:] = windows @ self._weights / self._weight_sum

        return self._make_result(out, data)

    def update(self, value: float) -> Optional[float]:
        """
        Feed a single new value and return the current WMA.

        Returns
        -------
        float or None
            ``None`` until ``period`` observations have been seen.
        """
        self._buffer.append(float(value))
        if len(self._buffer) < self.period:
            return None
        weights = self._weights if len(self._buffer) == self.period else np.arange(
            1, len(self._buffer) + 1, dtype=float
        )
        arr = np.fromiter(self._buffer, dtype=float, count=len(self._buffer))
        return float(np.dot(arr, weights) / weights.sum())
