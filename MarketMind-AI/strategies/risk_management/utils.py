"""
strategies/risk_management/utils.py

Shared, dependency-light helpers used across the
`strategies.risk_management` package.

Keeping validation/formatting helpers here means every risk manager,
`RiskResult`, and `RiskContext` validates and formats values in exactly
the same way, mirroring the role `analysis/utils.py` plays for
`analysis` and `signals/utils.py` plays for `signals`.

No position sizing, no stop-loss/take-profit, no order-execution, and
no trading/AI logic lives here -- only generic validation and small
pure helpers.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from strategies.risk_management.exceptions import RiskValidationError


def validate_non_empty_str(value: str, *, name: str) -> str:
    """
    Validate that `value` is a non-empty (non-whitespace-only) string.

    Raises:
        RiskValidationError: If `value` is not a `str`, or is empty
            after stripping whitespace.
    """
    if not isinstance(value, str) or not value.strip():
        raise RiskValidationError(f"{name} must be a non-empty string, got {value!r}")
    return value


def validate_unit_range(value: float, *, name: str) -> float:
    """
    Validate that `value` is a finite, non-boolean real number within
    the closed range [0.0, 1.0].

    Shared by `RiskResult.risk_score` and `RiskResult.confidence`, both
    of which use the same [0.0, 1.0] scale (`risk_score`: `0.0` no
    risk .. `1.0` maximum risk; `confidence`: how sure the risk manager
    is in that assessment).

    Raises:
        RiskValidationError: If `value` is not numeric, not finite, or
            outside of [0.0, 1.0].
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RiskValidationError(f"{name} must be numeric, got {type(value).__name__}")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise RiskValidationError(f"{name} must be finite, got {numeric_value}")
    if not (0.0 <= numeric_value <= 1.0):
        raise RiskValidationError(f"{name} must be within [0.0, 1.0], got {numeric_value}")
    return numeric_value


def validate_bool(value: Any, *, name: str) -> bool:
    """
    Validate that `value` is a genuine `bool`.

    Raises:
        RiskValidationError: If `value` is not a `bool`.
    """
    if not isinstance(value, bool):
        raise RiskValidationError(f"{name} must be a bool, got {type(value).__name__}")
    return value


def clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """
    Clamp `value` into the closed range [`low`, `high`].

    Generic numeric helper (mirrors `analysis.technical.utils.clip`'s
    role one layer up) used by concrete risk managers to keep derived
    sub-scores within a well-defined range without repeating
    `min(high, max(low, value))` everywhere.
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
