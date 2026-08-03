"""
test_basic_backtester.py
----------------------------
Purpose:
    Unit tests for `BasicBacktester` (Backtesting Engine Part 2), the
    first concrete `BaseBacktester` implementation.

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
from core.entities.trade import Trade
from core.enums import OrderSide, PositionSide, PositionStatus, SignalDirection

from strategies.base_strategy import BaseStrategy
from strategies.basic_strategy import BasicStrategy
from strategies.context import StrategyContext
from strategies.exceptions import InsufficientStrategyDataError
from strategies.result import StrategyResult

from backtesting import (
    BacktestContext,
    BacktestResult,
    BaseBacktester,
    BasicBacktester,
    InvalidBacktestContextError,
)

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------
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


def make_candles(closes: list, *, symbol: str = "BTCUSDT") -> list[Candle]:
    return [
        make_candle(open_time=NOW + timedelta(hours=i), close=close, symbol=symbol)
        for i, close in enumerate(closes)
    ]


def make_portfolio(*, cash_balance="10000", positions: list | None = None) -> Portfolio:
    return Portfolio(
        portfolio_id="portfolio-1",
        base_currency="USDT",
        cash_balance=Decimal(str(cash_balance)),
        positions=positions or [],
    )


def make_backtester() -> BasicBacktester:
    return BasicBacktester(name="BasicBacktester")


# ----------------------------------------------------------------------
# Fake strategies
# ----------------------------------------------------------------------
class ConstantStrategy(BaseStrategy):
    """Always returns the same fixed `action`, regardless of context."""

    def __init__(self, action: SignalDirection, *, confidence: float = 1.0, name=None):
        super().__init__(name=name)
        self._action = action
        self._confidence = confidence
        self.calls: list[StrategyContext] = []

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        self.calls.append(context)
        return self._build_result(
            action=self._action, confidence=self._confidence, summary="constant decision"
        )


class AlternatingStrategy(BaseStrategy):
    """BUY on even candle index, SELL on odd candle index."""

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        index = context.metadata["candle_index"]
        action = SignalDirection.BUY if index % 2 == 0 else SignalDirection.SELL
        return self._build_result(action=action, confidence=1.0, summary="alternating")


class PriceThresholdStrategy(BaseStrategy):
    """BUY when the current candle's close is below `threshold`, SELL when above."""

    def __init__(self, threshold, *, name=None):
        super().__init__(name=name)
        self.threshold = Decimal(str(threshold))

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        candle: Candle = context.metadata["candle"]
        if candle.close < self.threshold:
            action = SignalDirection.BUY
        elif candle.close > self.threshold:
            action = SignalDirection.SELL
        else:
            action = SignalDirection.HOLD
        return self._build_result(action=action, confidence=1.0, summary="threshold decision")


class AlwaysInsufficientStrategy(BaseStrategy):
    """Always raises `InsufficientStrategyDataError`."""

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        raise InsufficientStrategyDataError("no data available")


class InsufficientOnFirstNStrategy(BaseStrategy):
    """Raises `InsufficientStrategyDataError` for the first `n` candles, then BUYs."""

    def __init__(self, n: int, *, name=None):
        super().__init__(name=name)
        self.n = n

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        index = context.metadata["candle_index"]
        if index < self.n:
            raise InsufficientStrategyDataError("warming up")
        return self._build_result(
            action=SignalDirection.BUY, confidence=1.0, summary="ready"
        )


class BrokenStrategy(BaseStrategy):
    """Raises a plain, non-`StrategyError` exception -- a genuine bug."""

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        raise ValueError("boom")


class RecordingHoldStrategy(BaseStrategy):
    """Always HOLDs, but records every candle it was asked to decide on."""

    def __init__(self, *, name=None):
        super().__init__(name=name)
        self.seen_candles: list[Candle] = []

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        self.seen_candles.append(context.metadata["candle"])
        return self._build_result(action=SignalDirection.HOLD, confidence=1.0, summary="hold")


