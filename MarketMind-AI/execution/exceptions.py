"""
execution/exceptions.py

Custom exception hierarchy for the Execution Engine.

Keeping these separate from `base.py` / `context.py` / `result.py` lets
future consumers (later Execution Engine parts, `backtesting/`, `app/`)
depend on a single, stable set of exception types without importing
the abstractions themselves, mirroring the pattern already used by
`analysis/exceptions.py`, `signals/exceptions.py`,
`strategies/exceptions.py`, `strategies/risk_management/exceptions.py`,
`strategies/portfolio_management/exceptions.py`, and
`backtesting/exceptions.py`.
"""

from __future__ import annotations


class ExecutionError(Exception):
    """Base class for all errors raised by the `execution` package."""


class ExecutionValidationError(ExecutionError):
    """Raised when an `ExecutionResult` or `ExecutionContext` field fails validation."""


class InvalidExecutionContextError(ExecutionValidationError):
    """Raised when an `ExecutionContext` is missing required data or malformed."""


class InsufficientExecutionDataError(ExecutionError):
    """
    Raised by a `BaseExecutionEngine` when the supplied `ExecutionContext`
    does not contain enough data (e.g. no candidate decision to act on)
    to produce a meaningful `ExecutionResult`.
    """


class ExecutionEngineConfigurationError(ExecutionError):
    """Raised when an execution engine is constructed or used with invalid configuration/parameters."""
