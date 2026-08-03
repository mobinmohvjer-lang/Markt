"""
position_closed.py
---------------------
Purpose:
    Defines `PositionClosed`: published whenever a trading position is
    fully closed, typically for downstream portfolio updates, logging,
    notifications, or backtesting reports.

    Pure data container -- no execution logic, no publishing logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.entities.position import Position
from events.interfaces.event import Event


@dataclass(frozen=True)
class PositionClosed(Event):
    """
    Published when a trading position has been closed.

    Attributes:
        position: The position that was closed (its `realized_pnl` and
            `closed_at` fields describe the outcome).
    """

    position: Position

    @property
    def event_type(self) -> str:
        return "PositionClosed"