# ----------------------------------------------------------------------
# Construction / inheritance
# ----------------------------------------------------------------------
class TestBasicBacktesterConstruction(unittest.TestCase):
    def test_is_a_base_backtester(self):
        self.assertIsInstance(make_backtester(), BaseBacktester)

    def test_default_name_is_class_name(self):
        self.assertEqual(BasicBacktester().name, "BasicBacktester")

    def test_custom_name_is_honored(self):
        self.assertEqual(BasicBacktester(name="MyBacktester").name, "MyBacktester")

    def test_repr_contains_name(self):
        self.assertIn("MyBacktester", repr(BasicBacktester(name="MyBacktester")))


# ----------------------------------------------------------------------
# Context validation (inherited from BaseBacktester)
# ----------------------------------------------------------------------
class TestContextValidation(unittest.TestCase):
    def test_rejects_non_backtest_context(self):
        with self.assertRaises(InvalidBacktestContextError):
            make_backtester().run("not-a-context")  # type: ignore[arg-type]

    def test_rejects_none(self):
        with self.assertRaises(InvalidBacktestContextError):
            make_backtester().run(None)  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# HOLD-only: no trades, no portfolio change
# ----------------------------------------------------------------------
class TestHoldOnly(unittest.TestCase):
    def setUp(self):
        self.candles = make_candles(["100", "105", "110"])
        self.portfolio = make_portfolio(cash_balance="10000")
        self.context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=self.candles,
            strategy=ConstantStrategy(SignalDirection.HOLD),
            initial_portfolio=self.portfolio,
        )

    def test_returns_backtest_result(self):
        result = make_backtester().run(self.context)
        self.assertIsInstance(result, BacktestResult)

    def test_no_trades_recorded(self):
        result = make_backtester().run(self.context)
        self.assertEqual(result.trades, [])

    def test_cash_balance_unchanged(self):
        result = make_backtester().run(self.context)
        self.assertEqual(result.final_portfolio.cash_balance, Decimal("10000"))

    def test_no_positions_created(self):
        result = make_backtester().run(self.context)
        self.assertEqual(result.final_portfolio.positions, [])

    def test_final_portfolio_is_not_the_same_object(self):
        result = make_backtester().run(self.context)
        self.assertIsNot(result.final_portfolio, self.portfolio)

    def test_metadata_records_zero_trades(self):
        result = make_backtester().run(self.context)
        self.assertEqual(result.metadata["trades_executed"], 0)
        self.assertEqual(result.metadata["skipped_candles"], 0)
        self.assertEqual(result.metadata["candles_replayed"], 3)


# ----------------------------------------------------------------------
# BUY-only: exactly one position opened, no pyramiding
# ----------------------------------------------------------------------
class TestBuyOnly(unittest.TestCase):
    def setUp(self):
        self.candles = make_candles(["100", "105", "110"])
        self.portfolio = make_portfolio(cash_balance="1000")
        self.context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=self.candles,
            strategy=ConstantStrategy(SignalDirection.BUY),
            initial_portfolio=self.portfolio,
        )

    def test_exactly_one_trade_recorded(self):
        result = make_backtester().run(self.context)
        self.assertEqual(len(result.trades), 1)

    def test_trade_is_a_buy(self):
        result = make_backtester().run(self.context)
        self.assertEqual(result.trades[0].side, OrderSide.BUY)

    def test_trade_uses_first_candle_close_price(self):
        result = make_backtester().run(self.context)
        self.assertEqual(result.trades[0].price, Decimal("100"))

    def test_cash_balance_fully_spent(self):
        result = make_backtester().run(self.context)
        self.assertEqual(result.final_portfolio.cash_balance, Decimal("0"))

    def test_exactly_one_open_position(self):
        result = make_backtester().run(self.context)
        open_positions = [
            p for p in result.final_portfolio.positions if p.status == PositionStatus.OPEN
        ]
        self.assertEqual(len(open_positions), 1)

    def test_position_quantity_matches_cash_over_price(self):
        result = make_backtester().run(self.context)
        position = result.final_portfolio.positions[0]
        self.assertEqual(position.quantity, Decimal("1000") / Decimal("100"))

    def test_position_side_is_long(self):
        result = make_backtester().run(self.context)
        self.assertEqual(result.final_portfolio.positions[0].side, PositionSide.LONG)

    def test_no_pyramiding_on_repeated_buy_signals(self):
        # 3 candles, strategy always says BUY -- only the first should open.
        result = make_backtester().run(self.context)
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(len(result.final_portfolio.positions), 1)


