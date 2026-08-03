"""
backtesting/report.py

Defines `BacktestReport`: human-readable and machine-readable summary
generation for an already-completed backtest run.

This is Backtesting Engine Part 5 -- the final item previously
documented in `backtesting/__init__.py`'s "Planned contents" as
`report.py`. It consumes an already-produced `backtesting.result.
BacktestResult` and an already-produced `backtesting.metrics.
BacktestMetrics` (Part 4) and formats their contents into deterministic
summaries; it does not run a backtest, does not simulate trades, does
not compute any statistic itself, and does not define trading rules of
its own -- `backtesting/` remains a consumer, never a strategy author
(see `PROJECT_RULES.md` Section 1, principle 5).

Reuses only what already exists: `backtesting.result.BacktestResult`,
`backtesting.metrics.BacktestMetrics`, and
`backtesting.exceptions.BacktestValidationError` -- no new domain
concepts, no new exception types, and no changes to any existing
Backtesting Engine file (`base.py`, `context.py`, `result.py`,
`exceptions.py`, `utils.py`, `basic_backtester.py`,
`portfolio_simulator.py`, `metrics.py` are all left completely
untouched).

Deterministic and side-effect free: no randomness, no wall-clock
reads, no network/database/file I/O, no AI. Never mutates the
`BacktestResult`/`BacktestMetrics` passed in -- every method only
reads from them. Every public method returns only a `str` or a
`dict` (per this milestone's scope), never a custom object.

Explicitly out of scope for this module (see `PROJECT_RULES.md`
Section 1, principle 5 and this milestone's task boundaries):
    - No charts, no plotting libraries.
    - No HTML, no PDF.
    - No CSV export, no file writing of any kind.
    - No logging.
    - No AI.
    - No broker/order-execution/replay logic.
    - No new performance-statistics calculations -- everything
      reported here is read directly from the supplied
      `BacktestResult`/`BacktestMetrics`, never recomputed.
"""

from __future__ import annotations

from typing import Any

from core.entities.trade import Trade

from backtesting.exceptions import BacktestValidationError
from backtesting.metrics import BacktestMetrics
from backtesting.result import BacktestResult


