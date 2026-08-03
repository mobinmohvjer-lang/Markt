"""
strategies/portfolio_management/exceptions.py

Custom exception hierarchy for the Portfolio Management layer.

Keeping these separate from `base.py` / `context.py` / `result.py` lets
future consumers (later Portfolio Management parts, `backtesting/`,
`app/`) depend on a single, stable set of exception types without
importing the abstractions themselves, mirroring the pattern already
used by `analysis/exceptions.py`, `signals/exceptions.py`,
`strategies/exceptions.py`, and
`strategies/risk_management/exceptions.py`.
"""

from __future__ import annotations


class PortfolioError(Exception):
    """Base class for all errors raised by the `strategies.portfolio_management` package."""


class PortfolioValidationError(PortfolioError):
    """Raised when a `PortfolioResult` or `PortfolioContext` field fails validation."""


class InvalidPortfolioContextError(PortfolioValidationError):
    """Raised when a `PortfolioContext` is missing required data or malformed."""


class InsufficientPortfolioDataError(PortfolioError):
    """
    Raised by a `BasePortfolioManager` when the supplied
    `PortfolioContext` does not contain enough data (e.g. no portfolio)
    to produce a meaningful `PortfolioResult`.
    """


class PortfolioManagerConfigurationError(PortfolioError):
    """Raised when a portfolio manager is constructed or used with invalid configuration/parameters."""
