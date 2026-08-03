"""Hull Moving Average (HMA)."""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from .base import BaseIndicator, IndicatorResult
from .utils import ArrayLike, to_numpy_1d, validate_min_length
from .wma import WMA


class HMA(BaseIndicator):
    """
    Hull Moving Average.

    Defined as::

        HMA(n) = WMA( 2 * WMA(price, n/2) - WMA(price, n), round(sqrt(n)) )

    The Hull Moving Average reduces lag compared to a plain WMA/SMA
    while remaining smooth.

    Parameters
    ----------
    period:
        The base period ``n``. Must be >= 2 (so that ``n/2`` is at
        least 1).
    """

    def __init__(self, period: int) -> None:
        super().__init__(period, min_period=2)

    def _reset_state(self) -> None:
        self._half_period = max(1, round(self.period / 2))
        self._sqrt_period = max(1, round(math.sqrt(self.period)))

        self._wma_half = WMA(self._half_period)
        self._wma_full = WMA(self.period)
        self._wma_final = WMA(self._sqrt_period)

    def calculate(self, data: ArrayLike, *, column: Optional[str] = None) -> IndicatorResult:
        """
        Compute the HMA over the full input.

        Returns
        -------
        IndicatorResult
            Same length as input; leading values are ``NaN`` until enough
            history has accumulated (``period + sqrt(period) - 2``
            observations, approximately).
        """
        arr = to_numpy_1d(data, column=column, name="data")
        validate_min_length(arr, self.period, name="data")

        wma_half = WMA(self._half_period).calculate(arr).to_numpy()
        wma_full = WMA(self.period).calculate(arr).to_numpy()
        raw = 2.0 * wma_half - wma_full

        n = arr.shape[0]
        out = np.full(n, np.nan, dtype=float)
        valid_start = self.period - 1
        valid_raw = raw[valid_start:]

        if valid_raw.shape[0] >= self._sqrt_period:
            final = WMA(self._sqrt_period).calculate(valid_raw).to_numpy()
            out[valid_start:] = final

        return self._make_result(out, data, half_period=self._half_period, sqrt_period=self._sqrt_period)

    def update(self, value: float) -> Optional[float]:
        """
        Feed a single new value and return the current HMA.

        Returns
        -------
        float or None
            ``None`` until enough observations have accumulated.
        """
        half_val = self._wma_half.update(value)
        full_val = self._wma_full.update(value)

        if full_val is None:
            return None

        raw = 2.0 * half_val - full_val
        return self._wma_final.update(raw)
