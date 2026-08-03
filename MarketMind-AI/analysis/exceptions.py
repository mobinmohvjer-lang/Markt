"""
analysis/exceptions.py

Custom exception hierarchy for the Analysis Engine.

Keeping these separate from `base.py` / `context.py` / `result.py` lets
future sub-packages (e.g. `analysis/technical/`, `analysis/news/`,
`analysis/ai/`) depend on a single, stable set of exception types
without importing the abstractions themselves, mirroring the pattern
already used by `api/exceptions.py`.
"""

from __future__ import annotations


class AnalysisError(Exception):
    """Base class for all errors raised by the `analysis` package."""


class AnalysisValidationError(AnalysisError):
    """Raised when an `AnalysisResult` or `AnalysisContext` field fails validation."""


class InvalidAnalysisContextError(AnalysisValidationError):
    """Raised when an `AnalysisContext` is missing required data or malformed."""


class InsufficientDataError(AnalysisError):
    """
    Raised by a `BaseAnalyzer` when the supplied `AnalysisContext` does not
    contain enough data (e.g. missing indicators, no candle, no news) to
    produce a meaningful `AnalysisResult`.
    """


class AnalyzerConfigurationError(AnalysisError):
    """Raised when an analyzer is constructed or used with invalid configuration/parameters."""
