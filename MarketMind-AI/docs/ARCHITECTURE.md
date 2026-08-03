<!--
ARCHITECTURE.md
----------------
Purpose: Documents the intended Clean Architecture layout of MarketMind-AI
so future contributors (or future-you) understand where new code should go.
-->

# MarketMind-AI — Architecture

MarketMind-AI follows a **Clean Architecture** style layout. The core idea:
business rules live in the center and know nothing about frameworks or
external services; outer layers depend inward, never the reverse.

## Layers

| Layer | Folder | Depends on | Responsibility |
|---|---|---|---|
| Domain | `core/` | nothing | Entities, interfaces, business rules |
| Events | `events/` | `core` | Event-driven architecture: event types & pub/sub contracts |
| Data Access | `data/` | `core`, `events` | Market data acquisition & normalization |
| Persistence | `database/` | `core` | Storing/retrieving data (SQLite by default) |
| Indicators | `indicators/` | `core`, `events` | Pure technical indicator calculations (SMA, RSI, MACD...) |
| Analysis | `analysis/` | `core`, `data`, `indicators`, `events` | Technical / news / AI analysis |
| ML Models | `models/` | `core` | Training & inference for ML models |
| Signals | `signals/` | `core`, `analysis`, `events` | Standardized signal representation & aggregation |
| Strategies | `strategies/` | `core`, `analysis`, `signals`, `events` | Turning analysis/signals into trading decisions |
| Backtesting | `backtesting/` | `core`, `data`, `strategies`, `signals` | Simulating strategies against historical data |
| External Services | `services/` | `core`, `events` | Notifications, AI clients, schedulers, event bus implementation |
| Application | `app/` | all of the above | Orchestrates use cases |
| API | `api/` | `app` | HTTP interface exposing the application (thin adapter) |
| Configuration | `config/` | nothing | Typed settings & constants |
| Utilities | `utils/` | nothing | Generic, reusable helpers |
| Logs | `logs/` | nothing (runtime output) | Local log file storage, not a Python package |
| Tests | `tests/` | mirrors all layers | Automated tests |

## Guiding principles

1. **Dependency Rule** — inner layers (`core`) never import from outer
   layers (`data`, `services`, `app`, etc.).
2. **Interfaces over implementations** — outer layers implement
   interfaces/protocols defined in `core`, enabling easy swapping
   (e.g. replacing Binance with another exchange later).
3. **Free-first** — every dependency and integration chosen for this
   project targets free tiers or open-source tooling (Binance public API,
   SQLite, pytest, etc.).
4. **No trading logic yet** — this first version is a scaffold only. Each
   package currently contains only an explanatory `__init__.py` describing
   its future purpose, with the exception of `core/`, whose entities and
   interfaces are now fully defined (see below).
5. **Separation of calculation vs. interpretation vs. decision** —
   `indicators/` only calculates raw values, `analysis/` interprets those
   values into insights, `signals/` standardizes those insights into a
   common signal format, and `strategies/` turns signals into trading
   decisions. Each of these can be tested and swapped independently.
6. **Backtesting is a consumer, not a strategy** — `backtesting/` never
   contains trading rules; it only replays historical data through
   whatever strategy/signals are given to it and reports the results.
7. **API is the outermost adapter** — `api/` may only call into `app/`
   use cases, never directly into `core`, `data`, `analysis`, etc.

## Domain layer (`core/`)

`core/` is the only package with real content so far — entities and
interfaces, no implementations. It has no dependency on any other
package in this project (not even `config/`), which is why domain-level
enums (`OrderSide`, `PositionSide`, `PositionStatus`, `SignalDirection`)
live in `core/enums.py` rather than reusing `config/config.py`.

**Entities** (`core/entities/`) — plain, dependency-free dataclasses:

| Entity | File | Mutability | Represents |
|---|---|---|---|
| `Candle` | `candle.py` | frozen | A single OHLCV candlestick |
| `Ticker` | `ticker.py` | frozen | Real-time price snapshot |
| `OrderBook` / `OrderBookLevel` | `order_book.py` | frozen | Bid/ask depth snapshot |
| `Trade` | `trade.py` | frozen | An executed trade (market tape or own fill) |
| `Position` | `position.py` | mutable | An open/closed trading position |
| `Portfolio` | `portfolio.py` | mutable | Overall account state (cash + positions) |
| `Signal` | `signal.py` | frozen | A standardized trading signal |
| `IndicatorResult` | `indicator_result.py` | frozen | Output of a technical indicator |
| `NewsItem` | `news_item.py` | frozen | A single news article, optionally sentiment-scored |
| `MarketState` | `market_state.py` | frozen | Aggregated snapshot combining all of the above |

