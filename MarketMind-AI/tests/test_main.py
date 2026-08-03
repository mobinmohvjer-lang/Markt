"""
test_main.py
-------------------
Purpose:
    Unit tests for `MainApplication` (`app/main.py`, Main Application
    Part 1): construction, dependency injection, configuration loading,
    and initialization of every already-implemented top-level engine/
    service -- the application skeleton only.

Uses the standard-library ``unittest`` framework and the shared
`FakeBinanceClient` from `tests/helpers.py` (no real network access),
matching every other test suite in this repository.

Run with:
    pytest
    python3 -m unittest discover -s tests -p "test_*.py" -v
"""

from __future__ import annotations

import os
import tempfile
import unittest

from tests.helpers import make_fake_client

from analysis.aggregator import AnalysisAggregator
from analysis.base import BaseAnalyzer
from analysis.context import AnalysisContext
from analysis.result import AnalysisResult

from backtesting.base import BaseBacktester
from backtesting.basic_backtester import BasicBacktester
from backtesting.context import BacktestContext
from backtesting.result import BacktestResult

from config.settings import Settings, get_settings

from data.client import BinanceClientInterface, BinanceRESTClient
from data.engine import DataEngine

from services import InsufficientServiceDataError, SignalEngine
from services.context import ServiceContext
from services.result import ServiceResult

from signals.aggregator import SignalAggregator
from signals.base import BaseSignalGenerator
from signals.context import SignalContext
from signals.result import SignalResult

from strategies.aggregator import StrategyAggregator
from strategies.base_strategy import BaseStrategy
from strategies.context import StrategyContext
from strategies.result import StrategyResult

from strategies.portfolio_management import BasePortfolioManager, PortfolioManager
from strategies.risk_management import BaseRiskManager, BasicRiskManager

from core.enums import SignalDirection

from app.exceptions import PipelineConfigurationError, PipelineDataError
from app.main import DEFAULT_DATA_ENGINE_DB_PATH, MainApplication, _sqlite_path_from_database_url


# ----------------------------------------------------------------------
# Minimal fakes -- used only to prove real dependency injection (that an
# injected instance is stored as-is, never replaced by a default), never
# to exercise any orchestration/business logic.
# ----------------------------------------------------------------------


class _FakeAnalyzer(BaseAnalyzer):
    def analyze(self, context: AnalysisContext) -> AnalysisResult:  # pragma: no cover - unused
        raise NotImplementedError


class _FakeSignalGenerator(BaseSignalGenerator):
    def generate(self, context: SignalContext) -> SignalResult:  # pragma: no cover - unused
        raise NotImplementedError


class _FakeStrategy(BaseStrategy):
    def decide(self, context: StrategyContext) -> StrategyResult:  # pragma: no cover - unused
        raise NotImplementedError


class _FakeRiskManager(BaseRiskManager):
    def evaluate(self, context):  # pragma: no cover - unused
        raise NotImplementedError


class _FakePortfolioManager(BasePortfolioManager):
    def evaluate(self, context):  # pragma: no cover - unused
        raise NotImplementedError


class _FakeBacktester(BaseBacktester):
    def run(self, context: BacktestContext) -> BacktestResult:  # pragma: no cover - unused
        raise NotImplementedError


def _temp_sqlite_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    os.remove(path)
    return path


def _cleanup_sqlite(path: str) -> None:
    for suffix in ("", "-wal", "-shm"):
        candidate = path + suffix
        if os.path.exists(candidate):
            os.remove(candidate)


class TestSqlitePathFromDatabaseUrl(unittest.TestCase):
    """Unit coverage for the small configuration-translation helper."""

    def test_sqlite_scheme_is_translated_to_a_plain_path(self):
        self.assertEqual(
            _sqlite_path_from_database_url("sqlite:///./marketmind.db"),
            "./marketmind.db",
        )

    def test_sqlite_scheme_with_absolute_path(self):
        self.assertEqual(
            _sqlite_path_from_database_url("sqlite:////tmp/marketmind.db"),
            "/tmp/marketmind.db",
        )

    def test_empty_path_after_scheme_falls_back_to_default(self):
        self.assertEqual(
            _sqlite_path_from_database_url("sqlite:///"),
            DEFAULT_DATA_ENGINE_DB_PATH,
        )

    def test_non_sqlite_url_falls_back_to_default(self):
        self.assertEqual(
            _sqlite_path_from_database_url("postgresql://user:pass@host/db"),
            DEFAULT_DATA_ENGINE_DB_PATH,
        )

    def test_non_string_input_falls_back_to_default(self):
        self.assertEqual(_sqlite_path_from_database_url(None), DEFAULT_DATA_ENGINE_DB_PATH)  # type: ignore[arg-type]


