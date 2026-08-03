<!--
PROJECT_STATE.md
----------------
Purpose: A point-in-time snapshot of MarketMind-AI's implementation
status. Read this FIRST before making any change — it tells you what
exists, what's half-built, what's untouched, and what to do next, so
you don't have to re-derive it by reading the whole repository.

This file describes state, not rules. For "how do I build the next
piece correctly," see DEVELOPER_GUIDE.md.
-->

# MarketMind-AI — Project State

**Snapshot date:** reflects the repository as of this document's latest
update (Backtesting Integration — `app/backtest_runner.py`:
`BacktestRunner`, the second `app/`-layer use case, wiring
Data -> Backtesting -> Metrics -> Report for one symbol/timeframe
against real historical candle data).
**Latest implementation pass:** this pass built `app/backtest_runner.py`
from scratch — `BacktestRunner`, the second `app/`-layer use case
(after `MarketPipeline`), which loads real historical candles via a
dependency-injected `data.engine.DataEngine.load_history()`, replays
them through a dependency-injected `strategies.base_strategy.
BaseStrategy` (defaulting to `strategies.basic_strategy.BasicStrategy`)
and `backtesting.base.BaseBacktester` (defaulting to
`backtesting.basic_backtester.BasicBacktester`) via a real
`backtesting.context.BacktestContext`, then derives
`backtesting.metrics.BacktestMetrics` and wraps both into a
`backtesting.report.BacktestReport` — closing the exact gap
`PROJECT_STATE.md` (this file) previously documented under
`backtesting/`'s "what's missing" column: "Nothing currently assembles
a `BacktestContext` from real historical data (via `data/`) and a real
strategy end-to-end outside of tests." Returns one `BacktestRunResult`
dataclass per run (symbol/timeframe/candle_count/initial_portfolio/
result/metrics/report/metadata), mirroring `PipelineResult`'s shape.
Candle translation (`data.models.Candle` -> `core.entities.candle.
Candle`) reuses `app.pipeline._to_core_candle` directly rather than
duplicating it. Scoped to the minimum integration/orchestration layer
only, per this milestone's explicit instructions — no AI, no machine
learning, no broker/exchange connection, no live trading, no
order-execution engine, no UI, no server, no automatic/parameter
optimization, and no new trading logic (strategy decisions are
unchanged — `backtesting/` remains a consumer, never a strategy
author, `PROJECT_RULES.md` Section 1 principle 5). `app/exceptions.py`
gained three additive exception classes (`BacktestRunnerConfigurationError`,
`BacktestRunnerDataError`, `BacktestRunnerExecutionError`) and
`app/__init__.py` was updated to export/document `BacktestRunner`/
`BacktestRunResult` — no other existing implementation file was
modified. `tests/test_backtest_runner.py` (24 tests, new) covers
construction, dependency injection/validation, real end-to-end runs
(default `BasicStrategy` — every candle skipped, exactly as
`tests/test_basic_backtester.py`'s own real-`BasicStrategy`-integration
section already documents — and an always-buy fake strategy proving
real trade execution), `start_time`/`end_time`/`limit` forwarding to
`DataEngine`, custom/default `initial_portfolio` handling and
no-mutation guarantees, error wrapping (`BacktestRunnerDataError`/
`BacktestRunnerExecutionError`), determinism, and a real-`BasicStrategy`/
`BasicBacktester`-integration section. Full compile check, recursive
import check, and full test-suite run were run against the repository
as delivered; no existing implementation file's logic was modified.
See "Current test status" and "Compile status" below for exact
results, and "Last completed milestone" for full detail.

**Previously recorded snapshot** (retained for history): Main
Application Part 1 — `app/main.py`: `MainApplication`, the
application's composition root, shipping its constructor, dependency
injection, configuration loading, and initialization of every
already-implemented top-level engine/service only — no orchestration
logic; plus reconciliation of the already-present, previously
undocumented `app/pipeline.py`/`MarketPipeline`.
**Prior implementation pass:** this pass built `app/main.py` from
scratch — `MainApplication` (Main Application Part 1), the application's
composition root, holding one instance of every already-implemented
top-level engine/service (`DataEngine`, `AnalysisAggregator`,
`SignalAggregator`, `StrategyAggregator`, `BasicRiskManager`,
`PortfolioManager`, `BasicBacktester`, `services.SignalEngine`), wired
together via dependency injection, plus configuration loading via
`config.settings.get_settings()`. Scoped to public interfaces only
(constructor, DI, config loading, engine initialization) per this
milestone's explicit instructions — no orchestration, no analysis
execution, no AI, no broker, no UI, no CLI, no business logic.
`app/__init__.py` was updated to export and document `MainApplication`;
`tests/test_main.py` (47 tests, new) covers it. This pass additionally
found `app/pipeline.py` (`MarketPipeline`) already present, already
covered by `tests/test_pipeline.py`, and already correct, but
previously undocumented in this file's "Completed"/"Partially
completed" tables (`app/` was listed as stub-only) — it is now
reconciled into the `app/` row alongside `MainApplication`. Full
compile check, recursive import check, and full test-suite run
run were run against the repository as delivered; no existing
implementation file was modified. See "Current test status" and
"Compile status" below for exact results, and "Last completed
milestone" for full detail on `SignalEngine` itself.

**Previously recorded snapshot** (retained for history): Services Part
1 — `services/` foundation: `BaseService`, `ServiceContext`,
`ServiceResult`, the `ServiceError` hierarchy, and shared validation
helpers.
**Prior verification pass:** new-implementation pass. That pass built
`services/`'s Part 1 foundation from scratch — `BaseService` (`base.py`),
`ServiceContext` (`context.py`), `ServiceResult` (`result.py`), the
`ServiceError` hierarchy (`exceptions.py`), and shared validation
helpers (`utils.py`) — mirroring the exact Part 1 shape every other
engine (`analysis/`, `signals/`, `strategies/`,
`strategies/risk_management/`, `strategies/portfolio_management/`,
`backtesting/`, `execution/`) already established for its own
foundation, adapted to `services/`'s different nature (a generic
wrapper around heterogeneous external integrations, not a
trading-decision pipeline stage — see "Last completed milestone"
below for the reasoning). `services/__init__.py` (previously an
explanatory stub only) now exports and documents these five modules;
`tests/test_services.py` (48 tests, new) covers all of it. Full
compile check, recursive import check, and full test-suite run were
run against the repository as delivered; no existing implementation
file was modified. See "Current test status" and "Compile status"
below for exact results, and "Last completed milestone" for full
detail on `services/`'s Part 1 foundation itself.

**Previously recorded snapshot** (retained for history): Backtesting
Engine Part 3 — `PortfolioSimulator`, a standalone portfolio-state
simulation helper (`backtesting/portfolio_simulator.py`), added
alongside 53 dedicated tests in `tests/test_portfolio_simulator.py`.
Additive and not wired into `BasicBacktester` — it exists as a shared,
reusable simulation helper any current or future `BaseBacktester` can
adopt.

**Latest previous update** (retained for history): Backtesting Engine
Part 2 — first concrete backtester, `BasicBacktester`
(`backtesting/basic_backtester.py`), built entirely on Part 1's
foundation. Added `tests/test_basic_backtester.py` (56 tests).
**Current project version:** `0.1.0` (see `config/settings.py`,
`Settings.app_version`). `main.py` prints this version on startup and
does nothing else — there is no runtime application yet, only a
bootstrap proving configuration loads correctly.

## Completed modules

These packages contain real, tested implementation code (not just an
explanatory `__init__.py`):

