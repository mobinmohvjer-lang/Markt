"""
news_item.py
--------------
Purpose:
    Defines the `NewsItem` domain entity: a single news article or post
    relevant to market analysis, to be produced in future versions by
    `NewsProvider` implementations and optionally enriched with sentiment
    by `AIAnalyzer` implementations.

    Pure data container -- no fetching, no NLP/sentiment computation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class NewsItem:
    """
    A single news article or post relevant to market analysis.

    Attributes:
        news_id: Unique identifier for this news item.
        source: Name of the publisher/feed (e.g. "CoinDesk").
        title: Headline of the article.
        url: Link to the original article.
        published_at: Timestamp when the article was published.
        summary: Short summary or excerpt of the article, if available.
        sentiment_score: Sentiment score in the range [-1.0, 1.0],
            populated later by an `AIAnalyzer` implementation. `None`
            until analyzed.
        related_symbols: Trading pairs/instruments this news item is
            considered relevant to (e.g. ["BTCUSDT"]).
    """

    news_id: str
    source: str
    title: str
    url: str
    published_at: datetime
    summary: str | None = None
    sentiment_score: float | None = None
    related_symbols: list[str] = field(default_factory=list)
