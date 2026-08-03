"""
Configuration constants for the Data Engine.
"""

# Supported Binance Spot kline intervals.
TIMEFRAMES = ("1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d")

# Duration of a single candle in milliseconds, per timeframe.
TIMEFRAME_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


def assert_valid_timeframe(timeframe: str) -> None:
    if timeframe not in TIMEFRAMES:
        raise ValueError(
            f"Unsupported timeframe '{timeframe}'. "
            f"Supported timeframes: {', '.join(TIMEFRAMES)}"
        )
