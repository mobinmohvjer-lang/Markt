"""
test_core_domain.py
----------------------
Purpose:
    Smoke tests for the `core` domain layer. Since this layer contains
    only data structures and abstract contracts (no business logic yet),
    these tests only verify:
      1. Every entity dataclass can be instantiated with valid data.
      2. Every interface is genuinely abstract (cannot be instantiated
         directly, enforcing that concrete implementations must fulfill
         the contract).

Run with:
    pytest
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from core.entities.candle import Candle
from core.entities.indicator_result import IndicatorResult
from core.entities.market_state import MarketState
from core.entities.news_item import NewsItem
from core.entities.order_book import OrderBook, OrderBookLevel
from core.entities.portfolio import Portfolio
from core.entities.position import Position
from core.entities.signal import Signal
from core.entities.ticker import Ticker
from core.entities.trade import Trade
from core.enums import OrderSide, PositionSide, SignalDirection
from core.interfaces.ai_analyzer import AIAnalyzer
from core.interfaces.database_repository import DatabaseRepository
from core.interfaces.indicator_calculator import IndicatorCalculator
from core.interfaces.market_data_provider import MarketDataProvider
from core.interfaces.news_provider import NewsProvider
from core.interfaces.risk_manager import RiskManager
from core.interfaces.signal_generator import SignalGenerator
from core.interfaces.strategy import Strategy

NOW = datetime.now(timezone.utc)


def test_candle_instantiates() -> None:
    """Candle should accept its required OHLCV fields."""
    candle = Candle(
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
    assert candle.symbol == "BTCUSDT"


def test_ticker_instantiates() -> None:
    """Ticker should accept a last price and timestamp."""
    ticker = Ticker(symbol="BTCUSDT", last_price=Decimal("100"), timestamp=NOW)
    assert ticker.last_price == Decimal("100")


def test_order_book_instantiates() -> None:
    """OrderBook should hold bid/ask levels."""
    book = OrderBook(
        symbol="BTCUSDT",
        timestamp=NOW,
        bids=[OrderBookLevel(price=Decimal("99"), quantity=Decimal("1"))],
        asks=[OrderBookLevel(price=Decimal("101"), quantity=Decimal("1"))],
    )
    assert book.bids[0].price == Decimal("99")


def test_trade_instantiates() -> None:
    """Trade should accept side, price, and quantity."""
    trade = Trade(
        trade_id="t1",
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        price=Decimal("100"),
        quantity=Decimal("1"),
        executed_at=NOW,
    )
    assert trade.side is OrderSide.BUY


def test_position_and_portfolio_instantiate() -> None:
    """Position and Portfolio should compose together."""
    position = Position(
        position_id="p1",
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        entry_price=Decimal("100"),
        quantity=Decimal("1"),
        opened_at=NOW,
    )
    portfolio = Portfolio(
        portfolio_id="port1",
        base_currency="USDT",
        cash_balance=Decimal("1000"),
        positions=[position],
    )
    assert portfolio.positions[0].symbol == "BTCUSDT"


def test_signal_instantiates() -> None:
    """Signal should accept a direction and confidence score."""
    signal = Signal(
        signal_id="s1",
        symbol="BTCUSDT",
        direction=SignalDirection.BUY,
        confidence=0.75,
        source="manual-test",
        timeframe="1h",
        generated_at=NOW,
    )
    assert signal.direction is SignalDirection.BUY


def test_indicator_result_instantiates() -> None:
    """IndicatorResult should hold named output values."""
    result = IndicatorResult(
        indicator_name="RSI",
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=NOW,
        values={"value": 55.2},
    )
    assert result.values["value"] == 55.2


def test_news_item_instantiates() -> None:
    """NewsItem should accept basic article metadata."""
    item = NewsItem(
        news_id="n1",
        source="TestWire",
        title="Test headline",
        url="https://example.com",
        published_at=NOW,
    )
    assert item.title == "Test headline"


def test_market_state_instantiates() -> None:
    """MarketState should aggregate optional sub-entities."""
    state = MarketState(symbol="BTCUSDT", timeframe="1h", timestamp=NOW)
    assert state.recent_trades == []


@pytest.mark.parametrize(
    "interface",
    [
        MarketDataProvider,
        NewsProvider,
        AIAnalyzer,
        IndicatorCalculator,
        Strategy,
        SignalGenerator,
        RiskManager,
        DatabaseRepository,
    ],
)
def test_interfaces_are_abstract(interface: type) -> None:
    """Every core interface must be abstract and non-instantiable directly."""
    with pytest.raises(TypeError):
        interface()  # type: ignore[abstract]
