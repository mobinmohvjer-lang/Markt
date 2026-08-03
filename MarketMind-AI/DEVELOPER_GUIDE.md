<!--
DEVELOPER_GUIDE.md
------------------
Purpose: The rulebook for extending MarketMind-AI. Where PROJECT_STATE.md
tells you what exists right now, this file tells you how to build
whatever comes next so it fits the existing architecture instead of
fighting it. Read PROJECT_STATE.md first for current status, then this
file before writing any code.
-->

# MarketMind-AI — Developer Guide

## Overall architecture

MarketMind-AI is a personal, free/open, zero-cost AI-assisted trading
research assistant, built as a **Clean Architecture** Python project.
Business rules live at the center (`core/`) and know nothing about
frameworks, exchanges, databases, or AI providers. Every outer layer
depends inward on `core/`, never the reverse.

Full authoritative layer table and planned data flow diagrams live in
`docs/ARCHITECTURE.md` — read it alongside this guide; this section is
a summary, not a replacement.

Layer order (inner → outer):

```
core/  →  events/  →  data/ / indicators/ / database/  →  analysis/ / models/
       →  signals/  →  strategies/  →  backtesting/ / services/  →  app/  →  api/ (inbound, future)
```

`config/` and `utils/` sit outside this chain entirely — zero
dependencies, usable from anywhere.

The intended (not yet implemented) future data flow is event-driven:
packages will publish/subscribe via `events/` (e.g. `data/` publishes
`CandleClosed`, `indicators/` subscribes and publishes
`IndicatorCalculated`, `analysis/` subscribes and publishes
`AIAnalysisCompleted`, etc.) rather than calling each other's methods
directly. No concrete `EventBus` exists yet — that must be built in
`services/` or `app/` before this flow becomes real. Until then,
cross-package calls are direct function/class calls.

## Clean Architecture rules

1. **Dependency Rule**: inner layers never import outer layers.
   `core/` imports nothing project-internal (not even `config/`).
   `events/` imports only `core/`. And so on outward per the table in
   `docs/ARCHITECTURE.md`.
2. **Interfaces over implementations**: outer layers implement
   interfaces/protocols defined in `core/interfaces/`. This is what
   lets you swap Binance for another exchange, or one AI provider for
   another, without touching `core/` or anything depending on the
   interface.
3. **Free-first**: every dependency and integration must target a free
   tier or open-source tool (Binance public API, SQLite, pytest,
   free/local NLP or LLM). Do not introduce paid services or APIs that
   require a paid key.
4. **Separation of calculation vs. interpretation vs. decision**:
   `indicators/` only calculates numbers. `analysis/` interprets those
   numbers (and news) into scored `AnalysisResult` insights. `signals/`
   standardizes one or more `AnalysisResult`s into a common `SignalResult`
   format (`direction`/`strength`/`confidence`/`summary`/`metadata`, via
   `BaseSignalGenerator`). `strategies/` turns signals into trading
   decisions. Never collapse two of these responsibilities into one
   package.
5. **Backtesting is a consumer, never a strategy author**:
   `backtesting/` replays historical data through whatever
   strategy/signals it's given and reports results. It must never
   contain trading rules of its own.
6. **API is the outermost adapter (for its inbound-REST role)**: the
   future inbound REST surface in `api/` may only call into `app/` use
   cases, never directly into `core`, `data`, `analysis`, etc. (Note:
   `api/`'s existing outbound-transport role — `http_client.py`,
   `providers/` — is unrelated to this rule; see Package
   responsibilities below.)

## Dependency rules (quick reference)

| Package | May import from |
|---|---|
| `core/` | nothing project-internal |
| `config/`, `utils/` | nothing project-internal |
| `events/` | `core` |
| `database/` | `core` |
| `indicators/` | `core`, `events` |
| `data/` | `core`, `events`, `config` |
| `api/` (outbound transport, existing) | nothing project-internal (leaf) |
| `analysis/` | `core`, `data`, `indicators`, `events` |
| `models/` | `core` |
| `signals/` | `core`, `analysis`, `events` |
| `strategies/` | `core`, `analysis`, `signals`, `events` |
| `backtesting/` | `core`, `data`, `strategies`, `signals` |
| `execution/` | `core`, `strategies` (`StrategyResult`), `strategies.risk_management` (`RiskResult`), `strategies.portfolio_management` (`PortfolioResult`) |
| `services/` | `core`, `events` |
| `app/` | all of the above |
| `api/` (inbound REST, future) | `app` only |

If you find yourself needing an import that isn't in this table for
the package you're editing, that's a signal the code belongs in a
different package, or the abstraction needs to move to `core/`.

## Coding conventions

- **Every module opens with a module-level docstring** stating its
  Purpose (and, for packages, Contents / Planned contents). Follow this
  pattern for any new file — see `core/enums.py`, `indicators/base.py`,
  `analysis/__init__.py`, `api/__init__.py` for the house style.
- **`from __future__ import annotations`** is used at the top of
  essentially every module. Keep doing this for forward-compatible
  type hints.
- **Type hints are mandatory** on public functions/methods, including
  return types. Use `Optional[...]`, `Union[...]`, `Dict[...]` etc. from
  `typing` (project targets Python 3.12 but keeps `typing` imports
  explicit rather than relying only on builtin generics).
- **Docstrings use NumPy-style sections** (`Parameters`, `Returns`,
  etc.) for non-trivial classes/functions — see `indicators/base.py`'s
  `IndicatorResult` for the reference style.
- **Immutability by default.** Entities are frozen dataclasses unless
  they represent evolving state. Only `Position` and `Portfolio` are
  mutable in `core/entities/` — everything else (candles, tickers,
  trades, signals, indicator results, news items, market state
  snapshots) is a frozen, point-in-time value object. Follow this
  pattern for any new entity: default to frozen, justify mutability in
  the docstring if you deviate.
- **Abstract contracts use `abc.ABC` + `@abstractmethod`**, not
  `typing.Protocol`. Follow the existing interface style in
  `core/interfaces/` and `events/interfaces/`.
- **Dependency injection over hard-wiring.** External I/O (HTTP
  clients, databases) is injected via constructor parameters and
  defined against an abstract interface first (e.g.
  `BinanceClientInterface` in `data/client.py`, injectable with a fake
  for tests) so tests never require real network access.
- **No trading logic in scaffold/stub packages** until their real
  implementation milestone is reached — don't sneak partial logic into
  a package whose `__init__.py` says "no implementation yet" without
  first turning that into a real, tested implementation task.

## Naming conventions

- Package names are lowercase, singular-concept nouns describing the
  layer's responsibility (`core`, `events`, `data`, `indicators`,
  `analysis`, `signals`, `strategies`, `backtesting`, `services`,
  `app`, `api`, `models`, `database`, `config`, `utils`).
- Class names are `PascalCase` and describe the concrete thing
  (`Candle`, `DataValidator`, `HistoricalDataDownloader`, `SMA`,
  `HTTPClient`, `BaseAnalyzer`, `AnalysisContext`, `AnalysisResult`).
- Interfaces/abstract base classes are named for the *role* they play,
  not suffixed with "Interface" or "Abstract" except where an interface
  and its real implementation would otherwise collide in the same file
  (e.g. `BinanceClientInterface` vs. `BinanceRESTClient` in
  `data/client.py` — the suffix is used there specifically to
  disambiguate the pair).
- File names are `snake_case` and mirror the primary class they
  contain, singular (`market_data_provider.py` → `MarketDataProvider`,
  `signal.py` → `Signal`, `candle_closed.py` → `CandleClosed`).
- Event type classes are named `<Noun><PastTenseVerb>` or
  `<Noun><PastParticiple>` describing something that already happened
  (`CandleClosed`, `SignalGenerated`, `PositionOpened`,
  `AIAnalysisCompleted`), matching the pub/sub "this occurred" semantics
  of `events/`.
- Exception classes end in `Error` and live in a per-package
  `exceptions.py`, forming a small hierarchy rooted in a package-level
  base error (e.g. `AnalysisError` → `AnalysisValidationError`,
  `AnalyzerConfigurationError`; `HTTPClientError` in `api/exceptions.py`).
- Test files are named `test_<module_or_component>.py` and live flat in
  `tests/` (no subdirectory nesting mirroring package structure today).

## Package responsibilities

- **`core/`** — domain entities and interfaces only. No implementation,
  no dependencies. Anything here must remain framework- and
  provider-agnostic forever.
