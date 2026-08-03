"""
backtesting/utils.py

Shared, dependency-light helpers used across the Backtesting Engine
foundation (`backtesting/base.py`, `backtesting/context.py`,
`backtesting/result.py`).

Keeping validation/formatting helpers here means every backtester,
`BacktestContext`, and `BacktestResult` validates and formats values in
exactly the same way, mirroring the role `analysis/utils.py`,
`signals/utils.py`, `strategies/utils.py`, and
`strategies/risk_management/utils.py` each play for their own package.

No trade simulation, no PnL calculation, no performance-statistics
logic, and no aggregation lives here -- only generic validation and
small pure helpers.
"""

from __future__ import annotations

from typing import Any, Optional

from core.entities.candle import Candle

from backtesting.exceptions import BacktestValidationError


def validate_non_empty_str(value: str, *, name: str) -> str:
    """
    Validate that `value` is a non-empty (non-whitespace-only) string.

    Raises:
        BacktestValidationError: If `value` is not a `str`, or is empty
            after stripping whitespace.
    """
    if not isinstance(value, str) or not value.strip():
        raise BacktestValidationError(f"{name} must be a non-empty string, got {value!r}")
    return value


def validate_instance_list(values: Any, expected_type: type, *, name: str) -> list:
    """
    Validate that `values` is a `list` whose items are all instances of `expected_type`.

    Raises:
        BacktestValidationError: If `values` is not a `list`, or
            contains an item that is not an instance of `expected_type`.
    """
    if not isinstance(values, list):
        raise BacktestValidationError(f"{name} must be a list, got {type(values).__name__}")
    for index, item in enumerate(values):
        if not isinstance(item, expected_type):
            raise BacktestValidationError(
                f"{name}[{index}] must be a {expected_type.__name__}, "
                f"got {type(item).__name__}"
            )
    return values


def validate_chronological_candles(candles: list[Candle], *, name: str = "candles") -> list[Candle]:
    """
    Validate that `candles` is a non-empty list of `Candle` instances
    ordered from oldest to newest by `open_time`.

    This is structural validation only -- it does not interpret, clean,
    resample, or otherwise process the candles (that remains the
    responsibility of `data/` and any later Backtesting Engine part).

    Raises:
        BacktestValidationError: If `candles` is not a list, is empty,
            contains a non-`Candle` item, or is not strictly ordered by
            `open_time`.
    """
    validate_instance_list(candles, Candle, name=name)
    if not candles:
        raise BacktestValidationError(f"{name} must not be empty")
    previous = candles[0]
    for index, candle in enumerate(candles[1:], start=1):
        if candle.open_time < previous.open_time:
            raise BacktestValidationError(
                f"{name} must be ordered chronologically by open_time "
                f"({name}[{index}] precedes {name}[{index - 1}])"
            )
        previous = candle
    return candles


def merge_metadata(*sources: Optional[dict[str, Any]]) -> dict[str, Any]:
    """
    Merge any number of metadata dicts into a new dict.

    Later sources take precedence over earlier ones on key conflicts.
    `None` entries are silently skipped, so callers can pass optional
    metadata dicts directly (e.g. `merge_metadata(base_meta, extra_meta)`).
    """
    merged: dict[str, Any] = {}
    for source in sources:
        if source:
            merged.update(source)
    return merged
