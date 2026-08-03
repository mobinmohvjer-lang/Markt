"""
analysis/utils.py

Shared, dependency-light helpers used across the `analysis` package.

Keeping validation/formatting helpers here means every analyzer,
`AnalysisResult`, and `AnalysisContext` validates and formats values in
exactly the same way, mirroring the role `indicators/utils.py` plays
for the `indicators` package.

No calculation logic and no trading/AI logic lives here -- only generic
validation and small pure helpers.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional

from analysis.exceptions import AnalysisValidationError


def utcnow() -> datetime:
    """Return the current time as a timezone-aware UTC `datetime`."""
    return datetime.now(timezone.utc)


def validate_non_empty_str(value: str, *, name: str) -> str:
    """
    Validate that `value` is a non-empty (non-whitespace-only) string.

    Raises:
        AnalysisValidationError: If `value` is not a `str`, or is empty
            after stripping whitespace.
    """
    if not isinstance(value, str) or not value.strip():
        raise AnalysisValidationError(f"{name} must be a non-empty string, got {value!r}")
    return value


def validate_score(value: float, *, name: str = "score") -> float:
    """
    Validate that `value` is a finite, non-boolean real number.

    Score is intentionally unbounded here: different analyzers use
    different scales (e.g. -1.0..1.0 for bearish/bullish, 0..100 for a
    strength index). Concrete analyzers are responsible for documenting
    and enforcing their own scale.

    Raises:
        AnalysisValidationError: If `value` is not numeric or is not finite.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalysisValidationError(f"{name} must be numeric, got {type(value).__name__}")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise AnalysisValidationError(f"{name} must be finite, got {numeric_value}")
    return numeric_value


def validate_confidence(value: float, *, name: str = "confidence") -> float:
    """
    Validate that `value` is a finite number within the closed range [0.0, 1.0].

    Raises:
        AnalysisValidationError: If `value` is not numeric, not finite, or
            outside of [0.0, 1.0].
    """
    numeric_value = validate_score(value, name=name)
    if not (0.0 <= numeric_value <= 1.0):
        raise AnalysisValidationError(f"{name} must be within [0.0, 1.0], got {numeric_value}")
    return numeric_value


def validate_instance_list(values: Any, expected_type: type, *, name: str) -> list:
    """
    Validate that `values` is a `list` whose items are all instances of `expected_type`.

    Raises:
        AnalysisValidationError: If `values` is not a `list`, or contains
            an item that is not an instance of `expected_type`.
    """
    if not isinstance(values, list):
        raise AnalysisValidationError(f"{name} must be a list, got {type(values).__name__}")
    for index, item in enumerate(values):
        if not isinstance(item, expected_type):
            raise AnalysisValidationError(
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
