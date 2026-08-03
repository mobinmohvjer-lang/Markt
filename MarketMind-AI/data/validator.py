"""
DataValidator: detects corrupted or inconsistent candle data.
"""

import math
from typing import List, Tuple

from .models import Candle


class DataValidator:
    """Validates individual candles and batches of candles."""

    def validate_candle(self, candle: Candle) -> Tuple[bool, List[str]]:
        """
        Return (is_valid, list_of_issues) for a single candle.
        """
        issues: List[str] = []

        if candle is None:
            return False, ["candle is None"]

        numeric_fields = {
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
            "quote_volume": candle.quote_volume,
            "taker_buy_base": candle.taker_buy_base,
            "taker_buy_quote": candle.taker_buy_quote,
        }
        for name, value in numeric_fields.items():
            if value is None:
                issues.append(f"{name} is None")
            elif isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                issues.append(f"{name} is NaN/Inf")

        if issues:
            return False, issues

        if candle.open_time is None or candle.close_time is None:
            issues.append("missing open_time/close_time")
            return False, issues

        if candle.close_time <= candle.open_time:
            issues.append("close_time must be greater than open_time")

        if candle.open <= 0 or candle.high <= 0 or candle.low <= 0 or candle.close <= 0:
            issues.append("prices must be strictly positive")

        if candle.high < candle.low:
            issues.append("high < low")

        if candle.high < max(candle.open, candle.close):
            issues.append("high is less than open/close")

        if candle.low > min(candle.open, candle.close):
            issues.append("low is greater than open/close")

        if candle.volume < 0:
            issues.append("volume is negative")

        if candle.trades is not None and candle.trades < 0:
            issues.append("trades is negative")

        return (len(issues) == 0), issues

    def validate_batch(self, candles: List[Candle]) -> Tuple[List[Candle], List[Tuple[Candle, List[str]]]]:
        """
        Split a batch into (valid_candles, invalid_candles_with_issues).
        """
        valid: List[Candle] = []
        invalid: List[Tuple[Candle, List[str]]] = []
        for candle in candles:
            ok, issues = self.validate_candle(candle)
            if ok:
                valid.append(candle)
            else:
                invalid.append((candle, issues))
        return valid, invalid
