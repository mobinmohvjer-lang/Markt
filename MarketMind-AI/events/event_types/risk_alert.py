"""
risk_alert.py
---------------
Purpose:
    Defines `RiskAlert`: published whenever a `RiskManager` (or other
    risk-monitoring component) flags a concern -- e.g. a rejected
    signal, an exposure limit reached, or an unexpected drawdown.
    Typically triggers downstream notifications or safeguards.

    Pure data container -- no risk-calculation logic, no publishing logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.entities.position import Position
from core.entities.signal import Signal
from events.interfaces.event import Event


@dataclass(frozen=True)
class RiskAlert(Event):
    """
    Published when a risk management concern is raised.

    Attributes:
        message: Human-readable description of the concern.
        severity: Severity level of the alert (e.g. "info", "warning",
            "critical"). Kept as a plain string rather than an enum for
            now, since no risk logic has been implemented yet to define
            the canonical severity levels.
        symbol: Trading pair/instrument the alert relates to, if
            applicable.
        related_signal: The signal that triggered this alert, if
            applicable.
        related_position: The position that triggered this alert, if
            applicable.
    """

    message: str
    severity: str
    symbol: str | None = None
    related_signal: Signal | None = None
    related_position: Position | None = None

    @property
    def event_type(self) -> str:
        return "RiskAlert"
