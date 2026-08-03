"""
core package
-------------
Purpose:
    This is the "domain layer" in Clean Architecture terms -- the heart
    of the application. It contains the core business entities and
    abstract contracts that are independent of any framework, database,
    or external API.

    Following the Dependency Rule of Clean Architecture, code in `core`
    must NEVER import from outer layers such as `services`, `data`,
    `database`, `analysis`, `strategies`, `app`, `api`, or `config`.
    Everything else may depend on `core`, but `core` depends on nothing
    project-specific (only the Python standard library).

Contents:
    - enums.py          -> Shared domain enumerations (OrderSide,
                           PositionSide, PositionStatus, SignalDirection).
    - entities/          -> Plain domain objects (dataclasses):
                           Candle, Ticker, OrderBook, Trade, Position,
                           Portfolio, Signal, IndicatorResult, NewsItem,
                           MarketState.
    - interfaces/         -> Abstract contracts (abc.ABC) that outer
                           layers implement: MarketDataProvider,
                           NewsProvider, AIAnalyzer, IndicatorCalculator,
                           Strategy, SignalGenerator, RiskManager,
                           DatabaseRepository.

This first version contains architecture only: no implementations, no
API calls, no indicator/trading logic.
"""