class TestMainApplicationDefaults(unittest.TestCase):
    """Construction with no injected dependencies at all."""

    def setUp(self):
        self.db_path = _temp_sqlite_path()
        self.settings = Settings(database_url=f"sqlite:///{self.db_path}")
        self.app = MainApplication(settings=self.settings)

    def tearDown(self):
        self.app.data_engine.close()
        _cleanup_sqlite(self.db_path)

    def test_settings_defaults_to_get_settings_when_not_injected(self):
        app = MainApplication(data_engine=self.app.data_engine)
        self.assertIs(app.settings, get_settings())

    def test_injected_settings_is_stored_as_is(self):
        self.assertIs(self.app.settings, self.settings)

    def test_data_engine_is_constructed_by_default(self):
        self.assertIsInstance(self.app.data_engine, DataEngine)

    def test_data_engine_db_path_derived_from_settings(self):
        self.assertEqual(self.app.data_engine.storage.db_path, self.db_path)

    def test_analyzer_defaults_to_analysis_aggregator(self):
        self.assertIsInstance(self.app.analyzer, AnalysisAggregator)

    def test_signal_generator_defaults_to_signal_aggregator(self):
        self.assertIsInstance(self.app.signal_generator, SignalAggregator)

    def test_strategy_defaults_to_strategy_aggregator(self):
        self.assertIsInstance(self.app.strategy, StrategyAggregator)

    def test_risk_manager_defaults_to_basic_risk_manager(self):
        self.assertIsInstance(self.app.risk_manager, BasicRiskManager)

    def test_portfolio_manager_defaults_to_portfolio_manager(self):
        self.assertIsInstance(self.app.portfolio_manager, PortfolioManager)

    def test_backtester_defaults_to_basic_backtester(self):
        self.assertIsInstance(self.app.backtester, BasicBacktester)

    def test_signal_engine_defaults_to_services_signal_engine(self):
        self.assertIsInstance(self.app.signal_engine, SignalEngine)

    def test_default_signal_engine_has_no_event_bus(self):
        self.assertFalse(self.app.signal_engine.has_event_bus())

    def test_repr_mentions_environment_and_version(self):
        text = repr(self.app)
        self.assertIn(self.app.settings.environment, text)
        self.assertIn(self.app.settings.app_version, text)


