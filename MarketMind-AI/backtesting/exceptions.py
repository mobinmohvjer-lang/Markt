"""
backtesting/exceptions.py

Custom exception hierarchy for the Backtesting Engine.

Keeping these separate from `base.py` / `context.py` / `result.py` lets
future consumers (later Backtesting Engine parts, or `app/`'s
orchestration layer) depend on a single, stable set of exception types
without importing the abstractions themselves, mirroring the pattern
already used by `analysis/exceptions.py`, `signals/exceptions.py`,
`strategies/exceptions.py`, and `strategies/risk_management/exceptions.py`.
"""

from __future__ import annotations


class BacktestError(Exception):
    """Base class for all errors raised by the `backtesting` package."""


class BacktestValidationError(BacktestError):
    """Raised when a `BacktestResult` or `BacktestContext` field fails validation."""


class InvalidBacktestContextError(BacktestValidationError):
    """Raised when a `BacktestContext` is missing required data or malformed."""


class InsufficientBacktestDataError(BacktestError):
    """
    Raised by a `BaseBacktester` when the supplied `BacktestContext` does
    not contain enough data (e.g. no candles, no strategy) to run a
    meaningful backtest.
    """


class BacktesterConfigurationError(BacktestError):
    """Raised when a backtester is constructed or used with invalid configuration/parameters."""
