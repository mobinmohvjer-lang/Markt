"""Rate of Change (ROC)."""

from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

from .base import BaseIndicator, IndicatorResult
from .utils import ArrayLike, to_numpy_1d, validate_min_length


class ROC(BaseIndicator):
    """
    Rate of Change.

    Percentage change between the current value and the value
    ``period`` bars ago: ``(value[t] - value[t - period]) / value[t - period] * 100``.

    Parameters
    ----------
    period:
        Number of bars to look back. Must be >= 1.
    """

    def __init__(self, period: int = 12) -> None:
        super().__init__(period, min_period=1)

    def _reset_state(self) -> None:
        self._buffer: deque = deque(maxlen=self.period + 1)

    def calculate(self, data: ArrayLike, *, column: Optional[str] = None) -> IndicatorResult:
        """
        Compute the ROC over the full input.

        Returns
        -------
        IndicatorResult
            Same length as input; first ``period`` values are ``NaN``.
        """
        arr = to_numpy_1d(data, column=column, name="data")
        validate_min_length(arr, self.period + 1, name="data")

        n = arr.shape[0]
        out = np.full(n, np.nan, dtype=float)
        prev = arr[:-self.period]
        curr = arr[self.period:]
        with np.errstate(invalid="ignore", divide="ignore"):
            out[self.period:] = np.where(prev != 0, (curr - prev) / prev * 100.0, np.nan)

        return self._make_result(out, data)

    def update(self, value: float) -> Optional[float]:
        """
        Feed a single new value and return the current ROC.

        Returns
        -------
        float or None
            ``None`` until ``period + 1`` values have been observed.
        """
        value = float(value)
        self._buffer.append(value)
        if len(self._buffer) <= self.period:
            return None

        prev = self._buffer[0]
        if prev == 0:
            return np.nan
        return (value - prev) / prev * 100.0