class TestBuyWithNoCash(unittest.TestCase):
    def test_buy_with_zero_cash_is_a_no_op(self):
        candles = make_candles(["100"])
        portfolio = make_portfolio(cash_balance="0")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=ConstantStrategy(SignalDirection.BUY),
            initial_portfolio=portfolio,
        )
        result = make_backtester().run(context)
        self.assertEqual(result.trades, [])
        self.assertEqual(result.final_portfolio.positions, [])

    def test_buy_with_negative_cash_is_a_no_op(self):
        candles = make_candles(["100"])
        portfolio = make_portfolio(cash_balance="-50")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=ConstantStrategy(SignalDirection.BUY),
            initial_portfolio=portfolio,
        )
        result = make_backtester().run(context)
        self.assertEqual(result.trades, [])


# ----------------------------------------------------------------------
# SELL-only: no open position, always a no-op
# ----------------------------------------------------------------------
class TestSellWithNoPosition(unittest.TestCase):
    def test_sell_with_no_open_position_is_a_no_op(self):
        candles = make_candles(["100", "105"])
        portfolio = make_portfolio(cash_balance="1000")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=ConstantStrategy(SignalDirection.SELL),
            initial_portfolio=portfolio,
        )
        result = make_backtester().run(context)
        self.assertEqual(result.trades, [])
        self.assertEqual(result.final_portfolio.cash_balance, Decimal("1000"))


# ----------------------------------------------------------------------
# BUY then SELL: full round trip
# ----------------------------------------------------------------------
class TestBuyThenSell(unittest.TestCase):
    def setUp(self):
        # index 0: price 100 -> BUY; index 1: price 120 -> SELL
        self.candles = make_candles(["100", "120"])
        self.portfolio = make_portfolio(cash_balance="1000")
        self.context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=self.candles,
            strategy=PriceThresholdStrategy(threshold="110"),
            initial_portfolio=self.portfolio,
        )

    def test_two_trades_recorded(self):
        result = make_backtester().run(self.context)
        self.assertEqual(len(result.trades), 2)

    def test_trade_sides_are_buy_then_sell(self):
        result = make_backtester().run(self.context)
        self.assertEqual(result.trades[0].side, OrderSide.BUY)
        self.assertEqual(result.trades[1].side, OrderSide.SELL)

    def test_trade_order_matches_chronological_candle_order(self):
        result = make_backtester().run(self.context)
        self.assertLess(result.trades[0].executed_at, result.trades[1].executed_at)

    def test_position_closed_after_sell(self):
        result = make_backtester().run(self.context)
        position = result.final_portfolio.positions[0]
        self.assertEqual(position.status, PositionStatus.CLOSED)

    def test_cash_reflects_profit(self):
        result = make_backtester().run(self.context)
        # bought 10 units at 100 (spending all 1000), sold 10 units at 120 -> 1200
        self.assertEqual(result.final_portfolio.cash_balance, Decimal("1200"))

    def test_realized_pnl_recorded_on_position(self):
        result = make_backtester().run(self.context)
        position = result.final_portfolio.positions[0]
        self.assertEqual(position.realized_pnl, Decimal("200"))

    def test_no_open_positions_remain(self):
        result = make_backtester().run(self.context)
        open_positions = [
            p for p in result.final_portfolio.positions if p.status == PositionStatus.OPEN
        ]
        self.assertEqual(open_positions, [])


class TestPositionLeftOpenAtEnd(unittest.TestCase):
    def test_buy_never_sold_stays_open(self):
        candles = make_candles(["100", "105"])
        portfolio = make_portfolio(cash_balance="1000")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=ConstantStrategy(SignalDirection.BUY),
            initial_portfolio=portfolio,
        )
        result = make_backtester().run(context)
        self.assertEqual(len(result.final_portfolio.positions), 1)
        self.assertEqual(result.final_portfolio.positions[0].status, PositionStatus.OPEN)
        self.assertEqual(result.metadata["open_positions_remaining"], 1)


