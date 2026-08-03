"""
signal.py
----------
Purpose:
    Defines the `Signal` domain entity: a standardized representation of
    a trading signal (e.g. produced by a `Strategy` or `SignalGenerator`
    in future versions), independent of who produced it or what happens
    to it next.

    Pure data container -- no scoring logic, no aggregation logic (that
    will live in the future `signals/` package's `SignalGenerator`
    implementations).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.enums import SignalDirection


@dataclass(frozen=True)
class Signal:
    """
    A single trading signal.

    Attributes:
        signal_id: Unique identifier for this signal.
        symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").
        direction: Directional meaning of the signal (buy/sell/hold).
        confidence: Confidence score for this signal, conventionally in
            the range [0.0, 1.0].
        source: Name/identifier of whatever produced this signal (e.g. a
            strategy name, an AI model name, an indicator name).
        timeframe: Candle interval this signal was derived from
            (e.g. "1h").
        generated_at: Timestamp when this signal was produced.
        metadata: Free-form additional context about the signal (e.g.
            which indicator values or news items contributed to it).
    """

    signal_id: str
    symbol: str
    direction: SignalDirection
    confidence: float
    source: str
    timeframe: str
    generated_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)
