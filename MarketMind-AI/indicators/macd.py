"""Moving Average Convergence Divergence (MACD)."""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from .base import BaseIndicator, IndicatorResult
from .ema import EMA
from .utils import ArrayLike, IndicatorValidationError, to_numpy_1d, validate_min_length, validate_period


class MACD(BaseIndicator):
    """
    Moving Average Convergence Divergence.

    A trend-following momentum indicator computed as the difference
    between a fast and a slow EMA (the "MACD line"), together with an
    EMA of that difference (the "signal line") and their difference
    (the "histogram").

    Parameters
    ----------
    fast_period:
        Period of the fast EMA. Default 12.
    slow_period:
        Period of the slow EMA. Must be greater than ``fast_period``.
        Default 26.
    signal_period:
        Period of the EMA applied to the MACD line. Default 9.
    """

    def __init__(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> None:
        fast_period = validate_period(fast_period, min_period=1, name="fast_period")
        slow_period = validate_period(slow_period, min_period=1, name="slow_period")
        signal_period = validate_period(signal_period, min_period=1, name="signal_period")
        if slow_period <= fast_period:
            raise IndicatorValidationError(
                f"slow_period ({slow_period}) must be greater than fast_period ({fast_period})"
            )
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        # `period` on the base class represents the total warm-up requirement.
        super().__init__(slow_period, min_period=1)
        self.name = f"MACD_{fast_period}_{slow_period}_{signal_period}"

    def _reset_state(self) -> None:
        self._ema_fast = EMA(self.fast_period)
        self._ema_slow = EMA(self.slow_period)
        self._ema_signal = EMA(self.signal_period)

    def calculate(self, data: ArrayLike, *, column: Optional[str] = None) -> IndicatorResult:
        """
        Compute MACD line, signal line and histogram over the full input.

        Returns
        -------
        IndicatorResult
            Multi-output result with keys ``"macd"``, ``"signal"`` and
            ``"histogram"``, each the same length as the input.
        """
        arr = to_numpy_1d(data, column=column, name="data")
        validate_min_length(arr, self.slow_period, name="data")

        ema_fast = EMA(self.fast_period).calculate(arr).to_numpy()
        ema_slow = EMA(self.slow_period).calculate(arr).to_numpy()
        macd_line = ema_fast - ema_slow

        n = arr.shape[0]
        signal_line = np.full(n, np.nan, dtype=float)
        valid_start = self.slow_period - 1
        valid_macd = macd_line[valid_start:]

        if valid_macd.shape[0] >= self.signal_period:
            signal_valid = EMA(self.signal_period).calculate(valid_macd).to_numpy()
            signal_line[valid_start:] = signal_valid

        histogram = macd_line - signal_line

        values: Dict[str, np.ndarray] = {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram,
        }
        return self._make_result(
            values, data,
            fast_period=self.fast_period,
            slow_period=self.slow_period,
            signal_period=self.signal_period,
        )

    def update(self, value: float) -> Optional[Dict[str, float]]:
        """
        Feed a single new value and return the current MACD components.

        Returns
        -------
        dict or None
            ``{"macd": ..., "signal": ..., "histogram": ...}`` once enough
            history exists to compute the signal line, otherwise ``None``.
        """
        value = float(value)
        fast_val = self._ema_fast.update(value)
        slow_val = self._ema_slow.update(value)

        if fast_val is None or slow_val is None:
            return None

        macd_val = fast_val - slow_val
        signal_val = self._ema_signal.update(macd_val)

        if signal_val is None:
            return None

        return {
            "macd": macd_val,
            "signal": signal_val,
            "histogram": macd_val - signal_val,
        }
