<!--
README.md
----------
Purpose: Main entry-point documentation for the MarketMind-AI repository.
Explains what the project is, its architecture, and how to run it.
-->

# MarketMind-AI

**MarketMind-AI** is a personal, free, and open AI-assisted trading
research assistant built with a clean, modular, and scalable Python
architecture.

> ⚠️ **Status:** First version — architecture scaffold only. No trading
> logic is implemented yet. This repository currently defines the
> project structure that future features will be built on top of.

## Goals

This project is built for **personal use only** and is designed to
eventually support, at zero cost:

- 📈 Binance API integration (market data & free public endpoints)
- 📊 Technical analysis (indicators, patterns)
- 📰 News analysis (sentiment from free news sources)
- 🤖 AI-based market analysis
- 🔁 Backtesting
- 🛡️ Risk management
- 💼 Portfolio management
- 🧠 Machine learning models

## Architecture

MarketMind-AI follows **Clean Architecture** principles: business rules
live in the center (`core/`) and know nothing about frameworks, external
APIs, or databases. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
for the full breakdown of each layer and how data flows between them.

## Project structure

```
MarketMind-AI/
├── app/            # Application layer: orchestrates use cases
├── api/            # HTTP interface layer (thin adapter over app/)
├── config/         # Typed settings (settings.py) and constants (config.py)
├── core/           # Domain layer: entities, interfaces, business rules (populated — see below)
├── events/         # Event-driven architecture: event types & pub/sub contracts (populated — see below)
├── data/           # Market data acquisition (Binance, news, etc.)
├── services/       # External integrations (AI clients, notifications)
├── indicators/     # Pure technical indicator calculations (SMA, RSI...)
├── analysis/       # Technical / news / AI analysis
├── signals/        # Standardized signal representation & aggregation
├── strategies/     # Trading strategies, risk & portfolio management
├── backtesting/    # Historical strategy simulation & performance metrics
├── models/         # Machine learning models (training & inference)
├── database/       # Persistence layer (SQLite by default, free)
├── utils/          # Generic, reusable helper functions
├── logs/           # Local log file output (runtime, not a Python package)
├── tests/          # Automated tests (pytest)
├── docs/           # Architecture and design documentation
├── main.py         # Application entry point
├── requirements.txt
├── .gitignore
└── README.md
```

## Domain layer

`core/` is the first fully designed layer: entities and interfaces only,
no implementations. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#domain-layer-core)
for the full list of entities (`Candle`, `Ticker`, `OrderBook`, `Trade`,
`Position`, `Portfolio`, `Signal`, `IndicatorResult`, `NewsItem`,
`MarketState`) and interfaces (`MarketDataProvider`, `NewsProvider`,
`AIAnalyzer`, `IndicatorCalculator`, `Strategy`, `SignalGenerator`,
`RiskManager`, `DatabaseRepository`) it defines.

## Event-driven architecture

`events/` is the second fully designed package: the event vocabulary
(`MarketDataUpdated`, `CandleClosed`, `IndicatorCalculated`,
`NewsReceived`, `AIAnalysisCompleted`, `SignalGenerated`,
`PositionOpened`, `PositionClosed`, `RiskAlert`) plus the abstract
`Event`, `EventBus`, and `EventHandler` contracts that will let layers
communicate by publishing/subscribing instead of calling each other
directly. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md#event-driven-architecture-events)
for details. No bus implementation, no async, no external providers —
architecture only.

## Requirements

- Python 3.12
- Free Binance account (optional, for later versions — testnet supported)
- No paid services required

## Setup

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/MarketMind-AI.git
cd MarketMind-AI

# 2. Create and activate a virtual environment
python3.12 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) create a .env file for local configuration
# See config/settings.py for all available environment variables.

# 5. Run the application skeleton
python main.py
```

## Running tests

```bash
pytest
```

## Roadmap

- [x] Clean architecture scaffold (core, data, analysis, strategies, models, database, services, utils, app, tests, docs)
- [x] Extended scaffold (api, indicators, backtesting, signals, logs)
- [x] Domain layer design (entities & interfaces in `core/`)
- [x] Event-driven architecture design (event types & pub/sub contracts in `events/`)
- [ ] Binance market data integration
- [ ] Technical indicator calculations
- [ ] News sentiment analysis
- [ ] AI-based market commentary
- [ ] Signal generation & aggregation
- [ ] Backtesting engine
- [ ] Risk management rules
- [ ] Portfolio management
- [ ] Machine learning price prediction models
- [ ] REST API exposure

## License

Personal, private-use project. Not intended for redistribution or
commercial use.
