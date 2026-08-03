"""Bollinger Bands."""

from __future__ import annotations

from collections import deque
from typing import Dict, Optional

import numpy as np

from .base import BaseIndicator, IndicatorResult
from .utils import ArrayLike, IndicatorValidationError, to_numpy_1d, validate_min_length


class BollingerBands(BaseIndicator):
    """
    Bollinger Bands.

    A moving average (the middle band) plus/minus a multiple of the
    rolling (population) standard deviation, forming a volatility
    envelope around price.

    Parameters
    ----------
    period:
        Lookback period for the moving average and standard deviation.
        Must be >= 2.
    std_dev:
        Number of standard deviations for the upper/lower bands.
        Default 2.0.
    """

    def __init__(self, period: int = 20, std_dev: float = 2.0) -> None:
        if std_dev <= 0:
            raise IndicatorValidationError(f"std_dev must be > 0, got {std_dev}")
        self.std_dev = float(std_dev)
        super().__init__(period, min_period=2)

    def _reset_state(self) -> None:
        self._buffer: deque = deque(maxlen=self.period)

    def calculate(self, data: ArrayLike, *, column: Optional[str] = None) -> IndicatorResult:
        """
        Compute Bollinger Bands over the full input.

        Returns
        -------
        IndicatorResult
            Multi-output result with keys ``"middle"``, ``"upper"`` and
            ``"lower"``, each the same length as the input.
        """
        arr = to_numpy_1d(data, column=column, name="data")
        validate_min_length(arr, self.period, name="data")

        n = arr.shape[0]
        middle = np.full(n, np.nan, dtype=float)
        upper = np.full(n, np.nan, dtype=float)
        lower = np.full(n, np.nan, dtype=float)

        cumsum = np.cumsum(np.insert(arr, 0, 0.0))
        window_sums = cumsum[self.period:] - cumsum[:-self.period]
        rolling_mean = window_sums / self.period

        sq_cumsum = np.cumsum(np.insert(arr * arr, 0, 0.0))
        window_sq_sums = sq_cumsum[self.period:] - sq_cumsum[:-self.period]
        rolling_var = window_sq_sums / self.period - rolling_mean ** 2
        rolling_var = np.clip(rolling_var, 0.0, None)
        rolling_std = np.sqrt(rolling_var)

        middle[self.period - 1:] = rolling_mean
        upper[self.period - 1:] = rolling_mean + self.std_dev * rolling_std
        lower[self.period - 1:] = rolling_mean - self.std_dev * rolling_std

        values: Dict[str, np.ndarray] = {"middle": middle, "upper": upper, "lower": lower}
        return self._make_result(values, data, std_dev=self.std_dev)

    def update(self, value: float) -> Optional[Dict[str, float]]:
        """
        Feed a single new value and return the current bands.

        Returns
        -------
        dict or None
            ``{"middle": ..., "upper": ..., "lower": ...}`` once at least
            ``period`` values have been observed, otherwise ``None``.
        """
        value = float(value)
        self._buffer.append(value)
        if len(self._buffer) < self.period:
            return None

        window = np.fromiter(self._buffer, dtype=float, count=len(self._buffer))
        mean = window.mean()
        std = window.std(ddof=0)
        return {
            "middle": mean,
            "upper": mean + self.std_dev * std,
            "lower": mean - self.std_dev * std,
        }
