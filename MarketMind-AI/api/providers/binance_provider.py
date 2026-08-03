"""
api/providers/binance_provider.py

Clean HTTP interface over Binance's public REST API.

No trading logic, no indicators, no signal generation -- this class
only knows how to translate method calls into HTTP requests against
an injected HTTPClient and return the decoded JSON response.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from api.providers.base import BaseProvider

DEFAULT_BINANCE_BASE_URL = "https://api.binance.com"


class BinanceProvider(BaseProvider):
    """Wraps Binance's public market-data endpoints."""

    def ping(self) -> Dict[str, Any]:
        """GET /api/v3/ping -- connectivity check."""
        return self.client.get("/api/v3/ping")

    def server_time(self) -> Dict[str, Any]:
        """GET /api/v3/time -- current server time."""
        return self.client.get("/api/v3/time")

    def exchange_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """GET /api/v3/exchangeInfo -- trading rules and symbol metadata."""
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return self.client.get("/api/v3/exchangeInfo", params=params or None)

    def ticker(self, symbol: Optional[str] = None) -> Any:
        """
        GET /api/v3/ticker/24hr -- 24hr rolling window price change stats.
        Returns a dict for a single symbol, or a list of dicts for all symbols.
        """
        params: Dict[str, Any] = {}
        if symbol:
            params["symbol"] = symbol.upper()
        return self.client.get("/api/v3/ticker/24hr", params=params or None)

    def klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[List[Any]]:
        """GET /api/v3/klines -- candlestick data."""
        params: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit,
        }
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        return self.client.get("/api/v3/klines", params=params)

    def order_book(self, symbol: str, limit: int = 100) -> Dict[str, Any]:
        """GET /api/v3/depth -- order book (bids/asks)."""
        params = {"symbol": symbol.upper(), "limit": limit}
        return self.client.get("/api/v3/depth", params=params)

    def recent_trades(self, symbol: str, limit: int = 500) -> List[Dict[str, Any]]:
        """GET /api/v3/trades -- most recent public trades."""
        params = {"symbol": symbol.upper(), "limit": limit}
        return self.client.get("/api/v3/trades", params=params)
