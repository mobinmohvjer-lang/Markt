"""
strategies/portfolio_management/utils.py

Shared, dependency-light helpers used across the
`strategies.portfolio_management` package.

Keeping validation/formatting helpers here means every portfolio
manager, `PortfolioResult`, and `PortfolioContext` validates and
formats values in exactly the same way, mirroring the role
`analysis/utils.py` plays for `analysis`, `signals/utils.py` plays for
`signals`, `strategies/utils.py` plays for the Strategy Engine, and
`strategies/risk_management/utils.py` plays for the Risk Engine.

No allocation logic, no rebalancing, no optimization, no
broker/order-execution, and no AI logic lives here -- only generic
validation and small pure helpers.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from strategies.portfolio_management.exceptions import PortfolioValidationError


def validate_non_empty_str(value: str, *, name: str) -> str:
    """
    Validate that `value` is a non-empty (non-whitespace-only) string.

    Raises:
        PortfolioValidationError: If `value` is not a `str`, or is
            empty after stripping whitespace.
    """
    if not isinstance(value, str) or not value.strip():
        raise PortfolioValidationError(f"{name} must be a non-empty string, got {value!r}")
    return value


def validate_unit_range(value: float, *, name: str) -> float:
    """
    Validate that `value` is a finite, non-boolean real number within
    the closed range [0.0, 1.0].

    Shared by `PortfolioResult.confidence` and any future concrete
    portfolio manager's own [0.0, 1.0]-scaled sub-scores, the same
    scale `AnalysisResult`/`SignalResult`/`RiskResult`/`StrategyResult`
    all use for their own confidence-like fields.

    Raises:
        PortfolioValidationError: If `value` is not numeric, not
            finite, or outside of [0.0, 1.0].
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PortfolioValidationError(f"{name} must be numeric, got {type(value).__name__}")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise PortfolioValidationError(f"{name} must be finite, got {numeric_value}")
    if not (0.0 <= numeric_value <= 1.0):
        raise PortfolioValidationError(f"{name} must be within [0.0, 1.0], got {numeric_value}")
    return numeric_value


def validate_bool(value: Any, *, name: str) -> bool:
    """
    Validate that `value` is a genuine `bool`.

    Raises:
        PortfolioValidationError: If `value` is not a `bool`.
    """
    if not isinstance(value, bool):
        raise PortfolioValidationError(f"{name} must be a bool, got {type(value).__name__}")
    return value


def clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """
    Clamp `value` into the closed range [`low`, `high`].

    Generic numeric helper (mirrors `analysis.technical.utils.clip`'s,
    `strategies.utils.clip`'s, and `strategies.risk_management.utils.
    clip`'s role) available to future concrete portfolio managers that
    need to keep derived sub-scores within a well-defined range.
    """
    if value < low:
        return low
    if value > high:
        return high
    return value


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