- **`events/`** — event vocabulary and pub/sub contracts. No concrete
  `EventBus`. Depends only on `core` (for payload types).
- **`config/`** — typed settings (`settings.py`, env/.env-driven) and
  constants/enums (`config.py`, e.g. `TimeFrame`, `Exchange`). No
  project-internal dependencies.
- **`utils/`** — small, generic, reusable helpers with no business
  meaning, used by 2+ unrelated packages (logging setup, datetime
  conversion, generic validators). Currently empty — populate here
  rather than duplicating a helper across packages.
- **`data/`** — market data acquisition, validation, cleaning,
  normalization, storage, and caching. Currently Binance Spot OHLCV
  only, via the `DataEngine` facade. See `docs/DATA_ENGINE.md` for the
  full component table and usage examples.
- **`indicators/`** — pure, stateless technical indicator calculations.
  No knowledge of strategies, signals, or trading decisions. Every
  indicator supports both `calculate` (batch) and `update`
  (incremental) execution against `BaseIndicator`.
- **`api/`** — **two responsibilities coexist in this package today**:
  (1) outbound HTTP transport to third-party APIs — `http_client.py`
  (`HTTPClient`, `RateLimiter`, `RetryConfig`), `exceptions.py`, and
  `providers/` (Binance, CoinGecko, news); (2) a planned, not-yet-built
  inbound REST API exposing MarketMind-AI itself (`routes/`,
  `schemas/`, `server.py`, `dependencies.py`). When extending this
  package, be explicit about which of the two you're building.
- **`analysis/`** — transforms raw market/news data into scored
  insights without deciding what to do about them. Foundation
  (`BaseAnalyzer`, `AnalysisContext`, `AnalysisResult`, `AnalysisError`
  hierarchy, `utils.py`) exists; `technical/` is implemented
  (`TrendAnalyzer`, `MomentumAnalyzer`, `VolatilityAnalyzer`,
  `VolumeAnalyzer`); `news/` and `ai/` subpackages are still planned
  but not yet created.
- **`models/`** — ML model training and inference. Depends only on
  `core`. Stub only.
- **`signals/`** — standardizes `analysis/` output (`AnalysisResult`)
  into a common, lightweight signal representation and aggregates
  multiple signals. Foundation implemented (Signal Engine Part 1):
  `BaseSignalGenerator`, `SignalContext`, `SignalResult`, `SignalError`
  hierarchy, `utils.py` — mirroring `analysis/`'s own foundation. First
  concrete generator implemented (Signal Engine Part 2):
  `TechnicalSignalGenerator`, which standardizes an
  `analysis.aggregator.AnalysisAggregator` result into a Bullish/
  Bearish/Neutral `SignalResult`. Signal aggregation implemented
  (Signal Engine Part 3): `SignalAggregator` (`aggregator.py`), which
  itself subclasses `BaseSignalGenerator` and combines the
  `SignalResult`s of one or more injected sub-generators (weighted,
  confidence-scaled, gracefully skipping unavailable ones) into one
  final `SignalResult`, mirroring `analysis.aggregator.AnalysisAggregator`
  one layer down. Filtering implemented (Signal Engine Part 4):
  `signals/filters.py` -- `BaseSignalFilter` plus `ConfidenceFilter`,
  `DuplicateSignalFilter`, `CooldownFilter`, and `ConflictFilter`
  (accept/reject/modify an already-produced `SignalResult`, never
  generate one), combined via `SignalFilterPipeline`, which
  sequences filters and short-circuits on the first rejection.
  Validation implemented (Signal Engine Part 5): `signals/validation.py`
  -- `ValidationRule` plus `SummaryContentRule`, `RangeConsistencyRule`,
  `DirectionStrengthConsistencyRule`, `ConfidenceThresholdRule`, and
  `MetadataPresenceRule` (each reports errors/warnings on an
  already-produced `SignalResult`, never discarding or modifying it --
  a different boundary than filtering), combined via
  `SignalValidationPipeline`, which sequences rules in a
  caller-configurable order and never short-circuits, and
  `SignalValidator`, the facade most callers use (defaults to a
  built-in rule set; `validate_and_annotate()` merges findings into
  `metadata["signal_validation"]`).