# ----------------------------------------------------------------------
# Alternating BUY/SELL across many candles (multiple round trips)
# ----------------------------------------------------------------------
class TestMultipleRoundTrips(unittest.TestCase):
    def test_alternating_strategy_executes_a_trade_per_candle(self):
        candles = make_candles(["100", "110", "90", "120"])
        portfolio = make_portfolio(cash_balance="1000")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=AlternatingStrategy(),
            initial_portfolio=portfolio,
        )
        result = make_backtester().run(context)
        self.assertEqual(len(result.trades), 4)
        sides = [t.side for t in result.trades]
        self.assertEqual(sides, [OrderSide.BUY, OrderSide.SELL, OrderSide.BUY, OrderSide.SELL])
        self.assertEqual(len(result.final_portfolio.positions), 2)
        for position in result.final_portfolio.positions:
            self.assertEqual(position.status, PositionStatus.CLOSED)

    def test_trades_are_strictly_chronological(self):
        candles = make_candles(["100", "110", "90", "120"])
        portfolio = make_portfolio(cash_balance="1000")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=AlternatingStrategy(),
            initial_portfolio=portfolio,
        )
        result = make_backtester().run(context)
        timestamps = [t.executed_at for t in result.trades]
        self.assertEqual(timestamps, sorted(timestamps))


# ----------------------------------------------------------------------
# InsufficientStrategyDataError handling
# ----------------------------------------------------------------------
class TestInsufficientStrategyData(unittest.TestCase):
    def test_all_candles_skipped_when_strategy_always_raises(self):
        candles = make_candles(["100", "105", "110"])
        portfolio = make_portfolio(cash_balance="1000")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=AlwaysInsufficientStrategy(),
            initial_portfolio=portfolio,
        )
        result = make_backtester().run(context)
        self.assertEqual(result.trades, [])
        self.assertEqual(result.metadata["skipped_candles"], 3)
        self.assertEqual(result.final_portfolio.cash_balance, Decimal("1000"))

    def test_run_does_not_raise_when_strategy_raises_insufficient_data(self):
        candles = make_candles(["100"])
        portfolio = make_portfolio(cash_balance="1000")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=AlwaysInsufficientStrategy(),
            initial_portfolio=portfolio,
        )
        try:
            make_backtester().run(context)
        except InsufficientStrategyDataError:
            self.fail("InsufficientStrategyDataError should be caught per-candle, not propagate")

    def test_partial_warmup_then_recovers(self):
        candles = make_candles(["100", "105", "110", "115"])
        portfolio = make_portfolio(cash_balance="1000")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=InsufficientOnFirstNStrategy(n=2),
            initial_portfolio=portfolio,
        )
        result = make_backtester().run(context)
        self.assertEqual(result.metadata["skipped_candles"], 2)
        # BUY fires starting candle index 2 (price 110); repeated BUY after
        # is a no-op since a position is already open.
        self.assertEqual(len(result.trades), 1)
        self.assertEqual(result.trades[0].price, Decimal("110"))

    def test_summary_mentions_skipped_candles_when_any(self):
        candles = make_candles(["100"])
        portfolio = make_portfolio(cash_balance="1000")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=AlwaysInsufficientStrategy(),
            initial_portfolio=portfolio,
        )
        result = make_backtester().run(context)
        self.assertIn("skipped", result.summary.lower())


class TestOtherExceptionsPropagate(unittest.TestCase):
    def test_non_strategy_error_propagates(self):
        candles = make_candles(["100"])
        portfolio = make_portfolio(cash_balance="1000")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=BrokenStrategy(),
            initial_portfolio=portfolio,
        )
        with self.assertRaises(ValueError):
            make_backtester().run(context)


