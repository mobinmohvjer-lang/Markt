"""
indicator_calculator.py
--------------------------
Purpose:
    Defines the `IndicatorCalculator` interface: the contract any
    technical indicator implementation must fulfill to compute an
    `IndicatorResult` from a series of candles.

    No implementation, no calculations here -- concrete indicators
    (SMA, RSI, MACD, etc.) will live in the future `indicators/` package.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.entities.candle import Candle
from core.entities.indicator_result import IndicatorResult


class IndicatorCalculator(ABC):
    """Abstract contract for any technical indicator calculation."""

    @property
    @abstractmethod
    def name(self) -> str:
        """The indicator's canonical name (e.g. "RSI", "MACD")."""
        raise NotImplementedError

    @abstractmethod
    def calculate(self, candles: list[Candle], **parameters: Any) -> IndicatorResult:
        """
        Compute the indicator's value(s) from a series of candles.

        Args:
            candles: Ordered list of `Candle` entities to compute over.
            **parameters: Indicator-specific parameters (e.g. `period=14`).

        Returns:
            An `IndicatorResult` describing the computed output.
        """
        raise NotImplementedError
