"""
services/exceptions.py

Custom exception hierarchy for `services`.

Keeping these separate from `base.py` / `context.py` / `result.py` lets
future consumers (concrete services such as a notification service, an
AI/LLM client wrapper, a scheduler, or a concrete `EventBus`
implementation, plus `app/`'s orchestration layer) depend on a single,
stable set of exception types without importing the abstractions
themselves, mirroring the pattern already used by
`analysis/exceptions.py`, `signals/exceptions.py`,
`strategies/exceptions.py`, `strategies/risk_management/exceptions.py`,
`strategies/portfolio_management/exceptions.py`,
`backtesting/exceptions.py`, and `execution/exceptions.py`.
"""

from __future__ import annotations


class ServiceError(Exception):
    """Base class for all errors raised by the `services` package."""


class ServiceValidationError(ServiceError):
    """Raised when a `ServiceResult` or `ServiceContext` field fails validation."""


class InvalidServiceContextError(ServiceValidationError):
    """Raised when a `ServiceContext` is missing required data or malformed."""


class InsufficientServiceDataError(ServiceError):
    """
    Raised by a `BaseService` when the supplied `ServiceContext` does not
    contain enough data (e.g. no payload to act on) to carry out a
    meaningful service call.
    """


class ServiceConfigurationError(ServiceError):
    """Raised when a service is constructed or used with invalid configuration/parameters."""
