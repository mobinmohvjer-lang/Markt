"""
portfolio.py
--------------
Purpose:
    Defines the `Portfolio` domain entity: the overall account state,
    combining available cash and all currently tracked positions.

    Like `Position`, this represents evolving state and is therefore
    mutable (not frozen). No calculations are performed here: computing
    `total_equity` from `cash_balance` and `positions` is the
    responsibility of future service/strategy code, not this entity.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from core.entities.position import Position


@dataclass
class Portfolio:
    """
    The overall trading account state at a point in time.

    Attributes:
        portfolio_id: Unique identifier for this portfolio.
        base_currency: Currency/asset used to denominate cash and
            aggregated values (e.g. "USDT").
        cash_balance: Available (uninvested) cash balance.
        positions: All positions currently tracked by this portfolio
            (open and/or closed, depending on how it is populated).
        total_equity: Cash balance plus the value of all positions, if
            already computed elsewhere.
        updated_at: Timestamp of the last update to this snapshot.
    """

    portfolio_id: str
    base_currency: str
    cash_balance: Decimal
    positions: list[Position] = field(default_factory=list)
    total_equity: Decimal | None = None
    updated_at: datetime | None = None