# ----------------------------------------------------------------------
# Never mutates inputs
# ----------------------------------------------------------------------
class TestNoMutationOfInputs(unittest.TestCase):
    def test_initial_portfolio_left_untouched(self):
        candles = make_candles(["100", "110"])
        portfolio = make_portfolio(cash_balance="1000")
        portfolio_snapshot = copy.deepcopy(portfolio)
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=ConstantStrategy(SignalDirection.BUY),
            initial_portfolio=portfolio,
        )
        make_backtester().run(context)
        self.assertEqual(portfolio.cash_balance, portfolio_snapshot.cash_balance)
        self.assertEqual(portfolio.positions, portfolio_snapshot.positions)

    def test_candles_list_left_untouched(self):
        candles = make_candles(["100", "110", "120"])
        candles_snapshot = list(candles)
        portfolio = make_portfolio(cash_balance="1000")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=AlternatingStrategy(),
            initial_portfolio=portfolio,
        )
        make_backtester().run(context)
        self.assertEqual(context.candles, candles_snapshot)

    def test_context_object_itself_still_usable_after_run(self):
        candles = make_candles(["100", "110"])
        portfolio = make_portfolio(cash_balance="1000")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=ConstantStrategy(SignalDirection.HOLD),
            initial_portfolio=portfolio,
        )
        backtester = make_backtester()
        first = backtester.run(context)
        second = backtester.run(context)
        self.assertEqual(first.trades, second.trades)
        self.assertEqual(first.final_portfolio.cash_balance, second.final_portfolio.cash_balance)


# ----------------------------------------------------------------------
# Determinism
# ----------------------------------------------------------------------
class TestDeterminism(unittest.TestCase):
    def test_repeated_runs_produce_identical_trades(self):
        candles = make_candles(["100", "110", "90", "120"])
        portfolio = make_portfolio(cash_balance="1000")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=AlternatingStrategy(),
            initial_portfolio=portfolio,
        )
        backtester = make_backtester()
        result_a = backtester.run(context)
        result_b = backtester.run(context)
        self.assertEqual(result_a.trades, result_b.trades)
        self.assertEqual(
            result_a.final_portfolio.cash_balance, result_b.final_portfolio.cash_balance
        )
        self.assertEqual(len(result_a.final_portfolio.positions), len(result_b.final_portfolio.positions))


# ----------------------------------------------------------------------
# Chronological execution / StrategyContext wiring
# ----------------------------------------------------------------------
class TestChronologicalExecutionAndContextWiring(unittest.TestCase):
    def test_strategy_sees_candles_in_chronological_order(self):
        candles = make_candles(["100", "105", "110", "115"])
        portfolio = make_portfolio(cash_balance="1000")
        strategy = RecordingHoldStrategy()
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=strategy,
            initial_portfolio=portfolio,
        )
        make_backtester().run(context)
        self.assertEqual(strategy.seen_candles, candles)

    def test_strategy_context_carries_symbol_and_timeframe(self):
        candles = make_candles(["100"])
        portfolio = make_portfolio(cash_balance="1000")
        strategy = ConstantStrategy(SignalDirection.HOLD)
        context = BacktestContext(
            symbol="ETHUSDT",
            timeframe="4h",
            candles=candles,
            strategy=strategy,
            initial_portfolio=portfolio,
        )
        make_backtester().run(context)
        seen = strategy.calls[0]
        self.assertEqual(seen.symbol, "ETHUSDT")
        self.assertEqual(seen.timeframe, "4h")

    def test_strategy_context_has_no_analysis_signal_or_risk_result(self):
        candles = make_candles(["100"])
        portfolio = make_portfolio(cash_balance="1000")
        strategy = ConstantStrategy(SignalDirection.HOLD)
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=strategy,
            initial_portfolio=portfolio,
        )
        make_backtester().run(context)
        seen = strategy.calls[0]
        self.assertEqual(seen.analysis_results, [])
        self.assertIsNone(seen.signal_result)
        self.assertIsNone(seen.risk_result)

    def test_strategy_context_metadata_carries_current_candle_and_index(self):
        candles = make_candles(["100", "105"])
        portfolio = make_portfolio(cash_balance="1000")
        strategy = ConstantStrategy(SignalDirection.HOLD)
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=strategy,
            initial_portfolio=portfolio,
        )
        make_backtester().run(context)
        self.assertEqual(strategy.calls[0].metadata["candle_index"], 0)
        self.assertEqual(strategy.calls[1].metadata["candle_index"], 1)
        self.assertEqual(strategy.calls[0].metadata["candle"], candles[0])
        self.assertEqual(strategy.calls[1].metadata["candle"], candles[1])