`Position` and `Portfolio` are mutable because they represent evolving
account state; every other entity is an immutable point-in-time snapshot.

**Interfaces** (`core/interfaces/`) — abstract contracts (`abc.ABC`),
implemented by outer layers in later versions:

| Interface | File | Future implementation lives in |
|---|---|---|
| `MarketDataProvider` | `market_data_provider.py` | `data/providers/` |
| `NewsProvider` | `news_provider.py` | `data/providers/` |
| `AIAnalyzer` | `ai_analyzer.py` | `services/` |
| `IndicatorCalculator` | `indicator_calculator.py` | `indicators/` |
| `Strategy` | `strategy.py` | `strategies/` |
| `SignalGenerator` | `signal_generator.py` | `signals/` |
| `RiskManager` | `risk_manager.py` | `strategies/risk_management/` |
| `DatabaseRepository` | `database_repository.py` | `database/repositories/` |

## Event-driven architecture (`events/`)

`events/` is the second fully designed package — event types and pub/sub
contracts only, no implementation. It depends only on `core/` (for entity
types referenced by event payloads) and has **zero** dependency on
Binance or any external provider: the event bus contract is fully
generic and transport-agnostic.

**Interfaces** (`events/interfaces/`):

| Interface | File | Responsibility |
|---|---|---|
| `Event` | `event.py` | Abstract base every concrete event extends (`event_id`, `occurred_at`, abstract `event_type`) |
| `EventBus` | `event_bus.py` | Publish/subscribe/unsubscribe contract for routing events to handlers |
| `EventHandler` | `event_handler.py` | Generic contract (`EventHandler[E]`) for any component that reacts to a specific event type |

**Event types** (`events/event_types/`), each a frozen dataclass extending `Event`:

| Event | File | Payload |
|---|---|---|
| `MarketDataUpdated` | `market_data_updated.py` | `symbol`, optional `Ticker`/`OrderBook` |
| `CandleClosed` | `candle_closed.py` | `Candle` |
| `IndicatorCalculated` | `indicator_calculated.py` | `IndicatorResult` |
| `NewsReceived` | `news_received.py` | `NewsItem` |
| `AIAnalysisCompleted` | `ai_analysis_completed.py` | `symbol`, `summary` |
| `SignalGenerated` | `signal_generated.py` | `Signal` |
| `PositionOpened` | `position_opened.py` | `Position` |
| `PositionClosed` | `position_closed.py` | `Position` |
| `RiskAlert` | `risk_alert.py` | `message`, `severity`, optional `symbol`/`Signal`/`Position` |

Concrete `EventBus` implementations (e.g. a simple in-memory synchronous
dispatcher for personal/local use, or an async-capable one later) will
live in a future outer layer (`services/` or `app/`), never in `events/`
itself.

## Planned data flow (future versions)

```
data/  ──►  indicators/  ──►  analysis/  ──►  signals/  ──►  strategies/
                                                                  │
                                                                  ▼
                                                          backtesting/  (offline validation)
                                                                  │
                                                                  ▼
                                                    app/ (use cases)  ──►  api/ / main.py
   ▲
   └────────── core/ (entities & interfaces, used by every layer above) ──────────┘

   Every arrow above may, in a future version, be realized by publishing
   and subscribing to events/ instead of a direct call, e.g.:

     data/  ──publishes──►  CandleClosed
     indicators/  ──subscribes to CandleClosed, publishes──►  IndicatorCalculated
     analysis/  ──subscribes to IndicatorCalculated & NewsReceived, publishes──►  AIAnalysisCompleted
     strategies/  ──subscribes to AIAnalysisCompleted, publishes──►  SignalGenerated
     app/  ──subscribes to SignalGenerated, RiskAlert, PositionOpened/Closed──►  orchestrates use cases

                 database/, services/, models/, utils/, logs/  (supporting layers, used as needed)
```
