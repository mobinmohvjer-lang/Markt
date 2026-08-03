"""
event.py
----------
Purpose:
    Defines `Event`: the abstract base that every concrete event in
    `events/event_types/` must extend. It fixes the minimal shape every
    event shares (a unique identifier and an occurrence timestamp) and
    forces each concrete event to declare its own `event_type` name, so
    an `EventBus` can route events without inspecting their payload.

    Pure architecture -- no behavior beyond enforcing the contract.
    Populating `event_id`/`occurred_at` (e.g. generating a UUID, reading
    the clock) is the responsibility of whatever code constructs an
    event instance, not of this base class.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Event(ABC):
    """
    Abstract base class for all domain events.

    Attributes:
        event_id: Unique identifier for this event instance (e.g. a
            UUID string), used for deduplication, tracing, and logging.
        occurred_at: Timestamp marking when the underlying occurrence
            happened (not necessarily when it was published).
    """

    event_id: str
    occurred_at: datetime

    @property
    @abstractmethod
    def event_type(self) -> str:
        """
        Canonical string identifier for this event's type
        (e.g. "CandleClosed"), used by an `EventBus` for routing and by
        logging/observability tooling. Every concrete event subclass
        must override this.
        """
        raise NotImplementedError
