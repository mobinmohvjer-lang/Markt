"""
signal_generator.py
----------------------
Purpose:
    Defines the `SignalGenerator` interface: the contract for components
    that produce one or more `Signal` entities from a market snapshot,
    and/or combine multiple signals (e.g. from several strategies) into
    a single, aggregated signal.

    This is distinct from `Strategy`: a single `Strategy` produces at
    most one opinion, while a `SignalGenerator` may orchestrate several
    strategies/indicators and decide how to reconcile their outputs.

    No implementation, no aggregation logic here -- concrete generators
    will live in the future `signals/` package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.entities.market_state import MarketState
from core.entities.signal import Signal


class SignalGenerator(ABC):
    """Abstract contract for producing and combining trading signals."""

    @abstractmethod
    def generate(self, market_state: MarketState) -> list[Signal]:
        """
        Produce all candidate signals for the current market state.

        Args:
            market_state: The aggregated market snapshot to evaluate.

        Returns:
            A list of `Signal` entities (possibly empty, possibly from
            multiple underlying sources).
        """
        raise NotImplementedError

    @abstractmethod
    def aggregate(self, signals: list[Signal]) -> Signal | None:
        """
        Combine multiple candidate signals into a single decision.

        Args:
            signals: Candidate signals to reconcile (e.g. from multiple
                strategies or indicators).

        Returns:
            A single aggregated `Signal`, or `None` if no consensus /
            actionable signal could be formed.
        """
        raise NotImplementedError
