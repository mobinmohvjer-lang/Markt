"""Average Directional Index (ADX)."""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from .base import BaseIndicator, IndicatorResult
from .dmi import DMI
from .utils import IndicatorValidationError, get_index, to_numpy_1d, validate_min_length


class ADX(BaseIndicator):
    """
    Average Directional Index.

    Measures trend strength (not direction) as a Wilder-smoothed average
    of the Directional Index ``DX = 100 * |+DI - -DI| / (+DI + -DI)``,
    built on top of :class:`DMI`.

    Parameters
    ----------
    period:
        Smoothing period, used both for the underlying +DI/-DI and for
        smoothing DX into ADX. Must be >= 1.
    """

    def __init__(self, period: int = 14) -> None:
        super().__init__(period, min_period=1)

    def _reset_state(self) -> None:
        self._dmi = DMI(self.period)
        self._smoothed_dx: Optional[float] = None
        self._seed_dx: list = []

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
        Compute ADX (plus the underlying +DI/-DI) over the full input.

        Returns
        -------
        IndicatorResult
            Multi-output result with keys ``"adx"``, ``"plus_di"`` and
            ``"minus_di"``.
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
                "ADX.calculate requires either a DataFrame via 'data' or 'high', 'low' and 'close' arrays"
            )

        validate_min_length(high_arr, 2 * self.period, name="high/low/close")

        dmi_result = DMI(self.period).calculate(high=high_arr, low=low_arr, close=close_arr)
        plus_di = dmi_result.to_numpy()["plus_di"]
        minus_di = dmi_result.to_numpy()["minus_di"]

        di_sum = plus_di + minus_di
        with np.errstate(invalid="ignore", divide="ignore"):
            dx = np.where(di_sum != 0, 100 * np.abs(plus_di - minus_di) / di_sum, np.nan)

        n = high_arr.shape[0]
        adx = np.full(n, np.nan, dtype=float)

        first_valid = self.period  # index of first non-NaN DX value
        window_end = first_valid + self.period  # need `period` DX values to seed ADX
        if window_end < n:
            adx[window_end - 1] = np.nanmean(dx[first_valid:window_end])
            for i in range(window_end, n):
                adx[i] = (adx[i - 1] * (self.period - 1) + dx[i]) / self.period

        values: Dict[str, np.ndarray] = {"adx": adx, "plus_di": plus_di, "minus_di": minus_di}
        return self._make_result(values, data if isinstance(data, pd.DataFrame) else high)

    def update(self, high: float, low: float, close: float) -> Optional[Dict[str, float]]:
        """
        Feed a single new (high, low, close) observation and return the
        current ADX/+DI/-DI.

        Returns
        -------
        dict or None
            ``{"adx": ..., "plus_di": ..., "minus_di": ...}`` once enough
            history has accumulated, otherwise ``None``.
        """
        di = self._dmi.update(high, low, close)
        if di is None:
            return None

        plus_di, minus_di = di["plus_di"], di["minus_di"]
        di_sum = plus_di + minus_di
        dx = 100 * abs(plus_di - minus_di) / di_sum if di_sum else float("nan")

        if self._smoothed_dx is None:
            self._seed_dx.append(dx)
            if len(self._seed_dx) < self.period:
                return None
            self._smoothed_dx = float(np.nanmean(self._seed_dx))
        else:
            self._smoothed_dx = (self._smoothed_dx * (self.period - 1) + dx) / self.period

        return {"adx": self._smoothed_dx, "plus_di": plus_di, "minus_di": minus_di}
