"""
Binance Spot client abstraction.

The Data Engine never talks to the network directly through the downloader/
updater classes -- it depends only on `BinanceClientInterface`. This keeps
the engine testable (inject a fake client) and keeps networking concerns
isolated from storage/validation/normalization logic.
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from .config import assert_valid_timeframe


class BinanceClientInterface(ABC):
    """Abstract interface any Binance Spot kline provider must implement."""

    @abstractmethod
    def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> List[list]:
        """
        Return raw Binance kline arrays for the given symbol/interval.

        Each element must follow Binance's raw kline format:
        [open_time, open, high, low, close, volume, close_time,
         quote_asset_volume, number_of_trades,
         taker_buy_base_asset_volume, taker_buy_quote_asset_volume, ignore]
        """
        raise NotImplementedError


class BinanceRESTClient(BinanceClientInterface):
    """
    Thin wrapper around Binance Spot's public REST endpoint
    (`GET /api/v3/klines`). Requires the `requests` library and outbound
    network access -- not required for local unit testing (see
    `FakeBinanceClient` in tests/conftest.py).
    """

    BASE_URL = "https://api.binance.com"
    MAX_LIMIT = 1000

    def __init__(self, base_url: Optional[str] = None, session=None, timeout: float = 10.0):
        self.base_url = base_url or self.BASE_URL
        self.timeout = timeout
        if session is None:
            import requests  # local import: keep `requests` optional for tests
            session = requests.Session()
        self._session = session

    def get_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> List[list]:
        assert_valid_timeframe(interval)
        limit = min(limit, self.MAX_LIMIT)

        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit,
        }
        if start_time is not None:
            params["startTime"] = int(start_time)
        if end_time is not None:
            params["endTime"] = int(end_time)

        response = self._session.get(
            f"{self.base_url}/api/v3/klines", params=params, timeout=self.timeout
        )
        response.raise_for_status()
        return response.json()
