"""
strategies/risk_management/exceptions.py

Custom exception hierarchy for the Risk Engine.

Keeping these separate from `base.py` / `context.py` / `result.py` lets
future consumers (e.g. later Risk Engine parts, or `strategies/`'s own
trading-decision logic) depend on a single, stable set of exception
types without importing the abstractions themselves, mirroring the
pattern already used by `analysis/exceptions.py` and
`signals/exceptions.py`.
"""

from __future__ import annotations


class RiskError(Exception):
    """Base class for all errors raised by the `strategies.risk_management` package."""


class RiskValidationError(RiskError):
    """Raised when a `RiskResult` or `RiskContext` field fails validation."""


class InvalidRiskContextError(RiskValidationError):
    """Raised when a `RiskContext` is missing required data or malformed."""


class InsufficientRiskDataError(RiskError):
    """
    Raised by a `BaseRiskManager` when the supplied `RiskContext` does
    not contain enough data (e.g. no portfolio, no signal) to produce a
    meaningful `RiskResult`.
    """


class RiskManagerConfigurationError(RiskError):
    """Raised when a risk manager is constructed or used with invalid configuration/parameters."""
