"""
enums.py
---------
Purpose:
    Defines small, dependency-free enumerations that are part of the
    domain vocabulary (e.g. which side an order/position is on, what
    direction a signal points in). These live in `core` -- not in
    `config` -- because they express business/domain meaning rather than
    application configuration, and `core` must not depend on `config`
    (Dependency Rule: outer layers depend on `core`, never the reverse).

    Timeframe/exchange identifiers (e.g. "1h", "binance") remain plain
    `str` fields on the entities in this package rather than enums here,
    to avoid duplicating `config.config.TimeFrame` / `Exchange`. Those
    configuration-level enums describe *which values the application
    currently supports*, while the domain only needs to know "this is a
    string identifier" -- keeping `core` fully decoupled from `config`.

No implementation, no business logic: enumerations only.
"""

from __future__ import annotations

from enum import Enum


class OrderSide(str, Enum):
    """Direction of an order or executed trade."""

    BUY = "buy"
    SELL = "sell"


class PositionSide(str, Enum):
    """Direction of an open trading position."""

    LONG = "long"
    SHORT = "short"


class PositionStatus(str, Enum):
    """Lifecycle status of a trading position."""

    OPEN = "open"
    CLOSED = "closed"


class SignalDirection(str, Enum):
    """Directional meaning of a trading signal produced by analysis/strategies."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
