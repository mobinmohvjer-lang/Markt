"""
MarketMind-AI :: Data Engine
============================

This package implements the Data Engine ONLY:

    - HistoricalDataDownloader
    - IncrementalDataUpdater
    - MarketDataStorage
    - DataValidator
    - DataCleaner
    - DataNormalizer
    - CandleCache
    - DataEngine (facade tying everything together)

No indicators, AI, strategies, or signal logic live here by design.
"""

from .config import TIMEFRAMES, TIMEFRAME_MS
from .models import Candle
from .client import BinanceClientInterface, BinanceRESTClient
from .validator import DataValidator
from .cleaner import DataCleaner
from .normalizer import DataNormalizer
from .cache import CandleCache
from .storage import MarketDataStorage
from .downloader import HistoricalDataDownloader
from .updater import IncrementalDataUpdater
from .engine import DataEngine

__all__ = [
    "TIMEFRAMES",
    "TIMEFRAME_MS",
    "Candle",
    "BinanceClientInterface",
    "BinanceRESTClient",
    "DataValidator",
    "DataCleaner",
    "DataNormalizer",
    "CandleCache",
    "MarketDataStorage",
    "HistoricalDataDownloader",
    "IncrementalDataUpdater",
    "DataEngine",
]