- **`strategies/`** — turns signals into trading decisions; also houses
  risk management. Strategy Engine foundation implemented (Strategy
  Engine Part 1): `BaseStrategy` (`base_strategy.py`), `StrategyContext`
  (`context.py`), `StrategyResult` (`result.py`), the `StrategyError`
  hierarchy (`exceptions.py`), and `utils.py` — mirroring `analysis/`'s,
  `signals/`'s, and `strategies.risk_management`'s own Part 1
  foundations. `StrategyContext` composes existing `analysis.result.
  AnalysisResult`(s), an optional `signals.result.SignalResult`, and an
  optional `strategies.risk_management.result.RiskResult` for one
  symbol/timeframe — no new domain concepts. `StrategyResult` holds
  only `action` (reusing `core.enums.SignalDirection`), `confidence`,
  `summary`, `metadata` — no position sizing, stop-loss/take-profit, or
  order-id. `BaseStrategy` deliberately does not implement
  `core.interfaces.strategy.Strategy` (which takes a raw `MarketState`
  and returns an optional `Signal` directly — a different,
  MarketState-in/Signal-out shape), the same way `strategies.
  risk_management.base.BaseRiskManager` does not implement
  `core.interfaces.risk_manager.RiskManager`. First concrete strategy
  implemented (Strategy Engine Part 2): `BasicStrategy`
  (`basic_strategy.py`), which looks up one `AnalysisResult` (matched
  by `analyzer_name`, default `"AnalysisAggregator"`) and optionally
  reads `signal_result`/`risk_result`, combining them into a
  confidence-weighted `overall_score` thresholded onto
  `SignalDirection.BUY`/`SELL`/`HOLD`, an agreement-based
  `consistency_score`, and a risk gate that downgrades an unapproved
  `BUY`/`SELL` to `HOLD`. Covered by `tests/test_basic_strategy.py`.
  A way to combine multiple `BaseStrategy` instances implemented
  (Strategy Engine Part 3): `StrategyAggregator` (`aggregator.py`),
  itself a `BaseStrategy` subclass, which runs one or more injected
  sub-strategies (defaulting to a single `BasicStrategy()`) against
  the same `StrategyContext` and weight-averages their signed
  `action`/`confidence` into one final `StrategyResult` — mirroring
  `AnalysisAggregator`/`SignalAggregator` one and two layers down.
  Records `overall_score`, `confidence`, `completeness`, and
  `agreement` in full in `metadata`; treats a sub-strategy raising
  `InsufficientStrategyDataError` as "unavailable" rather than fatal,
  only raising itself when every sub-strategy is unavailable. Covered
  by `tests/test_strategy_aggregator.py`. `risk_management/`
  foundation implemented (Risk
  Engine Part 1): `BaseRiskManager`, `RiskContext`, `RiskResult`, the
  `RiskError` hierarchy, `utils.py` — mirroring `analysis/`'s and
  `signals/`'s own Part 1 foundations. `RiskContext` composes only
  existing `core.entities` (`Signal`, `Portfolio`, optional
  `MarketState`); `RiskResult` holds only `approved`/`risk_score`/
  `confidence`/`summary`/`metadata` — no position sizing, stop-loss/
  take-profit, or order execution. `BaseRiskManager` deliberately
  does not implement `core.interfaces.risk_manager.RiskManager` (which
  also requires position sizing/stop-loss), the same way
  `signals.base.BaseSignalGenerator` does not implement
  `core.interfaces.signal_generator.SignalGenerator`. First concrete
  risk manager implemented (Risk Engine Part 2): `BasicRiskManager`
  (`basic_risk_manager.py`), which evaluates signal confidence,
  optional signal strength (read defensively from `Signal.metadata`),
  portfolio exposure (derived from `RiskContext.portfolio`), and
  market-data availability into one weighted `risk_score`/`approved`
  decision, with configurable hard-threshold overrides and full
  traceability in `metadata`. Three further concrete risk managers
  implemented (Risk Engine Part 3 -- position sizing / protective
  levels): `PositionSizeRule` (`position_size_rule.py`, fixed-
  fractional risk sizing -- `recommended_position_value`/
  `recommended_position_size` in `metadata`), `StopLossRule`
  (`stop_loss_rule.py`, direction-aware protective stop price), and
  `TakeProfitRule` (`take_profit_rule.py`, direction-aware target price
  scaled by a configurable `risk_reward_ratio`). All three share the
  same ATR-or-percentage distance model but compute it independently
  -- none of the three imports or depends on either of the other two,
  or on `BasicRiskManager`. Each treats a `SignalDirection.HOLD` signal
  as "not applicable" rather than an error, and treats missing
  *optional* data (ATR always; a resolvable reference price, in
  `PositionSizeRule` only) as a reason to fall back and lower
  `confidence`, never to raise; each raises `InsufficientRiskDataError`
  only for a truly required input (unusable `signal.confidence` in all
  three; non-positive portfolio equity in `PositionSizeRule`; a
  completely unresolvable reference price in `StopLossRule`/
  `TakeProfitRule`). Covered by `tests/test_risk_rules.py`.
  `portfolio_management/` foundation implemented (Portfolio Management
  Part 1): `BasePortfolioManager`, `PortfolioContext`, `PortfolioResult`,
  the `PortfolioError` hierarchy, `utils.py` -- mirroring `analysis/`'s,
  `signals/`'s, and `strategies.risk_management`'s own Part 1
  foundations. `PortfolioContext` composes the current `core.entities.
  portfolio.Portfolio` (required), an optional `strategies.result.
  StrategyResult`, and an optional `strategies.risk_management.result.
  RiskResult`; `PortfolioResult` holds only `new_positions_allowed`/
  `confidence`/`summary`/`metadata` -- no target allocation, no
  rebalancing instructions, no order-id. First concrete portfolio
  manager implemented (Portfolio Management Part 2): `BasicPortfolioManager`
  (`basic_portfolio_manager.py`), which gates a candidate new position
  on four independent deterministic checks -- open-position count
  (against `max_open_positions`), aggregate exposure (against
  `max_exposure_ratio`), single-symbol concentration (against
  `max_symbol_exposure_ratio`, independent of the aggregate check), and
  upstream signal/risk agreement (directional `StrategyResult.action`
  and `RiskResult.approved`, when present) -- all four must pass for
  `new_positions_allowed=True`, with every reason recorded in
  `metadata["hard_reject_reasons"]`. No scoring, allocation,
  position-sizing, rebalancing, or broker integration -- every check is
  a plain threshold comparison. Covered by `tests/test_portfolio_management.py`
  (Part 1) and `tests/test_basic_portfolio_manager.py` (Part 2). A
  composite/aggregating manager is also implemented (Portfolio
  Management Part 3): `PortfolioManager` (`portfolio_manager.py`),
  itself a `BasePortfolioManager` that combines one or more injected
  `BasePortfolioManager` instances (default: a single plain
  `BasicPortfolioManager()`) into one final `PortfolioResult`,
  mirroring `StrategyAggregator`'s/`SignalAggregator`'s role one layer
  down each. Since `PortfolioResult` has no numeric score field, each
  sub-manager's `new_positions_allowed` is represented as a signed unit
  vote (`+1.0`/`-1.0`), weight-and-confidence-averaged into an
  `aggregate_score` and thresholded via a configurable `allow_threshold`
  (default `0.0`) back onto a final bool. Sub-managers are keyed by
  `.name` (duplicates rejected); any raising
  `InsufficientPortfolioDataError` is treated as unavailable
  (`metadata["managers_missing"]`) rather than failing the whole
  aggregation. Records `aggregate_score`/`completeness`/`agreement`/
  `confidence` in full, the same shape the three aggregators above
  already use. No allocation, position-sizing, rebalancing, or broker
  integration; reuses Parts 1-2 exactly as they exist. Covered by
  `tests/test_portfolio_manager.py` (Part 3), mirroring
  `tests/test_strategy_aggregator.py`/`tests/test_signal_aggregator.py`'s
  fake-sub-manager style plus a real-`BasicPortfolioManager`-integration
  section. A second, functionally-equivalent aggregator is also
  implemented (Portfolio Management Part 4): `PortfolioAggregator`
  (`aggregator.py`), itself a `BasePortfolioManager` built explicitly to
  mirror `strategies.aggregator.StrategyAggregator`'s naming/
  documentation conventions one layer up (the `*Aggregator` naming
  `AnalysisAggregator`/`SignalAggregator`/`StrategyAggregator` already
  use), rather than `PortfolioManager` (Part 3)'s own naming. Same
  weighted-vote/`allow_threshold`/`aggregate_score`/`completeness`/
  `agreement`/`confidence` shape as Part 3, same unavailable-sub-manager
  handling, same defaulting to a single plain `BasicPortfolioManager()`;
  deliberately independent of `PortfolioManager` -- neither module
  imports or subclasses the other, and either may be nested as a
  sub-manager of the other (or of itself). Reuses Parts 1-2 exactly as
  they exist; Part 3 is left completely untouched. Covered by
  `tests/test_portfolio_aggregator.py`, mirroring
  `tests/test_portfolio_manager.py`'s structure plus a dedicated
  independence section confirming the two aggregators do not depend on
  each other.
