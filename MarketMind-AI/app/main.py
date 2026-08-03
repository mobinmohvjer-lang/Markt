"""
app/main.py

Defines `MainApplication`: the application's composition root -- the
single object that holds one instance of every already-implemented
top-level engine/service in this repository, wired together via
dependency injection.

Scope (Main Application Part 1 -- deliberately bounded)
---------------------------------------------------------
Part 1 shipped **only** `MainApplication`'s public interfaces, per that
milestone's explicit instructions:

    - **Constructor only.** No other public method was added.
    - **Dependency injection only.** Every collaborator is an optional
      constructor parameter; a caller may inject a real instance, a fake
      (for tests), or omit it entirely and receive a sensible default --
      the same convention every engine in this repository already
      follows (`MarketPipeline`, `AnalysisAggregator`, `SignalAggregator`,
      `StrategyAggregator`, `BasicRiskManager`, `PortfolioManager`,
      `BasicBacktester`, `services.SignalEngine`, ...).
    - **Configuration loading only.** `config.settings.get_settings()` is
      read (or an injected `Settings` instance is used) and its
      `database_url` is translated into the local SQLite path the
      default `DataEngine` is constructed with. No other use of
      configuration is made.
    - **Initializes existing engines/services only.** Every attribute
      this class sets is either an injected instance or a plain,
      no-argument (or config-derived) construction of an already-shipped
      concrete class from this repository -- nothing new is computed,
      combined, or decided here.

Part 1's constructor never calls any engine's `run()`/`analyze()`/
`generate()`/`decide()`/`evaluate()`/`execute()` method -- it only
constructs and stores each engine as an attribute, exactly like
`MarketPipeline.__init__` already does for its own four collaborators
(`app/pipeline.py`).

Scope (Main Application Part 2 -- this milestone, deliberately bounded)
-------------------------------------------------------------------------
Part 2 adds exactly **one** public method: `run(symbol, timeframe)`.

    - **Orchestration only, of the already-existing pipeline.** `run()`
      builds an `app.pipeline.MarketPipeline` -- the Data -> Indicators
      -> Analysis -> Signals use case that already exists in this
      repository -- from the collaborators `MainApplication.__init__`
      already constructed/injected (`self.data_engine`, `self.analyzer`,
      `self.signal_generator`), calls its existing `.run(symbol,
      timeframe)` in the fixed order it already implements, and returns
      the resulting final `signals.result.SignalResult`.
    - **No new business logic.** `run()` computes nothing itself -- it
      only instantiates and calls `MarketPipeline`, exactly as documented
      in `app/pipeline.py`; every calculation/interpretation/decision
      still happens inside the package that already owns it
      (`indicators/`, `analysis/`, `signals/`).
    - **No broker, no execution engine, no AI, no CLI, no UI, no
      scheduling, no background service.** `self.strategy`,
      `self.risk_manager`, `self.portfolio_manager`, `self.backtester`,
      and `self.signal_engine` are untouched by `run()` -- assembling a
      `StrategyContext`/`RiskContext`/`PortfolioContext`/
      `ExecutionContext` from real Signal Engine output remains the
      future `app/`-layer wiring work `PROJECT_STATE.md`'s "Next
      recommended milestone" item 8 already documents; only the
      Data -> Indicators -> Analysis -> Signals stage `MarketPipeline`
      already implements is sequenced here.
    - **No new modules.** Only `app/main.py` (this file) is modified;
      `app/pipeline.py` (`MarketPipeline`), `data.engine.DataEngine`,
      `analysis.base.BaseAnalyzer`, and `signals.base.BaseSignalGenerator`
      are reused exactly as they already exist.

**No analysis execution, no AI, no broker, no UI, no CLI, no business
logic.** This module contains no calculation, interpretation, or
decision logic of its own -- every engine it references already owns
its own behavior; `MainApplication` only composes references to them.
No networking beyond what an injected/default collaborator's own
constructor already performs (e.g. `data.client.BinanceRESTClient()`
opening a local `requests.Session()` -- no request is made until a
method is called, which this class never does).

Which engines are composed
---------------------------
One instance of each already-*concrete* top-level engine/service this
repository ships, matching `PROJECT_STATE.md`'s "Completed"/first
concrete implementation for each layer:

    - `config.settings.Settings`             (configuration)
    - `data.engine.DataEngine`                (Data Engine)
    - `analysis.aggregator.AnalysisAggregator`      (Analysis Engine)
    - `signals.aggregator.SignalAggregator`         (Signal Engine)
    - `strategies.aggregator.StrategyAggregator`    (Strategy Engine)
    - `strategies.risk_management.BasicRiskManager` (Risk Engine)
    - `strategies.portfolio_management.PortfolioManager` (Portfolio Mgmt)
    - `backtesting.BasicBacktester`                 (Backtesting Engine)
    - `services.SignalEngine`                       (Services -- Part 2A)

`execution/` (Execution Engine Part 1) is deliberately **not**
instantiated here: it ships only an abstract `BaseExecutionEngine` --
no concrete implementation exists anywhere in the repository yet (see
`PROJECT_STATE.md`, "Next recommended milestone", item 0) -- and this
class only initializes engines/services that already exist in concrete
form. The same is true of a concrete `events.interfaces.event_bus.
EventBus`: none exists yet, so `services.SignalEngine` is constructed
with `event_bus=None`, exactly as `services.signal_engine.SignalEngine`
itself already defaults to.

`app.pipeline.MarketPipeline` (the existing Data -> Indicators ->
Analysis -> Signals use case) is also not composed here. Building one
requires a `DataEngine` plus (optionally) an analyzer/signal generator,
all of which `MainApplication` already holds -- wiring a `MarketPipeline`
instance from them is exactly the kind of sequencing/orchestration this
part explicitly excludes, so it is left to the future part that adds
`MainApplication`'s own orchestration behavior.

Reuses `config.settings`, `data.client`, `data.engine`,
`analysis.aggregator`, `analysis.base`, `signals.aggregator`,
`signals.base`, `strategies.aggregator`, `strategies.base_strategy`,
`strategies.risk_management`, `strategies.portfolio_management`,
`backtesting`, and `services` exactly as they already exist -- no
existing implementation file is modified by this module.
"""

