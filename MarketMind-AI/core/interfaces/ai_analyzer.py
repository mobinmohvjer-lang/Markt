"""
ai_analyzer.py
----------------
Purpose:
    Defines the `AIAnalyzer` interface: the contract any AI/LLM-backed
    analysis component must implement to turn raw market state and news
    into higher-level, human-readable or scored insights.

    No implementation, no model calls -- concrete analyzers will live in
    the future `services/` package (e.g. `services/ai_service.py`),
    likely wrapping a free/self-hosted model.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.entities.market_state import MarketState
from core.entities.news_item import NewsItem


class AIAnalyzer(ABC):
    """Abstract contract for any AI-driven market/news analysis component."""

    @abstractmethod
    def analyze_market_state(self, market_state: MarketState) -> str:
        """
        Produce a human-readable assessment of the current market state.

        Args:
            market_state: The aggregated market snapshot to analyze.

        Returns:
            A natural-language summary/commentary describing the market
            state (e.g. for display to the user or logging).
        """
        raise NotImplementedError

    @abstractmethod
    def analyze_news_sentiment(self, news_items: list[NewsItem]) -> list[NewsItem]:
        """
        Enrich a list of news items with a sentiment assessment.

        Args:
            news_items: News items to analyze.

        Returns:
            A list of `NewsItem` entities with `sentiment_score`
            populated (implementations should not mutate the input
            objects in place, since `NewsItem` is immutable -- they
            should return new instances instead).
        """
        raise NotImplementedError
