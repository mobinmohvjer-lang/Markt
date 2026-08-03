"""
events.event_types package
------------------------------
Purpose:
    Concrete event dataclasses, each extending `events.interfaces.event.Event`.
    Every event pairs the common `event_id` / `occurred_at` fields with a
    payload built from `core` entities -- these are pure data containers,
    not business logic.

Contents:
    - market_data_updated.py    -> MarketDataUpdated
    - candle_closed.py           -> CandleClosed
    - indicator_calculated.py    -> IndicatorCalculated
    - news_received.py           -> NewsReceived
    - ai_analysis_completed.py   -> AIAnalysisCompleted
    - signal_generated.py        -> SignalGenerated
    - position_opened.py         -> PositionOpened
    - position_closed.py         -> PositionClosed
    - risk_alert.py              -> RiskAlert
"""