from __future__ import annotations

from typing import Optional

from analysis import AnalysisAggregator, BaseAnalyzer
from backtesting import BaseBacktester, BasicBacktester
from config.settings import Settings, get_settings
from data.client import BinanceClientInterface, BinanceRESTClient
from data.engine import DataEngine
from services import SignalEngine
from signals import BaseSignalGenerator, SignalAggregator
from signals.result import SignalResult
from strategies import BaseStrategy, StrategyAggregator
from strategies.portfolio_management import BasePortfolioManager, PortfolioManager
from strategies.risk_management import BaseRiskManager, BasicRiskManager

from app.exceptions import PipelineConfigurationError
from app.pipeline import MarketPipeline

#: Default local SQLite file used for the Data Engine's candle storage
#: when neither a `data_engine` nor a `market_data_client`/explicit
#: path override is injected, and `Settings.database_url` does not use
#: the `sqlite:///` scheme (see `_sqlite_path_from_database_url`).
DEFAULT_DATA_ENGINE_DB_PATH = "market_data.sqlite3"


def _sqlite_path_from_database_url(database_url: str) -> str:
    """
    Translate `Settings.database_url` (e.g. `"sqlite:///./marketmind.db"`)
    into the plain filesystem path `data.engine.DataEngine` expects for
    its `db_path` parameter.

    This is configuration *loading* only -- reading an already-computed
    setting and reformatting it for an existing engine's constructor
    parameter -- not new business logic. Any `database_url` that is not
    a `sqlite:///`-scheme URL (e.g. a future PostgreSQL URL for the
    still-stub `database/` package) falls back to
    `DEFAULT_DATA_ENGINE_DB_PATH`, since `DataEngine` only ever speaks
    SQLite today.
    """
    prefix = "sqlite:///"
    if isinstance(database_url, str) and database_url.startswith(prefix):
        path = database_url[len(prefix):]
        return path or DEFAULT_DATA_ENGINE_DB_PATH
    return DEFAULT_DATA_ENGINE_DB_PATH


