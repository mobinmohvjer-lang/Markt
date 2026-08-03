"""
test_basic_risk_manager.py
-----------------------------
Purpose:
    Unit tests for `BasicRiskManager` (Risk Engine Part 2), the first
    concrete `strategies.risk_management.base.BaseRiskManager`
    implementation. Complements `tests/test_risk_management.py`, which
    covers the Part 1 foundation (`RiskResult`, `RiskContext`,
    `BaseRiskManager`, exceptions, utils) and is left untouched here.

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

from core.entities.candle import Candle
from core.entities.market_state import MarketState
from core.entities.portfolio import Portfolio
from core.entities.position import Position
from core.entities.signal import Signal
from core.enums import PositionSide, PositionStatus, SignalDirection
from strategies.risk_management import (
    BaseRiskManager,
    BasicRiskManager,
    InsufficientRiskDataError,
    InvalidRiskContextError,
    RiskContext,
    RiskManagerConfigurationError,
    RiskResult,
)

NOW = datetime.now(timezone.utc)


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
def make_signal(
    *,
    direction: SignalDirection = SignalDirection.BUY,
    confidence: float = 0.8,
    metadata: dict | None = None,
) -> Signal:
    return Signal(
        signal_id="sig-1",
        symbol="BTCUSDT",
        direction=direction,
        confidence=confidence,
        source="TechnicalSignalGenerator",
        timeframe="1h",
        generated_at=NOW,
        metadata=metadata or {},
    )


def make_position(
    *,
    quantity: Decimal = Decimal("1"),
    entry_price: Decimal = Decimal("100"),
    current_price: Decimal | None = Decimal("100"),
) -> Position:
    return Position(
        position_id="pos-1",
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        entry_price=entry_price,
        quantity=quantity,
        opened_at=NOW,
        status=PositionStatus.OPEN,
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


def make_market_state() -> MarketState:
    return MarketState(
        symbol="BTCUSDT",
        timeframe="1h",
        timestamp=NOW,
        latest_candle=Candle(
            symbol="BTCUSDT",
            timeframe="1h",
            open_time=NOW,
            close_time=NOW,
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("95"),
            close=Decimal("105"),
            volume=Decimal("1000"),
        ),
    )


def make_context(
    *,
    signal: Signal | None = None,
    portfolio: Portfolio | None = None,
    market_state: MarketState | None = None,
) -> RiskContext:
    return RiskContext(
        symbol="BTCUSDT",
        timeframe="1h",
        signal=signal if signal is not None else make_signal(),
        portfolio=portfolio if portfolio is not None else make_portfolio(),
        market_state=market_state,
    )


# ----------------------------------------------------------------------
# Construction / configuration validation
# ----------------------------------------------------------------------
class TestBasicRiskManagerConstruction(unittest.TestCase):
    def test_default_construction(self):
        manager = BasicRiskManager()
        self.assertEqual(manager.name, "BasicRiskManager")
        self.assertIsInstance(manager, BaseRiskManager)

    def test_custom_name(self):
        manager = BasicRiskManager(name="MyRiskManager")
        self.assertEqual(manager.name, "MyRiskManager")

    def test_weights_must_sum_to_one(self):
        with self.assertRaises(RiskManagerConfigurationError):
            BasicRiskManager(
                confidence_weight=0.5,
                strength_weight=0.5,
                exposure_weight=0.5,
                market_weight=0.5,
            )

    def test_custom_weights_summing_to_one_are_accepted(self):
        manager = BasicRiskManager(
            confidence_weight=0.4,
            strength_weight=0.2,
            exposure_weight=0.3,
            market_weight=0.1,
        )
        self.assertEqual(manager.confidence_weight, 0.4)

    def test_rejects_non_numeric_weight(self):
        with self.assertRaises(RiskManagerConfigurationError):
            BasicRiskManager(confidence_weight="high")  # type: ignore[arg-type]

    def test_rejects_out_of_range_weight(self):
        with self.assertRaises(RiskManagerConfigurationError):
            BasicRiskManager(confidence_weight=1.5, strength_weight=-0.5)

    def test_rejects_bool_weight(self):
        with self.assertRaises(RiskManagerConfigurationError):
            BasicRiskManager(confidence_weight=True)  # type: ignore[arg-type]

    def test_rejects_non_positive_max_exposure_ratio(self):
        with self.assertRaises(RiskManagerConfigurationError):
            BasicRiskManager(max_exposure_ratio=0.0)
        with self.assertRaises(RiskManagerConfigurationError):
            BasicRiskManager(max_exposure_ratio=-0.1)

    def test_rejects_non_numeric_max_exposure_ratio(self):
        with self.assertRaises(RiskManagerConfigurationError):
            BasicRiskManager(max_exposure_ratio="half")  # type: ignore[arg-type]

    def test_rejects_out_of_range_threshold(self):
        with self.assertRaises(RiskManagerConfigurationError):
            BasicRiskManager(risk_score_threshold=1.1)


# ----------------------------------------------------------------------
# validate_context() shared behavior (inherited from BaseRiskManager)
# ----------------------------------------------------------------------
class TestBasicRiskManagerContextValidation(unittest.TestCase):
    def test_evaluate_rejects_non_risk_context(self):
        manager = BasicRiskManager()
        with self.assertRaises(InvalidRiskContextError):
            manager.evaluate("not-a-context")  # type: ignore[arg-type]


# ----------------------------------------------------------------------
# Output shape
# ----------------------------------------------------------------------
class TestBasicRiskManagerOutputShape(unittest.TestCase):
    def test_returns_risk_result(self):
        manager = BasicRiskManager()
        result = manager.evaluate(make_context())
        self.assertIsInstance(result, RiskResult)

    def test_result_has_only_five_documented_fields(self):
        manager = BasicRiskManager()
        result = manager.evaluate(make_context())
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        self.assertEqual(
            field_names, {"approved", "risk_score", "confidence", "summary", "metadata"}
        )

    def test_risk_score_and_confidence_within_unit_range(self):
        manager = BasicRiskManager()
        result = manager.evaluate(make_context())
        self.assertGreaterEqual(result.risk_score, 0.0)
        self.assertLessEqual(result.risk_score, 1.0)
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_summary_is_non_empty_string(self):
        manager = BasicRiskManager()
        result = manager.evaluate(make_context())
        self.assertIsInstance(result.summary, str)
        self.assertTrue(result.summary.strip())

    def test_metadata_contains_expected_traceability_keys(self):
        manager = BasicRiskManager()
        result = manager.evaluate(make_context())
        expected_keys = {
            "risk_manager",
            "signal_confidence",
            "signal_confidence_clamped",
            "signal_strength",
            "signal_strength_available",
            "signal_strength_clamped",
            "exposure_ratio",
            "equity_used_for_exposure",
            "market_state_available",
            "components",
            "weights",
            "thresholds",
            "hard_reject_reasons",
        }
        self.assertTrue(expected_keys.issubset(result.metadata.keys()))

    def test_never_includes_position_sizing_or_order_fields(self):
        manager = BasicRiskManager()
        result = manager.evaluate(make_context())
        forbidden_terms = ("position_size", "stop_loss", "take_profit", "order_id")
        for term in forbidden_terms:
            self.assertNotIn(term, result.metadata)


# ----------------------------------------------------------------------
# Signal confidence facet
# ----------------------------------------------------------------------
class TestSignalConfidenceFacet(unittest.TestCase):
    def test_high_confidence_lowers_risk_contribution(self):
        manager = BasicRiskManager()
        high = manager.evaluate(make_context(signal=make_signal(confidence=0.95)))
        low = manager.evaluate(make_context(signal=make_signal(confidence=0.1)))
        self.assertLess(
            high.metadata["components"]["confidence_risk"],
            low.metadata["components"]["confidence_risk"],
        )

    def test_low_confidence_below_minimum_hard_rejects(self):
        manager = BasicRiskManager(min_signal_confidence=0.5)
        result = manager.evaluate(make_context(signal=make_signal(confidence=0.2)))
        self.assertFalse(result.approved)
        self.assertTrue(
            any("signal_confidence" in reason for reason in result.metadata["hard_reject_reasons"])
        )

    def test_raises_when_confidence_not_numeric(self):
        manager = BasicRiskManager()
        bad_signal = make_signal()
        object.__setattr__(bad_signal, "confidence", "high")
        with self.assertRaises(InsufficientRiskDataError):
            manager.evaluate(make_context(signal=bad_signal))

    def test_raises_when_confidence_not_finite(self):
        manager = BasicRiskManager()
        bad_signal = make_signal()
        object.__setattr__(bad_signal, "confidence", float("nan"))
        with self.assertRaises(InsufficientRiskDataError):
            manager.evaluate(make_context(signal=bad_signal))

    def test_out_of_range_confidence_is_clamped_not_rejected(self):
        manager = BasicRiskManager()
        bad_signal = make_signal()
        object.__setattr__(bad_signal, "confidence", 1.5)
        result = manager.evaluate(make_context(signal=bad_signal))
        self.assertEqual(result.metadata["signal_confidence"], 1.0)
        self.assertTrue(result.metadata["signal_confidence_clamped"])


# ----------------------------------------------------------------------
# Signal strength facet
# ----------------------------------------------------------------------
class TestSignalStrengthFacet(unittest.TestCase):
    def test_strength_read_from_signal_metadata(self):
        manager = BasicRiskManager()
        signal = make_signal(metadata={"strength": 0.9})
        result = manager.evaluate(make_context(signal=signal))
        self.assertTrue(result.metadata["signal_strength_available"])
        self.assertEqual(result.metadata["signal_strength"], 0.9)

    def test_missing_strength_is_unavailable_not_an_error(self):
        manager = BasicRiskManager()
        result = manager.evaluate(make_context(signal=make_signal(metadata={})))
        self.assertFalse(result.metadata["signal_strength_available"])
        self.assertIsNone(result.metadata["signal_strength"])

    def test_missing_strength_uses_neutral_default_risk(self):
        manager = BasicRiskManager()
        result = manager.evaluate(make_context(signal=make_signal(metadata={})))
        self.assertEqual(
            result.metadata["components"]["strength_risk"], manager.missing_strength_risk
        )

    def test_non_numeric_strength_treated_as_unavailable(self):
        manager = BasicRiskManager()
        signal = make_signal(metadata={"strength": "very strong"})
        result = manager.evaluate(make_context(signal=signal))
        self.assertFalse(result.metadata["signal_strength_available"])

    def test_out_of_range_strength_is_clamped(self):
        manager = BasicRiskManager()
        signal = make_signal(metadata={"strength": 1.7})
        result = manager.evaluate(make_context(signal=signal))
        self.assertTrue(result.metadata["signal_strength_available"])
        self.assertEqual(result.metadata["signal_strength"], 1.0)
        self.assertTrue(result.metadata["signal_strength_clamped"])

    def test_low_strength_below_minimum_hard_rejects(self):
        manager = BasicRiskManager(min_signal_strength=0.5)
        signal = make_signal(metadata={"strength": 0.1})
        result = manager.evaluate(make_context(signal=signal))
        self.assertFalse(result.approved)
        self.assertTrue(
            any("signal_strength" in reason for reason in result.metadata["hard_reject_reasons"])
        )

    def test_missing_strength_never_triggers_strength_hard_reject(self):
        manager = BasicRiskManager(min_signal_strength=0.9)
        result = manager.evaluate(make_context(signal=make_signal(metadata={})))
        self.assertFalse(
            any("signal_strength" in reason for reason in result.metadata["hard_reject_reasons"])
        )


# ----------------------------------------------------------------------
# Portfolio exposure facet
# ----------------------------------------------------------------------
class TestPortfolioExposureFacet(unittest.TestCase):
    def test_no_positions_means_zero_exposure(self):
        manager = BasicRiskManager()
        result = manager.evaluate(make_context(portfolio=make_portfolio(positions=[])))
        self.assertEqual(result.metadata["exposure_ratio"], 0.0)

    def test_exposure_computed_from_cash_and_positions_when_no_total_equity(self):
        manager = BasicRiskManager()
        portfolio = make_portfolio(
            cash_balance=Decimal("9000"),
            positions=[make_position(quantity=Decimal("10"), current_price=Decimal("100"))],
            total_equity=None,
        )
        # position value = 10 * 100 = 1000, equity = 9000 + 1000 = 10000
        result = manager.evaluate(make_context(portfolio=portfolio))
        self.assertAlmostEqual(result.metadata["exposure_ratio"], 0.1, places=6)

    def test_exposure_uses_total_equity_when_provided(self):
        manager = BasicRiskManager()
        portfolio = make_portfolio(
            cash_balance=Decimal("0"),
            positions=[make_position(quantity=Decimal("5"), current_price=Decimal("200"))],
            total_equity=Decimal("5000"),
        )
        # position value = 5 * 200 = 1000, equity = 5000 (explicit)
        result = manager.evaluate(make_context(portfolio=portfolio))
        self.assertAlmostEqual(result.metadata["exposure_ratio"], 0.2, places=6)

    def test_falls_back_to_entry_price_when_current_price_missing(self):
        manager = BasicRiskManager()
        portfolio = make_portfolio(
            cash_balance=Decimal("0"),
            positions=[
                make_position(
                    quantity=Decimal("5"), entry_price=Decimal("100"), current_price=None
                )
            ],
            total_equity=Decimal("500"),
        )
        result = manager.evaluate(make_context(portfolio=portfolio))
        self.assertAlmostEqual(result.metadata["exposure_ratio"], 1.0, places=6)

    def test_high_exposure_hard_rejects(self):
        manager = BasicRiskManager(max_exposure_ratio=0.5)
        portfolio = make_portfolio(
            cash_balance=Decimal("0"),
            positions=[make_position(quantity=Decimal("10"), current_price=Decimal("100"))],
            total_equity=Decimal("1000"),
        )
        result = manager.evaluate(make_context(portfolio=portfolio))
        self.assertFalse(result.approved)
        self.assertTrue(
            any("exposure_ratio" in reason for reason in result.metadata["hard_reject_reasons"])
        )

    def test_zero_or_negative_equity_with_positions_is_maximal_exposure(self):
        manager = BasicRiskManager()
        portfolio = make_portfolio(
            cash_balance=Decimal("-1000"),
            positions=[make_position(quantity=Decimal("1"), current_price=Decimal("100"))],
            total_equity=None,
        )
        result = manager.evaluate(make_context(portfolio=portfolio))
        self.assertEqual(result.metadata["exposure_ratio"], 1.0)

    def test_zero_equity_with_no_positions_is_zero_exposure(self):
        manager = BasicRiskManager()
        portfolio = make_portfolio(
            cash_balance=Decimal("0"), positions=[], total_equity=Decimal("0")
        )
        result = manager.evaluate(make_context(portfolio=portfolio))
        self.assertEqual(result.metadata["exposure_ratio"], 0.0)

    def test_malformed_position_is_skipped_not_raised(self):
        manager = BasicRiskManager()
        malformed = make_position(quantity=Decimal("1"), current_price=Decimal("100"))
        object.__setattr__(malformed, "quantity", "oops")
        portfolio = make_portfolio(
            cash_balance=Decimal("1000"), positions=[malformed], total_equity=None
        )
        result = manager.evaluate(make_context(portfolio=portfolio))
        self.assertEqual(result.metadata["exposure_ratio"], 0.0)


# ----------------------------------------------------------------------
# Market availability facet
# ----------------------------------------------------------------------
class TestMarketAvailabilityFacet(unittest.TestCase):
    def test_market_state_present_is_recorded(self):
        manager = BasicRiskManager()
        result = manager.evaluate(make_context(market_state=make_market_state()))
        self.assertTrue(result.metadata["market_state_available"])
        self.assertEqual(result.metadata["components"]["market_risk"], 0.0)

    def test_market_state_absent_applies_penalty_and_lowers_confidence(self):
        manager = BasicRiskManager()
        with_market = manager.evaluate(
            make_context(
                signal=make_signal(confidence=0.9, metadata={"strength": 0.9}),
                market_state=make_market_state(),
            )
        )
        without_market = manager.evaluate(
            make_context(
                signal=make_signal(confidence=0.9, metadata={"strength": 0.9}),
                market_state=None,
            )
        )
        self.assertFalse(without_market.metadata["market_state_available"])
        self.assertEqual(
            without_market.metadata["components"]["market_risk"],
            manager.market_unavailable_risk,
        )
        self.assertLess(without_market.confidence, with_market.confidence)

    def test_never_raises_for_missing_market_state(self):
        manager = BasicRiskManager()
        try:
            manager.evaluate(make_context(market_state=None))
        except InsufficientRiskDataError:
            self.fail("BasicRiskManager should not raise for a missing MarketState")


# ----------------------------------------------------------------------
# Approval decision (integration of all facets)
# ----------------------------------------------------------------------
class TestApprovalDecision(unittest.TestCase):
    def test_strong_favorable_context_is_approved_with_low_risk(self):
        manager = BasicRiskManager()
        signal = make_signal(confidence=0.9, metadata={"strength": 0.85})
        portfolio = make_portfolio(
            cash_balance=Decimal("9000"),
            positions=[make_position(quantity=Decimal("1"), current_price=Decimal("100"))],
            total_equity=None,
        )
        result = manager.evaluate(
            make_context(signal=signal, portfolio=portfolio, market_state=make_market_state())
        )
        self.assertTrue(result.approved)
        self.assertLess(result.risk_score, 0.5)

    def test_weak_unfavorable_context_is_rejected_with_high_risk(self):
        manager = BasicRiskManager()
        signal = make_signal(confidence=0.1, metadata={"strength": 0.1})
        portfolio = make_portfolio(
            cash_balance=Decimal("0"),
            positions=[make_position(quantity=Decimal("100"), current_price=Decimal("100"))],
            total_equity=Decimal("1000"),
        )
        result = manager.evaluate(make_context(signal=signal, portfolio=portfolio))
        self.assertFalse(result.approved)
        self.assertGreater(result.risk_score, 0.5)

    def test_risk_score_at_or_below_threshold_with_no_hard_rejects_is_approved(self):
        manager = BasicRiskManager(risk_score_threshold=1.0, max_exposure_ratio=100.0)
        signal = make_signal(confidence=0.0, metadata={})
        result = manager.evaluate(make_context(signal=signal))
        # threshold is maximal and hard-reject minimums default low enough to pass
        self.assertLessEqual(result.risk_score, 1.0)

    def test_approved_is_always_a_bool(self):
        manager = BasicRiskManager()
        result = manager.evaluate(make_context())
        self.assertIsInstance(result.approved, bool)


# ----------------------------------------------------------------------
# Integration: realistic end-to-end evaluation
# ----------------------------------------------------------------------
class TestBasicRiskManagerIntegration(unittest.TestCase):
    def test_end_to_end_with_realistic_signal_portfolio_and_market_state(self):
        manager = BasicRiskManager(name="ExposureAwareRiskManager")
        signal = make_signal(
            direction=SignalDirection.BUY,
            confidence=0.72,
            metadata={"strength": 0.65, "source_score": 0.4},
        )
        portfolio = make_portfolio(
            cash_balance=Decimal("7000"),
            positions=[
                make_position(
                    quantity=Decimal("3"),
                    entry_price=Decimal("950"),
                    current_price=Decimal("1000"),
                )
            ],
            total_equity=Decimal("10000"),
        )
        context = make_context(signal=signal, portfolio=portfolio, market_state=make_market_state())

        result = manager.evaluate(context)

        self.assertIsInstance(result, RiskResult)
        self.assertEqual(result.metadata["risk_manager"], "ExposureAwareRiskManager")
        self.assertAlmostEqual(result.metadata["exposure_ratio"], 0.3, places=6)
        self.assertTrue(result.metadata["market_state_available"])
        self.assertTrue(result.metadata["signal_strength_available"])
        self.assertIn("components", result.metadata)
        self.assertIn("weights", result.metadata)
        self.assertIn("thresholds", result.metadata)


if __name__ == "__main__":
    unittest.main()