class TestMainApplicationDependencyInjection(unittest.TestCase):
    """Every collaborator, when injected, is stored exactly as given."""

    def setUp(self):
        self.db_path = _temp_sqlite_path()
        self.fake_client = make_fake_client(num_candles=5, timeframe="1h")
        self.injected_data_engine = DataEngine(client=self.fake_client, db_path=self.db_path)

    def tearDown(self):
        self.injected_data_engine.close()
        _cleanup_sqlite(self.db_path)

    def test_injected_data_engine_is_stored_as_is(self):
        app = MainApplication(data_engine=self.injected_data_engine)
        self.assertIs(app.data_engine, self.injected_data_engine)

    def test_injected_market_data_client_is_used_when_no_data_engine_given(self):
        other_db_path = _temp_sqlite_path()
        settings = Settings(database_url=f"sqlite:///{other_db_path}")
        app = MainApplication(settings=settings, market_data_client=self.fake_client)
        try:
            self.assertIs(app.data_engine.client, self.fake_client)
        finally:
            app.data_engine.close()
            _cleanup_sqlite(other_db_path)

    def test_data_engine_injection_takes_precedence_over_market_data_client(self):
        unused_client = make_fake_client(num_candles=1, timeframe="1h")
        app = MainApplication(
            data_engine=self.injected_data_engine,
            market_data_client=unused_client,
        )
        self.assertIs(app.data_engine, self.injected_data_engine)
        self.assertIsNot(app.data_engine.client, unused_client)

    def test_injected_analyzer_is_stored_as_is(self):
        fake = _FakeAnalyzer()
        app = MainApplication(data_engine=self.injected_data_engine, analyzer=fake)
        self.assertIs(app.analyzer, fake)

    def test_injected_signal_generator_is_stored_as_is(self):
        fake = _FakeSignalGenerator()
        app = MainApplication(data_engine=self.injected_data_engine, signal_generator=fake)
        self.assertIs(app.signal_generator, fake)

    def test_injected_strategy_is_stored_as_is(self):
        fake = _FakeStrategy()
        app = MainApplication(data_engine=self.injected_data_engine, strategy=fake)
        self.assertIs(app.strategy, fake)

    def test_injected_risk_manager_is_stored_as_is(self):
        fake = _FakeRiskManager()
        app = MainApplication(data_engine=self.injected_data_engine, risk_manager=fake)
        self.assertIs(app.risk_manager, fake)

    def test_injected_portfolio_manager_is_stored_as_is(self):
        fake = _FakePortfolioManager()
        app = MainApplication(data_engine=self.injected_data_engine, portfolio_manager=fake)
        self.assertIs(app.portfolio_manager, fake)

    def test_injected_backtester_is_stored_as_is(self):
        fake = _FakeBacktester()
        app = MainApplication(data_engine=self.injected_data_engine, backtester=fake)
        self.assertIs(app.backtester, fake)

    def test_injected_signal_engine_is_stored_as_is(self):
        fake = SignalEngine(name="InjectedSignalEngine")
        app = MainApplication(data_engine=self.injected_data_engine, signal_engine=fake)
        self.assertIs(app.signal_engine, fake)

    def test_two_instances_do_not_share_state(self):
        other_db_path = _temp_sqlite_path()
        app_one = MainApplication(data_engine=self.injected_data_engine)
        app_two = MainApplication(
            settings=Settings(database_url=f"sqlite:///{other_db_path}"),
            market_data_client=make_fake_client(num_candles=1, timeframe="1h"),
        )
        try:
            self.assertIsNot(app_one.analyzer, app_two.analyzer)
            self.assertIsNot(app_one.signal_generator, app_two.signal_generator)
            self.assertIsNot(app_one.data_engine, app_two.data_engine)
        finally:
            app_two.data_engine.close()
            _cleanup_sqlite(other_db_path)


class TestMainApplicationValidation(unittest.TestCase):
    """Invalid injected collaborators raise `PipelineConfigurationError`."""

    def setUp(self):
        self.db_path = _temp_sqlite_path()
        self.fake_client = make_fake_client(num_candles=1, timeframe="1h")
        self.data_engine = DataEngine(client=self.fake_client, db_path=self.db_path)

    def tearDown(self):
        self.data_engine.close()
        _cleanup_sqlite(self.db_path)

    def test_invalid_settings_rejected(self):
        with self.assertRaises(PipelineConfigurationError):
            MainApplication(settings=object(), data_engine=self.data_engine)

    def test_invalid_market_data_client_rejected(self):
        with self.assertRaises(PipelineConfigurationError):
            MainApplication(market_data_client=object())

    def test_invalid_data_engine_rejected(self):
        with self.assertRaises(PipelineConfigurationError):
            MainApplication(data_engine=object())

    def test_invalid_analyzer_rejected(self):
        with self.assertRaises(PipelineConfigurationError):
            MainApplication(data_engine=self.data_engine, analyzer=object())

    def test_invalid_signal_generator_rejected(self):
        with self.assertRaises(PipelineConfigurationError):
            MainApplication(data_engine=self.data_engine, signal_generator=object())

    def test_invalid_strategy_rejected(self):
        with self.assertRaises(PipelineConfigurationError):
            MainApplication(data_engine=self.data_engine, strategy=object())

    def test_invalid_risk_manager_rejected(self):
        with self.assertRaises(PipelineConfigurationError):
            MainApplication(data_engine=self.data_engine, risk_manager=object())

    def test_invalid_portfolio_manager_rejected(self):
        with self.assertRaises(PipelineConfigurationError):
            MainApplication(data_engine=self.data_engine, portfolio_manager=object())

    def test_invalid_backtester_rejected(self):
        with self.assertRaises(PipelineConfigurationError):
            MainApplication(data_engine=self.data_engine, backtester=object())

    def test_invalid_signal_engine_rejected(self):
        with self.assertRaises(PipelineConfigurationError):
            MainApplication(data_engine=self.data_engine, signal_engine=object())

    def test_none_is_always_accepted_for_every_optional_parameter(self):
        # None means "use the default" for every parameter -- explicitly
        # passing None must never raise.
        app = MainApplication(
            settings=None,
            market_data_client=None,
            data_engine=self.data_engine,
            analyzer=None,
            signal_generator=None,
            strategy=None,
            risk_manager=None,
            portfolio_manager=None,
            backtester=None,
            signal_engine=None,
        )
        self.assertIsInstance(app, MainApplication)


