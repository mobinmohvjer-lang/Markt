"""
Shared test helpers for the Data Engine unit tests.

Uses only the standard library (unittest) -- no pytest dependency, since
this sandbox has no network access to install third-party packages.
"""



from data.client import BinanceClientInterface
from data.config import TIMEFRAME_MS
from data.models import Candle


class FakeBinanceClient(BinanceClientInterface):
    """
    Deterministic synthetic kline generator standing in for the real
    Binance REST API in tests (no network access required/allowed).

    Generates one candle per `interval` step, starting at price `base_price`
    and drifting up slightly each candle, from `series_start` up to (and
    excluding) `series_end` (exclusive upper bound on open_time).
    """

    def __init__(self, series_start: int, series_end: int, base_price: float = 100.0):
        self.series_start = series_start
        self.series_end = series_end
        self.base_price = base_price
        self.calls = []

    def get_klines(self, symbol, interval, start_time=None, end_time=None, limit=1000):
        self.calls.append((symbol, interval, start_time, end_time, limit))
        step = TIMEFRAME_MS[interval]
        cursor = start_time if start_time is not None else self.series_start
        cursor = max(cursor, self.series_start)

        upper_bound = self.series_end
        if end_time is not None:
            upper_bound = min(upper_bound, end_time + 1)

        klines = []
        idx = (cursor - self.series_start) // step
        t = cursor
        while t < upper_bound and len(klines) < limit:
            open_price = self.base_price + idx * 0.5
            close_price = open_price + 0.25
            high_price = close_price + 0.1
            low_price = open_price - 0.1
            volume = 10.0 + idx
            close_t = t + step - 1
            klines.append(
                [
                    t,
                    f"{open_price:.8f}",
                    f"{high_price:.8f}",
                    f"{low_price:.8f}",
                    f"{close_price:.8f}",
                    f"{volume:.8f}",
                    close_t,
                    f"{volume * close_price:.8f}",
                    100 + idx,
                    f"{volume / 2:.8f}",
                    f"{(volume / 2) * close_price:.8f}",
                    "0",
                ]
            )
            t += step
            idx += 1
        return klines


def make_fake_client(num_candles: int = 1000, timeframe: str = "1m", series_start: int = 1_700_000_000_000):
    series_end = series_start + num_candles * TIMEFRAME_MS[timeframe]
    return FakeBinanceClient(series_start, series_end)


def make_candle(open_time, symbol="BTCUSDT", timeframe="1m", close_time=None, **overrides):
    base = dict(
        symbol=symbol,
        timeframe=timeframe,
        open_time=open_time,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10.0,
        close_time=close_time if close_time is not None else open_time + 59999,
        quote_volume=1000.0,
        trades=5,
        taker_buy_base=1.0,
        taker_buy_quote=100.0,
    )
    base.update(overrides)
    return Candle(**base)
