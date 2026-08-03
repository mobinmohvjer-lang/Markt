"""
event_handler.py
------------------
Purpose:
    Defines `EventHandler`: the contract any component must implement to
    react to events delivered by an `EventBus`.

    Generic over the event type it handles (`EventHandler[CandleClosed]`,
    `EventHandler[SignalGenerated]`, etc.) so a single interface shape
    covers every future handler without needing one interface per event.

    No implementation, no business logic -- concrete handlers (e.g. "on
    CandleClosed, recalculate indicators") will live in future outer
    layers (`indicators/`, `analysis/`, `strategies/`, `app/`, ...).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from events.interfaces.event import Event

E = TypeVar("E", bound=Event)


class EventHandler(ABC, Generic[E]):
    """Abstract contract for any component that reacts to a specific event type."""

    @abstractmethod
    def handle(self, event: E) -> None:
        """
        React to a delivered event.

        Args:
            event: The event instance to handle.
        """
        raise NotImplementedError
