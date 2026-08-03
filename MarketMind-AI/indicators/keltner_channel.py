"""Keltner Channel."""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from .atr import ATR
from .base import BaseIndicator, IndicatorResult
from .ema import EMA
from .utils import IndicatorValidationError, get_index, to_numpy_1d, validate_min_length, validate_period


class KeltnerChannel(BaseIndicator):
    """
    Keltner Channel.

    A volatility envelope built from an EMA middle line plus/minus a
    multiple of the Average True Range.

    Parameters
    ----------
    period:
        EMA period for the middle line. Must be >= 1.
    atr_period:
        Period used for the ATR band width. Must be >= 1. Default 10.
    multiplier:
        Number of ATRs for the band offset. Default 2.0.
    """

    def __init__(self, period: int = 20, atr_period: int = 10, multiplier: float = 2.0) -> None:
        self.atr_period = validate_period(atr_period, min_period=1, name="atr_period")
        if multiplier <= 0:
            raise IndicatorValidationError(f"multiplier must be > 0, got {multiplier}")
        self.multiplier = float(multiplier)
        super().__init__(period, min_period=1)

    def _reset_state(self) -> None:
        self._ema = EMA(self.period)
        self._atr = ATR(self.atr_period)

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
        Compute the Keltner Channel over the full high/low/close history.

        Returns
        -------
        IndicatorResult
            Multi-output result with keys ``"middle"``, ``"upper"`` and
            ``"lower"``.
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
                "KeltnerChannel.calculate requires either a DataFrame via 'data' or "
                "'high', 'low' and 'close' arrays"
            )

        if not (high_arr.shape[0] == low_arr.shape[0] == close_arr.shape[0]):
            raise IndicatorValidationError("high, low and close must have equal length")

        validate_min_length(high_arr, max(self.period, self.atr_period), name="high/low/close")

        middle = EMA(self.period).calculate(close_arr).to_numpy()
        atr_vals = ATR(self.atr_period).calculate(high=high_arr, low=low_arr, close=close_arr).to_numpy()

        upper = middle + self.multiplier * atr_vals
        lower = middle - self.multiplier * atr_vals

        values: Dict[str, np.ndarray] = {"middle": middle, "upper": upper, "lower": lower}
        return self._make_result(
            values, data if isinstance(data, pd.DataFrame) else high,
            atr_period=self.atr_period, multiplier=self.multiplier,
        )

    def update(self, high: float, low: float, close: float) -> Optional[Dict[str, float]]:
        """
        Feed a single new (high, low, close) observation and return the
        current channel.

        Returns
        -------
        dict or None
            ``{"middle": ..., "upper": ..., "lower": ...}`` once both the
            EMA and ATR have warmed up, otherwise ``None``.
        """
        middle = self._ema.update(close)
        atr_val = self._atr.update(high, low, close)
        if middle is None or atr_val is None:
            return None
        return {
            "middle": middle,
            "upper": middle + self.multiplier * atr_val,
            "lower": middle - self.multiplier * atr_val,
        }
