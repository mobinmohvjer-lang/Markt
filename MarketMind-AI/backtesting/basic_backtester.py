"""
backtesting/basic_backtester.py

Defines `BasicBacktester`, the first concrete `BaseBacktester`
implementation (Backtesting Engine Part 2), built entirely on Part 1's
foundation (`BaseBacktester`, `BacktestContext`, `BacktestResult`, the
`BacktestError` hierarchy, `backtesting.utils`).

`BasicBacktester` replays `BacktestContext.candles` sequentially, oldest
to newest, against `BacktestContext.strategy` (any `BaseStrategy`
instance). For each candle it builds a minimal `strategies.context.
StrategyContext` for the context's symbol/timeframe -- carrying no
`AnalysisResult`/`SignalResult`/`RiskResult` of its own (`backtesting`
does not depend on `analysis`/produce signals -- see the dependency
table in `PROJECT_RULES.md` Section 4) and exposing the current candle
only via `StrategyContext.metadata` for traceability/strategy use --
and calls `context.strategy.decide(...)`. `BasicBacktester` consumes
only the resulting `strategies.result.StrategyResult.action`
(`core.enums.SignalDirection.BUY`/`SELL`/`HOLD`); it never inspects any
`AnalysisResult`/`SignalResult`/`RiskResult` directly and never decides
*why* to buy or sell -- that reasoning belongs entirely to the injected
strategy (`PROJECT_RULES.md` Section 1, principle 5: "Backtesting is a
consumer, never a strategy author").

Execution model:

    - `BUY` while no open position is held on `context.symbol`: spend
      up to `max_position_fraction` of the current cash balance
      (configurable at construction time, default `0.25`) to open one
      long `Position` at the candle's `close` price, and record one
      `Trade`. Remaining cash is kept as cash, not deployed. A `BUY`
      while a position is already open, or with zero/negative cash
      available, is a no-op (no pyramiding, no margin/leverage).
      When `stop_loss_pct`/`take_profit_pct` are configured (defaults:
      `stop_loss_pct=0.05`, `take_profit_pct=None`), the opened
      `Position.stop_loss`/`Position.take_profit` fields are populated
      from the entry price.
    - Every candle, *before* the strategy is even consulted, any open
      position's `stop_loss`/`take_profit` is checked against that
      candle's `low`/`high`. If triggered, the position is closed
      immediately at the stop/take-profit price. This check is fully
      independent of the strategy's `SELL` signal -- it fires whether
      the strategy says `BUY`, `SELL`, or `HOLD` for that candle, and
      even when the strategy raises `InsufficientStrategyDataError`.
    - `SELL` while an open position is held on `context.symbol` (and
      was not already closed by a stop-loss/take-profit trigger this
      same candle): close the entire position at the candle's `close`
      price, credit the proceeds back to cash, and record one `Trade`.
      A `SELL` with no open position is a no-op.
    - `HOLD` is always a no-op.

No slippage, no commissions/fees, and no leverage are modeled (trades
always fill exactly at the candle's `close` price -- or, for a
stop-loss/take-profit trigger, at that trigger price -- for the
position's full quantity, using only cash already on hand) -- those,
along with performance statistics (Sharpe ratio, max drawdown, win
rate, profit factor) and any cross-run aggregation, remain out of
scope for this part and belong to later Backtesting Engine parts (see
`backtesting/__init__.py`'s "Planned contents").

A strategy raising `strategies.exceptions.InsufficientStrategyDataError`
for a given candle is treated the same way every other engine in this
repository treats a per-item "unavailable" result: that candle is
skipped (no trade, `metadata["skipped_candles"]` records the count) and
replay continues with the next candle -- it never aborts the whole run.
Note that the stop-loss/take-profit check above still runs for a
skipped candle; only the strategy-driven BUY/SELL decision is skipped.
Any other exception raised by the strategy propagates unchanged, since
that indicates a genuine bug in the injected strategy, not an ordinary
"insufficient data" outcome.

Fully deterministic -- no randomness, no wall-clock reads, no network/
database I/O, no AI. Never mutates `context` or anything reachable from
it: `context.initial_portfolio` is copied before any positions/cash are
touched, and `context.candles` (a `list` of frozen `Candle` instances)
is only ever read, never written to.
"""

