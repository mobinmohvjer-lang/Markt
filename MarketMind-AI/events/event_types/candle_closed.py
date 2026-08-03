"""
candle_closed.py
------------------
Purpose:
    Defines `CandleClosed`: published whenever a candlestick interval
    for a symbol/timeframe has fully closed. This is the typical
    trigger for downstream indicator recalculation.

    Pure data container -- no fetching, no publishing logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.entities.candle import Candle
from events.interfaces.event import Event


@dataclass(frozen=True)
class CandleClosed(Event):
    """
    Published when a candlestick interval has closed.

    Attributes:
        candle: The newly closed candle (its `symbol` and `timeframe`
            fields identify what this event pertains to).
    """

    candle: Candle

    @property
    def event_type(self) -> str:
        return "CandleClosed"
