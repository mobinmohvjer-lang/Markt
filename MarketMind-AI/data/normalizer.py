"""
DataNormalizer: normalizes numeric values to consistent types/precision
so downstream storage and consumers never see mixed representations
(e.g. Decimal vs str vs float, or inconsistent rounding).
"""

from typing import List

from .models import Candle

DEFAULT_PRICE_PRECISION = 8
DEFAULT_VOLUME_PRECISION = 8


class DataNormalizer:
    def __init__(
        self,
        price_precision: int = DEFAULT_PRICE_PRECISION,
        volume_precision: int = DEFAULT_VOLUME_PRECISION,
    ):
        self.price_precision = price_precision
        self.volume_precision = volume_precision

    def normalize_candle(self, candle: Candle) -> Candle:
        return Candle(
            symbol=candle.symbol.upper(),
            timeframe=candle.timeframe,
            open_time=int(candle.open_time),
            open=round(float(candle.open), self.price_precision),
            high=round(float(candle.high), self.price_precision),
            low=round(float(candle.low), self.price_precision),
            close=round(float(candle.close), self.price_precision),
            volume=round(float(candle.volume), self.volume_precision),
            close_time=int(candle.close_time),
            quote_volume=round(float(candle.quote_volume), self.volume_precision),
            trades=int(candle.trades),
            taker_buy_base=round(float(candle.taker_buy_base), self.volume_precision),
            taker_buy_quote=round(float(candle.taker_buy_quote), self.volume_precision),
        )

    def normalize_batch(self, candles: List[Candle]) -> List[Candle]:
        return [self.normalize_candle(c) for c in candles]
