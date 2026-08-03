"""
indicator_calculated.py
--------------------------
Purpose:
    Defines `IndicatorCalculated`: published whenever a technical
    indicator has been computed for a symbol/timeframe, typically in
    reaction to a `CandleClosed` event.

    Pure data container -- no calculation, no publishing logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.entities.indicator_result import IndicatorResult
from events.interfaces.event import Event


@dataclass(frozen=True)
class IndicatorCalculated(Event):
    """
    Published when a technical indicator's result is ready.

    Attributes:
        indicator_result: The computed indicator output (its
            `symbol`/`timeframe`/`indicator_name` fields identify what
            this event pertains to).
    """

    indicator_result: IndicatorResult

    @property
    def event_type(self) -> str:
        return "IndicatorCalculated"