from __future__ import annotations

import copy
from decimal import Decimal
from typing import Optional

from core.entities.candle import Candle
from core.entities.portfolio import Portfolio
from core.entities.position import Position
from core.entities.trade import Trade
from core.enums import OrderSide, PositionSide, PositionStatus, SignalDirection

from strategies.context import StrategyContext
from strategies.exceptions import InsufficientStrategyDataError

from backtesting.base import BaseBacktester
from backtesting.context import BacktestContext
from backtesting.exceptions import BacktestValidationError, InsufficientBacktestDataError
from backtesting.result import BacktestResult
from backtesting.utils import merge_metadata

#: Default fraction of current cash spent on a single BUY (matches
#: `strategies.risk_management.position_size_rule.
#: DEFAULT_MAX_POSITION_FRACTION`'s own default, so both modules agree
#: on what a sane "don't bet the whole account" cap looks like).
DEFAULT_MAX_POSITION_FRACTION = 0.25

#: Default stop-loss distance, as a fraction of entry price, applied to
#: every new long position when the caller doesn't override it. `None`
#: would disable stop-loss handling entirely; a concrete default is
#: used here so the engine's own drawdown protection is "on" unless a
#: caller deliberately opts out.
DEFAULT_STOP_LOSS_PCT = 0.05

#: No take-profit cap is imposed by default -- winners are left to run
#: unless a caller explicitly configures one.
DEFAULT_TAKE_PROFIT_PCT: Optional[float] = None


