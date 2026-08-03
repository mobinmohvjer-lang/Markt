"""
database package
------------------
Purpose:
    Handles persistence: storing and retrieving historical market data,
    trade logs, backtest results, and application state.

    For a free, personal-use project, the default backend will be
    SQLite (via `settings.database_url`), which requires no external
    server or paid hosting. The design should still allow swapping to
    another engine later (e.g. PostgreSQL) without touching business
    logic, by keeping all persistence behind repository interfaces
    defined in `core`.

Planned contents (future versions):
    - connection.py: database engine/session setup.
    - models/: ORM table definitions (e.g. SQLAlchemy models).
    - repositories/: concrete repository implementations
      (e.g. `TradeRepository`, `MarketDataRepository`).
    - migrations/: schema migration scripts.

Currently empty: no trading logic implemented yet.
"""
