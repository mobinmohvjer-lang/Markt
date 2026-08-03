"""Average True Range (ATR)."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .base import BaseIndicator, IndicatorResult
from .utils import (
    IndicatorValidationError,
    get_index,
    to_numpy_1d,
    validate_min_length,
)


class ATR(BaseIndicator):
    """
    Average True Range, using Wilder's smoothing method.

    Measures volatility by averaging the True Range, which accounts
    for gaps between the previous close and the current high/low.

    Parameters
    ----------
    period:
        Smoothing period. Must be >= 1.
    """

    def __init__(self, period: int = 14) -> None:
        super().__init__(period, min_period=1)

    def _reset_state(self) -> None:
        self._prev_close: Optional[float] = None
        self._prev_atr: Optional[float] = None
        self._seed_trs: list = []

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
        Compute the ATR over full high/low/close history.

        Parameters
        ----------
        data:
            A ``pandas.DataFrame`` containing ``high_column``,
            ``low_column`` and ``close_column``. Mutually exclusive with
            passing ``high``/``low``/``close`` directly.
        high, low, close:
            Individual price arrays (list, ndarray, or Series) used when
            ``data`` is not a DataFrame.

        Returns
        -------
        IndicatorResult
            Same length as input; first ``period - 1`` values are ``NaN``.
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
                "ATR.calculate requires either a DataFrame via 'data' or "
                "'high', 'low' and 'close' arrays"
            )

        if not (high_arr.shape[0] == low_arr.shape[0] == close_arr.shape[0]):
            raise IndicatorValidationError("high, low and close must have equal length")
        validate_min_length(high_arr, self.period, name="high/low/close")

        n = high_arr.shape[0]
        tr = np.empty(n, dtype=float)
        tr[0] = high_arr[0] - low_arr[0]
        prev_close = close_arr[:-1]
        tr[1:] = np.maximum(
            high_arr[1:] - low_arr[1:],
            np.maximum(
                np.abs(high_arr[1:] - prev_close),
                np.abs(low_arr[1:] - prev_close),
            ),
        )

        out = np.full(n, np.nan, dtype=float)
        atr = tr[: self.period].mean()
        out[self.period - 1] = atr
        for i in range(self.period, n):
            atr = (atr * (self.period - 1) + tr[i]) / self.period
            out[i] = atr

        result = IndicatorResult(
            name=self.name,
            values=out,
            index=index,
            metadata={"period": self.period},
        )
        return result

    def update(self, high: float, low: float, close: float) -> Optional[float]:
        """
        Feed a single new (high, low, close) observation and return the ATR.

        Returns
        -------
        float or None
            ``None`` until ``period`` true-range observations have been
            accumulated.
        """
        high, low, close = float(high), float(low), float(close)

        if self._prev_close is None:
            tr = high - low
        else:
            tr = max(
                high - low,
                abs(high - self._prev_close),
                abs(low - self._prev_close),
            )
        self._prev_close = close

        if self._prev_atr is None:
            self._seed_trs.append(tr)
            if len(self._seed_trs) < self.period:
                return None
            self._prev_atr = sum(self._seed_trs) / self.period
            return self._prev_atr

        self._prev_atr = (self._prev_atr * (self.period - 1) + tr) / self.period
        return self._prev_atr
