"""
signal_generated.py
----------------------
Purpose:
    Defines `SignalGenerated`: published whenever a `Strategy` or
    `SignalGenerator` produces a trading signal, typically triggering
    downstream risk validation and, eventually, execution.

    Pure data container -- no strategy logic, no publishing logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.entities.signal import Signal
from events.interfaces.event import Event


@dataclass(frozen=True)
class SignalGenerated(Event):
    """
    Published when a new trading signal has been produced.

    Attributes:
        signal: The signal that was generated.
    """

    signal: Signal

    @property
    def event_type(self) -> str:
        return "SignalGenerated"
