"""Exponential Moving Average (EMA)."""

from __future__ import annotations

from typing import Optional

import numpy as np

from .base import BaseIndicator, IndicatorResult
from .utils import ArrayLike, to_numpy_1d, validate_min_length, validate_positive_number


class EMA(BaseIndicator):
    """
    Exponential Moving Average.

    Weights recent observations more heavily than older ones using a
    smoothing factor ``alpha = smoothing / (period + 1)``. The first
    valid EMA value is seeded with the SMA of the first ``period``
    observations (the conventional approach), and every observation
    thereafter is updated recursively.

    Parameters
    ----------
    period:
        Lookback period used to derive the smoothing factor.
    smoothing:
        Smoothing multiplier, conventionally ``2.0``.
    """

    def __init__(self, period: int, smoothing: float = 2.0) -> None:
        self.smoothing = validate_positive_number(smoothing, name="smoothing")
        super().__init__(period, min_period=1)

    def _reset_state(self) -> None:
        self._alpha: float = self.smoothing / (self.period + 1)
        self._seen: int = 0
        self._seed_sum: float = 0.0
        self._prev_ema: Optional[float] = None

    def calculate(self, data: ArrayLike, *, column: Optional[str] = None) -> IndicatorResult:
        """
        Compute the EMA over the full input.

        Returns
        -------
        IndicatorResult
            Same length as input; first ``period - 1`` values are ``NaN``.
        """
        arr = to_numpy_1d(data, column=column, name="data")
        validate_min_length(arr, self.period, name="data")

        n = arr.shape[0]
        out = np.full(n, np.nan, dtype=float)
        alpha = self.smoothing / (self.period + 1)

        seed = arr[: self.period].mean()
        out[self.period - 1] = seed
        prev = seed
        for i in range(self.period, n):
            prev = (arr[i] - prev) * alpha + prev
            out[i] = prev

        return self._make_result(out, data, smoothing=self.smoothing)

    def update(self, value: float) -> Optional[float]:
        """
        Feed a single new value and return the current EMA.

        Returns
        -------
        float or None
            ``None`` until ``period`` observations have been seen (the
            SMA seed value is returned on the ``period``-th observation).
        """
        value = float(value)
        self._seen += 1

        if self._prev_ema is None:
            self._seed_sum += value
            if self._seen < self.period:
                return None
            self._prev_ema = self._seed_sum / self.period
            return self._prev_ema

        self._prev_ema = (value - self._prev_ema) * self._alpha + self._prev_ema
        return self._prev_ema
