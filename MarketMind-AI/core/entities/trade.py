"""
trade.py
---------
Purpose:
    Defines the `Trade` domain entity: a single executed trade.

    This entity is intentionally general enough to represent both:
      1. A public market trade (an entry on the exchange's trade tape),
         used e.g. inside `MarketState.recent_trades`.
      2. The user's own executed fill, used when building/updating a
         `Position` or `Portfolio`.

    The fee-related and `order_id` fields are optional precisely because
    they are only meaningful for the user's own fills, not for public
    market trades.

    Pure data container -- no execution, no fetching, no calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from core.enums import OrderSide


@dataclass(frozen=True)
class Trade:
    """
    A single executed trade.

    Attributes:
        trade_id: Unique identifier for this trade (exchange-assigned
            or internally generated).
        symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").
        side: Direction of the trade (buy or sell).
        price: Execution price.
        quantity: Executed quantity (base asset).
        executed_at: Timestamp when the trade was executed.
        order_id: Identifier of the order that produced this trade, if
            this trade represents the user's own fill.
        fee: Fee charged for this trade, if this trade represents the
            user's own fill.
        fee_asset: Asset in which the fee was charged, if applicable.
        is_maker: Whether this fill was on the maker side, if known.
    """

    trade_id: str
    symbol: str
    side: OrderSide
    price: Decimal
    quantity: Decimal
    executed_at: datetime
    order_id: str | None = None
    fee: Decimal | None = None
    fee_asset: str | None = None
    is_maker: bool | None = None