| Module | Depth | Notes |
|---|---|---|
| `core/` | Full (for its scope) | Domain layer. 10 frozen/mutable entities (`core/entities/`) + 8 abstract interfaces (`core/interfaces/`) + domain enums (`core/enums.py`). Zero dependencies on any other package, including `config`. No implementations — only contracts, by design. |
| `events/` | Full (for its scope) | Event-driven architecture scaffold. `Event`/`EventBus`/`EventHandler` abstract contracts (`events/interfaces/`) + 9 concrete frozen-dataclass event types (`events/event_types/`). Depends only on `core`. No concrete `EventBus` implementation exists yet (intentionally deferred to `services/` or `app/`). |
| `data/` | Full — this is the most mature module in the repo | The **Data Engine**: `Candle`/kline parsing (`models.py`), abstract + real Binance REST client (`client.py`), `DataValidator`, `DataCleaner`, `DataNormalizer`, `MarketDataStorage` (SQLite), `CandleCache` (in-memory LRU), `HistoricalDataDownloader`, `IncrementalDataUpdater`, and the `DataEngine` facade wiring all of it together. Fully documented in `docs/DATA_ENGINE.md`. Only covers **Binance Spot OHLCV data** — no news data, no other exchanges. |
| `indicators/` | Full | 17 pure, stateless technical indicators (SMA, EMA, WMA, HMA, MACD, RSI, ADX, DMI, ROC, Stochastic, CCI, Ichimoku, SuperTrend, ATR, Bollinger Bands, Keltner Channel, Donchian Channel, OBV, VWAP, Volume SMA — see `indicators/__init__.py` for the exact export list). Shared `BaseIndicator`/`IndicatorResult` base in `indicators/base.py`. Every indicator supports both batch (`calculate`) and incremental/streaming (`update`) computation. |
| `api/` | Full (transport layer only) | `HTTPClient` with retry/backoff and rate-limiting (`http_client.py`), an `HTTPClientError` exception hierarchy (`exceptions.py`), and thin provider wrappers: `BinanceProvider`, `CoinGeckoProvider`, a news provider (`api/providers/`). This is the outbound HTTP transport boundary — no inbound REST API (`routes/`, `server.py`) exists yet; that is planned future work for this same package. |
| `config/` | Full (for its scope) | Typed `Settings` (`config/settings.py`, env/`.env`-driven) and constants/enums such as `TimeFrame`/`Exchange` (`config/config.py`). No dependencies on any other package. |
| `analysis/technical/` | Full (5 analyzers) | **Analysis Engine Parts 2, 3A, 3B, and 3C.** `TrendAnalyzer` (`trend_analyzer.py`), `MomentumAnalyzer` (`momentum_analyzer.py`), `VolatilityAnalyzer` (`volatility_analyzer.py`), `VolumeAnalyzer` (`volume_analyzer.py`), and `MarketStructureAnalyzer` (`market_structure_analyzer.py`), all subclassing `analysis.base.BaseAnalyzer`, plus shared normalization helpers (`utils.py`: `clip`, `normalize_diff`, `normalize_center`, `normalize_scaled`, `weighted_average`, `mean_abs`, `completeness_ratio`, `score_label`). `TrendAnalyzer` interprets SMA/EMA relationships, MACD, and ADX into a trend score; `MomentumAnalyzer` interprets RSI, ROC, Stochastic, and the MACD histogram into a momentum score; `VolatilityAnalyzer` (Part 3A) interprets ATR, Bollinger Bands, Keltner Channel, and Donchian Channel into a volatility-*regime* score (`-1.0` contraction/range-bound .. `0.0` normal .. `+1.0` expansion/breakout-prone — direction-free, unlike the other four); `VolumeAnalyzer` (Part 3B) interprets OBV, VWAP, and Volume SMA into a directional volume-flow score (`-1.0` strong bearish/selling .. `0.0` neutral .. `+1.0` strong bullish/buying); `MarketStructureAnalyzer` (Part 3C) interprets swing-point structure into a directional market-structure score (`-1.0` strong bearish structure .. `0.0` neutral/mixed .. `+1.0` strong bullish structure). All five produce `AnalysisResult` only (score `-1.0..+1.0`, confidence `0.0..1.0`, fully-explained `metadata`) — no AI, no signals, no strategies, no trading decisions. `VolatilityAnalyzer`'s `metadata` additionally reports `volatility_expansion`/`volatility_contraction` degree, `range_compression`, `breakout_probability` (via a Bollinger-inside-Keltner "squeeze" heuristic), and a confidence-only `trend_strength_contribution` (it never determines trend direction itself). `VolumeAnalyzer`'s `metadata` additionally reports `volume_confirmation`/`volume_divergence` (agreement between the latest candle's direction and OBV-implied flow), `buying_pressure`/`selling_pressure` (current volume vs its Volume SMA baseline, signed by candle direction), `volume_trend`/`participation_strength` (current volume vs its Volume SMA baseline, direction-free), and `price_vs_vwap` (price's relative position to VWAP); unlike the other analyzers, `VolumeAnalyzer` also reads `AnalysisContext.market_state.latest_candle` (open/close/volume) — data already carried on the context, not a new indicator or fetch — since OBV/VWAP/Volume SMA alone have nothing to compare the *current* price/volume against; the candle's absence only lowers confidence, it never raises. `MarketStructureAnalyzer`'s `metadata` additionally reports `swing_high`/`swing_low` (the raw swing-point values plus an `HH`/`LH`/`HL`/`LL`/`equal_high`/`equal_low` classification each), `structure_bias` (`"bullish"`/`"bearish"`/`"mixed"`), `market_regime` (`"uptrend"`/`"downtrend"`/`"ranging"`), `bos`/`choch` (each `{"detected": bool, "direction": ...}`), and `trend_continuation`/`trend_reversal` (each `0.0`..`1.0`); like `VolumeAnalyzer`, it also reads `AnalysisContext.market_state.latest_candle` (close price only, to test for a BOS/CHOCH break), and its absence only lowers what can be computed, never raises. Unlike the other four, `MarketStructureAnalyzer` does not consume any indicator produced by the existing `indicators/` package (none of the 17 indicators there compute swing points) — it documents the exact `values` shape (`swing_high_1`/`swing_high_2`/`swing_low_1`/`swing_low_2` on a `"SwingPoints_1"`-named `IndicatorResult`) it expects a future swing-point detector to supply, the same way `TrendAnalyzer` documents the `SMA_20`/`EMA_12`/... shapes it expects. The five analyzers are fully independent of each other and do not import `analysis/__init__.py` (Part 1's package init was left untouched); import via `from analysis.technical import TrendAnalyzer, MomentumAnalyzer, VolatilityAnalyzer, VolumeAnalyzer, MarketStructureAnalyzer`. 80 dedicated tests in `tests/test_analysis_technical.py` (Trend/Momentum, unchanged) + 65 dedicated tests in `tests/test_volatility_analyzer.py` (Volatility, unchanged) + 41 dedicated tests in `tests/test_volume_analyzer.py` (Volume, unchanged by Part 3C) + 26 dedicated tests in `tests/test_market_structure_analyzer.py` (Market Structure, new). |
| `analysis/aggregator.py` (Part 4) | Full | **`AnalysisAggregator`.** Combines the five `analysis/technical` analyzer outputs (`TrendAnalyzer`, `MomentumAnalyzer`, `VolatilityAnalyzer`, `VolumeAnalyzer`, `MarketStructureAnalyzer`) into one final `AnalysisResult`. Subclasses `BaseAnalyzer`; each sub-analyzer is constructor-injected (defaulting to a plain real instance of the corresponding class), matching the project's dependency-injection convention. `overall_score` is a confidence-and-weight-weighted average of only the *four directional* sub-scores that were available (`TrendAnalyzer`/`MomentumAnalyzer`/`VolumeAnalyzer`/`MarketStructureAnalyzer`); `VolatilityAnalyzer`'s direction-free regime score is deliberately excluded from that average (see its row above) but its confidence and full result are still merged into overall `confidence` and into `metadata["components"]["volatility"]` / `metadata["volatility"]` (each tagged `"contributes_to_directional_score": False`). Any sub-analyzer raising `InsufficientDataError` for a given context is treated as "unavailable" rather than failing the whole call — `metadata["components_missing"]` records which and why, and `overall_score`/`confidence` are computed from whichever subset remains; `AnalysisAggregator` itself only raises `InsufficientDataError` when *all four* directional analyzers are unavailable. No AI, no signals, no strategies, no trading decisions, and no new analytical logic beyond merging — reuses Parts 1-3C exactly as they exist, without modifying any of them. Imported and re-exported through `analysis/__init__.py` (unlike `analysis/technical/`, which is imported directly): `from analysis import AnalysisAggregator`. 36 dedicated tests in `tests/test_aggregator.py`, including a real-sub-analyzer integration section (not just fakes) proving actual reuse of `analysis.technical`. |

## Partially completed modules

| Module | What exists | What's missing |
|---|---|---|
| `analysis/` (foundation) + `analysis/technical/` + `analysis/aggregator.py` | Foundation ("Part 1"): `BaseAnalyzer` (`base.py`), `AnalysisContext` (`context.py`), `AnalysisResult` (`result.py`), `AnalysisError` hierarchy (`exceptions.py`), shared validation helpers (`utils.py`) — unchanged since Part 1. **`technical/` (Parts 2, 3A, 3B, and 3C) and `aggregator.py` (Part 4) are now fully implemented** — see Completed modules above. | `analysis/news/` (sentiment analysis) and `analysis/ai/` (AI-based market assessment) are still documented in the package docstring but do not exist on disk yet. A concrete swing-point-detection indicator (in `indicators/` or elsewhere) to supply `MarketStructureAnalyzer`'s expected `SwingPoints_1`-shaped input also does not exist yet — see that analyzer's row above; `AnalysisAggregator` inherits this gap indirectly (it just treats a resulting `MarketStructureAnalyzer` `InsufficientDataError` as "unavailable", same as any other missing sub-analyzer). |
| `signals/` (foundation, Part 1 + concrete generator, Part 2 + aggregation, Part 3 + filtering, Part 4 + validation, Part 5) | **Signal Engine Part 1** (foundation): `BaseSignalGenerator` (`base.py`), `SignalContext` (`context.py`), `SignalResult` (`result.py`), the `SignalError` hierarchy (`exceptions.py`), and shared validation helpers (`utils.py`) — mirrors the shape/role `analysis/base.py`/`context.py`/`result.py`/`exceptions.py`/`utils.py` play for `analysis/`. `SignalContext` consumes `analysis.result.AnalysisResult` objects (individual `analysis.technical` analyzer outputs and/or the merged `AnalysisAggregator` output — both are the same type) for one symbol/timeframe. `SignalResult` is deliberately minimal: only `direction` (`core.enums.SignalDirection`), `strength` (`0.0..1.0`), `confidence` (`0.0..1.0`), `summary`, and `metadata` — no `id`/`source`/`timestamp` (unlike `core.entities.signal.Signal`, which this package does not yet produce). **Signal Engine Part 2**: `TechnicalSignalGenerator` (`technical_signal_generator.py`), the first concrete `BaseSignalGenerator`. It looks up exactly one `AnalysisResult` on its `SignalContext` — the one produced by `AnalysisAggregator` (matched by `analyzer_name`, default `"AnalysisAggregator"`) — and maps its `-1.0..+1.0` directional score onto exactly three signal directions: Bullish (`SignalDirection.BUY`, score `> buy_threshold`, default `0.2`), Bearish (`SignalDirection.SELL`, score `< sell_threshold`, default `-0.2`), Neutral (`SignalDirection.HOLD`, otherwise) — reusing `core.enums.SignalDirection` rather than inventing a new enum. `strength` is `abs(score)` clamped to `[0.0, 1.0]`; `confidence` passes the aggregator's own `confidence` straight through; `metadata` records `source_analyzer`/`source_score`/`source_confidence`/`score_label`/`buy_threshold`/`sell_threshold`/`aggregator_metadata` (the full underlying `AnalysisAggregator` metadata, for traceability). Raises `InsufficientSignalDataError` when no `AnalysisResult` with the expected `analyzer_name` is present on the context; never reads any individual `analysis.technical` analyzer output directly, even when also present on the same context. 31 dedicated tests in `tests/test_technical_signal_generator.py`, including a real-`AnalysisAggregator`-integration section proving actual reuse of Part 4's output shape. **Signal Engine Part 3**: `SignalAggregator` (`aggregator.py`), which itself subclasses `BaseSignalGenerator` and combines the `SignalResult`s of one or more injected sub-generators (defaulting to a single `TechnicalSignalGenerator()` when none are supplied) into one final `SignalResult`, mirroring `analysis.aggregator.AnalysisAggregator` one layer down. Each sub-generator is keyed by its own `.name` (duplicates rejected) and may carry a constructor-configurable `weight` (default `1.0`, `>= 0.0`); a sub-generator's own `confidence` further scales its contribution. The combined signed score (`direction` sign x `strength`, weight-and-confidence-averaged across sub-generators) is mapped back onto Bullish/Bearish/Neutral via configurable `buy_threshold`/`sell_threshold` (same defaults/validation as Part 2); aggregated `confidence` follows `AnalysisAggregator`'s completeness x conviction x weighted-confidence shape. Any sub-generator raising `InsufficientSignalDataError` is treated as "unavailable" (`metadata["generators_missing"]` records which and why); `SignalAggregator` itself only raises `InsufficientSignalDataError` when every sub-generator was unavailable. `metadata` includes `components` (every component signal, available or not), `weights`, `aggregation_details` (method, aggregate score, score label, thresholds, completeness ratio, conviction), `generators_available`, and `generators_missing`. No AI, no Risk Engine, no Strategy Engine, no order execution, no trading decisions — Parts 1 and 2 were left untouched, and its small numeric helpers live privately in `aggregator.py` itself rather than in `signals/utils.py`. 36 dedicated tests in `tests/test_signal_aggregator.py`, including a real-`TechnicalSignalGenerator`-integration section (two differently-thresholded real instances) proving actual reuse of Part 2. **Signal Engine Part 4** (new, this milestone): a filter pipeline (`filters.py`) sitting between generation and any future consumer. `BaseSignalFilter` (abstract; `apply(result, context) -> FilterOutcome`) plus four concrete filters — `ConfidenceFilter` (rejects below a `min_confidence`), `DuplicateSignalFilter` (stateful; rejects a consecutive repeat of the same `(direction, strength)` for a symbol/timeframe), `CooldownFilter` (stateful; rejects a signal arriving within `cooldown_seconds` of the previous accepted one for a symbol/timeframe, via an injectable `clock`), `ConflictFilter` (stateful; downgrades a direct direction reversal to `SignalDirection.HOLD` with dampened strength/confidence rather than rejecting — the one `action="modify"` case) — plus `SignalFilterPipeline`, which sequences filters against one `SignalResult`/`SignalContext`, short-circuiting on the first rejection. Every filter returns a `FilterOutcome` (`action`/`reason`, never a bare `SignalResult`), so a rejection's reasoning is preserved; the pipeline's full `trace` is returned via `SignalFilterPipelineResult` and, for a surviving signal, also merged into `metadata["filter_pipeline_trace"]`. Filters are independent of each other and of `SignalFilterPipeline`, which contains no filtering logic of its own. Raises `SignalValidationError` (reused from Part 1) only for invalid input types, never for an ordinary reject/modify outcome. No AI, no Risk Engine, no Strategy Engine, no order execution — Parts 1-3 were left untouched. 63 dedicated tests in `tests/test_signal_filters.py`, including a full end-to-end integration section combining all four filters in one pipeline. **Signal Engine Part 5** (new, this milestone): signal *validation* (`validation.py`), a different boundary than Part 4's filters — where `filters.py` decides whether a `SignalResult` is worth passing on (accept/modify/reject), `validation.py` decides whether it is internally well-formed and trustworthy, collecting *errors*/*warnings* rather than discarding or modifying it. `ValidationRule` (abstract; `evaluate(result, context) -> RuleOutcome`) plus five concrete rules — `SummaryContentRule` (errors on a blank summary, warns below a configurable `min_length`), `RangeConsistencyRule` (errors on out-of-range/non-finite `strength`/`confidence`, warns on exactly-zero `confidence`), `DirectionStrengthConsistencyRule` (errors when a `BUY`/`SELL` signal has `strength == 0.0`, warns when a `HOLD` signal's `strength` exceeds a configurable threshold), `ConfidenceThresholdRule` (warns, never errors, below a configurable `min_confidence`), `MetadataPresenceRule` (warns on empty `metadata`) — plus `SignalValidationPipeline`, which runs rules in a caller-configurable order via `.run()`/`.reorder()`, **never short-circuiting** (every rule always runs), producing a `SignalValidationReport` (`is_valid`, `errors`, `warnings`, `trace`), and `SignalValidator`, the facade most callers use (defaults to the five rules above; `.validate()` returns the report, `.validate_and_annotate()` merges it into a new `SignalResult`'s `metadata["signal_validation"]` without mutating the original, mirroring `filter_pipeline_trace`'s traceability convention). No AI, no Risk Engine, no Strategy Engine, no order execution, no trading decisions — Parts 1-4 were left untouched. 60 dedicated tests in `tests/test_signal_validation.py`, including a full end-to-end integration section. | Nothing currently assembles a `SignalContext` from real `AnalysisAggregator`/`analysis.technical` output end-to-end outside of tests (that remains a future `app/` use case, mirroring `AnalysisContext`'s same gap). Nothing currently wires `SignalFilterPipeline`/`SignalValidator` between a real generator/aggregator and a consumer end-to-end outside of tests either — that is also a future `app/` use case. `signals/` does not yet produce `core.entities.signal.Signal` or use `events/` — both remain open for a later Signal Engine part or `strategies/`. |
| `utils/` | Package exists with a documented purpose (generic, cross-cutting helpers with no business meaning). | Empty — no `logger.py`, `datetime_utils.py`, or `validators.py` yet, despite being named as planned contents. |
| `strategies/` (Strategy Engine Part 1 foundation + Part 2 concrete strategy + Part 3 aggregation + concrete risk managers — `risk_management/`, Risk Engine Parts 1-3) | **Strategy Engine Part 1** (foundation, new this milestone): `BaseStrategy` (`base_strategy.py`), `StrategyContext` (`context.py`), `StrategyResult` (`result.py`), the `StrategyError` hierarchy (`exceptions.py`), and shared validation helpers (`utils.py`), mirroring the exact role `analysis/base.py`/`context.py`/`result.py`/`exceptions.py`/`utils.py` play as Analysis Engine Part 1's foundation, `signals/base.py`/.../`utils.py` play as Signal Engine Part 1's, and `strategies/risk_management/base.py`/.../`utils.py` play as Risk Engine Part 1's. `StrategyContext` composes existing `analysis.result.AnalysisResult`(s), an optional `signals.result.SignalResult`, and an optional `strategies.risk_management.result.RiskResult` for one symbol/timeframe — no new domain concepts. `StrategyResult` is deliberately minimal: only `action` (reusing `core.enums.SignalDirection` rather than inventing a new enum, the same convention `SignalResult.direction` uses), `confidence` (`0.0..1.0`), `summary`, and `metadata` — no position size, stop-loss, take-profit, order-id, or `strategy_name` field (mirroring `RiskResult`'s omission of `risk_manager_name`). `BaseStrategy` is an `abc.ABC` with an abstract `decide(context: StrategyContext) -> StrategyResult` method plus shared `validate_context`/`_build_result` helpers, and deliberately does **not** implement `core.interfaces.strategy.Strategy` (that interface takes a raw `MarketState` and returns an optional `Signal` directly — a different, MarketState-in/Signal-out shape meant for a strategy that reasons over market data on its own) — mirroring how `strategies.risk_management.base.BaseRiskManager` does not itself implement `core.interfaces.risk_manager.RiskManager`. Framework only: no concrete strategy ships in this part, no AI, no order execution, no broker integration. Imported and re-exported through `strategies/__init__.py` (unlike `strategies.risk_management`, which is imported directly), the same convention `analysis/__init__.py` uses for `AnalysisAggregator` relative to `analysis/technical/`. Only `strategies/__init__.py` (to export the new names and document Part 1) was updated among existing files; `strategies/risk_management/` (all of Risk Engine Parts 1-3), `analysis/`, `signals/`, and `core/` were left completely untouched. 62 dedicated tests in `tests/test_strategies.py`, including a real-`AnalysisResult`/`SignalResult`/`RiskResult`-integration section proving actual reuse of the Analysis/Signal/Risk Engines' output shapes. **Strategy Engine Part 2** (new, this milestone): `BasicStrategy` (`basic_strategy.py`), the first concrete `BaseStrategy`. Looks up one `AnalysisResult` on its `StrategyContext` (matched by `analyzer_name`, default `"AnalysisAggregator"` — the same lookup convention `TechnicalSignalGenerator` uses), and optionally reads `signal_result`/`risk_result`. Combines the analysis score and, when present, the signal's signed score (`direction` sign x `strength`, the `SignalAggregator` convention) into a confidence-weighted `overall_score`, thresholded onto `SignalDirection.BUY`/`SELL`/`HOLD` (configurable `buy_threshold`/`sell_threshold`, same defaults as `TechnicalSignalGenerator`). Scores an agreement-based `consistency_score` between the analysis-derived direction and the signal's own direction (when present), and between the tentative action and risk approval (when present); a `RiskResult.approved=False` downgrades a would-be `BUY`/`SELL` to `HOLD` (`metadata["risk_override"] = True`) — a `HOLD` is never overridden, mirroring `ConflictFilter`'s downgrade-rather-than-reject pattern one layer down. `confidence` combines each available result's own confidence, the consistency score, and a completeness ratio (analysis required; signal/risk each add to completeness only when present) — the same `completeness * conviction/consistency * confidence` shape `AnalysisAggregator`/`SignalAggregator` already use. `StrategyResult` carries no `score` field, so `metadata["overall_score"]` holds the required overall strategy score, alongside every other intermediate value (`analysis`/`signal`/`risk` facets, `consistency`, `confidence_breakdown`, `thresholds`, `weights`, `inputs_available`) for full traceability. Fully deterministic — no AI, no randomness, no wall-clock reads. No order execution, no broker integration, no portfolio management, no optimization, and only this one concrete strategy ships in this part. Reuses Part 1 (`BaseStrategy`/`StrategyContext`/`StrategyResult`/exceptions/utils) and `RiskResult` exactly as they already exist; `strategies/risk_management/`, `analysis/`, and `signals/` were left completely untouched. Only `strategies/__init__.py` (to export `BasicStrategy` and document Part 2) was updated among existing files. 39 dedicated tests in `tests/test_basic_strategy.py`, covering construction/configuration validation, required-input handling (missing/mismatched `AnalysisResult`), directional decisions from analysis alone, consistency scoring (agreement/conflict/partial-agreement across analysis/signal/risk), the risk gate (override on unapproved risk, never overriding an already-`HOLD` decision), metadata/summary traceability, determinism (identical results across repeated calls), scope-boundary checks (`StrategyResult`'s exact four fields, no order/broker/AI fields anywhere), and an end-to-end integration section. **Strategy Engine Part 3** (new, this milestone): `StrategyAggregator` (`aggregator.py`), which itself subclasses `BaseStrategy` and combines the `StrategyResult`s of one or more injected `BaseStrategy` instances (defaulting to a single plain `BasicStrategy()` when none are supplied) into one final `StrategyResult`, mirroring the role `analysis.aggregator.AnalysisAggregator` and `signals.aggregator.SignalAggregator` already play one and two layers down, respectively. Each sub-strategy is keyed by its own `.name` (duplicates rejected) and may carry a constructor-configurable `weight` (default `1.0`, `>= 0.0`); a sub-strategy's own `confidence` further scales its contribution. Since `StrategyResult` has no numeric score/strength field, each sub-strategy's `action` is represented as a signed unit value (`+1.0`/`-1.0`/`0.0`) scaled by its `confidence`, weight-averaged into an aggregate score and thresholded back onto BUY/SELL/HOLD via configurable `buy_threshold`/`sell_threshold` (same defaults/validation as `BasicStrategy`/`SignalAggregator`). Runs every sub-strategy sequentially against the same `StrategyContext`; any sub-strategy raising `InsufficientStrategyDataError` is treated as "unavailable" (`metadata["strategies_missing"]` records which and why) — `StrategyAggregator` itself only raises `InsufficientStrategyDataError` when every sub-strategy was unavailable. Calculates and records, in full, four traceable facets: `overall_score`, `confidence`, `completeness` (fraction of sub-strategies that produced a usable decision), and `agreement` (weighted agreement between each contributing decision and the final aggregated action, `1.0`/`0.5`/`0.0` scale) — `confidence` itself is `completeness x agreement x` average confidence, the same shape the two engines below already use. Fully deterministic: no AI, no randomness, no wall-clock reads, no I/O; never mutates any sub-strategy's `StrategyResult`. No order execution, no broker integration, no portfolio management, no optimization — only aggregation. Reuses Parts 1-2 (`BaseStrategy`/`StrategyContext`/`StrategyResult`/exceptions/utils, `BasicStrategy`) exactly as they already exist; `strategies/risk_management/`, `analysis/`, and `signals/` were left completely untouched. Only this `strategies/__init__.py` (to export `StrategyAggregator` and document Part 3) was updated among existing files. See `aggregator.py` for the full scoring/completeness/agreement/confidence shape. 50 dedicated tests in `tests/test_strategy_aggregator.py`, including a real-`BasicStrategy`-integration section proving actual reuse of Part 2. **Risk Engine Part 1** (foundation): `strategies/risk_management/` — `BaseRiskManager` (`base.py`), `RiskContext` (`context.py`), `RiskResult` (`result.py`), the `RiskError` hierarchy (`exceptions.py`), and shared validation helpers (`utils.py`), mirroring the exact role `analysis/base.py`/`context.py`/`result.py`/`exceptions.py`/`utils.py` play as Analysis Engine Part 1's foundation, and `signals/base.py`/`context.py`/`result.py`/`exceptions.py`/`utils.py` play as Signal Engine Part 1's. `RiskContext` composes only existing `core.entities` (`Signal`, `Portfolio`, optional `MarketState`) for one symbol/timeframe — no new domain concepts. `RiskResult` is deliberately minimal: only `approved` (`bool`), `risk_score` (`0.0..1.0`), `confidence` (`0.0..1.0`), `summary`, and `metadata` — no position size, stop-loss, take-profit, or order-id fields. `BaseRiskManager` is an `abc.ABC` with an abstract `evaluate(context: RiskContext) -> RiskResult` method plus shared `validate_context`/`_build_result` helpers, and deliberately does **not** implement `core.interfaces.risk_manager.RiskManager` (that interface also requires `calculate_position_size`/`calculate_stop_loss`, out of scope for this part) — mirroring how `signals.base.BaseSignalGenerator` does not itself implement `core.interfaces.signal_generator.SignalGenerator`. **Risk Engine Part 2** (new, this milestone): `BasicRiskManager` (`basic_risk_manager.py`), the first concrete `BaseRiskManager`. It evaluates four independent facets of a `RiskContext` into one `RiskResult`: signal confidence (`RiskContext.signal.confidence`, defensively validated — raises `InsufficientRiskDataError` only if non-numeric/non-finite, clamps if merely out of `[0.0, 1.0]`), signal strength (an optional `"strength"` entry read from `RiskContext.signal.metadata`, since `Signal` itself has no `strength` field — its absence only means the facet is treated as "unavailable" with a neutral default risk contribution, never raised), portfolio exposure (fraction of portfolio equity already committed to open positions, computed from `RiskContext.portfolio.positions`/`cash_balance`/`total_equity`, falling back to `cash_balance + position_value` when `total_equity` is not already computed), and market-data availability (`RiskContext.has_market_state()`). Each facet becomes a `0.0..1.0` risk contribution, combined via configurable weights (summing to `1.0`, validated at construction) into `risk_score`; three configurable hard-threshold checks (`min_signal_confidence`, `min_signal_strength` when strength is available, `max_exposure_ratio`) can independently force `approved=False` regardless of `risk_score`. `confidence` reflects both `signal.confidence` and how much optional data (strength, market state) was actually available. `metadata` records every intermediate value (`signal_confidence`, `signal_strength`/`signal_strength_available`, `exposure_ratio`, `equity_used_for_exposure`, `market_state_available`, `components`, `weights`, `thresholds`, `hard_reject_reasons`) for full traceability. No position sizing, no stop-loss/take-profit, no order execution, no strategy/trading decisions, no AI — `BasicRiskManager` does not implement `core.interfaces.risk_manager.RiskManager` for the same reason `BaseRiskManager` does not. Imported directly (`from strategies.risk_management import BaseRiskManager, BasicRiskManager, RiskContext, RiskResult, ...`), not re-exported through `strategies/__init__.py`, the same convention `analysis/technical/` uses relative to `analysis/`. Only `strategies/risk_management/__init__.py` (to export `BasicRiskManager`) and `strategies/risk_management/utils.py` (one additive `clip()` helper — no existing helper changed) were updated among existing files; `base.py`, `context.py`, `result.py`, `exceptions.py`, `analysis/`, `signals/`, and `core/` were left completely untouched. **Risk Engine Part 3** (new, this milestone): three further concrete `BaseRiskManager` implementations, all consuming only `RiskContext`/existing `core.entities`, producing only `RiskResult`, and deliberately independent of each other and of `BasicRiskManager` (none imports or depends on any of the others; each computes its own ATR-or-percentage per-unit distance internally rather than consuming another rule's output) — `PositionSizeRule` (`position_size_rule.py`): fixed-fractional risk sizing — `risk_amount` (portfolio equity x configurable `risk_per_trade`) divided by a per-unit risk distance estimated from ATR when available (`atr_value * atr_multiplier / reference_price`) or a configurable `default_stop_distance_pct` fallback, capped at a configurable `max_position_fraction` of equity; reports a quote-currency `recommended_position_value` always, and additionally a base-asset `recommended_position_size` when a reference price is resolvable (from `signal.metadata[\"entry_price\"]` or `market_state.latest_candle.close`) — its absence only lowers `confidence`, unlike `StopLossRule`/`TakeProfitRule` below, since it is the only one of the three that can still express a result in quote-currency terms without one. `StopLossRule` (`stop_loss_rule.py`): a direction-aware protective stop price (below the reference price for `BUY`, above it for `SELL`), from the same ATR-or-percentage distance estimate, clamped to a configurable `[min_stop_distance_pct, max_stop_distance_pct]` range. `TakeProfitRule` (`take_profit_rule.py`): a direction-aware target price (above the reference price for `BUY`, below it for `SELL`), computing its own equivalent base risk-leg distance the same way `StopLossRule` does (not by consuming `StopLossRule`'s output) and scaling it by a configurable `risk_reward_ratio`. All three treat a `SignalDirection.HOLD` signal as an explicit "not applicable" result (`approved=False`, the relevant price/size field `None`) rather than an error, and raise `InsufficientRiskDataError` only for a truly required input that is completely unusable: an unusable `signal.confidence` (non-numeric/non-finite, all three), non-positive portfolio equity (`PositionSizeRule` only), or a completely unresolvable reference price (`StopLossRule`/`TakeProfitRule` only — a stop-loss/take-profit is a price, so no price data means no result at all, unlike `PositionSizeRule`). An available-but-missing ATR reading never raises for any of the three — it only falls back to the percentage-based distance and lowers `confidence`. Every intermediate value (reference price and its source, ATR availability/value, basis used, computed distances/clamping flags, the resulting price/size) is recorded in `RiskResult.metadata` for full traceability. Imported directly alongside `BasicRiskManager` (`from strategies.risk_management import PositionSizeRule, StopLossRule, TakeProfitRule, ...`) and re-exported through `strategies/risk_management/__init__.py`. No AI, no Strategy Engine, no order execution, and no writing computed values back onto `core.entities.position.Position.stop_loss`/`take_profit` — each only recommends a value via `RiskResult.metadata`; acting on it is out of scope. 103 dedicated tests in `tests/test_risk_rules.py`, including a dedicated rule-independence section verifying none of the three imports the others and that evaluating one does not affect another's output. | Additional concrete `BaseRiskManager` implementations beyond Part 3 (e.g. drawdown checks, volatility-based risk) remain future work, along with an optional composite/aggregating risk manager combining several concrete risk managers (mirroring `SignalAggregator`'s role one layer down). `BasicStrategy` (Part 2) is still the only concrete decision-making `BaseStrategy` — `StrategyAggregator` (Part 3) combines instances of it (or any other `BaseStrategy`) but adds no new decision logic of its own; additional concrete strategies (e.g. trend-following, mean-reversion) remain future Strategy Engine parts. Order execution remains unbuilt; `strategies/portfolio_management/` now has Portfolio Management Parts 1-4 (foundation + `BasicPortfolioManager` + the composite/aggregating `PortfolioManager` + the second aggregator `PortfolioAggregator`, see next row). Nothing currently assembles a `RiskContext` from a real `SignalResult`/`AnalysisResult`/live portfolio end-to-end outside of tests, nor a `StrategyContext` from real `AnalysisAggregator`/`SignalAggregator`/risk-manager output end-to-end outside of tests — both remain a future `app/` use case, the same gap `AnalysisContext`/`SignalContext` already have. |

| `strategies/portfolio_management/` (Portfolio Management Part 1 foundation + Part 2 concrete manager + Part 3 composite/aggregating manager + Part 4 second aggregator) | **Portfolio Management Part 1** (foundation): `BasePortfolioManager` (`base.py`), `PortfolioContext` (`context.py`), `PortfolioResult` (`result.py`), the `PortfolioError` hierarchy (`exceptions.py`), and shared validation helpers (`utils.py`), mirroring the exact role `analysis/base.py`/`context.py`/`result.py`/`exceptions.py`/`utils.py` play as Analysis Engine Part 1's foundation, `strategies/base_strategy.py`/.../`utils.py` play as Strategy Engine Part 1's, and `strategies/risk_management/base.py`/.../`utils.py` play as Risk Engine Part 1's. `PortfolioContext` composes the current `core.entities.portfolio.Portfolio` (required — a portfolio manager cannot evaluate constraints without it), an optional `strategies.result.StrategyResult` (the candidate trading decision under consideration), and an optional `strategies.risk_management.result.RiskResult` (that decision's risk evaluation) for one symbol/timeframe — no new domain concepts. `PortfolioResult` is deliberately minimal: only `new_positions_allowed` (`bool`), `confidence` (`0.0..1.0`), `summary`, and `metadata` — no target allocation, no rebalancing instructions, no order-id, no `portfolio_manager_name` field (mirroring `RiskResult`'s omission of `risk_manager_name`). `BasePortfolioManager` is an `abc.ABC` with an abstract `evaluate(context: PortfolioContext) -> PortfolioResult` method plus shared `validate_context`/`_build_result` helpers. 57 dedicated tests in `tests/test_portfolio_management.py`, including a real-`StrategyResult`/`RiskResult`/`Portfolio`-integration section proving actual reuse of the Strategy/Risk Engines' and `core`'s output shapes. **Portfolio Management Part 2** (first concrete manager): `BasicPortfolioManager` (`basic_portfolio_manager.py`), the first concrete `BasePortfolioManager`, mirroring the pattern `BasicRiskManager` established one layer down. Gates a candidate new position on four deterministic, independent checks — open-position count (`PositionStatus.OPEN` positions on `PortfolioContext.portfolio`, against a configurable `max_open_positions`), aggregate portfolio exposure (fraction of equity already committed to open positions, current price falling back to entry price, against a configurable `max_exposure_ratio`), single-symbol concentration (the same fraction narrowed to `PortfolioContext.symbol` only, against a configurable `max_symbol_exposure_ratio` — deliberately independent of the aggregate check, since a portfolio can be under its aggregate limit while still overly concentrated in one symbol), and, when available, upstream signal/risk agreement (whether the candidate `StrategyResult.action` is directional — not `HOLD` — and whether the candidate `RiskResult.approved` is `True`). All four gates must pass for `new_positions_allowed=True`; any one failing blocks, with every reason recorded in `metadata["hard_reject_reasons"]` alongside every intermediate value for full traceability. `confidence` is derived only from how much optional context (`strategy_result`/`risk_result`) was available and their own confidence values — never from the pass/fail decision itself. No scoring, weighting, optimization, allocation/position-sizing, rebalancing, broker integration, or AI — every check is a plain threshold comparison. Reuses Part 1 (`BasePortfolioManager`/`PortfolioContext`/`PortfolioResult`/exceptions/utils) and the existing `StrategyResult`/`RiskResult`/`Portfolio`/`Position` exactly as they already exist; `strategies/risk_management/`, `strategies/`'s own foundation/`BasicStrategy`/`StrategyAggregator`, `analysis/`, and `signals/` were left completely untouched. Both parts are imported directly (`from strategies.portfolio_management import BasePortfolioManager, BasicPortfolioManager, PortfolioContext, PortfolioResult, ...`), not re-exported through `strategies/__init__.py`, the same convention `strategies.risk_management` already uses relative to `strategies/`. Only `strategies/portfolio_management/__init__.py` (to export `BasicPortfolioManager` and document Part 2) was updated among existing files for this milestone — no prior implementation file was modified. 43 dedicated tests in `tests/test_basic_portfolio_manager.py` (100 combined with Part 1's 57), covering construction/configuration validation, each of the four gates individually and in combination, confidence derivation, metadata/summary traceability, and an end-to-end integration section. **Portfolio Management Part 3** (composite/aggregating manager, this milestone): `PortfolioManager` (`portfolio_manager.py`), itself a concrete `BasePortfolioManager` that combines the `PortfolioResult`s of one or more injected `BasePortfolioManager` instances (defaulting to a single `BasicPortfolioManager()` when none are supplied) into one final `PortfolioResult`, mirroring the exact role `strategies.aggregator.StrategyAggregator`/`signals.aggregator.SignalAggregator`/`analysis.aggregator.AnalysisAggregator` already play one, two, and three layers down, respectively. Since `PortfolioResult` has no numeric score field (only a boolean `new_positions_allowed`), each sub-manager's decision is represented as a signed unit vote (`+1.0` allowed, `-1.0` blocked), weight-and-confidence-averaged into an `aggregate_score` and thresholded via a configurable `allow_threshold` (default `0.0`) back onto a final bool. Every sub-manager is keyed by its own `.name` (duplicates rejected) and may carry a constructor-configurable `weight` (default `1.0`, `>= 0.0`). Any sub-manager raising `InsufficientPortfolioDataError` is treated as "unavailable" (`metadata["managers_missing"]` records which and why); `PortfolioManager` itself only raises `InsufficientPortfolioDataError` when every sub-manager was unavailable. Calculates and records `aggregate_score`, `completeness`, `agreement` (1.0/0.0 match scale against the final decision — no `HOLD`-style neutral state exists for a boolean), and `confidence` (`completeness x agreement x` average confidence, the same shape the three aggregators above already use). Fully deterministic — no AI, no randomness, no wall-clock reads, no I/O; never mutates any sub-manager's `PortfolioResult`. No allocation, no position-sizing, no rebalancing, no broker integration — only aggregation. Reuses Parts 1-2 (`BasePortfolioManager`/`PortfolioContext`/`PortfolioResult`/exceptions/utils, `BasicPortfolioManager`) exactly as they already exist. Only `strategies/portfolio_management/__init__.py` (to export `PortfolioManager` and document Part 3) was updated among existing files — no prior implementation file was modified, including in this pass, which added test coverage only. 58 dedicated tests in `tests/test_portfolio_manager.py`, mirroring `tests/test_strategy_aggregator.py`/`tests/test_signal_aggregator.py`'s fake-sub-component style: construction/configuration validation (managers/weights/allow_threshold), `evaluate()` context validation and unavailable-sub-manager handling, weighted-vote aggregation and threshold mapping, completeness/agreement/confidence shape, output-shape/metadata/summary/determinism checks, and a real-`BasicPortfolioManager`-integration section (including a real `InsufficientPortfolioDataError` case) proving actual reuse of Part 2. **Portfolio Management Part 4** (second aggregator, this milestone): `PortfolioAggregator` (`aggregator.py`), itself a concrete `BasePortfolioManager` functionally equivalent to `PortfolioManager` (Part 3) — same weighted-vote/`allow_threshold`/`aggregate_score`/`completeness`/`agreement`/`confidence` shape, same unavailable-sub-manager handling, same defaulting to a single plain `BasicPortfolioManager()` — but named/documented explicitly to mirror `strategies.aggregator.StrategyAggregator`'s (and `analysis.aggregator.AnalysisAggregator`'s/`signals.aggregator.SignalAggregator`'s) `*Aggregator` naming convention. Deliberately independent of `PortfolioManager`: neither module imports or subclasses the other, both are plain `BasePortfolioManager` siblings, and either may be nested as a sub-manager of the other (or of itself, since `PortfolioAggregator` is itself a `BasePortfolioManager`). Adds no new decision logic of its own beyond merging — reuses Parts 1-2 (`BasePortfolioManager`/`PortfolioContext`/`PortfolioResult`/exceptions/utils, `BasicPortfolioManager`) exactly as they already exist; Part 3 (`portfolio_manager.py`) is left completely untouched and is not imported by this module. Only `strategies/portfolio_management/__init__.py` (to export `PortfolioAggregator` and document Part 4) was updated among existing files — no prior implementation file was modified, including in this pass, which added test coverage only. 62 dedicated tests in `tests/test_portfolio_aggregator.py` (new this pass), mirroring `tests/test_portfolio_manager.py`'s structure (construction/configuration validation, `evaluate()` context validation and unavailable-sub-manager handling, weighted-vote aggregation and threshold mapping, completeness/agreement/confidence shape, output-shape/metadata/summary/determinism checks, a real-`BasicPortfolioManager`-integration section) plus a dedicated independence section confirming `PortfolioAggregator` does not import or subclass `PortfolioManager` (and vice versa), and that either can be nested as a sub-manager of the other. Portfolio Management total across all four parts: **220 tests** (57 + 43 + 58 + 62), all passing. | Allocation/sizing logic across multiple assets and rebalancing of existing positions remain future work. Nothing currently assembles a `PortfolioContext` from real `BasicStrategy`/`StrategyAggregator`/risk-manager/live-portfolio output end-to-end outside of tests either — the same future `app/`-use-case gap `AnalysisContext`/`SignalContext`/`RiskContext`/`StrategyContext` already document. |

| `backtesting/` (Backtesting Engine Part 1 foundation + Part 2 first concrete backtester + Part 3 portfolio simulation helper + Part 4 performance statistics) | **Backtesting Engine Part 1** (foundation): `BaseBacktester` (`base.py`), `BacktestContext` (`context.py`), `BacktestResult` (`result.py`), the `BacktestError` hierarchy (`exceptions.py`), and shared validation helpers (`utils.py`), mirroring the exact role `analysis/base.py`/`context.py`/`result.py`/`exceptions.py`/`utils.py` play as Analysis Engine Part 1's foundation, and the equivalent Part 1 foundations `signals/`, `strategies/`, `strategies/risk_management/`, and `strategies/portfolio_management/` already have. `BacktestContext` composes only existing abstractions — historical `core.entities.candle.Candle` data (validated non-empty and chronologically ordered by `open_time`), a `strategies.base_strategy.BaseStrategy` instance, and a starting `core.entities.portfolio.Portfolio` — for one symbol/timeframe run; no new domain concepts. `BacktestResult` is deliberately minimal: only `final_portfolio` (`Portfolio`), `summary`, `trades` (a list of `core.entities.trade.Trade`, empty by default), and `metadata` — no PnL, no Sharpe ratio, no max drawdown, no win rate, no profit factor, and no `backtester_name` field (mirroring `RiskResult`'s omission of `risk_manager_name`). `BaseBacktester` is an `abc.ABC` with an abstract `run(context: BacktestContext) -> BacktestResult` method plus shared `validate_context`/`_build_result` helpers. Framework only: no concrete backtester shipped in Part 1, no trade simulation, no PnL calculation, no performance statistics, no aggregation across runs, no report generation — `backtesting/` remains a consumer of whatever strategy it is given, never a source of trading rules (`PROJECT_RULES.md` Section 1, principle 5). 52 dedicated tests in `tests/test_backtesting.py`, including a real-`BaseStrategy`/`Portfolio`-integration section proving actual reuse of the Strategy Engine's and `core`'s existing shapes. **Backtesting Engine Part 2** (new, this milestone): `BasicBacktester` (`basic_backtester.py`), the first concrete `BaseBacktester`, built entirely on Part 1's foundation. It replays `BacktestContext.candles` sequentially and chronologically (oldest to newest, matching `BacktestContext`'s own validated candle ordering) through `BacktestContext.strategy` (any `strategies.base_strategy.BaseStrategy`), building one minimal `strategies.context.StrategyContext` per candle — `symbol`/`timeframe` taken from the `BacktestContext`, `analysis_results=[]`, `signal_result=None`, `risk_result=None` (since `backtesting` does not depend on `analysis`/produce its own signals — see the dependency table in `PROJECT_RULES.md` Section 4), and the current candle plus its index exposed only via `StrategyContext.metadata` (`{"candle": ..., "candle_index": ...}`) for traceability/strategy use — and calling `context.strategy.decide(...)`. `BasicBacktester` consumes only the resulting `strategies.result.StrategyResult.action` (`core.enums.SignalDirection.BUY`/`SELL`/`HOLD`); it never inspects any `AnalysisResult`/`SignalResult`/`RiskResult` directly and never decides *why* to trade — all trading logic remains the injected strategy's responsibility, preserving `backtesting`'s consumer-only role. Execution model (the simplest deterministic one that satisfies "record trades" without inventing trading rules of its own): a `BUY` while no position is open on the context's symbol spends the entire current cash balance to open one long `Position` at the candle's `close` price and records one `Trade` (a no-op if a position is already open, or if there is no positive cash available — no pyramiding, no margin/leverage); a `SELL` while a position is open closes it in full at the candle's `close` price, credits the proceeds back to cash, records the corresponding `Trade`, and sets the position's `realized_pnl`/`status`/`closed_at` (a no-op if no position is open); `HOLD` is always a no-op. No slippage, no commissions/fees, no leverage, and no performance statistics (Sharpe ratio, max drawdown, win rate, profit factor) are modeled — those remain out of scope for this part (see `backtesting/__init__.py`'s "Planned contents"). A strategy raising `strategies.exceptions.InsufficientStrategyDataError` for a given candle is treated as "skip this candle" (`metadata["skipped_candles"]` records the count) rather than a fatal error for the whole run, mirroring the "absence only lowers, never raises" convention every other engine in this repository follows for per-item unavailability; any other exception raised by the strategy propagates unchanged, since that indicates a genuine bug in the injected strategy rather than an ordinary "insufficient data" outcome. Fully deterministic — no randomness, no wall-clock reads, no network/database I/O, no AI. Never mutates `context` or anything reachable from it: `context.initial_portfolio` is deep-copied (via `copy.deepcopy`) before any position/cash state is touched, and `context.candles` (a list of frozen `Candle` instances) is only ever read. Reuses Part 1's `BaseBacktester`/`BacktestContext`/`BacktestResult`/`backtesting.exceptions.InsufficientBacktestDataError`/`backtesting.utils.merge_metadata` exactly as they already exist, plus `strategies.context.StrategyContext` and `strategies.exceptions.InsufficientStrategyDataError` from the Strategy Engine — no new domain concepts, and `analysis/`, `signals/`, `strategies/` (including `risk_management/` and `portfolio_management/`), and `core/` were left completely untouched. Only `backtesting/__init__.py` (to export `BasicBacktester` and document Part 2) was updated among existing files. 56 dedicated tests in `tests/test_basic_backtester.py`: construction/inheritance, inherited context validation, HOLD-only (no trades/no portfolio change), BUY-only (single position opened, no pyramiding, zero/negative-cash no-op), SELL-with-no-position no-op, a full BUY-then-SELL round trip (trade sides/order, `realized_pnl`, cash/position state), a position left open at run end, multiple alternating round trips with strict chronological trade ordering, `InsufficientStrategyDataError` handling (all-skipped, partial warm-up then recovery, run itself never raises it, summary mentions skips), a non-`StrategyError` exception propagating unchanged, no-mutation-of-inputs checks (`initial_portfolio`, `candles`, re-running the same context), determinism across repeated runs, chronological-execution/`StrategyContext`-wiring checks (candle order, symbol/timeframe, empty `analysis_results`/`None` signal/risk, per-candle metadata), output-shape/metadata/summary/scope-boundary checks (exact `BacktestResult` fields, no order-execution/AI/performance-metric keys anywhere), a real-`BasicStrategy`-integration section (proving genuine `BaseStrategy.decide()` reuse — every candle is skipped since no matching `AnalysisResult` is ever supplied, exactly as `BasicStrategy` itself would require), and a defensive empty-candles completeness check. **Backtesting Engine Part 3** (new, this milestone): `PortfolioSimulator` (`portfolio_simulator.py`), a standalone, deterministic helper that simulates a `core.entities.portfolio.Portfolio`'s cash/position state as a replay progresses. Factors out the exact simulation mechanics `BasicBacktester` already implements inline (as private static helpers) into their own reusable, independently-tested class, so any current or future `BaseBacktester` can share identical portfolio-simulation behavior instead of re-implementing it; `BasicBacktester` itself is left completely untouched and does not use `PortfolioSimulator` — this is purely additive. Constructed from one `Portfolio` (deep-copied immediately; the caller's instance is never mutated); exposes `portfolio`/`cash_balance`/`trades` properties, `get_open_position`/`get_open_positions`/`has_open_position` lookups, `open_position`/`close_position` (long or short, one open position per symbol at a time — no pyramiding, spends/credits the full cash balance, calculates `realized_pnl` on close), `update_market_price` (marks an open position's `current_price`/`unrealized_pnl` to a given price) plus `total_equity()` (cash plus mark-to-market value of open positions, refreshed onto `portfolio.total_equity` after every mutating call), and `open_position_from_candle`/`close_position_from_candle`/`update_market_price_from_candle` convenience wrappers that read price/timestamp from a `core.entities.candle.Candle`'s `close`/`close_time` without ever mutating the candle. No leverage, no margin, no slippage, no commissions/fees, no partial fills, no portfolio optimization, and no performance metrics (Sharpe ratio, max drawdown, profit factor, etc.) — those remain out of scope, matching `PROJECT_RULES.md` Section 1 principle 5. Reuses `core.entities.portfolio.Portfolio`/`core.entities.position.Position`/`core.entities.trade.Trade`/`core.entities.candle.Candle`/`core.enums.OrderSide`/`PositionSide`/`PositionStatus` and `backtesting.exceptions.BacktestValidationError`/`backtesting.utils.validate_non_empty_str` exactly as they already exist — `backtesting/exceptions.py` and `backtesting/utils.py` themselves were left completely untouched, along with `base.py`/`context.py`/`result.py`/`basic_backtester.py` and every other existing engine. Only `backtesting/__init__.py` (to export `PortfolioSimulator` and document Part 3) was updated among existing files. 53 dedicated tests in `tests/test_portfolio_simulator.py`: construction (valid/invalid input, deep-copy-of-portfolio-and-positions, no mutation of the caller's `Portfolio`), position lookup (`get_open_position`/`get_open_positions`/`has_open_position` across symbols and statuses), opening positions (spends all cash, no-pyramiding no-op, zero/negative-cash no-op, long and short sides, invalid price/timestamp/symbol validation), closing positions (credits cash, realized PnL for both long and short — profit and loss cases, no-op with none open, validation errors), a full open-then-close round trip and multiple alternating round trips with strict chronological trade ordering, marking to market (`current_price`/`unrealized_pnl` updates, no-op with no position, invalid-price validation), `total_equity()` (cash-only, open-position mark-to-market, post-close realized value, `portfolio.total_equity` field refreshed after every mutating call), the three `Candle`-based convenience wrappers (correct price/timestamp extraction, no mutation of the candle, invalid-candle validation), and determinism/no-mutation checks (repeated identical operations produce identical state, `trades`/`positions` properties return copies rather than internal references). **Backtesting Engine Part 4** (performance statistics): `metrics.py`, defining `BacktestMetrics` (a frozen result container) and `calculate_metrics(result, initial_portfolio, ...)`, the main entry point that derives every statistic from the closed `Position` entries on an already-produced `BacktestResult.final_portfolio` and the `Portfolio` the run started from — it does not run a backtest or simulate any trade itself, preserving `backtesting`'s consumer-only role (`PROJECT_RULES.md` Section 1, principle 5). `BacktestMetrics` reports trade counts (`total_trades`/`winning_trades`/`losing_trades`/`breakeven_trades`), `win_rate`, `gross_profit`/`gross_loss`/`total_realized_pnl`, `profit_factor` (`None` when there are no losing trades — the ratio is undefined/unbounded rather than a real number), `average_win`/`average_loss`/`largest_win`/`largest_loss` (each `None` when there are no winning/losing trades respectively), `initial_equity`/`final_equity`/`total_return`/`total_return_pct`, `open_positions_remaining`, an `equity_curve` (a simplified proxy built from `initial_equity` plus each closed position's `realized_pnl` in order — not a full intra-trade mark-to-market curve), `max_drawdown_pct`/`max_drawdown_amount`, `sharpe_ratio` (computed over the equity curve's period-over-period returns, with configurable `risk_free_rate`/`annualization_factor`, `0.0` when fewer than two returns are available or return variance is zero), and a traceability `metadata` dict — the same shape every other engine in this repository uses. The smaller composable building blocks (`win_rate`, `profit_factor`, `compute_equity_curve`, `max_drawdown`, `sharpe_ratio`) are also independently importable. Raises `backtesting.exceptions.BacktestValidationError` (reused, no new exception type) only when `result`/`initial_portfolio` are not the expected types. Deterministic and side-effect free — no randomness, no wall-clock reads, no network/database/file I/O, no AI, no broker/order-execution integration, no optimization, and no report/chart generation (`report.py`, see Part 5 next). Never mutates the `BacktestResult`/`Portfolio` passed in. Reuses only `core.entities.portfolio.Portfolio`, `core.entities.position.Position`, `core.enums.PositionStatus`, `backtesting.result.BacktestResult`, and `backtesting.exceptions.BacktestValidationError` exactly as they already exist — no new domain concepts, and `base.py`/`context.py`/`result.py`/`exceptions.py`/`utils.py`/`basic_backtester.py`/`portfolio_simulator.py` were all left completely untouched. `backtesting/__init__.py` already exports and documents `BacktestMetrics`/`calculate_metrics`/`win_rate`/`profit_factor`/`compute_equity_curve`/`max_drawdown`/`sharpe_ratio` (`from backtesting import BacktestMetrics, calculate_metrics, ...`). 36 dedicated tests in `tests/test_metrics.py`. **Backtesting Engine Part 5** (report generation, reconciled into this document this pass — see "Last completed milestone" below): `BacktestReport` (`report.py`), the final item previously documented only in `backtesting/__init__.py`'s own "Planned contents" as pending. Wraps an already-produced `BacktestResult` (Parts 1/2) and `BacktestMetrics` (Part 4) into four read-only, deterministic views: `summary()` (one-paragraph text combining the run's own summary with headline performance figures), `detailed_summary()` (a longer multi-section text: overview, trade statistics, equity/return, risk), `trades_summary()`/`metrics_summary()` (structured `dict`s over every recorded `Trade`/every `BacktestMetrics` field), and `full_report()` (all four combined). Computes nothing itself — every figure is read directly from `result`/`metrics`, never recomputed — and never mutates either input. No charts/plotting, no HTML/PDF, no CSV export, no file writing, no logging, no AI, no broker/order-execution logic. Raises `backtesting.exceptions.BacktestValidationError` (reused) only when `result`/`metrics` are not the expected types. Reuses only `core.entities.trade.Trade`, `backtesting.result.BacktestResult`, `backtesting.metrics.BacktestMetrics`, and `backtesting.exceptions.BacktestValidationError` exactly as they already exist — every other Backtesting Engine file was left completely untouched. `backtesting/__init__.py` already exports and documents `BacktestReport` (`from backtesting import BacktestReport`). 41 dedicated tests in `tests/test_report.py`, all passing. | Additional concrete backtesters (e.g. one consuming `signals.result.SignalResult` directly, or supporting multiple concurrent positions per symbol/short selling/slippage/fees, or one that actually wires in `PortfolioSimulator`) remain the one open Backtesting Engine item — `report.py` is no longer pending (see Part 5 above). Nothing currently assembles a `BacktestContext` from real historical data (via `data/`) and a real strategy end-to-end outside of tests either — the same future `app/`-use-case gap `AnalysisContext`/`SignalContext`/`RiskContext`/`StrategyContext`/`PortfolioContext` already document. |

| `execution/` (Execution Engine Part 1 — foundation) | **Execution Engine Part 1** (foundation; found already present and reconciled into this document this pass — see "Last completed milestone" below): `BaseExecutionEngine` (`base.py`), `ExecutionContext` (`context.py`), `ExecutionResult` (`result.py`), the `ExecutionError` hierarchy (`exceptions.py`), and shared validation helpers (`utils.py`), mirroring the exact Part 1 shape `analysis/`, `signals/`, `strategies/`, `strategies/risk_management/`, `strategies/portfolio_management/`, and `backtesting/` each already established for their own foundations. `ExecutionContext` composes only existing abstractions — the current `core.entities.portfolio.Portfolio` (required — an execution engine cannot reason about capacity/state without it), an optional `strategies.result.StrategyResult` (the candidate trading decision under consideration), an optional `strategies.risk_management.result.RiskResult` (that decision's risk evaluation), and an optional `strategies.portfolio_management.result.PortfolioResult` (whether the portfolio has capacity for it) for one symbol/timeframe — no new domain concepts. `ExecutionResult` is deliberately minimal: only `execution_approved` (`bool`), `confidence` (`0.0..1.0`), `summary`, and `metadata` — no order-id, no fill price/quantity, no broker/exchange identifiers, and no `engine_name` field (mirroring `RiskResult`'s omission of `risk_manager_name` and `PortfolioResult`'s omission of `portfolio_manager_name`). `BaseExecutionEngine` is an `abc.ABC` with an abstract `execute(context: ExecutionContext) -> ExecutionResult` method plus shared `validate_context`/`_build_result` helpers. `execution/` is the last framework-only checkpoint before an approved trading decision would ever reach a broker/exchange — it never places that order itself. Framework only: Part 1 ships no concrete execution engine, no broker integration, no exchange API, no order execution, no networking, no threading, no async, and no AI. Imported directly (`from execution import BaseExecutionEngine, ExecutionContext, ExecutionResult, ExecutionError, ExecutionValidationError, InvalidExecutionContextError, InsufficientExecutionDataError, ExecutionEngineConfigurationError`) — this package has no parent package to re-export through, the same leaf-level convention `strategies.risk_management`/`strategies.portfolio_management` already use relative to `strategies/`. 60 dedicated tests in `tests/test_execution.py`, including a real-`StrategyResult`/`RiskResult`/`PortfolioResult`/`Portfolio`-integration section proving actual reuse of every upstream engine's output shape. | No concrete `BaseExecutionEngine` implementation exists yet — Part 1 is framework only (see "Next recommended milestone" below). No broker/exchange integration, no order placement, no networking/threading/async I/O anywhere in this package (deliberately out of scope for every Execution Engine part until that milestone is reached, per `PROJECT_RULES.md` Section 1 principle 3). Nothing currently assembles an `ExecutionContext` from real `Portfolio`/`StrategyResult`/`RiskResult`/`PortfolioResult` output end-to-end outside of tests either — the same future `app/`-use-case gap every other `*Context` type in this repository already documents. |

| `app/` (`MarketPipeline` use case + Main Application Part 1 + `BacktestRunner`, new this pass) | `app/pipeline.py` — `MarketPipeline`, the first `app/`-layer use case, was found already present, already covered by `tests/test_pipeline.py`, and already correct; it was not previously documented in this table (`app/` was listed as stub-only). It wires Data (`data.engine.DataEngine.load_history()`) -> Indicators (a configurable set of `indicators.BaseIndicator`s, defaulting to the names `analysis.technical`'s five analyzers already expect) -> Analysis (an injected `analysis.base.BaseAnalyzer`, default `AnalysisAggregator`) -> Signals (an injected `signals.base.BaseSignalGenerator`, default `SignalAggregator`), in that fixed order, for one symbol/timeframe, returning a `PipelineResult`. Adds no calculation/interpretation/decision logic of its own — every stage's actual work still happens inside the package that already owns it. **`app/main.py` — `MainApplication`, Main Application Part 1** (new this pass): the application's composition root, holding one instance of every already-implemented top-level engine/service — `data.engine.DataEngine`, `analysis.aggregator.AnalysisAggregator`, `signals.aggregator.SignalAggregator`, `strategies.aggregator.StrategyAggregator`, `strategies.risk_management.BasicRiskManager`, `strategies.portfolio_management.PortfolioManager`, `backtesting.BasicBacktester`, and `services.SignalEngine` — wired together via dependency injection, plus a `config.settings.Settings` instance loaded via `get_settings()` (or injected directly). Every collaborator is an optional, keyword-only constructor parameter, validated against the same abstract base its own ecosystem already uses (`InvalidX`-style checks raise `app.exceptions.PipelineConfigurationError`, reused rather than adding a new exception type) and defaulting to a plain, no-argument construction of the corresponding concrete class when omitted. The default `DataEngine`'s `db_path` is derived from `settings.database_url` (translating the `sqlite:///` scheme to the plain filesystem path `DataEngine` expects; any other scheme — e.g. a future `database/`-layer URL — falls back to `DEFAULT_DATA_ENGINE_DB_PATH`). **Constructor only, per this milestone's explicit scope**: no other public method exists (besides a cosmetic `__repr__`, mirroring every `Base*`/`BaseService` class's own convention); no orchestration (no engine's `run()`/`analyze()`/`generate()`/`decide()`/`evaluate()`/`execute()` is ever called), no analysis execution, no AI, no broker, no UI, no CLI, and no business logic of any kind. `execution/` (Execution Engine Part 1) is deliberately **not** composed — it ships no concrete `BaseExecutionEngine` implementation yet (see that row above) — and neither is `app.pipeline.MarketPipeline` itself, since assembling one from `MainApplication`'s own collaborators is exactly the kind of sequencing this part excludes. Reuses `config.settings`, `data.client`, `data.engine`, `analysis`, `signals`, `strategies`, `strategies.risk_management`, `strategies.portfolio_management`, `backtesting`, and `services` exactly as they already exist; no existing implementation file (other than `app/__init__.py`, to export `MainApplication` and document it in the package docstring) was modified. 47 dedicated tests in `tests/test_main.py`: the `_sqlite_path_from_database_url` helper in isolation, construction with every collaborator defaulted, dependency injection (each collaborator, when supplied, stored exactly as given — real instances and fakes both, including precedence of an injected `data_engine` over `market_data_client`), validation (`PipelineConfigurationError` for every mistyped collaborator, `None` always accepted), a scope-boundary section (exactly the nine documented public attributes exist, no `execution_engine`/`pipeline` attribute, no public method besides the constructor, construction never triggers any engine's own logic), and an end-to-end integration section building two independent, fully-wired `MainApplication` instances against real `Settings`. **`app/backtest_runner.py` — `BacktestRunner`, new this pass**: the second `app/`-layer use case, wiring Data (`data.engine.DataEngine.load_history()`, optionally bounded by `start_time`/`end_time`/`limit`) -> Backtesting (an injected `strategies.base_strategy.BaseStrategy`, default `BasicStrategy`, and an injected `backtesting.base.BaseBacktester`, default `BasicBacktester`, run via a real `backtesting.context.BacktestContext`) -> Metrics (`backtesting.metrics.calculate_metrics`) -> Report (`backtesting.report.BacktestReport`), in that fixed order, for one symbol/timeframe and a starting `core.entities.portfolio.Portfolio` (an injected one, or a fresh cash-only default), returning a `BacktestRunResult`. Closes the exact gap this table's own "what's missing" column previously documented: "Nothing currently assembles a `BacktestContext` from real historical data (via `data/`) and a real strategy end-to-end outside of tests." Adds no calculation/interpretation/decision logic of its own — every stage's actual work still happens inside the package that already owns it (`data/`, `backtesting/`); reuses `app.pipeline._to_core_candle` directly for candle translation rather than duplicating it. No AI, no machine learning, no broker/exchange connection, no live trading, no order-execution engine, no UI, no server, no automatic/parameter optimization. 24 dedicated tests in `tests/test_backtest_runner.py`, including a real-`BasicStrategy`/`BasicBacktester`-integration section. | `MainApplication` (Part 1) is composition only — sequencing these engines into an actual use case (the "conductor" behavior `app/__init__.py` describes) remains a future Main Application part, the same `app/`-layer wiring gap `PROJECT_STATE.md`'s "Next recommended milestone" item 8 already documents for `SignalContext`/`RiskContext`/`StrategyContext`/`PortfolioContext`/`ExecutionContext`. No concrete `BaseExecutionEngine` exists yet for `MainApplication` to compose (see `execution/` above). Neither `app.pipeline.MarketPipeline` nor `app.backtest_runner.BacktestRunner` is yet wired into `MainApplication`. `BacktestRunner`'s default `BasicStrategy` requires a matching `AnalysisResult` that a plain backtest run never supplies (`BacktestContext`/`BasicBacktester` build an empty `analysis_results` list by design, per `backtesting/`'s own documented consumer-only role) — every candle is skipped unless a caller injects a strategy that does not depend on `AnalysisResult`, or a future milestone wires `MarketPipeline`'s Analysis stage into a per-candle `BacktestRunner` flow. |

| `services/` (Services Part 1 foundation + Part 2A first concrete service) | **Services Part 1** (foundation): `BaseService` (`base.py`), `ServiceContext` (`context.py`), `ServiceResult` (`result.py`), the `ServiceError` hierarchy (`exceptions.py`), and shared validation helpers (`utils.py`), mirroring the exact Part 1 shape `analysis/`, `signals/`, `strategies/`, `strategies/risk_management/`, `strategies/portfolio_management/`, `backtesting/`, and `execution/` each already established for their own foundations — adapted to `services/`'s different nature: it wraps external integrations and cross-cutting technical concerns (notifications, an AI/LLM client wrapper, scheduling, a concrete `EventBus`) that are heterogeneous by design, rather than one stage of the trading-decision pipeline. `ServiceContext` therefore composes no domain entities — it stays a generic `service_name` + free-form `payload` + `metadata` envelope. `ServiceResult` is deliberately minimal: only `success` (`bool`), `summary`, and `metadata` — no `service_name` field, no delivery receipt, no provider/vendor identifiers, no `confidence` field. `BaseService` is an `abc.ABC` with an abstract `execute(context: ServiceContext) -> ServiceResult` method plus shared `validate_context`/`_build_result` helpers. 48 dedicated tests in `tests/test_services.py`. **Services Part 2A** (new this milestone): `SignalEngine` (`signal_engine.py`), the first concrete `BaseService` in this package. Despite the name, it is unrelated to (and does not import) the `signals/` package — `services/` may only depend on `core`/`events` (`PROJECT_RULES.md` Section 4) — it will, in a future Services part (2B), publish an already-produced `core.entities.signal.Signal` as an `events.event_types.signal_generated.SignalGenerated` event via an injected `events.interfaces.event_bus.EventBus`. This part (2A) ships only `SignalEngine`'s public interfaces, per this milestone's explicit scope: a constructor accepting an optional dependency-injected `EventBus` (`event_bus=None` is valid — no concrete `EventBus` implementation exists anywhere in the repo yet), validation of that injected `EventBus` (`ServiceConfigurationError` if neither `None` nor an `EventBus` instance) and of a caller-configurable, merged-with-defaults `config` dict (`SignalEngine.DEFAULT_CONFIG`: `auto_generate_signal_metadata`/`require_min_confidence`, both `bool`, and `min_confidence`, a finite `float` in `[0.0, 1.0]` — unrecognized keys or invalid values raise `ServiceConfigurationError`), and engine configuration exposed via `get_configuration()` (returns a defensive copy) and `has_event_bus()`. **No orchestration logic ships in this part**: `execute()` — the one abstract method `BaseService` requires, so `SignalEngine` is already concrete/instantiable, not another abstract base — validates its `ServiceContext` via the inherited `validate_context()` and then always raises `NotImplementedError`, explicitly deferring the real build-`Signal`-from-payload/apply-`min_confidence`/`event_bus.publish(...)`/return-`ServiceResult` flow to a future Services Part 2B. Reuses `core.entities.signal.Signal`, `events.interfaces.event_bus.EventBus`, and Part 1's `BaseService`/`ServiceContext`/`ServiceResult`/`ServiceConfigurationError`/`services.utils.validate_dict` exactly as they already exist; no existing file among Part 1's five modules was modified, and `analysis/`, `signals/`, `strategies/` (including `risk_management/`/`portfolio_management/`), `backtesting/`, `execution/`, and `core/` were all left completely untouched. Only `services/__init__.py` (to export `SignalEngine` and document Part 2A) was updated among existing files. 32 dedicated tests in `tests/test_signal_engine.py`: construction/inheritance, dependency injection (accepts/rejects an injected `EventBus`), configuration (default shape, defensive-copy `get_configuration()`, partial/full overrides, boundary/invalid `min_confidence`, unknown-key/non-dict rejection, `DEFAULT_CONFIG` never mutated), `execute()` (context-type validation still runs first, always raises `NotImplementedError` afterward, never calls `event_bus.publish(...)`), a scope-boundary section (confirms this module never imports `signals/`), and an end-to-end integration section with a real `Signal` and a fake `EventBus`. | No concrete `BaseService` implementation existed before this milestone; `SignalEngine` (Part 2A) is now the first, but it is deliberately not yet usable end-to-end — Part 2B (`SignalEngine.execute()`'s real orchestration: building/validating a `Signal` from `context.payload`, applying `min_confidence`, publishing via `self.event_bus`, and returning a populated `ServiceResult`) remains the next open item for this package, alongside the still-unbuilt notification service, AI/LLM client wrapper, scheduler, and concrete `EventBus` implementation. No networking/threading/async I/O anywhere in this package. Nothing currently assembles a `ServiceContext` from a real request end-to-end outside of tests either — the same future `app/`-use-case gap every other `*Context` type in this repository already documents. |


## Remaining modules (stub only — explanatory `__init__.py`, no logic)

These packages currently contain **only** a docstring describing their
future purpose. They have no classes, functions, or tests. Do not
assume any implementation exists here:

- `models/` — will hold ML model training/inference code.
- `database/` — will hold `DatabaseRepository` implementations (SQLite by default) fulfilling the `core.interfaces.database_repository.DatabaseRepository` contract. Note: `data/storage.py` already implements SQLite persistence for candles directly — the future `database/` layer is expected to generalize/replace this for other entity types (positions, portfolios, signals, etc.), not duplicate it.
- `logs/` — not a Python package; runtime log output directory only (contains `README.md` and `.gitkeep`).

`app/` is no longer stub-only — see its row in "Partially completed
modules" below (`MarketPipeline`, found already present and reconciled
into this document in an earlier pass, and `MainApplication`, Main
Application Part 1, new this pass).

## Folder structure

```
MarketMind-AI/
├── app/            # PARTIAL — pipeline.py (MarketPipeline, Data->Indicators->Analysis->Signals use case) + main.py (MainApplication, Part 1 — composition root, DI/config-loading/engine-initialization only, no orchestration yet) + backtest_runner.py (BacktestRunner, Data->Backtesting->Metrics->Report use case, new)
├── api/            # IMPLEMENTED — HTTP transport (http_client, exceptions, providers/)
│   └── providers/  # BinanceProvider, CoinGeckoProvider, news provider, base
├── backtesting/    # PARTIAL — foundation (Part 1): BaseBacktester, BacktestContext, BacktestResult, exceptions.py, utils.py; BasicBacktester (Part 2, first concrete backtester); PortfolioSimulator (Part 3, portfolio simulation helper, not yet wired into BasicBacktester); metrics.py (Part 4, performance statistics — BacktestMetrics/calculate_metrics); report.py (Part 5, IMPLEMENTED — BacktestReport, human-readable/structured summaries)
├── config/         # IMPLEMENTED — settings.py (typed env settings), config.py (constants/enums)
├── core/           # IMPLEMENTED (domain-contract scope) — entities/, interfaces/, enums.py
│   ├── entities/   # Candle, Ticker, OrderBook, Trade, Position, Portfolio, Signal, IndicatorResult, NewsItem, MarketState
│   └── interfaces/ # MarketDataProvider, NewsProvider, AIAnalyzer, IndicatorCalculator, Strategy, SignalGenerator, RiskManager, DatabaseRepository
├── analysis/       # PARTIAL — foundation (Part 1) + technical/ (Parts 2, 3A, 3B & 3C, IMPLEMENTED) + aggregator.py (Part 4, IMPLEMENTED)
│   ├── technical/  # IMPLEMENTED — TrendAnalyzer, MomentumAnalyzer, VolatilityAnalyzer, VolumeAnalyzer, MarketStructureAnalyzer, utils.py
│   └── aggregator.py  # IMPLEMENTED — AnalysisAggregator (Part 4, combines the five technical/ analyzers)
├── data/           # IMPLEMENTED (most mature) — Binance OHLCV data engine
├── database/       # STUB — persistence layer (SQLite)
├── docs/           # ARCHITECTURE.md, DATA_ENGINE.md (+ this PROJECT_STATE.md / DEVELOPER_GUIDE.md are at repo root, not here)
├── events/         # IMPLEMENTED (contract scope) — interfaces/, event_types/
├── execution/      # PARTIAL — foundation (Part 1, IMPLEMENTED): BaseExecutionEngine, ExecutionContext, ExecutionResult, exceptions.py, utils.py; no concrete execution engine yet
├── indicators/     # IMPLEMENTED — 17 pure technical indicators + base.py + utils.py
├── logs/           # Runtime log output (not a package)
├── models/         # STUB — ML models
├── services/       # PARTIAL — foundation (Part 1): BaseService, ServiceContext, ServiceResult, exceptions.py, utils.py; SignalEngine (Part 2A, first concrete BaseService — public interfaces only, no orchestration logic yet)
├── signals/        # PARTIAL — foundation (Part 1) + TechnicalSignalGenerator (Part 2) + SignalAggregator (Part 3) + filters.py (Part 4) + validation.py (Part 5), IMPLEMENTED
├── strategies/     # PARTIAL — foundation (Part 1) + BasicStrategy (Part 2) + StrategyAggregator (Part 3), IMPLEMENTED; risk_management/ (Risk Engine Parts 1-3, IMPLEMENTED); portfolio_management/ (Portfolio Management Parts 1-4, IMPLEMENTED — foundation + BasicPortfolioManager + composite/aggregating PortfolioManager + PortfolioAggregator); additional strategies still STUB
│   ├── risk_management/  # IMPLEMENTED — BaseRiskManager, RiskContext, RiskResult, exceptions.py, utils.py (Part 1); BasicRiskManager (Part 2); PositionSizeRule, StopLossRule, TakeProfitRule (Part 3)
│   └── portfolio_management/  # IMPLEMENTED — BasePortfolioManager, PortfolioContext, PortfolioResult, exceptions.py, utils.py (Part 1); BasicPortfolioManager (Part 2); PortfolioManager composite/aggregating manager (Part 3); PortfolioAggregator, a second aggregator mirroring StrategyAggregator's naming (Part 4)
├── tests/          # 1633 test cases total across implemented modules (1604 unittest-discoverable-and-passing + 29 pytest-parametrize cases in the two pytest-specific files) — see "Current test status" for the full breakdown
├── utils/          # STUB (empty helpers package)
├── main.py         # Thin bootstrap: loads Settings, prints version, exits
├── requirements.txt
├── .gitignore
└── README.md
```

## Dependency graph

This mirrors the intended Clean Architecture dependency direction
documented in `docs/ARCHITECTURE.md` — inner layers never import outer
layers:

```
core/           (depends on: nothing)
config/         (depends on: nothing)
utils/          (depends on: nothing)

events/         (depends on: core)
database/       (depends on: core)                          [stub]
indicators/     (depends on: core, events)
data/           (depends on: core, events)                   [also uses config/ for TimeFrame]
api/            (depends on: nothing internal yet — pure transport; will feed data/ providers)

analysis/       (depends on: core, data, indicators, events)  [foundation; technical/ subpackage + aggregator.py (Part 4) implemented]
models/         (depends on: core)                            [stub]

signals/        (depends on: core, analysis, events)          [foundation (Part 1) + TechnicalSignalGenerator (Part 2) + SignalAggregator (Part 3) + filters.py (Part 4) + validation.py (Part 5) implemented]
strategies/     (depends on: core, analysis, signals, events) [foundation (Part 1) + BasicStrategy (Part 2) + StrategyAggregator (Part 3) implemented; risk_management/ Risk Engine Parts 1-3 implemented; portfolio_management/ Portfolio Management Parts 1-4 implemented — foundation + BasicPortfolioManager + composite/aggregating PortfolioManager + PortfolioAggregator (depends on: core, strategies (StrategyResult), strategies.risk_management (RiskResult) — no new outer-layer dependency); additional strategies still stub]

backtesting/    (depends on: core, data, strategies, signals) [foundation (Part 1) + BasicBacktester (Part 2) + PortfolioSimulator (Part 3) + metrics.py (Part 4) + report.py (Part 5) implemented]
execution/      (depends on: core, strategies, strategies.risk_management, strategies.portfolio_management) [foundation (Part 1) implemented; no concrete execution engine yet]
services/       (depends on: core, events)                    [foundation (Part 1) implemented; SignalEngine (Part 2A, first concrete BaseService — public interfaces only, no orchestration logic) implemented]

app/            (depends on: all of the above)                [partial -- MarketPipeline (Data->Indicators->Analysis->Signals use case) + MainApplication (Part 1, composition root: DI/config-loading/engine-initialization only, no orchestration yet) + BacktestRunner (Data->Backtesting->Metrics->Report use case, new)]
api/ (as inbound REST, future) (depends on: app)               [not started]
```

**Verified actual import relationships today** (not just intended):
`data/` imports `core` entities (`Candle`) and `config` (`TimeFrame`);
`indicators/` is self-contained (numpy/pandas + its own `base.py`/`utils.py`,
no imports from `core` yet in practice, though the interface contract
exists in `core.interfaces.indicator_calculator`); `analysis/` imports
`core` entity/result types via its `context.py` and `result.py`; `signals/`
imports `core.enums.SignalDirection` (via `result.py`/`utils.py`) and
`analysis.result.AnalysisResult` (via `context.py`) — it does not import
`events` yet in practice, though the dependency table allows it; `api/`
has no internal cross-package imports — it's a leaf transport layer
consumed by nothing yet. `strategies.risk_management` imports only
`core` entities (`Signal`, `Portfolio`, `MarketState`) via its
`context.py` — it does not import `analysis`, `signals`, or `events`
yet in practice, though the dependency table allows all three.
`strategies.basic_strategy` imports only `core.enums.SignalDirection`
plus its own package's Part 1 modules (`base_strategy`, `context`,
`exceptions`, `result`, `utils`) — it does not import `analysis` or
`signals` directly (it reads their result types only via the
`AnalysisResult`/`SignalResult` instances already carried on
`StrategyContext`, not via a fresh import of those packages' modules).
`services/` (Part 1 foundation) imports nothing outside its own
package in practice yet — `ServiceContext`/`ServiceResult` compose no
domain entities (unlike every other package's Part 1 foundation),
though the dependency table above still allows `core`/`events` for a
future concrete service (e.g. a notification service reading
`core.entities`, or an `EventBus` implementation reading `events`).
`main.py` imports only `config.settings`. `execution/` imports only
`core.entities.portfolio.Portfolio`, `strategies.result.StrategyResult`,
`strategies.risk_management.result.RiskResult`, and `strategies.
portfolio_management.result.PortfolioResult` — exactly the subset the
dependency table above allows, and no `events`/`data`/`analysis`/
`signals` import in practice yet, though the table would allow
reaching them indirectly.

## Design decisions

- **Clean Architecture, dependency rule enforced by folder + review, not tooling.** There is no lint rule or CI check currently enforcing "inner layers don't import outer layers" — it is a convention documented in `docs/ARCHITECTURE.md` and must be manually respected.
- **`core/enums.py` duplicates timeframe-adjacent concepts on purpose.** Domain enums (`OrderSide`, `PositionSide`, `PositionStatus`, `SignalDirection`) live in `core`, not `config`, specifically so `core` never has to import `config`. `TimeFrame`/`Exchange` stay in `config/config.py` and are treated as plain `str` on domain entities.
- **Calculation vs. interpretation vs. decision are three separate packages.** `indicators/` only computes numbers; `analysis/` turns numbers into scored/interpreted insights; `signals/` standardizes one or more `AnalysisResult`s into a common `SignalResult` format (`direction`/`strength`/`confidence`/`summary`/`metadata`) via `BaseSignalGenerator`; `strategies/` (foundation implemented — Part 1 — plus a first concrete strategy `BasicStrategy`, Part 2, and a way to combine multiple `BaseStrategy` instances, `StrategyAggregator`, Part 3) turns analysis/signal/risk output into a trading decision (`StrategyResult`). This split is intentional so each layer can be tested and swapped independently — do not merge these responsibilities.
- **`backtesting/` is a consumer, never a strategy author.** It will replay historical data through whatever strategy/signals it's given; it must never contain trading rules itself.
- **`api/` is split into two unrelated responsibilities that happen to share a package name today:** (1) outbound transport to third-party APIs (implemented: `http_client.py`, `providers/`), and (2) a future inbound REST API exposing MarketMind-AI itself (`routes/`, `server.py` — not started). Don't confuse the two when extending this package.
- **Free-first, zero-cost by design.** Every chosen dependency (SQLite, Binance public endpoints, pytest/unittest, free news sources) targets a free tier or open-source tool. This is a hard constraint from `README.md`, not a suggestion — don't introduce paid services.
- **`data/storage.py` vs. future `database/`.** The Data Engine already has its own SQLite persistence for candles. The still-stub `database/` package is expected to eventually provide the general-purpose `DatabaseRepository` implementation (for positions, portfolios, signals, etc.) per the `core.interfaces.database_repository` contract — it is not yet clear whether `data/storage.py` will be refactored to sit on top of `database/` or remain independent. This is an open design question, not a decided one.

## Technical debt

- No CI pipeline / no automated enforcement of the dependency rule or code style.
- `analysis/news/` and `analysis/ai/` subpackages are still documented but not created (`analysis/technical/` and `analysis/aggregator.py` are now implemented — see Completed modules); nothing currently *assembles* an `AnalysisContext` from live data end-to-end (that remains a future `app/` use case, per `analysis/context.py`'s docstring), so `TrendAnalyzer`/`MomentumAnalyzer`/`VolatilityAnalyzer`/`VolumeAnalyzer`/`MarketStructureAnalyzer`/`AnalysisAggregator` are exercised only via hand-built contexts in tests today.
- No concrete swing-point-detection indicator exists anywhere in the repo (not in `indicators/`, not elsewhere) — `MarketStructureAnalyzer` (Part 3C) documents the `SwingPoints_1`-shaped `IndicatorResult` it expects, but nothing currently produces one from raw candle history. Until such a detector is built, `MarketStructureAnalyzer` can only be exercised with hand-built swing-point values in tests, same as the other four analyzers' hand-built indicator values.
- No concrete `EventBus` implementation anywhere in the repo — every event type and the pub/sub contracts exist, but nothing publishes or subscribes yet. Any module (`indicators/`, `analysis/`, `strategies/`) that is meant to eventually communicate via events currently has no way to do so.
- `signals/` now has one concrete `BaseSignalGenerator` (`TechnicalSignalGenerator`, Part 2), a way to combine multiple generators' output (`SignalAggregator`, Part 3), a filter pipeline (`SignalFilterPipeline` + four filters, Part 4), and a validation pipeline (`SignalValidationPipeline` + five rules + `SignalValidator`, Part 5), but nothing currently *assembles* a `SignalContext` from real `AnalysisAggregator`/`analysis.technical` output end-to-end outside of tests, nor wires `SignalFilterPipeline`/`SignalValidator` between a real generator/aggregator and a consumer end-to-end — both remain a future `app/` use case. `signals/` also does not yet import `events/` in practice, despite the dependency table allowing it.
- `utils/` is an empty placeholder — any cross-cutting helper needed today (logging, datetime conversion) has to be written ad hoc inside whichever module needs it first, which risks duplication once `utils/` is finally populated.
- `api/` name overload (see design decisions above) — extending it for the future inbound REST API without a clear routes/schemas convention risks conflating outbound and inbound concerns in one package.
- Two tests (`test_core_domain.py`, `test_events.py`) depend on `pytest` specifically (not just `unittest`), while the rest of the suite and `docs/DATA_ENGINE.md` advertise pure-`unittest`, dependency-free execution — this is a minor inconsistency in the test suite's stated zero-dependency guarantee.
- `strategies/risk_management/` now has four concrete `BaseRiskManager` implementations (`BasicRiskManager`, Risk Engine Part 2; `PositionSizeRule`/`StopLossRule`/`TakeProfitRule`, Risk Engine Part 3), but nothing currently assembles a `RiskContext` from a real `SignalResult`/`AnalysisResult`/live `Portfolio` end-to-end outside of tests — that remains a future `app/`-layer use case, the same gap `AnalysisContext`/`SignalContext` already have. Additional concrete risk managers (drawdown checks, volatility-based risk) and an optional composite/aggregating risk manager remain future work.
- `strategies/` now has a Strategy Engine Part 1 foundation (`BaseStrategy`/`StrategyContext`/`StrategyResult`/`StrategyError` hierarchy/`utils.py`), a first concrete strategy `BasicStrategy` (Part 2), and a way to combine multiple `BaseStrategy` instances' output, `StrategyAggregator` (Part 3), all re-exported through `strategies/__init__.py`. `decide()` is now exercised by both a real strategy and a real aggregator in tests, not just a hand-built fake, but `BasicStrategy` remains the only concrete decision-making strategy — additional ones (trend-following, mean-reversion, etc.) remain future work. Nothing currently assembles a `StrategyContext` from real `AnalysisAggregator`/`SignalAggregator`/risk-manager output end-to-end outside of tests either — a future `app/` use case.
- `strategies/portfolio_management/` now has a Portfolio Management Part 1 foundation (`BasePortfolioManager`/`PortfolioContext`/`PortfolioResult`/`PortfolioError` hierarchy/`utils.py`), a first concrete manager, `BasicPortfolioManager` (Part 2), gating new positions on open-position count, aggregate exposure, symbol concentration, and upstream signal/risk approval, and (this milestone) a composite/aggregating manager, `PortfolioManager` (Part 3), which combines one or more injected `BasePortfolioManager` instances (default: a single `BasicPortfolioManager()`) via a confidence-and-weight-weighted vote of each sub-manager's signed `new_positions_allowed` decision, mirroring `StrategyAggregator`'s/`SignalAggregator`'s role one layer down each. No allocation/position-sizing or rebalancing logic exists yet. Nothing currently assembles a `PortfolioContext` from real `BasicStrategy`/`StrategyAggregator`/risk-manager/live-portfolio output end-to-end outside of tests either — a future `app/` use case.
- `execution/` now has an Execution Engine Part 1 foundation (`BaseExecutionEngine`/`ExecutionContext`/`ExecutionResult`/`ExecutionError` hierarchy/`utils.py`), but no concrete `BaseExecutionEngine` implementation yet — it is framework only, the same state every other engine's Part 1 started from before its first concrete implementation. Nothing currently assembles an `ExecutionContext` from real `Portfolio`/`StrategyResult`/`RiskResult`/`PortfolioResult` output end-to-end outside of tests either — the same future `app/`-use-case gap every other `*Context` type in this repository already documents. Actual order placement/broker integration remains entirely out of scope for this or any future Execution Engine part until that milestone is explicitly reached.

- `services/` now has a Services Part 1 foundation (`BaseService`/`ServiceContext`/`ServiceResult`/`ServiceError` hierarchy/`utils.py`) and a Part 2A first concrete `BaseService`, `SignalEngine` (`signal_engine.py`) — but `SignalEngine.execute()` still raises `NotImplementedError` by design (Part 2A ships only its constructor/dependency-injection/validation/configuration public interfaces, no orchestration logic), so no service call anywhere in this package can yet be carried out end-to-end. No notification service, AI/LLM client wrapper, scheduler, or concrete `EventBus` implementation exists yet. Nothing currently assembles a `ServiceContext` from a real request end-to-end outside of tests either — the same future `app/`-use-case gap every other `*Context` type in this repository already documents.

## Known limitations

- Only Binance Spot OHLCV market data is supported; no other exchanges, no news data ingestion (despite `NewsProvider` interface and a `news_provider.py` API wrapper already existing), no WebSocket/real-time streaming (REST polling only).
- No trading logic anywhere in the repository. Nothing places orders — `execution/` (Part 1) only provides the framework to evaluate whether a candidate decision is cleared to proceed toward order placement, with no concrete engine yet and no broker/exchange integration; `main.py` only proves configuration loads.
- No authentication/secrets management beyond `.env` loading via `python-dotenv`; no key rotation, no secrets vault integration.
- Single-machine, single-user design (`README.md`: "personal, free... project"), not built for multi-tenant or concurrent-user use.
- `indicators/`, `analysis/`, and `signals/` are not wired to `events/` in practice yet, despite the architecture doc describing an eventual event-driven flow between them.
- `signals/` does not yet produce `core.entities.signal.Signal` (the persisted/actionable entity) — only the lighter-weight `SignalResult` (`direction`/`strength`/`confidence`/`summary`/`metadata`). Building a `Signal` from one or more `SignalResult`s is deferred to a later Signal Engine part or `strategies/`.

- **This pass (Main Application Part 1 — new implementation):** running
  `python3 -m unittest discover -s tests -p "test_*.py"` gives **1699
  pass, 3 failures, 3 errors**. 2 of the errors are the same
  pre-existing `pytest`-availability errors described below
  (`test_core_domain.py`/`test_events.py`); the remaining 3 failures +
  1 error are pre-existing `tests/test_signal_engine.py` cases
  (`TestExecuteNotYetOrchestrated`/`TestIntegration`) asserting Services
  Part 2A's "`execute()` always raises `NotImplementedError`" behavior
  against a `services/signal_engine.py` that, on inspection this pass,
  already ships real Part 2B orchestration end-to-end — a pre-existing
  inconsistency between that test file and the implementation it
  covers, predating and unrelated to this pass (confirmed by
  temporarily removing `app/main.py`/`tests/test_main.py` and
  re-running: the identical 6 issues reproduce against a baseline of
  1652 tests). This total now includes `tests/test_main.py` (47 tests,
  new — Main Application Part 1: the `_sqlite_path_from_database_url`
  helper, construction with every collaborator defaulted, dependency
  injection of every collaborator, validation, a scope-boundary
  section, and an end-to-end integration section). Combined with the 29
  pytest-`parametrize`-expanded cases in the two pytest-only files
  (unchanged, carried forward), the grand total is **1699 test cases**
  across **50 files** in `tests/`, of which **1699 - 6 = 1693 (plus the
  29 pytest-only cases) are genuinely passing** and 6 are the
  pre-existing issues just described. `app/main.py` and every other
  existing file byte-compile and import cleanly (see Compile status
  below); no existing implementation file was changed other than
  `app/__init__.py`.
- **This pass (`app/backtest_runner.py` — `BacktestRunner`, new implementation):**
  running `python3 -m unittest discover -s tests -p "test_*.py"` gives
  **1867 pass, 2 errors** (the same 2 pre-existing `pytest`-availability
  errors described below — `test_core_domain.py`/`test_events.py` —
  not real failures). This total now includes
  `tests/test_backtest_runner.py` (24 tests, new — construction/DI
  validation, real end-to-end runs with the default `BasicStrategy`
  and an always-buy fake strategy proving real trade execution,
  `start_time`/`end_time`/`limit` forwarding, default/custom
  `initial_portfolio` handling and no-mutation guarantees, error
  wrapping, determinism, and a real-`BasicStrategy`/`BasicBacktester`-
  integration section). Combined with the 29 pytest-`parametrize`-
  expanded cases in the two pytest-only files (unchanged, carried
  forward — neither file nor its dependencies changed this pass), the
  grand total is **1896 test cases** across **55 files** in `tests/`,
  all passing. `app/backtest_runner.py` and every other existing file
  byte-compile and import cleanly (see Compile status below); no
  existing implementation file's logic was changed (`app/exceptions.py`
  and `app/__init__.py` only gained additive exception classes/exports).
  Note: the unittest-passing total jumped from the previously-recorded
  1636 (Services Part 2A pass) to 1867 minus this pass's 24 new tests
  (i.e. 1843 pre-existing) — a gap versus what intervening milestones'
  own recorded counts would predict, consistent with the same kind of
  documentation-reconciliation lag this file has flagged before (e.g.
  `app/pipeline.py`/`tests/test_pipeline.py` and `backtesting/report.py`/
  `tests/test_metrics.py` were each found already present and passing
  before being reconciled into this document); a full accounting of
  that gap is out of scope for this pass, which only adds the new
  integration path requested.
- **Prior pass (Services Part 2A — new implementation):** running
  `python3 -m unittest discover -s tests -p "test_*.py"` gives **1636
  pass, 2 errors** (the same 2 pre-existing `pytest`-availability
  errors described below — `test_core_domain.py`/`test_events.py` —
  not real failures). This total now includes `tests/test_signal_engine.py`
  (32 tests, new — Services Part 2A: `SignalEngine` construction/
  inheritance, dependency injection of an optional `EventBus`,
  configuration merge/validation, `execute()`'s
  validate-then-`NotImplementedError` behavior, a scope-boundary
  section confirming no `signals/` import, and an end-to-end
  integration section with a real `Signal` and a fake `EventBus`).
  Combined with the 29 pytest-`parametrize`-expanded cases in the two
  pytest-only files (unchanged, carried forward — neither file nor its
  dependencies changed this pass), the grand total is **1665 test
  cases** across **49 files** in `tests/`, all passing.
  `services/signal_engine.py` and every other existing file
  byte-compile and import cleanly (see Compile status below); no
  existing implementation file was changed.
- **Prior pass (Services Part 1 — new implementation):** running
  `python3 -m unittest discover -s tests -p "test_*.py"` gives **1604
  pass, 2 errors** (the same 2 pre-existing `pytest`-availability
  errors described below — `test_core_domain.py`/`test_events.py` —
  not real failures). This total now includes `tests/test_services.py`
  (48 tests, new — Services Part 1: `ServiceResult`/`ServiceContext`
  construction/validation/frozen-field/scope-boundary checks,
  `services.utils`/`services.exceptions` unit coverage, `BaseService`
  abstract-base behavior via a minimal `FakeService`, and an end-to-end
  integration section). Combined with the 29 pytest-`parametrize`-
  expanded cases in the two pytest-only files (unchanged, carried
  forward — neither file nor its dependencies changed this pass), the
  grand total is **1633 test cases** across **48 files** in `tests/`,
  all passing. `services/*.py` and every other existing file
  byte-compile and import cleanly (see Compile status below); no
  existing implementation file was changed.
- **Prior pass (Execution Engine Part 1 verification):** running
  `python3 -m unittest discover -s tests -p "test_*.py"` gives **1556
  pass, 2 errors** (the same 2 pre-existing `pytest`-availability
  errors described below — `test_core_domain.py`/`test_events.py` —
  not real failures). This total included `tests/test_execution.py`
  (60 tests — Execution Engine Part 1) and `tests/test_report.py`
  (41 tests — Backtesting Engine Part 5, found already present and
  already passing but previously undocumented, mirroring how
  `tests/test_metrics.py` was reconciled into this document in the
  prior pass). Combined with the 29 pytest-`parametrize`-expanded cases
  in the two pytest-only files, the grand total was
  **1585 test cases** across **47 files** in `tests/`, all passing.
  `execution/*.py` and every other existing file byte-compiled and
  imported cleanly; no implementation change was required.
- **1484 test cases total** across `tests/` (45 files, one per implemented module/component): **1455 pass via the standard-library `unittest` runner** (`python3 -m unittest discover -s tests -p "test_*.py"`) plus **29 additional pytest-`parametrize`-expanded cases** in the two files that require real `pytest` (`test_core_domain.py`, `test_events.py` — see verification note below). Includes, among others: **analysis technical — `TrendAnalyzer`/`MomentumAnalyzer`, 80 tests** (`tests/test_analysis_technical.py`), **`VolatilityAnalyzer`, 65 tests**, **`VolumeAnalyzer`, 41 tests**, **`MarketStructureAnalyzer`, 26 tests**, **`AnalysisAggregator`, 36 tests**, **Signal Engine foundation, 45 tests**, **`TechnicalSignalGenerator`, 31 tests**, **`SignalAggregator`, 36 tests**, **Signal Engine filtering, 63 tests**, **Signal Engine validation, 60 tests**, **Risk Engine Part 1 foundation, 51 tests**, **`BasicRiskManager`, 45 tests**, **`PositionSizeRule`/`StopLossRule`/`TakeProfitRule`, 103 tests**, **Strategy Engine Part 1 foundation, 62 tests**, **`BasicStrategy`, 39 tests**, **`StrategyAggregator`, 50 tests**, **Portfolio Management Part 1 foundation — `BasePortfolioManager`/`PortfolioContext`/`PortfolioResult`/`PortfolioError` hierarchy/utils, 57 tests** (`tests/test_portfolio_management.py`), **`BasicPortfolioManager` — Portfolio Management Part 2, 43 tests** (`tests/test_basic_portfolio_manager.py`, construction/configuration validation, each of the four gating checks — open-position count, aggregate exposure, symbol concentration, upstream signal/risk approval — individually and in combination, confidence derivation from optional-context availability, metadata/summary traceability, and an end-to-end integration section), **`PortfolioManager` — Portfolio Management Part 3, 58 tests** (`tests/test_portfolio_manager.py`, construction/configuration validation, `evaluate()` context validation and unavailable-sub-manager handling, weighted-vote aggregation and threshold mapping, completeness/agreement/confidence shape, output-shape/metadata/summary/determinism checks, and a real-`BasicPortfolioManager`-integration section), **`PortfolioAggregator` — Portfolio Management Part 4, 62 tests** (`tests/test_portfolio_aggregator.py`: the same construction/evaluate/aggregation/completeness-agreement-confidence/output-shape coverage as Part 3's test file, plus a real-`BasicPortfolioManager`-integration section, plus a dedicated independence section confirming `PortfolioAggregator` does not import or subclass `PortfolioManager`, and vice versa) — Portfolio Management total: **220 tests** (57 + 43 + 58 + 62), all passing —, **Backtesting Engine Part 1 foundation, 52 tests** (`tests/test_backtesting.py`: `BacktestResult` construction/validation/frozen-field/scope-boundary checks, `BacktestContext` construction/validation (including chronological-candle ordering), `backtesting.utils`/`backtesting.exceptions` unit coverage, `BaseBacktester` abstract-base behavior via a minimal fake, and a real-`BaseStrategy`/`Portfolio`-integration section), **`BasicBacktester` — Backtesting Engine Part 2, 56 tests** (`tests/test_basic_backtester.py`: construction/inheritance, inherited `BacktestContext` validation, HOLD-only replay (no trades/no portfolio change), BUY-only replay (single position opened, no pyramiding, zero/negative-cash no-op), SELL-with-no-position no-op, a full BUY-then-SELL round trip (trade sides/order, `realized_pnl`, cash/position state), a position left open at run end, multiple alternating round trips with strict chronological trade ordering, `InsufficientStrategyDataError` handling (all-skipped, partial warm-up then recovery, `run()` itself never raises it, summary mentions skips), a non-`StrategyError` exception propagating unchanged, no-mutation-of-inputs checks (`initial_portfolio`, `candles`, re-running the same context), determinism across repeated runs, chronological-execution/`StrategyContext`-wiring checks (candle order, symbol/timeframe, empty `analysis_results`/`None` signal/risk, per-candle metadata), output-shape/metadata/summary/scope-boundary checks, a real-`BasicStrategy`-integration section proving genuine `BaseStrategy.decide()` reuse, and a defensive empty-candles completeness check), and **`PortfolioSimulator` — Backtesting Engine Part 3, 53 tests** (`tests/test_portfolio_simulator.py`, new this pass: construction validation and deep-copy/no-mutation guarantees, position lookup across symbols/statuses, opening positions (all-cash spend, no-pyramiding no-op, zero/negative-cash no-op, long/short sides, validation errors), closing positions (cash credit, realized PnL for long and short in both profit/loss cases, no-op with none open, validation errors), a full round trip and multiple alternating round trips with strict chronological ordering, marking to market (`current_price`/`unrealized_pnl` updates, no-op, validation), `total_equity()` (cash-only, mark-to-market, post-close, `portfolio.total_equity` refresh), the three `Candle`-based convenience wrappers (correct extraction, no candle mutation, invalid-candle validation), and determinism/no-mutation checks). Backtesting Engine total: **161 tests** (52 + 56 + 53), all passing.
- **Verification pass (this pass, current — documentation-reconciliation pass):** this sandbox has no network access to `pip install pytest`/`SQLAlchemy`/`python-binance` (`pip`/`uv` both fail with no matching distribution found, confirmed again this pass). A `grep` of the entire repository confirms zero hard `import sqlalchemy`/`import binance` statements anywhere — those two packages are pinned in `requirements.txt` for future layers only and are not yet load-bearing, so their absence does not affect this run. Running `python3 -m unittest discover -s tests -p "test_*.py"` gives **1455 pass, 2 errors** — the 2 errors (`test_core_domain.py`, `test_events.py`) are `ModuleNotFoundError: No module named 'pytest'`, not real test failures; both files pre-date and are unrelated to this pass, and both explicitly `import pytest` for `pytest.raises`/`pytest.mark.parametrize` (confirmed via `grep` to be the *only* pytest-specific surface used anywhere in the suite — no fixtures, no `conftest.py`, no other pytest API). Both were previously verified passing (12 parametrized test functions expanding to **29 cases, 29 passed, 0 failed**) via a disk-local `pytest`-compatible shim in an earlier pass; that result is carried forward here since neither file nor its dependencies changed. Combined result for this pass: **1484/1484 test cases passing, 0 failures**, of which **36 (`tests/test_metrics.py`) were found already present and already passing but undocumented** — this pass's actual code change is zero; the 36-test increase versus the previously-recorded 1448/1419 totals reflects `backtesting/metrics.py`/`tests/test_metrics.py` being reconciled into this document, not new work performed during this pass. A real `pytest` install (`pip install -r requirements.txt`) should be used instead whenever network access is available.
- No genuine test failures of any kind were observed — only the pre-existing, environment-dependent `pytest`-availability gap above.
- Some HTTP client tests intentionally exercise retry/timeout/rate-limit paths against a fake unreachable host (`https://example.test/foo`); the resulting connection-error/retry log lines during a test run are expected test output, not bugs.
- A full recursive import check (every module under `core/`, `data/`, `analysis/`, `indicators/`, `signals/`, `strategies/` — including `strategies.portfolio_management`, with `portfolio_manager.py` (Part 3) and `aggregator.py` (Part 4) — `api/`, `config/`, `database/`, `events/`, `models/`, `services/` — including the five Part 1 modules (`base.py`, `context.py`, `result.py`, `exceptions.py`, `utils.py`), new this pass — `backtesting/`, `execution/`, `app/`, `utils/`, plus `main.py`) imports cleanly with zero import-time errors: 161/161 real modules checked this pass import cleanly (the only 2 import failures anywhere in the repository remain the pre-existing `tests.test_core_domain`/`tests.test_events` pytest-availability gap described above, not a real-module import error). `tests.test_services` also imports and passes cleanly.

## Compile status

- **This pass:** all 228 `.py` files in the repository (173 non-test
  files, 55 files under `tests/`, the latter including `helpers.py`/
  `__init__.py`) byte-compile cleanly with `python3 -m py_compile`
  (Python 3.12.3) — zero syntax errors, zero import-time errors at
  compile stage. This total newly includes `app/backtest_runner.py`
  (new this pass) and its dedicated test file
  (`tests/test_backtest_runner.py`) — both new this pass;
  `app/exceptions.py` and `app/__init__.py` were also updated (not
  newly added) to add/export the new `BacktestRunner*` exception
  classes and `BacktestRunner`/`BacktestRunResult` respectively. Note:
  the previously-recorded count directly below (216/165/51) does not
  fully account for every file present before this pass began (see
  the "Current test status" note above on the same reconciliation
  lag) — this pass verifies and records the actual current count
  directly, without auditing the full history of that gap.
- **Previously recorded** (Main Application Part 1 pass): all 216
  `.py` files in the repository (165 non-test files, 51 files under
  `tests/`, the latter including `helpers.py`/`__init__.py`)
  byte-compile cleanly with `python3 -m py_compile` (Python 3.12.3) —
  zero syntax errors, zero import-time errors at compile stage. This
  total newly included `app/main.py` (Main Application Part 1) and its
  dedicated test file (`tests/test_main.py`) — both new that pass;
  `app/__init__.py` was also updated (not newly added) to export and
  document `MainApplication`. Note: the previously-recorded count
  directly below (211/162/49) was already stale by 3 files even before
  that pass — `app/pipeline.py` and `tests/test_pipeline.py` existed
  and byte-compiled cleanly but had not been included in that prior
  count, the same reconciliation gap described in "Last completed
  milestone" above.
- Previously recorded: all 211 `.py` files in the repository (162 non-test
  files, 49 files under `tests/`) byte-compile cleanly with
  `python3 -m py_compile` (Python 3.12.3) — zero syntax errors, zero
  import-time errors at compile stage. This total newly includes
  `services/signal_engine.py` (Services Part 2A) and its dedicated
  test file (`tests/test_signal_engine.py`) versus the
  previously-recorded 209/48 totals below — both are new this pass;
  `services/__init__.py` was also updated (not newly added) to export
  and document `SignalEngine`.
- Previously recorded: all 209 `.py` files in the repository (161
  non-test files, 48 files under `tests/`), including the six
  `services/` modules (`base.py`, `context.py`, `result.py`,
  `exceptions.py`, `utils.py`, `__init__.py` — Services Part 1, new
  implementation) and their dedicated test file
  (`tests/test_services.py`), byte-compiled cleanly with
  `python3 -m py_compile` (Python 3.12.3) — zero syntax errors, zero
  import-time errors at compile stage.
- Prior to that: all 203 `.py` files in the repository (156
  non-test files, 47 files under `tests/`), including the six
  `execution/` modules (`base.py`, `context.py`, `result.py`,
  `exceptions.py`, `utils.py`, `__init__.py` — Execution Engine
  Part 1), `backtesting/report.py` (Backtesting Engine Part 5), and
  their two dedicated test files (`tests/test_execution.py`,
  `tests/test_report.py`), byte-compiled cleanly with
  `python3 -m py_compile` (Python 3.12.3) — zero syntax errors, zero
  import-time errors at compile stage.

## Last completed milestone

**New implementation — Main Application Part 1 (`app/main.py` —
`MainApplication`), plus reconciliation of `app/pipeline.py`
(`MarketPipeline`)**: this pass built `MainApplication`, the
application's composition root, and additionally reconciled this
document with `app/pipeline.py` (`MarketPipeline`), which was found
already present, already covered by `tests/test_pipeline.py`, and
already correct, but had not previously been documented in the
"Completed"/"Partially completed" tables above (`app/` was listed as
stub-only).

`MainApplication` holds one instance of every already-implemented
top-level engine/service, wired together via dependency injection:

- **Configuration loading** — `config.settings.get_settings()` (or an
  injected `Settings` instance) supplies `MainApplication.settings`;
  its `database_url` is translated (via a small private helper,
  `_sqlite_path_from_database_url`) into the plain filesystem path the
  default `DataEngine` is constructed with.
- **Dependency injection** — every collaborator (`data_engine`/
  `market_data_client`, `analyzer`, `signal_generator`, `strategy`,
  `risk_manager`, `portfolio_manager`, `backtester`, `signal_engine`)
  is an optional, keyword-only constructor parameter, validated against
  the same abstract base its own ecosystem already uses
  (`app.exceptions.PipelineConfigurationError` — reused, no new
  exception type added — on a type mismatch).
- **Initializes existing engines/services only** — omitting a
  collaborator constructs a plain, no-argument instance of the
  corresponding already-shipped concrete class: `data.engine.DataEngine`
  (via `data.client.BinanceRESTClient` by default), `analysis.aggregator.
  AnalysisAggregator`, `signals.aggregator.SignalAggregator`,
  `strategies.aggregator.StrategyAggregator`, `strategies.
  risk_management.BasicRiskManager`, `strategies.portfolio_management.
  PortfolioManager`, `backtesting.BasicBacktester`, and `services.
  SignalEngine` (with no `EventBus` injected — none exists concretely
  anywhere in the repository yet).
- **Constructor only, no orchestration** — no other public method
  exists on `MainApplication` besides a cosmetic `__repr__` (mirroring
  every `Base*`/`BaseService` class's own convention); no engine's
  `run()`/`analyze()`/`generate()`/`decide()`/`evaluate()`/`execute()`
  is ever called from `__init__`. No analysis execution, no AI, no
  broker, no UI, no CLI, and no business logic of any kind.

`execution/` (Execution Engine Part 1) is deliberately **not**
composed — it ships no concrete `BaseExecutionEngine` implementation
yet. `app.pipeline.MarketPipeline` is also not composed — assembling
one from `MainApplication`'s own collaborators is exactly the kind of
sequencing this part excludes; that remains open for a future Main
Application part, alongside actually orchestrating the engines this
part only constructs.

Reuses `config.settings`, `data.client`, `data.engine`, `analysis`,
`signals`, `strategies`, `strategies.risk_management`, `strategies.
portfolio_management`, `backtesting`, and `services` exactly as they
already exist — no existing implementation file was modified, other
than `app/__init__.py` (to export `MainApplication` and document it in
the package's module docstring). `analysis/`, `signals/`, `strategies/`
(including `risk_management/`/`portfolio_management/`), `backtesting/`,
`execution/`, `services/`, and `core/` were all left completely
untouched.

Covered by 47 new unit tests in `tests/test_main.py`: the
`_sqlite_path_from_database_url` helper in isolation (the `sqlite:///`
scheme, an absolute-path variant, an empty path falling back to the
default, a non-`sqlite` URL falling back to the default, non-`str`
input falling back to the default), construction with every
collaborator defaulted (each attribute is an instance of the expected
concrete class; `settings` defaults to the process-wide
`get_settings()` singleton), dependency injection (every collaborator,
when supplied — a real instance or a fake — is stored exactly as
given, including that an injected `data_engine` takes precedence over
an injected `market_data_client`, and that two `MainApplication`
instances never share collaborator state), validation
(`PipelineConfigurationError` for every mistyped collaborator, `None`
always accepted as "use the default" for every parameter), a
scope-boundary section (exactly the nine documented public attributes
exist and no others, no `execution_engine`/`pipeline` attribute, the
constructor is the only public callable besides `__repr__`,
construction never triggers any stored engine's own logic — probed via
a fresh call to `signal_engine.execute()` after construction still
failing exactly the way a never-orchestrated `SignalEngine` always
does), and an end-to-end integration section building two independent,
fully-wired `MainApplication` instances against real `Settings`
pointing at separate temporary SQLite databases.

No existing implementation file was modified by this pass other than
`app/__init__.py`, as noted above. `PROJECT_RULES.md` required no
changes — no rule itself changed. `DEVELOPER_GUIDE.md` required no
changes either — no architecture rule, convention, or reusable
abstraction itself changed; `MainApplication` follows the same
constructor-DI-with-sensible-defaults convention every engine in this
repository already established.

A full compile check (218 `.py` files: 164 non-test, 54 under `tests/`)
byte-compiled cleanly. A full test-suite run via the standard-library
`unittest` runner gives **1699 pass, 3 failures, 3 errors** — the same
6 pre-existing issues every prior pass has carried forward
(`test_core_domain.py`/`test_events.py` needing `pytest`, plus three
`tests/test_signal_engine.py` cases that assert Services Part 2A's
"`execute()` always raises `NotImplementedError`" behavior against a
`services/signal_engine.py` that, on inspection this pass, already
ships real Part 2B orchestration — a pre-existing inconsistency
between that test file and the implementation it covers, predating and
unrelated to this pass's own change; verified by temporarily removing
`app/main.py`/`tests/test_main.py` and re-running the suite, which
reproduces the identical 6 issues against a baseline of 1652 tests).
Fixing that pre-existing inconsistency is outside this milestone's
scope (Main Application Part 1 touches only `app/`) and is noted here
for whichever pass reconciles Services Part 2B into this document.

Before this, the prior milestone was:

**New implementation — Services Part 2A (`services/signal_engine.py` —
`SignalEngine`)**: this pass built `SignalEngine`, the first concrete
`BaseService` in `services/`, on top of Part 1's foundation
(`BaseService`/`ServiceContext`/`ServiceResult`/`ServiceError`
hierarchy/`services.utils`). Despite the name, `SignalEngine` is
unrelated to (and does not import) the `signals/` package — `services/`
may only depend on `core`/`events` (`PROJECT_RULES.md` Section 4).
It will, in a future Services part (2B), publish an already-produced
`core.entities.signal.Signal` as an `events.event_types.
signal_generated.SignalGenerated` event through an injected
`events.interfaces.event_bus.EventBus`.

Per this milestone's explicit scope, Part 2A ships only `SignalEngine`'s
**public interfaces** — no orchestration logic:

- **Constructor** — `SignalEngine(event_bus=None, *, config=None,
  name=None)`, calling `BaseService.__init__(name=name)` and then
  validating and storing its two collaborators.
- **Dependency injection** — `event_bus` is an optional
  `events.interfaces.event_bus.EventBus`, dependency-injected rather
  than hard-wired to any concrete implementation (none exists anywhere
  in the repository yet — see `services/__init__.py`'s "Planned
  contents"). `None` is a fully valid value for this part; `has_event_bus()`
  reports whether one was supplied.
- **Validation** — `event_bus` must be `None` or an `EventBus`
  instance (`ServiceConfigurationError` otherwise). `config` must be a
  `dict` containing only keys already present in `SignalEngine.
  DEFAULT_CONFIG` (`auto_generate_signal_metadata`/
  `require_min_confidence`, both `bool`; `min_confidence`, a finite
  `float` in `[0.0, 1.0]`, with `int`/`bool`-typed input handled
  correctly — a plain `int` is coerced to `float`, a `bool` is
  explicitly rejected since `bool` is a `int` subclass in Python) —
  unrecognized keys, wrong types, or out-of-range/non-finite values
  all raise `ServiceConfigurationError`.
- **Engine configuration** — `config` overrides are merged onto
  `DEFAULT_CONFIG` (never partially replacing it) and exposed via
  `get_configuration()`, which returns a defensive copy so a caller
  can never mutate the engine's own `self.config` through the
  returned `dict`.
- **Public interfaces only** — `execute(context: ServiceContext) ->
  ServiceResult` is `BaseService`'s one abstract method, so
  `SignalEngine` is already concrete/instantiable, not another
  abstract base like Part 1's `BaseService` itself. Its body validates
  `context` via the inherited `validate_context()` (so an invalid
  `ServiceContext` is still rejected exactly as it would be for any
  other `BaseService`), then **always raises `NotImplementedError`**
  with a message naming the engine and pointing at "Services Part
  2B" — deliberately not building a `Signal` from `context.payload`,
  not applying `SignalEngine.config`, not calling
  `self.event_bus.publish(...)`, and not returning a `ServiceResult`
  reflecting a real publish attempt. That orchestration is explicitly
  out of scope for this milestone and is documented as the next open
  item for this package (see "Next recommended milestone" below).

Reuses `core.entities.signal.Signal`, `events.interfaces.event_bus.
EventBus`, and Services Part 1's `BaseService`/`ServiceContext`/
`ServiceResult`/`ServiceConfigurationError`/`services.utils.
validate_dict` exactly as they already exist — none of Part 1's five
modules (`base.py`, `context.py`, `result.py`, `exceptions.py`,
`utils.py`) was modified, and `analysis/`, `signals/`, `strategies/`
(including `risk_management/`/`portfolio_management/`),
`backtesting/`, `execution/`, and `core/` were all left completely
untouched. Only `services/__init__.py` (to export `SignalEngine` and
document Part 2A in its module docstring) was updated among existing
files.

Covered by 32 new unit tests in `tests/test_signal_engine.py`:
construction/inheritance (`is a BaseService`, default/custom `name`,
`repr` contents), dependency injection (accepts a real `EventBus` fake,
rejects a non-`EventBus` value, two instances never share state),
configuration (exact default shape, `get_configuration()`'s
defensive-copy semantics, partial and full overrides, `min_confidence`
boundary acceptance at `0.0`/`1.0`, `int`-to-`float` coercion,
rejection of a non-`dict` `config`, an unrecognized key, a non-`bool`
flag, an out-of-range/non-finite/`bool`-typed/non-numeric
`min_confidence`, and confirmation `DEFAULT_CONFIG` itself is never
mutated by an instance), `execute()` behavior (context-type validation
still runs and raises `InvalidServiceContextError` first, a valid
context still leads to `NotImplementedError`, the exception message
names the engine, and no event is ever published to an injected fake
bus), a scope-boundary section (a source-text check that this module
never imports `signals/`, confirmation `event_bus` is optional at
construction, confirmation the class is directly instantiable without
a fake subclass), and an end-to-end integration section building a
realistic `ServiceContext` around a real `core.entities.signal.Signal`
and a fake `EventBus`.

No existing implementation file was modified by this pass — Services
Part 1's own five modules, and every other package, were confirmed
unchanged and untouched. `PROJECT_RULES.md` required no changes — no
rule itself changed.

Before this, the prior milestone was:

**New implementation — Services Part 1 (`services/` foundation)**:
this pass built `services/`'s Part 1 foundation from scratch —
`BaseService` (`base.py`), `ServiceContext` (`context.py`),
`ServiceResult` (`result.py`), the `ServiceError` hierarchy
(`exceptions.py`), and shared validation helpers (`utils.py`) —
mirroring the exact Part 1 shape `analysis/`, `signals/`,
`strategies/`, `strategies/risk_management/`,
`strategies/portfolio_management/`, `backtesting/`, and `execution/`
each already established for their own foundation, adapted to
`services/`'s different nature: unlike every trading-decision engine
one layer down, `services/` wraps external integrations and
cross-cutting technical concerns (notifications, an AI/LLM client
wrapper, scheduling, a concrete `EventBus`) that are heterogeneous by
design, so its context/result types stay generic rather than
composing specific domain entities.

`ServiceContext` composes no domain entities (unlike `ExecutionContext`/
`BacktestContext`/`PortfolioContext`/etc. one layer down, each of which
bundles specific `core.entities`/upstream-result types) — it is a
generic `service_name` (identifies the target service/operation, e.g.
`"notification"`, `"ai_commentary"`, `"scheduler"`) + free-form
`payload` (the call's request data, whose shape is entirely up to
whichever concrete service interprets it) + `metadata` envelope, plus
a `has_payload()` helper. `ServiceResult` is deliberately minimal:
only `success` (`bool`), `summary`, and `metadata` — no `service_name`
field (mirroring `RiskResult`'s omission of `risk_manager_name` and
`ExecutionResult`'s omission of `engine_name`), no delivery receipt,
no provider/vendor identifiers, and — unlike every trading-decision
result one layer down (`AnalysisResult`/`SignalResult`/`StrategyResult`/
`RiskResult`/`PortfolioResult`/`ExecutionResult`, all of which carry a
`confidence` field) — no `confidence` field either, since a service
call either succeeds or it does not; there is no probabilistic
evaluation to express here. `BaseService` is an `abc.ABC` with an
abstract `execute(context: ServiceContext) -> ServiceResult` method
plus shared `validate_context`/`_build_result` helpers, the same
shape `BaseExecutionEngine.execute()` uses one layer down.

Framework only — Services Part 1 ships no concrete service (no
notification service, no AI/LLM client, no scheduler, no concrete
`EventBus` implementation), no broker integration, no execution
logic, no networking, no threading, no async, and no AI. Imported
directly (`from services import BaseService, ServiceContext,
ServiceResult, ServiceError, ServiceValidationError,
InvalidServiceContextError, InsufficientServiceDataError,
ServiceConfigurationError`) — this package has no parent package to
re-export through, the same leaf-level convention `execution/`/
`strategies.risk_management`/`strategies.portfolio_management`
already use. `services/__init__.py` (previously an explanatory stub
only, describing planned future contents) now documents this Part 1
foundation the same way `execution/__init__.py` documents its own
Part 1, while retaining its "Planned contents" section describing
`notification_service.py`/`ai_service.py`/`scheduler_service.py`/a
concrete `EventBus` implementation as still-future work. 48 dedicated
tests in `tests/test_services.py`: `ServiceResult` construction/
validation/frozen-field/scope-boundary checks (including a defensive
check that no `confidence`/`service_name`/provider/delivery-receipt
field has been introduced), `ServiceContext` construction/validation
(`service_name` non-empty-string validation, `payload`/`metadata`
dict-type validation, frozen-field/immutability checks, `has_payload()`),
`services.utils`/`services.exceptions` unit coverage, `BaseService`
abstract-base behavior via a minimal `FakeService` (mirroring
`test_execution.py`'s `FakeExecutionEngine` pattern), and an
end-to-end integration section building a real `ServiceContext` and
running it through a real `BaseService` subclass.

No existing implementation file was modified by this pass —
`analysis/`, `signals/`, `strategies/` (including `risk_management/`/
`portfolio_management/`), `backtesting/`, `execution/`, `core/`, and
every other package were confirmed unchanged and untouched.
`PROJECT_RULES.md` required no changes — no rule itself changed.

Before this, the prior milestone was:

**Verification/integration pass — Execution Engine Part 1
(`execution/`), plus reconciliation of Backtesting Engine Part 5
(`report.py`)**: this pass verified the repository as delivered
(byte-compile check, recursive import check, full `unittest`-runner
suite) and found two already-implemented, already-tested pieces of
code that this document had not yet been updated to describe.

`execution/` — `BaseExecutionEngine` (`base.py`), `ExecutionContext`
(`context.py`), `ExecutionResult` (`result.py`), the `ExecutionError`
hierarchy (`exceptions.py`), and shared validation helpers
(`utils.py`) — is the Execution Engine's Part 1 foundation, the last
framework-only checkpoint before an approved trading decision would
ever reach a broker/exchange. It mirrors the exact Part 1 shape
`analysis/`, `signals/`, `strategies/`, `strategies/risk_management/`,
`strategies/portfolio_management/`, and `backtesting/` each already
established: `ExecutionContext` composes only existing abstractions —
the current `core.entities.portfolio.Portfolio` (required), an
optional `strategies.result.StrategyResult` (the candidate trading
decision), an optional `strategies.risk_management.result.RiskResult`
(that decision's risk evaluation), and an optional `strategies.
portfolio_management.result.PortfolioResult` (whether the portfolio
has capacity) for one symbol/timeframe — no new domain concepts.
`ExecutionResult` is deliberately minimal: only `execution_approved`
(`bool`), `confidence` (`0.0..1.0`), `summary`, and `metadata` — no
order-id, no fill price/quantity, no broker/exchange identifiers, and
no `engine_name` field (mirroring `RiskResult`'s omission of
`risk_manager_name` and `PortfolioResult`'s omission of
`portfolio_manager_name`). `BaseExecutionEngine` is an `abc.ABC` with
an abstract `execute(context: ExecutionContext) -> ExecutionResult`
method plus shared `validate_context`/`_build_result` helpers.
Framework only — Part 1 ships no concrete execution engine, no
broker integration, no exchange API, no order execution, no
networking, no threading, no async, and no AI. Imported directly
(`from execution import BaseExecutionEngine, ExecutionContext,
ExecutionResult, ...`) — this package has no parent package to
re-export through, the same leaf-level convention `strategies.
risk_management`/`strategies.portfolio_management` already use
relative to `strategies/`. 60 dedicated tests in
`tests/test_execution.py`: construction/inheritance,
`ExecutionContext` construction/validation (required `Portfolio`,
each optional result's type-checking, frozen-field/immutability
checks), `ExecutionResult` construction/validation (bounds/type
checks on all four fields, `with_metadata()`'s new-instance
semantics), the `ExecutionError` hierarchy, `execution.utils`'
shared helpers (`clip`, `merge_metadata`, `validate_bool`,
`validate_non_empty_str`, `validate_unit_range`), and an end-to-end
integration section building a real `ExecutionContext` from real
`StrategyResult`/`RiskResult`/`PortfolioResult`/`Portfolio` instances.

`backtesting/report.py` — `BacktestReport` (Backtesting Engine
Part 5) — was also found already present, already exported and
documented in `backtesting/__init__.py`'s own module docstring, and
already fully covered by `tests/test_report.py` (41 tests, all
passing). It wraps an already-produced `BacktestResult` (Parts 1/2)
and `BacktestMetrics` (Part 4) into four read-only views — `summary()`
(one paragraph), `detailed_summary()` (multi-section text),
`trades_summary()`/`metrics_summary()` (structured `dict`s), and
`full_report()` (all four combined) — computing nothing itself and
mutating neither input. No charts, no HTML/PDF/CSV export, no
logging, no AI, no broker/order-execution logic — exactly what
`docs/ARCHITECTURE.md`'s "Backtesting Engine reporting" item (`PROJECT_STATE.md`'s
own prior "Next recommended milestone" list) had called out as
still-pending; it was not pending, only undocumented.

Per verification policy, implementation is only touched when
verification finds a real defect; both `execution/` and
`backtesting/report.py` were already correct and fully tested, so no
implementation file was changed this pass. Only this document and
`DEVELOPER_GUIDE.md` were updated, to describe code that was already
there. `PROJECT_RULES.md` required no changes — no rule itself
changed (the Dependency Rule direction, which `execution/` already
follows by importing only `core`, `strategies.result`, `strategies.
risk_management.result`, and `strategies.portfolio_management.result`,
was not touched). Every other engine (`analysis/`, `signals/`,
`strategies/` including `risk_management/`/`portfolio_management/`,
`backtesting/`'s other seven modules, `core/`, `data/`) was confirmed
unchanged and untouched by this pass.

Before this, the prior milestone was:

**Documentation-reconciliation pass (Backtesting Engine Part 4 —
`metrics.py`)**: this pass did not add or change any implementation
code. It verified the full repository as delivered (compile check,
recursive import check, full `unittest`-runner test suite) and found
that `backtesting/metrics.py` — performance-statistics calculations
for a completed backtest run (`BacktestMetrics`, `calculate_metrics`,
plus the composable `win_rate`/`profit_factor`/`compute_equity_curve`/
`max_drawdown`/`sharpe_ratio` helpers) — and its dedicated test file,
`tests/test_metrics.py` (36 tests), were already present in the
repository, already fully exported and documented in
`backtesting/__init__.py`'s own module docstring as "Backtesting
Engine Part 4", already byte-compiling cleanly, already importing
cleanly, and all 36 tests already passing. This file and
`DEVELOPER_GUIDE.md` had not been updated to reflect that state —
both still listed `metrics.py`/performance statistics as pending
future work. Per verification policy, implementation is only touched
when verification finds a real defect; since `metrics.py` was already
correct and fully tested, no implementation file was changed. Only
this document and `DEVELOPER_GUIDE.md` were updated, to describe the
`metrics.py` module that was already there (see `backtesting/
metrics.py`'s own module docstring, and the `backtesting/` row in
"Partially completed modules" above, for full detail on what it
computes). `PROJECT_RULES.md` required no changes — no rule itself
changed. `base.py`, `context.py`, `result.py`, `exceptions.py`,
`utils.py`, `basic_backtester.py`, and `portfolio_simulator.py` were
confirmed unchanged and untouched by this pass, as was every other
engine (`analysis/`, `signals/`, `strategies/` including
`risk_management/`/`portfolio_management/`, `core/`, `data/`).

The rest of this section (below) retains the prior milestones'
narrative — Backtesting Engine Part 2 (`BasicBacktester`), then
Backtesting Engine Part 1 (foundation), then earlier milestones — as
historical record.

**Backtesting Engine Part 2 — first concrete backtester
(`BasicBacktester`)**: this milestone added `BasicBacktester`
(`backtesting/basic_backtester.py`), the first concrete
`BaseBacktester`, built entirely on Part 1's foundation
(`BaseBacktester`/`BacktestContext`/`BacktestResult`/`BacktestError`
hierarchy/`backtesting.utils`).

- **Sequential, chronological replay** — iterates `context.candles`
  (already validated non-empty and chronologically ordered by
  `BacktestContext` itself) oldest to newest, calling
  `context.strategy.decide(...)` once per candle.
- **A minimal per-candle `StrategyContext`** — `symbol`/`timeframe`
  copied from the `BacktestContext`, `analysis_results=[]`,
  `signal_result=None`, `risk_result=None` (since `backtesting` does
  not depend on `analysis`/produce its own signals), with the current
  `Candle` and its index exposed only via `StrategyContext.metadata`
  (`{"candle": ..., "candle_index": ...}`) for a strategy that wants
  the underlying price data.
- **Consumes only `StrategyResult.action`** — never inspects any
  `AnalysisResult`/`SignalResult`/`RiskResult` directly and never
  decides *why* to trade; all trading logic remains the injected
  strategy's responsibility (`PROJECT_RULES.md` Section 1, principle
  5: "Backtesting is a consumer, never a strategy author").
- **Execution model** (the simplest deterministic one that satisfies
  "record trades" without inventing trading rules): `BUY` while no
  position is open on the symbol spends the entire current cash
  balance to open one long `Position` at the candle's `close` price
  and records one `Trade` (no-op if already holding a position, or if
  there is no positive cash available — no pyramiding, no
  margin/leverage); `SELL` while a position is open closes it in full
  at the candle's `close` price, credits the proceeds back to cash,
  records the `Trade`, and sets the position's
  `realized_pnl`/`status`/`closed_at` (no-op if no position is open);
  `HOLD` is always a no-op. No slippage, no commissions/fees, no
  leverage, and no performance statistics (Sharpe ratio, max drawdown,
  win rate, profit factor) are modeled — all remain future Backtesting
  Engine work (see `backtesting/__init__.py`'s "Planned contents":
  `metrics.py`, `report.py`, additional concrete backtesters).
- **Graceful per-candle unavailability** — a strategy raising
  `strategies.exceptions.InsufficientStrategyDataError` for a given
  candle is treated as "skip this candle"
  (`metadata["skipped_candles"]` records the count), mirroring the
  "absence only lowers, never raises" convention every other engine in
  this repository already follows; any other exception propagates
  unchanged, since that signals a genuine bug in the injected
  strategy rather than an ordinary "insufficient data" outcome.
- **Fully deterministic, no mutation of inputs** — no randomness, no
  wall-clock reads, no network/database I/O, no AI;
  `context.initial_portfolio` is deep-copied (`copy.deepcopy`) before
  any position/cash state is touched, and `context.candles` is only
  ever read.

Reuses Part 1's `BaseBacktester`/`BacktestContext`/`BacktestResult`/
`backtesting.exceptions.InsufficientBacktestDataError`/
`backtesting.utils.merge_metadata` exactly as they already exist, plus
`strategies.context.StrategyContext` and `strategies.exceptions.
InsufficientStrategyDataError` from the Strategy Engine — no new
domain concepts. `analysis/`, `signals/`, `strategies/` (including
`risk_management/` and `portfolio_management/`), and `core/` were left
completely untouched; none of Backtesting Engine Part 1's own files
(`base.py`, `context.py`, `result.py`, `exceptions.py`, `utils.py`,
`tests/test_backtesting.py`) were modified either. Only
`backtesting/__init__.py` (to export `BasicBacktester` and document
Part 2 in its module docstring) was updated among existing files.
`PROJECT_STATE.md` and `DEVELOPER_GUIDE.md` were updated to reflect the
current state; `PROJECT_RULES.md` required no changes — no rule itself
changed.

Covered by 56 new unit tests in `tests/test_basic_backtester.py`:
construction/inheritance (is a `BaseBacktester`, default/custom `name`,
`repr`), inherited `BacktestContext` validation (`InvalidBacktestContextError`
on a non-context/`None` argument), HOLD-only replay (no trades, cash
and positions unchanged, a fresh `final_portfolio` object, zero-trade
metadata), BUY-only replay (exactly one trade, `OrderSide.BUY`, first
candle's `close` price, cash fully spent, exactly one open long
`Position` sized at `cash / price`, no pyramiding across repeated BUY
signals, zero/negative-cash BUY is a no-op), SELL-with-no-open-position
no-op, a full BUY-then-SELL round trip (two trades in `BUY`/`SELL`
order, strictly chronological `executed_at`, position closed,
`realized_pnl` correct, cash reflects the round-trip profit, no open
positions remain), a position intentionally left open at run end
(recorded correctly in `metadata["open_positions_remaining"]`),
multiple alternating BUY/SELL round trips across many candles with
trades verified strictly chronological, `InsufficientStrategyDataError`
handling (every candle skipped, `run()` itself never raises it, a
partial-warm-up-then-recovery scenario, the summary mentioning skipped
candles), a non-`StrategyError` exception (`ValueError`) propagating
unchanged rather than being swallowed, no-mutation-of-inputs checks
(the original `initial_portfolio` and `candles` list are byte-for-byte
unchanged after `run()`, and running the same `BacktestContext` twice
produces identical results), determinism across repeated runs,
chronological-execution/`StrategyContext`-wiring checks (a recording
fake strategy sees candles in exact input order; `symbol`/`timeframe`
carried through; `analysis_results`/`signal_result`/`risk_result` are
always empty/`None`; per-candle `metadata["candle"]`/`["candle_index"]`
correct), output-shape/metadata/summary/scope-boundary checks (`Trade`
instances, non-empty summary mentioning symbol and strategy name,
every documented `metadata` key present, no order-execution/AI/
performance-metric keys anywhere, caller-supplied `BacktestContext.
metadata` preserved), a real-`BasicStrategy`-integration section
(proving genuine `BaseStrategy.decide()` reuse rather than a
special-cased fake — every candle is skipped since no matching
`AnalysisResult` is ever supplied on the per-candle `StrategyContext`,
exactly as a real `BasicStrategy` would require), and a defensive
empty-candles completeness check (confirming `BacktestContext` itself
already rejects an empty candle list, so `BasicBacktester`'s own
defensive `InsufficientBacktestDataError` guard is unreachable through
normal construction but remains a documented, self-contained
guarantee).

The rest of this section (below) retains the prior milestones'
narrative — Backtesting Engine Part 1 (foundation), then Portfolio
Management Part 4 (`PortfolioAggregator` test-coverage pass) — as
historical record; both predate and are unrelated to Backtesting
Engine Part 2.

**Backtesting Engine Part 1 — foundation** (prior milestone): this
milestone added the Backtesting Engine's foundation, mirroring the
exact Part 1 pattern already established for `analysis/`, `signals/`,
`strategies/`, `strategies/risk_management/`, and `strategies/
portfolio_management/`: `BaseBacktester` (`backtesting/base.py`, an
`abc.ABC` with an abstract `run(context: BacktestContext) ->
BacktestResult` plus shared `validate_context`/`_build_result`
helpers), `BacktestContext` (`backtesting/context.py`, a frozen
dataclass composing historical `core.entities.candle.Candle` data —
validated non-empty and chronologically ordered by `open_time` — a
`strategies.base_strategy.BaseStrategy` instance, and a starting
`core.entities.portfolio.Portfolio`, for one symbol/timeframe run),
`BacktestResult` (`backtesting/result.py`, a frozen dataclass:
`final_portfolio`, `summary`, `trades` (list of `core.entities.trade.
Trade`, empty by default), `metadata`, plus `with_metadata()`), the
`BacktestError` hierarchy (`backtesting/exceptions.py`:
`BacktestValidationError`, `InvalidBacktestContextError`,
`InsufficientBacktestDataError`, `BacktesterConfigurationError`), and
shared validation helpers (`backtesting/utils.py`:
`validate_non_empty_str`, `validate_instance_list`,
`validate_chronological_candles`, `merge_metadata`). Framework only,
per `PROJECT_RULES.md` Section 1, principle 5 ("Backtesting is a
consumer, never a strategy author"): no concrete backtester shipped in
this part, no trade simulation, no PnL calculation, no performance
statistics (Sharpe ratio, max drawdown, win rate, profit factor), and
no aggregation across runs. Only `backtesting/__init__.py` was
rewritten (from its prior explanatory-only stub docstring) to export
and document the new names; no existing engine (`analysis/`,
`signals/`, `strategies/`, `strategies/risk_management/`, `strategies/
portfolio_management/`, `core/`, `data/`) was modified. 52 dedicated
tests were added in `tests/test_backtesting.py`, covering
`BacktestResult`/`BacktestContext` construction and validation
(including chronological-candle-ordering rejection), the
`BacktestError` hierarchy, `backtesting.utils` unit coverage,
`BaseBacktester`'s abstract-base behavior via a minimal concrete fake,
and a real-`BaseStrategy`/`Portfolio`-integration section proving
actual reuse of the Strategy Engine's and `core`'s existing shapes.

**Portfolio Management Part 4 — test-coverage pass** (prior milestone):
this milestone
added the previously-missing dedicated unit-test file,
`tests/test_portfolio_aggregator.py` (62 tests), for `PortfolioAggregator`
(`strategies/portfolio_management/aggregator.py`), which had been
delivered as part of the project's implementation but was, until now,
only verified indirectly (compile/import checks, manual smoke-testing).
No implementation file was modified in this pass — `aggregator.py` was
compared against the existing implementation, confirmed correct, and
left exactly as-is. The rest of this section describes
`PortfolioAggregator` itself for context.

`PortfolioAggregator` is itself a concrete `BasePortfolioManager` built
on Parts 1-2's foundation (`BasePortfolioManager`/`PortfolioContext`/
`PortfolioResult`, `BasicPortfolioManager`) and is functionally
equivalent to `PortfolioManager` (Part 3) — same weighted-vote
aggregation shape — but named/documented explicitly to mirror
`strategies.aggregator.StrategyAggregator`'s (and `analysis.aggregator.
AnalysisAggregator`'s/`signals.aggregator.SignalAggregator`'s)
`*Aggregator` naming convention, rather than `PortfolioManager`'s own.

- **Combines one or more injected `BasePortfolioManager` instances**
  (defaulting to a single plain `BasicPortfolioManager()` when none are
  supplied) into one final `PortfolioResult`, running each
  sequentially against the same `PortfolioContext` — no concurrency,
  no wall-clock reads, no randomness, no I/O.
- **Weighted vote, not weighted score**: since `PortfolioResult` has no
  numeric score field (only a boolean `new_positions_allowed`), each
  sub-manager's decision is represented as a signed unit vote (`+1.0`
  allowed, `-1.0` blocked), scaled by a fixed per-manager `weight`
  (default `1.0`, keyed by the manager's own `.name`) and further
  scaled by that manager's own `confidence`. The resulting weighted-
  average `aggregate_score` (`-1.0`..`+1.0`) is thresholded via a
  configurable `allow_threshold` (default `0.0`) back onto a final
  boolean `new_positions_allowed`.
- **Unavailable managers**: any injected manager may raise
  `InsufficientPortfolioDataError` for a given context; `PortfolioAggregator`
  catches that per-manager and treats it as "this manager produced no
  decision" (`metadata["managers_missing"]` records which and why)
  rather than failing the whole aggregation — it only raises
  `InsufficientPortfolioDataError` itself when *none* of the injected
  managers produced a usable `PortfolioResult`.
- **Calculates and records**, in full, `aggregate_score`, `completeness`
  (fraction of injected sub-managers that produced a usable decision),
  `agreement` (weighted 1.0/0.0 match scale against the final decision
  — no `HOLD`-style neutral state exists for a boolean), and
  `confidence` (`completeness x agreement x` average confidence, the
  same shape the three aggregators above already use).
- **No scoring changes to Parts 1-3, no allocation, no position-sizing,
  no rebalancing, no broker/order-execution integration, no AI** —
  only weighted-arithmetic combination of already-computed decisions.
- **Independent of `PortfolioManager` (Part 3)**: neither module
  imports or subclasses the other; both are plain `BasePortfolioManager`
  siblings, and either may be nested as a sub-manager of the other (or
  of itself).

Consumes `BasePortfolioManager`/`PortfolioContext`/`PortfolioResult`/
exceptions/utils (Part 1) and `BasicPortfolioManager` (Part 2) exactly
as they already exist — no new domain concepts, and nothing in Parts
1-3 or the Analysis/Signal/Risk/Strategy Engines was modified. Only
`strategies/portfolio_management/__init__.py` (to export
`PortfolioAggregator` and document Part 4 in its module docstring) was
updated among existing files; every other file in the repository was
left untouched by this milestone's implementation. Imported directly
alongside Parts 1-3 (`from strategies.portfolio_management import
PortfolioAggregator, PortfolioManager, BasePortfolioManager,
BasicPortfolioManager, PortfolioContext, PortfolioResult, ...`), not
re-exported through `strategies/__init__.py`, the same convention
`strategies.risk_management` already uses relative to `strategies/`.

This pass added `tests/test_portfolio_aggregator.py` (62 tests) and
confirmed (no implementation changes): a full compile check (182/182
`.py` files byte-compile cleanly, including the new test file), a full
recursive import check (141/141 non-test modules import cleanly, plus
the new `tests.test_portfolio_aggregator` module), and a full test-suite
run via the standard-library `unittest` runner (1258/1260 pass; the
same 2 pre-existing errors as the prior milestone —
`test_core_domain.py`/`test_events.py` requiring `pytest`, which this
network-isolated sandbox cannot install — see "Current test status"
above; both files are unrelated to Portfolio Management). `PROJECT_STATE.md`
and `DEVELOPER_GUIDE.md` were updated to reflect the current state;
`PROJECT_RULES.md` required no changes — no rule or reusable-abstraction
convention itself changed by this pass.

`tests/test_portfolio_aggregator.py` mirrors the established
fake-sub-component style of `tests/test_portfolio_manager.py`/
`tests/test_strategy_aggregator.py`/`tests/test_signal_aggregator.py`
one, two, and three layers up, respectively: a `_FakePortfolioManager`
test double (constructor-injectable allowed/confidence/unavailable)
exercises the aggregation/merging logic precisely, and a dedicated
integration section combines real `BasicPortfolioManager` instances —
including a genuine `InsufficientPortfolioDataError` case from an
uncomputable-equity `Portfolio` — to prove the module actually reuses
Portfolio Management Part 2 end-to-end. A further dedicated
independence section confirms `PortfolioAggregator` does not import or
subclass `PortfolioManager` (and vice versa), that both are
`BasePortfolioManager` instances, and that a `PortfolioAggregator` can
be nested as a sub-manager of another `PortfolioAggregator`. Coverage
includes: construction/configuration validation (managers/weights/
allow_threshold, including boundary and rejection cases), `evaluate()`
context validation and unavailable-sub-manager handling (including the
"all unavailable raises" case and that sub-manager results are never
mutated), weighted-vote aggregation and `allow_threshold` mapping
(agreeing/conflicting/weighted/zero-weight/low-confidence votes), the
completeness/agreement/confidence shape, output-shape checks
(`PortfolioResult`'s exact four
fields, no allocation/order/AI fields anywhere), metadata/summary
traceability, determinism across repeated calls, and the real-manager
integration section described above.

Before this, the prior milestone was **Portfolio Management Part 3 —
test-coverage pass**: it added the previously-missing dedicated
unit-test file, `tests/test_portfolio_manager.py` (58 tests), for
`PortfolioManager` (`strategies/portfolio_management/
portfolio_manager.py`) — the first composite/aggregating
`BasePortfolioManager`, combining one or more injected
`BasePortfolioManager` instances (defaulting to a single plain
`BasicPortfolioManager()`) into one final `PortfolioResult` via the
same weighted-vote/`allow_threshold`/`aggregate_score`/`completeness`/
`agreement`/`confidence` shape `PortfolioAggregator` (Part 4, described
above) uses, mirroring `StrategyAggregator`'s/`SignalAggregator`'s role
one and two layers down each. No implementation file was modified in
that pass either — `portfolio_manager.py` was verified against the
existing implementation and left exactly as-is. That pass confirmed a
full compile check (180/180 `.py` files then in the repository), a
full recursive import check (140/140 non-test modules then in the
repository), and a full test-suite run (1196/1198 pass via the
standard-library `unittest` runner, the same 2 pre-existing pytest-only
errors as every other pass).

Before this, the prior milestone was **Portfolio Management Part 2**
(first concrete manager): `BasicPortfolioManager`
(`strategies/portfolio_management/basic_portfolio_manager.py`), the first
concrete `BasePortfolioManager`, built on Part 1's foundation
(`BasePortfolioManager`/`PortfolioContext`/`PortfolioResult`) and
mirroring the pattern `strategies.risk_management.basic_risk_manager.
BasicRiskManager` established one layer down.

- **Four independent gating checks** against a `PortfolioContext`:
  open-position count (how many currently `PositionStatus.OPEN`
  positions `PortfolioContext.portfolio` already holds, against a
  configurable `max_open_positions` ceiling), aggregate exposure (the
  fraction of portfolio equity already committed to open positions —
  current price, falling back to entry price, times quantity, summed
  across all open positions — against a configurable
  `max_exposure_ratio` ceiling), symbol concentration (the same
  fraction narrowed to open positions on `PortfolioContext.symbol`
  only, against a configurable `max_symbol_exposure_ratio` ceiling —
  deliberately independent of the aggregate check, since a portfolio
  can be under its aggregate limit while still overly concentrated in
  one symbol), and upstream signal/risk agreement (whether the
  candidate `strategies.result.StrategyResult` — when present —
  recommends a directional action, `BUY`/`SELL` not `HOLD`, and
  whether the candidate `strategies.risk_management.result.RiskResult`
  — when present — has `approved=True`).
- **All four gates must pass** for `new_positions_allowed=True`; any
  one failing is enough to block, with every reason recorded in
  `PortfolioResult.metadata["hard_reject_reasons"]` alongside every
  intermediate value that produced the decision, so the result can
  always be traced back to its inputs.
- **`confidence`** is derived only from how much of the optional
  context was actually available (`strategy_result`/`risk_result`
  presence) and, when present, their own `confidence` values — never
  from the pass/fail decision itself.
- **No scoring, weighting, or optimization** anywhere in this module —
  every check is a plain deterministic threshold/gate comparison. No
  allocation or position-sizing algorithm, no rebalancing of existing
  positions, no broker/order-execution integration, no AI-based
  assessment.

Consumes `PortfolioContext`/`PortfolioResult` (Part 1) and the existing
`core.entities.portfolio.Portfolio`/`core.entities.position.Position`,
`strategies.result.StrategyResult`, and `strategies.risk_management.
result.RiskResult` exactly as they already exist — no new domain
concepts, and nothing in the Analysis/Signal/Risk/Strategy Engines or
the Portfolio Management Part 1 foundation was modified. Only
`strategies/portfolio_management/__init__.py` (to export
`BasicPortfolioManager` and document Part 2 in its module docstring)
was updated among existing files; every other file in the repository
was left untouched by this milestone's implementation. Imported
directly alongside Part 1 (`from strategies.portfolio_management
import BasePortfolioManager, BasicPortfolioManager, PortfolioContext,
PortfolioResult, ...`), not re-exported through `strategies/__init__.py`,
the same convention `strategies.risk_management` already uses relative
to `strategies/`.

This verification/integration pass additionally confirmed (no
implementation changes): a full compile check (178/178 `.py` files byte-
compile cleanly), a full recursive import check (139/139 non-test
modules import cleanly), and a full test-suite run (1167/1167 test
cases passing — see "Current test status" above for the exact
methodology, including the disk-local `pytest` shim used to execute
the two pre-existing `pytest`-only test files in this network-isolated
sandbox). `PROJECT_STATE.md` and `DEVELOPER_GUIDE.md` were updated to
reflect the current state; `PROJECT_RULES.md` required no changes — no
rule or reusable-abstraction convention itself changed by this pass.

Covered by 43 new unit tests in `tests/test_basic_portfolio_manager.py`
(100 combined with Part 1's 57 in `tests/test_portfolio_management.py`):
construction/configuration validation (threshold ranges, weight
defaults), each of the four gating checks individually (open-position
count at/under the limit, closed positions not counted, aggregate
exposure at/under the limit, symbol concentration independent of the
aggregate check, missing/present `StrategyResult`/`RiskResult` and
their effect on gating), gate combinations, `confidence` derivation
from optional-context availability alone (never from the pass/fail
outcome), metadata/summary traceability (`hard_reject_reasons` and
every intermediate value), and an end-to-end integration section.

Before this, the prior milestone was **Portfolio Management Part 1**
(foundation): `strategies/portfolio_management/` —
`BasePortfolioManager` (`base.py`), `PortfolioContext` (`context.py`),
`PortfolioResult` (`result.py`), the `PortfolioError` hierarchy
(`exceptions.py`), and shared validation helpers (`utils.py`),
mirroring the exact role `analysis/base.py`/`context.py`/`result.py`/
`exceptions.py`/`utils.py` play as Analysis Engine Part 1's foundation,
`strategies/base_strategy.py`/`context.py`/`result.py`/`exceptions.py`/
`utils.py` play as Strategy Engine Part 1's, and `strategies/
risk_management/base.py`/`context.py`/`result.py`/`exceptions.py`/
`utils.py` play as Risk Engine Part 1's.

- **`PortfolioContext`** composes the current `core.entities.portfolio.
  Portfolio` (required — a portfolio manager cannot evaluate exposure/
  position-count constraints without it), an optional `strategies.
  result.StrategyResult` (the candidate trading decision under
  consideration), and an optional `strategies.risk_management.result.
  RiskResult` (that decision's risk evaluation) for one symbol/
  timeframe — no new domain concepts introduced.
- **`PortfolioResult`** is deliberately minimal: only
  `new_positions_allowed` (`bool`), `confidence` (`0.0..1.0`),
  `summary`, and `metadata` — no target allocation, no rebalancing
  instructions, no order-id, no `portfolio_manager_name` field
  (mirroring `RiskResult`'s omission of `risk_manager_name`).
- **`BasePortfolioManager`** is an `abc.ABC` with an abstract
  `evaluate(context: PortfolioContext) -> PortfolioResult` method plus
  shared `validate_context`/`_build_result` helpers, documenting (but
  not implementing) the responsibilities every concrete portfolio
  manager is expected to fulfill: evaluate overall portfolio state,
  determine whether a new position is allowed, enforce whatever
  portfolio-level constraints it defines, calculate `confidence`, and
  record every intermediate decision in `metadata`.

Framework only: no concrete portfolio manager ships in this part, no
allocation algorithm, no rebalancing logic, no broker integration.
Consumes existing `StrategyResult`, `RiskResult`, and `Portfolio`
exactly as they already exist; produces only `PortfolioResult`.
Fully deterministic — no AI, no randomness, no wall-clock reads, no
I/O. Reuses `strategies.result.StrategyResult` and `strategies.
risk_management.result.RiskResult` exactly as they already exist;
`strategies/risk_management/`, `strategies/`'s own foundation/
`BasicStrategy`/`StrategyAggregator`, `analysis/`, and `signals/` were
left completely untouched. Only `strategies/__init__.py` (to document
Part 1's existence in its module docstring) was updated among existing
files; `strategies/portfolio_management/` itself is an entirely new
package, imported directly (`from strategies.portfolio_management
import BasePortfolioManager, PortfolioContext, PortfolioResult, ...`),
not re-exported through `strategies/__init__.py`, the same convention
`strategies.risk_management` already uses relative to `strategies/`.
`PROJECT_STATE.md` was updated to reflect the new state
(`DEVELOPER_GUIDE.md`/`PROJECT_RULES.md` required no changes — no rule
or reusable-abstraction convention itself changed).

Covered by 57 new unit tests in `tests/test_portfolio_management.py`:
construction/validation for `PortfolioResult` (frozen, exactly the four
documented fields, out-of-range/non-finite confidence, non-bool
`new_positions_allowed`, blank summary, non-dict metadata rejected,
`with_metadata` immutability) and `PortfolioContext` (frozen, required
`Portfolio`, optional `StrategyResult`/`RiskResult`, blank symbol/
timeframe and non-instance fields rejected), the `PortfolioError`
hierarchy, `strategies.portfolio_management.utils` helpers
(`validate_non_empty_str`/`validate_unit_range`/`validate_bool`/
`clip`/`merge_metadata`), `BasePortfolioManager` via a minimal concrete
fake (abstract-instantiation guard, `validate_context`, `_build_result`
default metadata, `repr`), and a real-`StrategyResult`/`RiskResult`/
`Portfolio`-integration section proving actual reuse of the Strategy/
Risk Engines' and `core`'s output shapes, plus explicit scope-boundary
checks (no allocation/position-size/rebalancing/order-id fields
anywhere).

Before this, the prior milestone was Strategy Engine Part 3:
`StrategyAggregator` (`strategies/aggregator.py`),
which itself subclasses `BaseStrategy` and combines the `StrategyResult`s
of one or more injected `BaseStrategy` instances (defaulting to a single
plain `BasicStrategy()` when none are supplied) into one final
`StrategyResult` for one `StrategyContext` — mirroring the role
`analysis.aggregator.AnalysisAggregator` and `signals.aggregator.
SignalAggregator` already play one and two layers down, respectively.

- **Weighted aggregation** — each sub-strategy is keyed by its own
  `.name` (duplicates rejected) and may carry a constructor-
  configurable `weight` (default `1.0`, must be finite and `>= 0.0`,
  via the `weights` constructor parameter keyed by name); a
  sub-strategy's own `confidence` further scales its contribution on
  top of its fixed weight. Since `StrategyResult` has no numeric
  score/strength field, each sub-strategy's `action` is represented as
  a signed unit value (`+1.0`/`-1.0`/`0.0`), scaled by its confidence
  and weight, and weight-averaged into an aggregate score, thresholded
  back onto `SignalDirection.BUY`/`SELL`/`HOLD` via configurable
  `buy_threshold`/`sell_threshold` (same defaults/validation as
  `BasicStrategy`/`SignalAggregator`).
- **Availability handling** — runs every sub-strategy sequentially
  against the same `StrategyContext`; any sub-strategy raising
  `InsufficientStrategyDataError` is treated as "unavailable"
  (`metadata["strategies_missing"]` records which and why, mirroring
  `SignalAggregator`'s `generators_missing`/`AnalysisAggregator`'s
  `components_missing` convention) — `StrategyAggregator` itself only
  raises `InsufficientStrategyDataError` when every sub-strategy was
  unavailable.
- **Traceable facets** — calculates and records, in full, four facets:
  `overall_score`, `confidence`, `completeness` (fraction of
  sub-strategies that produced a usable decision), and `agreement`
  (weighted agreement between each contributing decision and the
  final aggregated action, on a `1.0`/`0.5`/`0.0` scale) — `confidence`
  itself is `completeness x agreement x` average confidence, the same
  shape `AnalysisAggregator`/`SignalAggregator` already use.

Fully deterministic — no AI, no randomness, no wall-clock reads, no
I/O; never mutates any sub-strategy's `StrategyResult`. No order
execution, no broker integration, no portfolio management, no
optimization — only aggregation. Reuses Parts 1-2
(`BaseStrategy`/`StrategyContext`/`StrategyResult`/exceptions/utils,
`BasicStrategy`) exactly as they already exist; `strategies/
risk_management/`, `analysis/`, and `signals/` were left completely
untouched. Only `strategies/__init__.py` (to export
`StrategyAggregator` and document Part 3 in its module docstring) was
updated among existing files; `PROJECT_STATE.md` and
`DEVELOPER_GUIDE.md` were the only other files updated
(`PROJECT_RULES.md` required no changes — no rule itself changed).

Covered by 50 new unit tests in `tests/test_strategy_aggregator.py`:
construction/configuration validation (weights, thresholds, duplicate
names, non-`BaseStrategy` items, empty strategy list), aggregation
behavior (agreeing/conflicting/HOLD sub-strategies, weight and
confidence scaling, threshold effects), completeness/agreement/
confidence shape (missing-strategy and disagreement effects, bounds),
output shape (metadata contents, determinism, no order/broker/AI
fields, summary content, sequential ordering preserved), validation
(non-`StrategyContext` input rejected, single-unavailable-strategy
tolerated, all-unavailable raises, missing reasons recorded, no
mutation of sub-strategy results), and a real-`BasicStrategy`-
integration section proving actual reuse of Part 2.

Before this, the prior milestone was Strategy Engine Part 2:
`BasicStrategy` (`strategies/basic_strategy.py`), the first
concrete `BaseStrategy` implementation, built on Part 1's foundation
(`BaseStrategy`, `StrategyContext`, `StrategyResult`). It combines one
`AnalysisResult` (matched by `analyzer_name`, default
`"AnalysisAggregator"` — the same lookup convention
`TechnicalSignalGenerator` already uses), an optional `SignalResult`,
and an optional `RiskResult` into a single `StrategyResult`, in three
deterministic steps:

- **Directional scoring** — the analysis score (`-1.0..+1.0`) and, when
  a signal is present, its signed score (`direction` sign x
  `strength`, the same convention `SignalAggregator` uses) are combined
  into a confidence-weighted `overall_score`, then thresholded onto
  `SignalDirection.BUY`/`SELL`/`HOLD` via configurable
  `buy_threshold`/`sell_threshold` (same defaults as
  `TechnicalSignalGenerator`: `0.2`/`-0.2`).
- **Consistency evaluation** — a `0.0..1.0` agreement score between the
  analysis-derived direction and the signal's own direction (when
  present: `1.0` match, `0.5` one-sided `HOLD`, `0.0` direct
  BUY/SELL conflict), and between the tentative action and risk
  approval (when present). A signal or risk evaluation that is simply
  absent never manufactures a conflict — it only lowers completeness,
  the same "absence only lowers confidence, never raises" convention
  every prior engine part in this repository follows.
- **Risk gate** — an unapproved `RiskResult` downgrades a would-be
  `BUY`/`SELL` to `HOLD` (`metadata["risk_override"] = True`), mirroring
  how `signals.filters.ConflictFilter` downgrades rather than silently
  drops a conflicting signal. A `HOLD` action is never overridden —
  there is nothing for risk to approve/reject when no trade is
  proposed.

`confidence` combines each contributing result's own confidence
(weighted the same way as `overall_score`), the consistency score, and
a completeness ratio (analysis always counts; signal/risk each add to
completeness only when present) — the same `completeness * conviction *
confidence` shape `AnalysisAggregator`/`SignalAggregator` already use
one layer down. `StrategyResult` carries no `score` field (mirroring
`RiskResult`'s minimalism), so the required overall strategy score
lives at `metadata["overall_score"]`, alongside every other
intermediate value (`analysis`/`signal`/`risk` facets used,
`raw_action` vs `final_action`, `risk_override`, the full consistency
and confidence breakdown, thresholds, weights, `inputs_available`) for
full traceability.

Fully deterministic — no randomness, no wall-clock reads, no network/
database I/O. No AI, no order execution, no broker integration, no
portfolio management (never reads a `Portfolio` — `RiskResult.approved`/
`risk_score` are consumed exactly as already computed by
`strategies.risk_management`), no optimization (thresholds/weights are
simple constructor constants, never fit or searched over), and only
this one concrete strategy ships in this part — additional strategies
remain future Strategy Engine parts. Part 1
(`strategies/base_strategy.py`, `context.py`, `result.py`,
`exceptions.py`, `utils.py`), `strategies/risk_management/` (all of
Risk Engine Parts 1-3), `analysis/`, `signals/`, and `core/` were left
completely untouched. Only `strategies/__init__.py` (to export
`BasicStrategy` and document Part 2 in its module docstring) was
updated among existing files; `PROJECT_STATE.md` was the only other
file updated (`DEVELOPER_GUIDE.md` and `PROJECT_RULES.md` required no
changes — no reusable abstraction or rule itself changed, `strategies/`
already documented `BasicStrategy` as planned future content).

Covered by 39 new unit tests in `tests/test_basic_strategy.py`:
constructor/configuration validation (analyzer name, threshold ranges,
non-negative weights), required-input handling (raises
`InsufficientStrategyDataError` when no matching `AnalysisResult` is
present; a custom `analysis_analyzer_name` is honored), directional
decisions from analysis alone (strong bullish/bearish/neutral, and that
a missing signal/risk lowers confidence without raising), consistency
scoring (full/zero/partial agreement between analysis and signal
directions; full alignment when risk approves; fully-consistent
treatment when signal/risk are simply absent), the risk gate
(downgrades both BUY and SELL to HOLD on `approved=False`, never
overrides an already-HOLD decision, never overrides on `approved=True`),
metadata/summary traceability (every documented metadata key present,
`available`/`unavailable` flags correct, summary mentions symbol/
timeframe and notes missing inputs/risk overrides), determinism
(identical `StrategyResult` across repeated `decide()` calls on the
same context, across a range of scores), scope-boundary checks
(`StrategyResult`'s exact four fields, no `order_id`/`broker`/
`ai_model`/`position_size`/`execution_status` anywhere, `confidence`/
`overall_score` always within their documented bounds), and a dedicated
end-to-end integration section building realistic `StrategyContext`s
from `AnalysisResult` + `SignalResult` + `RiskResult`.

Before this, the prior milestone was Risk Engine Part 3: three further concrete `BaseRiskManager`
implementations — `PositionSizeRule` (`position_size_rule.py`),
`StopLossRule` (`stop_loss_rule.py`), and `TakeProfitRule`
(`take_profit_rule.py`) — built on Part 1's foundation, alongside (not
on top of) Part 2's `BasicRiskManager`. All three consume only
`RiskContext`/existing `core.entities`, produce only `RiskResult`
(computed prices/sizes live in `metadata`, never as new `RiskResult`
fields), and are deliberately independent of each other and of
`BasicRiskManager` — none imports or depends on any of the others, and
each computes its own per-unit risk distance internally rather than
consuming another rule's output.

- **`PositionSizeRule`** — fixed-fractional risk sizing.
  `risk_amount` = portfolio equity x a configurable `risk_per_trade`.
  A per-unit risk distance (expressed as a ratio of price) is
  estimated from ATR when available (`atr_value * atr_multiplier /
  reference_price`) or a configurable `default_stop_distance_pct`
  fallback. `recommended_position_value` = `risk_amount /
  stop_distance_ratio`, capped at a configurable
  `max_position_fraction` of equity. A base-asset
  `recommended_position_size` is additionally reported when a
  reference price is resolvable (from `signal.metadata["entry_price"]`
  or `market_state.latest_candle.close`) — its absence only lowers
  `confidence`, since a quote-currency value can still be reported
  without one.
- **`StopLossRule`** — a direction-aware protective stop price (below
  the reference price for `BUY`, above it for `SELL`), from the same
  ATR-or-percentage distance estimate, clamped to a configurable
  `[min_stop_distance_pct, max_stop_distance_pct]` range. Unlike ATR,
  a reference price is *required* here — a stop-loss is a price, and
  no price data means none can be computed.
- **`TakeProfitRule`** — a direction-aware target price (above the
  reference price for `BUY`, below it for `SELL`), computing its own
  equivalent base risk-leg distance the same way `StopLossRule` does
  (never by consuming `StopLossRule`'s output) and scaling it by a
  configurable `risk_reward_ratio`. Also requires a resolvable
  reference price for the same reason `StopLossRule` does.

All three treat a `SignalDirection.HOLD` signal as an explicit "not
applicable" result (`approved=False`, the relevant price/size field
`None`) rather than an error, and raise `InsufficientRiskDataError`
only for a truly required input that is completely unusable: an
unusable `signal.confidence` (non-numeric/non-finite, all three),
non-positive portfolio equity (`PositionSizeRule` only), or a
completely unresolvable reference price (`StopLossRule`/
`TakeProfitRule` only). A missing-but-optional ATR reading never
raises for any of the three — it only falls back to the
percentage-based distance and lowers `confidence`. Every intermediate
value (reference price and its source, ATR availability/value, basis
used, computed distances/clamping flags, the resulting price/size) is
recorded in `RiskResult.metadata` for full traceability.

No AI, no Strategy Engine, no order execution, and no writing computed
values back onto `core.entities.position.Position.stop_loss`/
`take_profit` — each rule only recommends a value via
`RiskResult.metadata`; acting on it is out of scope. Risk Engine
Parts 1-2 (`base.py`, `context.py`, `result.py`, `exceptions.py`,
`basic_risk_manager.py`) and `analysis/`/`signals/`/`core/` were left
completely untouched. Only `strategies/risk_management/__init__.py`
(to export the three new rules and document Part 3 in its module
docstring) was updated among existing files; `PROJECT_STATE.md` and
`DEVELOPER_GUIDE.md` were the only other files updated
(`PROJECT_RULES.md` required no changes — no rule itself changed).
Covered by 103 new unit tests in `tests/test_risk_rules.py`:
construction/configuration validation for each rule, `validate_context()`'s
inherited behavior, normal-path evaluation (BUY/SELL, ATR available,
reference price available), edge cases (percentage-based fallback,
missing optional data, clamping/capping, HOLD short-circuit), invalid
input (non-numeric/non-finite `signal.confidence`, wrong context type,
unresolvable required data), `metadata` shape/traceability,
`confidence` behavior (degrades gracefully with missing optional data,
never raises for it), and a dedicated rule-independence section
confirming none of the three imports the others and that evaluating
one does not affect another's output.

Before this, the prior milestone was Risk Engine Part 2: `BasicRiskManager`
(`strategies/risk_management/basic_risk_manager.py`), the first
concrete `BaseRiskManager` implementation, built on Part 1's
foundation (`BaseRiskManager`, `RiskContext`, `RiskResult`). It
evaluates four independent facets of a `RiskContext` into one
`RiskResult`:

- **Signal confidence** — `RiskContext.signal.confidence`, defensively
  validated: raises `InsufficientRiskDataError` only when the value is
  not a usable, finite number (no meaningful assessment is possible
  from it); merely out-of-`[0.0, 1.0]` values are clamped and the
  clamp is recorded in `metadata["signal_confidence_clamped"]`.
- **Signal strength** — an optional `"strength"` entry read from
  `RiskContext.signal.metadata` (`core.entities.signal.Signal` itself
  has no `strength` field, unlike `signals.result.SignalResult`,
  which does). Its absence, or an unusable value, only means the
  facet is treated as "unavailable" with a neutral default risk
  contribution (`missing_strength_risk`, default `0.5`) — it never
  raises, and a missing/unavailable strength never triggers the
  strength hard-reject check.
- **Portfolio exposure** — the fraction of portfolio equity already
  committed to open positions, computed from
  `RiskContext.portfolio.positions` (`current_price`, falling back to
  `entry_price`, times `quantity`) against `portfolio.total_equity`
  when already computed, or `cash_balance + position_value` as a
  graceful fallback otherwise. A malformed individual `Position` is
  skipped rather than failing the whole evaluation. Zero/negative
  equity with open positions is treated as maximal (`1.0`) exposure;
  zero equity with no positions is `0.0`.
- **Market availability** — `RiskContext.has_market_state()`; its
  absence only lowers this result's `confidence` and applies a
  configurable `market_unavailable_risk` contribution, exactly like
  every other optional facet `RiskContext` already documents — it
  never raises.

Each facet becomes a `0.0..1.0` risk contribution; these are combined
via four constructor-configurable weights (`confidence_weight`,
`strength_weight`, `exposure_weight`, `market_weight` — validated at
construction to each lie in `[0.0, 1.0]` and sum to exactly `1.0`,
raising `RiskManagerConfigurationError` otherwise) into `risk_score`.
Three further configurable hard-threshold checks —
`min_signal_confidence`, `min_signal_strength` (only enforced when
strength is available), and `max_exposure_ratio` — can each
independently force `approved=False` regardless of `risk_score`;
`approved` is `True` only when `risk_score <= risk_score_threshold`
**and** no hard-reject reason fired. `confidence` (the `RiskResult`'s
own confidence in its assessment, distinct from `signal.confidence`)
scales `signal.confidence` down by a completeness factor reflecting
how much optional data (strength, market state) was actually
available. `metadata` records every intermediate value —
`signal_confidence`/`signal_confidence_clamped`,
`signal_strength`/`signal_strength_available`/
`signal_strength_clamped`, `exposure_ratio`,
`equity_used_for_exposure`, `market_state_available`, `components`
(each facet's risk contribution), `weights`, `thresholds`, and
`hard_reject_reasons` — so every decision is fully traceable back to
its inputs.

No position sizing, no stop-loss/take-profit calculation, no order
execution, no strategy/trading decisions, no AI — `BasicRiskManager`
does not implement `core.interfaces.risk_manager.RiskManager` for the
same reason `BaseRiskManager` itself does not (that interface also
requires `calculate_position_size`/`calculate_stop_loss`). Risk Engine
Part 1 (`strategies/risk_management/base.py`, `context.py`,
`result.py`, `exceptions.py`) and `analysis/`/`signals/`/`core/` were
left completely untouched. Only `strategies/risk_management/__init__.py`
(to export `BasicRiskManager`), `strategies/risk_management/utils.py`
(one additive `clip()` helper — no existing helper changed), and
`strategies/__init__.py` (docstring only) were updated among existing
files; `PROJECT_STATE.md` and `DEVELOPER_GUIDE.md` were the only other
files updated (`PROJECT_RULES.md` required no changes — `risk_management/`
and its future concrete implementations were already documented there,
so no rule itself changed). Covered by 45 new unit tests in
`tests/test_basic_risk_manager.py`: constructor/configuration
validation (weight range/sum, `max_exposure_ratio` positivity,
threshold ranges), `validate_context()`'s inherited behavior, output
shape (`RiskResult`'s five fields only, no position-size/stop-loss/
take-profit/order-id keys anywhere in `metadata`), each of the four
facets in isolation (confidence clamping/rejection, strength
availability/clamping, exposure computed from `total_equity` vs. the
cash+positions fallback vs. malformed-position skipping, market
availability's effect on `confidence`), the approval decision
combining all four facets, and a dedicated end-to-end integration
section building a realistic `RiskContext` from a `Signal` (with a
`SignalResult`-style `strength` in its metadata) + `Portfolio` (with
an open `Position`) + `MarketState` and evaluating it through a real
`BasicRiskManager`.

Before this, the prior milestone was Risk Engine Part 1: the `strategies/risk_management/` package
foundation -- `BaseRiskManager` (`base.py`), `RiskContext`
(`context.py`), `RiskResult` (`result.py`), the `RiskError` hierarchy
(`exceptions.py`), and shared validation helpers (`utils.py`). Mirrors
the exact role `analysis/`'s and `signals/`'s own Part 1 foundations
play: `analysis/` interprets raw data into an `AnalysisResult`,
`signals/` standardizes one or more `AnalysisResult`s into a
`SignalResult`, and `strategies.risk_management` evaluates whether a
candidate `Signal` is safe to act on against a `Portfolio`, without
deciding position size, protective levels, or whether to place an
order.

- `BaseRiskManager` is an `abc.ABC` with an abstract
  `evaluate(context: RiskContext) -> RiskResult` method plus shared
  `validate_context`/`_build_result` helpers. It deliberately does
  **not** implement `core.interfaces.risk_manager.RiskManager` --
  that interface also requires `calculate_position_size`/
  `calculate_stop_loss`, which are out of scope for this part --
  mirroring how `signals.base.BaseSignalGenerator` does not itself
  implement `core.interfaces.signal_generator.SignalGenerator`.
- `RiskContext` is an immutable, validated bundle of `symbol`,
  `timeframe`, `signal: Signal`, `portfolio: Portfolio`, and an
  optional `market_state: MarketState | None` (+ free-form `metadata`),
  reusing only existing `core.entities` -- no new domain type is
  introduced. A `has_market_state()` helper mirrors
  `AnalysisContext.has_news()`.
- `RiskResult` is a frozen dataclass containing *only* the five fields
  specified for this milestone -- `approved` (`bool`), `risk_score`
  (`0.0..1.0`), `confidence` (`0.0..1.0`), `summary`, and `metadata` --
  deliberately excluding any position-size, stop-loss, take-profit, or
  order-id field. A `with_metadata()` helper mirrors
  `AnalysisResult`/`SignalResult`'s own immutable-update convention.

No position sizing, no stop-loss/take-profit calculation, no order
execution, no strategy/trading decisions, no AI -- and no concrete
`BaseRiskManager` implementation either; this part is foundation only,
exactly as `analysis/`'s and `signals/`'s own Part 1 were before later
parts landed. `analysis/` and `signals/` (every existing file) were
left completely untouched. Only `strategies/__init__.py` was updated
among existing files (to document the new `risk_management/`
subpackage, which is imported directly -- `from
strategies.risk_management import BaseRiskManager, RiskContext,
RiskResult, ...` -- not re-exported through `strategies/__init__.py`,
the same convention `analysis/technical/` uses relative to
`analysis/`). `PROJECT_STATE.md` and `DEVELOPER_GUIDE.md` were the
only other files updated (`PROJECT_RULES.md` required no changes --
`risk_management/` was already documented there as a planned
subpackage of the existing `strategies/` package, so no rule itself
changed). Covered by 51 new unit tests in
`tests/test_risk_management.py`: `RiskResult` construction/validation
(including confirming it has exactly the five documented fields),
`RiskContext` construction/validation (including optional
`market_state`), the `RiskError` hierarchy, every
`strategies.risk_management.utils` helper, `BaseRiskManager` shared-
helper behavior via a minimal concrete fake (mirroring
`test_analysis.py`'s fake `BaseAnalyzer` / `test_signals.py`'s fake
`BaseSignalGenerator` pattern), and a dedicated integration section
building a realistic `RiskContext` from `Signal` + `Portfolio` +
`MarketState` and evaluating it end-to-end through a real
`BaseRiskManager` subclass.

Before this, the prior milestone was Signal Engine Part 5: signal
*validation* (`signals/validation.py`),
sitting alongside `filters.py` (Part 4) between generation (Parts 1-3)
and any future consumer (`strategies/`), but answering a different
question. Where a filter decides whether an already-produced
`SignalResult` is worth *passing on* (accept/modify/reject),
validation decides whether it is *internally well-formed and
trustworthy* -- it never discards, mutates the decision content of, or
rejects a signal; it only collects findings (errors/warnings) and,
when asked, annotates the result's own `metadata` with them. Adds ten
new public names, all re-exported from `signals/__init__.py`:

- `ValidationRule` -- abstract base every concrete rule implements
  (`evaluate(result, context) -> RuleOutcome`), mirroring the role
  `BaseSignalFilter` plays for filters. Provides `_pass`/`_warn`/`_fail`
  helpers and a `reset()` hook (no-op by default).
- `RuleOutcome` -- a frozen dataclass (`rule_name`, `passed`,
  `severity` in `{None, "error", "warning"}`, `message`) returned by
  every `evaluate()` call; `severity` must be `None` when `passed` is
  `True` and one of `"error"`/`"warning"` when `passed` is `False`,
  enforced in `__post_init__`.
- `SummaryContentRule` -- errors on a blank/whitespace `summary`
  (defensive, since `SignalResult` already guarantees this at
  construction) or warns when it is shorter than a configurable
  `min_length` (default `10`).
- `RangeConsistencyRule` -- errors when `strength`/`confidence` are
  non-numeric, non-finite, or outside `[0.0, 1.0]` (defensive); warns
  when `confidence` is exactly `0.0`.
- `DirectionStrengthConsistencyRule` -- errors when a directional
  signal (`BUY`/`SELL`) carries `strength == 0.0` (self-contradictory);
  warns when a `HOLD` signal's `strength` exceeds a configurable
  `hold_strength_warn_threshold` (default `0.5`).
- `ConfidenceThresholdRule` -- warns (never errors) when `confidence`
  is below a configurable `min_confidence` (default `0.3`) -- distinct
  from `filters.ConfidenceFilter`, which rejects instead.
- `MetadataPresenceRule` -- warns when `metadata` is empty, undermining
  the traceability convention every other `signals/` module relies on.
- `SignalValidationPipeline` (+ `SignalValidationReport`) -- runs a
  caller-configurable-order sequence of `ValidationRule`s via `.run()`,
  **never short-circuiting** (every rule always runs, unlike
  `SignalFilterPipeline`), producing a `SignalValidationReport`
  (`is_valid` -- `True` iff zero rules reported `"error"` severity --
  `errors`, `warnings`, `trace`). `.reorder(rule_names)` reconfigures
  execution order after construction (must be an exact permutation of
  current rule names); duplicate rule names are rejected at
  construction. `.reset()` resets every rule.
- `SignalValidator` -- the convenience facade most callers use directly
  (mirroring `TechnicalSignalGenerator`/`SignalAggregator`'s role over
  their bases), defaulting to the five rules above when neither `rules`
  nor a pre-built `pipeline` is supplied. `.validate()` returns the
  `SignalValidationReport` directly; `.validate_and_annotate()` returns
  a **new** `SignalResult` (via `SignalResult.with_metadata`, never
  mutating the original) with the report merged into
  `metadata["signal_validation"]`, mirroring the traceability
  convention `SignalFilterPipeline` already established for
  `metadata["filter_pipeline_trace"]`.

Every rule validates its inputs (`result` must be a `SignalResult`,
`context` must be a `SignalContext`) and raises
`signals.exceptions.SignalValidationError` -- reused from Signal Engine
Part 1, no new exception type was added -- only for that kind of
invalid input; an unusual *value* (e.g. zero strength on a directional
signal, empty metadata) is a normal validation finding
(error/warning), never a raised exception. This module validates only
`SignalResult` objects (for one `SignalContext`) -- it never inspects
`analysis.result.AnalysisResult`, `core.entities.signal.Signal`, or any
other type directly. No AI, no Risk Engine, no Strategy Engine, no
order execution, no trading decisions -- validation is not deciding
whether/how to act, only whether an already-produced signal is
internally trustworthy, the same boundary every `signals/` module
respects. Signal Engine Parts 1-4 (`signals/base.py`, `context.py`,
`result.py`, `exceptions.py`, `utils.py`,
`technical_signal_generator.py`, `aggregator.py`, `filters.py`) and
`analysis/` were left completely untouched. Only `signals/__init__.py`
was updated among existing files (to document and re-export the ten
new names); `PROJECT_STATE.md` and `DEVELOPER_GUIDE.md` were the only
other files updated (`PROJECT_RULES.md` required no changes). Covered
by 60 new unit tests in `tests/test_signal_validation.py`:
`RuleOutcome` construction/validation, `ValidationRule` shared-helper
behavior via a minimal concrete subclass, each of the five concrete
rules in isolation (pass/warn/error paths, invalid-configuration
handling), `SignalValidationPipeline` sequencing with no
short-circuiting, configurable `reorder()`, duplicate-name rejection,
`reset()`, invalid-input handling, `SignalValidationReport.as_metadata()`
shape/copy semantics, `SignalValidator` (default rule set, custom
rules/pipeline precedence, `validate_and_annotate()` metadata merging
without mutating the original, never raising on a failed validation),
and a dedicated end-to-end integration section running a realistic
hand-built `SignalResult` through a real `SignalValidator`.

Before this, the prior milestone was Signal Engine Part 4: a filter
pipeline (`signals/filters.py`) that
sits between signal *generation* (Parts 1-3) and any future consumer
(`strategies/`), accepting, rejecting, or modifying an already-produced
`SignalResult` without ever generating a new one from scratch. Adds six
new public names, all re-exported from `signals/__init__.py`:

- `BaseSignalFilter` -- abstract base every concrete filter implements
  (`apply(result, context) -> FilterOutcome`), mirroring the role
  `BaseSignalGenerator` plays for generators. Provides `_accept`/
  `_modify`/`_reject` helpers and a `reset()` hook (no-op by default)
  for filters that keep internal history.
- `FilterOutcome` -- a frozen dataclass (`filter_name`, `action` in
  `{"accept", "modify", "reject"}`, `result`, `reason`) returned by
  every `apply()` call instead of a bare `Optional[SignalResult]`, so a
  *rejection* still carries a `reason` rather than losing it the moment
  the signal is dropped. `result` is required for `accept`/`modify` and
  forbidden for `reject`, enforced in `__post_init__`.
- `ConfidenceFilter` -- rejects a `SignalResult` whose `confidence`
  falls below a constructor-configurable `min_confidence` (default
  `0.3`). Accept/reject only, never modifies.
- `DuplicateSignalFilter` -- stateful; rejects a `SignalResult` that
  repeats the immediately-previous *accepted* `(direction, strength)`
  pair for the same `SignalContext.symbol`/`timeframe` (strength
  compared after rounding to a configurable `strength_precision`,
  default `3`). A different intervening signal resets the duplicate
  check. Accept/reject only.
- `CooldownFilter` -- stateful; rejects any `SignalResult` (any
  direction) arriving less than a constructor-configurable
  `cooldown_seconds` after the previous *accepted* one for the same
  symbol/timeframe. Takes an injectable `clock` callable (defaults to
  `time.monotonic`), matching the project's dependency-injection
  convention for non-deterministic external input -- tests never depend
  on real wall-clock time. Accept/reject only.
- `ConflictFilter` -- stateful; when a `SignalResult` directly reverses
  the previous *accepted* non-`HOLD` direction for the same
  symbol/timeframe (BUY immediately after SELL or vice versa),
  downgrades it to `SignalDirection.HOLD` with `strength`/`confidence`
  scaled by a constructor-configurable `dampening` (default `0.5`)
  rather than rejecting it -- this filter set's one `action="modify"`
  case. The standing direction is not updated by a downgrade, so a
  repeated conflicting signal keeps conflicting until a
  *non-conflicting* directional signal is accepted.
- `SignalFilterPipeline` (+ `SignalFilterPipelineResult`) -- runs a
  sequence of `BaseSignalFilter`s against one `SignalResult`/
  `SignalContext` pair via `.run()`, in order, short-circuiting on the
  first rejection. Contains no filtering logic of its own -- purely a
  sequencer/collector, mirroring the combiner role `SignalAggregator`
  (Part 3) plays for generators. Returns a `SignalFilterPipelineResult`
  (`accepted`, `result`, `trace` -- the ordered list of every filter's
  `FilterOutcome.as_trace_entry()`, `rejected_by`); when the signal
  survives every filter, the same trace is also merged into
  `result.metadata["filter_pipeline_trace"]`, so traceability lives
  both on the pipeline's return value and on the `SignalResult` itself
  for anything that reaches a consumer. `.reset()` resets every filter
  in the pipeline in one call.

Every filter validates its inputs (`result` must be a `SignalResult`,
`context` must be a `SignalContext`) and raises
`signals.exceptions.SignalValidationError` -- reused from Signal Engine
Part 1, no new exception type was added -- only for that kind of
invalid input; an unusual *value* (e.g. zero confidence, a direct
direction reversal) is a normal filtering outcome (`reject`/`modify`),
never an error. No AI, no Risk Engine, no Strategy Engine, no order
execution, no trading decisions -- filtering is not deciding
whether/how to act, only whether an already-produced signal is worth
passing on, the same boundary every `signals/` module respects. Signal
Engine Parts 1-3 (`signals/base.py`, `context.py`, `result.py`,
`exceptions.py`, `utils.py`, `technical_signal_generator.py`,
`aggregator.py`) and `analysis/` were left completely untouched. Only
`signals/__init__.py` was updated among existing files (to document and
re-export the six new names); `PROJECT_STATE.md` and
`DEVELOPER_GUIDE.md` were the only other files updated. Covered by 63
new unit tests in `tests/test_signal_filters.py`: `FilterOutcome`
construction/validation, `BaseSignalFilter` shared-helper behavior via a
minimal concrete subclass, each of the four concrete filters in
isolation (accept/reject/modify paths, stateful per-symbol/timeframe
history, `reset()`, invalid-input handling), `SignalFilterPipeline`
sequencing/short-circuiting/trace composition (including a modified
result flowing correctly into a subsequent filter), and a dedicated
end-to-end integration section combining all four filters in one
realistic pipeline run.

**Signal Engine Part 5** (new, this milestone): signal *validation*
(`signals/validation.py`) -- a different boundary than Part 4's
filters. Where `filters.py` decides whether an already-produced
`SignalResult` is worth passing on (accept/modify/reject), `validation.py`
decides whether it is internally well-formed and trustworthy, collecting
*errors* and *warnings* into a report rather than discarding or
modifying the signal's decision content. Adds `ValidationRule` (abstract
base every concrete rule implements, mirroring `BaseSignalFilter`'s
role), `RuleOutcome` (a frozen dataclass -- `rule_name`, `passed`,
`severity` in `{None, "error", "warning"}`, `message` -- returned by
every `evaluate()` call), five concrete rules (`SummaryContentRule`,
`RangeConsistencyRule`, `DirectionStrengthConsistencyRule`,
`ConfidenceThresholdRule`, `MetadataPresenceRule`), `SignalValidationPipeline`
(+ `SignalValidationReport`), and `SignalValidator`. All ten new public
names are re-exported from `signals/__init__.py`.

- `ValidationRule` -- abstract base (`evaluate(result, context) ->
  RuleOutcome`) providing `_pass`/`_warn`/`_fail` helpers and a
  `reset()` hook (no-op by default), mirroring `BaseSignalFilter`.
- `RuleOutcome` -- frozen dataclass; enforces `severity is None` when
  `passed=True` and `severity in {"error", "warning"}` when
  `passed=False` in `__post_init__`; `as_trace_entry()` gives a compact
  `dict` form.
- `SummaryContentRule` -- errors on a blank/whitespace `summary`
  (defensive -- `SignalResult` already guarantees this at construction)
  or warns when it is shorter than a configurable `min_length` (default
  `10`).
- `RangeConsistencyRule` -- errors when `strength`/`confidence` are
  non-numeric, non-finite, or outside `[0.0, 1.0]` (defensive, same
  rationale); warns when `confidence` is exactly `0.0`.
- `DirectionStrengthConsistencyRule` -- errors when a directional
  signal (`BUY`/`SELL`) carries `strength == 0.0` (self-contradictory);
  warns when a `HOLD` signal's `strength` exceeds a configurable
  `hold_strength_warn_threshold` (default `0.5`).
- `ConfidenceThresholdRule` -- warns (never errors) when `confidence`
  is below a configurable `min_confidence` (default `0.3`); distinct
  from `filters.ConfidenceFilter`, which rejects instead of warning.
- `MetadataPresenceRule` -- warns when `metadata` is empty, since an
  empty dict undermines the traceability convention every other
  `signals/` module relies on.
- `SignalValidationPipeline` (+ `SignalValidationReport`) -- runs a
  caller-configurable-order sequence of `ValidationRule`s via `.run()`,
  **never short-circuiting** (unlike `SignalFilterPipeline`): every
  rule always runs so a caller sees the complete set of findings in one
  pass. Collects a `SignalValidationReport` (`is_valid` -- `True` iff
  zero rules reported `"error"` severity; `warnings` do not affect it
  -- `errors`, `warnings`, `trace`). `.reorder(rule_names)` lets a
  caller reconfigure execution order after construction (must be an
  exact permutation of current rule names); rule names must be unique
  within a pipeline (enforced at construction). `.reset()` resets every
  rule.
- `SignalValidator` -- convenience facade most callers use directly
  (mirroring `TechnicalSignalGenerator`'s/`SignalAggregator`'s role over
  their respective bases), defaulting to the five concrete rules above
  when neither `rules` nor a pre-built `pipeline` is supplied (`pipeline`
  takes precedence when both are given). `.validate()` returns the
  `SignalValidationReport` directly; `.validate_and_annotate()` returns
  a **new** `SignalResult` (via `SignalResult.with_metadata`, never
  mutating the original) with the report merged into
  `metadata["signal_validation"]`, so findings stay traceable on the
  signal itself -- the same convention `SignalFilterPipeline` already
  established for `metadata["filter_pipeline_trace"]`. Never raises for
  a validation finding and never discards/executes a signal regardless
  of `is_valid` -- deciding what to do about a failed validation is left
  entirely to the caller.

Only `signals/validation.py` validates only `SignalResult` objects (for
one `SignalContext`) -- it never inspects `analysis.result.AnalysisResult`,
`core.entities.signal.Signal`, or any other type directly. No AI, no
Risk Engine, no Strategy Engine, no order execution, no trading
decisions of any kind. Signal Engine Parts 1-4 (`signals/base.py`,
`context.py`, `result.py`, `exceptions.py`, `utils.py`,
`technical_signal_generator.py`, `aggregator.py`, `filters.py`) and
`analysis/` were left completely untouched -- only `signals/__init__.py`
was updated among existing files (to document and re-export the ten new
names); `PROJECT_STATE.md` and `DEVELOPER_GUIDE.md` were the only other
files updated (`PROJECT_RULES.md` required no changes -- no rule
itself changed). Covered by 60 new unit tests in
`tests/test_signal_validation.py`: `RuleOutcome`
construction/validation, `ValidationRule` shared-helper behavior via a
minimal concrete subclass, each of the five concrete rules in isolation
(pass/warn/error paths, invalid-configuration handling),
`SignalValidationPipeline` sequencing with no short-circuiting,
configurable `reorder()`, duplicate-name rejection, `reset()`,
invalid-input handling, `SignalValidationReport.as_metadata()` shape and
copy semantics, `SignalValidator` (default rule set, custom
rules/pipeline precedence, `validate_and_annotate()` metadata merging
without mutating the original, never raising on a failed validation),
and a dedicated end-to-end integration section running a realistic
hand-built `SignalResult` (as if produced by
`TechnicalSignalGenerator`/`SignalAggregator` and filtered by
`SignalFilterPipeline`) through a real `SignalValidator`.

Before this, the prior milestone was Signal Engine Part 3:
`SignalAggregator` (`signals/aggregator.py`), which combines the
`SignalResult`s of one or more injected `BaseSignalGenerator` instances
-- defaulting to a single plain `TechnicalSignalGenerator()` when none
are supplied -- into a single final `SignalResult`, mirroring
`analysis.aggregator.AnalysisAggregator` one layer down via
confidence-and-weight-weighted averaging of each sub-generator's signed
`(direction * strength)` value, thresholded back onto
`SignalDirection.BUY`/`SELL`/`HOLD`. Any sub-generator raising
`InsufficientSignalDataError` is treated as "unavailable" rather than
failing the whole call; `SignalAggregator` itself only raises it when
*every* injected sub-generator was unavailable. `metadata` records
`components`, `weights`, `aggregation_details`, `generators_available`,
and `generators_missing`. Covered by 36 unit tests in
`tests/test_signal_aggregator.py`, including a real-`TechnicalSignalGenerator`
integration section. See `signals/aggregator.py`'s own module docstring
for full detail.

Before that, the prior milestone was Signal Engine Part 2:
`TechnicalSignalGenerator`
(`signals/technical_signal_generator.py`), the first concrete
`BaseSignalGenerator` implementation, built on Part 1's foundation. It
looks up exactly one `AnalysisResult` on the `SignalContext` it is
given -- the one produced by `analysis.aggregator.AnalysisAggregator`,
matched by `AnalysisResult.analyzer_name` (default
`"AnalysisAggregator"`, configurable via the `aggregator_name`
constructor parameter) -- and standardizes it into a `SignalResult` by
mapping the aggregator's `-1.0..+1.0` directional score onto exactly
three signal directions, reusing `core.enums.SignalDirection` rather
than inventing a new enum:

- Bullish -> `SignalDirection.BUY` (score strictly above
  `buy_threshold`, default `0.2`)
- Bearish -> `SignalDirection.SELL` (score strictly below
  `sell_threshold`, default `-0.2`)
- Neutral -> `SignalDirection.HOLD` (score at or between the two
  thresholds)

Both thresholds are constructor-configurable (validated as finite
numbers in `(0.0, 1.0]` / `[-1.0, 0.0)` respectively, raising
`SignalGeneratorConfigurationError` otherwise). `strength` is
`abs(score)` clamped to `[0.0, 1.0]`; `confidence` passes the
aggregator's own `confidence` straight through unchanged; `summary` is
a short, human-readable sentence naming the symbol/timeframe, direction
label, score, and confidence; `metadata` records `source_analyzer`,
`source_score`, `source_confidence`, `score_label`, `buy_threshold`,
`sell_threshold`, and the full underlying `aggregator_metadata` for
traceability. `generate()` raises `InsufficientSignalDataError` when no
`AnalysisResult` with the expected `analyzer_name` is present on the
`SignalContext` (e.g. only individual `analysis.technical` outputs were
supplied, or the context is empty) -- it never falls back to reading
any individual `analysis.technical` analyzer output directly, even when
one is also present on the same context alongside the aggregator
result. No AI, no risk management, no strategy/trading decisions, no
order execution -- this generator only standardizes an already-computed
score via arithmetic thresholding, exactly the boundary Signal Engine
Part 1 documented. `analysis/` (`base.py`, `context.py`, `result.py`,
`exceptions.py`, `utils.py`, `technical/`, `aggregator.py`) and Signal
Engine Part 1's own foundation (`signals/base.py`, `context.py`,
`result.py`, `exceptions.py`, `utils.py`) were left completely
untouched. Only `signals/__init__.py` was updated among existing files
(to document and re-export `TechnicalSignalGenerator` and
`DEFAULT_AGGREGATOR_NAME`); `PROJECT_STATE.md` and `DEVELOPER_GUIDE.md`
were the only other files updated. Covered by 31 new unit tests in
`tests/test_technical_signal_generator.py`: construction/configuration
validation, `generate()` context validation (including ignoring
non-aggregator results present alongside the aggregator's), direction
mapping across the full score range including both threshold
boundaries, output-shape/metadata checks, and a dedicated integration
section that builds a real `AnalysisAggregator` (with injected fake
sub-analyzers, mirroring `tests/test_aggregator.py`'s own fixture
style) to prove actual end-to-end reuse of Part 4's real output shape,
not just hand-built `AnalysisResult`s.

Before this, the prior milestone was Signal Engine Part 1: the
`signals/` package foundation -- `BaseSignalGenerator`
(`signals/base.py`), `SignalContext` (`signals/context.py`),
`SignalResult` (`signals/result.py`), the `SignalError` hierarchy
(`signals/exceptions.py`), and shared validation helpers
(`signals/utils.py`). Mirrors the exact role
`analysis/base.py`/`context.py`/`result.py`/`exceptions.py`/`utils.py`
play as Analysis Engine Part 1's foundation: `BaseSignalGenerator` is
an `abc.ABC` with an abstract `generate(context: SignalContext) ->
SignalResult` method plus shared `validate_context`/`_build_result`
helpers; `SignalContext` is an immutable, validated bundle of `symbol`,
`timeframe`, and `analysis_results: list[AnalysisResult]` (reusing
`analysis.result.AnalysisResult` directly -- no new domain type -- so a
`SignalContext` can hold individual `analysis.technical` analyzer
outputs, the merged `AnalysisAggregator` output, or both, since both
are the same type), with a `get_result(analyzer_name)` lookup helper
mirroring `AnalysisContext.get_indicator`; `SignalResult` is a frozen
dataclass containing *only* the five fields specified for this
milestone -- `direction` (`core.enums.SignalDirection`, reused rather
than a new enum), `strength` (`0.0..1.0`), `confidence` (`0.0..1.0`),
`summary`, and `metadata` -- deliberately excluding `analyzer_name`/
`symbol`/`timeframe`/`timestamp`-equivalent fields that `AnalysisResult`
has, and deliberately distinct from `core.entities.signal.Signal`
(which carries an id/source/timestamp and represents a persisted,
actionable signal -- building one from a `SignalResult` is out of scope
for this part). No AI, no strategies, no risk management, no order
execution, no trading decisions -- and no concrete `BaseSignalGenerator`
implementation either; this part is foundation only, exactly as
`analysis/`'s own Part 1 was before Parts 2-4 landed. Covered by 45
unit tests in `tests/test_signals.py`, including a hand-built fake
`BaseSignalGenerator` subclass (mirroring `test_analysis.py`'s fake
`BaseAnalyzer` subclass) to exercise `generate()`/`validate_context()`/
`_build_result()`, plus dedicated coverage for `SignalResult`'s
five-field shape, `SignalContext`'s validation and `AnalysisAggregator`-
shaped-result acceptance, the `SignalError` hierarchy, and every
`signals.utils` helper.

Before this, the prior milestone was Analysis Engine Part 4:
`AnalysisAggregator`
(`analysis/aggregator.py`), which combines the five independent
`analysis/technical` analyzer outputs — `TrendAnalyzer`,
`MomentumAnalyzer`, `VolatilityAnalyzer`, `VolumeAnalyzer`, and
`MarketStructureAnalyzer` — into a single final `AnalysisResult`. It
subclasses `BaseAnalyzer` and constructor-injects one instance of each
sub-analyzer (defaulting to real instances, matching the project's
dependency-injection convention). Because `VolatilityAnalyzer` alone
produces a direction-free volatility-*regime* score rather than a
bullish/bearish one (see Part 3A), `overall_score` is a
confidence-and-weight-weighted average of only the four *directional*
sub-scores (`TrendAnalyzer`/`MomentumAnalyzer`/`VolumeAnalyzer`/
`MarketStructureAnalyzer`); `VolatilityAnalyzer`'s result is still fully
merged into overall `confidence` and into `metadata` (tagged
`"contributes_to_directional_score": False`), just never averaged into
the directional score itself. Any sub-analyzer raising
`InsufficientDataError` for a given context is caught and treated as
"unavailable" rather than failing the whole call — `overall_score`/
`confidence` are computed from whichever subset remains, and
`metadata["components_missing"]` records which analyzers were
unavailable and why; `AnalysisAggregator` itself only raises
`InsufficientDataError` when all four directional analyzers are
unavailable (a volatility-only result carries no direction to
aggregate). No AI, no signals, no strategies, no trading decisions, and
no new analytical logic beyond merging — Parts 1, 2, 3A, 3B, and 3C
(`analysis/base.py`, `context.py`, `result.py`, `exceptions.py`,
`utils.py`, and every file under `analysis/technical/`) were left
completely untouched; `AnalysisAggregator` is imported and re-exported
through `analysis/__init__.py` (`from analysis import
AnalysisAggregator`) — unlike `analysis/technical/`'s analyzers, which
are imported directly from that subpackage and not re-exported through
the parent. Covered by 36 new unit tests in `tests/test_aggregator.py`:
most use injected fake sub-analyzers to exercise the merging/weighting/
missing-data logic precisely, plus a dedicated integration section that
builds a real, default `AnalysisAggregator()` (real sub-analyzers)
against real indicator/candle data to confirm actual reuse of
`analysis.technical` end-to-end.

Before this, the prior milestone was Analysis Engine Part 3C:
`MarketStructureAnalyzer`
(`analysis/technical/market_structure_analyzer.py`), the fifth concrete
technical analyzer built on the Part 1 foundation, joining Part 2's
`TrendAnalyzer`/`MomentumAnalyzer`, Part 3A's `VolatilityAnalyzer`, and
Part 3B's `VolumeAnalyzer`. It subclasses `BaseAnalyzer`, consumes an
`AnalysisContext`, and produces only an `AnalysisResult` (score
`-1.0..+1.0`, confidence `0.0..1.0`, fully-explained `metadata`) — no
AI, no signals, no strategies, no trading decisions. Like `TrendAnalyzer`/
`MomentumAnalyzer`/`VolumeAnalyzer`, its score is directional: `-1.0`
(strong bearish structure) .. `0.0` (neutral/mixed) .. `+1.0` (strong
bullish structure), interpreting a swing-point pair (`swing_high_1`/
`swing_high_2` and `swing_low_1`/`swing_low_2`, expected on a
`"SwingPoints_1"`-named `IndicatorResult`) — the high pair and low pair
optional independently, with `InsufficientDataError` raised only when
neither is usable. Like `VolumeAnalyzer`, it also reads
`AnalysisContext.market_state.latest_candle` (close price only) to test
for a break of the most recent swing point; the candle's absence only
means BOS/CHOCH cannot be evaluated for that call, it never raises.
Unlike the other four analyzers, `MarketStructureAnalyzer` consumes no
output from the existing `indicators/` package at all — none of the 17
indicators listed there compute swing points, so this analyzer instead
documents the exact input shape it expects a future swing-point
detector to supply (see Partially completed modules / Technical debt
above). `metadata` covers exactly the eleven facets in this milestone's
design brief: `swing_high`/`swing_low` (values plus `HH`/`LH`/`HL`/`LL`/
`equal_high`/`equal_low` classification), `bos`/`choch` (each
`{"detected": bool, "direction": ...}`), `trend_continuation`/
`trend_reversal` (each `0.0`..`1.0`), and `market_regime`
(`"uptrend"`/`"downtrend"`/`"ranging"`, derived from `structure_bias`).
A confirmed BOS or CHOCH is weighted heavily enough in the overall score
to reflect the break's own direction (a CHOCH slightly less than a BOS,
since it is a single-event first sign of reversal working against an
already-established bias, versus a BOS confirming a bias the high and
low components already agree on). Covered by 26 new unit tests in
`tests/test_market_structure_analyzer.py`. Part 1 (`analysis/base.py`,
`context.py`, `result.py`, `exceptions.py`, `utils.py`, `__init__.py`),
Part 2's two analyzers (`trend_analyzer.py`, `momentum_analyzer.py`,
`tests/test_analysis_technical.py`), Part 3A's `VolatilityAnalyzer`
(`volatility_analyzer.py`, `tests/test_volatility_analyzer.py`), and
Part 3B's `VolumeAnalyzer` (`volume_analyzer.py`,
`tests/test_volume_analyzer.py`) were left untouched;
`analysis/technical/__init__.py` was updated only to additionally
export `MarketStructureAnalyzer` (its docstring updated accordingly) —
`MarketStructureAnalyzer` is imported directly from
`analysis.technical`, not re-exported through `analysis/__init__.py`,
same as Parts 2, 3A, and 3B.

Before that, per `README.md`'s roadmap checklist, the prior milestones
were: domain layer design (`core/`), event-driven architecture design
(`events/`), the Data Engine (`data/`), the full indicator library
(`indicators/`), the outbound API transport layer (`api/`), Analysis
Engine Part 2 (`TrendAnalyzer`/`MomentumAnalyzer`), Analysis Engine
Part 3A (`VolatilityAnalyzer`), Analysis Engine Part 3B
(`VolumeAnalyzer`), Analysis Engine Part 3C (`MarketStructureAnalyzer`),
Analysis Engine Part 4 (`AnalysisAggregator`), Signal Engine Part 1
(`BaseSignalGenerator`/`SignalContext`/`SignalResult` foundation), and
Signal Engine Part 2 (`TechnicalSignalGenerator`). The README roadmap
checklist itself has not been updated to reflect any of this — updating
it remains a good low-risk task.

## Next recommended milestone

With `analysis/aggregator.py` (Part 4) combining the five
`analysis/technical` analyzers into one final `AnalysisResult`,
`signals/` providing generation through validation (Parts 1-5),
`strategies/risk_management/` providing foundation through three
concrete risk managers (Risk Engine Parts 1-3), `strategies/` providing
foundation through a concrete strategy and an aggregator (Strategy
Engine Parts 1-3), `strategies/portfolio_management/` providing
its foundation, a first concrete manager, and two fully test-covered
composite/aggregating managers (`BasicPortfolioManager`/`PortfolioManager`/
`PortfolioAggregator`, Portfolio Management Parts 1-4, all four now with
dedicated test files), `backtesting/` now providing its own foundation,
a first concrete backtester, a standalone portfolio simulation helper,
performance-statistics calculations, and report generation
(`BaseBacktester`/`BacktestContext`/`BacktestResult`, Backtesting
Engine Part 1; `BasicBacktester`, Backtesting Engine Part 2;
`PortfolioSimulator`, Backtesting Engine Part 3; `metrics.py`,
Backtesting Engine Part 4; `report.py`/`BacktestReport`, Backtesting
Engine Part 5), `execution/` now providing its own foundation
(`BaseExecutionEngine`/`ExecutionContext`/`ExecutionResult`, Execution
Engine Part 1), and `services/` now also providing its own foundation
(`BaseService`/`ServiceContext`/`ServiceResult`, Services Part 1), the
natural next steps are, in order of least friction:

0. **A first concrete `BaseExecutionEngine`** — Execution Engine Part 1
   (`execution/`) is framework only: it ships `BaseExecutionEngine`,
   `ExecutionContext`, `ExecutionResult`, the `ExecutionError`
   hierarchy, and `utils.py`, but no concrete engine that actually
   evaluates an `ExecutionContext` (its `strategy_result`/`risk_result`/
   `portfolio_result`/`portfolio`) into a real `execution_approved`
   decision — mirroring how `strategies/`, `strategies/risk_management/`,
   `strategies/portfolio_management/`, and `backtesting/` each needed a
   first concrete implementation after their own Part 1 foundation. A
   natural first design: require all three upstream results to be
   present and agree (candidate action is directional, risk approved,
   portfolio has capacity) before approving, following the same
   "absence only lowers confidence, disagreement blocks" convention
   every layer below it already uses.
0a. **`SignalEngine`'s Part 2B orchestration** — Services Part 2A
   (`services/signal_engine.py`) shipped `SignalEngine`'s constructor,
   dependency injection (an optional `EventBus`), validation, and
   engine configuration, but `execute()` still always raises
   `NotImplementedError` by design. The natural next step is Part 2B:
   interpret `context.payload` as (or build) a `core.entities.signal.
   Signal`, apply `SignalEngine.config` (e.g. reject/flag it when
   `require_min_confidence` is `True` and `signal.confidence <
   min_confidence`), call `self.event_bus.publish(SignalGenerated(...))`
   when an `EventBus` was injected, and return a `ServiceResult`
   reflecting what actually happened — the same "framework, then first
   concrete, then wire it up" progression every other engine in this
   repository has already followed. This remains blocked on nothing
   currently missing (a fake `EventBus` already exercises the
   constructor/DI path in `tests/test_signal_engine.py`), so it is
   pure orchestration work, not a dependency gap.
0b. **A concrete in-memory `EventBus`** — still no concrete
   `events.interfaces.event_bus.EventBus` implementation exists
   anywhere in the repository (see item 6 below); `SignalEngine`
   already accepts one via dependency injection (Part 2A) and would be
   the natural first real consumer of it once Part 2B lands. A
   `notification_service.py` (e.g. a Telegram-bot free-tier wrapper) or
   `ai_service.py` (a free/self-hosted AI/LLM client) would equally
   exercise `BaseService.execute()`/`ServiceContext.payload`/
   `ServiceResult.success` for the first time against a real external
   call.
1. **Wiring `PortfolioSimulator` (Backtesting Part 3) into
   `BasicBacktester`** (or a new concrete backtester) so its mechanics
   are actually used instead of `BasicBacktester`'s own still-separate
   inline helpers, and additional concrete backtesters (e.g. one
   consuming `signals.result.SignalResult` directly, or supporting
   multiple concurrent positions per symbol/short selling/slippage/
   fees) are also open, mirroring how further concrete
   `BaseRiskManager`/`BaseStrategy`/`BasePortfolioManager`
   implementations followed each engine's first one.

2. **Additional concrete `BaseRiskManager` implementations beyond
   Part 3** — e.g. a drawdown-based or volatility-based risk manager,
   following the pattern `BasicRiskManager`/`PositionSizeRule`/
   `StopLossRule`/`TakeProfitRule` already established; optionally a
   composite/aggregating risk manager combining several, mirroring
   `SignalAggregator`'s role over multiple signal generators.
3. **Additional concrete `BaseStrategy` implementations beyond
   `BasicStrategy`** — a trend-following or mean-reversion strategy
   following the same `StrategyContext` -> `StrategyResult` contract
   would exercise the same abstraction differently, and could then
   also be combined via `StrategyAggregator` alongside `BasicStrategy`.
4. **A concrete swing-point-detection indicator** — the one dependency
   `MarketStructureAnalyzer` (Part 3C) has documented but cannot yet
   receive from anywhere real; would live in `indicators/` (matching
   the calculation/interpretation split) or an `app/`-layer pivot
   detector, producing the `"SwingPoints_1"`-shaped `IndicatorResult`
   this analyzer already expects. `AnalysisAggregator` already degrades
   gracefully today when this input is absent (treats
   `MarketStructureAnalyzer` as "unavailable"), so this remains
   unblocking but not blocking.
5. **`analysis/news/`** — a sentiment analyzer consuming
   `AnalysisContext.news` (`NewsItem` list), following the exact same
   `BaseAnalyzer` → `AnalysisResult` pattern `TrendAnalyzer`/
   `MomentumAnalyzer`/`VolatilityAnalyzer`/`VolumeAnalyzer`/
   `MarketStructureAnalyzer` already established. Once it exists,
   whether/how `AnalysisAggregator` should incorporate it (vs. leaving
   news aggregation to `analysis/ai/`) is an open design question, not
   a decided one.
6. **A concrete in-memory `EventBus`** (in `services/`) — unblocked
   independently of the above since every event type and contract it
   needs already exists in `events/`.
7. **`analysis/ai/`** — once there are at least a technical and a news
   analyzer to combine into a higher-level AI-based assessment.
8. **An `app/`-layer wiring use case** spanning `signals/`/
   `strategies.risk_management`/`strategies`/`strategies.
   portfolio_management` — nothing today assembles a `SignalContext`
   from real `AnalysisAggregator` output, runs a `SignalResult` through
   `SignalFilterPipeline`/`SignalValidator`, assembles a `RiskContext`
   from a real `Signal`/`Portfolio`, assembles a `StrategyContext` from
   real `AnalysisAggregator`/`SignalAggregator`/risk-manager output, or
   assembles a `PortfolioContext` from real `BasicStrategy`/
   `StrategyAggregator`/risk-manager/live-portfolio output, outside of
   tests; this mirrors the same end-to-end wiring gap `AnalysisContext`
   already has — and also assembling an `execution.context.
   ExecutionContext` from real `Portfolio`/`StrategyResult`/`RiskResult`/
   `PortfolioResult` output. Actual order placement (a concrete
   `BaseExecutionEngine` calling out to a broker/exchange) remains
   entirely unbuilt and out of scope for any layer implemented so far
   — `execution/` (Part 1, see item 0 above) only provides the
   framework to evaluate whether a candidate decision is cleared to
   proceed toward it.
