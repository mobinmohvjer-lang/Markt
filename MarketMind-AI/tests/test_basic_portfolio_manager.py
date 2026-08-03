"""
test_basic_portfolio_manager.py
-----------------------------------
Purpose:
    Unit tests for `BasicPortfolioManager` (Portfolio Management Part
    2), the first concrete `strategies.portfolio_management.base.
    BasePortfolioManager` implementation. Complements `tests/
    test_portfolio_management.py`, which covers the Part 1 foundation
    (`PortfolioResult`, `PortfolioContext`, `BasePortfolioManager`,
    exceptions, utils) and is left untouched here.

Uses the standard-library ``unittest`` framework, matching every other
test file in this suite (no external test-runner dependency).

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal

from core.entities.portfolio import Portfolio
from core.entities.position import Position
from core.enums import PositionSide, PositionStatus, SignalDirection

from strategies.portfolio_management import (
    BasePortfolioManager,
    BasicPortfolioManager,
    InsufficientPortfolioDataError,
    InvalidPortfolioContextError,
    PortfolioContext,
    PortfolioManagerConfigurationError,
    PortfolioResult,
)
from strategies.result import StrategyResult
from strategies.risk_management.result import RiskResult

NOW = datetime.now(timezone.utc)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
def make_position(
    *,
    symbol: str = "BTCUSDT",
    quantity: Decimal = Decimal("1"),
    entry_price: Decimal = Decimal("100"),
    current_price: Decimal | None = Decimal("100"),
    status: PositionStatus = PositionStatus.OPEN,
) -> Position:
    return Position(
        position_id="pos-1",
        symbol=symbol,
        side=PositionSide.LONG,
        entry_price=entry_price,
        quantity=quantity,
        opened_at=NOW,
        status=status,
        current_price=current_price,
    )


def make_portfolio(
    *,
    cash_balance: Decimal = Decimal("10000"),
    positions: list[Position] | None = None,
    total_equity: Decimal | None = None,
) -> Portfolio:
    return Portfolio(
        portfolio_id="portfolio-1",
        base_currency="USDT",
        cash_balance=cash_balance,
        positions=positions or [],
        total_equity=total_equity,
    )


def make_strategy_result(
    *, action: SignalDirection = SignalDirection.BUY, confidence: float = 0.7
) -> StrategyResult:
    return StrategyResult(
        action=action,
        confidence=confidence,
        summary="Directional decision from analysis/signal inputs",
    )


def make_risk_result(*, approved: bool = True, confidence: float = 0.8) -> RiskResult:
    return RiskResult(
        approved=approved,
        risk_score=0.2,
        confidence=confidence,
        summary="Signal within acceptable risk tolerance",
    )


def make_context(
    *,
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
    portfolio: Portfolio | None = None,
    strategy_result: StrategyResult | None = None,
    risk_result: RiskResult | None = None,
) -> PortfolioContext:
    return PortfolioContext(
        symbol=symbol,
        timeframe=timeframe,
        portfolio=portfolio if portfolio is not None else make_portfolio(),
        strategy_result=strategy_result,
        risk_result=risk_result,
    )


# ----------------------------------------------------------------------
# Construction
# ----------------------------------------------------------------------
class TestBasicPortfolioManagerConstruction(unittest.TestCase):
    def test_is_a_base_portfolio_manager(self):
        manager = BasicPortfolioManager()
        self.assertIsInstance(manager, BasePortfolioManager)

    def test_default_name_is_class_name(self):
        manager = BasicPortfolioManager()
        self.assertEqual(manager.name, "BasicPortfolioManager")

    def test_custom_name(self):
        manager = BasicPortfolioManager(name="my-manager")
        self.assertEqual(manager.name, "my-manager")

    def test_default_limits(self):
        manager = BasicPortfolioManager()
        self.assertEqual(manager.max_open_positions, 10)
        self.assertEqual(manager.max_exposure_ratio, 0.8)
        self.assertEqual(manager.max_symbol_exposure_ratio, 0.25)
        self.assertTrue(manager.require_risk_approval)
        self.assertTrue(manager.block_on_hold_action)

    def test_custom_limits(self):
        manager = BasicPortfolioManager(
            max_open_positions=3,
            max_exposure_ratio=0.5,
            max_symbol_exposure_ratio=0.1,
            require_risk_approval=False,
            block_on_hold_action=False,
        )
        self.assertEqual(manager.max_open_positions, 3)
        self.assertEqual(manager.max_exposure_ratio, 0.5)
        self.assertEqual(manager.max_symbol_exposure_ratio, 0.1)
        self.assertFalse(manager.require_risk_approval)
        self.assertFalse(manager.block_on_hold_action)

    def test_rejects_non_int_max_open_positions(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            BasicPortfolioManager(max_open_positions=3.5)  # type: ignore[arg-type]

    def test_rejects_bool_max_open_positions(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            BasicPortfolioManager(max_open_positions=True)  # type: ignore[arg-type]

    def test_rejects_zero_max_open_positions(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            BasicPortfolioManager(max_open_positions=0)

    def test_rejects_negative_max_open_positions(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            BasicPortfolioManager(max_open_positions=-1)

    def test_rejects_non_numeric_max_exposure_ratio(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            BasicPortfolioManager(max_exposure_ratio="high")  # type: ignore[arg-type]

    def test_rejects_zero_max_exposure_ratio(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            BasicPortfolioManager(max_exposure_ratio=0.0)

    def test_rejects_negative_max_exposure_ratio(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            BasicPortfolioManager(max_exposure_ratio=-0.1)

    def test_rejects_non_finite_max_exposure_ratio(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            BasicPortfolioManager(max_exposure_ratio=float("nan"))

    def test_rejects_zero_max_symbol_exposure_ratio(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            BasicPortfolioManager(max_symbol_exposure_ratio=0.0)

    def test_rejects_non_bool_require_risk_approval(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            BasicPortfolioManager(require_risk_approval="yes")  # type: ignore[arg-type]

    def test_rejects_non_bool_block_on_hold_action(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            BasicPortfolioManager(block_on_hold_action="yes")  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Context validation (inherited from BasePortfolioManager)
# ----------------------------------------------------------------------
class TestBasicPortfolioManagerContextValidation(unittest.TestCase):
    def test_rejects_non_portfolio_context(self):
        manager = BasicPortfolioManager()
        with self.assertRaises(InvalidPortfolioContextError):
            manager.evaluate("not-a-context")  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Output shape
# ----------------------------------------------------------------------
class TestBasicPortfolioManagerOutputShape(unittest.TestCase):
    def test_returns_portfolio_result(self):
        manager = BasicPortfolioManager()
        result = manager.evaluate(make_context())
        self.assertIsInstance(result, PortfolioResult)

    def test_metadata_contains_expected_keys(self):
        manager = BasicPortfolioManager()
        result = manager.evaluate(
            make_context(strategy_result=make_strategy_result(), risk_result=make_risk_result())
        )
        expected_keys = {
            "portfolio_manager",
            "symbol",
            "timeframe",
            "open_position_count",
            "exposure_ratio",
            "symbol_exposure_ratio",
            "equity_used",
            "position_value",
            "symbol_position_value",
            "strategy_result_available",
            "strategy_action",
            "strategy_confidence",
            "risk_result_available",
            "risk_approved",
            "risk_confidence",
            "limits",
            "options",
            "hard_reject_reasons",
        }
        self.assertEqual(set(result.metadata.keys()), expected_keys)

    def test_metadata_records_manager_name(self):
        manager = BasicPortfolioManager(name="pm-1")
        result = manager.evaluate(make_context())
        self.assertEqual(result.metadata["portfolio_manager"], "pm-1")


# ----------------------------------------------------------------------
# Open-position-count facet
# ----------------------------------------------------------------------
class TestOpenPositionCountFacet(unittest.TestCase):
    def test_allows_when_under_limit(self):
        manager = BasicPortfolioManager(max_open_positions=5)
        portfolio = make_portfolio(positions=[make_position()])
        result = manager.evaluate(make_context(portfolio=portfolio))
        self.assertTrue(result.new_positions_allowed)
        self.assertEqual(result.metadata["open_position_count"], 1)

    def test_blocks_when_at_limit(self):
        manager = BasicPortfolioManager(max_open_positions=2)
        portfolio = make_portfolio(
            positions=[make_position(), make_position()], total_equity=Decimal("100000")
        )
        result = manager.evaluate(make_context(portfolio=portfolio))
        self.assertFalse(result.new_positions_allowed)
        self.assertTrue(
            any("open_position_count" in reason for reason in result.metadata["hard_reject_reasons"])
        )

    def test_closed_positions_do_not_count(self):
        manager = BasicPortfolioManager(max_open_positions=1)
        portfolio = make_portfolio(
            positions=[make_position(status=PositionStatus.CLOSED)],
            total_equity=Decimal("100000"),
        )
        result = manager.evaluate(make_context(portfolio=portfolio))
        self.assertEqual(result.metadata["open_position_count"], 0)
        self.assertTrue(result.new_positions_allowed)


# ----------------------------------------------------------------------
# Aggregate exposure facet
# ----------------------------------------------------------------------
class TestAggregateExposureFacet(unittest.TestCase):
    def test_allows_when_under_exposure_limit(self):
        manager = BasicPortfolioManager(max_exposure_ratio=0.5)
        portfolio = make_portfolio(
            cash_balance=Decimal("9000"),
            positions=[make_position(quantity=Decimal("1"), current_price=Decimal("100"))],
        )
        # equity = 9000 (cash) + 100 (position) = 9100; exposure = 100/9100 ~= 0.011
        result = manager.evaluate(make_context(portfolio=portfolio))
        self.assertTrue(result.new_positions_allowed)
        self.assertLess(result.metadata["exposure_ratio"], 0.5)

    def test_blocks_when_exposure_exceeds_limit(self):
        manager = BasicPortfolioManager(max_exposure_ratio=0.3, max_symbol_exposure_ratio=1.0)
        portfolio = make_portfolio(
            cash_balance=Decimal("100"),
            positions=[make_position(quantity=Decimal("10"), current_price=Decimal("100"))],
        )
        # equity = 100 + 1000 = 1100; exposure = 1000/1100 ~= 0.909
        result = manager.evaluate(make_context(portfolio=portfolio))
        self.assertFalse(result.new_positions_allowed)
        self.assertTrue(
            any("exposure_ratio" in reason for reason in result.metadata["hard_reject_reasons"])
        )

    def test_uses_total_equity_when_present(self):
        manager = BasicPortfolioManager()
        portfolio = make_portfolio(
            cash_balance=Decimal("100"),
            positions=[make_position(quantity=Decimal("1"), current_price=Decimal("100"))],
            total_equity=Decimal("100000"),
        )
        result = manager.evaluate(make_context(portfolio=portfolio))
        self.assertEqual(result.metadata["equity_used"], str(Decimal("100000")))

    def test_falls_back_to_current_price_then_entry_price(self):
        manager = BasicPortfolioManager()
        portfolio = make_portfolio(
            positions=[
                make_position(quantity=Decimal("1"), entry_price=Decimal("50"), current_price=None)
            ]
        )
        result = manager.evaluate(make_context(portfolio=portfolio))
        self.assertEqual(result.metadata["position_value"], str(Decimal("50")))

    def test_raises_when_equity_cannot_be_computed(self):
        manager = BasicPortfolioManager()
        portfolio = make_portfolio(cash_balance="not-a-decimal")  # type: ignore[arg-type]
        with self.assertRaises(InsufficientPortfolioDataError):
            manager.evaluate(make_context(portfolio=portfolio))


# ----------------------------------------------------------------------
# Symbol concentration facet
# ----------------------------------------------------------------------
class TestSymbolConcentrationFacet(unittest.TestCase):
    def test_blocks_on_symbol_concentration_even_under_aggregate_limit(self):
        manager = BasicPortfolioManager(max_exposure_ratio=0.9, max_symbol_exposure_ratio=0.05)
        portfolio = make_portfolio(
            cash_balance=Decimal("0"),
            positions=[make_position(symbol="BTCUSDT", quantity=Decimal("1"), current_price=Decimal("100"))],
            total_equity=Decimal("1000"),
        )
        # symbol exposure = 100/1000 = 0.1 > 0.05, aggregate exposure = 0.1 <= 0.9
        result = manager.evaluate(make_context(symbol="BTCUSDT", portfolio=portfolio))
        self.assertFalse(result.new_positions_allowed)
        self.assertTrue(
            any(
                "symbol_exposure_ratio" in reason
                for reason in result.metadata["hard_reject_reasons"]
            )
        )

    def test_other_symbols_do_not_count_toward_concentration(self):
        manager = BasicPortfolioManager(max_symbol_exposure_ratio=0.05)
        portfolio = make_portfolio(
            cash_balance=Decimal("0"),
            positions=[
                make_position(symbol="ETHUSDT", quantity=Decimal("1"), current_price=Decimal("100"))
            ],
            total_equity=Decimal("1000"),
        )
        result = manager.evaluate(make_context(symbol="BTCUSDT", portfolio=portfolio))
        self.assertEqual(result.metadata["symbol_exposure_ratio"], 0.0)


# ----------------------------------------------------------------------
# Strategy-action facet
# ----------------------------------------------------------------------
class TestStrategyActionFacet(unittest.TestCase):
    def test_blocks_on_hold_action(self):
        manager = BasicPortfolioManager()
        result = manager.evaluate(
            make_context(strategy_result=make_strategy_result(action=SignalDirection.HOLD))
        )
        self.assertFalse(result.new_positions_allowed)
        self.assertTrue(
            any("HOLD" in reason for reason in result.metadata["hard_reject_reasons"])
        )

    def test_allows_on_buy_action(self):
        manager = BasicPortfolioManager()
        result = manager.evaluate(
            make_context(strategy_result=make_strategy_result(action=SignalDirection.BUY))
        )
        self.assertTrue(result.new_positions_allowed)

    def test_missing_strategy_result_does_not_block(self):
        manager = BasicPortfolioManager()
        result = manager.evaluate(make_context(strategy_result=None))
        self.assertTrue(result.new_positions_allowed)

    def test_hold_does_not_block_when_disabled(self):
        manager = BasicPortfolioManager(block_on_hold_action=False)
        result = manager.evaluate(
            make_context(strategy_result=make_strategy_result(action=SignalDirection.HOLD))
        )
        self.assertTrue(result.new_positions_allowed)


# ----------------------------------------------------------------------
# Risk-approval facet
# ----------------------------------------------------------------------
class TestRiskApprovalFacet(unittest.TestCase):
    def test_blocks_when_risk_not_approved(self):
        manager = BasicPortfolioManager()
        result = manager.evaluate(
            make_context(risk_result=make_risk_result(approved=False))
        )
        self.assertFalse(result.new_positions_allowed)
        self.assertTrue(
            any("risk_result.approved" in reason for reason in result.metadata["hard_reject_reasons"])
        )

    def test_allows_when_risk_approved(self):
        manager = BasicPortfolioManager()
        result = manager.evaluate(make_context(risk_result=make_risk_result(approved=True)))
        self.assertTrue(result.new_positions_allowed)

    def test_missing_risk_result_does_not_block(self):
        manager = BasicPortfolioManager()
        result = manager.evaluate(make_context(risk_result=None))
        self.assertTrue(result.new_positions_allowed)

    def test_unapproved_does_not_block_when_disabled(self):
        manager = BasicPortfolioManager(require_risk_approval=False)
        result = manager.evaluate(
            make_context(risk_result=make_risk_result(approved=False))
        )
        self.assertTrue(result.new_positions_allowed)


# ----------------------------------------------------------------------
# Confidence
# ----------------------------------------------------------------------
class TestConfidenceCalculation(unittest.TestCase):
    def test_confidence_within_unit_range(self):
        manager = BasicPortfolioManager()
        result = manager.evaluate(make_context())
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_confidence_higher_with_both_results_available(self):
        manager = BasicPortfolioManager()
        bare_result = manager.evaluate(make_context())
        full_result = manager.evaluate(
            make_context(
                strategy_result=make_strategy_result(confidence=0.9),
                risk_result=make_risk_result(confidence=0.9),
            )
        )
        self.assertGreater(full_result.confidence, bare_result.confidence)

    def test_confidence_independent_of_decision(self):
        manager = BasicPortfolioManager()
        strategy_result = make_strategy_result(confidence=0.9)
        risk_result = make_risk_result(approved=False, confidence=0.9)
        blocked = manager.evaluate(
            make_context(strategy_result=strategy_result, risk_result=risk_result)
        )
        self.assertFalse(blocked.new_positions_allowed)
        approved_risk_result = make_risk_result(approved=True, confidence=0.9)
        allowed = manager.evaluate(
            make_context(strategy_result=strategy_result, risk_result=approved_risk_result)
        )
        self.assertTrue(allowed.new_positions_allowed)
        self.assertEqual(blocked.confidence, allowed.confidence)


# ----------------------------------------------------------------------
# Integration: real StrategyResult / RiskResult / Portfolio
# ----------------------------------------------------------------------
class TestBasicPortfolioManagerIntegration(unittest.TestCase):
    def test_full_pipeline_allows_a_clean_candidate(self):
        manager = BasicPortfolioManager(
            max_open_positions=5, max_exposure_ratio=0.5, max_symbol_exposure_ratio=0.2
        )
        portfolio = make_portfolio(
            cash_balance=Decimal("9500"),
            positions=[
                make_position(symbol="ETHUSDT", quantity=Decimal("1"), current_price=Decimal("500"))
            ],
            total_equity=Decimal("10000"),
        )
        strategy_result = make_strategy_result(action=SignalDirection.BUY, confidence=0.75)
        risk_result = make_risk_result(approved=True, confidence=0.85)
        context = make_context(
            symbol="BTCUSDT",
            portfolio=portfolio,
            strategy_result=strategy_result,
            risk_result=risk_result,
        )

        result = manager.evaluate(context)

        self.assertIsInstance(result, PortfolioResult)
        self.assertTrue(result.new_positions_allowed)
        self.assertEqual(result.metadata["hard_reject_reasons"], [])
        self.assertEqual(result.metadata["strategy_action"], "buy")
        self.assertTrue(result.metadata["risk_approved"])

    def test_full_pipeline_blocks_an_overexposed_portfolio(self):
        manager = BasicPortfolioManager(max_open_positions=5, max_exposure_ratio=0.4)
        portfolio = make_portfolio(
            cash_balance=Decimal("0"),
            positions=[
                make_position(symbol="ETHUSDT", quantity=Decimal("9"), current_price=Decimal("100"))
            ],
            total_equity=Decimal("1000"),
        )
        strategy_result = make_strategy_result(action=SignalDirection.BUY)
        risk_result = make_risk_result(approved=True)
        context = make_context(
            symbol="BTCUSDT",
            portfolio=portfolio,
            strategy_result=strategy_result,
            risk_result=risk_result,
        )

        result = manager.evaluate(context)

        self.assertFalse(result.new_positions_allowed)
        self.assertTrue(
            any("exposure_ratio" in reason for reason in result.metadata["hard_reject_reasons"])
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
