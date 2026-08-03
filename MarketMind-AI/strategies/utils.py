"""
strategies/utils.py

Shared, dependency-light helpers used across the Strategy Engine
foundation (`strategies/base_strategy.py`, `strategies/context.py`,
`strategies/result.py`).

Keeping validation/formatting helpers here means every strategy,
`StrategyResult`, and `StrategyContext` validates and formats values in
exactly the same way, mirroring the role `analysis/utils.py` plays for
`analysis`, `signals/utils.py` plays for `signals`, and `strategies.
risk_management.utils` plays for the Risk Engine.

No trading-decision logic, no position sizing, no order-execution, and
no AI logic lives here -- only generic validation and small pure
helpers.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from core.enums import SignalDirection

from strategies.exceptions import StrategyValidationError


def validate_non_empty_str(value: str, *, name: str) -> str:
    """
    Validate that `value` is a non-empty (non-whitespace-only) string.

    Raises:
        StrategyValidationError: If `value` is not a `str`, or is empty
            after stripping whitespace.
    """
    if not isinstance(value, str) or not value.strip():
        raise StrategyValidationError(f"{name} must be a non-empty string, got {value!r}")
    return value


def validate_unit_range(value: float, *, name: str) -> float:
    """
    Validate that `value` is a finite, non-boolean real number within
    the closed range [0.0, 1.0].

    Used by `StrategyResult.confidence`, the same [0.0, 1.0] scale
    `analysis.result.AnalysisResult`, `signals.result.SignalResult`,
    and `strategies.risk_management.result.RiskResult` all use for
    their own confidence-like fields.

    Raises:
        StrategyValidationError: If `value` is not numeric, not finite,
            or outside of [0.0, 1.0].
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StrategyValidationError(f"{name} must be numeric, got {type(value).__name__}")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise StrategyValidationError(f"{name} must be finite, got {numeric_value}")
    if not (0.0 <= numeric_value <= 1.0):
        raise StrategyValidationError(f"{name} must be within [0.0, 1.0], got {numeric_value}")
    return numeric_value


def validate_action(value: Any, *, name: str = "action") -> SignalDirection:
    """
    Validate that `value` is a `core.enums.SignalDirection` member.

    `StrategyResult.action` reuses `SignalDirection` rather than
    inventing a new enum, the same convention `signals.result.
    SignalResult.direction` follows.

    Raises:
        StrategyValidationError: If `value` is not a `SignalDirection`.
    """
    if not isinstance(value, SignalDirection):
        raise StrategyValidationError(
            f"{name} must be a SignalDirection, got {type(value).__name__}"
        )
    return value


def validate_instance_list(values: Any, expected_type: type, *, name: str) -> list:
    """
    Validate that `values` is a `list` whose items are all instances of `expected_type`.

    Raises:
        StrategyValidationError: If `values` is not a `list`, or
            contains an item that is not an instance of `expected_type`.
    """
    if not isinstance(values, list):
        raise StrategyValidationError(f"{name} must be a list, got {type(values).__name__}")
    for index, item in enumerate(values):
        if not isinstance(item, expected_type):
            raise StrategyValidationError(
                f"{name}[{index}] must be a {expected_type.__name__}, "
                f"got {type(item).__name__}"
            )
    return values


def clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """
    Clamp `value` into the closed range [`low`, `high`].

    Generic numeric helper (mirrors `analysis.technical.utils.clip`'s
    and `strategies.risk_management.utils.clip`'s role) available to
    future concrete strategies that need to keep derived sub-scores
    within a well-defined range.
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