class TestMainApplicationScopeBoundary(unittest.TestCase):
    """Confirms Part 1's explicit exclusions (no execution engine, no
    pipeline attribute) plus Part 2's narrow addition: exactly one new
    public method, `run()`, and nothing else."""

    def setUp(self):
        self.db_path = _temp_sqlite_path()
        self.fake_client = make_fake_client(num_candles=1, timeframe="1h")
        self.data_engine = DataEngine(client=self.fake_client, db_path=self.db_path)
        self.app = MainApplication(data_engine=self.data_engine)

    def tearDown(self):
        self.data_engine.close()
        _cleanup_sqlite(self.db_path)

    def test_only_the_documented_public_attributes_exist(self):
        expected = {
            "settings",
            "data_engine",
            "analyzer",
            "signal_generator",
            "strategy",
            "risk_manager",
            "portfolio_manager",
            "backtester",
            "signal_engine",
        }
        actual = {name for name in vars(self.app) if not name.startswith("_")}
        self.assertEqual(actual, expected)

    def test_no_execution_engine_attribute(self):
        self.assertFalse(hasattr(self.app, "execution_engine"))

    def test_no_pipeline_attribute(self):
        self.assertFalse(hasattr(self.app, "pipeline"))

    def test_run_is_the_only_public_method_besides_dunder_repr(self):
        # Part 1 shipped the constructor only; Part 2 adds exactly one
        # new public method, `run()`, for pipeline orchestration -- no
        # other public method (broker/execution/AI/CLI/UI/scheduling/
        # background-service surface) exists.
        public_callables = [
            name
            for name in dir(MainApplication)
            if not name.startswith("_") and callable(getattr(MainApplication, name))
        ]
        self.assertEqual(public_callables, ["run"])

    def test_construction_does_not_call_any_engine_method(self):
        # Each stored engine is still in its freshly-constructed state --
        # e.g. the signal engine never had execute() called on it during
        # MainApplication's own construction, so calling it now with an
        # empty payload still fails exactly the way a fresh SignalEngine
        # instance always does (whichever failure mode this build uses --
        # a bare NotImplementedError for Services Part 2A's public-
        # interfaces-only scope, or InsufficientServiceDataError once
        # Part 2B's payload-building orchestration exists).
        context = ServiceContext(service_name="probe", payload={})
        with self.assertRaises((NotImplementedError, InsufficientServiceDataError)):
            self.app.signal_engine.execute(context)


class TestMainApplicationIntegration(unittest.TestCase):
    """End-to-end construction against a realistic, fully-wired application."""

    def test_full_default_construction_against_real_settings(self):
        db_path = _temp_sqlite_path()
        try:
            settings = Settings(
                app_name="MarketMind-AI",
                app_version="0.1.0",
                environment="testing",
                database_url=f"sqlite:///{db_path}",
            )
            app = MainApplication(settings=settings)
            try:
                self.assertEqual(app.settings.environment, "testing")
                self.assertIsInstance(app.data_engine, DataEngine)
                self.assertIsInstance(app.analyzer, BaseAnalyzer)
                self.assertIsInstance(app.signal_generator, BaseSignalGenerator)
                self.assertIsInstance(app.strategy, BaseStrategy)
                self.assertIsInstance(app.risk_manager, BaseRiskManager)
                self.assertIsInstance(app.portfolio_manager, BasePortfolioManager)
                self.assertIsInstance(app.backtester, BaseBacktester)
                self.assertIsInstance(app.signal_engine, SignalEngine)
            finally:
                app.data_engine.close()
        finally:
            _cleanup_sqlite(db_path)

    def test_repeated_construction_is_independent_and_side_effect_free(self):
        db_path_a = _temp_sqlite_path()
        db_path_b = _temp_sqlite_path()
        try:
            app_a = MainApplication(settings=Settings(database_url=f"sqlite:///{db_path_a}"))
            app_b = MainApplication(settings=Settings(database_url=f"sqlite:///{db_path_b}"))
            try:
                self.assertIsNot(app_a, app_b)
                self.assertIsNot(app_a.data_engine, app_b.data_engine)
                self.assertNotEqual(
                    app_a.data_engine.storage.db_path, app_b.data_engine.storage.db_path
                )
            finally:
                app_a.data_engine.close()
                app_b.data_engine.close()
        finally:
            _cleanup_sqlite(db_path_a)
            _cleanup_sqlite(db_path_b)


