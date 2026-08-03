<!--
PROJECT_RULES.md
-----------------
Purpose: A single, authoritative reference for how MarketMind-AI is built —
architecture, folder structure, naming, dependency, coding, testing,
integration, and repository-workflow rules. This file consolidates rules
already established in `docs/ARCHITECTURE.md` and `DEVELOPER_GUIDE.md`
(both remain the more detailed, narrative sources) into one checklist-style
reference. If this file and one of those ever disagree, treat it as drift
to be fixed, not as license to pick whichever is convenient — reconcile
them and update whichever is stale.
-->

# MarketMind-AI — Project Rules

## 1. Architecture

MarketMind-AI follows a **Clean Architecture** layout: business rules live
in the center (`core/`) and know nothing about frameworks or external
services; outer layers depend inward, never the reverse.

Guiding principles:

1. **Dependency Rule** — inner layers never import outer layers. `core/`
   imports nothing project-internal (not even `config/`); every other
   package may only import what the dependency table in Section 4 allows.
2. **Interfaces over implementations** — outer layers implement
   interfaces/protocols defined in `core/interfaces/`, so implementations
   (e.g. exchange, AI provider) can be swapped without touching `core/`.
3. **Free-first** — every dependency/integration targets a free tier or
   open-source tool (Binance public API, SQLite, pytest, free/local NLP or
   LLM). Never introduce a paid service or key as a hard dependency.
4. **Separation of calculation vs. interpretation vs. decision** —
   `indicators/` only calculates numbers; `analysis/` interprets those
   numbers (and news) into scored `AnalysisResult` insights; `signals/`
   standardizes one or more `AnalysisResult`s into a common `SignalResult`
   (via `BaseSignalGenerator`) and may filter/aggregate those signals;
   `strategies/` turns signals into trading decisions. Never collapse two
   of these responsibilities into one package.
5. **Backtesting is a consumer, never a strategy author** —
   `backtesting/` replays historical data through whatever
   strategy/signals it is given and reports results; it must never define
   trading rules of its own.
6. **API is the outermost adapter (for its inbound-REST role)** — the
   future inbound REST surface in `api/` may only call into `app/` use
   cases, never directly into `core`, `data`, `analysis`, etc. (`api/`'s
   existing outbound-transport role — `http_client.py`, `providers/` — is
   unrelated to this rule; see Section 5.)

## 2. Folder structure

| Layer | Folder | Depends on | Responsibility |
|---|---|---|---|
| Domain | `core/` | nothing | Entities, interfaces, business rules |
| Events | `events/` | `core` | Event types & pub/sub contracts |
| Data Access | `data/` | `core`, `events`, `config` | Market data acquisition & normalization |
| Persistence | `database/` | `core` | Storing/retrieving data (SQLite by default) |
| Indicators | `indicators/` | `core`, `events` | Pure technical indicator calculations |
| Analysis | `analysis/` | `core`, `data`, `indicators`, `events` | Technical / news / AI analysis |
| ML Models | `models/` | `core` | Training & inference for ML models |
| Signals | `signals/` | `core`, `analysis`, `events` | Standardized signal representation, aggregation & filtering |
| Strategies | `strategies/` | `core`, `analysis`, `signals`, `events` | Turning analysis/signals into trading decisions |
| Backtesting | `backtesting/` | `core`, `data`, `strategies`, `signals` | Simulating strategies against historical data |
| External Services | `services/` | `core`, `events` | Notifications, AI clients, schedulers, event bus implementation |
| Application | `app/` | all of the above | Orchestrates use cases |
| API | `api/` (inbound REST, future) | `app` only | HTTP interface exposing the application |
| API | `api/` (outbound transport, existing) | nothing project-internal (leaf) | `http_client.py`, `providers/` |
| Configuration | `config/` | nothing | Typed settings & constants |
| Utilities | `utils/` | nothing | Generic, reusable helpers |
| Logs | `logs/` | nothing (runtime output) | Local log file storage, not a Python package |
| Tests | `tests/` | mirrors all layers | Automated tests, flat directory |

