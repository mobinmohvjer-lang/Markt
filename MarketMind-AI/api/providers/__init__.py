"""
api/providers package

Clean, single-responsibility HTTP wrappers around external data
sources. No trading logic, no indicators, no AI, no signal
generation -- providers only translate method calls into HTTP
requests via an injected HTTPClient and return decoded JSON.
"""

from api.providers.base import BaseProvider
from api.providers.binance_provider import BinanceProvider, DEFAULT_BINANCE_BASE_URL
from api.providers.coingecko_provider import CoinGeckoProvider, DEFAULT_COINGECKO_BASE_URL
from api.providers.news_provider import NewsProvider

__all__ = [
    "BaseProvider",
    "BinanceProvider",
    "DEFAULT_BINANCE_BASE_URL",
    "CoinGeckoProvider",
    "DEFAULT_COINGECKO_BASE_URL",
    "NewsProvider",
]
