"""
tests/test_binance_provider.py

Unit tests for api/providers/binance_provider.py. The HTTPClient is
mocked entirely, so no real network calls are made.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from api.providers.binance_provider import BinanceProvider


class TestBinanceProvider(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.provider = BinanceProvider(self.client)

    def test_ping(self):
        self.client.get.return_value = {}
        result = self.provider.ping()
        self.client.get.assert_called_once_with("/api/v3/ping")
        self.assertEqual(result, {})

    def test_server_time(self):
        self.client.get.return_value = {"serverTime": 123456}
        result = self.provider.server_time()
        self.client.get.assert_called_once_with("/api/v3/time")
        self.assertEqual(result["serverTime"], 123456)

    def test_exchange_info_no_symbol(self):
        self.client.get.return_value = {"symbols": []}
        self.provider.exchange_info()
        self.client.get.assert_called_once_with("/api/v3/exchangeInfo", params=None)

    def test_exchange_info_with_symbol(self):
        self.client.get.return_value = {"symbols": []}
        self.provider.exchange_info(symbol="btcusdt")
        self.client.get.assert_called_once_with(
            "/api/v3/exchangeInfo", params={"symbol": "BTCUSDT"}
        )

    def test_ticker_single_symbol(self):
        self.client.get.return_value = {"symbol": "BTCUSDT", "lastPrice": "1"}
        self.provider.ticker(symbol="btcusdt")
        self.client.get.assert_called_once_with(
            "/api/v3/ticker/24hr", params={"symbol": "BTCUSDT"}
        )

    def test_ticker_all_symbols(self):
        self.client.get.return_value = []
        self.provider.ticker()
        self.client.get.assert_called_once_with("/api/v3/ticker/24hr", params=None)

    def test_klines(self):
        self.client.get.return_value = [[1, 2, 3]]
        result = self.provider.klines("btcusdt", "1h", limit=10, start_time=100, end_time=200)
        self.client.get.assert_called_once_with(
            "/api/v3/klines",
            params={
                "symbol": "BTCUSDT",
                "interval": "1h",
                "limit": 10,
                "startTime": 100,
                "endTime": 200,
            },
        )
        self.assertEqual(result, [[1, 2, 3]])

    def test_klines_minimal(self):
        self.client.get.return_value = []
        self.provider.klines("ethusdt", "5m")
        self.client.get.assert_called_once_with(
            "/api/v3/klines",
            params={"symbol": "ETHUSDT", "interval": "5m", "limit": 500},
        )

    def test_order_book(self):
        self.client.get.return_value = {"bids": [], "asks": []}
        self.provider.order_book("btcusdt", limit=50)
        self.client.get.assert_called_once_with(
            "/api/v3/depth", params={"symbol": "BTCUSDT", "limit": 50}
        )

    def test_recent_trades(self):
        self.client.get.return_value = []
        self.provider.recent_trades("btcusdt", limit=20)
        self.client.get.assert_called_once_with(
            "/api/v3/trades", params={"symbol": "BTCUSDT", "limit": 20}
        )


if __name__ == "__main__":
    unittest.main()
