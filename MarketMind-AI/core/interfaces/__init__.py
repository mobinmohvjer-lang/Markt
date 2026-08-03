"""
core.interfaces package
--------------------------
Purpose:
    Abstract base classes (contracts) that outer layers must implement.
    Following the Dependency Inversion Principle, `core` defines *what*
    capabilities the application needs, while concrete implementations
    (a Binance client, a specific news API, an LLM wrapper, a SQLite
    repository, ...) live in outer layers (`data`, `services`,
    `database`, `analysis`, `strategies`, etc.) and depend on these
    interfaces -- never the other way around.

    Every interface here is an `abc.ABC` with `@abstractmethod` members
    only: no implementation, no default behavior, no I/O.

Contents:
    - market_data_provider.py  -> MarketDataProvider
    - news_provider.py         -> NewsProvider
    - ai_analyzer.py           -> AIAnalyzer
    - indicator_calculator.py  -> IndicatorCalculator
    - strategy.py              -> Strategy
    - signal_generator.py      -> SignalGenerator
    - risk_manager.py          -> RiskManager
    - database_repository.py   -> DatabaseRepository
"""
