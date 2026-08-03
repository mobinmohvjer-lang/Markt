"""
Utility helpers for the Indicators module.

This module centralizes:
    * Input validation (periods, array lengths, numeric content)
    * Conversion between the array-like types the indicators accept
      (``list``, ``tuple``, ``numpy.ndarray``, ``pandas.Series``,
      ``pandas.DataFrame``) and plain ``numpy.ndarray`` objects used
      internally for computation.

Keeping this logic in one place means every indicator validates and
parses its input in exactly the same way.
"""

from __future__ import annotations

from typing import Optional, Sequence, Union

import numpy as np
import pandas as pd

# Type alias for anything an indicator is willing to accept as input.
ArrayLike = Union[Sequence[float], np.ndarray, pd.Series, pd.DataFrame]


class IndicatorValidationError(ValueError):
    """Raised when indicator input fails validation."""


def validate_period(period: int, *, min_period: int = 1, name: str = "period") -> int:
    """
    Validate that ``period`` is an integer greater than or equal to ``min_period``.

    Parameters
    ----------
    period:
        The period value to validate.
    min_period:
        The minimum allowed value (inclusive).
    name:
        Name of the parameter, used in the error message.

    Returns
    -------
    int
        The validated period.

    Raises
    ------
    IndicatorValidationError
        If ``period`` is not an integer or is smaller than ``min_period``.
    """
    if isinstance(period, bool) or not isinstance(period, (int, np.integer)):
        raise IndicatorValidationError(f"{name} must be an int, got {type(period).__name__}")
    if period < min_period:
        raise IndicatorValidationError(f"{name} must be >= {min_period}, got {period}")
    return int(period)


def validate_positive_number(value: float, *, name: str) -> float:
    """Validate that ``value`` is a positive, finite number."""
    if not isinstance(value, (int, float, np.integer, np.floating)):
        raise IndicatorValidationError(f"{name} must be numeric, got {type(value).__name__}")
    if not np.isfinite(value):
        raise IndicatorValidationError(f"{name} must be finite, got {value}")
    if value <= 0:
        raise IndicatorValidationError(f"{name} must be > 0, got {value}")
    return float(value)


def to_numpy_1d(data: ArrayLike, *, column: Optional[str] = None, name: str = "data") -> np.ndarray:
    """
    Convert supported array-like input to a 1-D ``numpy.ndarray`` of floats.

    Parameters
    ----------
    data:
        One of ``list``, ``tuple``, ``numpy.ndarray``, ``pandas.Series`` or
        ``pandas.DataFrame`` (in which case ``column`` must be provided).
    column:
        Column name to extract when ``data`` is a ``pandas.DataFrame``.
    name:
        Name used in error messages.

    Returns
    -------
    numpy.ndarray
        1-D float64 array.

    Raises
    ------
    IndicatorValidationError
        If the input type is unsupported, empty, not 1-D, or contains
        non-numeric values.
    """
    if isinstance(data, pd.DataFrame):
        if column is None:
            raise IndicatorValidationError(
                f"'{name}' is a DataFrame; a 'column' name must be provided"
            )
        if column not in data.columns:
            raise IndicatorValidationError(f"column '{column}' not found in DataFrame")
        arr = data[column].to_numpy(dtype=float)
    elif isinstance(data, pd.Series):
        arr = data.to_numpy(dtype=float)
    elif isinstance(data, np.ndarray):
        arr = data.astype(float, copy=False)
    elif isinstance(data, (list, tuple)):
        arr = np.asarray(data, dtype=float)
    else:
        raise IndicatorValidationError(
            f"Unsupported type for '{name}': {type(data).__name__}. "
            "Expected list, tuple, numpy.ndarray, pandas.Series or pandas.DataFrame."
        )

    if arr.ndim != 1:
        raise IndicatorValidationError(f"'{name}' must be 1-D, got shape {arr.shape}")
    if arr.size == 0:
        raise IndicatorValidationError(f"'{name}' must not be empty")
    if np.isnan(arr).all():
        raise IndicatorValidationError(f"'{name}' contains only NaN values")
    return arr


def validate_min_length(arr: np.ndarray, min_length: int, *, name: str = "data") -> None:
    """Validate that ``arr`` has at least ``min_length`` elements."""
    if arr.size < min_length:
        raise IndicatorValidationError(
            f"'{name}' must contain at least {min_length} element(s), got {arr.size}"
        )


def get_index(data: ArrayLike) -> Optional[pd.Index]:
    """Return the pandas index of ``data`` if it has one, otherwise ``None``."""
    if isinstance(data, (pd.Series, pd.DataFrame)):
        return data.index
    return None


def rolling_window_view(arr: np.ndarray, window: int) -> np.ndarray:
    """
    Return a 2-D sliding-window view over ``arr``.

    Row ``i`` of the result is ``arr[i:i + window]``. There are
    ``len(arr) - window + 1`` rows.
    """
    if window > arr.shape[0]:
        raise IndicatorValidationError(
            f"window ({window}) cannot exceed array length ({arr.shape[0]})"
        )
    return np.lib.stride_tricks.sliding_window_view(arr, window)
