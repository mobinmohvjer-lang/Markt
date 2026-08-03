"""Directional Movement Index (DMI): +DI and -DI."""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from .base import BaseIndicator, IndicatorResult
from .utils import IndicatorValidationError, get_index, to_numpy_1d, validate_min_length


class DMI(BaseIndicator):
    """
    Directional Movement Index.

    Computes the smoothed positive (+DI) and negative (-DI) directional
    indicators using Wilder's smoothing, the basis for :class:`ADX`.

    Parameters
    ----------
    period:
        Smoothing period. Must be >= 1.
    """

    def __init__(self, period: int = 14) -> None:
        super().__init__(period, min_period=1)

    def _reset_state(self) -> None:
        self._prev_high: Optional[float] = None
        self._prev_low: Optional[float] = None
        self._prev_close: Optional[float] = None
        self._smoothed_tr: Optional[float] = None
        self._smoothed_plus_dm: Optional[float] = None
        self._smoothed_minus_dm: Optional[float] = None
        self._seed_tr: list = []
        self._seed_plus_dm: list = []
        self._seed_minus_dm: list = []

    @staticmethod
    def _directional_movement(high_arr: np.ndarray, low_arr: np.ndarray, close_arr: np.ndarray):
        n = high_arr.shape[0]
        tr = np.empty(n, dtype=float)
        tr[0] = high_arr[0] - low_arr[0]
        prev_close = close_arr[:-1]
        tr[1:] = np.maximum(
            high_arr[1:] - low_arr[1:],
            np.maximum(np.abs(high_arr[1:] - prev_close), np.abs(low_arr[1:] - prev_close)),
        )

        up_move = np.empty(n, dtype=float)
        down_move = np.empty(n, dtype=float)
        up_move[0] = 0.0
        down_move[0] = 0.0
        up_move[1:] = high_arr[1:] - high_arr[:-1]
        down_move[1:] = low_arr[:-1] - low_arr[1:]

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        plus_dm[0] = 0.0
        minus_dm[0] = 0.0
        return tr, plus_dm, minus_dm

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
        Compute +DI/-DI over the full high/low/close history.

        Returns
        -------
        IndicatorResult
            Multi-output result with keys ``"plus_di"`` and ``"minus_di"``.
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
                "DMI.calculate requires either a DataFrame via 'data' or 'high', 'low' and 'close' arrays"
            )

        if not (high_arr.shape[0] == low_arr.shape[0] == close_arr.shape[0]):
            raise IndicatorValidationError("high, low and close must have equal length")

        validate_min_length(high_arr, self.period + 1, name="high/low/close")

        n = high_arr.shape[0]
        tr, plus_dm, minus_dm = self._directional_movement(high_arr, low_arr, close_arr)

        plus_di = np.full(n, np.nan, dtype=float)
        minus_di = np.full(n, np.nan, dtype=float)

        smoothed_tr = tr[1:self.period + 1].sum()
        smoothed_plus_dm = plus_dm[1:self.period + 1].sum()
        smoothed_minus_dm = minus_dm[1:self.period + 1].sum()

        idx = self.period
        with np.errstate(invalid="ignore", divide="ignore"):
            plus_di[idx] = 100 * (smoothed_plus_dm / smoothed_tr) if smoothed_tr else np.nan
            minus_di[idx] = 100 * (smoothed_minus_dm / smoothed_tr) if smoothed_tr else np.nan

        for i in range(self.period + 1, n):
            smoothed_tr = smoothed_tr - smoothed_tr / self.period + tr[i]
            smoothed_plus_dm = smoothed_plus_dm - smoothed_plus_dm / self.period + plus_dm[i]
            smoothed_minus_dm = smoothed_minus_dm - smoothed_minus_dm / self.period + minus_dm[i]
            with np.errstate(invalid="ignore", divide="ignore"):
                plus_di[i] = 100 * (smoothed_plus_dm / smoothed_tr) if smoothed_tr else np.nan
                minus_di[i] = 100 * (smoothed_minus_dm / smoothed_tr) if smoothed_tr else np.nan

        values: Dict[str, np.ndarray] = {"plus_di": plus_di, "minus_di": minus_di}
        return self._make_result(values, data if isinstance(data, pd.DataFrame) else high)

    def update(self, high: float, low: float, close: float) -> Optional[Dict[str, float]]:
        """
        Feed a single new (high, low, close) observation and return the
        current +DI/-DI.

        Returns
        -------
        dict or None
            ``{"plus_di": ..., "minus_di": ...}`` once enough history has
            accumulated, otherwise ``None``.
        """
        high, low, close = float(high), float(low), float(close)

        if self._prev_close is None:
            self._prev_high, self._prev_low, self._prev_close = high, low, close
            return None

        tr = max(
            high - low,
            abs(high - self._prev_close),
            abs(low - self._prev_close),
        )
        up_move = high - self._prev_high
        down_move = self._prev_low - low
        plus_dm = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm = down_move if (down_move > up_move and down_move > 0) else 0.0

        self._prev_high, self._prev_low, self._prev_close = high, low, close

        if self._smoothed_tr is None:
            self._seed_tr.append(tr)
            self._seed_plus_dm.append(plus_dm)
            self._seed_minus_dm.append(minus_dm)
            if len(self._seed_tr) < self.period:
                return None
            self._smoothed_tr = sum(self._seed_tr)
            self._smoothed_plus_dm = sum(self._seed_plus_dm)
            self._smoothed_minus_dm = sum(self._seed_minus_dm)
        else:
            self._smoothed_tr = self._smoothed_tr - self._smoothed_tr / self.period + tr
            self._smoothed_plus_dm = self._smoothed_plus_dm - self._smoothed_plus_dm / self.period + plus_dm
            self._smoothed_minus_dm = self._smoothed_minus_dm - self._smoothed_minus_dm / self.period + minus_dm

        if not self._smoothed_tr:
            return {"plus_di": float("nan"), "minus_di": float("nan")}
        return {
            "plus_di": 100 * self._smoothed_plus_dm / self._smoothed_tr,
            "minus_di": 100 * self._smoothed_minus_dm / self._smoothed_tr,
        }
