"""
test_metrics.py
------------------
Purpose:
    Unit tests for `backtesting/metrics.py` (Backtesting Engine Part 4):
    `BacktestMetrics`, `calculate_metrics`, and the smaller
    building-block calculations it composes (`win_rate`,
    `profit_factor`, `compute_equity_curve`, `max_drawdown`,
    `sharpe_ratio`).

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
from core.enums import PositionSide, PositionStatus

from backtesting.exceptions import BacktestValidationError
from backtesting.metrics import (
    BacktestMetrics,
    calculate_metrics,
    compute_equity_curve,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    win_rate,
)
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


def make_result(*, final_portfolio: Portfolio, trades: list | None = None) -> BacktestResult:
    return BacktestResult(
        final_portfolio=final_portfolio,
        summary="test backtest run",
        trades=trades or [],
        metadata={},
    )


# ----------------------------------------------------------------------
# win_rate()
# ----------------------------------------------------------------------
class TestWinRate(unittest.TestCase):
    def test_empty_list_returns_zero(self) -> None:
        self.assertEqual(win_rate([]), 0.0)

    def test_all_winners(self) -> None:
        positions = [make_closed_position(realized_pnl="10"), make_closed_position(realized_pnl="5")]
        self.assertEqual(win_rate(positions), 1.0)

    def test_all_losers(self) -> None:
        positions = [make_closed_position(realized_pnl="-10"), make_closed_position(realized_pnl="-5")]
        self.assertEqual(win_rate(positions), 0.0)

    def test_mixed(self) -> None:
        positions = [
            make_closed_position(realized_pnl="10"),
            make_closed_position(realized_pnl="-5"),
            make_closed_position(realized_pnl="3"),
            make_closed_position(realized_pnl="0"),
        ]
        # 2 winners (strictly > 0) out of 4
        self.assertAlmostEqual(win_rate(positions), 0.5)


# ----------------------------------------------------------------------
# profit_factor()
# ----------------------------------------------------------------------
class TestProfitFactor(unittest.TestCase):
    def test_empty_list_returns_zero(self) -> None:
        self.assertEqual(profit_factor([]), 0.0)

    def test_no_losses_returns_none(self) -> None:
        positions = [make_closed_position(realized_pnl="10"), make_closed_position(realized_pnl="5")]
        self.assertIsNone(profit_factor(positions))

    def test_no_profits_no_losses_returns_zero(self) -> None:
        positions = [make_closed_position(realized_pnl="0")]
        self.assertEqual(profit_factor(positions), 0.0)

    def test_typical_ratio(self) -> None:
        positions = [
            make_closed_position(realized_pnl="20"),
            make_closed_position(realized_pnl="-10"),
        ]
        self.assertAlmostEqual(profit_factor(positions), 2.0)


# ----------------------------------------------------------------------
# compute_equity_curve()
# ----------------------------------------------------------------------
class TestComputeEquityCurve(unittest.TestCase):
    def test_no_closed_positions_returns_single_point(self) -> None:
        curve = compute_equity_curve(Decimal("1000"), [])
        self.assertEqual(curve, [Decimal("1000")])

    def test_cumulative_progression(self) -> None:
        positions = [
            make_closed_position(realized_pnl="100"),
            make_closed_position(realized_pnl="-30"),
            make_closed_position(realized_pnl="50"),
        ]
        curve = compute_equity_curve(Decimal("1000"), positions)
        self.assertEqual(curve, [Decimal("1000"), Decimal("1100"), Decimal("1070"), Decimal("1120")])


# ----------------------------------------------------------------------
# max_drawdown()
# ----------------------------------------------------------------------
class TestMaxDrawdown(unittest.TestCase):
    def test_empty_curve_raises(self) -> None:
        with self.assertRaises(BacktestValidationError):
            max_drawdown([])

    def test_monotonic_increase_has_no_drawdown(self) -> None:
        pct, amount = max_drawdown([Decimal("100"), Decimal("110"), Decimal("120")])
        self.assertEqual(pct, 0.0)
        self.assertEqual(amount, Decimal("0"))

    def test_single_decline(self) -> None:
        pct, amount = max_drawdown([Decimal("100"), Decimal("80")])
        self.assertEqual(amount, Decimal("20"))
        self.assertAlmostEqual(pct, 0.2)

    def test_recovers_then_declines_further(self) -> None:
        # peak 100 -> trough 50 (drawdown 50) -> new peak 200 -> trough 100 (drawdown 100)
        curve = [Decimal("100"), Decimal("50"), Decimal("200"), Decimal("100")]
        pct, amount = max_drawdown(curve)
        self.assertEqual(amount, Decimal("100"))
        self.assertAlmostEqual(pct, 0.5)

    def test_non_positive_peak_pct_is_zero(self) -> None:
        curve = [Decimal("0"), Decimal("-10")]
        pct, amount = max_drawdown(curve)
        self.assertEqual(amount, Decimal("10"))
        self.assertEqual(pct, 0.0)


# ----------------------------------------------------------------------
# sharpe_ratio()
# ----------------------------------------------------------------------
class TestSharpeRatio(unittest.TestCase):
    def test_fewer_than_two_returns_is_zero(self) -> None:
        self.assertEqual(sharpe_ratio([]), 0.0)
        self.assertEqual(sharpe_ratio([0.1]), 0.0)

    def test_zero_variance_is_zero(self) -> None:
        self.assertEqual(sharpe_ratio([0.05, 0.05, 0.05]), 0.0)

    def test_positive_returns_give_positive_ratio(self) -> None:
        ratio = sharpe_ratio([0.1, 0.05, 0.2, -0.02])
        self.assertGreater(ratio, 0.0)

    def test_risk_free_rate_shifts_ratio(self) -> None:
        returns = [0.1, 0.05, 0.2, -0.02]
        base = sharpe_ratio(returns)
        shifted = sharpe_ratio(returns, risk_free_rate=0.5)
        self.assertNotEqual(base, shifted)

    def test_annualization_scales_ratio(self) -> None:
        returns = [0.1, 0.05, 0.2, -0.02]
        base = sharpe_ratio(returns)
        annualized = sharpe_ratio(returns, annualization_factor=4.0)
        self.assertAlmostEqual(annualized, base * (4.0 ** 0.5))


# ----------------------------------------------------------------------
# calculate_metrics() -- input validation
# ----------------------------------------------------------------------
class TestCalculateMetricsValidation(unittest.TestCase):
    def test_non_backtest_result_raises(self) -> None:
        with self.assertRaises(BacktestValidationError):
            calculate_metrics("not-a-result", make_portfolio())  # type: ignore[arg-type]

    def test_non_portfolio_initial_raises(self) -> None:
        result = make_result(final_portfolio=make_portfolio())
        with self.assertRaises(BacktestValidationError):
            calculate_metrics(result, "not-a-portfolio")  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# calculate_metrics() -- behavior
# ----------------------------------------------------------------------
class TestCalculateMetricsBehavior(unittest.TestCase):
    def test_no_trades_at_all(self) -> None:
        initial = make_portfolio(cash_balance="10000")
        final = make_portfolio(cash_balance="10000")
        result = make_result(final_portfolio=final)

        metrics = calculate_metrics(result, initial)

        self.assertIsInstance(metrics, BacktestMetrics)
        self.assertEqual(metrics.total_trades, 0)
        self.assertEqual(metrics.winning_trades, 0)
        self.assertEqual(metrics.losing_trades, 0)
        self.assertEqual(metrics.breakeven_trades, 0)
        self.assertEqual(metrics.win_rate, 0.0)
        self.assertEqual(metrics.gross_profit, Decimal("0"))
        self.assertEqual(metrics.gross_loss, Decimal("0"))
        self.assertEqual(metrics.total_realized_pnl, Decimal("0"))
        self.assertEqual(metrics.profit_factor, 0.0)
        self.assertIsNone(metrics.average_win)
        self.assertIsNone(metrics.average_loss)
        self.assertIsNone(metrics.largest_win)
        self.assertIsNone(metrics.largest_loss)
        self.assertEqual(metrics.initial_equity, Decimal("10000"))
        self.assertEqual(metrics.final_equity, Decimal("10000"))
        self.assertEqual(metrics.total_return, Decimal("0"))
        self.assertEqual(metrics.total_return_pct, 0.0)
        self.assertEqual(metrics.open_positions_remaining, 0)
        self.assertEqual(metrics.equity_curve, [Decimal("10000")])
        self.assertEqual(metrics.max_drawdown_pct, 0.0)
        self.assertEqual(metrics.max_drawdown_amount, Decimal("0"))
        self.assertEqual(metrics.sharpe_ratio, 0.0)

    def test_winning_and_losing_trades(self) -> None:
        initial = make_portfolio(cash_balance="10000")
        closed = [
            make_closed_position(realized_pnl="200", opened_at=NOW),
            make_closed_position(realized_pnl="-50", opened_at=NOW + timedelta(hours=2)),
            make_closed_position(realized_pnl="100", opened_at=NOW + timedelta(hours=4)),
        ]
        final = make_portfolio(cash_balance="10250", positions=closed)
        result = make_result(final_portfolio=final)

        metrics = calculate_metrics(result, initial)

        self.assertEqual(metrics.total_trades, 3)
        self.assertEqual(metrics.winning_trades, 2)
        self.assertEqual(metrics.losing_trades, 1)
        self.assertEqual(metrics.breakeven_trades, 0)
        self.assertAlmostEqual(metrics.win_rate, 2 / 3)
        self.assertEqual(metrics.gross_profit, Decimal("300"))
        self.assertEqual(metrics.gross_loss, Decimal("50"))
        self.assertEqual(metrics.total_realized_pnl, Decimal("250"))
        self.assertAlmostEqual(metrics.profit_factor, 6.0)
        self.assertEqual(metrics.average_win, Decimal("150"))
        self.assertEqual(metrics.average_loss, Decimal("50"))
        self.assertEqual(metrics.largest_win, Decimal("200"))
        self.assertEqual(metrics.largest_loss, Decimal("-50"))
        self.assertEqual(metrics.initial_equity, Decimal("10000"))
        self.assertEqual(metrics.final_equity, Decimal("10250"))
        self.assertEqual(metrics.total_return, Decimal("250"))
        self.assertAlmostEqual(metrics.total_return_pct, 0.025)
        self.assertEqual(
            metrics.equity_curve,
            [Decimal("10000"), Decimal("10200"), Decimal("10150"), Decimal("10250")],
        )

    def test_breakeven_trade_counted_separately(self) -> None:
        initial = make_portfolio(cash_balance="5000")
        closed = [make_closed_position(realized_pnl="0")]
        final = make_portfolio(cash_balance="5000", positions=closed)
        result = make_result(final_portfolio=final)

        metrics = calculate_metrics(result, initial)

        self.assertEqual(metrics.total_trades, 1)
        self.assertEqual(metrics.winning_trades, 0)
        self.assertEqual(metrics.losing_trades, 0)
        self.assertEqual(metrics.breakeven_trades, 1)
        self.assertEqual(metrics.win_rate, 0.0)
        self.assertEqual(metrics.profit_factor, 0.0)

    def test_open_positions_excluded_from_trade_stats_but_counted(self) -> None:
        initial = make_portfolio(cash_balance="10000")
        closed = [make_closed_position(realized_pnl="100")]
        still_open = make_open_position(current_price="110", entry_price="100", quantity="2")
        final = make_portfolio(cash_balance="9800", positions=closed + [still_open])
        result = make_result(final_portfolio=final)

        metrics = calculate_metrics(result, initial)

        self.assertEqual(metrics.total_trades, 1)
        self.assertEqual(metrics.open_positions_remaining, 1)
        # final equity should use cash + mark-to-market of the open position
        self.assertEqual(metrics.final_equity, Decimal("9800") + Decimal("2") * Decimal("110"))

    def test_closed_position_with_none_realized_pnl_is_skipped(self) -> None:
        initial = make_portfolio(cash_balance="10000")
        unresolved = Position(
            position_id="unresolved",
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            entry_price=Decimal("100"),
            quantity=Decimal("1"),
            opened_at=NOW,
            status=PositionStatus.CLOSED,
            realized_pnl=None,
        )
        final = make_portfolio(cash_balance="10000", positions=[unresolved])
        result = make_result(final_portfolio=final)

        metrics = calculate_metrics(result, initial)

        self.assertEqual(metrics.total_trades, 0)

    def test_total_equity_field_used_when_present(self) -> None:
        initial = make_portfolio(cash_balance="10000", total_equity="10000")
        final = make_portfolio(cash_balance="9000", total_equity="11500")
        result = make_result(final_portfolio=final)

        metrics = calculate_metrics(result, initial)

        self.assertEqual(metrics.initial_equity, Decimal("10000"))
        self.assertEqual(metrics.final_equity, Decimal("11500"))
        self.assertEqual(metrics.total_return, Decimal("1500"))

    def test_non_positive_initial_equity_gives_zero_return_pct(self) -> None:
        initial = make_portfolio(cash_balance="0")
        final = make_portfolio(cash_balance="500")
        result = make_result(final_portfolio=final)

        metrics = calculate_metrics(result, initial)

        self.assertEqual(metrics.total_return_pct, 0.0)

    def test_max_drawdown_reflected_in_metrics(self) -> None:
        initial = make_portfolio(cash_balance="1000")
        closed = [
            make_closed_position(realized_pnl="-500", opened_at=NOW),
        ]
        final = make_portfolio(cash_balance="500", positions=closed)
        result = make_result(final_portfolio=final)

        metrics = calculate_metrics(result, initial)

        self.assertEqual(metrics.max_drawdown_amount, Decimal("500"))
        self.assertAlmostEqual(metrics.max_drawdown_pct, 0.5)

    def test_sharpe_ratio_parameters_forwarded(self) -> None:
        initial = make_portfolio(cash_balance="1000")
        closed = [
            make_closed_position(realized_pnl="100", opened_at=NOW),
            make_closed_position(realized_pnl="-40", opened_at=NOW + timedelta(hours=1)),
            make_closed_position(realized_pnl="60", opened_at=NOW + timedelta(hours=2)),
        ]
        final = make_portfolio(cash_balance="1120", positions=closed)
        result = make_result(final_portfolio=final)

        default_metrics = calculate_metrics(result, initial)
        annualized_metrics = calculate_metrics(result, initial, annualization_factor=4.0)

        self.assertNotEqual(default_metrics.sharpe_ratio, annualized_metrics.sharpe_ratio)

    def test_metadata_contains_traceable_details(self) -> None:
        initial = make_portfolio(cash_balance="1000")
        closed = [make_closed_position(realized_pnl="50")]
        final = make_portfolio(cash_balance="1050", positions=closed)
        result = make_result(final_portfolio=final)

        metrics = calculate_metrics(result, initial, risk_free_rate=0.01, annualization_factor=2.0)

        self.assertEqual(metrics.metadata["closed_position_count"], 1)
        self.assertEqual(metrics.metadata["open_position_count"], 0)
        self.assertEqual(metrics.metadata["equity_curve_points"], 2)
        self.assertEqual(metrics.metadata["risk_free_rate"], 0.01)
        self.assertEqual(metrics.metadata["annualization_factor"], 2.0)

    def test_determinism_across_repeated_calls(self) -> None:
        initial = make_portfolio(cash_balance="1000")
        closed = [
            make_closed_position(realized_pnl="30", opened_at=NOW),
            make_closed_position(realized_pnl="-10", opened_at=NOW + timedelta(hours=1)),
        ]
        final = make_portfolio(cash_balance="1020", positions=closed)
        result = make_result(final_portfolio=final)

        first = calculate_metrics(result, initial)
        second = calculate_metrics(result, initial)

        self.assertEqual(first, second)

    def test_no_mutation_of_inputs(self) -> None:
        initial = make_portfolio(cash_balance="1000")
        closed = [make_closed_position(realized_pnl="30")]
        final = make_portfolio(cash_balance="1030", positions=closed)
        result = make_result(final_portfolio=final)

        initial_snapshot = copy.deepcopy(initial)
        final_snapshot = copy.deepcopy(final)
        result_snapshot = copy.deepcopy(result)

        calculate_metrics(result, initial)

        self.assertEqual(initial.cash_balance, initial_snapshot.cash_balance)
        self.assertEqual(initial.positions, initial_snapshot.positions)
        self.assertEqual(final.cash_balance, final_snapshot.cash_balance)
        self.assertEqual(final.positions, final_snapshot.positions)
        self.assertEqual(result.trades, result_snapshot.trades)
        self.assertEqual(result.metadata, result_snapshot.metadata)


# ----------------------------------------------------------------------
# Scope-boundary checks
# ----------------------------------------------------------------------
class TestScopeBoundaries(unittest.TestCase):
    def test_backtest_metrics_has_no_order_or_ai_fields(self) -> None:
        field_names = set(BacktestMetrics.__dataclass_fields__.keys())
        forbidden = {
            "order_id",
            "broker",
            "ai_model",
            "execution_status",
            "optimized_parameters",
            "chart",
            "report",
        }
        self.assertTrue(field_names.isdisjoint(forbidden))

    def test_backtest_metrics_is_frozen(self) -> None:
        initial = make_portfolio(cash_balance="1000")
        final = make_portfolio(cash_balance="1000")
        result = make_result(final_portfolio=final)
        metrics = calculate_metrics(result, initial)

        with self.assertRaises(Exception):
            metrics.total_trades = 99  # type: ignore[misc]


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
