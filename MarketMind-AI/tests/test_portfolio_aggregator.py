"""
test_portfolio_aggregator.py
-----------------------------
Purpose:
    Unit tests for the Portfolio Management Part 4 concrete module:
    `strategies.portfolio_management.aggregator.PortfolioAggregator`.

Mirrors the local-factory / assertion style already used by
`tests/test_portfolio_management.py` (Part 1),
`tests/test_basic_portfolio_manager.py` (Part 2), and
`tests/test_portfolio_manager.py` (Part 3, the closest structural
sibling -- `PortfolioAggregator` plays functionally the same combining
role `PortfolioManager` does, but is built to mirror
`strategies.aggregator.StrategyAggregator`'s naming/documentation
conventions one layer up), all left untouched by this change.

Most tests inject fake `BasePortfolioManager` sub-managers
(constructor-injected, matching the project's dependency-injection
convention) so the aggregation/merging logic itself can be exercised
precisely, without needing to hand-construct a full
analysis/signal/risk/strategy chain for every test. A dedicated
integration section combines real `BasicPortfolioManager` instances to
prove the module actually reuses Portfolio Management Part 2 end-to-end,
and a dedicated independence section confirms `PortfolioAggregator`
does not import or depend on `PortfolioManager` (Part 3), as documented
in `aggregator.py` and `strategies/portfolio_management/__init__.py`.

Uses the standard-library ``unittest`` framework, no external
test-runner dependency, no network access.

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
    PortfolioAggregator,
    PortfolioContext,
    PortfolioManagerConfigurationError,
    PortfolioResult,
)
from strategies.result import StrategyResult
from strategies.risk_management.result import RiskResult

NOW = datetime.now(timezone.utc)
SYMBOL = "BTCUSDT"
TIMEFRAME = "1h"


# ----------------------------------------------------------------------
# Local test factories
# ----------------------------------------------------------------------
def make_position(
    *,
    symbol: str = SYMBOL,
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
    symbol: str = SYMBOL,
    timeframe: str = TIMEFRAME,
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


class _FakePortfolioManager(BasePortfolioManager):
    """
    Test double for a sub-manager: returns a fixed `PortfolioResult`,
    or raises `InsufficientPortfolioDataError` if configured to be
    "unavailable". Lets aggregation logic be tested independently of
    any real `BasicPortfolioManager` machinery.
    """

    def __init__(
        self,
        *,
        allowed: bool = True,
        confidence: float = 1.0,
        unavailable: bool = False,
        name: str | None = None,
    ) -> None:
        super().__init__(name=name)
        self.allowed = allowed
        self.confidence = confidence
        self.unavailable = unavailable

    def evaluate(self, context: PortfolioContext) -> PortfolioResult:
        self.validate_context(context)
        if self.unavailable:
            raise InsufficientPortfolioDataError(f"{self.name} has no data")
        return self._build_result(
            new_positions_allowed=self.allowed,
            confidence=self.confidence,
            summary=f"fake decision from {self.name}",
            metadata={"fake": True},
        )


# ----------------------------------------------------------------------
# Construction / configuration validation
# ----------------------------------------------------------------------
class TestConstruction(unittest.TestCase):
    def test_defaults_to_single_basic_portfolio_manager(self):
        aggregator = PortfolioAggregator()
        self.assertEqual(list(aggregator._managers), ["BasicPortfolioManager"])
        self.assertIsInstance(
            aggregator._managers["BasicPortfolioManager"], BasicPortfolioManager
        )
        self.assertEqual(aggregator.weights, {"BasicPortfolioManager": 1.0})
        self.assertEqual(aggregator.allow_threshold, 0.0)
        self.assertEqual(aggregator.name, "PortfolioAggregator")

    def test_is_a_base_portfolio_manager(self):
        self.assertIsInstance(PortfolioAggregator(), BasePortfolioManager)

    def test_custom_managers_and_name(self):
        mgr_a = _FakePortfolioManager(name="A")
        mgr_b = _FakePortfolioManager(name="B")
        aggregator = PortfolioAggregator(managers=[mgr_a, mgr_b], name="Custom")
        self.assertEqual(list(aggregator._managers), ["A", "B"])
        self.assertEqual(aggregator.name, "Custom")

    def test_rejects_empty_manager_list(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            PortfolioAggregator(managers=[])

    def test_rejects_non_manager_item(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            PortfolioAggregator(managers=["not a manager"])  # type: ignore[list-item]

    def test_rejects_duplicate_manager_names(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            PortfolioAggregator(
                managers=[_FakePortfolioManager(name="A"), _FakePortfolioManager(name="A")]
            )

    def test_custom_weights(self):
        mgr_a = _FakePortfolioManager(name="A")
        mgr_b = _FakePortfolioManager(name="B")
        aggregator = PortfolioAggregator(managers=[mgr_a, mgr_b], weights={"A": 2.0, "B": 0.5})
        self.assertEqual(aggregator.weights, {"A": 2.0, "B": 0.5})

    def test_weights_default_to_one_when_unspecified(self):
        mgr_a = _FakePortfolioManager(name="A")
        mgr_b = _FakePortfolioManager(name="B")
        aggregator = PortfolioAggregator(managers=[mgr_a, mgr_b], weights={"A": 3.0})
        self.assertEqual(aggregator.weights, {"A": 3.0, "B": 1.0})

    def test_rejects_unknown_weight_key(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            PortfolioAggregator(
                managers=[_FakePortfolioManager(name="A")], weights={"Unknown": 1.0}
            )

    def test_rejects_negative_weight(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            PortfolioAggregator(managers=[_FakePortfolioManager(name="A")], weights={"A": -1.0})

    def test_rejects_non_numeric_weight(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            PortfolioAggregator(
                managers=[_FakePortfolioManager(name="A")],
                weights={"A": "high"},  # type: ignore[dict-item]
            )

    def test_rejects_boolean_weight(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            PortfolioAggregator(
                managers=[_FakePortfolioManager(name="A")],
                weights={"A": True},  # type: ignore[dict-item]
            )

    def test_rejects_non_finite_weight(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            PortfolioAggregator(
                managers=[_FakePortfolioManager(name="A")], weights={"A": float("nan")}
            )

    def test_accepts_zero_weight(self):
        aggregator = PortfolioAggregator(
            managers=[_FakePortfolioManager(name="A")], weights={"A": 0.0}
        )
        self.assertEqual(aggregator.weights["A"], 0.0)

    def test_rejects_non_numeric_allow_threshold(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            PortfolioAggregator(allow_threshold="high")  # type: ignore[arg-type]

    def test_rejects_boolean_allow_threshold(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            PortfolioAggregator(allow_threshold=True)  # type: ignore[arg-type]

    def test_rejects_non_finite_allow_threshold(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            PortfolioAggregator(allow_threshold=float("nan"))

    def test_rejects_allow_threshold_out_of_range(self):
        with self.assertRaises(PortfolioManagerConfigurationError):
            PortfolioAggregator(allow_threshold=1.5)
        with self.assertRaises(PortfolioManagerConfigurationError):
            PortfolioAggregator(allow_threshold=-1.5)

    def test_accepts_boundary_allow_thresholds(self):
        PortfolioAggregator(allow_threshold=1.0)
        PortfolioAggregator(allow_threshold=-1.0)


# ----------------------------------------------------------------------
# evaluate() -- context validation and unavailable-manager handling
# ----------------------------------------------------------------------
class TestEvaluateValidation(unittest.TestCase):
    def test_rejects_non_portfolio_context(self):
        aggregator = PortfolioAggregator(managers=[_FakePortfolioManager(name="A")])
        with self.assertRaises(InvalidPortfolioContextError):
            aggregator.evaluate("not a context")  # type: ignore[arg-type]

    def test_raises_when_all_managers_unavailable(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", unavailable=True),
                _FakePortfolioManager(name="B", unavailable=True),
            ]
        )
        with self.assertRaises(InsufficientPortfolioDataError):
            aggregator.evaluate(make_context())

    def test_ignores_a_single_unavailable_manager(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", unavailable=True),
                _FakePortfolioManager(name="B", allowed=True, confidence=0.9),
            ]
        )
        result = aggregator.evaluate(make_context())
        self.assertTrue(result.new_positions_allowed)
        self.assertIn("A", result.metadata["managers_missing"])
        self.assertIn("B", result.metadata["managers_available"])

    def test_missing_reason_is_recorded(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", unavailable=True),
                _FakePortfolioManager(name="B", allowed=True, confidence=0.5),
            ]
        )
        result = aggregator.evaluate(make_context())
        self.assertIn("A has no data", result.metadata["components"]["A"]["reason"])

    def test_never_mutates_sub_manager_results(self):
        # Calling evaluate() twice must not change what the sub-manager
        # itself would independently produce -- PortfolioResult is
        # frozen, but this also confirms the aggregator never rebuilds
        # a sub-result in place.
        mgr = _FakePortfolioManager(name="A", allowed=True, confidence=0.7)
        aggregator = PortfolioAggregator(managers=[mgr])
        ctx = make_context()
        first = mgr.evaluate(ctx)
        aggregator.evaluate(ctx)
        second = mgr.evaluate(ctx)
        self.assertEqual(first, second)


# ----------------------------------------------------------------------
# evaluate() -- weighted vote aggregation / threshold mapping
# ----------------------------------------------------------------------
class TestEvaluateAggregation(unittest.TestCase):
    def test_agreeing_allowing_managers_yield_allowed(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=0.9),
                _FakePortfolioManager(name="B", allowed=True, confidence=0.8),
            ]
        )
        result = aggregator.evaluate(make_context())
        self.assertTrue(result.new_positions_allowed)
        self.assertGreater(result.confidence, 0.0)
        self.assertEqual(result.metadata["aggregate_score"], 1.0)
        self.assertEqual(result.metadata["agreement"], 1.0)
        self.assertEqual(result.metadata["completeness"], 1.0)

    def test_agreeing_blocking_managers_yield_blocked(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=False, confidence=0.9),
                _FakePortfolioManager(name="B", allowed=False, confidence=0.8),
            ]
        )
        result = aggregator.evaluate(make_context())
        self.assertFalse(result.new_positions_allowed)
        self.assertEqual(result.metadata["aggregate_score"], -1.0)

    def test_conflicting_managers_at_default_threshold_block(self):
        # Equal-weight, equal-confidence opposite votes average to a
        # net score of 0.0; the default allow_threshold is 0.0 and the
        # comparison is strict (`>`), so a tied vote blocks.
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=1.0),
                _FakePortfolioManager(name="B", allowed=False, confidence=1.0),
            ]
        )
        result = aggregator.evaluate(make_context())
        self.assertFalse(result.new_positions_allowed)
        self.assertAlmostEqual(result.metadata["aggregate_score"], 0.0)
        self.assertLess(result.metadata["agreement"], 1.0)

    def test_weights_change_outcome(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=1.0),
                _FakePortfolioManager(name="B", allowed=False, confidence=1.0),
            ],
            weights={"A": 5.0, "B": 1.0},
        )
        result = aggregator.evaluate(make_context())
        self.assertTrue(result.new_positions_allowed)

    def test_zero_weight_manager_does_not_affect_decision(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=1.0),
                _FakePortfolioManager(name="B", allowed=False, confidence=1.0),
            ],
            weights={"A": 1.0, "B": 0.0},
        )
        result = aggregator.evaluate(make_context())
        self.assertTrue(result.new_positions_allowed)

    def test_low_confidence_manager_contributes_less(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=1.0),
                _FakePortfolioManager(name="B", allowed=False, confidence=0.01),
            ]
        )
        result = aggregator.evaluate(make_context())
        self.assertTrue(result.new_positions_allowed)

    def test_custom_allow_threshold_blocks_weak_positive_vote(self):
        # A lone allowing manager produces a signed unit score of
        # +1.0; a threshold at the ceiling of 1.0 is not strictly
        # exceeded, so the aggregate decision blocks.
        aggregator = PortfolioAggregator(
            managers=[_FakePortfolioManager(name="A", allowed=True, confidence=1.0)],
            allow_threshold=1.0,
        )
        result = aggregator.evaluate(make_context())
        self.assertFalse(result.new_positions_allowed)

    def test_negative_allow_threshold_permits_net_negative_vote(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=1.0),
                _FakePortfolioManager(name="B", allowed=False, confidence=1.0),
                _FakePortfolioManager(name="C", allowed=False, confidence=1.0),
            ],
            allow_threshold=-1.0,
        )
        result = aggregator.evaluate(make_context())
        # aggregate_score here is (1 - 1 - 1) / 3 = -0.333..., which is
        # strictly greater than an allow_threshold of -1.0.
        self.assertTrue(result.new_positions_allowed)


# ----------------------------------------------------------------------
# evaluate() -- completeness / agreement / confidence shape
# ----------------------------------------------------------------------
class TestEvaluateCompletenessAgreementConfidence(unittest.TestCase):
    def test_completeness_reflects_missing_managers(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=1.0),
                _FakePortfolioManager(name="B", unavailable=True),
            ]
        )
        result = aggregator.evaluate(make_context())
        self.assertAlmostEqual(result.metadata["completeness"], 0.5)

    def test_full_completeness_when_all_available(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=1.0),
                _FakePortfolioManager(name="B", allowed=True, confidence=1.0),
            ]
        )
        result = aggregator.evaluate(make_context())
        self.assertEqual(result.metadata["completeness"], 1.0)

    def test_full_agreement_when_all_managers_agree_with_final(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=1.0),
                _FakePortfolioManager(name="B", allowed=True, confidence=1.0),
            ]
        )
        result = aggregator.evaluate(make_context())
        self.assertEqual(result.metadata["agreement"], 1.0)

    def test_confidence_never_exceeds_component_confidences(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=0.4),
                _FakePortfolioManager(name="B", allowed=True, confidence=0.6),
            ]
        )
        result = aggregator.evaluate(make_context())
        self.assertLessEqual(result.confidence, 0.6)

    def test_missing_manager_lowers_confidence_via_completeness(self):
        base = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=0.9),
                _FakePortfolioManager(name="B", allowed=True, confidence=0.9),
            ]
        )
        degraded = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=0.9),
                _FakePortfolioManager(name="B", unavailable=True),
            ]
        )
        base_result = base.evaluate(make_context())
        degraded_result = degraded.evaluate(make_context())
        self.assertLess(degraded_result.confidence, base_result.confidence)

    def test_disagreement_lowers_confidence_via_agreement(self):
        agreeing = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=0.9),
                _FakePortfolioManager(name="B", allowed=True, confidence=0.9),
            ]
        )
        disagreeing = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=0.9),
                _FakePortfolioManager(name="B", allowed=False, confidence=0.9),
            ]
        )
        agreeing_result = agreeing.evaluate(make_context())
        disagreeing_result = disagreeing.evaluate(make_context())
        self.assertLess(disagreeing_result.confidence, agreeing_result.confidence)

    def test_confidence_is_zero_to_one(self):
        aggregator = PortfolioAggregator(
            managers=[_FakePortfolioManager(name="A", allowed=True, confidence=1.0)]
        )
        result = aggregator.evaluate(make_context())
        self.assertGreaterEqual(result.confidence, 0.0)
        self.assertLessEqual(result.confidence, 1.0)

    def test_single_manager_unanimous_and_complete(self):
        aggregator = PortfolioAggregator(
            managers=[_FakePortfolioManager(name="A", allowed=True, confidence=0.75)]
        )
        result = aggregator.evaluate(make_context())
        self.assertEqual(result.metadata["completeness"], 1.0)
        self.assertEqual(result.metadata["agreement"], 1.0)
        self.assertAlmostEqual(result.confidence, 0.75)


# ----------------------------------------------------------------------
# evaluate() -- output shape (metadata / summary content / determinism)
# ----------------------------------------------------------------------
class TestEvaluateOutputShape(unittest.TestCase):
    def setUp(self):
        self.mgr_a = _FakePortfolioManager(name="A", allowed=True, confidence=0.9)
        self.mgr_b = _FakePortfolioManager(name="B", allowed=True, confidence=0.6)
        self.aggregator = PortfolioAggregator(
            managers=[self.mgr_a, self.mgr_b], weights={"A": 2.0, "B": 1.0}
        )

    def test_result_is_a_valid_portfolio_result_with_four_fields(self):
        result = self.aggregator.evaluate(make_context())
        self.assertIsInstance(result, PortfolioResult)
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        self.assertEqual(
            field_names, {"new_positions_allowed", "confidence", "summary", "metadata"}
        )

    def test_result_has_no_allocation_order_or_ai_fields(self):
        result = self.aggregator.evaluate(make_context())
        field_names = {f.name for f in result.__dataclass_fields__.values()}
        for forbidden in (
            "order_id",
            "position_size",
            "allocation",
            "rebalance",
            "portfolio_manager_name",
        ):
            self.assertNotIn(forbidden, field_names)

    def test_metadata_contains_every_component_manager(self):
        result = self.aggregator.evaluate(make_context())
        components = result.metadata["components"]
        self.assertIn("A", components)
        self.assertIn("B", components)
        self.assertTrue(components["A"]["available"])
        self.assertEqual(components["A"]["new_positions_allowed"], True)
        self.assertEqual(components["A"]["confidence"], 0.9)
        self.assertEqual(components["A"]["weight"], 2.0)
        self.assertEqual(components["A"]["metadata"], {"fake": True})
        self.assertIn("agreement_with_final", components["A"])

    def test_metadata_contains_weights(self):
        result = self.aggregator.evaluate(make_context())
        self.assertEqual(result.metadata["weights"], {"A": 2.0, "B": 1.0})

    def test_metadata_contains_aggregation_details(self):
        result = self.aggregator.evaluate(make_context())
        details = result.metadata["aggregation_details"]
        self.assertIn("method", details)
        self.assertIn("aggregate_score", details)
        self.assertIn("final_new_positions_allowed", details)
        self.assertIn("completeness", details)
        self.assertIn("agreement", details)
        self.assertEqual(details["allow_threshold"], self.aggregator.allow_threshold)

    def test_metadata_contains_top_level_required_facets(self):
        result = self.aggregator.evaluate(make_context())
        for key in (
            "aggregate_score",
            "completeness",
            "agreement",
            "score_scale",
            "confidence_scale",
        ):
            self.assertIn(key, result.metadata)

    def test_metadata_missing_manager_has_reason_and_no_new_positions_allowed_key(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=0.9),
                _FakePortfolioManager(name="B", unavailable=True),
            ]
        )
        result = aggregator.evaluate(make_context())
        component_b = result.metadata["components"]["B"]
        self.assertFalse(component_b["available"])
        self.assertIn("reason", component_b)
        self.assertNotIn("new_positions_allowed", component_b)

    def test_summary_mentions_decision_and_contributing_managers(self):
        result = self.aggregator.evaluate(make_context())
        decision_word = "Allowed" if result.new_positions_allowed else "Blocked"
        self.assertIn(decision_word, result.summary)
        self.assertIn("A", result.summary)
        self.assertIn("B", result.summary)

    def test_summary_mentions_missing_managers(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="A", allowed=True, confidence=0.9),
                _FakePortfolioManager(name="B", unavailable=True),
            ]
        )
        result = aggregator.evaluate(make_context())
        self.assertIn("missing", result.summary)
        self.assertIn("B", result.summary)

    def test_determinism_repeated_calls_produce_identical_results(self):
        ctx = make_context()
        first = self.aggregator.evaluate(ctx)
        second = self.aggregator.evaluate(ctx)
        self.assertEqual(first.new_positions_allowed, second.new_positions_allowed)
        self.assertEqual(first.confidence, second.confidence)
        self.assertEqual(first.summary, second.summary)
        self.assertEqual(first.metadata, second.metadata)

    def test_sequential_order_preserved_in_metadata(self):
        result = self.aggregator.evaluate(make_context())
        self.assertEqual(list(result.metadata["components"]), ["A", "B"])

    def test_managers_available_and_missing_are_sorted(self):
        aggregator = PortfolioAggregator(
            managers=[
                _FakePortfolioManager(name="Z", allowed=True, confidence=0.9),
                _FakePortfolioManager(name="Y", unavailable=True),
                _FakePortfolioManager(name="A", allowed=True, confidence=0.5),
            ]
        )
        result = aggregator.evaluate(make_context())
        self.assertEqual(result.metadata["managers_available"], ["A", "Z"])
        self.assertEqual(result.metadata["managers_missing"], ["Y"])


# ----------------------------------------------------------------------
# Integration -- real BasicPortfolioManager instances (Part 2)
# ----------------------------------------------------------------------
class TestRealBasicPortfolioManagerIntegration(unittest.TestCase):
    def test_two_agreeing_basic_managers_yield_allowed(self):
        portfolio = make_portfolio()
        ctx = make_context(
            portfolio=portfolio,
            strategy_result=make_strategy_result(action=SignalDirection.BUY, confidence=0.8),
            risk_result=make_risk_result(approved=True, confidence=0.8),
        )
        aggregator = PortfolioAggregator(
            managers=[
                BasicPortfolioManager(name="Loose", max_open_positions=20),
                BasicPortfolioManager(name="Strict", max_open_positions=5),
            ]
        )
        result = aggregator.evaluate(ctx)
        self.assertIsInstance(result, PortfolioResult)
        self.assertTrue(result.new_positions_allowed)
        self.assertGreater(result.confidence, 0.0)
        self.assertIn("Loose", result.metadata["managers_available"])
        self.assertIn("Strict", result.metadata["managers_available"])

    def test_disagreeing_basic_managers_reduce_agreement(self):
        # Four open positions: one BasicPortfolioManager with a limit
        # of 3 blocks on open-position count, another with a limit of
        # 10 does not -- the two real BasicPortfolioManager instances
        # genuinely disagree.
        positions = [
            make_position(quantity=Decimal("1"), entry_price=Decimal("100")) for _ in range(4)
        ]
        portfolio = make_portfolio(positions=positions, total_equity=Decimal("100000"))
        ctx = make_context(portfolio=portfolio)

        aggregator = PortfolioAggregator(
            managers=[
                BasicPortfolioManager(name="Tight", max_open_positions=3),
                BasicPortfolioManager(name="Loose", max_open_positions=10),
            ]
        )
        result = aggregator.evaluate(ctx)
        self.assertLess(result.metadata["agreement"], 1.0)

    def test_all_basic_managers_blocking_yields_blocked(self):
        positions = [
            make_position(quantity=Decimal("1"), entry_price=Decimal("100")) for _ in range(4)
        ]
        portfolio = make_portfolio(positions=positions, total_equity=Decimal("100000"))
        ctx = make_context(portfolio=portfolio)

        aggregator = PortfolioAggregator(
            managers=[
                BasicPortfolioManager(name="Tight1", max_open_positions=2),
                BasicPortfolioManager(name="Tight2", max_open_positions=3),
            ]
        )
        result = aggregator.evaluate(ctx)
        self.assertFalse(result.new_positions_allowed)
        self.assertEqual(result.metadata["agreement"], 1.0)

    def test_default_construction_uses_real_basic_portfolio_manager(self):
        ctx = make_context(
            strategy_result=make_strategy_result(action=SignalDirection.BUY, confidence=0.8),
            risk_result=make_risk_result(approved=True, confidence=0.8),
        )
        result = PortfolioAggregator().evaluate(ctx)
        self.assertTrue(result.new_positions_allowed)

    def test_basic_manager_insufficient_data_treated_as_unavailable(self):
        # A Portfolio whose equity cannot be computed makes
        # BasicPortfolioManager raise InsufficientPortfolioDataError;
        # PortfolioAggregator must treat that as "unavailable" for
        # that sub-manager rather than failing the whole aggregation,
        # as long as at least one other sub-manager can still evaluate.
        broken_portfolio = make_portfolio(cash_balance=None, total_equity=None)  # type: ignore[arg-type]
        ctx = make_context(portfolio=broken_portfolio)

        aggregator = PortfolioAggregator(
            managers=[
                BasicPortfolioManager(name="NeedsEquity"),
                _FakePortfolioManager(name="Fallback", allowed=True, confidence=0.5),
            ]
        )
        result = aggregator.evaluate(ctx)
        self.assertIn("NeedsEquity", result.metadata["managers_missing"])
        self.assertIn("Fallback", result.metadata["managers_available"])

    def test_all_basic_managers_insufficient_data_raises(self):
        broken_portfolio = make_portfolio(cash_balance=None, total_equity=None)  # type: ignore[arg-type]
        ctx = make_context(portfolio=broken_portfolio)

        aggregator = PortfolioAggregator(managers=[BasicPortfolioManager()])
        with self.assertRaises(InsufficientPortfolioDataError):
            aggregator.evaluate(ctx)


# ----------------------------------------------------------------------
# Independence -- PortfolioAggregator vs. PortfolioManager (Part 3)
# ----------------------------------------------------------------------
class TestIndependenceFromPortfolioManager(unittest.TestCase):
    """
    `aggregator.py` (Part 4) documents that it is a sibling of
    `portfolio_manager.py` (Part 3), not a wrapper or subclass of it --
    both combine `BasePortfolioManager` instances independently, and
    neither imports the other. These tests confirm that boundary holds
    at the module/class level, not just in the docstring.
    """

    def test_portfolio_aggregator_module_does_not_import_portfolio_manager_module(self):
        import strategies.portfolio_management.aggregator as aggregator_module

        self.assertNotIn("PortfolioManager", dir(aggregator_module))

    def test_portfolio_aggregator_is_not_a_portfolio_manager_subclass(self):
        from strategies.portfolio_management.portfolio_manager import (
            PortfolioManager as _PortfolioManagerClass,
        )

        self.assertFalse(issubclass(PortfolioAggregator, _PortfolioManagerClass))
        self.assertFalse(issubclass(_PortfolioManagerClass, PortfolioAggregator))

    def test_portfolio_aggregator_and_portfolio_manager_are_both_base_portfolio_managers(self):
        from strategies.portfolio_management.portfolio_manager import (
            PortfolioManager as _PortfolioManagerClass,
        )

        self.assertIsInstance(PortfolioAggregator(), BasePortfolioManager)
        self.assertIsInstance(_PortfolioManagerClass(), BasePortfolioManager)

    def test_portfolio_aggregator_can_be_nested_as_a_sub_manager_of_itself(self):
        # PortfolioAggregator is itself a BasePortfolioManager, so it
        # must be injectable as a sub-manager of another
        # PortfolioAggregator.
        inner = PortfolioAggregator(
            managers=[_FakePortfolioManager(name="Inner", allowed=True, confidence=0.9)],
            name="Inner-Aggregator",
        )
        outer = PortfolioAggregator(managers=[inner], name="Outer-Aggregator")
        result = outer.evaluate(make_context())
        self.assertTrue(result.new_positions_allowed)
        self.assertIn("Inner-Aggregator", result.metadata["managers_available"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
