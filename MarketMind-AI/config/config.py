"""
config.py
----------
Purpose:
    Holds static, non-secret configuration values: constants, enums,
    default parameters, and file paths. Unlike `settings.py` (which reads
    values from the environment), everything here is a fixed constant
    that is safe to version-control.

Design notes:
    - Keep secrets OUT of this file. API keys and credentials belong in
      `settings.py` and must come from environment variables.
    - This file is a good place to define enums shared across the app
      (e.g. supported exchanges, supported timeframes) so that
      `core`, `data`, `services`, `analysis`, and `strategies` modules
      all reference the same source of truth.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path


# Root directory of the project, useful for building relative paths
# (e.g. logs, cached data, exported reports) in a platform-independent way.
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# Directory where local data (cached market data, exports, logs) will be
# stored. Created lazily by whichever module first needs it.
DATA_DIR: Path = PROJECT_ROOT / "data"

# Directory reserved for generated documentation, reports, or diagrams.
DOCS_DIR: Path = PROJECT_ROOT / "docs"


class Exchange(str, Enum):
    """Supported exchanges. Only Binance is planned for the free/personal MVP."""

    BINANCE = "binance"


class TimeFrame(str, Enum):
    """
    Standard candlestick timeframes, matching Binance's kline intervals.
    Centralizing this avoids "magic strings" scattered across the codebase.
    """

    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"


class AssetClass(str, Enum):
    """Broad categories of tradable assets the assistant may support."""

    CRYPTO = "crypto"
    # Placeholder for future expansion (stocks, forex, etc.).


# Default trading pair used for local testing/demo purposes only.
DEFAULT_SYMBOL: str = "BTCUSDT"

# Default candlestick interval used across analysis modules unless overridden.
DEFAULT_TIMEFRAME: TimeFrame = TimeFrame.H1