class BacktestReport:
    """
    Deterministic summary generator for a completed backtest run.

    Wraps an already-produced `BacktestResult` (Backtesting Engine
    Part 1/2) and an already-produced `BacktestMetrics` (Backtesting
    Engine Part 4) and exposes several read-only views over them --
    a short one-line `summary()`, a longer `detailed_summary()`, a
    structured `trades_summary()`, and a structured `metrics_summary()`.

    Neither the `BacktestResult` nor the `BacktestMetrics` supplied at
    construction is ever mutated, and no field of either is
    recomputed -- this class only reads and formats what it is given.

    Attributes:
        result: The `BacktestResult` this report describes.
        metrics: The `BacktestMetrics` this report describes.
    """

    def __init__(self, result: BacktestResult, metrics: BacktestMetrics) -> None:
        """
        Parameters
        ----------
        result : BacktestResult
            The already-produced output of some `BaseBacktester.run()`
            call.
        metrics : BacktestMetrics
            The already-produced output of `backtesting.metrics.
            calculate_metrics()` for the same run.

        Raises
        ------
        BacktestValidationError
            If `result` is not a `BacktestResult`, or `metrics` is not
            a `BacktestMetrics`.
        """
        if not isinstance(result, BacktestResult):
            raise BacktestValidationError(
                f"result must be a BacktestResult, got {type(result).__name__}"
            )
        if not isinstance(metrics, BacktestMetrics):
            raise BacktestValidationError(
                f"metrics must be a BacktestMetrics, got {type(metrics).__name__}"
            )
        self.result = result
        self.metrics = metrics

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def summary(self) -> str:
        """
        A short, one-paragraph, human-readable summary of the run.

        Combines the backtester's own `BacktestResult.summary` with the
        headline performance figures from `BacktestMetrics`.

        Returns
        -------
        str
        """
        m = self.metrics
        profit_factor_text = (
            f"{m.profit_factor:.2f}" if m.profit_factor is not None else "undefined (no losses)"
        )
        return (
            f"{self.result.summary} "
            f"Performance: {m.total_trades} closed trade(s), "
            f"win rate {self._pct(m.win_rate)}, "
            f"profit factor {profit_factor_text}, "
            f"total return {self._pct(m.total_return_pct)} "
            f"({m.total_return}), "
            f"max drawdown {self._pct(m.max_drawdown_pct)}, "
            f"Sharpe ratio {m.sharpe_ratio:.2f}."
        )

    def detailed_summary(self) -> str:
        """
        A longer, multi-section, human-readable summary of the run.

        Sections: overview (`summary()`), trade statistics, equity/
        return statistics, and risk statistics -- every figure taken
        directly from `self.result`/`self.metrics`, nothing recomputed.

        Returns
        -------
        str
        """
        m = self.metrics
        profit_factor_text = (
            f"{m.profit_factor:.2f}" if m.profit_factor is not None else "undefined (no losses)"
        )
        average_win_text = f"{m.average_win}" if m.average_win is not None else "n/a"
        average_loss_text = f"{m.average_loss}" if m.average_loss is not None else "n/a"
        largest_win_text = f"{m.largest_win}" if m.largest_win is not None else "n/a"
        largest_loss_text = f"{m.largest_loss}" if m.largest_loss is not None else "n/a"

        lines = [
            "Backtest Report",
            "===============",
            "",
            "Overview",
            "--------",
            self.summary(),
            "",
            "Trade Statistics",
            "-----------------",
            f"Total trades: {m.total_trades}",
            f"Winning trades: {m.winning_trades}",
            f"Losing trades: {m.losing_trades}",
            f"Breakeven trades: {m.breakeven_trades}",
            f"Win rate: {self._pct(m.win_rate)}",
            f"Profit factor: {profit_factor_text}",
            f"Gross profit: {m.gross_profit}",
            f"Gross loss: {m.gross_loss}",
            f"Total realized P&L: {m.total_realized_pnl}",
            f"Average win: {average_win_text}",
            f"Average loss: {average_loss_text}",
            f"Largest win: {largest_win_text}",
            f"Largest loss: {largest_loss_text}",
            "",
            "Equity & Return",
            "-----------------",
            f"Initial equity: {m.initial_equity}",
            f"Final equity: {m.final_equity}",
            f"Total return: {m.total_return} ({self._pct(m.total_return_pct)})",
            f"Open positions remaining: {m.open_positions_remaining}",
            f"Equity curve points: {len(m.equity_curve)}",
            "",
            "Risk",
            "-----",
            f"Max drawdown: {self._pct(m.max_drawdown_pct)} ({m.max_drawdown_amount})",
            f"Sharpe ratio: {m.sharpe_ratio:.4f}",
        ]
        return "\n".join(lines)

    def trades_summary(self) -> dict[str, Any]:
        """
        A structured view over every `Trade` recorded in `self.result`.

        Returns
        -------
        dict[str, Any]
            ``{"total_trades": int, "trades": [ {...}, ... ]}`` -- each
            trade entry built by `_trade_to_dict`, in the same order
            `BacktestResult.trades` already carries them (chronological,
            per every existing concrete `BaseBacktester`).
        """
        trades = self.result.trades
        return {
            "total_trades": len(trades),
            "trades": [self._trade_to_dict(trade) for trade in trades],
        }

    def metrics_summary(self) -> dict[str, Any]:
        """
        A structured view over every field of `self.metrics`.

        Returns
        -------
        dict[str, Any]
            One key per `BacktestMetrics` field (excluding `metadata`,
            which is merged in under its own key), read directly --
            nothing recomputed.
        """
        m = self.metrics
        return {
            "total_trades": m.total_trades,
            "winning_trades": m.winning_trades,
            "losing_trades": m.losing_trades,
            "breakeven_trades": m.breakeven_trades,
            "win_rate": m.win_rate,
            "gross_profit": m.gross_profit,
            "gross_loss": m.gross_loss,
            "total_realized_pnl": m.total_realized_pnl,
            "profit_factor": m.profit_factor,
            "average_win": m.average_win,
            "average_loss": m.average_loss,
            "largest_win": m.largest_win,
            "largest_loss": m.largest_loss,
            "initial_equity": m.initial_equity,
            "final_equity": m.final_equity,
            "total_return": m.total_return,
            "total_return_pct": m.total_return_pct,
            "open_positions_remaining": m.open_positions_remaining,
            "equity_curve_points": len(m.equity_curve),
            "max_drawdown_pct": m.max_drawdown_pct,
            "max_drawdown_amount": m.max_drawdown_amount,
            "sharpe_ratio": m.sharpe_ratio,
            "metadata": dict(m.metadata),
        }

    def full_report(self) -> dict[str, Any]:
        """
        Every structured view combined into a single dict.

        Returns
        -------
        dict[str, Any]
            ``{"summary": str, "detailed_summary": str,
            "trades": {...}, "metrics": {...}}`` -- a convenience
            aggregate; no new information beyond the other four
            methods.
        """
        return {
            "summary": self.summary(),
            "detailed_summary": self.detailed_summary(),
            "trades": self.trades_summary(),
            "metrics": self.metrics_summary(),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _pct(value: float) -> str:
        """Format a fractional value (e.g. `0.1234`) as `'12.34%'`."""
        return f"{value * 100:.2f}%"

    @staticmethod
    def _trade_to_dict(trade: Trade) -> dict[str, Any]:
        """Build a plain dict view of a single `Trade`."""
        return {
            "trade_id": trade.trade_id,
            "symbol": trade.symbol,
            "side": trade.side.value,
            "price": trade.price,
            "quantity": trade.quantity,
            "executed_at": trade.executed_at,
            "order_id": trade.order_id,
            "fee": trade.fee,
            "fee_asset": trade.fee_asset,
            "is_maker": trade.is_maker,
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"{self.__class__.__name__}(trades={self.metrics.total_trades}, "
            f"win_rate={self.metrics.win_rate:.2%})"
        )
