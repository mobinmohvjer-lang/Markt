"""
api/providers/news_provider.py

Generic HTTP interface for a news REST API.

Only the architecture and transport are implemented here, per spec:
the provider is deliberately vendor-agnostic (base URL, API key, and
param/header formatting are all injectable) so it can be pointed at
NewsAPI.org, GNews, or any similarly-shaped headline/search REST API
without changing this class. No parsing beyond generic JSON
decoding, no sentiment/AI analysis, no signal generation.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from api.providers.base import BaseProvider


class NewsProvider(BaseProvider):
    """
    Thin wrapper over a news REST API.

    Parameters
    ----------
    http_client:
        An HTTPClient already configured with the provider's base_url
        (e.g. "https://newsapi.org/v2") and any auth headers.
    api_key_param:
        Name of the query-string parameter used to pass the API key,
        if the target API expects the key as a query param rather than
        a header (e.g. "apiKey" for NewsAPI.org). Leave as None if the
        key is supplied purely via headers on the injected HTTPClient.
    api_key:
        The API key value, only used if api_key_param is set.
    """

    def __init__(
        self,
        http_client,
        api_key: Optional[str] = None,
        api_key_param: Optional[str] = None,
        logger=None,
    ) -> None:
        super().__init__(http_client, logger)
        self.api_key = api_key
        self.api_key_param = api_key_param

    def _with_auth(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if self.api_key_param and self.api_key:
            params = dict(params)
            params[self.api_key_param] = self.api_key
        return params

    def top_headlines(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        country: Optional[str] = None,
        language: str = "en",
        page_size: int = 20,
        page: int = 1,
    ) -> Dict[str, Any]:
        """Fetch top/breaking headlines, optionally filtered."""
        params: Dict[str, Any] = {
            "language": language,
            "pageSize": page_size,
            "page": page,
        }
        if query:
            params["q"] = query
        if category:
            params["category"] = category
        if country:
            params["country"] = country
        return self.client.get("/top-headlines", params=self._with_auth(params))

    def search(
        self,
        query: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        language: str = "en",
        sort_by: str = "publishedAt",
        page_size: int = 20,
        page: int = 1,
    ) -> Dict[str, Any]:
        """Search all articles matching a query, with optional date range."""
        params: Dict[str, Any] = {
            "q": query,
            "language": language,
            "sortBy": sort_by,
            "pageSize": page_size,
            "page": page,
        }
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        return self.client.get("/everything", params=self._with_auth(params))

    def sources(self, category: Optional[str] = None, language: str = "en") -> Dict[str, Any]:
        """List available news sources, optionally filtered by category."""
        params: Dict[str, Any] = {"language": language}
        if category:
            params["category"] = category
        return self.client.get("/sources", params=self._with_auth(params))
