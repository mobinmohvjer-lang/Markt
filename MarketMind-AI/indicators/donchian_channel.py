"""Donchian Channel."""

from __future__ import annotations

from collections import deque
from typing import Dict, Optional

import numpy as np
import pandas as pd

from .base import BaseIndicator, IndicatorResult
from .utils import IndicatorValidationError, get_index, to_numpy_1d, validate_min_length


class DonchianChannel(BaseIndicator):
    """
    Donchian Channel.

    The rolling highest high and lowest low over ``period`` bars, with
    the midpoint as the middle line.

    Parameters
    ----------
    period:
        Lookback period. Must be >= 1.
    """

    def __init__(self, period: int = 20) -> None:
        super().__init__(period, min_period=1)

    def _reset_state(self) -> None:
        self._highs: deque = deque(maxlen=self.period)
        self._lows: deque = deque(maxlen=self.period)

    def calculate(
        self,
        data: Optional[pd.DataFrame] = None,
        *,
        high=None,
        low=None,
        high_column: str = "high",
        low_column: str = "low",
    ) -> IndicatorResult:
        """
        Compute the Donchian Channel over the full high/low history.

        Returns
        -------
        IndicatorResult
            Multi-output result with keys ``"upper"``, ``"lower"`` and
            ``"middle"``.
        """
        if isinstance(data, pd.DataFrame):
            high_arr = to_numpy_1d(data, column=high_column, name="high")
            low_arr = to_numpy_1d(data, column=low_column, name="low")
            index = get_index(data)
        elif high is not None and low is not None:
            high_arr = to_numpy_1d(high, name="high")
            low_arr = to_numpy_1d(low, name="low")
            index = get_index(high)
        else:
            raise IndicatorValidationError(
                "DonchianChannel.calculate requires either a DataFrame via 'data' or "
                "'high' and 'low' arrays"
            )

        if high_arr.shape[0] != low_arr.shape[0]:
            raise IndicatorValidationError("high and low must have equal length")

        validate_min_length(high_arr, self.period, name="high/low")

        upper = pd.Series(high_arr).rolling(self.period).max().to_numpy()
        lower = pd.Series(low_arr).rolling(self.period).min().to_numpy()
        middle = (upper + lower) / 2.0

        values: Dict[str, np.ndarray] = {"upper": upper, "lower": lower, "middle": middle}
        return self._make_result(values, data if isinstance(data, pd.DataFrame) else high)

    def update(self, high: float, low: float) -> Optional[Dict[str, float]]:
        """
        Feed a single new (high, low) observation and return the current
        channel.

        Returns
        -------
        dict or None
            ``{"upper": ..., "lower": ..., "middle": ...}`` once
            ``period`` observations have been accumulated, otherwise
            ``None``.
        """
        self._highs.append(float(high))
        self._lows.append(float(low))
        if len(self._highs) < self.period:
            return None

        upper = max(self._highs)
        lower = min(self._lows)
        return {"upper": upper, "lower": lower, "middle": (upper + lower) / 2.0}
