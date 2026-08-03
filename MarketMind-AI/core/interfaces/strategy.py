"""
strategy.py
-------------
Purpose:
    Defines the `Strategy` interface: the contract any trading strategy
    implementation must fulfill to turn a market snapshot into a trading
    signal.

    No implementation, no trading logic here -- concrete strategies will
    live in the future `strategies/` package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.entities.market_state import MarketState
from core.entities.signal import Signal


class Strategy(ABC):
    """Abstract contract for any trading strategy."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The strategy's canonical name (e.g. "TrendFollowing")."""
        raise NotImplementedError

    @abstractmethod
    def generate_signal(self, market_state: MarketState) -> Signal | None:
        """
        Evaluate the current market state and optionally produce a signal.

        Args:
            market_state: The aggregated market snapshot to evaluate.

        Returns:
            A `Signal` if the strategy has a recommendation, or `None`
            if it has nothing actionable to say for this market state.
        """
        raise NotImplementedError
