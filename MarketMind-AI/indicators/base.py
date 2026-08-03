"""
Base abstractions for the Indicators module.

Defines:
    * :class:`IndicatorResult` - a uniform container for indicator output,
      supporting both single-series indicators (SMA, EMA, ...) and
      multi-series indicators (MACD, which produces a macd line, a
      signal line and a histogram).
    * :class:`BaseIndicator` - the abstract base every concrete indicator
      implements, defining the common batch/incremental interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional, Union

import numpy as np
import pandas as pd

from .utils import ArrayLike, get_index, validate_period

#: Values held by an IndicatorResult: either a single array (e.g. SMA)
#: or a mapping of named arrays (e.g. MACD -> macd/signal/histogram).
ResultValues = Union[np.ndarray, Dict[str, np.ndarray]]


class IndicatorResult:
    """
    Container for the output of an indicator calculation.

    Parameters
    ----------
    name:
        Name of the indicator (e.g. ``"SMA_20"``).
    values:
        Either a 1-D ``numpy.ndarray`` (single-output indicators) or a
        ``dict`` mapping output name -> 1-D ``numpy.ndarray``
        (multi-output indicators such as MACD).
    index:
        Optional pandas index to associate with the values, propagated
        from a ``pandas.Series``/``pandas.DataFrame`` input.
    metadata:
        Optional dictionary of extra information (e.g. parameters used).
    """

    __slots__ = ("name", "values", "index", "metadata")

    def __init__(
        self,
        name: str,
        values: ResultValues,
        index: Optional[pd.Index] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        self.name = name
        self.values = values
        self.index = index
        self.metadata = metadata or {}

    @property
    def is_multi_output(self) -> bool:
        """Whether this result wraps multiple named arrays."""
        return isinstance(self.values, dict)

    def to_numpy(self) -> ResultValues:
        """Return the raw numpy representation (ndarray or dict of ndarrays)."""
        return self.values

    def to_series(self) -> pd.Series:
        """
        Return a single ``pandas.Series`` for single-output results.

        Raises
        ------
        TypeError
            If called on a multi-output result; use :meth:`to_dataframe`
            instead.
        """
        if self.is_multi_output:
            raise TypeError(
                f"'{self.name}' has multiple outputs; use to_dataframe() instead"
            )
        return pd.Series(self.values, index=self.index, name=self.name)

    def to_dataframe(self) -> pd.DataFrame:
        """Return the result as a ``pandas.DataFrame`` (works for both cases)."""
        if self.is_multi_output:
            return pd.DataFrame(self.values, index=self.index)
        return pd.DataFrame({self.name: self.values}, index=self.index)

    def __len__(self) -> int:
        if self.is_multi_output:
            return len(next(iter(self.values.values())))
        return len(self.values)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        outputs = list(self.values.keys()) if self.is_multi_output else [self.name]
        return f"IndicatorResult(name={self.name!r}, outputs={outputs}, length={len(self)})"


class BaseIndicator(ABC):
    """
    Abstract base class for all technical indicators.

    Every concrete indicator supports two calculation modes:

    * **Batch** (:meth:`calculate`): compute the indicator over an entire
      historical array/Series/DataFrame at once, returning an
      :class:`IndicatorResult` the same length as the input (warm-up
      positions are filled with ``NaN``).
    * **Incremental** (:meth:`update`): feed a single new data point (or
      tuple of points, for multi-input indicators like ATR) and receive
      the indicator's latest value, maintaining internal state between
      calls. This is intended for streaming/online use.

    Attributes
    ----------
    period:
        The lookback period used by the indicator.
    name:
        Human readable name of the indicator instance (e.g. ``"SMA_20"``).
    """

    def __init__(self, period: int, *, min_period: int = 1) -> None:
        self.period = validate_period(period, min_period=min_period)
        self.name = f"{self.__class__.__name__}_{self.period}"
        self._reset_state()

    # ------------------------------------------------------------------
    # Abstract API
    # ------------------------------------------------------------------
    @abstractmethod
    def _reset_state(self) -> None:
        """Initialize/reset all internal incremental-calculation state."""
        raise NotImplementedError

    @abstractmethod
    def calculate(self, data: ArrayLike, **kwargs) -> IndicatorResult:
        """Compute the indicator over a full array/Series/DataFrame (batch mode)."""
        raise NotImplementedError

    @abstractmethod
    def update(self, value, **kwargs) -> Optional[float]:
        """
        Feed one new observation and return the updated indicator value.

        Returns ``None`` while still in the warm-up period (i.e. fewer
        than ``period`` observations have been seen).
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Reset all incremental state, as if no data had been seen."""
        self._reset_state()

    def _make_result(self, values: ResultValues, data: ArrayLike, **metadata) -> IndicatorResult:
        """Helper to build an :class:`IndicatorResult` carrying the source index."""
        return IndicatorResult(
            name=self.name,
            values=values,
            index=get_index(data),
            metadata={"period": self.period, **metadata},
        )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(period={self.period})"
