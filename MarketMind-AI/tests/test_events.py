"""
test_events.py
----------------
Purpose:
    Smoke tests for the `events` package. Since this layer contains only
    data structures and abstract contracts (no business logic, no bus
    implementation yet), these tests only verify:
      1. Every concrete event dataclass can be instantiated and is a
         proper `Event` subclass with a distinct `event_type`.
      2. `Event`, `EventBus`, and `EventHandler` are genuinely abstract
         (cannot be instantiated directly).

Run with:
    pytest
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.entities.candle import Candle
from core.entities.indicator_result import IndicatorResult
from core.entities.news_item import NewsItem
from core.entities.position import Position
from core.entities.signal import Signal
from core.entities.ticker import Ticker
from core.enums import PositionSide, SignalDirection
from events.event_types.ai_analysis_completed import AIAnalysisCompleted
from events.event_types.candle_closed import CandleClosed
from events.event_types.indicator_calculated import IndicatorCalculated
from events.event_types.market_data_updated import MarketDataUpdated
from events.event_types.news_received import NewsReceived
from events.event_types.position_closed import PositionClosed
from events.event_types.position_opened import PositionOpened
from events.event_types.risk_alert import RiskAlert
from events.event_types.signal_generated import SignalGenerated
from events.interfaces.event import Event
from events.interfaces.event_bus import EventBus
from events.interfaces.event_handler import EventHandler

NOW = datetime.now(timezone.utc)

CANDLE = Candle(
    symbol="BTCUSDT",
    timeframe="1h",
    open_time=NOW,
    close_time=NOW,
    open=Decimal("100"),
    high=Decimal("110"),
    low=Decimal("95"),
    close=Decimal("105"),
    volume=Decimal("10"),
)

SIGNAL = Signal(
    signal_id="s1",
    symbol="BTCUSDT",
    direction=SignalDirection.BUY,
    confidence=0.8,
    source="test",
    timeframe="1h",
    generated_at=NOW,
)

POSITION = Position(
    position_id="p1",
    symbol="BTCUSDT",
    side=PositionSide.LONG,
    entry_price=Decimal("100"),
    quantity=Decimal("1"),
    opened_at=NOW,
)


@pytest.mark.parametrize(
    "event, expected_type",
    [
        (MarketDataUpdated(event_id="e", occurred_at=NOW, symbol="BTCUSDT"), "MarketDataUpdated"),
        (CandleClosed(event_id="e", occurred_at=NOW, candle=CANDLE), "CandleClosed"),
        (
            IndicatorCalculated(
                event_id="e",
                occurred_at=NOW,
                indicator_result=IndicatorResult(
                    indicator_name="RSI", symbol="BTCUSDT", timeframe="1h",
                    timestamp=NOW, values={"value": 50.0},
                ),
            ),
            "IndicatorCalculated",
        ),
        (
            NewsReceived(
                event_id="e",
                occurred_at=NOW,
                news_item=NewsItem(
                    news_id="n1", source="TestWire", title="Headline",
                    url="https://example.com", published_at=NOW,
                ),
            ),
            "NewsReceived",
        ),
        (
            AIAnalysisCompleted(event_id="e", occurred_at=NOW, symbol="BTCUSDT", summary="test"),
            "AIAnalysisCompleted",
        ),
        (SignalGenerated(event_id="e", occurred_at=NOW, signal=SIGNAL), "SignalGenerated"),
        (PositionOpened(event_id="e", occurred_at=NOW, position=POSITION), "PositionOpened"),
        (PositionClosed(event_id="e", occurred_at=NOW, position=POSITION), "PositionClosed"),
        (
            RiskAlert(event_id="e", occurred_at=NOW, message="Exposure limit reached", severity="warning"),
            "RiskAlert",
        ),
    ],
)
def test_event_instantiates_and_reports_type(event: Event, expected_type: str) -> None:
    """Each concrete event should be an Event and report its own event_type."""
    assert isinstance(event, Event)
    assert event.event_type == expected_type


@pytest.mark.parametrize("interface", [Event, EventBus, EventHandler])
def test_core_event_interfaces_are_abstract(interface: type) -> None:
    """Event, EventBus, and EventHandler must all be non-instantiable directly."""
    with pytest.raises(TypeError):
        interface()  # type: ignore[abstract]
