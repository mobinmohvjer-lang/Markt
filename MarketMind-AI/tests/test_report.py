"""
test_report.py
------------------
Purpose:
    Unit tests for `backtesting/report.py` (Backtesting Engine Part 5):
    `BacktestReport`.

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

from core.entities.portfolio import Portfolio
from core.entities.position import Position
from core.entities.trade import Trade
from core.enums import OrderSide, PositionSide, PositionStatus

from backtesting.exceptions import BacktestValidationError
from backtesting.metrics import BacktestMetrics, calculate_metrics
from backtesting.report import BacktestReport
from backtesting.result import BacktestResult

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


# ----------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------
def make_portfolio(
    *, cash_balance="10000", positions: list | None = None, total_equity=None
) -> Portfolio:
    return Portfolio(
        portfolio_id="portfolio-1",
        base_currency="USDT",
        cash_balance=Decimal(str(cash_balance)),
        positions=positions or [],
        total_equity=Decimal(str(total_equity)) if total_equity is not None else None,
    )


def make_closed_position(
    *,
    symbol: str = "BTCUSDT",
    entry_price="100",
    quantity="1",
    realized_pnl,
    opened_at: datetime = NOW,
    closed_at: datetime | None = None,
    side: PositionSide = PositionSide.LONG,
) -> Position:
    return Position(
        position_id=f"pos-{opened_at.isoformat()}-{realized_pnl}",
        symbol=symbol,
        side=side,
        entry_price=Decimal(str(entry_price)),
        quantity=Decimal(str(quantity)),
        opened_at=opened_at,
        status=PositionStatus.CLOSED,
        realized_pnl=Decimal(str(realized_pnl)),
        closed_at=closed_at or (opened_at + timedelta(hours=1)),
    )


def make_open_position(
    *,
    symbol: str = "BTCUSDT",
    entry_price="100",
    quantity="1",
    current_price=None,
    opened_at: datetime = NOW,
    side: PositionSide = PositionSide.LONG,
) -> Position:
    return Position(
        position_id=f"open-{opened_at.isoformat()}",
        symbol=symbol,
        side=side,
        entry_price=Decimal(str(entry_price)),
        quantity=Decimal(str(quantity)),
        opened_at=opened_at,
        status=PositionStatus.OPEN,
        current_price=Decimal(str(current_price)) if current_price is not None else None,
    )


def make_trade(
    *,
    trade_id: str = "trade-1",
    symbol: str = "BTCUSDT",
    side: OrderSide = OrderSide.BUY,
    price="100",
    quantity="1",
    executed_at: datetime = NOW,
    order_id=None,
    fee=None,
    fee_asset=None,
    is_maker=None,
) -> Trade:
    return Trade(
        trade_id=trade_id,
        symbol=symbol,
        side=side,
        price=Decimal(str(price)),
        quantity=Decimal(str(quantity)),
        executed_at=executed_at,
        order_id=order_id,
        fee=Decimal(str(fee)) if fee is not None else None,
        fee_asset=fee_asset,
        is_maker=is_maker,
    )


def make_result(
    *, final_portfolio: Portfolio, trades: list[Trade] | None = None, summary="Ran a backtest."
) -> BacktestResult:
    return BacktestResult(
        final_portfolio=final_portfolio,
        summary=summary,
        trades=trades or [],
        metadata={"backtester": "TestBacktester"},
    )


def make_report(
    *,
    initial_portfolio: Portfolio | None = None,
    final_portfolio: Portfolio | None = None,
    trades: list[Trade] | None = None,
    summary: str = "Ran a backtest.",
) -> BacktestReport:
    initial_portfolio = initial_portfolio or make_portfolio()
    final_portfolio = final_portfolio or make_portfolio()
    result = make_result(final_portfolio=final_portfolio, trades=trades, summary=summary)
    metrics = calculate_metrics(result, initial_portfolio)
    return BacktestReport(result, metrics)


# ----------------------------------------------------------------------
# Construction / validation
# ----------------------------------------------------------------------
class TestBacktestReportConstruction(unittest.TestCase):
    def test_valid_construction(self) -> None:
        report = make_report()
        self.assertIsInstance(report.result, BacktestResult)
        self.assertIsInstance(report.metrics, BacktestMetrics)

    def test_rejects_non_backtest_result(self) -> None:
        metrics = calculate_metrics(make_result(final_portfolio=make_portfolio()), make_portfolio())
        with self.assertRaises(BacktestValidationError):
            BacktestReport("not-a-result", metrics)

    def test_rejects_none_result(self) -> None:
        metrics = calculate_metrics(make_result(final_portfolio=make_portfolio()), make_portfolio())
        with self.assertRaises(BacktestValidationError):
            BacktestReport(None, metrics)

    def test_rejects_non_backtest_metrics(self) -> None:
        result = make_result(final_portfolio=make_portfolio())
        with self.assertRaises(BacktestValidationError):
            BacktestReport(result, "not-metrics")

    def test_rejects_none_metrics(self) -> None:
        result = make_result(final_portfolio=make_portfolio())
        with self.assertRaises(BacktestValidationError):
            BacktestReport(result, None)

    def test_rejects_metadata_dict_as_metrics(self) -> None:
        # A raw dict must not be silently accepted in place of BacktestMetrics.
        result = make_result(final_portfolio=make_portfolio())
        with self.assertRaises(BacktestValidationError):
            BacktestReport(result, {"win_rate": 0.5})

    def test_stores_exact_objects_supplied(self) -> None:
        final_portfolio = make_portfolio()
        result = make_result(final_portfolio=final_portfolio)
        metrics = calculate_metrics(result, make_portfolio())
        report = BacktestReport(result, metrics)
        self.assertIs(report.result, result)
        self.assertIs(report.metrics, metrics)


# ----------------------------------------------------------------------
# summary()
# ----------------------------------------------------------------------
class TestSummary(unittest.TestCase):
    def test_returns_string(self) -> None:
        report = make_report()
        self.assertIsInstance(report.summary(), str)

    def test_includes_result_summary_text(self) -> None:
        report = make_report(summary="Custom run summary text.")
        self.assertIn("Custom run summary text.", report.summary())

    def test_includes_trade_count(self) -> None:
        positions = [make_closed_position(realized_pnl="10")]
        report = make_report(final_portfolio=make_portfolio(positions=positions))
        self.assertIn("1 closed trade(s)", report.summary())

    def test_no_trades_summary_mentions_zero(self) -> None:
        report = make_report()
        self.assertIn("0 closed trade(s)", report.summary())

    def test_profit_factor_none_is_labeled_undefined(self) -> None:
        # Only winning trades -> profit_factor is None (no losses).
        positions = [make_closed_position(realized_pnl="10")]
        report = make_report(final_portfolio=make_portfolio(positions=positions))
        self.assertIn("undefined (no losses)", report.summary())

    def test_profit_factor_numeric_when_losses_present(self) -> None:
        positions = [
            make_closed_position(realized_pnl="20", opened_at=NOW),
            make_closed_position(realized_pnl="-10", opened_at=NOW + timedelta(hours=1)),
        ]
        report = make_report(final_portfolio=make_portfolio(positions=positions))
        summary = report.summary()
        self.assertNotIn("undefined", summary)
        self.assertIn("profit factor 2.00", summary)

    def test_percentages_formatted(self) -> None:
        positions = [make_closed_position(realized_pnl="10")]
        report = make_report(
            initial_portfolio=make_portfolio(cash_balance="100"),
            final_portfolio=make_portfolio(cash_balance="110", positions=positions),
        )
        summary = report.summary()
        self.assertIn("win rate 100.00%", summary)
        self.assertIn("total return 10.00%", summary)


# ----------------------------------------------------------------------
# detailed_summary()
# ----------------------------------------------------------------------
class TestDetailedSummary(unittest.TestCase):
    def test_returns_string(self) -> None:
        report = make_report()
        self.assertIsInstance(report.detailed_summary(), str)

    def test_contains_section_headers(self) -> None:
        report = make_report()
        detailed = report.detailed_summary()
        for header in ("Overview", "Trade Statistics", "Equity & Return", "Risk"):
            self.assertIn(header, detailed)

    def test_contains_summary_text(self) -> None:
        report = make_report()
        self.assertIn(report.summary(), report.detailed_summary())

    def test_contains_every_metric_label(self) -> None:
        report = make_report()
        detailed = report.detailed_summary()
        for label in (
            "Total trades:",
            "Winning trades:",
            "Losing trades:",
            "Breakeven trades:",
            "Win rate:",
            "Profit factor:",
            "Gross profit:",
            "Gross loss:",
            "Total realized P&L:",
            "Average win:",
            "Average loss:",
            "Largest win:",
            "Largest loss:",
            "Initial equity:",
            "Final equity:",
            "Total return:",
            "Open positions remaining:",
            "Equity curve points:",
            "Max drawdown:",
            "Sharpe ratio:",
        ):
            self.assertIn(label, detailed)

    def test_no_trades_shows_na_for_win_loss_fields(self) -> None:
        report = make_report()
        detailed = report.detailed_summary()
        self.assertIn("Average win: n/a", detailed)
        self.assertIn("Average loss: n/a", detailed)
        self.assertIn("Largest win: n/a", detailed)
        self.assertIn("Largest loss: n/a", detailed)

    def test_open_positions_remaining_reflected(self) -> None:
        open_position = make_open_position(current_price="150")
        report = make_report(final_portfolio=make_portfolio(positions=[open_position]))
        self.assertIn("Open positions remaining: 1", report.detailed_summary())


# ----------------------------------------------------------------------
# trades_summary()
# ----------------------------------------------------------------------
class TestTradesSummary(unittest.TestCase):
    def test_returns_dict(self) -> None:
        report = make_report()
        self.assertIsInstance(report.trades_summary(), dict)

    def test_empty_trades(self) -> None:
        report = make_report()
        summary = report.trades_summary()
        self.assertEqual(summary["total_trades"], 0)
        self.assertEqual(summary["trades"], [])

    def test_total_trades_matches_count(self) -> None:
        trades = [
            make_trade(trade_id="t1", side=OrderSide.BUY),
            make_trade(trade_id="t2", side=OrderSide.SELL, executed_at=NOW + timedelta(hours=1)),
        ]
        report = make_report(trades=trades)
        summary = report.trades_summary()
        self.assertEqual(summary["total_trades"], 2)
        self.assertEqual(len(summary["trades"]), 2)

    def test_trade_dict_shape(self) -> None:
        trade = make_trade(
            trade_id="t1",
            symbol="ETHUSDT",
            side=OrderSide.BUY,
            price="200",
            quantity="2",
            executed_at=NOW,
            order_id="order-1",
            fee="0.5",
            fee_asset="USDT",
            is_maker=True,
        )
        report = make_report(trades=[trade])
        entry = report.trades_summary()["trades"][0]
        self.assertEqual(
            entry,
            {
                "trade_id": "t1",
                "symbol": "ETHUSDT",
                "side": "buy",
                "price": Decimal("200"),
                "quantity": Decimal("2"),
                "executed_at": NOW,
                "order_id": "order-1",
                "fee": Decimal("0.5"),
                "fee_asset": "USDT",
                "is_maker": True,
            },
        )

    def test_trade_side_is_plain_string_not_enum(self) -> None:
        report = make_report(trades=[make_trade(side=OrderSide.SELL)])
        entry = report.trades_summary()["trades"][0]
        self.assertEqual(entry["side"], "sell")
        self.assertNotIsInstance(entry["side"], OrderSide)

    def test_trade_order_preserved(self) -> None:
        trades = [
            make_trade(trade_id="t1", executed_at=NOW),
            make_trade(trade_id="t2", executed_at=NOW + timedelta(hours=1)),
            make_trade(trade_id="t3", executed_at=NOW + timedelta(hours=2)),
        ]
        report = make_report(trades=trades)
        ids = [entry["trade_id"] for entry in report.trades_summary()["trades"]]
        self.assertEqual(ids, ["t1", "t2", "t3"])

    def test_optional_fields_default_none(self) -> None:
        trade = make_trade(trade_id="t1")
        report = make_report(trades=[trade])
        entry = report.trades_summary()["trades"][0]
        self.assertIsNone(entry["order_id"])
        self.assertIsNone(entry["fee"])
        self.assertIsNone(entry["fee_asset"])
        self.assertIsNone(entry["is_maker"])


# ----------------------------------------------------------------------
# metrics_summary()
# ----------------------------------------------------------------------
class TestMetricsSummary(unittest.TestCase):
    def test_returns_dict(self) -> None:
        report = make_report()
        self.assertIsInstance(report.metrics_summary(), dict)

    def test_contains_every_documented_key(self) -> None:
        report = make_report()
        summary = report.metrics_summary()
        expected_keys = {
            "total_trades",
            "winning_trades",
            "losing_trades",
            "breakeven_trades",
            "win_rate",
            "gross_profit",
            "gross_loss",
            "total_realized_pnl",
            "profit_factor",
            "average_win",
            "average_loss",
            "largest_win",
            "largest_loss",
            "initial_equity",
            "final_equity",
            "total_return",
            "total_return_pct",
            "open_positions_remaining",
            "equity_curve_points",
            "max_drawdown_pct",
            "max_drawdown_amount",
            "sharpe_ratio",
            "metadata",
        }
        self.assertEqual(set(summary.keys()), expected_keys)

    def test_values_match_underlying_metrics(self) -> None:
        positions = [
            make_closed_position(realized_pnl="20", opened_at=NOW),
            make_closed_position(realized_pnl="-10", opened_at=NOW + timedelta(hours=1)),
        ]
        report = make_report(final_portfolio=make_portfolio(positions=positions))
        summary = report.metrics_summary()
        m = report.metrics
        self.assertEqual(summary["total_trades"], m.total_trades)
        self.assertEqual(summary["winning_trades"], m.winning_trades)
        self.assertEqual(summary["losing_trades"], m.losing_trades)
        self.assertEqual(summary["win_rate"], m.win_rate)
        self.assertEqual(summary["gross_profit"], m.gross_profit)
        self.assertEqual(summary["gross_loss"], m.gross_loss)
        self.assertEqual(summary["profit_factor"], m.profit_factor)
        self.assertEqual(summary["initial_equity"], m.initial_equity)
        self.assertEqual(summary["final_equity"], m.final_equity)
        self.assertEqual(summary["total_return"], m.total_return)
        self.assertEqual(summary["sharpe_ratio"], m.sharpe_ratio)
        self.assertEqual(summary["max_drawdown_pct"], m.max_drawdown_pct)
        self.assertEqual(summary["max_drawdown_amount"], m.max_drawdown_amount)

    def test_equity_curve_points_is_length_not_curve(self) -> None:
        positions = [make_closed_position(realized_pnl="5")]
        report = make_report(final_portfolio=make_portfolio(positions=positions))
        summary = report.metrics_summary()
        self.assertEqual(summary["equity_curve_points"], len(report.metrics.equity_curve))
        self.assertNotIn("equity_curve", summary)

    def test_metadata_is_copy_not_same_object(self) -> None:
        report = make_report()
        summary = report.metrics_summary()
        self.assertEqual(summary["metadata"], report.metrics.metadata)
        self.assertIsNot(summary["metadata"], report.metrics.metadata)

    def test_no_losses_profit_factor_is_none(self) -> None:
        positions = [make_closed_position(realized_pnl="10")]
        report = make_report(final_portfolio=make_portfolio(positions=positions))
        self.assertIsNone(report.metrics_summary()["profit_factor"])


# ----------------------------------------------------------------------
# full_report()
# ----------------------------------------------------------------------
class TestFullReport(unittest.TestCase):
    def test_returns_dict_with_all_four_sections(self) -> None:
        report = make_report()
        full = report.full_report()
        self.assertIsInstance(full, dict)
        self.assertEqual(
            set(full.keys()), {"summary", "detailed_summary", "trades", "metrics"}
        )

    def test_sections_match_individual_methods(self) -> None:
        positions = [make_closed_position(realized_pnl="10")]
        trades = [make_trade(trade_id="t1")]
        report = make_report(final_portfolio=make_portfolio(positions=positions), trades=trades)
        full = report.full_report()
        self.assertEqual(full["summary"], report.summary())
        self.assertEqual(full["detailed_summary"], report.detailed_summary())
        self.assertEqual(full["trades"], report.trades_summary())
        self.assertEqual(full["metrics"], report.metrics_summary())


# ----------------------------------------------------------------------
# Determinism / no mutation / scope boundaries
# ----------------------------------------------------------------------
class TestDeterminismAndNoMutation(unittest.TestCase):
    def test_repeated_calls_produce_identical_output(self) -> None:
        positions = [
            make_closed_position(realized_pnl="20", opened_at=NOW),
            make_closed_position(realized_pnl="-5", opened_at=NOW + timedelta(hours=1)),
        ]
        trades = [make_trade(trade_id="t1"), make_trade(trade_id="t2")]
        report = make_report(final_portfolio=make_portfolio(positions=positions), trades=trades)

        self.assertEqual(report.summary(), report.summary())
        self.assertEqual(report.detailed_summary(), report.detailed_summary())
        self.assertEqual(report.trades_summary(), report.trades_summary())
        self.assertEqual(report.metrics_summary(), report.metrics_summary())

    def test_does_not_mutate_result_or_metrics(self) -> None:
        positions = [make_closed_position(realized_pnl="10")]
        result = make_result(final_portfolio=make_portfolio(positions=positions))
        metrics = calculate_metrics(result, make_portfolio())
        result_before = copy.deepcopy(result)
        metrics_before = copy.deepcopy(metrics)

        report = BacktestReport(result, metrics)
        report.summary()
        report.detailed_summary()
        report.trades_summary()
        report.metrics_summary()
        report.full_report()

        self.assertEqual(result, result_before)
        self.assertEqual(metrics, metrics_before)

    def test_mutating_returned_trades_dict_does_not_affect_report(self) -> None:
        report = make_report(trades=[make_trade(trade_id="t1")])
        first_call = report.trades_summary()
        first_call["trades"].append({"fake": "entry"})
        second_call = report.trades_summary()
        self.assertEqual(len(second_call["trades"]), 1)

    def test_mutating_returned_metadata_does_not_affect_report(self) -> None:
        report = make_report()
        summary = report.metrics_summary()
        summary["metadata"]["extra_key"] = "should not persist"
        self.assertNotIn("extra_key", report.metrics.metadata)

    def test_no_broker_order_ai_fields_anywhere(self) -> None:
        positions = [make_closed_position(realized_pnl="10")]
        trades = [make_trade(trade_id="t1")]
        report = make_report(final_portfolio=make_portfolio(positions=positions), trades=trades)
        full_text = repr(report.full_report())
        for forbidden in ("broker", "order_execution", "ai_model", "chart", "html", "pdf"):
            self.assertNotIn(forbidden, full_text.lower())


# ----------------------------------------------------------------------
# Integration: a realistic multi-trade run
# ----------------------------------------------------------------------
class TestIntegration(unittest.TestCase):
    def test_end_to_end_report_from_realistic_run(self) -> None:
        initial_portfolio = make_portfolio(cash_balance="1000")

        closed_positions = [
            make_closed_position(
                symbol="BTCUSDT",
                entry_price="100",
                quantity="1",
                realized_pnl="50",
                opened_at=NOW,
                closed_at=NOW + timedelta(hours=1),
            ),
            make_closed_position(
                symbol="BTCUSDT",
                entry_price="150",
                quantity="1",
                realized_pnl="-20",
                opened_at=NOW + timedelta(hours=2),
                closed_at=NOW + timedelta(hours=3),
            ),
        ]
        open_position = make_open_position(
            symbol="BTCUSDT",
            entry_price="200",
            quantity="0.5",
            current_price="210",
            opened_at=NOW + timedelta(hours=4),
        )
        final_portfolio = make_portfolio(
            cash_balance="1030",
            positions=closed_positions + [open_position],
        )

        trades = [
            make_trade(trade_id="t1", side=OrderSide.BUY, price="100", executed_at=NOW),
            make_trade(
                trade_id="t2",
                side=OrderSide.SELL,
                price="150",
                executed_at=NOW + timedelta(hours=1),
            ),
            make_trade(
                trade_id="t3",
                side=OrderSide.BUY,
                price="150",
                executed_at=NOW + timedelta(hours=2),
            ),
            make_trade(
                trade_id="t4",
                side=OrderSide.SELL,
                price="130",
                executed_at=NOW + timedelta(hours=3),
            ),
            make_trade(
                trade_id="t5",
                side=OrderSide.BUY,
                price="200",
                quantity="0.5",
                executed_at=NOW + timedelta(hours=4),
            ),
        ]

        result = make_result(
            final_portfolio=final_portfolio,
            trades=trades,
            summary="Replayed 5 candle(s) for BTCUSDT/1h using strategy 'TestStrategy'.",
        )
        metrics = calculate_metrics(result, initial_portfolio)
        report = BacktestReport(result, metrics)

        # summary()
        summary = report.summary()
        self.assertIn("Replayed 5 candle(s)", summary)
        self.assertIn("2 closed trade(s)", summary)

        # detailed_summary()
        detailed = report.detailed_summary()
        self.assertIn("Total trades: 2", detailed)
        self.assertIn("Winning trades: 1", detailed)
        self.assertIn("Losing trades: 1", detailed)
        self.assertIn("Open positions remaining: 1", detailed)

        # trades_summary()
        trades_view = report.trades_summary()
        self.assertEqual(trades_view["total_trades"], 5)
        self.assertEqual(
            [entry["trade_id"] for entry in trades_view["trades"]],
            ["t1", "t2", "t3", "t4", "t5"],
        )

        # metrics_summary()
        metrics_view = report.metrics_summary()
        self.assertEqual(metrics_view["total_trades"], 2)
        self.assertEqual(metrics_view["winning_trades"], 1)
        self.assertEqual(metrics_view["losing_trades"], 1)
        self.assertEqual(metrics_view["gross_profit"], Decimal("50"))
        self.assertEqual(metrics_view["gross_loss"], Decimal("20"))
        self.assertEqual(metrics_view["open_positions_remaining"], 1)

        # full_report() ties everything together consistently
        full = report.full_report()
        self.assertEqual(full["summary"], summary)
        self.assertEqual(full["detailed_summary"], detailed)
        self.assertEqual(full["trades"], trades_view)
        self.assertEqual(full["metrics"], metrics_view)

        # Reused BacktestMetrics/BacktestResult objects were never mutated.
        self.assertEqual(len(final_portfolio.positions), 3)
        self.assertEqual(initial_portfolio.cash_balance, Decimal("1000"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
