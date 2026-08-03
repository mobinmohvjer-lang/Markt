"""
indicator_result.py
----------------------
Purpose:
    Defines the `IndicatorResult` domain entity: the standardized output
    of a technical indicator calculation, produced in future versions by
    `IndicatorCalculator` implementations in the `indicators/` package.

    `values` is a mapping rather than a single number so this one entity
    can represent both single-output indicators (e.g. RSI -> {"rsi": ...})
    and multi-output indicators (e.g. MACD -> {"macd": ..., "signal": ...,
    "histogram": ...}) without needing a different entity per indicator.

    Pure data container -- no calculation happens here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class IndicatorResult:
    """
    The output of a single technical indicator calculation.

    Attributes:
        indicator_name: Name of the indicator (e.g. "RSI", "MACD").
        symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").
        timeframe: Candle interval the indicator was calculated on
            (e.g. "1h").
        timestamp: Timestamp the result corresponds to (typically the
            close time of the most recent candle used).
        values: Named output values produced by the indicator (e.g.
            {"value": 55.2} for RSI, or {"macd": 1.1, "signal": 0.9,
            "histogram": 0.2} for MACD).
        parameters: The parameters the indicator was calculated with
            (e.g. {"period": 14}), kept for traceability.
    """

    indicator_name: str
    symbol: str
    timeframe: str
    timestamp: datetime
    values: dict[str, float] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
