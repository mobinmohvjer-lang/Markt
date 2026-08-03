"""
events package
-----------------
Purpose:
    Defines MarketMind-AI's event-driven architecture: the vocabulary of
    domain events that flow between layers, plus the abstract contracts
    (`Event`, `EventBus`, `EventHandler`) that any concrete pub/sub
    implementation must fulfill.

    This package is the backbone that will eventually let layers
    communicate by publishing and subscribing to events instead of
    calling each other directly -- e.g. `data/` publishes
    `CandleClosed`, `indicators/` subscribes to it and later publishes
    `IndicatorCalculated`, `strategies/` subscribes to that and
    publishes `SignalGenerated`, and so on.

    Design rules enforced by this package:
    - `events/` depends only on `core/` (for entity types referenced by
      event payloads, e.g. `Candle`, `Signal`, `Position`). It has ZERO
      dependency on Binance, any exchange, or any other external
      provider -- the event bus and event types are fully generic.
    - No business logic, no network code, no async implementation.
      Everything here is a data shape or an abstract contract.
    - Concrete event bus implementations (in-memory, Redis-backed, etc.)
      belong in a future outer layer (e.g. `services/` or `app/`), not
      in this package.

Contents:
    - interfaces/  -> Event (abstract base), EventBus, EventHandler
    - event_types/  -> Concrete event dataclasses: MarketDataUpdated,
      CandleClosed, IndicatorCalculated, NewsReceived,
      AIAnalysisCompleted, SignalGenerated, PositionOpened,
      PositionClosed, RiskAlert.
"""
