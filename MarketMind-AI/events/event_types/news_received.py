"""
news_received.py
-------------------
Purpose:
    Defines `NewsReceived`: published whenever a new, relevant news item
    has been retrieved, typically triggering downstream AI/sentiment
    analysis.

    Pure data container -- no fetching, no publishing logic.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.entities.news_item import NewsItem
from events.interfaces.event import Event


@dataclass(frozen=True)
class NewsReceived(Event):
    """
    Published when a new news item has been retrieved.

    Attributes:
        news_item: The news item that was received.
    """

    news_item: NewsItem

    @property
    def event_type(self) -> str:
        return "NewsReceived"
