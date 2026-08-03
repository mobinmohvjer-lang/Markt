"""
tests/test_news_provider.py

Unit tests for api/providers/news_provider.py. The HTTPClient is
mocked entirely, so no real network calls are made.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from api.providers.news_provider import NewsProvider


class TestNewsProviderNoAuthParam(unittest.TestCase):
    """When auth is handled via headers on the injected HTTPClient."""

    def setUp(self):
        self.client = MagicMock()
        self.provider = NewsProvider(self.client)

    def test_top_headlines_minimal(self):
        self.client.get.return_value = {"articles": []}
        self.provider.top_headlines()
        self.client.get.assert_called_once_with(
            "/top-headlines",
            params={"language": "en", "pageSize": 20, "page": 1},
        )

    def test_top_headlines_with_filters(self):
        self.client.get.return_value = {"articles": []}
        self.provider.top_headlines(query="bitcoin", category="business", country="us", page_size=5, page=2)
        self.client.get.assert_called_once_with(
            "/top-headlines",
            params={
                "language": "en",
                "pageSize": 5,
                "page": 2,
                "q": "bitcoin",
                "category": "business",
                "country": "us",
            },
        )

    def test_search(self):
        self.client.get.return_value = {"articles": []}
        self.provider.search("ethereum", from_date="2026-01-01", to_date="2026-01-31")
        self.client.get.assert_called_once_with(
            "/everything",
            params={
                "q": "ethereum",
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 20,
                "page": 1,
                "from": "2026-01-01",
                "to": "2026-01-31",
            },
        )

    def test_sources(self):
        self.client.get.return_value = {"sources": []}
        self.provider.sources(category="crypto")
        self.client.get.assert_called_once_with(
            "/sources", params={"language": "en", "category": "crypto"}
        )


class TestNewsProviderWithAuthParam(unittest.TestCase):
    """When the target API expects the API key as a query param."""

    def setUp(self):
        self.client = MagicMock()
        self.provider = NewsProvider(self.client, api_key="secret-key", api_key_param="apiKey")

    def test_top_headlines_injects_api_key(self):
        self.client.get.return_value = {"articles": []}
        self.provider.top_headlines(query="bitcoin")
        _, kwargs = self.client.get.call_args
        self.assertEqual(kwargs["params"]["apiKey"], "secret-key")
        self.assertEqual(kwargs["params"]["q"], "bitcoin")

    def test_search_injects_api_key(self):
        self.client.get.return_value = {"articles": []}
        self.provider.search("ethereum")
        _, kwargs = self.client.get.call_args
        self.assertEqual(kwargs["params"]["apiKey"], "secret-key")


if __name__ == "__main__":
    unittest.main()
