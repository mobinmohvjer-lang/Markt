"""
MarketDataStorage: SQLite-backed storage for OHLCV candles.

Design goals:
  - Efficient batch inserts (executemany, single transaction).
  - No duplicate candles (UNIQUE constraint on symbol/timeframe/open_time
    with INSERT OR IGNORE).
  - Fast loading via an index on (symbol, timeframe, open_time).
  - `load_last_candle` for resuming downloads from where we left off.
"""

import sqlite3
from typing import List, Optional

from .models import Candle

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    open_time       INTEGER NOT NULL,
    open            REAL NOT NULL,
    high            REAL NOT NULL,
    low             REAL NOT NULL,
    close           REAL NOT NULL,
    volume          REAL NOT NULL,
    close_time      INTEGER NOT NULL,
    quote_volume    REAL NOT NULL DEFAULT 0,
    trades          INTEGER NOT NULL DEFAULT 0,
    taker_buy_base  REAL NOT NULL DEFAULT 0,
    taker_buy_quote REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, timeframe, open_time)
);

CREATE INDEX IF NOT EXISTS idx_candles_lookup
    ON candles (symbol, timeframe, open_time);
"""

_INSERT_SQL = """
INSERT OR IGNORE INTO candles (
    symbol, timeframe, open_time, open, high, low, close, volume,
    close_time, quote_volume, trades, taker_buy_base, taker_buy_quote
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_SELECT_COLUMNS = ", ".join(Candle.columns())


class MarketDataStorage:
    def __init__(self, db_path: str = "market_data.sqlite3"):
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA synchronous=NORMAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def insert_candles(self, candles: List[Candle]) -> int:
        """
        Batch insert candles, ignoring any that would duplicate an existing
        (symbol, timeframe, open_time) row. Returns the number of NEW rows
        actually inserted.
        """
        if not candles:
            return 0
        rows = [c.as_tuple() for c in candles]
        before = self._conn.total_changes
        with self._conn:
            self._conn.executemany(_INSERT_SQL, rows)
        after = self._conn.total_changes
        return after - before

    def load_history(
        self,
        symbol: str,
        timeframe: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> List[Candle]:
        """
        Load candles for a symbol/timeframe, ordered ascending by open_time,
        optionally bounded by [start_time, end_time] (inclusive) and capped
        by `limit`.
        """
        query = f"SELECT {_SELECT_COLUMNS} FROM candles WHERE symbol = ? AND timeframe = ?"
        params: list = [symbol.upper(), timeframe]

        if start_time is not None:
            query += " AND open_time >= ?"
            params.append(int(start_time))
        if end_time is not None:
            query += " AND open_time <= ?"
            params.append(int(end_time))

        query += " ORDER BY open_time ASC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))

        cursor = self._conn.execute(query, params)
        return [Candle.from_row(row) for row in cursor.fetchall()]

    def load_last_candle(self, symbol: str, timeframe: str) -> Optional[Candle]:
        query = (
            f"SELECT {_SELECT_COLUMNS} FROM candles "
            "WHERE symbol = ? AND timeframe = ? "
            "ORDER BY open_time DESC LIMIT 1"
        )
        cursor = self._conn.execute(query, (symbol.upper(), timeframe))
        row = cursor.fetchone()
        return Candle.from_row(row) if row else None

    def count(self, symbol: str, timeframe: str) -> int:
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM candles WHERE symbol = ? AND timeframe = ?",
            (symbol.upper(), timeframe),
        )
        return cursor.fetchone()[0]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
