# MarketMind-AI — Data Engine

This module implements **only** the Data Engine layer for Binance Spot OHLCV
data. No indicators, AI, strategies, or signal logic are included by design.

## Components

| Class                       | File                    | Responsibility |
|------------------------------|-------------------------|----------------|
| `Candle`                     | `data/models.py`        | Immutable OHLCV record + Binance raw-kline parsing |
| `BinanceClientInterface`     | `data/client.py`        | Abstract kline source (inject a fake for tests) |
| `BinanceRESTClient`          | `data/client.py`        | Real `GET /api/v3/klines` implementation |
| `DataValidator`               | `data/validator.py`     | Detects corrupted/inconsistent candles |
| `DataCleaner`                 | `data/cleaner.py`       | Dedupes, sorts, drops invalid rows |
| `DataNormalizer`              | `data/normalizer.py`    | Normalizes numeric precision/types |
| `MarketDataStorage`           | `data/storage.py`       | SQLite storage, batch inserts, no duplicates |
| `CandleCache`                 | `data/cache.py`         | In-memory LRU cache of recently used candles |
| `HistoricalDataDownloader`   | `data/downloader.py`    | Paginated historical download |
| `IncrementalDataUpdater`     | `data/updater.py`       | Resumes from the last stored candle |
| `DataEngine`                  | `data/engine.py`        | Facade wiring everything together |

## Supported timeframes

`1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d` (see `data/config.py`).

## Quick start

```python
from data import DataEngine, BinanceRESTClient

engine = DataEngine(client=BinanceRESTClient(), db_path="market_data.sqlite3")

# One-time historical backfill (ms since epoch)
engine.download_history("BTCUSDT", "1h", start_time=1_600_000_000_000)

# Resume automatically from the last stored candle
engine.update_latest("BTCUSDT", "1h")

# Fast reads (served from cache when unbounded)
candles = engine.load_history("BTCUSDT", "1h", limit=500)
last = engine.load_last_candle("BTCUSDT", "1h")

engine.clear_cache()
engine.close()
```

Each component (`HistoricalDataDownloader`, `IncrementalDataUpdater`,
`MarketDataStorage`, `DataValidator`, `DataCleaner`, `DataNormalizer`,
`CandleCache`) can also be used directly/independently if you don't want the
`DataEngine` facade.

## Running the tests

No third-party test dependencies required (uses `unittest` from the standard
library — no network/pytest needed):

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

61 tests covering validation, cleaning, normalization, storage
(dedup/persistence/bounded loads), caching (LRU eviction, trimming),
historical download pagination across all 8 timeframes, incremental resume
behavior, and the `DataEngine` facade.

Historical downloads are tested against a deterministic
`FakeBinanceClient` (see `tests/helpers.py`) so no real network access is
required.
