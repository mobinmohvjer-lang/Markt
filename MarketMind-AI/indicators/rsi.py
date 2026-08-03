"""Relative Strength Index (RSI)."""

from __future__ import annotations

from typing import Optional

import numpy as np

from .base import BaseIndicator, IndicatorResult
from .utils import ArrayLike, to_numpy_1d, validate_min_length


class RSI(BaseIndicator):
    """
    Relative Strength Index, using Wilder's smoothing method.

    RSI oscillates between 0 and 100 and measures the speed/magnitude
    of recent price changes to identify overbought/oversold conditions.

    Parameters
    ----------
    period:
        Number of periods used for the average gain/loss. Must be >= 1.
    """

    def __init__(self, period: int = 14) -> None:
        super().__init__(period, min_period=1)

    def _reset_state(self) -> None:
        self._prev_value: Optional[float] = None
        self._avg_gain: Optional[float] = None
        self._avg_loss: Optional[float] = None
        self._seed_gains: list = []
        self._seed_losses: list = []

    def calculate(self, data: ArrayLike, *, column: Optional[str] = None) -> IndicatorResult:
        """
        Compute the RSI over the full input.

        Returns
        -------
        IndicatorResult
            Same length as input; first ``period`` values are ``NaN``.
        """
        arr = to_numpy_1d(data, column=column, name="data")
        validate_min_length(arr, self.period + 1, name="data")

        n = arr.shape[0]
        out = np.full(n, np.nan, dtype=float)

        deltas = np.diff(arr)
        gains = np.clip(deltas, a_min=0, a_max=None)
        losses = np.clip(-deltas, a_min=0, a_max=None)

        avg_gain = gains[: self.period].mean()
        avg_loss = losses[: self.period].mean()
        out[self.period] = self._rsi_from_avgs(avg_gain, avg_loss)

        for i in range(self.period, len(deltas)):
            avg_gain = (avg_gain * (self.period - 1) + gains[i]) / self.period
            avg_loss = (avg_loss * (self.period - 1) + losses[i]) / self.period
            out[i + 1] = self._rsi_from_avgs(avg_gain, avg_loss)

        return self._make_result(out, data)

    @staticmethod
    def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def update(self, value: float) -> Optional[float]:
        """
        Feed a single new value and return the current RSI.

        Returns
        -------
        float or None
            ``None`` until ``period + 1`` observations have been seen.
        """
        value = float(value)

        if self._prev_value is None:
            self._prev_value = value
            return None

        delta = value - self._prev_value
        self._prev_value = value
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)

        if self._avg_gain is None:
            self._seed_gains.append(gain)
            self._seed_losses.append(loss)
            if len(self._seed_gains) < self.period:
                return None
            self._avg_gain = sum(self._seed_gains) / self.period
            self._avg_loss = sum(self._seed_losses) / self.period
            return self._rsi_from_avgs(self._avg_gain, self._avg_loss)

        self._avg_gain = (self._avg_gain * (self.period - 1) + gain) / self.period
        self._avg_loss = (self._avg_loss * (self.period - 1) + loss) / self.period
        return self._rsi_from_avgs(self._avg_gain, self._avg_loss)
