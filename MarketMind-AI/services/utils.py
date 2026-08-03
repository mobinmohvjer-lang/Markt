"""
services/utils.py

Shared, dependency-light helpers used across the `services` package.

Keeping validation/formatting helpers here means every service,
`ServiceContext`, and `ServiceResult` validates and formats values in
exactly the same way, mirroring the role `analysis/utils.py` plays for
`analysis`, `signals/utils.py` plays for `signals`, `strategies/utils.py`
plays for the Strategy Engine, `strategies/risk_management/utils.py`
plays for the Risk Engine, `strategies/portfolio_management/utils.py`
plays for Portfolio Management, `backtesting/utils.py` plays for the
Backtesting Engine, and `execution/utils.py` plays for the Execution
Engine.

No notification/alert delivery, no AI/LLM client logic, no scheduler
implementation, no event-bus implementation, no networking, no
threading, no async logic lives here -- only generic validation and
small pure helpers.
"""

from __future__ import annotations

from typing import Any, Optional

from services.exceptions import ServiceValidationError


def validate_non_empty_str(value: str, *, name: str) -> str:
    """
    Validate that `value` is a non-empty (non-whitespace-only) string.

    Raises:
        ServiceValidationError: If `value` is not a `str`, or is empty
            after stripping whitespace.
    """
    if not isinstance(value, str) or not value.strip():
        raise ServiceValidationError(f"{name} must be a non-empty string, got {value!r}")
    return value


def validate_bool(value: Any, *, name: str) -> bool:
    """
    Validate that `value` is a genuine `bool`.

    Raises:
        ServiceValidationError: If `value` is not a `bool`.
    """
    if not isinstance(value, bool):
        raise ServiceValidationError(f"{name} must be a bool, got {type(value).__name__}")
    return value


def validate_dict(value: Any, *, name: str) -> dict:
    """
    Validate that `value` is a `dict`.

    Shared by `ServiceContext.payload`/`metadata` and `ServiceResult.
    metadata`, the same free-form supporting-data shape every other
    package's context/result types already use.

    Raises:
        ServiceValidationError: If `value` is not a `dict`.
    """
    if not isinstance(value, dict):
        raise ServiceValidationError(f"{name} must be a dict, got {type(value).__name__}")
    return value


def clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """
    Clamp `value` into the closed range [`low`, `high`].

    Generic numeric helper (mirrors `analysis.technical.utils.clip`'s,
    `strategies.utils.clip`'s, `strategies.risk_management.utils.
    clip`'s, `strategies.portfolio_management.utils.clip`'s, and
    `execution.utils.clip`'s role) available to future concrete
    services that need to keep a derived sub-score within a
    well-defined range.
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
