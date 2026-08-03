"""
DataCleaner: sorts candles chronologically, removes duplicates, and drops
rows that fail validation.
"""

from typing import List, Optional

from .models import Candle
from .validator import DataValidator


class DataCleaner:
    def __init__(self, validator: Optional[DataValidator] = None):
        self.validator = validator or DataValidator()

    def remove_duplicates(self, candles: List[Candle]) -> List[Candle]:
        """
        Deduplicate by open_time, keeping the LAST occurrence
        (assumed most recent/authoritative if the same candle was re-fetched).
        """
        by_open_time = {}
        for candle in candles:
            by_open_time[candle.open_time] = candle
        return list(by_open_time.values())

    def sort_candles(self, candles: List[Candle]) -> List[Candle]:
        return sorted(candles, key=lambda c: c.open_time)

    def drop_invalid(self, candles: List[Candle]) -> List[Candle]:
        valid, _invalid = self.validator.validate_batch(candles)
        return valid

    def clean(self, candles: List[Candle]) -> List[Candle]:
        """
        Full cleaning pipeline: drop invalid -> dedupe -> sort.
        """
        candles = [c for c in candles if c is not None]
        candles = self.drop_invalid(candles)
        candles = self.remove_duplicates(candles)
        candles = self.sort_candles(candles)
        return candles