- **`backtesting/`** — replays historical data through a given
  strategy/signals and reports performance metrics. Never contains
  trading rules itself. Foundation implemented (Part 1):
  `BaseBacktester`, `BacktestContext`, `BacktestResult`, `BacktestError`
  hierarchy, shared validation helpers — same shape as the `analysis`/
  `signals`/`strategies`/`strategies.risk_management`/
  `strategies.portfolio_management` Part 1 foundations. First concrete
  backtester implemented (Backtesting Engine Part 2): `BasicBacktester`
  (`basic_backtester.py`), which replays `BacktestContext.candles`
  sequentially/chronologically through `BacktestContext.strategy`,
  building a minimal per-candle `strategies.context.StrategyContext`
  (empty `analysis_results`, no `signal_result`/`risk_result`, current
  candle exposed only via `metadata`) and consuming only the resulting
  `strategies.result.StrategyResult.action`. `BUY` opens one long
  `Position` with all available cash at the candle's `close` price
  (no-op if already holding, or with no cash); `SELL` closes an open
  position in full at `close` (no-op if none open); `HOLD` is a no-op.
  No slippage, commissions, leverage, or performance statistics are
  modeled. A strategy raising `InsufficientStrategyDataError` for a
  candle is treated as "skip that candle", never a fatal error for the
  run. Covered by `tests/test_basic_backtester.py`. Standalone
  portfolio-simulation helper implemented (Backtesting Engine Part 3):
  `PortfolioSimulator` (`portfolio_simulator.py`), which factors the
  exact cash/position-simulation mechanics `BasicBacktester` already
  implements inline into their own reusable, independently-tested
  class — `open_position`/`close_position` (long or short, one open
  position per symbol, no pyramiding), `update_market_price` (marks an
  open position's `current_price`/`unrealized_pnl`), `total_equity()`,
  and `Candle`-based convenience wrappers. Deep-copies its
  `Portfolio` at construction and never mutates the caller's instance
  or any `Candle` passed to it. Purely additive: `BasicBacktester`
  itself is untouched and does not use `PortfolioSimulator` yet — a
  future concrete backtester (or a refactor of `BasicBacktester`, a
  deliberate decision if/when made) may adopt it instead of
  duplicating the mechanics. Covered by
  `tests/test_portfolio_simulator.py`. Performance-statistics
  calculations implemented (Backtesting Engine Part 4): `metrics.py`
  — `BacktestMetrics` (a frozen result container) and
  `calculate_metrics(result, initial_portfolio, ...)`, which derives
  trade counts, `win_rate`, `gross_profit`/`gross_loss`,
  `profit_factor`, average/largest win and loss, initial/final equity
  and total return, an `equity_curve`, `max_drawdown_pct`/`_amount`,
  and `sharpe_ratio` entirely from the closed `Position` entries on an
  already-produced `BacktestResult.final_portfolio` and the starting
  `Portfolio` — it does not run a backtest or simulate trades itself.
  The smaller building blocks (`win_rate`, `profit_factor`,
  `compute_equity_curve`, `max_drawdown`, `sharpe_ratio`) are also
  independently importable. Deterministic, side-effect free, and
  purely additive — every other Backtesting Engine file was left
  completely untouched. Covered by `tests/test_metrics.py`. Report
  generation implemented (Backtesting Engine Part 5): `BacktestReport`
  (`report.py`), which wraps an already-produced `BacktestResult`/
  `BacktestMetrics` into four read-only views — `summary()` (one
  paragraph), `detailed_summary()` (multi-section text),
  `trades_summary()`/`metrics_summary()` (structured dicts), and
  `full_report()` (all combined) — computing nothing itself and
  mutating neither input. No charts, HTML/PDF/CSV export, logging, AI,
  or broker/order-execution logic. Covered by `tests/test_report.py`.
- **`execution/`** — the last framework-only checkpoint before an
  approved trading decision would ever reach a broker/exchange; never
  places an order itself. Foundation implemented (Execution Engine
  Part 1): `BaseExecutionEngine` (`base.py`), `ExecutionContext`
  (`context.py`), `ExecutionResult` (`result.py`), the `ExecutionError`
  hierarchy (`exceptions.py`), and `utils.py` — mirroring the exact
  Part 1 shape every other engine (`analysis/`, `signals/`,
  `strategies/`, `strategies.risk_management`, `strategies.
  portfolio_management`, `backtesting/`) already established.
  `ExecutionContext` composes the current `core.entities.portfolio.
  Portfolio` (required), an optional `strategies.result.StrategyResult`
  (the candidate trading decision), an optional `strategies.
  risk_management.result.RiskResult` (its risk evaluation), and an
  optional `strategies.portfolio_management.result.PortfolioResult`
  (whether the portfolio has capacity) — no new domain concepts.
  `ExecutionResult` holds only `execution_approved`/`confidence`/
  `summary`/`metadata` — no order-id, no fill price/quantity, no
  broker/exchange identifiers. Framework only: no concrete execution
  engine, no broker integration, no exchange API, no order execution,
  no networking, no threading, no async, no AI. Imported directly
  (`from execution import BaseExecutionEngine, ExecutionContext,
  ExecutionResult, ...`) — this package has no parent to re-export
  through, the same leaf-level convention `strategies.risk_management`/
  `strategies.portfolio_management` already use relative to
  `strategies/`. Covered by `tests/test_execution.py`.
- **`database/`** — persistence layer implementing
  `core.interfaces.database_repository.DatabaseRepository` (SQLite by
  default). Stub only — note `data/storage.py` already does SQLite
  persistence for candles specifically; see open question in
  PROJECT_STATE.md's Design decisions before assuming this package
  should wrap or replace it.
- **`services/`** — wraps external integrations and cross-cutting
  technical concerns (notifications, an AI/LLM client wrapper,
  scheduling, a concrete `EventBus`) that are heterogeneous by nature,
  unlike every trading-decision engine above. Foundation implemented
  (Services Part 1): `BaseService` (`base.py`), `ServiceContext`
  (`context.py`), `ServiceResult` (`result.py`), the `ServiceError`
  hierarchy (`exceptions.py`), and `utils.py` — mirroring the exact
  Part 1 shape every other engine (`analysis/`, `signals/`,
  `strategies/`, `strategies.risk_management`, `strategies.
  portfolio_management`, `backtesting/`, `execution/`) already
  established, adapted for `services/`'s generic nature.
  `ServiceContext` composes no domain entities — it's a generic
  `service_name` + free-form `payload` + `metadata` envelope, since
  each concrete service (notification, AI/LLM, scheduler) interprets
  `payload` for its own purpose. `ServiceResult` holds only `success`
  (`bool`)/`summary`/`metadata` — no `confidence` field (unlike every
  trading-decision result above), since a service call either succeeds
  or it doesn't. Framework only: no concrete service (no notification
  service, no AI/LLM client, no scheduler, no concrete `EventBus`),
  no broker integration, no execution logic, no networking, no
  threading, no async, no AI. Imported directly (`from services import
  BaseService, ServiceContext, ServiceResult, ...`) — this package has
  no parent to re-export through, the same leaf-level convention
  `execution/`/`strategies.risk_management`/`strategies.
  portfolio_management` already use. Covered by
  `tests/test_services.py`. Planned future contents (not yet built):
  `notification_service.py` (e.g. a Telegram-bot free-tier wrapper),
  `ai_service.py` (a free/self-hosted AI/LLM client), `scheduler_service.py`
  (periodic job runner), and a concrete `EventBus` implementation.
- **`app/`** — orchestrates use cases across every other layer. The
  only package permitted to depend on all of them. Stub only.
- **`logs/`** — not a Python package. Runtime log file output directory
  only.

## How new modules should be implemented

Follow this sequence when moving a stub package (or a new subpackage,
e.g. `analysis/technical/`) from "explanatory `__init__.py`" to real
code:

1. **Re-read `docs/ARCHITECTURE.md` and this guide's dependency table**
   for the package you're implementing — confirm what it may and may
   not import before writing anything.
2. **Check `core/interfaces/`** for an existing abstract contract this
   module should implement or consume (e.g. a concrete analyzer should
   subclass `analysis.base.BaseAnalyzer`; a new market data source
   should implement `core.interfaces.market_data_provider.MarketDataProvider`).
   Do not invent a parallel abstraction if one already exists.
3. **Write the module docstring first** (Purpose / Contents / Planned
   contents), matching the house style described above, before or
   alongside the code — don't skip it.
4. **Depend only on what the dependency table allows.** If the package
   needs something from a package not listed, stop and reconsider the
   design rather than adding the import anyway.
5. **Inject external dependencies** (HTTP clients, DB connections,
   AI/model clients) via constructor parameters against an interface,
   the way `data/client.py`'s `BinanceClientInterface` /
   `BinanceRESTClient` split does, so tests can supply a fake.
6. **Write tests in `tests/test_<name>.py`** using the existing
   fakes/helpers in `tests/helpers.py` where applicable (e.g.
   `FakeBinanceClient`) rather than hitting real network endpoints.
7. **Update `docs/ARCHITECTURE.md`** if the new module changes or adds
   to the layer table, and add a dedicated doc under `docs/` if the
   module is substantial (mirroring `docs/DATA_ENGINE.md`'s format:
   component table, quick start, test-running instructions).
8. **Update `README.md`'s roadmap checklist and `PROJECT_STATE.md`**
   once the module is real and tested, so project state stays accurate
   for the next person (or AI) picking this up.

## Existing abstractions that must be reused

Do not create parallel versions of these — extend or implement them:

- `core.entities.*` — `Candle`, `Ticker`, `OrderBook`/`OrderBookLevel`,
  `Trade`, `Position`, `Portfolio`, `Signal`, `IndicatorResult`,
  `NewsItem`, `MarketState`. Any new code representing one of these
  concepts must use these classes, not a new dataclass.
- `core.interfaces.*` — `MarketDataProvider`, `NewsProvider`,
  `AIAnalyzer`, `IndicatorCalculator`, `Strategy`, `SignalGenerator`,
  `RiskManager`, `DatabaseRepository`. Any new provider/analyzer/
  strategy/repository must implement the matching interface.
- `core.enums.*` — `OrderSide`, `PositionSide`, `PositionStatus`,
  `SignalDirection`. Use these instead of inventing new string
  literals or duplicate enums.
- `events.interfaces.*` — `Event`, `EventBus`, `EventHandler`, and the
  9 concrete event types in `events.event_types`. Any future
  pub/sub-based communication between packages must extend these, not
  define a new event contract.
- `indicators.base.BaseIndicator` / `IndicatorResult` — every new
  indicator must subclass `BaseIndicator` and support both `calculate`
  and `update`.
- `analysis.base.BaseAnalyzer`, `analysis.context.AnalysisContext`,
  `analysis.result.AnalysisResult`, `analysis.exceptions.AnalysisError`
  hierarchy — every concrete analyzer (`technical/`, `news/`, `ai/`)
  must build on these, not redefine its own context/result shape.
- `strategies.risk_management.base.BaseRiskManager`,
  `strategies.risk_management.context.RiskContext`,
  `strategies.risk_management.result.RiskResult`,
  `strategies.risk_management.exceptions.RiskError` hierarchy — every
  concrete risk manager (including future Risk Engine parts beyond
  `strategies.risk_management.basic_risk_manager.BasicRiskManager`)
  must build on these, not redefine its own context/result shape.
- `strategies.base_strategy.BaseStrategy`, `strategies.context.
  StrategyContext`, `strategies.result.StrategyResult`, `strategies.
  exceptions.StrategyError` hierarchy — every concrete strategy
  (future Strategy Engine parts) must build on these, not redefine its
  own context/result shape.
- `execution.base.BaseExecutionEngine`, `execution.context.
  ExecutionContext`, `execution.result.ExecutionResult`, `execution.
  exceptions.ExecutionError` hierarchy — every concrete execution
  engine (future Execution Engine parts) must build on these, not
  redefine its own context/result shape.
