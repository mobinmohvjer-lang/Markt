"""
strategies/risk_management package
-------------------------------------
Purpose:
    The Risk Engine: evaluates whether a candidate `core.entities.
    signal.Signal` is safe to act on against the current
    `core.entities.portfolio.Portfolio`, standardizing that evaluation
    into a single `RiskResult`. Mirrors the role `analysis/` plays for
    raw market/news data and `signals/` plays for `AnalysisResult`s:
    each layer interprets/standardizes its predecessor's output without
    deciding what to do about it.

Contents (Risk Engine Part 1 -- foundation):
    - `BaseRiskManager` (`base.py`): abstract base every concrete risk
      manager implements.
    - `RiskContext` (`context.py`): immutable bundle of a candidate
      `Signal`, the current `Portfolio`, and optional `MarketState` for
      one symbol/timeframe.
    - `RiskResult` (`result.py`): standardized output --
      `approved`/`risk_score`/`confidence`/`summary`/`metadata`.
    - `RiskError` hierarchy (`exceptions.py`).
    - Shared validation helpers (`utils.py`).

Also contains (Risk Engine Part 2 -- first concrete implementation):
    - `BasicRiskManager` (`basic_risk_manager.py`): the first concrete
      `BaseRiskManager`. Evaluates signal confidence, an optional
      signal-strength value (read defensively from `Signal.metadata`,
      since `Signal` itself has no `strength` field), portfolio
      exposure (derived from `RiskContext.portfolio`), and market-data
      availability (`RiskContext.has_market_state()`) into one
      `risk_score`/`approved` decision, with every intermediate value
      recorded in `RiskResult.metadata` for traceability.

Also contains (Risk Engine Part 3 -- position sizing / protective
levels, three independent concrete `BaseRiskManager` implementations,
none of which import or depend on each other or on `BasicRiskManager`):
    - `PositionSizeRule` (`position_size_rule.py`): recommends a
      position size via fixed-fractional risk sizing (portfolio equity
      x a configurable `risk_per_trade`, divided by a per-unit risk
      distance estimated from ATR when available or a configurable
      percentage fallback otherwise, capped at a configurable
      `max_position_fraction` of equity). Reports both a quote-currency
      `recommended_position_value` and, when a reference price is
      available, a base-asset `recommended_position_size` in
      `RiskResult.metadata`.
    - `StopLossRule` (`stop_loss_rule.py`): computes a direction-aware
      stop-loss price (below the reference price for `BUY`, above it
      for `SELL`) from the same ATR-or-percentage distance estimate,
      clamped to a configurable `[min_stop_distance_pct,
      max_stop_distance_pct]` range.
    - `TakeProfitRule` (`take_profit_rule.py`): computes a
      direction-aware take-profit price the same way, scaled by a
      configurable `risk_reward_ratio` against its own independently
      estimated base risk-leg distance (it does not consume
      `StopLossRule`'s output).

  All three: consume only `RiskContext`/existing `core.entities`,
  produce only `RiskResult` (no new fields -- computed prices/sizes
  live in `metadata`), treat a `SignalDirection.HOLD` signal as
  "not applicable" rather than an error, and treat missing *optional*
  data (ATR, in all three; a resolvable reference price, in
  `PositionSizeRule` only) as a reason to fall back and lower
  `confidence`, never to raise. Each raises `InsufficientRiskDataError`
  only when a truly required input is unusable: an unusable
  `signal.confidence` (all three), non-positive portfolio equity
  (`PositionSizeRule`), or a completely unresolvable reference price
  (`StopLossRule`/`TakeProfitRule`, which -- unlike `PositionSizeRule`
  -- cannot express a price-based result without one at all).

Explicitly out of scope for all three parts (deferred to
`strategies/`'s own trading-decision logic and/or order-execution
layer):
    - Order execution / actually placing an order.
    - Strategy/trading decisions (which signal to act on at all).
    - AI-based risk assessment.
    - Writing computed values back onto `core.entities.position.
      Position.stop_loss`/`take_profit` -- that remains the
      responsibility of whatever later component acts on a
      `RiskResult`.

Planned contents (future Risk Engine parts / `strategies/`):
    - Additional concrete `BaseRiskManager` implementations (e.g.
      drawdown checks, volatility-based risk).
    - An optional composite/aggregating risk manager combining several
      concrete risk managers, mirroring `SignalAggregator`'s role over
      multiple signal generators.
    - portfolio_management/: allocation logic across multiple assets.
"""

from __future__ import annotations

from strategies.risk_management.base import BaseRiskManager
from strategies.risk_management.basic_risk_manager import BasicRiskManager
from strategies.risk_management.context import RiskContext
from strategies.risk_management.exceptions import (
    InsufficientRiskDataError,
    InvalidRiskContextError,
    RiskError,
    RiskManagerConfigurationError,
    RiskValidationError,
)
from strategies.risk_management.position_size_rule import PositionSizeRule
from strategies.risk_management.result import RiskResult
from strategies.risk_management.stop_loss_rule import StopLossRule
from strategies.risk_management.take_profit_rule import TakeProfitRule

__all__ = [
    "BaseRiskManager",
    "BasicRiskManager",
    "PositionSizeRule",
    "StopLossRule",
    "TakeProfitRule",
    "RiskContext",
    "RiskResult",
    "RiskError",
    "RiskValidationError",
    "InvalidRiskContextError",
    "InsufficientRiskDataError",
    "RiskManagerConfigurationError",
]
