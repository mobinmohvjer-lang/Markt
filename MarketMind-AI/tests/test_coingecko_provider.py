"""
tests/test_coingecko_provider.py

Unit tests for api/providers/coingecko_provider.py. The HTTPClient is
mocked entirely, so no real network calls are made.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from api.providers.coingecko_provider import CoinGeckoProvider


class TestCoinGeckoProvider(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.provider = CoinGeckoProvider(self.client)

    def test_markets_defaults(self):
        self.client.get.return_value = []
        self.provider.markets()
        self.client.get.assert_called_once_with(
            "/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 100,
                "page": 1,
                "sparkline": "false",
            },
        )

    def test_markets_with_ids(self):
        self.client.get.return_value = []
        self.provider.markets(vs_currency="eur", ids=["bitcoin", "ethereum"], per_page=5, page=2, sparkline=True)
        self.client.get.assert_called_once_with(
            "/coins/markets",
            params={
                "vs_currency": "eur",
                "order": "market_cap_desc",
                "per_page": 5,
                "page": 2,
                "sparkline": "true",
                "ids": "bitcoin,ethereum",
            },
        )

    def test_coin_details_defaults(self):
        self.client.get.return_value = {"id": "bitcoin"}
        result = self.provider.coin_details("bitcoin")
        self.client.get.assert_called_once_with(
            "/coins/bitcoin",
            params={
                "localization": "false",
                "tickers": "false",
                "market_data": "true",
                "community_data": "false",
                "developer_data": "false",
                "sparkline": "false",
            },
        )
        self.assertEqual(result["id"], "bitcoin")

    def test_coin_details_custom_flags(self):
        self.client.get.return_value = {}
        self.provider.coin_details(
            "ethereum",
            localization=True,
            tickers=True,
            market_data=False,
            community_data=True,
            developer_data=True,
            sparkline=True,
        )
        self.client.get.assert_called_once_with(
            "/coins/ethereum",
            params={
                "localization": "true",
                "tickers": "true",
                "market_data": "false",
                "community_data": "true",
                "developer_data": "true",
                "sparkline": "true",
            },
        )


if __name__ == "__main__":
    unittest.main()