- `services.base.BaseService`, `services.context.ServiceContext`,
  `services.result.ServiceResult`, `services.exceptions.ServiceError`
  hierarchy — every concrete service (notification, AI/LLM client,
  scheduler, event bus) must build on these, not redefine its own
  context/result shape.
- `api.http_client.HTTPClient` / `RateLimiter` / `RetryConfig` — any new
  outbound HTTP integration should go through this client rather than
  calling `requests`/`httpx` directly, to keep retry/rate-limit
  behavior consistent.
- `data.client.BinanceClientInterface` — the pattern to copy for any
  new external data source: define the abstract interface first, then
  the real implementation, so it stays fake-injectable for tests.
- `config.settings.get_settings()` / `config.config` — the single
  source of typed configuration and constants (e.g. `TimeFrame`,
  `Exchange`). Don't read `os.environ` directly elsewhere or hardcode
  timeframe/exchange strings that already exist as constants here.

## What must never be changed

- **The Dependency Rule direction.** Inner layers (`core`, `config`,
  `utils`) must never import outer layers, under any circumstance,
  even temporarily "to make something work."
- **`core/`'s zero-dependency status.** `core` must never import
  `config`, `data`, `services`, or anything else project-internal —
  this is why domain enums live in `core/enums.py` rather than reusing
  `config/config.py`.
- **Frozen entities' immutability.** Do not make any `core/entities/`
  class other than `Position`/`Portfolio` mutable without a strong,
  documented reason — immutability is relied on elsewhere (e.g. safe
  caching in `data/cache.py`).
- **`indicators/`'s purity.** Indicators must remain stateless
  calculations with no knowledge of strategies, signals, or trading
  decisions. Never add trading-decision logic here.
- **`backtesting/`'s consumer-only role.** It must never define trading
  rules itself, even once implemented.
- **The free-first constraint.** Never introduce a paid API, paid
  database, or paid AI service as a hard dependency.
- **Existing public interfaces in `core/interfaces/` and
  `events/interfaces/`.** Changing their method signatures is a
  breaking change to every future implementer — treat as append-only
  unless a deliberate, repo-wide migration is planned.
- **The Data Engine's tested behavior in `data/`.** It is the most
  mature, fully tested module in the repo (61 dedicated tests per
  `docs/DATA_ENGINE.md`) — do not refactor its public API without
  updating every consumer and test.
- **Anything explicitly requested by the task instructions in a given
  session** — e.g. "do not modify existing functionality" instructions
  always take precedence over convenience refactors.

## Testing conventions

- Test framework: **pytest** is the project standard (pinned in
  `requirements.txt`), though most existing tests are written to also
  run under the standard-library `unittest` runner with zero
  third-party dependencies (per `docs/DATA_ENGINE.md`) — only
  `test_core_domain.py` and `test_events.py` currently require `pytest`
  specifically (they use `pytest.raises`/`pytest.mark.parametrize`; no
  test file anywhere in the suite uses `conftest.py` or `@pytest.fixture`).
- **Verifying in a network-isolated environment:** if `pip install -r
  requirements.txt` cannot reach the network, the full suite can still
  be verified without a real `pytest` install, because the only pytest
  surface used anywhere is `pytest.raises` and `pytest.mark.parametrize`
  — both trivial to shim (a `raises` context manager plus a
  `mark.parametrize` decorator that records its cases for expansion by
  a small custom collector supporting both `unittest.TestCase` classes
  and plain pytest-style functions). This was most recently confirmed
  during the Portfolio Management Part 4 test-coverage pass: 1258 tests
  passing via the standard-library `unittest` runner across 41 test
  files (1196 carried over unchanged from the Part 3 pass + 62 new in
  `tests/test_portfolio_aggregator.py`), plus 29 pytest-`parametrize`-
  expanded cases (from 12 parametrized test functions) across the two
  pytest-only files, run separately via the shim — 1287 test cases
  total, all passing. (In this specific verification environment,
  `pip install pytest` had no network access, so `test_core_domain.py`/
  `test_events.py` surface as `unittest`-loader import errors rather
  than running via the shim; this is a pre-existing, environment-only
  gap unrelated to this change — see Compile status in
  PROJECT_STATE.md.) Prefer
  a real `pytest` install whenever network access is available; the
  shim exists only to close the verification gap when it isn't.
  Most recently reconfirmed during the Execution Engine Part 1
  verification/integration pass: **1556 tests passing via the
  standard-library `unittest` runner** across 47 test files (1455
  carried over unchanged + 41 new-to-this-document in
  `tests/test_report.py`, found already present and passing —
  Backtesting Engine Part 5 — + 60 new in `tests/test_execution.py`
  — Execution Engine Part 1), plus the same 29 pytest-`parametrize`-
  expanded cases in the two pytest-only files (unchanged) — **1585
  test cases total**, all passing. No network access to install
  `pytest` in this specific environment either, so
  `test_core_domain.py`/`test_events.py` again surfaced as
  `unittest`-loader import errors rather than real failures — see
  Current test status in `PROJECT_STATE.md` for the full breakdown.
  Most recently reconfirmed during the Services Part 1 new-
  implementation pass: **1604 tests passing via the standard-library
  `unittest` runner** across 48 test files (1556 carried over
  unchanged + 48 new in `tests/test_services.py` — Services Part 1),
  plus the same 29 pytest-`parametrize`-expanded cases in the two
  pytest-only files (unchanged) — **1633 test cases total**, all
  passing. No network access to install `pytest` in this specific
  environment either, so `test_core_domain.py`/`test_events.py` again
  surfaced as `unittest`-loader import errors rather than real
  failures — see Current test status in `PROJECT_STATE.md` for the
  full breakdown.
- Test files live flat in `tests/`, named `test_<component>.py`, one
  per implemented module/component (mirrors the package it tests, not
  a nested directory tree).
- Shared fakes/helpers (e.g. `FakeBinanceClient`) live in
  `tests/helpers.py` — reuse these instead of writing a new fake per
  test file.
- No real network access in tests. External I/O is faked via
  dependency injection against the relevant `core`/`data` interface
  (see `BinanceClientInterface`).
- Run the full suite with either:
  ```bash
  pytest
  # or, dependency-free:
  python3 -m unittest discover -s tests -p "test_*.py" -v
  ```
- New modules must ship with tests in the same change — an
  implementation without a corresponding `tests/test_<name>.py` is
  incomplete by this project's standard.

## Documentation conventions

- Every module/package opens with a docstring: Purpose, then Contents
  (and Planned contents for stubs) — see Coding conventions above.
- Substantial modules get a dedicated file under `docs/`, following the
  `docs/DATA_ENGINE.md` format: a component table (class → file →
  responsibility), any supported-values table (e.g. timeframes), a
  "Quick start" runnable code example, and a "Running the tests"
  section.
- `docs/ARCHITECTURE.md` is the single source of truth for the layer
  table and dependency graph — update it whenever a package's
  dependencies or responsibilities change, don't let it drift from
  reality.
- `README.md` carries the human-facing project overview and the
  roadmap checklist (`- [x]` / `- [ ]`) — keep the checklist in sync
  with actual completion state.