# ----------------------------------------------------------------------
# Output shape / metadata / summary / scope-boundary checks
# ----------------------------------------------------------------------
class TestOutputShape(unittest.TestCase):
    def setUp(self):
        self.candles = make_candles(["100", "110"])
        self.portfolio = make_portfolio(cash_balance="1000")
        self.context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=self.candles,
            strategy=PriceThresholdStrategy(threshold="105"),
            initial_portfolio=self.portfolio,
        )

    def test_result_has_only_backtest_result_fields(self):
        result = make_backtester().run(self.context)
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        self.assertEqual(field_names, {"final_portfolio", "summary", "trades", "metadata"})

    def test_trades_are_trade_instances(self):
        result = make_backtester().run(self.context)
        for trade in result.trades:
            self.assertIsInstance(trade, Trade)

    def test_summary_is_non_empty_string(self):
        result = make_backtester().run(self.context)
        self.assertIsInstance(result.summary, str)
        self.assertTrue(result.summary.strip())

    def test_summary_mentions_symbol_and_strategy_name(self):
        result = make_backtester().run(self.context)
        self.assertIn("BTCUSDT", result.summary)
        self.assertIn(self.context.strategy.name, result.summary)

    def test_metadata_contains_expected_keys(self):
        result = make_backtester().run(self.context)
        for key in (
            "backtester",
            "strategy_name",
            "symbol",
            "timeframe",
            "candles_replayed",
            "skipped_candles",
            "trades_executed",
            "open_positions_remaining",
        ):
            self.assertIn(key, result.metadata)

    def test_no_order_execution_or_ai_fields_anywhere(self):
        result = make_backtester().run(self.context)
        forbidden = {"order_id", "broker", "ai_model", "sharpe_ratio", "max_drawdown"}
        self.assertTrue(forbidden.isdisjoint(result.metadata.keys()))

    def test_context_supplied_metadata_is_preserved(self):
        candles = make_candles(["100"])
        portfolio = make_portfolio(cash_balance="1000")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=ConstantStrategy(SignalDirection.HOLD),
            initial_portfolio=portfolio,
            metadata={"run_id": "abc-123"},
        )
        result = make_backtester().run(context)
        self.assertEqual(result.metadata["run_id"], "abc-123")


# ----------------------------------------------------------------------
# Real-BaseStrategy integration (proves genuine reuse of the Strategy
# Engine's contract, not just a hand-built fake).
# ----------------------------------------------------------------------
class TestRealBasicStrategyIntegration(unittest.TestCase):
    def test_real_basic_strategy_has_no_matching_analysis_result_so_every_candle_is_skipped(self):
        # BasicBacktester never supplies an AnalysisResult on the
        # per-candle StrategyContext, so a real BasicStrategy (which
        # requires one matching its default analyzer_name) raises
        # InsufficientStrategyDataError for every candle -- proving
        # BasicBacktester genuinely calls through to BaseStrategy.decide()
        # rather than special-casing any particular strategy type.
        candles = make_candles(["100", "105", "110"])
        portfolio = make_portfolio(cash_balance="1000")
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=candles,
            strategy=BasicStrategy(),
            initial_portfolio=portfolio,
        )
        result = make_backtester().run(context)
        self.assertEqual(result.trades, [])
        self.assertEqual(result.metadata["skipped_candles"], 3)
        self.assertEqual(result.final_portfolio.cash_balance, Decimal("1000"))

    def test_real_basic_strategy_is_a_base_strategy_instance(self):
        self.assertIsInstance(BasicStrategy(), BaseStrategy)


# ----------------------------------------------------------------------
# Empty-candles defensive check
# ----------------------------------------------------------------------
class TestEmptyCandlesDefensiveCheck(unittest.TestCase):
    def test_backtest_context_itself_already_rejects_empty_candles(self):
        # BacktestContext's own validation guarantees non-empty candles,
        # so BasicBacktester's own defensive check is unreachable through
        # normal construction -- confirmed here for completeness.
        portfolio = make_portfolio(cash_balance="1000")
        with self.assertRaises(Exception):
            BacktestContext(
                symbol="BTCUSDT",
                timeframe="1h",
                candles=[],
                strategy=ConstantStrategy(SignalDirection.HOLD),
                initial_portfolio=portfolio,
            )


if __name__ == "__main__":
    unittest.main()
