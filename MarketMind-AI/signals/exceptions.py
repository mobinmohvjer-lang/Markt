"""
signals/exceptions.py

Custom exception hierarchy for the Signal Engine.

Keeping these separate from `base.py` / `context.py` / `result.py` lets
future consumers (e.g. `strategies/`) depend on a single, stable set of
exception types without importing the abstractions themselves,
mirroring the pattern already used by `analysis/exceptions.py`.
"""

from __future__ import annotations


class SignalError(Exception):
    """Base class for all errors raised by the `signals` package."""


class SignalValidationError(SignalError):
    """Raised when a `SignalResult` or `SignalContext` field fails validation."""


class InvalidSignalContextError(SignalValidationError):
    """Raised when a `SignalContext` is missing required data or malformed."""


class InsufficientSignalDataError(SignalError):
    """
    Raised by a `BaseSignalGenerator` when the supplied `SignalContext`
    does not contain enough data (e.g. no `AnalysisResult`s) to produce
    a meaningful `SignalResult`.
    """


class SignalGeneratorConfigurationError(SignalError):
    """Raised when a signal generator is constructed or used with invalid configuration/parameters."""