Test files live flat in `tests/`, named `test_<module_or_component>.py`,
one per implemented module/component — no subdirectory nesting mirroring
package structure. See `docs/ARCHITECTURE.md` for the full narrative
description and the planned data-flow diagram.

## 3. Naming conventions

- Package names are lowercase, singular-concept nouns describing the
  layer's responsibility (`core`, `events`, `data`, `indicators`,
  `analysis`, `signals`, `strategies`, `backtesting`, `services`, `app`,
  `api`, `models`, `database`, `config`, `utils`).
- Class names are `PascalCase` and describe the concrete thing (`Candle`,
  `DataValidator`, `HistoricalDataDownloader`, `SMA`, `HTTPClient`,
  `BaseAnalyzer`, `AnalysisContext`, `AnalysisResult`, `SignalResult`,
  `SignalFilterPipeline`).
- Interfaces/abstract base classes are named for the *role* they play, not
  suffixed with "Interface" or "Abstract" except where an interface and
  its real implementation would otherwise collide in the same file (e.g.
  `BinanceClientInterface` vs. `BinanceRESTClient` in `data/client.py`).
- File names are `snake_case` and mirror the primary class they contain,
  singular (`market_data_provider.py` → `MarketDataProvider`, `signal.py`
  → `Signal`, `candle_closed.py` → `CandleClosed`).
- Event type classes are named `<Noun><PastTenseVerb>` or
  `<Noun><PastParticiple>` describing something that already happened
  (`CandleClosed`, `SignalGenerated`, `PositionOpened`,
  `AIAnalysisCompleted`).
- Exception classes end in `Error` and live in a per-package
  `exceptions.py`, forming a small hierarchy rooted in a package-level
  base error (e.g. `SignalError` → `SignalValidationError`,
  `SignalGeneratorConfigurationError`).
- Test files are named `test_<module_or_component>.py`.

## 4. Dependency rules (quick reference)

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
| `services/` | `core`, `events` |
| `app/` | all of the above |
| `api/` (inbound REST, future) | `app` only |

If a needed import isn't in this table for the package being edited,
that's a signal the code belongs in a different package, or the
abstraction needs to move to `core/`.

## 5. Coding standards

- **Every module opens with a module-level docstring** stating its
  Purpose (and, for packages, Contents / Planned contents).
- **`from __future__ import annotations`** at the top of essentially
  every module, for forward-compatible type hints.
- **Type hints are mandatory** on public functions/methods, including
  return types (project targets Python 3.12 but keeps `typing` imports
  explicit rather than relying only on builtin generics).
- **Docstrings use NumPy-style sections** (`Parameters`, `Returns`,
  `Raises`, etc.) for non-trivial classes/functions.
- **Immutability by default.** Entities are frozen dataclasses unless
  they represent evolving state. Only `Position` and `Portfolio` are
  mutable in `core/entities/` — everything else (candles, tickers,
  trades, signals, indicator results, news items, market state
  snapshots, `SignalResult`, `FilterOutcome`) is a frozen, point-in-time
  value object.
- **Abstract contracts use `abc.ABC` + `@abstractmethod`**, not
  `typing.Protocol`.
- **Dependency injection over hard-wiring.** External I/O (HTTP clients,
  databases) and non-deterministic inputs (e.g. wall-clock time) are
  injected via constructor parameters, defined against an abstract
  interface or a simple injectable callable, so tests never require real
  network access or real time passage (e.g. `BinanceClientInterface` in
  `data/client.py`; the injectable `clock` in `signals.filters.CooldownFilter`).
- **No trading logic in scaffold/stub packages** until their real
  implementation milestone is reached.

## 6. Dependency rules for third-party packages

- Only free-tier or open-source dependencies (see Section 1, principle 3).
- New third-party dependencies are pinned in `requirements.txt`.
- No paid API, paid database, or paid AI service as a hard dependency.

## 7. Testing rules

- Test framework: **pytest** is the project standard (pinned in
  `requirements.txt`), though most existing tests are written to also run
  under the standard-library `unittest` runner with zero third-party
  dependencies — only `test_core_domain.py` and `test_events.py`
  currently require `pytest` specifically.
