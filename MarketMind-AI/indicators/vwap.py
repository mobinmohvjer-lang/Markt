"""Volume Weighted Average Price (VWAP)."""

from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np
import pandas as pd

from .base import BaseIndicator, IndicatorResult
from .utils import IndicatorValidationError, get_index, to_numpy_1d, validate_min_length


class VWAP(BaseIndicator):
    """
    Rolling Volume Weighted Average Price.

    The volume-weighted average of the typical price ``(high + low +
    close) / 3`` over a rolling window. Unlike a session VWAP (which
    resets at a fixed anchor such as market open), this is a fixed-length
    rolling window, consistent with the batch/incremental contract of
    :class:`BaseIndicator`.

    Parameters
    ----------
    period:
        Rolling window length. Must be >= 1.
    """

    def __init__(self, period: int = 14) -> None:
        super().__init__(period, min_period=1)

    def _reset_state(self) -> None:
        self._tp_vol: deque = deque(maxlen=self.period)
        self._vol: deque = deque(maxlen=self.period)

    def calculate(
        self,
        data: Optional[pd.DataFrame] = None,
        *,
        high=None,
        low=None,
        close=None,
        volume=None,
        high_column: str = "high",
        low_column: str = "low",
        close_column: str = "close",
        volume_column: str = "volume",
    ) -> IndicatorResult:
        """
        Compute rolling VWAP over full high/low/close/volume history.

        Parameters
        ----------
        data:
            A ``pandas.DataFrame`` containing the four price/volume
            columns. Mutually exclusive with passing the arrays directly.
        high, low, close, volume:
            Individual arrays used when ``data`` is not a DataFrame.

        Returns
        -------
        IndicatorResult
            Same length as input; first ``period - 1`` values are ``NaN``.
        """
        if isinstance(data, pd.DataFrame):
            high_arr = to_numpy_1d(data, column=high_column, name="high")
            low_arr = to_numpy_1d(data, column=low_column, name="low")
            close_arr = to_numpy_1d(data, column=close_column, name="close")
            volume_arr = to_numpy_1d(data, column=volume_column, name="volume")
            index = get_index(data)
        elif high is not None and low is not None and close is not None and volume is not None:
            high_arr = to_numpy_1d(high, name="high")
            low_arr = to_numpy_1d(low, name="low")
            close_arr = to_numpy_1d(close, name="close")
            volume_arr = to_numpy_1d(volume, name="volume")
            index = get_index(high)
        else:
            raise IndicatorValidationError(
                "VWAP.calculate requires either a DataFrame via 'data' or "
                "'high', 'low', 'close' and 'volume' arrays"
            )

        if not (high_arr.shape[0] == low_arr.shape[0] == close_arr.shape[0] == volume_arr.shape[0]):
            raise IndicatorValidationError("high, low, close and volume must have equal length")

        validate_min_length(high_arr, self.period, name="high/low/close/volume")

        typical = (high_arr + low_arr + close_arr) / 3.0
        tp_vol = typical * volume_arr

        n = high_arr.shape[0]
        out = np.full(n, np.nan, dtype=float)

        tp_vol_cumsum = np.cumsum(np.insert(tp_vol, 0, 0.0))
        vol_cumsum = np.cumsum(np.insert(volume_arr, 0, 0.0))
        window_tp_vol = tp_vol_cumsum[self.period:] - tp_vol_cumsum[:-self.period]
        window_vol = vol_cumsum[self.period:] - vol_cumsum[:-self.period]

        with np.errstate(invalid="ignore", divide="ignore"):
            out[self.period - 1:] = np.where(window_vol != 0, window_tp_vol / window_vol, np.nan)

        return IndicatorResult(
            name=self.name,
            values=out,
            index=index,
            metadata={"period": self.period},
        )

    def update(self, high: float, low: float, close: float, volume: float) -> Optional[float]:
        """
        Feed a single new (high, low, close, volume) observation and
        return the current rolling VWAP.

        Returns
        -------
        float or None
            ``None`` until ``period`` observations have been accumulated.
        """
        high, low, close, volume = float(high), float(low), float(close), float(volume)
        typical = (high + low + close) / 3.0
        self._tp_vol.append(typical * volume)
        self._vol.append(volume)
        if len(self._vol) < self.period:
            return None

        total_vol = sum(self._vol)
        if total_vol == 0:
            return np.nan
        return sum(self._tp_vol) / total_vol
