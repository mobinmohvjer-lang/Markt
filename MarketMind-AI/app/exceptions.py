"""
app/exceptions.py

Custom exception hierarchy for the `app` layer.

Keeping these separate from the use-case modules themselves mirrors the
pattern already used by every other package in this repository (e.g.
`analysis/exceptions.py`, `signals/exceptions.py`, `services/exceptions.py`).
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for all errors raised by the `app` layer."""


class PipelineConfigurationError(AppError):
    """Raised when a pipeline is constructed with invalid dependencies/configuration."""


class PipelineDataError(AppError):
    """Raised when the Data stage cannot supply what the rest of the pipeline needs."""


class PipelineAnalysisError(AppError):
    """Raised when the Analysis stage fails (wraps an underlying `analysis.exceptions.AnalysisError`)."""


class PipelineSignalError(AppError):
    """Raised when the Signals stage fails (wraps an underlying `signals.exceptions.SignalError`)."""


class BacktestRunnerConfigurationError(AppError):
    """Raised when a `BacktestRunner` is constructed or run with invalid dependencies/configuration."""


class BacktestRunnerDataError(AppError):
    """Raised when no historical candle data is available for the requested symbol/timeframe."""


class BacktestRunnerExecutionError(AppError):
    """Raised when the backtest replay itself fails (wraps an underlying `backtesting.exceptions.BacktestError`)."""
