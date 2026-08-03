"""
api/providers/coingecko_provider.py

Clean HTTP interface over CoinGecko's public REST API.

No trading logic, no indicators, no signal generation -- this class
only knows how to translate method calls into HTTP requests against
an injected HTTPClient and return the decoded JSON response.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from api.providers.base import BaseProvider

DEFAULT_COINGECKO_BASE_URL = "https://api.coingecko.com/api/v3"


class CoinGeckoProvider(BaseProvider):
    """Wraps CoinGecko's public market-data endpoints."""

    def markets(
        self,
        vs_currency: str = "usd",
        ids: Optional[List[str]] = None,
        order: str = "market_cap_desc",
        per_page: int = 100,
        page: int = 1,
        sparkline: bool = False,
    ) -> List[Dict[str, Any]]:
        """GET /coins/markets -- paginated market data for coins."""
        params: Dict[str, Any] = {
            "vs_currency": vs_currency,
            "order": order,
            "per_page": per_page,
            "page": page,
            "sparkline": str(sparkline).lower(),
        }
        if ids:
            params["ids"] = ",".join(ids)
        return self.client.get("/coins/markets", params=params)

    def coin_details(
        self,
        coin_id: str,
        localization: bool = False,
        tickers: bool = False,
        market_data: bool = True,
        community_data: bool = False,
        developer_data: bool = False,
        sparkline: bool = False,
    ) -> Dict[str, Any]:
        """GET /coins/{id} -- full metadata + market data for a single coin."""
        params: Dict[str, Any] = {
            "localization": str(localization).lower(),
            "tickers": str(tickers).lower(),
            "market_data": str(market_data).lower(),
            "community_data": str(community_data).lower(),
            "developer_data": str(developer_data).lower(),
            "sparkline": str(sparkline).lower(),
        }
        return self.client.get(f"/coins/{coin_id}", params=params)
