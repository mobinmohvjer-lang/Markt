"""
strategies/exceptions.py

Custom exception hierarchy for the Strategy Engine.

Keeping these separate from `base_strategy.py` / `context.py` /
`result.py` lets future consumers (later Strategy Engine parts,
`backtesting/`, `app/`) depend on a single, stable set of exception
types without importing the abstractions themselves, mirroring the
pattern already used by `analysis/exceptions.py`, `signals/
exceptions.py`, and `strategies/risk_management/exceptions.py`.
"""

from __future__ import annotations


class StrategyError(Exception):
    """Base class for all errors raised by the `strategies` package's Strategy Engine."""


class StrategyValidationError(StrategyError):
    """Raised when a `StrategyResult` or `StrategyContext` field fails validation."""


class InvalidStrategyContextError(StrategyValidationError):
    """Raised when a `StrategyContext` is missing required data or malformed."""


class InsufficientStrategyDataError(StrategyError):
    """
    Raised by a `BaseStrategy` when the supplied `StrategyContext` does
    not contain enough data (e.g. no signal result, no risk result) to
    produce a meaningful `StrategyResult`.
    """


class StrategyConfigurationError(StrategyError):
    """Raised when a strategy is constructed or used with invalid configuration/parameters."""