- `PROJECT_STATE.md` (this repo's root) is the point-in-time
  implementation snapshot — update it at the end of any milestone that
  changes what's completed, partial, or remaining.
- This file, `DEVELOPER_GUIDE.md`, changes only when architecture rules,
  conventions, or reusable abstractions themselves change — not for
  routine feature work.

## Integration checklist

Before considering any new module "done" and merged:

- [ ] Module docstring present (Purpose / Contents / Planned contents).
- [ ] Only imports packages allowed by the dependency table above.
- [ ] Implements/extends the correct existing `core`/`events`/`analysis`
      abstraction rather than inventing a parallel one.
- [ ] External I/O is interface-based and dependency-injected; a fake
      is available for tests (added to `tests/helpers.py` if reusable).
- [ ] Type hints on all public functions/methods, including returns.
- [ ] Tests added in `tests/test_<name>.py`; full suite still passes
      (`pytest` or `python3 -m unittest discover -s tests -p "test_*.py"`).
- [ ] All new/changed files byte-compile cleanly
      (`python3 -m py_compile <files>`).
- [ ] No paid service/dependency introduced.
- [ ] No change to an existing frozen entity's mutability or an
      existing interface's method signature, unless that is the
      explicit, deliberate goal of the change.
- [ ] `docs/ARCHITECTURE.md` updated if layer responsibilities or
      dependencies changed; a new `docs/<MODULE>.md` added if the
      module is substantial.
- [ ] `README.md` roadmap checklist and `PROJECT_STATE.md` updated to
      reflect the new completion state.

## Future roadmap

Per `README.md`'s roadmap and the current implementation snapshot in
`PROJECT_STATE.md`, in the order that respects existing dependencies
(each item below is unblocked once the items above it are done):

1. ~~`analysis/technical/` — concrete analyzer(s) consuming
   `indicators/` output via `AnalysisContext`, producing
   `AnalysisResult`.~~ **Done (Analysis Engine Part 2):**
   `TrendAnalyzer` and `MomentumAnalyzer`. **Extended (Analysis Engine
   Part 3A):** `VolatilityAnalyzer` (ATR, Bollinger Bands, Keltner
   Channel, Donchian Channel → a direction-free volatility-regime
   score). **Extended (Analysis Engine Part 3B):** `VolumeAnalyzer`
   (OBV, VWAP, Volume SMA → a directional volume-flow score, plus
   confirmation/divergence, buying/selling pressure, volume trend,
   participation strength, and price-vs-VWAP metadata). **Extended
   (Analysis Engine Part 3C):** `MarketStructureAnalyzer` (swing-point
   pairs → a directional market-structure score, plus HH/HL/LH/LL
   classification, BOS, CHOCH, trend continuation/reversal, and market
   regime). Unlike the other four, `MarketStructureAnalyzer` consumes
   no existing `indicators/` output — it documents the swing-point
   input shape it expects a future indicator/detector to supply; see
   the Future roadmap item below and PROJECT_STATE.md for details on
   all five.
2. ~~`analysis/aggregator.py` — combine the five `analysis/technical`
   analyzer outputs into one final `AnalysisResult`.~~ **Done (Analysis
   Engine Part 4):** `AnalysisAggregator`. Constructor-injects one
   instance of each of the five sub-analyzers (defaulting to real
   instances); `overall_score` weight-and-confidence-averages only the
   four *directional* sub-scores (`TrendAnalyzer`/`MomentumAnalyzer`/
   `VolumeAnalyzer`/`MarketStructureAnalyzer`) — `VolatilityAnalyzer`'s
   direction-free regime score is merged into `confidence`/`metadata`
   but deliberately excluded from that average. Any sub-analyzer
   raising `InsufficientDataError` is treated as "unavailable" rather
   than failing the call. Imported via `from analysis import
   AnalysisAggregator` (re-exported through `analysis/__init__.py`,
   unlike `analysis/technical/`'s analyzers). See PROJECT_STATE.md for
   full details.
3. A concrete swing-point-detection indicator — supplies the
   `"SwingPoints_1"`-shaped `IndicatorResult` (`swing_high_1`/
   `swing_high_2`/`swing_low_1`/`swing_low_2`) that
   `MarketStructureAnalyzer` (Part 3C) already documents and expects.
   Would live in `indicators/` (consistent with the calculation-vs-
   interpretation split in Clean Architecture rule 4 above) or be
   assembled by a future `app/`-layer pivot detector; no code currently
   produces it. `AnalysisAggregator` (Part 4) already degrades
   gracefully without it today, so this is not a blocker for anything
   downstream.
4. `analysis/news/` — news sentiment analysis, consuming
   `core.interfaces.news_provider.NewsProvider` and the existing
   `api/providers` news wrapper.
5. `analysis/ai/` — AI-based market assessment combining technical +
   news analysis, implementing `core.interfaces.ai_analyzer.AIAnalyzer`
   (real implementation would live in `services/`, per the interface
   table in `docs/ARCHITECTURE.md`).
6. ~~`signals/` — foundation: `BaseSignalGenerator`, `SignalContext`,
   `SignalResult`, exceptions, utils.~~ **Done (Signal Engine Part 1):**
   mirrors `analysis/`'s own Part 1 foundation. `SignalContext` consumes
   `analysis.result.AnalysisResult` (individual `analysis.technical`
   outputs and/or the merged `AnalysisAggregator` output — same type);
   `SignalResult` holds only `direction`/`strength`/`confidence`/
   `summary`/`metadata`.
   ~~`signals/` — first concrete `BaseSignalGenerator`.~~ **Done (Signal
   Engine Part 2):** `TechnicalSignalGenerator`
   (`signals/technical_signal_generator.py`). Looks up the
   `AnalysisResult` produced by `AnalysisAggregator` on its
   `SignalContext` (via `analyzer_name`, default `"AnalysisAggregator"`)
   and maps its `-1.0..+1.0` score onto Bullish/Bearish/Neutral
   (`SignalDirection.BUY`/`SELL`/`HOLD`) via configurable
   `buy_threshold`/`sell_threshold`. No AI, no risk management, no
   strategy/trading decisions, no order execution. Whether/how a later
   Signal Engine part (or `strategies/`) should also produce a persisted
   `core.entities.signal.Signal` (id/source/timestamp) remains an open
   design question, not decided here.
   ~~`signals/aggregator.py` — combine multiple `SignalResult`s.~~
   **Done (Signal Engine Part 3):** `SignalAggregator`
   (`signals/aggregator.py`). Itself a `BaseSignalGenerator`; combines
   the `SignalResult`s of one or more injected sub-generators (defaulting
   to a single `TechnicalSignalGenerator()`) via confidence-and-weight-
   weighted averaging of each component's signed direction/strength,
   thresholded back onto Bullish/Bearish/Neutral the same way Part 2
   does. A sub-generator raising `InsufficientSignalDataError` is treated
   as unavailable rather than failing the whole call; `SignalAggregator`
   itself only raises it when every sub-generator was unavailable. No AI,
   no Risk Engine, no Strategy Engine, no order execution, no trading
   decisions.
   ~~`signals/filters.py` — rules to discard low-confidence or
   conflicting signals.~~ **Done (Signal Engine Part 4):** a filter
   pipeline (`signals/filters.py`) sitting between generation (Parts
   1-3) and any future consumer. `BaseSignalFilter` (abstract;
   `apply(result, context) -> FilterOutcome`) plus four concrete
   filters — `ConfidenceFilter` (rejects below a minimum confidence),
   `DuplicateSignalFilter` (stateful; rejects a consecutive repeat of
   the same direction/strength for a symbol/timeframe),
   `CooldownFilter` (stateful; rejects a signal arriving too soon after
   the previous accepted one for a symbol/timeframe, via an injectable
   clock), `ConflictFilter` (stateful; downgrades a direct direction
   reversal to `SignalDirection.HOLD` with dampened strength/confidence
   rather than rejecting — the one `action="modify"` case) — plus
   `SignalFilterPipeline`, which sequences filters against one
   `SignalResult`/`SignalContext`, short-circuiting on the first
   rejection. Every filter returns a `FilterOutcome` (`action`/
   `reason`), never a bare `SignalResult`, so a rejection's reasoning
   is preserved in `SignalFilterPipelineResult.trace` and, for a
   surviving signal, also in `metadata["filter_pipeline_trace"]`. No
   AI, no Risk Engine, no Strategy Engine, no order execution, no
   trading decisions — Parts 1-3 were left untouched.
   ~~`signals/validation.py` — rules to report on signal quality/
   consistency.~~ **Done (Signal Engine Part 5):** signal *validation*
   (`signals/validation.py`), a different boundary than Part 4's
   filters — it never accepts/rejects/modifies a signal, only reports
   errors/warnings and (optionally) annotates metadata. `ValidationRule`
   (abstract; `evaluate(result, context) -> RuleOutcome`) plus five
   concrete rules — `SummaryContentRule`, `RangeConsistencyRule`,
   `DirectionStrengthConsistencyRule`, `ConfidenceThresholdRule`,
   `MetadataPresenceRule` — plus `SignalValidationPipeline`, which
   sequences rules in a caller-configurable order via `.run()`/
   `.reorder()` and never short-circuits (every rule always runs),
   producing a `SignalValidationReport` (`is_valid`/`errors`/
   `warnings`/`trace`); plus `SignalValidator`, the facade most callers
   use, defaulting to the five rules above, whose
   `validate_and_annotate()` merges the report into a new
   `SignalResult`'s own `metadata["signal_validation"]` (via
   `SignalResult.with_metadata`, never mutating the original). No AI,
   no Risk Engine, no Strategy Engine, no order execution, no trading
   decisions — Parts 1-4 were left untouched.
7. `services/` (event bus) — a concrete, simple in-memory `EventBus`
   implementing `events.interfaces.event_bus.EventBus`. *(Unblocked
   today — all event contracts and types already exist; can proceed in
   parallel with items 1–6.)*
8. ~~`strategies/risk_management/` — foundation: `BaseRiskManager`,
   `RiskContext`, `RiskResult`, exceptions, utils.~~ **Done (Risk Engine
   Part 1):** mirrors `analysis/`'s and `signals/`'s own Part 1
   foundations. `RiskContext` composes only existing `core.entities`
   (`Signal`, `Portfolio`, optional `MarketState`); `RiskResult` holds
   only `approved`/`risk_score`/`confidence`/`summary`/`metadata`. No
   position sizing, no stop-loss/take-profit, no order execution, no
   strategy/trading decisions, no AI.
   ~~`strategies/risk_management/` — a concrete `BaseRiskManager`
   implementation.~~ **Done (Risk Engine Part 2):** `BasicRiskManager`
   (`strategies/risk_management/basic_risk_manager.py`). Evaluates
   signal confidence, optional signal strength (read defensively from
   `Signal.metadata`, since `Signal` has no dedicated `strength`
   field), portfolio exposure (from `RiskContext.portfolio`), and
   market-data availability (`RiskContext.has_market_state()`) into a
   weighted `risk_score`, combined with configurable hard-threshold
   checks to decide `approved`; every intermediate value is recorded
   in `RiskResult.metadata`. Still no position sizing, no
   stop-loss/take-profit, no order execution, no strategy/trading
   decisions, no AI.
   ~~`strategies/risk_management/` — position sizing and protective
   levels.~~ **Done (Risk Engine Part 3):** three further independent
   concrete `BaseRiskManager` implementations -- `PositionSizeRule`
   (`position_size_rule.py`, fixed-fractional risk sizing),
   `StopLossRule` (`stop_loss_rule.py`, direction-aware stop price),
   and `TakeProfitRule` (`take_profit_rule.py`, direction-aware target
   price via a configurable `risk_reward_ratio`). None of the three
   imports or depends on either of the other two, or on
   `BasicRiskManager`; each computes its own ATR-or-percentage
   distance estimate independently. Covered by
   `tests/test_risk_rules.py`.
   `strategies/` — remaining Risk Engine work: additional concrete
   `BaseRiskManager` implementations beyond Part 3 (e.g.
   drawdown/volatility-based risk) and an optional composite/
   aggregating risk manager.
   ~~`strategies/` — foundation: `BaseStrategy`, `StrategyContext`,
   `StrategyResult`, exceptions, utils.~~ **Done (Strategy Engine
   Part 1):** mirrors `analysis/`'s, `signals/`'s, and `strategies.
   risk_management`'s own Part 1 foundations. `StrategyContext`
   composes existing `analysis.result.AnalysisResult`(s), an optional
   `signals.result.SignalResult`, and an optional `strategies.
   risk_management.result.RiskResult`; `StrategyResult` holds only
   `action` (reusing `core.enums.SignalDirection`)/`confidence`/
   `summary`/`metadata`. `BaseStrategy` deliberately does not implement
   `core.interfaces.strategy.Strategy` (a different, MarketState-in/
   Signal-out shape). No concrete strategy, no AI, no order execution,
   no broker integration. Covered by `tests/test_strategies.py`.
   ~~`strategies/` — at least one concrete `BaseStrategy`
   implementation.~~ **Done (Strategy Engine Part 2):** `BasicStrategy`
   (`strategies/basic_strategy.py`). Looks up one `AnalysisResult`
   (matched by `analyzer_name`, default `"AnalysisAggregator"`) and
   optionally reads `signal_result`/`risk_result`, combining them into
   a confidence-weighted `overall_score` thresholded onto
   `SignalDirection.BUY`/`SELL`/`HOLD`, an agreement-based
   `consistency_score`, and a risk gate downgrading an unapproved
   `BUY`/`SELL` to `HOLD`. Covered by `tests/test_basic_strategy.py`.
   ~~`strategies/` — a way to combine multiple `BaseStrategy`
   instances.~~ **Done (Strategy Engine Part 3):** `StrategyAggregator`
   (`strategies/aggregator.py`), itself a `BaseStrategy` subclass,
   mirroring `AnalysisAggregator`/`SignalAggregator` one and two layers
   down. Runs one or more injected sub-strategies (defaulting to a
   single `BasicStrategy()`) and weight-averages their signed
   `action`/`confidence` into one final `StrategyResult`, recording
   `overall_score`/`confidence`/`completeness`/`agreement` in full.
   Covered by `tests/test_strategy_aggregator.py`.
   `strategies/` — remaining work: additional concrete `BaseStrategy`
   implementations beyond `BasicStrategy` (e.g. trend-following,
   mean-reversion — `StrategyAggregator` can already combine them once
   they exist).
   ~~`strategies/portfolio_management/` — foundation: `BasePortfolioManager`,
   `PortfolioContext`, `PortfolioResult`, exceptions, utils.~~ **Done
   (Portfolio Management Part 1):** mirrors `analysis/`'s, `signals/`'s,
   `strategies`'s, and `strategies.risk_management`'s own Part 1
   foundations. `PortfolioContext` composes the current `core.entities.
   portfolio.Portfolio` (required), an optional `strategies.result.
   StrategyResult`, and an optional `strategies.risk_management.result.
   RiskResult`; `PortfolioResult` holds only `new_positions_allowed`/
   `confidence`/`summary`/`metadata`. No concrete manager, no allocation
   algorithm, no rebalancing logic, no broker integration. Covered by
   `tests/test_portfolio_management.py`.
   ~~`strategies/portfolio_management/` — a concrete `BasePortfolioManager`
   implementation.~~ **Done (Portfolio Management Part 2):**
   `BasicPortfolioManager` (`strategies/portfolio_management/
   basic_portfolio_manager.py`). Gates a candidate new position on four
   independent deterministic checks — open-position count, aggregate
   exposure, single-symbol concentration (independent of the aggregate
   check), and upstream signal/risk agreement (when available) — all
   four must pass for `new_positions_allowed=True`, with every reason
   recorded in `metadata["hard_reject_reasons"]`. No scoring,
   allocation, position-sizing, rebalancing, or broker integration.
   Covered by `tests/test_basic_portfolio_manager.py`.
   ~~`strategies/portfolio_management/` — a composite/aggregating
   portfolio manager combining several concrete `BasePortfolioManager`
   instances.~~ **Done (Portfolio Management Part 3):**
   `PortfolioManager` (`strategies/portfolio_management/
   portfolio_manager.py`), mirroring `StrategyAggregator`'s/
   `SignalAggregator`'s role one layer down each. Combines one or more
   injected `BasePortfolioManager` instances (default: a single plain
   `BasicPortfolioManager()`) via a confidence-and-weight-weighted vote
   of each sub-manager's signed `new_positions_allowed` decision,
   thresholded via a configurable `allow_threshold` back onto a final
   bool. No scoring changes to Parts 1-2, no allocation,
   position-sizing, rebalancing, or broker integration. Covered by
   `tests/test_portfolio_manager.py`.
   ~~`strategies/portfolio_management/` — a second aggregator mirroring
   `StrategyAggregator`'s naming convention.~~ **Done (Portfolio
   Management Part 4):** `PortfolioAggregator` (`strategies/
   portfolio_management/aggregator.py`). Functionally the same
   weighted-vote combining role `PortfolioManager` (Part 3) plays, but
   named/documented to mirror `analysis.aggregator.AnalysisAggregator`/
   `signals.aggregator.SignalAggregator`/`strategies.aggregator.
   StrategyAggregator`'s `*Aggregator` convention. Deliberately
   independent of `PortfolioManager` — neither imports or subclasses
   the other. No scoring changes to Parts 1-3, no allocation,
   position-sizing, rebalancing, or broker integration. Covered by
   `tests/test_portfolio_aggregator.py`.
   `strategies/portfolio_management/` — remaining work: allocation/
   position-sizing logic across multiple assets and rebalancing of
   existing positions.
