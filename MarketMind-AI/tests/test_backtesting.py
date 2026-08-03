"""
test_backtesting.py
----------------------
Purpose:
    Unit tests for the Backtesting Engine foundation (Part 1):
    `BacktestResult`, `BacktestContext`, `BaseBacktester`, and the
    `backtesting.exceptions` / `.utils` helpers.

Uses the standard-library ``unittest`` framework, matching the
`analysis`/`signals`/`strategies`/`strategies.risk_management` test
suites (no external test-runner dependency).

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from core.entities.candle import Candle
from core.entities.portfolio import Portfolio
from core.entities.trade import Trade
from core.enums import OrderSide, SignalDirection

from strategies.base_strategy import BaseStrategy
from strategies.context import StrategyContext
from strategies.result import StrategyResult

from backtesting import (
    BacktestContext,
    BacktestError,
    BacktesterConfigurationError,
    BacktestResult,
    BacktestValidationError,
    BaseBacktester,
    InsufficientBacktestDataError,
    InvalidBacktestContextError,
)
from backtesting.utils import (
    merge_metadata,
    validate_chronological_candles,
    validate_instance_list,
    validate_non_empty_str,
)

NOW = datetime.now(timezone.utc)


def make_candle(*, open_time: datetime, close: Decimal = Decimal("105")) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        timeframe="1h",
        open_time=open_time,
        close_time=open_time + timedelta(hours=1),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("95"),
        close=close,
        volume=Decimal("1000"),
    )


def make_candles(count: int = 3) -> list[Candle]:
    return [make_candle(open_time=NOW + timedelta(hours=i)) for i in range(count)]


def make_portfolio(*, cash_balance: Decimal = Decimal("10000")) -> Portfolio:
    return Portfolio(
        portfolio_id="portfolio-1",
        base_currency="USDT",
        cash_balance=cash_balance,
    )


class FakeStrategy(BaseStrategy):
    """Minimal concrete `BaseStrategy` used only to satisfy `BacktestContext.strategy`."""

    def decide(self, context: StrategyContext) -> StrategyResult:
        self.validate_context(context)
        return self._build_result(
            action=SignalDirection.HOLD, confidence=0.5, summary="No-op fake decision"
        )


def make_strategy() -> BaseStrategy:
    return FakeStrategy(name="FakeStrategy")


# ----------------------------------------------------------------------
# BacktestResult
# ----------------------------------------------------------------------
class TestBacktestResult(unittest.TestCase):
    def test_instantiates_with_required_fields(self):
        result = BacktestResult(final_portfolio=make_portfolio(), summary="Backtest completed")
        self.assertIsInstance(result.final_portfolio, Portfolio)
        self.assertEqual(result.summary, "Backtest completed")
        self.assertEqual(result.trades, [])
        self.assertEqual(result.metadata, {})

    def test_only_has_the_four_documented_fields(self):
        result = BacktestResult(final_portfolio=make_portfolio(), summary="Done")
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        self.assertEqual(field_names, {"final_portfolio", "summary", "trades", "metadata"})

    def test_is_frozen(self):
        result = BacktestResult(final_portfolio=make_portfolio(), summary="Done")
        with self.assertRaises(Exception):
            result.summary = "Changed"  # type: ignore[misc]

    def test_rejects_non_portfolio_final_portfolio(self):
        with self.assertRaises(TypeError):
            BacktestResult(final_portfolio="not-a-portfolio", summary="Done")  # type: ignore[arg-type]

    def test_rejects_blank_summary(self):
        with self.assertRaises(BacktestValidationError):
            BacktestResult(final_portfolio=make_portfolio(), summary="   ")

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(TypeError):
            BacktestResult(
                final_portfolio=make_portfolio(),
                summary="Done",
                metadata="not-a-dict",  # type: ignore[arg-type]
            )

    def test_rejects_non_trade_items_in_trades(self):
        with self.assertRaises(BacktestValidationError):
            BacktestResult(
                final_portfolio=make_portfolio(),
                summary="Done",
                trades=["not-a-trade"],  # type: ignore[list-item]
            )

    def test_accepts_valid_trades(self):
        trade = Trade(
            trade_id="t1",
            symbol="BTCUSDT",
            side=OrderSide.BUY,
            price=Decimal("100"),
            quantity=Decimal("1"),
            executed_at=NOW,
        )
        result = BacktestResult(final_portfolio=make_portfolio(), summary="Done", trades=[trade])
        self.assertEqual(result.trade_count(), 1)

    def test_with_metadata_returns_new_instance(self):
        original = BacktestResult(
            final_portfolio=make_portfolio(), summary="Done", metadata={"a": 1}
        )
        updated = original.with_metadata(b=2)
        self.assertIsNot(updated, original)
        self.assertEqual(original.metadata, {"a": 1})
        self.assertEqual(updated.metadata, {"a": 1, "b": 2})

    def test_with_metadata_overrides_on_conflict(self):
        original = BacktestResult(
            final_portfolio=make_portfolio(), summary="Done", metadata={"a": 1}
        )
        updated = original.with_metadata(a=99)
        self.assertEqual(updated.metadata, {"a": 99})

    def test_trade_count_defaults_to_zero(self):
        result = BacktestResult(final_portfolio=make_portfolio(), summary="Done")
        self.assertEqual(result.trade_count(), 0)


# ----------------------------------------------------------------------
# BacktestContext
# ----------------------------------------------------------------------
class TestBacktestContext(unittest.TestCase):
    def test_instantiates_with_required_fields(self):
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=make_candles(),
            strategy=make_strategy(),
            initial_portfolio=make_portfolio(),
        )
        self.assertEqual(context.symbol, "BTCUSDT")
        self.assertEqual(context.timeframe, "1h")
        self.assertEqual(len(context.candles), 3)
        self.assertIsInstance(context.strategy, BaseStrategy)
        self.assertIsInstance(context.initial_portfolio, Portfolio)
        self.assertEqual(context.metadata, {})

    def test_candle_count(self):
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=make_candles(5),
            strategy=make_strategy(),
            initial_portfolio=make_portfolio(),
        )
        self.assertEqual(context.candle_count(), 5)

    def test_is_frozen(self):
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=make_candles(),
            strategy=make_strategy(),
            initial_portfolio=make_portfolio(),
        )
        with self.assertRaises(Exception):
            context.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_rejects_blank_symbol(self):
        with self.assertRaises(InvalidBacktestContextError):
            BacktestContext(
                symbol="   ",
                timeframe="1h",
                candles=make_candles(),
                strategy=make_strategy(),
                initial_portfolio=make_portfolio(),
            )

    def test_rejects_blank_timeframe(self):
        with self.assertRaises(InvalidBacktestContextError):
            BacktestContext(
                symbol="BTCUSDT",
                timeframe="",
                candles=make_candles(),
                strategy=make_strategy(),
                initial_portfolio=make_portfolio(),
            )

    def test_rejects_empty_candles(self):
        with self.assertRaises(InvalidBacktestContextError):
            BacktestContext(
                symbol="BTCUSDT",
                timeframe="1h",
                candles=[],
                strategy=make_strategy(),
                initial_portfolio=make_portfolio(),
            )

    def test_rejects_non_chronological_candles(self):
        candles = list(reversed(make_candles(3)))
        with self.assertRaises(InvalidBacktestContextError):
            BacktestContext(
                symbol="BTCUSDT",
                timeframe="1h",
                candles=candles,
                strategy=make_strategy(),
                initial_portfolio=make_portfolio(),
            )

    def test_rejects_non_candle_items(self):
        with self.assertRaises(InvalidBacktestContextError):
            BacktestContext(
                symbol="BTCUSDT",
                timeframe="1h",
                candles=["not-a-candle"],  # type: ignore[list-item]
                strategy=make_strategy(),
                initial_portfolio=make_portfolio(),
            )

    def test_rejects_non_strategy(self):
        with self.assertRaises(InvalidBacktestContextError):
            BacktestContext(
                symbol="BTCUSDT",
                timeframe="1h",
                candles=make_candles(),
                strategy="not-a-strategy",  # type: ignore[arg-type]
                initial_portfolio=make_portfolio(),
            )

    def test_rejects_non_portfolio(self):
        with self.assertRaises(InvalidBacktestContextError):
            BacktestContext(
                symbol="BTCUSDT",
                timeframe="1h",
                candles=make_candles(),
                strategy=make_strategy(),
                initial_portfolio="not-a-portfolio",  # type: ignore[arg-type]
            )

    def test_rejects_non_dict_metadata(self):
        with self.assertRaises(InvalidBacktestContextError):
            BacktestContext(
                symbol="BTCUSDT",
                timeframe="1h",
                candles=make_candles(),
                strategy=make_strategy(),
                initial_portfolio=make_portfolio(),
                metadata="not-a-dict",  # type: ignore[arg-type]
            )


# ----------------------------------------------------------------------
# backtesting.utils
# ----------------------------------------------------------------------
class TestUtils(unittest.TestCase):
    def test_validate_non_empty_str_accepts_valid_string(self):
        self.assertEqual(validate_non_empty_str("BTCUSDT", name="symbol"), "BTCUSDT")

    def test_validate_non_empty_str_rejects_blank(self):
        with self.assertRaises(BacktestValidationError):
            validate_non_empty_str("   ", name="symbol")

    def test_validate_non_empty_str_rejects_non_string(self):
        with self.assertRaises(BacktestValidationError):
            validate_non_empty_str(123, name="symbol")  # type: ignore[arg-type]

    def test_validate_instance_list_accepts_valid_list(self):
        candles = make_candles(2)
        self.assertEqual(validate_instance_list(candles, Candle, name="candles"), candles)

    def test_validate_instance_list_rejects_non_list(self):
        with self.assertRaises(BacktestValidationError):
            validate_instance_list("not-a-list", Candle, name="candles")  # type: ignore[arg-type]

    def test_validate_instance_list_rejects_wrong_item_type(self):
        with self.assertRaises(BacktestValidationError):
            validate_instance_list([1, 2], Candle, name="candles")

    def test_validate_chronological_candles_accepts_ordered_list(self):
        candles = make_candles(3)
        self.assertEqual(validate_chronological_candles(candles), candles)

    def test_validate_chronological_candles_rejects_empty_list(self):
        with self.assertRaises(BacktestValidationError):
            validate_chronological_candles([])

    def test_validate_chronological_candles_rejects_out_of_order(self):
        candles = list(reversed(make_candles(3)))
        with self.assertRaises(BacktestValidationError):
            validate_chronological_candles(candles)

    def test_validate_chronological_candles_accepts_equal_open_times(self):
        # Not strictly increasing, only non-decreasing, is allowed.
        candle_a = make_candle(open_time=NOW)
        candle_b = make_candle(open_time=NOW)
        self.assertEqual(
            validate_chronological_candles([candle_a, candle_b]), [candle_a, candle_b]
        )

    def test_merge_metadata_combines_sources(self):
        merged = merge_metadata({"a": 1}, {"b": 2})
        self.assertEqual(merged, {"a": 1, "b": 2})

    def test_merge_metadata_later_source_wins(self):
        merged = merge_metadata({"a": 1}, {"a": 2})
        self.assertEqual(merged, {"a": 2})

    def test_merge_metadata_skips_none(self):
        merged = merge_metadata(None, {"a": 1}, None)
        self.assertEqual(merged, {"a": 1})

    def test_merge_metadata_no_sources_returns_empty_dict(self):
        self.assertEqual(merge_metadata(), {})


# ----------------------------------------------------------------------
# backtesting.exceptions
# ----------------------------------------------------------------------
class TestExceptionHierarchy(unittest.TestCase):
    def test_backtest_validation_error_is_backtest_error(self):
        self.assertTrue(issubclass(BacktestValidationError, BacktestError))

    def test_invalid_backtest_context_error_is_backtest_validation_error(self):
        self.assertTrue(issubclass(InvalidBacktestContextError, BacktestValidationError))

    def test_insufficient_backtest_data_error_is_backtest_error(self):
        self.assertTrue(issubclass(InsufficientBacktestDataError, BacktestError))
        self.assertFalse(issubclass(InsufficientBacktestDataError, BacktestValidationError))

    def test_backtester_configuration_error_is_backtest_error(self):
        self.assertTrue(issubclass(BacktesterConfigurationError, BacktestError))

    def test_backtest_error_is_exception(self):
        self.assertTrue(issubclass(BacktestError, Exception))


# ----------------------------------------------------------------------
# BaseBacktester (via a minimal concrete fake, mirroring
# test_risk_management.py's fake BaseRiskManager pattern)
# ----------------------------------------------------------------------
class FakeBacktester(BaseBacktester):
    """Minimal concrete `BaseBacktester` used only to exercise the base class."""

    def run(self, context: BacktestContext) -> BacktestResult:
        self.validate_context(context)
        if context.candle_count() < 2:
            raise InsufficientBacktestDataError("at least two candles are required")
        return self._build_result(
            final_portfolio=context.initial_portfolio,
            summary=f"Replayed {context.candle_count()} candles for {context.symbol}",
            metadata={"run_by": self.name},
        )


class TestBaseBacktester(unittest.TestCase):
    def test_defaults_name_to_class_name(self):
        backtester = FakeBacktester()
        self.assertEqual(backtester.name, "FakeBacktester")

    def test_accepts_custom_name(self):
        backtester = FakeBacktester(name="CustomBacktester")
        self.assertEqual(backtester.name, "CustomBacktester")

    def test_cannot_instantiate_abstract_base_directly(self):
        with self.assertRaises(TypeError):
            BaseBacktester()  # type: ignore[abstract]

    def test_validate_context_accepts_valid_context(self):
        backtester = FakeBacktester()
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=make_candles(),
            strategy=make_strategy(),
            initial_portfolio=make_portfolio(),
        )
        self.assertIs(backtester.validate_context(context), context)

    def test_validate_context_rejects_non_context(self):
        backtester = FakeBacktester()
        with self.assertRaises(InvalidBacktestContextError):
            backtester.validate_context("not-a-context")  # type: ignore[arg-type]

    def test_run_returns_backtest_result(self):
        backtester = FakeBacktester()
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=make_candles(3),
            strategy=make_strategy(),
            initial_portfolio=make_portfolio(),
        )
        result = backtester.run(context)
        self.assertIsInstance(result, BacktestResult)
        self.assertIs(result.final_portfolio, context.initial_portfolio)
        self.assertIn("BTCUSDT", result.summary)
        self.assertEqual(result.metadata, {"run_by": "FakeBacktester"})

    def test_run_raises_insufficient_data_when_too_few_candles(self):
        backtester = FakeBacktester()
        context = BacktestContext(
            symbol="BTCUSDT",
            timeframe="1h",
            candles=make_candles(1),
            strategy=make_strategy(),
            initial_portfolio=make_portfolio(),
        )
        with self.assertRaises(InsufficientBacktestDataError):
            backtester.run(context)

    def test_build_result_defaults_trades_and_metadata(self):
        backtester = FakeBacktester()
        result = backtester._build_result(
            final_portfolio=make_portfolio(), summary="No trades yet"
        )
        self.assertEqual(result.trades, [])
        self.assertEqual(result.metadata, {})

    def test_repr_includes_class_and_name(self):
        backtester = FakeBacktester(name="Replayer")
        self.assertEqual(repr(backtester), "FakeBacktester(name='Replayer')")


# ----------------------------------------------------------------------
# Integration: a realistic BacktestContext built from Candle + Portfolio
# + a real BaseStrategy subclass, run end-to-end by a real
# BaseBacktester subclass.
# ----------------------------------------------------------------------
class TestIntegration(unittest.TestCase):
    def test_end_to_end_run(self):
        backtester = FakeBacktester(name="EndToEndBacktester")
        context = BacktestContext(
            symbol="ETHUSDT",
            timeframe="1h",
            candles=make_candles(4),
            strategy=make_strategy(),
            initial_portfolio=make_portfolio(cash_balance=Decimal("2500")),
            metadata={"run_id": "backtest-1"},
        )
        result = backtester.run(context)

        self.assertEqual(context.candle_count(), 4)
        self.assertEqual(result.final_portfolio.cash_balance, Decimal("2500"))
        self.assertIn("ETHUSDT", result.summary)
        self.assertEqual(result.trades, [])

    def test_no_pnl_statistics_or_aggregation_fields(self):
        # Defensive: BacktestResult must expose exactly the four
        # documented fields -- no PnL, drawdown, win-rate, or other
        # statistics fields have been introduced by this part.
        result = BacktestResult(final_portfolio=make_portfolio(), summary="Done")
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        for forbidden in (
            "pnl",
            "total_return",
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "profit_factor",
        ):
            self.assertNotIn(forbidden, field_names)


if __name__ == "__main__":
    unittest.main()
