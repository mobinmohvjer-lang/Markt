"""
news_provider.py
------------------
Purpose:
    Defines the `NewsProvider` interface: the contract any news data
    source must implement to supply `NewsItem` entities to the rest of
    the application.

    No implementation, no API calls -- concrete providers will live in
    the future `data/` package (e.g. `data/providers/news_provider.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from core.entities.news_item import NewsItem


class NewsProvider(ABC):
    """Abstract contract for any source of market-relevant news."""

    @abstractmethod
    def get_latest_news(
        self,
        symbols: list[str] | None = None,
        limit: int = 50,
    ) -> list[NewsItem]:
        """
        Return the most recent news items, optionally filtered by symbol.

        Args:
            symbols: Optional list of trading pairs/instruments to filter
                news relevance by (e.g. ["BTCUSDT"]).
            limit: Maximum number of news items to return.

        Returns:
            A list of `NewsItem` entities.
        """
        raise NotImplementedError

    @abstractmethod
    def search_news(
        self,
        query: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[NewsItem]:
        """
        Search for news items matching a free-text query within an
        optional time range.

        Args:
            query: Free-text search query.
            start: Optional start of the requested time range.
            end: Optional end of the requested time range.

        Returns:
            A list of `NewsItem` entities.
        """
        raise NotImplementedError
