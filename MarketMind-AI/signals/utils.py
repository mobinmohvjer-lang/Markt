"""
signals/utils.py

Shared, dependency-light helpers used across the `signals` package.

Keeping validation/formatting helpers here means every generator,
`SignalResult`, and `SignalContext` validates and formats values in
exactly the same way, mirroring the role `analysis/utils.py` plays for
the `analysis` package.

No signal-generation logic and no trading/AI logic lives here -- only
generic validation and small pure helpers.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from core.enums import SignalDirection

from signals.exceptions import SignalValidationError


def validate_non_empty_str(value: str, *, name: str) -> str:
    """
    Validate that `value` is a non-empty (non-whitespace-only) string.

    Raises:
        SignalValidationError: If `value` is not a `str`, or is empty
            after stripping whitespace.
    """
    if not isinstance(value, str) or not value.strip():
        raise SignalValidationError(f"{name} must be a non-empty string, got {value!r}")
    return value


def validate_unit_range(value: float, *, name: str) -> float:
    """
    Validate that `value` is a finite, non-boolean real number within
    the closed range [0.0, 1.0].

    Shared by `SignalResult.strength` and `SignalResult.confidence`,
    both of which use the same [0.0, 1.0] scale.

    Raises:
        SignalValidationError: If `value` is not numeric, not finite, or
            outside of [0.0, 1.0].
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SignalValidationError(f"{name} must be numeric, got {type(value).__name__}")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise SignalValidationError(f"{name} must be finite, got {numeric_value}")
    if not (0.0 <= numeric_value <= 1.0):
        raise SignalValidationError(f"{name} must be within [0.0, 1.0], got {numeric_value}")
    return numeric_value


def validate_direction(value: Any, *, name: str = "direction") -> SignalDirection:
    """
    Validate that `value` is a `core.enums.SignalDirection` member.

    Raises:
        SignalValidationError: If `value` is not a `SignalDirection`.
    """
    if not isinstance(value, SignalDirection):
        raise SignalValidationError(
            f"{name} must be a SignalDirection, got {type(value).__name__}"
        )
    return value


def validate_instance_list(values: Any, expected_type: type, *, name: str) -> list:
    """
    Validate that `values` is a `list` whose items are all instances of `expected_type`.

    Raises:
        SignalValidationError: If `values` is not a `list`, or contains
            an item that is not an instance of `expected_type`.
    """
    if not isinstance(values, list):
        raise SignalValidationError(f"{name} must be a list, got {type(values).__name__}")
    for index, item in enumerate(values):
        if not isinstance(item, expected_type):
            raise SignalValidationError(
                f"{name}[{index}] must be a {expected_type.__name__}, "
                f"got {type(item).__name__}"
            )
    return values


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