class MainApplication:
    """
    Composition root holding one instance of every already-implemented
    top-level engine/service, wired together via dependency injection.

    Every collaborator is an optional, keyword-only constructor
    parameter. Omitting one constructs a plain, default instance of the
    corresponding concrete class already shipped elsewhere in this
    repository; supplying one (a real instance or a test fake) is
    validated against the same abstract base that engine's own
    ecosystem already uses.

    Parameters
    ----------
    settings:
        Application configuration. Defaults to
        `config.settings.get_settings()`.
    market_data_client:
        Optional `data.client.BinanceClientInterface` used to construct
        the default `DataEngine` when `data_engine` itself is not
        injected. Ignored if `data_engine` is supplied directly.
        Defaults to `data.client.BinanceRESTClient()`.
    data_engine:
        The Data Engine facade. Defaults to a `data.engine.DataEngine`
        built from `market_data_client` (or its own default) and a
        `db_path` derived from `settings.database_url`.
    analyzer:
        The Analysis Engine entry point. Defaults to
        `analysis.aggregator.AnalysisAggregator()`.
    signal_generator:
        The Signal Engine entry point. Defaults to
        `signals.aggregator.SignalAggregator()`.
    strategy:
        The Strategy Engine entry point. Defaults to
        `strategies.aggregator.StrategyAggregator()`.
    risk_manager:
        The Risk Engine entry point. Defaults to
        `strategies.risk_management.BasicRiskManager()`.
    portfolio_manager:
        The Portfolio Management entry point. Defaults to
        `strategies.portfolio_management.PortfolioManager()`.
    backtester:
        The Backtesting Engine entry point. Defaults to
        `backtesting.BasicBacktester()`.
    signal_engine:
        The `services/` Signal Engine (Services Part 2A). Defaults to
        `services.SignalEngine()` (no `EventBus` injected -- no concrete
        implementation exists anywhere in the repository yet).

    Raises
    ------
    app.exceptions.PipelineConfigurationError
        Any supplied collaborator is not `None` and not an instance of
        the type it is expected to be.

    Notes
    -----
    This constructor performs no I/O of its own beyond what an
    injected/default collaborator's own constructor already performs
    (e.g. opening a local `requests.Session()` inside the default
    `BinanceRESTClient`) -- no network request, no database query, no
    file write. It calls no engine's `run()`/`analyze()`/`generate()`/
    `decide()`/`evaluate()`/`execute()` method.
    """

    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        market_data_client: Optional[BinanceClientInterface] = None,
        data_engine: Optional[DataEngine] = None,
        analyzer: Optional[BaseAnalyzer] = None,
        signal_generator: Optional[BaseSignalGenerator] = None,
        strategy: Optional[BaseStrategy] = None,
        risk_manager: Optional[BaseRiskManager] = None,
        portfolio_manager: Optional[BasePortfolioManager] = None,
        backtester: Optional[BaseBacktester] = None,
        signal_engine: Optional[SignalEngine] = None,
    ) -> None:
        # ------------------------------------------------------------
        # Configuration loading
        # ------------------------------------------------------------
        if settings is not None and not isinstance(settings, Settings):
            raise PipelineConfigurationError(
                f"settings must be a Settings instance, got {type(settings).__name__}"
            )
        self.settings: Settings = settings if settings is not None else get_settings()

        # ------------------------------------------------------------
        # Data Engine (dependency injection)
        # ------------------------------------------------------------
        if market_data_client is not None and not isinstance(
            market_data_client, BinanceClientInterface
        ):
            raise PipelineConfigurationError(
                "market_data_client must be a BinanceClientInterface, got "
                f"{type(market_data_client).__name__}"
            )

        if data_engine is not None:
            if not isinstance(data_engine, DataEngine):
                raise PipelineConfigurationError(
                    f"data_engine must be a DataEngine, got {type(data_engine).__name__}"
                )
            self.data_engine: DataEngine = data_engine
        else:
            client = market_data_client if market_data_client is not None else BinanceRESTClient()
            self.data_engine = DataEngine(
                client=client,
                db_path=_sqlite_path_from_database_url(self.settings.database_url),
            )

        # ------------------------------------------------------------
        # Analysis Engine
        # ------------------------------------------------------------
        if analyzer is not None and not isinstance(analyzer, BaseAnalyzer):
            raise PipelineConfigurationError(
                f"analyzer must be a BaseAnalyzer, got {type(analyzer).__name__}"
            )
        self.analyzer: BaseAnalyzer = analyzer if analyzer is not None else AnalysisAggregator()

        # ------------------------------------------------------------
        # Signal Engine
        # ------------------------------------------------------------
        if signal_generator is not None and not isinstance(signal_generator, BaseSignalGenerator):
            raise PipelineConfigurationError(
                f"signal_generator must be a BaseSignalGenerator, got {type(signal_generator).__name__}"
            )
        self.signal_generator: BaseSignalGenerator = (
            signal_generator if signal_generator is not None else SignalAggregator()
        )

        # ------------------------------------------------------------
        # Strategy Engine
        # ------------------------------------------------------------
        if strategy is not None and not isinstance(strategy, BaseStrategy):
            raise PipelineConfigurationError(
                f"strategy must be a BaseStrategy, got {type(strategy).__name__}"
            )
        self.strategy: BaseStrategy = strategy if strategy is not None else StrategyAggregator()

        # ------------------------------------------------------------
        # Risk Engine
        # ------------------------------------------------------------
        if risk_manager is not None and not isinstance(risk_manager, BaseRiskManager):
            raise PipelineConfigurationError(
                f"risk_manager must be a BaseRiskManager, got {type(risk_manager).__name__}"
            )
        self.risk_manager: BaseRiskManager = (
            risk_manager if risk_manager is not None else BasicRiskManager()
        )

        # ------------------------------------------------------------
        # Portfolio Management
        # ------------------------------------------------------------
        if portfolio_manager is not None and not isinstance(portfolio_manager, BasePortfolioManager):
            raise PipelineConfigurationError(
                "portfolio_manager must be a BasePortfolioManager, got "
                f"{type(portfolio_manager).__name__}"
            )
        self.portfolio_manager: BasePortfolioManager = (
            portfolio_manager if portfolio_manager is not None else PortfolioManager()
        )

        # ------------------------------------------------------------
        # Backtesting Engine
        # ------------------------------------------------------------
        if backtester is not None and not isinstance(backtester, BaseBacktester):
            raise PipelineConfigurationError(
                f"backtester must be a BaseBacktester, got {type(backtester).__name__}"
            )
        self.backtester: BaseBacktester = backtester if backtester is not None else BasicBacktester()

        # ------------------------------------------------------------
        # Services -- SignalEngine (Services Part 2A)
        # ------------------------------------------------------------
        if signal_engine is not None and not isinstance(signal_engine, SignalEngine):
            raise PipelineConfigurationError(
                f"signal_engine must be a SignalEngine, got {type(signal_engine).__name__}"
            )
        self.signal_engine: SignalEngine = (
            signal_engine if signal_engine is not None else SignalEngine()
        )

    def run(self, symbol: str, timeframe: str) -> SignalResult:
        """
        Execute the existing Data -> Indicators -> Analysis -> Signals
        pipeline (`app.pipeline.MarketPipeline`) for one symbol/timeframe
        and return its final signal.

        This reuses `self.data_engine`, `self.analyzer`, and
        `self.signal_generator` -- already constructed/injected by
        `__init__` -- to build a `MarketPipeline` and calls its existing
        `.run(symbol, timeframe)` exactly as `app/pipeline.py` already
        implements it. No new calculation/interpretation/decision logic
        is added here; `self.strategy`, `self.risk_manager`,
        `self.portfolio_manager`, `self.backtester`, and
        `self.signal_engine` are not involved.

        Parameters
        ----------
        symbol, timeframe:
            Identify which already-downloaded candle series to run
            against (see `DataEngine.download_history`/`update_latest`).

        Returns
        -------
        signals.result.SignalResult
            The pipeline's final signal.

        Raises
        ------
        app.exceptions.PipelineConfigurationError
            `symbol`/`timeframe` are not non-empty strings.
        app.exceptions.PipelineDataError
            No candle history is available for `symbol`/`timeframe`.
        app.exceptions.PipelineAnalysisError
            The Analysis stage could not produce an `AnalysisResult`.
        app.exceptions.PipelineSignalError
            The Signals stage could not produce a `SignalResult`.
        """
        pipeline = MarketPipeline(
            self.data_engine,
            analyzer=self.analyzer,
            signal_generator=self.signal_generator,
        )
        pipeline_result = pipeline.run(symbol, timeframe)
        return pipeline_result.signal_result

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"{self.__class__.__name__}(environment={self.settings.environment!r}, "
            f"app_version={self.settings.app_version!r})"
        )
