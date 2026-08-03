"""
ai_analysis_completed.py
---------------------------
Purpose:
    Defines `AIAnalysisCompleted`: published whenever an `AIAnalyzer`
    implementation finishes assessing a market state (and/or a batch of
    news items), typically triggering downstream signal generation.

    Pure data container -- no analysis, no publishing logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from events.interfaces.event import Event


@dataclass(frozen=True)
class AIAnalysisCompleted(Event):
    """
    Published when an AI-driven market/news analysis has finished.

    Attributes:
        symbol: Trading pair/instrument identifier this analysis
            pertains to (e.g. "BTCUSDT").
        summary: The natural-language assessment produced by the
            `AIAnalyzer` implementation.
    """

    symbol: str
    summary: str

    @property
    def event_type(self) -> str:
        return "AIAnalysisCompleted"