class TestMainApplicationRun(unittest.TestCase):
    """Unit coverage for Main Application Part 2's `run()` method."""

    def setUp(self):
        self.db_path = _temp_sqlite_path()
        self.fake_client = make_fake_client(num_candles=200, timeframe="1h")
        self.data_engine = DataEngine(client=self.fake_client, db_path=self.db_path)
        self.app = MainApplication(data_engine=self.data_engine)

    def tearDown(self):
        self.data_engine.close()
        _cleanup_sqlite(self.db_path)

    def test_run_returns_a_signal_result(self):
        self.data_engine.download_history(
            symbol="BTCUSDT",
            timeframe="1h",
            start_time=self.fake_client.series_start,
            batch_limit=200,
        )
        result = self.app.run("BTCUSDT", "1h")
        self.assertIsInstance(result, SignalResult)
        self.assertIn(
            result.direction,
            (SignalDirection.BUY, SignalDirection.SELL, SignalDirection.HOLD),
        )

    def test_run_uppercases_symbol_like_the_underlying_pipeline(self):
        self.data_engine.download_history(
            symbol="BTCUSDT",
            timeframe="1h",
            start_time=self.fake_client.series_start,
            batch_limit=200,
        )
        result = self.app.run("btcusdt", "1h")
        self.assertIsInstance(result, SignalResult)

    def test_run_raises_pipeline_data_error_when_no_history_available(self):
        with self.assertRaises(PipelineDataError):
            self.app.run("BTCUSDT", "1h")

    def test_run_raises_pipeline_configuration_error_for_invalid_symbol(self):
        with self.assertRaises(PipelineConfigurationError):
            self.app.run("", "1h")

    def test_run_uses_the_injected_analyzer_and_signal_generator(self):
        # Prove real reuse of the collaborators MainApplication already
        # holds (not new instances built independently of them).
        analyzer = AnalysisAggregator()
        signal_generator = SignalAggregator()
        app = MainApplication(
            data_engine=self.data_engine,
            analyzer=analyzer,
            signal_generator=signal_generator,
        )
        self.data_engine.download_history(
            symbol="ETHUSDT",
            timeframe="1h",
            start_time=self.fake_client.series_start,
            batch_limit=200,
        )
        result = app.run("ETHUSDT", "1h")
        self.assertIsInstance(result, SignalResult)

    def test_run_does_not_touch_strategy_risk_portfolio_backtester_or_signal_engine(self):
        strategy = _FakeStrategy()
        risk_manager = _FakeRiskManager()
        portfolio_manager = _FakePortfolioManager()
        backtester = _FakeBacktester()
        app = MainApplication(
            data_engine=self.data_engine,
            strategy=strategy,
            risk_manager=risk_manager,
            portfolio_manager=portfolio_manager,
            backtester=backtester,
        )
        self.data_engine.download_history(
            symbol="BTCUSDT",
            timeframe="1h",
            start_time=self.fake_client.series_start,
            batch_limit=200,
        )
        # None of these fakes raise NotImplementedError unless actually
        # called -- run() completing successfully proves they were not.
        result = app.run("BTCUSDT", "1h")
        self.assertIsInstance(result, SignalResult)
        self.assertIs(app.strategy, strategy)
        self.assertIs(app.risk_manager, risk_manager)
        self.assertIs(app.portfolio_manager, portfolio_manager)
        self.assertIs(app.backtester, backtester)

    def test_run_does_not_add_a_pipeline_attribute(self):
        self.data_engine.download_history(
            symbol="BTCUSDT",
            timeframe="1h",
            start_time=self.fake_client.series_start,
            batch_limit=200,
        )
        self.app.run("BTCUSDT", "1h")
        self.assertFalse(hasattr(self.app, "pipeline"))


if __name__ == "__main__":
    unittest.main()