- Test files live flat in `tests/`, named `test_<component>.py`, one per
  implemented module/component (mirrors the package it tests, not a
  nested directory tree).
- Shared fakes/helpers (e.g. `FakeBinanceClient`) live in
  `tests/helpers.py` — reuse these instead of writing a new fake per test
  file.
- No real network access in tests. External I/O is faked via dependency
  injection against the relevant `core`/`data` interface.
- Run the full suite with either:
  ```bash
  pytest
  # or, dependency-free:
  python3 -m unittest discover -s tests -p "test_*.py" -v
  ```
- New modules must ship with tests in the same change — an implementation
  without a corresponding `tests/test_<name>.py` is incomplete.

## 8. Integration rules

Before considering any new module "done" and merged:

- [ ] Module docstring present (Purpose / Contents / Planned contents).
- [ ] Only imports packages allowed by the dependency table (Section 4).
- [ ] Implements/extends the correct existing `core`/`events`/`analysis`/
      `signals` abstraction rather than inventing a parallel one.
- [ ] External I/O is interface-based and dependency-injected; a fake is
      available for tests (added to `tests/helpers.py` if reusable).
- [ ] Type hints on all public functions/methods, including returns.
- [ ] Tests added in `tests/test_<name>.py`; full suite still passes.
- [ ] All new/changed files byte-compile cleanly
      (`python3 -m py_compile <files>`).
- [ ] No paid service/dependency introduced.
- [ ] No change to an existing frozen entity's mutability or an existing
      interface's method signature, unless that is the explicit,
      deliberate goal of the change.
- [ ] `docs/ARCHITECTURE.md` updated if layer responsibilities or
      dependencies changed; a new `docs/<MODULE>.md` added if the module
      is substantial.
- [ ] `README.md` roadmap checklist, `PROJECT_STATE.md`, and (when
      architecture rules/conventions/reusable abstractions themselves
      change) `DEVELOPER_GUIDE.md` updated to reflect the new state.
- [ ] `PROJECT_RULES.md` (this file) updated if a rule itself changed —
      not for routine feature work.

**What must never be changed** without a deliberate, documented, repo-wide
decision:

- The Dependency Rule direction (inner layers never import outer layers).
- `core/`'s zero-dependency status.
- Frozen entities' immutability (other than `Position`/`Portfolio`).
- `indicators/`'s purity — stateless calculations only, no trading logic.
- `backtesting/`'s consumer-only role — never defines trading rules.
- The free-first constraint.
- Existing public interfaces in `core/interfaces/` and
  `events/interfaces/` — treat as append-only.
- The Data Engine's tested behavior in `data/` — its public API is not
  refactored without updating every consumer and test.
- Anything explicitly requested by task instructions in a given session
  (e.g. "do not modify existing functionality" takes precedence over
  convenience refactors).

## 9. Repository workflow

- Work proceeds milestone-by-milestone (e.g. "Signal Engine Part N");
  each milestone is scoped to one package or one clearly-bounded piece of
  a package, implemented with its own tests, and documented before the
  next milestone starts.
- A milestone that only adds new files/behavior (no edits to existing
  logic) should leave prior modules' source untouched — only the
  package's `__init__.py` (to document and re-export new names) and the
  project-level docs (`PROJECT_STATE.md`, `DEVELOPER_GUIDE.md`, and this
  file when a rule itself changes) are updated alongside it.
- `PROJECT_STATE.md` is the point-in-time implementation snapshot —
  updated at the end of any milestone that changes what's completed,
  partial, or remaining, including current test counts and compile
  status.
- `DEVELOPER_GUIDE.md` changes only when architecture rules, conventions,
  or reusable abstractions themselves change — not for routine feature
  work.
- Before merging changes from any secondary/updated repository into the
  primary one: compare both trees, preserve everything already
  implemented in the primary repository, integrate every valid change
  from the secondary one, never overwrite newer code with older code,
  never duplicate modules, never redesign the architecture, and never
  remove existing functionality. Re-run the full compile check, import
  verification, and test suite after merging, and update
  `PROJECT_STATE.md`/`DEVELOPER_GUIDE.md` to reflect the merged state.
