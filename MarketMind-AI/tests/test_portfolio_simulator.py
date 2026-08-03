"""
test_portfolio_simulator.py
------------------------------
Purpose:
    Unit tests for `PortfolioSimulator` (Backtesting Engine Part 3).

Uses the standard-library ``unittest`` framework, matching every other
test file in this repository (no external test-runner dependency).

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import copy
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from core.entities.candle import Candle
from core.entities.portfolio import Portfolio
from core.entities.position import Position
from core.enums import OrderSide, PositionSide, PositionStatus

from backtesting.exceptions import BacktestValidationError
from backtesting.portfolio_simulator import PortfolioSimulator

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------
def make_portfolio(*, cash_balance="10000", positions: list | None = None) -> Portfolio:
    return Portfolio(
        portfolio_id="portfolio-1",
        base_currency="USDT",
        cash_balance=Decimal(str(cash_balance)),
        positions=positions or [],
    )


def make_candle(*, open_time: datetime, close, symbol: str = "BTCUSDT") -> Candle:
    close = Decimal(str(close))
    return Candle(
        symbol=symbol,
        timeframe="1h",
        open_time=open_time,
        close_time=open_time + timedelta(hours=1),
        open=Decimal("100"),
        high=close + Decimal("5"),
        low=close - Decimal("5"),
        close=close,
        volume=Decimal("1000"),
    )


def make_open_position(
    *,
    symbol: str = "BTCUSDT",
    entry_price="100",
    quantity="10",
    side: PositionSide = PositionSide.LONG,
    opened_at: datetime = NOW,
) -> Position:
    return Position(
        position_id=f"{symbol}-existing",
        symbol=symbol,
        side=side,
        entry_price=Decimal(str(entry_price)),
        quantity=Decimal(str(quantity)),
        opened_at=opened_at,
        status=PositionStatus.OPEN,
        current_price=Decimal(str(entry_price)),
    )


# ----------------------------------------------------------------------
# Construction
# ----------------------------------------------------------------------
class TestConstruction(unittest.TestCase):
    def test_construction_with_valid_portfolio_succeeds(self):
        portfolio = make_portfolio()
        simulator = PortfolioSimulator(portfolio)
        self.assertIsInstance(simulator.portfolio, Portfolio)
        self.assertEqual(simulator.cash_balance, Decimal("10000"))
        self.assertEqual(simulator.trades, [])

    def test_construction_rejects_non_portfolio(self):
        with self.assertRaises(BacktestValidationError):
            PortfolioSimulator("not-a-portfolio")

    def test_construction_rejects_none(self):
        with self.assertRaises(BacktestValidationError):
            PortfolioSimulator(None)

    def test_construction_deep_copies_the_portfolio(self):
        portfolio = make_portfolio()
        simulator = PortfolioSimulator(portfolio)
        self.assertIsNot(simulator.portfolio, portfolio)
        self.assertIsNot(simulator.portfolio.positions, portfolio.positions)

    def test_construction_does_not_mutate_caller_portfolio(self):
        portfolio = make_portfolio(cash_balance="5000")
        original = copy.deepcopy(portfolio)
        simulator = PortfolioSimulator(portfolio)

        simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)

        self.assertEqual(portfolio.cash_balance, original.cash_balance)
        self.assertEqual(portfolio.positions, original.positions)

    def test_construction_deep_copies_existing_positions(self):
        existing = make_open_position()
        portfolio = make_portfolio(cash_balance="0", positions=[existing])
        simulator = PortfolioSimulator(portfolio)

        simulator.close_position(symbol="BTCUSDT", price=Decimal("150"), timestamp=NOW)

        # Caller's original position object must remain untouched.
        self.assertEqual(existing.status, PositionStatus.OPEN)
        self.assertIsNone(existing.realized_pnl)


# ----------------------------------------------------------------------
# Position lookup
# ----------------------------------------------------------------------
class TestPositionLookup(unittest.TestCase):
    def test_get_open_position_returns_none_when_none_open(self):
        simulator = PortfolioSimulator(make_portfolio())
        self.assertIsNone(simulator.get_open_position("BTCUSDT"))

    def test_get_open_position_returns_the_open_position(self):
        position = make_open_position(symbol="BTCUSDT")
        simulator = PortfolioSimulator(make_portfolio(cash_balance="0", positions=[position]))
        found = simulator.get_open_position("BTCUSDT")
        self.assertIsNotNone(found)
        self.assertEqual(found.symbol, "BTCUSDT")

    def test_get_open_position_ignores_closed_positions(self):
        closed = make_open_position(symbol="BTCUSDT")
        closed.status = PositionStatus.CLOSED
        simulator = PortfolioSimulator(make_portfolio(positions=[closed]))
        self.assertIsNone(simulator.get_open_position("BTCUSDT"))

    def test_get_open_position_ignores_other_symbols(self):
        position = make_open_position(symbol="ETHUSDT")
        simulator = PortfolioSimulator(make_portfolio(positions=[position]))
        self.assertIsNone(simulator.get_open_position("BTCUSDT"))

    def test_get_open_position_rejects_empty_symbol(self):
        simulator = PortfolioSimulator(make_portfolio())
        with self.assertRaises(BacktestValidationError):
            simulator.get_open_position("")

    def test_has_open_position_true_and_false(self):
        position = make_open_position(symbol="BTCUSDT")
        simulator = PortfolioSimulator(make_portfolio(cash_balance="0", positions=[position]))
        self.assertTrue(simulator.has_open_position("BTCUSDT"))
        self.assertFalse(simulator.has_open_position("ETHUSDT"))

    def test_get_open_positions_returns_all_open_across_symbols(self):
        btc = make_open_position(symbol="BTCUSDT")
        eth = make_open_position(symbol="ETHUSDT")
        closed = make_open_position(symbol="SOLUSDT")
        closed.status = PositionStatus.CLOSED
        simulator = PortfolioSimulator(
            make_portfolio(cash_balance="0", positions=[btc, eth, closed])
        )
        open_positions = simulator.get_open_positions()
        self.assertEqual({p.symbol for p in open_positions}, {"BTCUSDT", "ETHUSDT"})

    def test_get_open_positions_empty_when_none_open(self):
        simulator = PortfolioSimulator(make_portfolio())
        self.assertEqual(simulator.get_open_positions(), [])


# ----------------------------------------------------------------------
# Opening positions
# ----------------------------------------------------------------------
class TestOpenPosition(unittest.TestCase):
    def test_open_position_spends_all_cash_and_records_trade(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        trade = simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)

        self.assertIsNotNone(trade)
        self.assertEqual(trade.side, OrderSide.BUY)
        self.assertEqual(trade.symbol, "BTCUSDT")
        self.assertEqual(trade.price, Decimal("100"))
        self.assertEqual(trade.quantity, Decimal("10"))
        self.assertEqual(trade.executed_at, NOW)
        self.assertEqual(simulator.cash_balance, Decimal("0"))
        self.assertEqual(len(simulator.trades), 1)

    def test_open_position_creates_open_long_position_by_default(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)

        position = simulator.get_open_position("BTCUSDT")
        self.assertIsNotNone(position)
        self.assertEqual(position.side, PositionSide.LONG)
        self.assertEqual(position.status, PositionStatus.OPEN)
        self.assertEqual(position.entry_price, Decimal("100"))
        self.assertEqual(position.quantity, Decimal("10"))
        self.assertEqual(position.opened_at, NOW)
        self.assertEqual(position.current_price, Decimal("100"))
        self.assertEqual(position.unrealized_pnl, Decimal("0"))

    def test_open_position_supports_short_side(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        simulator.open_position(
            symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW, side=PositionSide.SHORT
        )
        position = simulator.get_open_position("BTCUSDT")
        self.assertEqual(position.side, PositionSide.SHORT)

    def test_open_position_is_noop_when_already_open(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        first = simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)
        second = simulator.open_position(symbol="BTCUSDT", price=Decimal("200"), timestamp=NOW)

        self.assertIsNotNone(first)
        self.assertIsNone(second)
        self.assertEqual(len(simulator.trades), 1)
        # Cash was already fully spent by the first open; unaffected by the no-op.
        self.assertEqual(simulator.cash_balance, Decimal("0"))

    def test_open_position_is_noop_with_zero_cash(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="0"))
        trade = simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)
        self.assertIsNone(trade)
        self.assertIsNone(simulator.get_open_position("BTCUSDT"))
        self.assertEqual(simulator.trades, [])

    def test_open_position_is_noop_with_negative_cash(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="-50"))
        trade = simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)
        self.assertIsNone(trade)
        self.assertEqual(simulator.trades, [])

    def test_open_position_allows_multiple_symbols_concurrently(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)
        # All cash was spent on BTCUSDT, so ETHUSDT open is a no-op (zero cash) --
        # confirms symbols are tracked independently even though this call fails.
        trade = simulator.open_position(symbol="ETHUSDT", price=Decimal("50"), timestamp=NOW)
        self.assertIsNone(trade)
        self.assertTrue(simulator.has_open_position("BTCUSDT"))
        self.assertFalse(simulator.has_open_position("ETHUSDT"))

    def test_open_position_rejects_non_decimal_price(self):
        simulator = PortfolioSimulator(make_portfolio())
        with self.assertRaises(BacktestValidationError):
            simulator.open_position(symbol="BTCUSDT", price=100, timestamp=NOW)

    def test_open_position_rejects_zero_price(self):
        simulator = PortfolioSimulator(make_portfolio())
        with self.assertRaises(BacktestValidationError):
            simulator.open_position(symbol="BTCUSDT", price=Decimal("0"), timestamp=NOW)

    def test_open_position_rejects_negative_price(self):
        simulator = PortfolioSimulator(make_portfolio())
        with self.assertRaises(BacktestValidationError):
            simulator.open_position(symbol="BTCUSDT", price=Decimal("-10"), timestamp=NOW)

    def test_open_position_rejects_empty_symbol(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        with self.assertRaises(BacktestValidationError):
            simulator.open_position(symbol="", price=Decimal("100"), timestamp=NOW)

    def test_open_position_rejects_non_datetime_timestamp(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        with self.assertRaises(BacktestValidationError):
            simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp="not-a-date")


# ----------------------------------------------------------------------
# Closing positions
# ----------------------------------------------------------------------
class TestClosePosition(unittest.TestCase):
    def test_close_position_credits_cash_and_records_trade(self):
        position = make_open_position(symbol="BTCUSDT", entry_price="100", quantity="10")
        simulator = PortfolioSimulator(make_portfolio(cash_balance="0", positions=[position]))

        later = NOW + timedelta(hours=1)
        trade = simulator.close_position(symbol="BTCUSDT", price=Decimal("120"), timestamp=later)

        self.assertIsNotNone(trade)
        self.assertEqual(trade.side, OrderSide.SELL)
        self.assertEqual(trade.price, Decimal("120"))
        self.assertEqual(trade.quantity, Decimal("10"))
        self.assertEqual(trade.executed_at, later)
        self.assertEqual(simulator.cash_balance, Decimal("1200"))

    def test_close_position_marks_position_closed_with_realized_pnl(self):
        position = make_open_position(symbol="BTCUSDT", entry_price="100", quantity="10")
        simulator = PortfolioSimulator(make_portfolio(cash_balance="0", positions=[position]))

        later = NOW + timedelta(hours=1)
        simulator.close_position(symbol="BTCUSDT", price=Decimal("120"), timestamp=later)

        closed = simulator.portfolio.positions[0]
        self.assertEqual(closed.status, PositionStatus.CLOSED)
        self.assertEqual(closed.realized_pnl, Decimal("200"))  # (120 - 100) * 10
        self.assertEqual(closed.unrealized_pnl, Decimal("0"))
        self.assertEqual(closed.current_price, Decimal("120"))
        self.assertEqual(closed.closed_at, later)

    def test_close_position_realized_pnl_negative_on_a_loss(self):
        position = make_open_position(symbol="BTCUSDT", entry_price="100", quantity="10")
        simulator = PortfolioSimulator(make_portfolio(cash_balance="0", positions=[position]))
        simulator.close_position(symbol="BTCUSDT", price=Decimal("90"), timestamp=NOW)
        closed = simulator.portfolio.positions[0]
        self.assertEqual(closed.realized_pnl, Decimal("-100"))  # (90 - 100) * 10

    def test_close_position_realized_pnl_for_short_position(self):
        position = make_open_position(
            symbol="BTCUSDT", entry_price="100", quantity="10", side=PositionSide.SHORT
        )
        simulator = PortfolioSimulator(make_portfolio(cash_balance="0", positions=[position]))
        simulator.close_position(symbol="BTCUSDT", price=Decimal("80"), timestamp=NOW)
        closed = simulator.portfolio.positions[0]
        # Short profits when price falls: (entry - exit) * quantity
        self.assertEqual(closed.realized_pnl, Decimal("200"))

    def test_close_position_is_noop_when_none_open(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        trade = simulator.close_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)
        self.assertIsNone(trade)
        self.assertEqual(simulator.trades, [])
        self.assertEqual(simulator.cash_balance, Decimal("1000"))

    def test_close_position_rejects_non_decimal_price(self):
        position = make_open_position(symbol="BTCUSDT")
        simulator = PortfolioSimulator(make_portfolio(cash_balance="0", positions=[position]))
        with self.assertRaises(BacktestValidationError):
            simulator.close_position(symbol="BTCUSDT", price="120", timestamp=NOW)

    def test_close_position_rejects_zero_or_negative_price(self):
        position = make_open_position(symbol="BTCUSDT")
        simulator = PortfolioSimulator(make_portfolio(cash_balance="0", positions=[position]))
        with self.assertRaises(BacktestValidationError):
            simulator.close_position(symbol="BTCUSDT", price=Decimal("0"), timestamp=NOW)

    def test_close_position_rejects_non_datetime_timestamp(self):
        position = make_open_position(symbol="BTCUSDT")
        simulator = PortfolioSimulator(make_portfolio(cash_balance="0", positions=[position]))
        with self.assertRaises(BacktestValidationError):
            simulator.close_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=12345)


# ----------------------------------------------------------------------
# Full round trip
# ----------------------------------------------------------------------
class TestRoundTrip(unittest.TestCase):
    def test_open_then_close_round_trip(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        open_time = NOW
        close_time = NOW + timedelta(hours=2)

        buy_trade = simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=open_time)
        sell_trade = simulator.close_position(symbol="BTCUSDT", price=Decimal("150"), timestamp=close_time)

        self.assertEqual(buy_trade.side, OrderSide.BUY)
        self.assertEqual(sell_trade.side, OrderSide.SELL)
        self.assertEqual(len(simulator.trades), 2)
        self.assertEqual(simulator.cash_balance, Decimal("1500"))
        self.assertIsNone(simulator.get_open_position("BTCUSDT"))
        closed = simulator.portfolio.positions[0]
        self.assertEqual(closed.realized_pnl, Decimal("500"))

    def test_multiple_alternating_round_trips_are_recorded_in_order(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)
        simulator.close_position(
            symbol="BTCUSDT", price=Decimal("110"), timestamp=NOW + timedelta(hours=1)
        )
        simulator.open_position(
            symbol="BTCUSDT", price=Decimal("110"), timestamp=NOW + timedelta(hours=2)
        )
        simulator.close_position(
            symbol="BTCUSDT", price=Decimal("121"), timestamp=NOW + timedelta(hours=3)
        )

        sides = [t.side for t in simulator.trades]
        self.assertEqual(sides, [OrderSide.BUY, OrderSide.SELL, OrderSide.BUY, OrderSide.SELL])
        timestamps = [t.executed_at for t in simulator.trades]
        self.assertEqual(timestamps, sorted(timestamps))
        # Both closed positions should be present, none left open.
        self.assertEqual(len(simulator.portfolio.positions), 2)
        self.assertEqual(simulator.get_open_positions(), [])

    def test_position_left_open_at_end_has_no_realized_pnl(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)
        position = simulator.get_open_position("BTCUSDT")
        self.assertIsNone(position.realized_pnl)
        self.assertEqual(position.status, PositionStatus.OPEN)


# ----------------------------------------------------------------------
# Marking to market / total equity
# ----------------------------------------------------------------------
class TestMarkToMarket(unittest.TestCase):
    def test_update_market_price_updates_current_price_and_unrealized_pnl(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)

        simulator.update_market_price(symbol="BTCUSDT", price=Decimal("120"))

        position = simulator.get_open_position("BTCUSDT")
        self.assertEqual(position.current_price, Decimal("120"))
        self.assertEqual(position.unrealized_pnl, Decimal("200"))  # (120 - 100) * 10

    def test_update_market_price_unrealized_pnl_negative_on_paper_loss(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)
        simulator.update_market_price(symbol="BTCUSDT", price=Decimal("90"))
        position = simulator.get_open_position("BTCUSDT")
        self.assertEqual(position.unrealized_pnl, Decimal("-100"))

    def test_update_market_price_is_noop_when_no_open_position(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        # Should not raise, simply do nothing.
        result = simulator.update_market_price(symbol="BTCUSDT", price=Decimal("100"))
        self.assertIsNone(result)

    def test_update_market_price_rejects_invalid_price(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)
        with self.assertRaises(BacktestValidationError):
            simulator.update_market_price(symbol="BTCUSDT", price=Decimal("-1"))

    def test_total_equity_with_no_positions_equals_cash(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        self.assertEqual(simulator.total_equity(), Decimal("1000"))

    def test_total_equity_includes_open_position_market_value(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)
        # All cash spent (1000 / 100 = 10 units); mark price still 100.
        self.assertEqual(simulator.total_equity(), Decimal("1000"))

        simulator.update_market_price(symbol="BTCUSDT", price=Decimal("150"))
        self.assertEqual(simulator.total_equity(), Decimal("1500"))

    def test_total_equity_reflects_realized_gains_after_close(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)
        simulator.close_position(symbol="BTCUSDT", price=Decimal("120"), timestamp=NOW)
        self.assertEqual(simulator.total_equity(), Decimal("1200"))

    def test_open_close_and_update_refresh_portfolio_total_equity_field(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)
        self.assertEqual(simulator.portfolio.total_equity, Decimal("1000"))

        simulator.update_market_price(symbol="BTCUSDT", price=Decimal("200"))
        self.assertEqual(simulator.portfolio.total_equity, Decimal("2000"))

        simulator.close_position(symbol="BTCUSDT", price=Decimal("200"), timestamp=NOW)
        self.assertEqual(simulator.portfolio.total_equity, Decimal("2000"))


# ----------------------------------------------------------------------
# Candle-based convenience wrappers
# ----------------------------------------------------------------------
class TestCandleConvenienceMethods(unittest.TestCase):
    def test_open_position_from_candle_uses_close_and_close_time(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        candle = make_candle(open_time=NOW, close="100")

        trade = simulator.open_position_from_candle(symbol="BTCUSDT", candle=candle)

        self.assertEqual(trade.price, candle.close)
        self.assertEqual(trade.executed_at, candle.close_time)

    def test_close_position_from_candle_uses_close_and_close_time(self):
        position = make_open_position(symbol="BTCUSDT", entry_price="100", quantity="10")
        simulator = PortfolioSimulator(make_portfolio(cash_balance="0", positions=[position]))
        candle = make_candle(open_time=NOW, close="130")

        trade = simulator.close_position_from_candle(symbol="BTCUSDT", candle=candle)

        self.assertEqual(trade.price, candle.close)
        self.assertEqual(trade.executed_at, candle.close_time)

    def test_update_market_price_from_candle_uses_close(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)
        candle = make_candle(open_time=NOW, close="140")

        simulator.update_market_price_from_candle(symbol="BTCUSDT", candle=candle)

        position = simulator.get_open_position("BTCUSDT")
        self.assertEqual(position.current_price, candle.close)

    def test_candle_wrappers_do_not_mutate_the_candle(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        candle = make_candle(open_time=NOW, close="100")
        original = copy.deepcopy(candle)

        simulator.open_position_from_candle(symbol="BTCUSDT", candle=candle)
        simulator.update_market_price_from_candle(symbol="BTCUSDT", candle=candle)
        simulator.close_position_from_candle(symbol="BTCUSDT", candle=candle)

        self.assertEqual(candle, original)

    def test_open_position_from_candle_rejects_non_candle(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        with self.assertRaises(BacktestValidationError):
            simulator.open_position_from_candle(symbol="BTCUSDT", candle="not-a-candle")


# ----------------------------------------------------------------------
# Determinism / no mutation of inputs
# ----------------------------------------------------------------------
class TestDeterminismAndNoMutation(unittest.TestCase):
    def test_repeated_identical_operations_produce_identical_state(self):
        def run() -> PortfolioSimulator:
            sim = PortfolioSimulator(make_portfolio(cash_balance="1000"))
            sim.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)
            sim.update_market_price(symbol="BTCUSDT", price=Decimal("110"))
            sim.close_position(
                symbol="BTCUSDT", price=Decimal("120"), timestamp=NOW + timedelta(hours=1)
            )
            return sim

        first = run()
        second = run()

        self.assertEqual(first.cash_balance, second.cash_balance)
        self.assertEqual(first.total_equity(), second.total_equity())
        self.assertEqual(
            [(t.side, t.price, t.quantity, t.executed_at) for t in first.trades],
            [(t.side, t.price, t.quantity, t.executed_at) for t in second.trades],
        )

    def test_trades_property_returns_a_copy_not_the_internal_list(self):
        simulator = PortfolioSimulator(make_portfolio(cash_balance="1000"))
        simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)

        trades = simulator.trades
        trades.append("tampered")

        self.assertEqual(len(simulator.trades), 1)

    def test_portfolio_positions_is_the_simulators_own_list_not_callers(self):
        original_positions: list[Position] = []
        portfolio = make_portfolio(cash_balance="1000", positions=original_positions)
        simulator = PortfolioSimulator(portfolio)

        simulator.open_position(symbol="BTCUSDT", price=Decimal("100"), timestamp=NOW)

        self.assertEqual(original_positions, [])
        self.assertEqual(len(simulator.portfolio.positions), 1)


if __name__ == "__main__":
    unittest.main()