9. ~~`backtesting/` — foundation: `BaseBacktester`, `BacktestContext`,
   `BacktestResult`, exceptions, utils.~~ **Done (Backtesting Engine
   Part 1):** mirrors `analysis/`'s, `signals/`'s, `strategies`'s, and
   `strategies.risk_management`'s/`strategies.portfolio_management`'s
   own Part 1 foundations. `BacktestContext` composes historical
   `core.entities.candle.Candle` data (validated non-empty and
   chronologically ordered), a `strategies.base_strategy.BaseStrategy`
   instance, and a starting `core.entities.portfolio.Portfolio`;
   `BacktestResult` holds only `final_portfolio`/`summary`/`trades`/
   `metadata`. No concrete backtester, no trade simulation, no PnL
   calculation, no performance statistics.
   ~~`backtesting/` — a concrete `BaseBacktester` implementation.~~
   **Done (Backtesting Engine Part 2):** `BasicBacktester`
   (`backtesting/basic_backtester.py`). Replays `BacktestContext.candles`
   sequentially and chronologically through `BacktestContext.strategy`,
   building a minimal per-candle `StrategyContext` (empty
   `analysis_results`, no `signal_result`/`risk_result`, current candle
   exposed only via `metadata`) and consuming only the resulting
   `StrategyResult.action`. `BUY` opens one long `Position` with all
   available cash at the candle's `close` price (no-op if already
   holding a position, or with no cash available); `SELL` closes an
   open position in full at `close` (no-op if none open); `HOLD` is a
   no-op. No slippage, commissions, leverage, or performance statistics
   are modeled. A strategy raising `InsufficientStrategyDataError` for
   a candle is treated as "skip that candle", never a fatal error for
   the whole run. Never mutates `BacktestContext` or anything reachable
   from it. Covered by `tests/test_basic_backtester.py`.
   ~~`backtesting/` — a standalone portfolio-simulation helper.~~
   **Done (Backtesting Engine Part 3):** `PortfolioSimulator`
   (`backtesting/portfolio_simulator.py`). Simulates a `Portfolio`'s
   cash/position state independently of any concrete backtester:
   `open_position`/`close_position` (long or short, one open position
   per symbol at a time, no pyramiding — spends/credits the full cash
   balance and calculates `realized_pnl` on close), `update_market_price`
   (marks an open position's `current_price`/`unrealized_pnl`),
   `total_equity()` (cash plus mark-to-market value of open positions),
   and `Candle`-based convenience wrappers. Deep-copies its `Portfolio`
   at construction (never mutates the caller's instance) and never
   mutates any `Candle` passed to it. No leverage, margin, slippage,
   commissions/fees, partial fills, portfolio optimization, or
   performance metrics. Factors out mechanics `BasicBacktester` already
   implements inline, but is purely additive — `BasicBacktester` itself
   is untouched and does not use it yet. Covered by
   `tests/test_portfolio_simulator.py`.
   ~~`backtesting/` — performance statistics.~~ **Done (Backtesting
   Engine Part 4):** `metrics.py` (`backtesting/metrics.py`) —
   `BacktestMetrics` (a frozen result container: trade counts,
   `win_rate`, `gross_profit`/`gross_loss`, `profit_factor`,
   average/largest win and loss, initial/final equity, total return, an
   `equity_curve`, `max_drawdown_pct`/`_amount`, `sharpe_ratio`, and a
   traceability `metadata` dict) and `calculate_metrics(result,
   initial_portfolio, ...)`, the entry point that derives every
   statistic from the closed `Position` entries on an already-produced
   `BacktestResult.final_portfolio` and the `Portfolio` the run started
   from — it does not run a backtest or simulate any trade itself,
   preserving `backtesting`'s consumer-only role. The smaller building
   blocks (`win_rate`, `profit_factor`, `compute_equity_curve`,
   `max_drawdown`, `sharpe_ratio`) are also independently importable.
   Deterministic and side-effect free; reuses only existing `core`/
   `backtesting` types, no new domain concepts or exception types; every
   other Backtesting Engine file (`base.py`, `context.py`, `result.py`,
   `exceptions.py`, `utils.py`, `basic_backtester.py`,
   `portfolio_simulator.py`) was left completely untouched. Covered by
   `tests/test_metrics.py`.
   ~~`backtesting/` — human-readable report generation (`report.py`).~~
   **Done (Backtesting Engine Part 5):** `BacktestReport`
   (`backtesting/report.py`). Wraps an already-produced `BacktestResult`
   (Parts 1/2) and `BacktestMetrics` (Part 4) into four read-only,
   deterministic views: `summary()` (one paragraph), `detailed_summary()`
   (multi-section text: overview, trade statistics, equity/return,
   risk), `trades_summary()`/`metrics_summary()` (structured `dict`s),
   and `full_report()` (all four combined). Computes nothing itself —
   every figure is read directly from the supplied result/metrics,
   never recomputed — and never mutates either input. No charts, no
   HTML/PDF, no CSV export, no file writing, no logging, no AI, no
   broker/order-execution logic. Covered by `tests/test_report.py`.
   `backtesting/` — remaining work: additional concrete backtesters
   (e.g. one consuming `signals.result.SignalResult` directly, or
   supporting multiple concurrent positions per symbol/short
   selling/slippage/fees), and optionally adopting `PortfolioSimulator`
   inside `BasicBacktester` or a new concrete backtester.
10. ~~`execution/` — foundation: `BaseExecutionEngine`,
    `ExecutionContext`, `ExecutionResult`, exceptions, utils.~~ **Done
    (Execution Engine Part 1):** mirrors `analysis/`'s, `signals/`'s,
    `strategies/`'s, `strategies.risk_management`'s,
    `strategies.portfolio_management`'s, and `backtesting/`'s own
    Part 1 foundations. `ExecutionContext` composes only existing
    abstractions — the current `Portfolio` (required), an optional
    `StrategyResult` (the candidate trading decision), an optional
    `RiskResult` (that decision's risk evaluation), and an optional
    `PortfolioResult` (whether the portfolio has capacity) for one
    symbol/timeframe; `ExecutionResult` holds only
    `execution_approved`/`confidence`/`summary`/`metadata`. `execution/`
    is the last framework-only checkpoint before an approved decision
    would ever reach a broker/exchange — it never places that order
    itself. No concrete execution engine, no broker integration, no
    exchange API, no order execution, no networking, no threading, no
    async, no AI. Imported directly (`from execution import
    BaseExecutionEngine, ExecutionContext, ExecutionResult, ...`) — no
    parent package to re-export through. Covered by
    `tests/test_execution.py`.
    `execution/` — remaining work: a first concrete
    `BaseExecutionEngine` implementation (e.g. one that requires all
    three upstream results present and in agreement before approving),
    then eventually real order placement/broker integration — the
    latter explicitly out of scope until that milestone is reached
    (free-first constraint still applies to any future broker choice).
10a. ~~`services/` — foundation: `BaseService`, `ServiceContext`,
    `ServiceResult`, exceptions, utils.~~ **Done (Services Part 1):**
    mirrors `analysis/`'s, `signals/`'s, `strategies/`'s,
    `strategies.risk_management`'s, `strategies.portfolio_management`'s,
    `backtesting/`'s, and `execution/`'s own Part 1 foundations, adapted
    to `services/`'s different, heterogeneous nature (external
    integrations/cross-cutting concerns, not one stage of the
    trading-decision pipeline). `ServiceContext` composes no domain
    entities — a generic `service_name` + free-form `payload` +
    `metadata` envelope, since each concrete service (notification,
    AI/LLM client, scheduler, event bus) interprets `payload`
    differently. `ServiceResult` holds only `success`(`bool`)/`summary`/
    `metadata` — no `confidence` field, unlike every trading-decision
    result above (a service call either succeeds or it doesn't).
    Framework only: no concrete service, no broker integration, no
    execution logic, no networking, no threading, no async, no AI.
    Imported directly (`from services import BaseService,
    ServiceContext, ServiceResult, ...`) — no parent package to
    re-export through. Covered by `tests/test_services.py`.
    `services/` — remaining work: item 7 above (a concrete in-memory
    `EventBus`) is the lowest-friction first concrete service, followed
    by `notification_service.py`/`ai_service.py`/`scheduler_service.py`.
11. `database/` — general-purpose `DatabaseRepository` implementation;
    resolve its relationship to `data/storage.py` (see open design
    question in PROJECT_STATE.md) before or during this work.
12. `models/` — ML price-prediction models, once there's a concrete
    consumer (likely `analysis/ai/` or `strategies/`) that needs one.
13. `app/` — use-case orchestration wiring together data, analysis,
    signals, strategies, backtesting, execution, database, and
    services.
14. `api/` inbound REST surface (`routes/`, `schemas/`, `server.py`,
    `dependencies.py`) — exposing `app/`'s use cases over HTTP, last,
    since it depends on `app/` being real.

`utils/` and `config/` can be populated incrementally at any point
whenever a genuinely cross-cutting helper or new setting is needed —
they have no upstream blockers.
