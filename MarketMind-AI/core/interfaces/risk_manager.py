"""
risk_manager.py
------------------
Purpose:
    Defines the `RiskManager` interface: the contract for components
    that decide whether a signal is safe to act on, how large a position
    it should translate to, and where protective levels should sit.

    No implementation, no risk calculations here -- concrete risk
    management rules will live in the future
    `strategies/risk_management/` package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from core.entities.portfolio import Portfolio
from core.entities.signal import Signal


class RiskManager(ABC):
    """Abstract contract for validating signals and sizing positions."""

    @abstractmethod
    def validate_signal(self, signal: Signal, portfolio: Portfolio) -> bool:
        """
        Decide whether a signal is currently safe/allowed to act on.

        Args:
            signal: The candidate signal to evaluate.
            portfolio: The current portfolio state.

        Returns:
            `True` if the signal passes risk checks, `False` otherwise.
        """
        raise NotImplementedError

    @abstractmethod
    def calculate_position_size(self, signal: Signal, portfolio: Portfolio) -> Decimal:
        """
        Determine how large a position should be opened for a signal.

        Args:
            signal: The candidate signal to size.
            portfolio: The current portfolio state.

        Returns:
            The position size (in base asset units) to use.
        """
        raise NotImplementedError

    @abstractmethod
    def calculate_stop_loss(self, signal: Signal, reference_price: Decimal) -> Decimal | None:
        """
        Determine a protective stop-loss price for a signal.

        Args:
            signal: The candidate signal being acted on.
            reference_price: Price to base the stop-loss calculation on
                (e.g. the current market price).

        Returns:
            The stop-loss price to use, or `None` if not applicable.
        """
        raise NotImplementedError
