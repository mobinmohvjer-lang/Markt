"""
event_bus.py
--------------
Purpose:
    Defines `EventBus`: the contract for the central publish/subscribe
    mechanism that lets layers communicate through events instead of
    direct calls.

    Completely independent from Binance or any external provider, and
    from any specific transport: a future implementation could be a
    simple in-memory synchronous dispatcher for local/personal use, or
    something more elaborate later (e.g. asyncio-based, or backed by a
    message broker) -- this interface does not assume either.

    No implementation, no network code, no async here -- concrete buses
    will live in a future outer layer (e.g. `services/` or `app/`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from events.interfaces.event import Event
from events.interfaces.event_handler import EventHandler


class EventBus(ABC):
    """Abstract contract for a publish/subscribe event bus."""

    @abstractmethod
    def publish(self, event: Event) -> None:
        """
        Publish an event to all handlers subscribed to its type.

        Args:
            event: The event instance to publish.
        """
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        """
        Register a handler to be invoked whenever an event of the given
        type is published.

        Args:
            event_type: The concrete `Event` subclass to subscribe to
                (e.g. `CandleClosed`).
            handler: The handler to invoke when a matching event is
                published.
        """
        raise NotImplementedError

    @abstractmethod
    def unsubscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        """
        Remove a previously registered handler for the given event type.

        Args:
            event_type: The concrete `Event` subclass to unsubscribe from.
            handler: The handler instance to remove.
        """
        raise NotImplementedError
