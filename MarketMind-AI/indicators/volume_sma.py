"""Volume Simple Moving Average."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .base import BaseIndicator, IndicatorResult
from .sma import SMA
from .utils import IndicatorValidationError, get_index, to_numpy_1d


class VolumeSMA(BaseIndicator):
    """
    Simple Moving Average applied to trading volume.

    A thin, volume-specific wrapper around :class:`SMA`, useful for
    spotting volume spikes/dry-ups relative to their recent average.

    Parameters
    ----------
    period:
        Number of observations averaged over. Must be >= 1.
    """

    def __init__(self, period: int = 20) -> None:
        super().__init__(period, min_period=1)

    def _reset_state(self) -> None:
        self._sma = SMA(self.period)

    def calculate(
        self,
        data: Optional[pd.DataFrame] = None,
        *,
        volume=None,
        volume_column: str = "volume",
    ) -> IndicatorResult:
        """
        Compute the SMA of volume over the full input.

        Parameters
        ----------
        data:
            A ``pandas.DataFrame`` containing ``volume_column``. Mutually
            exclusive with passing ``volume`` directly.
        volume:
            Volume array (list, ndarray, or Series) used when ``data`` is
            not a DataFrame.

        Returns
        -------
        IndicatorResult
            Same length as input; first ``period - 1`` values are ``NaN``.
        """
        if isinstance(data, pd.DataFrame):
            volume_arr = to_numpy_1d(data, column=volume_column, name="volume")
            index = get_index(data)
        elif volume is not None:
            volume_arr = to_numpy_1d(volume, name="volume")
            index = get_index(volume)
        else:
            raise IndicatorValidationError(
                "VolumeSMA.calculate requires either a DataFrame via 'data' or a 'volume' array"
            )

        out = SMA(self.period).calculate(volume_arr).to_numpy()
        return IndicatorResult(
            name=self.name,
            values=out,
            index=index,
            metadata={"period": self.period},
        )

    def update(self, volume: float) -> Optional[float]:
        """
        Feed a single new volume observation and return the current
        volume SMA.

        Returns
        -------
        float or None
            The volume SMA once at least ``period`` values have been
            observed, otherwise ``None``.
        """
        return self._sma.update(float(volume))
