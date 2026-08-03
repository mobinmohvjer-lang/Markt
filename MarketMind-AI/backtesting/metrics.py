"""
backtesting/metrics.py

Defines performance-statistics calculations for a completed backtest
run: `BacktestMetrics` (a frozen result container) plus the function
that produces it, `calculate_metrics`, along with the smaller
building-block calculations it composes (`win_rate`, `profit_factor`,
`compute_equity_curve`, `max_drawdown`, `sharpe_ratio`).

This is Backtesting Engine Part 4 -- previously documented in
`backtesting/__init__.py`'s "Planned contents" as `metrics.py`. It
computes performance statistics from an already-produced
`backtesting.result.BacktestResult` (and the `core.entities.portfolio.
Portfolio` the run started from); it does not run a backtest, does not
simulate trades, and does not define trading rules of its own --
`backtesting/` remains a consumer, never a strategy author (see
`PROJECT_RULES.md` Section 1, principle 5).

Reuses only what already exists: `core.entities.portfolio.Portfolio`,
`core.entities.position.Position`, `core.enums.PositionStatus`,
`backtesting.result.BacktestResult`, and
`backtesting.exceptions.BacktestValidationError` -- no new domain
concepts, no new exception types, and no changes to any existing
Backtesting Engine file (`base.py`, `context.py`, `result.py`,
`exceptions.py`, `utils.py`, `basic_backtester.py`,
`portfolio_simulator.py` are all left completely untouched).

Deterministic and side-effect free: no randomness, no wall-clock
reads, no network/database/file I/O, no AI. Never mutates the
`BacktestResult`/`Portfolio` passed in -- every calculation only reads
from them.

Out of scope for this module (see `PROJECT_RULES.md` Section 1,
principle 5 and this milestone's task boundaries):
    - No AI-based assessment of performance.
    - No broker/order-execution integration of any kind.
    - No optimization (parameter search, walk-forward tuning, etc.).
    - No report/chart generation -- `report.py` (human-readable
      summaries) remains a separate, still-pending Backtesting Engine
      milestone; this module only produces numeric statistics.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional

from core.entities.portfolio import Portfolio
from core.entities.position import Position
from core.enums import PositionStatus

from backtesting.exceptions import BacktestValidationError
from backtesting.result import BacktestResult


# ----------------------------------------------------------------------
# Small building-block calculations
# ----------------------------------------------------------------------
def _portfolio_equity(portfolio: Portfolio) -> Decimal:
    """
    Resolve `portfolio`'s total equity.

    Uses `portfolio.total_equity` when it has already been computed
    elsewhere; otherwise falls back to `cash_balance` plus the
    mark-to-market value of every currently open position
    (`quantity * current_price`, falling back to `entry_price` when no
    `current_price` is recorded yet) -- the same
    already-computed-or-fallback convention
    `strategies.risk_management.basic_risk_manager.BasicRiskManager`
    already uses for portfolio exposure.

    Parameters
    ----------
    portfolio : Portfolio

    Returns
    -------
    Decimal
    """
    if portfolio.total_equity is not None:
        return portfolio.total_equity

    equity = portfolio.cash_balance
    for position in portfolio.positions:
        if position.status != PositionStatus.OPEN:
            continue
        price = (
            position.current_price
            if position.current_price is not None
            else position.entry_price
        )
        equity += position.quantity * price
    return equity


def _closed_positions(portfolio: Portfolio) -> list[Position]:
    """
    Return every `Position` in `portfolio.positions` that is closed and
    carries a computed `realized_pnl`, in the order they already
    appear on the portfolio.

    A closed position with `realized_pnl is None` (never computed by
    whatever produced the portfolio) is skipped rather than treated as
    a zero-PnL trade, since "unknown" and "zero" are not the same
    thing.
    """
    return [
        position
        for position in portfolio.positions
        if position.status == PositionStatus.CLOSED and position.realized_pnl is not None
    ]


def win_rate(closed_positions: list[Position]) -> float:
    """
    Fraction of `closed_positions` with a strictly positive `realized_pnl`.

    Parameters
    ----------
    closed_positions : list[Position]

    Returns
    -------
    float
        `0.0` when `closed_positions` is empty (no trades to be right
        or wrong about), otherwise `winning / total`, in `[0.0, 1.0]`.
    """
    if not closed_positions:
        return 0.0
    wins = sum(1 for position in closed_positions if position.realized_pnl > 0)
    return wins / len(closed_positions)


def profit_factor(closed_positions: list[Position]) -> Optional[float]:
    """
    Ratio of gross profit to gross loss across `closed_positions`.

    Parameters
    ----------
    closed_positions : list[Position]

    Returns
    -------
    Optional[float]
        `gross_profit / gross_loss` when there is at least one losing
        trade; `None` when there are no losing trades at all (the
        ratio is undefined/unbounded rather than a real number --
        callers should treat `None` as "no losses to divide by", not
        as zero); `0.0` when there are also no winning trades (nothing
        to compute a ratio from).
    """
    gross_profit = sum(
        (position.realized_pnl for position in closed_positions if position.realized_pnl > 0),
        Decimal("0"),
    )
    gross_loss = sum(
        (-position.realized_pnl for position in closed_positions if position.realized_pnl < 0),
        Decimal("0"),
    )
    if gross_loss == 0:
        return None if gross_profit > 0 else 0.0
    return float(gross_profit / gross_loss)


def compute_equity_curve(
    initial_equity: Decimal, closed_positions: list[Position]
) -> list[Decimal]:
    """
    Build a deterministic equity progression from `initial_equity` and
    the realized PnL of `closed_positions`, taken in the order given.

    This is a simplified proxy for a full mark-to-market equity curve
    (it reflects only the *realized* PnL of each closed position, not
    intra-trade unrealized swings or any position still open at the
    end of the run) -- sufficient for maximum-drawdown and
    Sharpe-ratio calculations without re-simulating the entire trade
    sequence.

    Parameters
    ----------
    initial_equity : Decimal
    closed_positions : list[Position]
        Expected to already be in chronological order (the order
        `Portfolio.positions` was populated in).

    Returns
    -------
    list[Decimal]
        `[initial_equity, initial_equity + pnl_1, initial_equity +
        pnl_1 + pnl_2, ...]` -- always has at least one element.
    """
    curve = [initial_equity]
    running = initial_equity
    for position in closed_positions:
        running = running + position.realized_pnl
        curve.append(running)
    return curve


def max_drawdown(equity_curve: list[Decimal]) -> tuple[float, Decimal]:
    """
    Largest peak-to-trough decline observed in `equity_curve`.

    Parameters
    ----------
    equity_curve : list[Decimal]
        Must be non-empty.

    Returns
    -------
    tuple[float, Decimal]
        `(drawdown_pct, drawdown_amount)`: `drawdown_pct`, in
        `[0.0, 1.0]` for a peak that never goes non-positive, is the
        decline as a fraction of the peak equity at the time it
        occurred (`0.0` when equity never fell below a prior peak, or
        when the relevant peak was not positive so a percentage is
        undefined); `drawdown_amount` is the absolute `Decimal`
        decline.

    Raises
    ------
    BacktestValidationError
        If `equity_curve` is empty.
    """
    if not equity_curve:
        raise BacktestValidationError("equity_curve must not be empty")

    peak = equity_curve[0]
    max_amount = Decimal("0")
    max_pct = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        decline = peak - value
        if decline > max_amount:
            max_amount = decline
            max_pct = float(decline / peak) if peak > 0 else 0.0
    return max_pct, max_amount


def _period_returns(equity_curve: list[Decimal]) -> list[float]:
    """
    Convert `equity_curve` into period-over-period fractional returns,
    skipping any period whose starting equity is not positive (a
    return is undefined when dividing by a non-positive base).
    """
    returns: list[float] = []
    for previous, current in zip(equity_curve, equity_curve[1:]):
        if previous > 0:
            returns.append(float((current - previous) / previous))
    return returns


def sharpe_ratio(
    returns: list[float],
    *,
    risk_free_rate: float = 0.0,
    annualization_factor: float = 1.0,
) -> float:
    """
    Sharpe ratio of a series of period returns.

    Parameters
    ----------
    returns : list[float]
        Period-over-period fractional returns (e.g. from applying
        `_period_returns` to an equity curve).
    risk_free_rate : float, default 0.0
        Per-period risk-free rate subtracted from each return before
        computing the ratio. Left at `0.0` by default since this
        module has no notion of the run's real-world time frequency.
    annualization_factor : float, default 1.0
        Multiplies the raw per-period ratio by
        `sqrt(annualization_factor)`, the standard annualization
        convention. Left at `1.0` (no annualization) by default for
        the same reason.

    Returns
    -------
    float
        `0.0` when fewer than two returns are available, or when the
        sample standard deviation of excess returns is `0.0` (no
        variance to normalize by).
    """
    excess = [value - risk_free_rate for value in returns]
    count = len(excess)
    if count < 2:
        return 0.0
    mean = sum(excess) / count
    variance = sum((value - mean) ** 2 for value in excess) / (count - 1)
    std_dev = math.sqrt(variance)
    if math.isclose(std_dev, 0.0, abs_tol=1e-12):
        return 0.0
    return (mean / std_dev) * math.sqrt(annualization_factor)


# ----------------------------------------------------------------------
# Standardized output
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class BacktestMetrics:
    """
    Standardized performance-statistics output for a single
    `BacktestResult`, evaluated against the `Portfolio` its run
    started from.

    Deliberately a plain data container -- no report formatting, no
    charting, no optimization. Every field is derived purely from
    `BacktestResult.final_portfolio` (via its closed `Position`
    entries) and the supplied starting `Portfolio`.

    Attributes
    ----------
    total_trades : int
        Number of closed positions with a computed `realized_pnl`.
    winning_trades : int
    losing_trades : int
    breakeven_trades : int
        Closed positions with `realized_pnl == 0`.
    win_rate : float
        `winning_trades / total_trades`, `0.0` when there were no
        trades.
    gross_profit : Decimal
    gross_loss : Decimal
        Always `>= 0` (the absolute value of summed losses).
    total_realized_pnl : Decimal
        `gross_profit - gross_loss`.
    profit_factor : Optional[float]
        See `profit_factor()`.
    average_win : Optional[Decimal]
    average_loss : Optional[Decimal]
        `None` when there are no winning/losing trades respectively.
    largest_win : Optional[Decimal]
    largest_loss : Optional[Decimal]
        `None` when there are no winning/losing trades respectively.
    initial_equity : Decimal
    final_equity : Decimal
    total_return : Decimal
        `final_equity - initial_equity`.
    total_return_pct : float
        `total_return / initial_equity`, `0.0` when `initial_equity`
        is not positive.
    open_positions_remaining : int
        Number of positions still open on `final_portfolio`.
    equity_curve : list[Decimal]
        See `compute_equity_curve()`.
    max_drawdown_pct : float
    max_drawdown_amount : Decimal
        See `max_drawdown()`.
    sharpe_ratio : float
        See `sharpe_ratio()`, computed over `equity_curve`'s
        period-over-period returns with the parameters passed to
        `calculate_metrics()`.
    metadata : dict[str, Any]
        Free-form supporting detail for traceability (e.g. how many
        closed/open positions were used, which parameters were
        applied), mirroring every other engine's `metadata`
        convention in this repository.
    """

    total_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: float
    gross_profit: Decimal
    gross_loss: Decimal
    total_realized_pnl: Decimal
    profit_factor: Optional[float]
    average_win: Optional[Decimal]
    average_loss: Optional[Decimal]
    largest_win: Optional[Decimal]
    largest_loss: Optional[Decimal]
    initial_equity: Decimal
    final_equity: Decimal
    total_return: Decimal
    total_return_pct: float
    open_positions_remaining: int
    equity_curve: list[Decimal] = field(default_factory=list)
    max_drawdown_pct: float = 0.0
    max_drawdown_amount: Decimal = Decimal("0")
    sharpe_ratio: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


def calculate_metrics(
    result: BacktestResult,
    initial_portfolio: Portfolio,
    *,
    risk_free_rate: float = 0.0,
    annualization_factor: float = 1.0,
) -> BacktestMetrics:
    """
    Compute `BacktestMetrics` for a completed backtest run.

    Parameters
    ----------
    result : BacktestResult
        The already-produced output of some `BaseBacktester.run()`
        call. Never mutated.
    initial_portfolio : Portfolio
        The `Portfolio` the run started from (typically the same
        `BacktestContext.initial_portfolio` supplied to that run) --
        used to establish the baseline for `total_return`/the equity
        curve. Never mutated.
    risk_free_rate : float, default 0.0
        Forwarded to `sharpe_ratio()`.
    annualization_factor : float, default 1.0
        Forwarded to `sharpe_ratio()`.

    Returns
    -------
    BacktestMetrics

    Raises
    ------
    BacktestValidationError
        If `result` is not a `BacktestResult`, or `initial_portfolio`
        is not a `Portfolio`.
    """
    if not isinstance(result, BacktestResult):
        raise BacktestValidationError(
            f"result must be a BacktestResult, got {type(result).__name__}"
        )
    if not isinstance(initial_portfolio, Portfolio):
        raise BacktestValidationError(
            f"initial_portfolio must be a Portfolio, got {type(initial_portfolio).__name__}"
        )

    final_portfolio = result.final_portfolio
    closed = _closed_positions(final_portfolio)

    winning = [position for position in closed if position.realized_pnl > 0]
    losing = [position for position in closed if position.realized_pnl < 0]
    breakeven = [position for position in closed if position.realized_pnl == 0]

    gross_profit = sum((position.realized_pnl for position in winning), Decimal("0"))
    gross_loss = sum((-position.realized_pnl for position in losing), Decimal("0"))
    total_realized_pnl = gross_profit - gross_loss

    average_win = (gross_profit / len(winning)) if winning else None
    average_loss = (gross_loss / len(losing)) if losing else None
    largest_win = max((position.realized_pnl for position in winning), default=None)
    largest_loss = min((position.realized_pnl for position in losing), default=None)

    initial_equity = _portfolio_equity(initial_portfolio)
    final_equity = _portfolio_equity(final_portfolio)
    total_return = final_equity - initial_equity
    total_return_pct = (
        float(total_return / initial_equity) if initial_equity > 0 else 0.0
    )

    open_positions_remaining = sum(
        1 for position in final_portfolio.positions if position.status == PositionStatus.OPEN
    )

    equity_curve = compute_equity_curve(initial_equity, closed)
    drawdown_pct, drawdown_amount = max_drawdown(equity_curve)
    returns = _period_returns(equity_curve)
    sharpe = sharpe_ratio(
        returns, risk_free_rate=risk_free_rate, annualization_factor=annualization_factor
    )

    return BacktestMetrics(
        total_trades=len(closed),
        winning_trades=len(winning),
        losing_trades=len(losing),
        breakeven_trades=len(breakeven),
        win_rate=win_rate(closed),
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        total_realized_pnl=total_realized_pnl,
        profit_factor=profit_factor(closed),
        average_win=average_win,
        average_loss=average_loss,
        largest_win=largest_win,
        largest_loss=largest_loss,
        initial_equity=initial_equity,
        final_equity=final_equity,
        total_return=total_return,
        total_return_pct=total_return_pct,
        open_positions_remaining=open_positions_remaining,
        equity_curve=equity_curve,
        max_drawdown_pct=drawdown_pct,
        max_drawdown_amount=drawdown_amount,
        sharpe_ratio=sharpe,
        metadata={
            "closed_position_count": len(closed),
            "open_position_count": open_positions_remaining,
            "equity_curve_points": len(equity_curve),
            "risk_free_rate": risk_free_rate,
            "annualization_factor": annualization_factor,
        },
    )