class BasicBacktester(BaseBacktester):
    """
    The first concrete `BaseBacktester`: a straightforward, deterministic
    sequential replay of one strategy against one candle series.

    Consumes only `strategies.result.StrategyResult.action` from the
    injected `BacktestContext.strategy` -- no strategy-authored risk
    management, no portfolio optimization, no leverage, no slippage, no
    commissions, and no performance-metric calculation (Sharpe ratio,
    max drawdown, win rate, profit factor, etc.) are performed here.
    This class *does* own basic position-sizing (`max_position_fraction`)
    and stop-loss/take-profit enforcement (`stop_loss_pct`/
    `take_profit_pct`), since both are properties of how the engine
    fills/exits orders, not of strategy signal generation -- see the
    module docstring for the exact execution model and
    `backtesting/__init__.py`'s "Planned contents" for what still
    belongs to later Backtesting Engine parts.

    Attributes
    ----------
    max_position_fraction : float
        Fraction of current cash balance (0.0, 1.0] spent on a single
        BUY. Never 1.0 by default -- see `DEFAULT_MAX_POSITION_FRACTION`.
    stop_loss_pct : float or None
        Fractional distance below entry price, in (0.0, 1.0), at which
        a new long position's `Position.stop_loss` is set. `None`
        disables stop-loss handling for newly opened positions.
    take_profit_pct : float or None
        Fractional distance above entry price, in (0.0, 1.0), at which
        a new long position's `Position.take_profit` is set. `None`
        disables take-profit handling for newly opened positions.
    """

    def __init__(
        self,
        *,
        max_position_fraction: float = DEFAULT_MAX_POSITION_FRACTION,
        stop_loss_pct: Optional[float] = DEFAULT_STOP_LOSS_PCT,
        take_profit_pct: Optional[float] = DEFAULT_TAKE_PROFIT_PCT,
    ) -> None:
        """
        Parameters
        ----------
        max_position_fraction : float, default 0.25
            Fraction of current cash balance to spend on each BUY.
            Must be within (0.0, 1.0]. `1.0` reproduces the old
            "spend everything" behavior; anything less caps exposure
            per trade.
        stop_loss_pct : float or None, default 0.05
            Fractional stop-loss distance below entry price applied to
            every newly opened position. Must be within (0.0, 1.0)
            when given. Pass `None` to disable stop-loss handling.
        take_profit_pct : float or None, default None
            Fractional take-profit distance above entry price applied
            to every newly opened position. Must be within (0.0, 1.0)
            when given. `None` (the default) disables take-profit
            handling.

        Raises
        ------
        BacktestValidationError
            If any of the above are out of their valid range or of the
            wrong type.
        """
        super().__init__()
        self.max_position_fraction = self._validate_fraction(
            max_position_fraction, name="max_position_fraction"
        )
        self.stop_loss_pct = self._validate_optional_fraction(
            stop_loss_pct, name="stop_loss_pct"
        )
        self.take_profit_pct = self._validate_optional_fraction(
            take_profit_pct, name="take_profit_pct"
        )

    def run(self, context: BacktestContext) -> BacktestResult:
        """
        Replay `context.candles` through `context.strategy`, sequentially
        and chronologically, and return the resulting `BacktestResult`.

        Parameters
        ----------
        context : BacktestContext
            The historical candles, strategy, and starting portfolio to
            replay. Never mutated by this call.

        Returns
        -------
        BacktestResult
            The final portfolio state, recorded trades, a human-readable
            summary, and traceability `metadata`.

        Raises
        ------
        InvalidBacktestContextError
            If `context` is not a `BacktestContext` instance (via
            `self.validate_context`).
        InsufficientBacktestDataError
            If `context` carries no candles to replay. In practice this
            cannot happen for an already-constructed `BacktestContext`
            (its own validation already rejects an empty candle list),
            but this check is kept as a defensive, self-contained
            guarantee of this method's own documented contract.
        """
        self.validate_context(context)

        if not context.candles:
            raise InsufficientBacktestDataError(
                f"{self.name} requires at least one candle to replay, got none"
            )

        # Never mutate the caller's starting portfolio -- work on a deep
        # copy for the whole run instead.
        portfolio = copy.deepcopy(context.initial_portfolio)
        trades: list[Trade] = []
        skipped_candles = 0
        trade_sequence = 0
        stop_loss_triggers = 0
        take_profit_triggers = 0

        for index, candle in enumerate(context.candles):
            # Stop-loss/take-profit is checked every candle, independent
            # of whatever the strategy decides (or whether it can decide
            # at all this candle) -- see the module docstring.
            open_position = self._find_open_position(portfolio, context.symbol)
            if open_position is not None:
                trade_sequence, exit_reason = self._check_stop_loss_take_profit(
                    portfolio=portfolio,
                    position=open_position,
                    candle=candle,
                    trades=trades,
                    trade_sequence=trade_sequence,
                )
                if exit_reason == "stop_loss":
                    stop_loss_triggers += 1
                elif exit_reason == "take_profit":
                    take_profit_triggers += 1

            strategy_context = StrategyContext(
                symbol=context.symbol,
                timeframe=context.timeframe,
                metadata={"candle": candle, "candle_index": index},
            )

            try:
                decision = context.strategy.decide(strategy_context)
            except InsufficientStrategyDataError:
                skipped_candles += 1
                continue

            # Re-fetch: the stop-loss/take-profit check above may have
            # already closed this candle's open position.
            open_position = self._find_open_position(portfolio, context.symbol)

            if decision.action == SignalDirection.BUY and open_position is None:
                trade_sequence = self._open_position(
                    portfolio=portfolio,
                    symbol=context.symbol,
                    candle=candle,
                    trades=trades,
                    trade_sequence=trade_sequence,
                )
            elif decision.action == SignalDirection.SELL and open_position is not None:
                trade_sequence = self._close_position(
                    portfolio=portfolio,
                    position=open_position,
                    price=candle.close,
                    closed_at=candle.close_time,
                    trades=trades,
                    trade_sequence=trade_sequence,
                    trade_id_suffix="sell",
                )
            # SignalDirection.HOLD, or a BUY/SELL that does not apply
            # given current position state, is always a no-op.

        portfolio.updated_at = context.candles[-1].close_time

        summary = self._build_summary(
            context=context,
            trades=trades,
            skipped_candles=skipped_candles,
            final_portfolio=portfolio,
            stop_loss_triggers=stop_loss_triggers,
            take_profit_triggers=take_profit_triggers,
        )
        metadata = merge_metadata(
            context.metadata,
            {
                "backtester": self.name,
                "strategy_name": context.strategy.name,
                "symbol": context.symbol,
                "timeframe": context.timeframe,
                "candles_replayed": len(context.candles),
                "skipped_candles": skipped_candles,
                "trades_executed": len(trades),
                "open_positions_remaining": sum(
                    1 for p in portfolio.positions if p.status == PositionStatus.OPEN
                ),
                "stop_loss_triggers": stop_loss_triggers,
                "take_profit_triggers": take_profit_triggers,
                "max_position_fraction": self.max_position_fraction,
                "stop_loss_pct": self.stop_loss_pct,
                "take_profit_pct": self.take_profit_pct,
            },
        )

        return self._build_result(
            final_portfolio=portfolio,
            summary=summary,
            trades=trades,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Construction-time validation
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_fraction(value: object, *, name: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BacktestValidationError(
                f"{name} must be numeric, got {type(value).__name__}"
            )
        numeric_value = float(value)
        if not (0.0 < numeric_value <= 1.0):
            raise BacktestValidationError(
                f"{name} must be within (0.0, 1.0], got {numeric_value}"
            )
        return numeric_value

    @staticmethod
    def _validate_optional_fraction(value: Optional[object], *, name: str) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BacktestValidationError(
                f"{name} must be numeric or None, got {type(value).__name__}"
            )
        numeric_value = float(value)
        if not (0.0 < numeric_value < 1.0):
            raise BacktestValidationError(
                f"{name} must be within (0.0, 1.0), got {numeric_value}"
            )
        return numeric_value

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _find_open_position(portfolio: Portfolio, symbol: str) -> Optional[Position]:
        """Return the first open `Position` on `symbol`, or `None`."""
        for position in portfolio.positions:
            if position.symbol == symbol and position.status == PositionStatus.OPEN:
                return position
        return None

    def _open_position(
        self,
        *,
        portfolio: Portfolio,
        symbol: str,
        candle: Candle,
        trades: list[Trade],
        trade_sequence: int,
    ) -> int:
        """
        Open one long `Position` on `symbol` at `candle.close`, sizing
        it to `self.max_position_fraction` of the current cash balance
        (rather than the entire balance), and record the corresponding
        `Trade`. A no-op (returns `trade_sequence` unchanged) when there
        is no positive cash available to spend.

        When `self.stop_loss_pct`/`self.take_profit_pct` are configured,
        the resulting `Position.stop_loss`/`Position.take_profit` are
        populated from the entry price.

        Returns the updated `trade_sequence` counter.
        """
        if portfolio.cash_balance <= 0:
            return trade_sequence

        price = candle.close
        allocation = portfolio.cash_balance * Decimal(str(self.max_position_fraction))
        if allocation <= 0:
            return trade_sequence

        quantity = allocation / price
        trade_sequence += 1

        stop_loss: Optional[Decimal] = None
        if self.stop_loss_pct is not None:
            stop_loss = price * (Decimal("1") - Decimal(str(self.stop_loss_pct)))

        take_profit: Optional[Decimal] = None
        if self.take_profit_pct is not None:
            take_profit = price * (Decimal("1") + Decimal(str(self.take_profit_pct)))

        position = Position(
            position_id=f"{symbol}-{trade_sequence}",
            symbol=symbol,
            side=PositionSide.LONG,
            entry_price=price,
            quantity=quantity,
            opened_at=candle.open_time,
            status=PositionStatus.OPEN,
            current_price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        portfolio.positions.append(position)
        portfolio.cash_balance -= allocation

        trades.append(
            Trade(
                trade_id=f"{symbol}-{trade_sequence}-buy",
                symbol=symbol,
                side=OrderSide.BUY,
                price=price,
                quantity=quantity,
                executed_at=candle.close_time,
            )
        )
        return trade_sequence

    @staticmethod
    def _close_position(
        *,
        portfolio: Portfolio,
        position: Position,
        price: Decimal,
        closed_at,
        trades: list[Trade],
        trade_sequence: int,
        trade_id_suffix: str = "sell",
    ) -> int:
        """
        Close `position` in full at `price` (the candle's `close` for a
        strategy-driven SELL, or the stop-loss/take-profit trigger
        price for a risk-driven exit), credit the proceeds back to
        `portfolio.cash_balance`, and record the corresponding `Trade`.

        Returns the updated `trade_sequence` counter.
        """
        quantity = position.quantity
        proceeds = quantity * price

        position.current_price = price
        position.realized_pnl = (price - position.entry_price) * quantity
        position.status = PositionStatus.CLOSED
        position.closed_at = closed_at

        portfolio.cash_balance += proceeds
        trade_sequence += 1

        trades.append(
            Trade(
                trade_id=f"{position.symbol}-{trade_sequence}-{trade_id_suffix}",
                symbol=position.symbol,
                side=OrderSide.SELL,
                price=price,
                quantity=quantity,
                executed_at=closed_at,
            )
        )
        return trade_sequence

    @staticmethod
    def _check_stop_loss_take_profit(
        *,
        portfolio: Portfolio,
        position: Position,
        candle: Candle,
        trades: list[Trade],
        trade_sequence: int,
    ) -> tuple[int, Optional[str]]:
        """
        Check whether `candle` triggers `position.stop_loss`/
        `position.take_profit`, independent of any strategy signal, and
        close the position immediately if so.

        Stop-loss is checked before take-profit when both could
        plausibly trigger within the same candle (a conservative
        assumption: `candle.low` at/below `stop_loss` and `candle.high`
        at/above `take_profit` in the same bar). Long-only, matching
        this engine's own execution model.

        Returns
        -------
        tuple[int, str or None]
            The updated `trade_sequence` counter, and one of
            `"stop_loss"`, `"take_profit"`, or `None` (no trigger).
        """
        if position.stop_loss is not None and candle.low <= position.stop_loss:
            trade_sequence = BasicBacktester._close_position(
                portfolio=portfolio,
                position=position,
                price=position.stop_loss,
                closed_at=candle.close_time,
                trades=trades,
                trade_sequence=trade_sequence,
                trade_id_suffix="stop_loss",
            )
            return trade_sequence, "stop_loss"

        if position.take_profit is not None and candle.high >= position.take_profit:
            trade_sequence = BasicBacktester._close_position(
                portfolio=portfolio,
                position=position,
                price=position.take_profit,
                closed_at=candle.close_time,
                trades=trades,
                trade_sequence=trade_sequence,
                trade_id_suffix="take_profit",
            )
            return trade_sequence, "take_profit"

        return trade_sequence, None

    @staticmethod
    def _build_summary(
        *,
        context: BacktestContext,
        trades: list[Trade],
        skipped_candles: int,
        final_portfolio: Portfolio,
        stop_loss_triggers: int,
        take_profit_triggers: int,
    ) -> str:
        """Build a short, human-readable summary of the completed run."""
        open_count = sum(1 for p in final_portfolio.positions if p.status == PositionStatus.OPEN)
        parts = [
            f"Replayed {len(context.candles)} candle(s) for "
            f"{context.symbol}/{context.timeframe} using strategy "
            f"'{context.strategy.name}': executed {len(trades)} trade(s), "
            f"ending with {open_count} open position(s) and cash balance "
            f"{final_portfolio.cash_balance}.",
        ]
        if skipped_candles:
            parts.append(
                f"{skipped_candles} candle(s) were skipped because the "
                f"strategy raised InsufficientStrategyDataError."
            )
        if stop_loss_triggers or take_profit_triggers:
            parts.append(
                f"{stop_loss_triggers} stop-loss trigger(s) and "
                f"{take_profit_triggers} take-profit trigger(s) closed "
                f"positions independently of the strategy's own SELL signal."
            )
        return " ".join(parts)
