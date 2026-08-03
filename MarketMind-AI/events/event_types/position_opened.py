"""
position_opened.py
---------------------
Purpose:
    Defines `PositionOpened`: published whenever a new trading position
    is opened, typically for downstream portfolio updates, logging, or
    notifications.

    Pure data container -- no execution logic, no publishing logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.entities.position import Position
from events.interfaces.event import Event


@dataclass(frozen=True)
class PositionOpened(Event):
    """
    Published when a new trading position has been opened.

    Attributes:
        position: The position that was opened.
    """

    position: Position

    @property
    def event_type(self) -> str:
        return "PositionOpened"
