"""
core.entities package
------------------------
Purpose:
    Plain domain objects (dataclasses) that model the concepts the whole
    application reasons about: market data snapshots, trades, positions,
    portfolios, signals, indicator outputs, news items, and the
    aggregated market state.

    These are pure data containers:
    - No business logic, no calculations, no persistence, no I/O.
    - No dependencies on outer layers (`data`, `database`, `services`,
      `analysis`, `strategies`, `app`, `api`, `config`, etc.).
    - Safe to import from anywhere in the project.

Contents:
    - candle.py            -> Candle
    - ticker.py             -> Ticker
    - order_book.py         -> OrderBook, OrderBookLevel
    - trade.py              -> Trade
    - position.py           -> Position
    - portfolio.py          -> Portfolio
    - signal.py             -> Signal
    - indicator_result.py   -> IndicatorResult
    - news_item.py          -> NewsItem
    - market_state.py       -> MarketState
"""
