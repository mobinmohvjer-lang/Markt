"""On-Balance Volume (OBV)."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .base import BaseIndicator, IndicatorResult
from .utils import IndicatorValidationError, get_index, to_numpy_1d


class OBV(BaseIndicator):
    """
    On-Balance Volume.

    A cumulative volume-flow indicator: volume is added on up days,
    subtracted on down days, and left unchanged on flat days. OBV has no
    natural lookback window; ``period`` is accepted only for interface
    consistency with :class:`BaseIndicator` and defaults to 1.

    Parameters
    ----------
    period:
        Accepted for API consistency; does not affect the calculation.
        Must be >= 1.
    """

    def __init__(self, period: int = 1) -> None:
        super().__init__(period, min_period=1)

    def _reset_state(self) -> None:
        self._prev_close: Optional[float] = None
        self._obv: float = 0.0
        self._seen: bool = False

    def calculate(
        self,
        data: Optional[pd.DataFrame] = None,
        *,
        close=None,
        volume=None,
        close_column: str = "close",
        volume_column: str = "volume",
    ) -> IndicatorResult:
        """
        Compute the cumulative OBV over the full input.

        Parameters
        ----------
        data:
            A ``pandas.DataFrame`` containing ``close_column`` and
            ``volume_column``. Mutually exclusive with passing
            ``close``/``volume`` directly.
        close, volume:
            Individual arrays used when ``data`` is not a DataFrame.

        Returns
        -------
        IndicatorResult
            Same length as input; no ``NaN`` warm-up (OBV is defined from
            the first bar, seeded with that bar's volume).
        """
        if isinstance(data, pd.DataFrame):
            close_arr = to_numpy_1d(data, column=close_column, name="close")
            volume_arr = to_numpy_1d(data, column=volume_column, name="volume")
            index = get_index(data)
        elif close is not None and volume is not None:
            close_arr = to_numpy_1d(close, name="close")
            volume_arr = to_numpy_1d(volume, name="volume")
            index = get_index(close)
        else:
            raise IndicatorValidationError(
                "OBV.calculate requires either a DataFrame via 'data' or 'close' and 'volume' arrays"
            )

        if close_arr.shape[0] != volume_arr.shape[0]:
            raise IndicatorValidationError("close and volume must have equal length")

        n = close_arr.shape[0]
        out = np.empty(n, dtype=float)
        out[0] = volume_arr[0]
        direction = np.sign(np.diff(close_arr))
        signed_volume = direction * volume_arr[1:]
        out[1:] = out[0] + np.cumsum(signed_volume)

        return IndicatorResult(
            name=self.name,
            values=out,
            index=index,
            metadata={"period": self.period},
        )

    def update(self, close: float, volume: float) -> Optional[float]:
        """
        Feed a single new (close, volume) observation and return the
        running OBV.

        Returns
        -------
        float
            The updated OBV. Always defined from the first observation
            onward (never ``None``).
        """
        close, volume = float(close), float(volume)
        if not self._seen:
            self._obv = volume
            self._seen = True
        else:
            if close > self._prev_close:
                self._obv += volume
            elif close < self._prev_close:
                self._obv -= volume
        self._prev_close = close
        return self._obv
