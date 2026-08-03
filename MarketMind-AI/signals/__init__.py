"""
signals package
------------------
Purpose:
    Defines the standardized representation of a scored "signal" (i.e.
    direction, strength, and confidence, with supporting metadata),
    produced by standardizing one or more `analysis.result.AnalysisResult`
    outputs from `analysis/` -- WITHOUT deciding what to actually do about
    them (that decision belongs to `strategies/`).

    This package sits between `analysis/` (which scores market data) and
    `strategies/` (which will decide what to do with a signal, such as
    opening a position or sizing risk). Keeping signal standardization
    separate from strategy logic makes it easy to combine signals from
    multiple analyzers/generators later (e.g. an ensemble/voting system)
    without changing either layer.

Contents (Signal Engine Part 1 -- foundation only):
    - base.py: `BaseSignalGenerator`, the abstract base every concrete
      signal generator implements.
    - context.py: `SignalContext`, the immutable bundle of one or more
      `analysis.result.AnalysisResult`s (+ symbol, timeframe) a generator
      consumes.
    - result.py: `SignalResult`, the standardized output every generator
      produces (`direction`, `strength`, `confidence`, `summary`,
      `metadata`).
    - exceptions.py: the `SignalError` hierarchy.
    - utils.py: shared validation helpers used across the package.

Also contains (Signal Engine Part 2 -- first concrete generator):
    - technical_signal_generator.py: `TechnicalSignalGenerator`, which
      standardizes the merged `analysis.aggregator.AnalysisAggregator`
      output for one symbol/timeframe into a `SignalResult`, mapping its
      `-1.0..+1.0` directional score onto exactly three signal
      directions -- Bullish (`SignalDirection.BUY`), Bearish
      (`SignalDirection.SELL`), Neutral (`SignalDirection.HOLD`) --
      reusing `core.enums.SignalDirection` rather than inventing a new
      enum. It consumes only the `AnalysisResult` produced by
      `AnalysisAggregator` (identified by `analyzer_name`), never the
      individual `analysis.technical` analyzer outputs directly, and
      never modifies `analysis/`.

Also contains (Signal Engine Part 3 -- signal aggregation):
    - aggregator.py: `SignalAggregator`, which combines the
      `SignalResult`s of one or more injected `BaseSignalGenerator`
      instances (defaulting to a single `TechnicalSignalGenerator` when
      none are supplied) into one final `SignalResult`, via
      confidence-and-weight-weighted averaging of each component
      signal's signed direction/strength. Any injected generator raising
      `InsufficientSignalDataError` is treated as unavailable rather
      than failing the whole aggregation; `SignalAggregator` itself only
      raises `InsufficientSignalDataError` when none of them produced a
      usable signal. Mirrors `analysis/aggregator.py`'s
      `AnalysisAggregator` one layer down. Does not modify Signal
      Engine Parts 1 or 2.

Also contains (Signal Engine Part 4 -- signal filtering):
    - filters.py: `BaseSignalFilter` (the abstract base every concrete
      filter implements) plus four concrete filters --
      `ConfidenceFilter` (rejects low-confidence signals),
      `DuplicateSignalFilter` (rejects a signal repeating the previous
      accepted (direction, strength) for the same symbol/timeframe),
      `CooldownFilter` (rejects a signal arriving too soon after the
      previous accepted one for the same symbol/timeframe), and
      `ConflictFilter` (downgrades a signal that directly reverses the
      previous accepted direction to `SignalDirection.HOLD` rather than
      rejecting it -- the filter set's one `action="modify"` case) --
      plus `SignalFilterPipeline`, which runs a sequence of these
      filters against one `SignalResult`/`SignalContext`,
      short-circuiting on the first rejection. Every filter returns a
      `FilterOutcome` (`action` + `reason`, never a bare
      `SignalResult`), so a decision's reasoning is preserved even when
      a signal is rejected; the full sequence of outcomes is both
      returned as `SignalFilterPipelineResult.trace` and, for a
      surviving signal, merged into its own
      `metadata["filter_pipeline_trace"]`. Filters are independent of
      each other -- `SignalFilterPipeline` only sequences them and
      collects outcomes, mirroring the combiner role `SignalAggregator`
      (Part 3) plays for generators. Does not modify Signal Engine
      Parts 1-3.

Also contains (Signal Engine Part 5 -- signal validation):
    - validation.py: `ValidationRule` (the abstract base every concrete
      validation rule implements) plus five concrete rules --
      `SummaryContentRule`, `RangeConsistencyRule`,
      `DirectionStrengthConsistencyRule`, `ConfidenceThresholdRule`,
      `MetadataPresenceRule` -- plus `SignalValidationPipeline`, which
      runs a caller-configurable-order sequence of these rules against
      one `SignalResult`/`SignalContext`, never short-circuiting (every
      rule always runs), collecting a `SignalValidationReport`
      (`is_valid`/`errors`/`warnings`/`trace`); plus `SignalValidator`,
      a convenience facade defaulting to a sensible built-in rule set,
      whose `validate_and_annotate()` merges the report into a new
      `SignalResult`'s own ``metadata["signal_validation"]`` for
      traceability. Distinct from `filters.py` (Part 4): validation
      never accepts/rejects/modifies a signal -- it only reports
      findings and annotates metadata, leaving any resulting decision
      to the caller. Does not modify Signal Engine Parts 1-4.

No AI, no strategies, no risk management, no order execution, and no
trading decisions are implemented here or planned for this package --
this package only standardizes analysis output into a common,
lightweight signal shape (and validates/filters it). Turning a
`SignalResult` into an actual trading decision (or into a persisted
`core.entities.signal.Signal`) is the responsibility of the future
`strategies/` package.
"""

from __future__ import annotations

from signals.aggregator import SignalAggregator
from signals.base import BaseSignalGenerator
from signals.context import SignalContext
from signals.exceptions import (
    InsufficientSignalDataError,
    InvalidSignalContextError,
    SignalError,
    SignalGeneratorConfigurationError,
    SignalValidationError,
)
from signals.filters import (
    BaseSignalFilter,
    ConfidenceFilter,
    ConflictFilter,
    CooldownFilter,
    DuplicateSignalFilter,
    FilterOutcome,
    SignalFilterPipeline,
    SignalFilterPipelineResult,
)
from signals.result import SignalResult
from signals.technical_signal_generator import (
    DEFAULT_AGGREGATOR_NAME,
    TechnicalSignalGenerator,
)
from signals.validation import (
    ConfidenceThresholdRule,
    DirectionStrengthConsistencyRule,
    MetadataPresenceRule,
    RangeConsistencyRule,
    RuleOutcome,
    SignalValidationPipeline,
    SignalValidationReport,
    SignalValidator,
    SummaryContentRule,
    ValidationRule,
)

__all__ = [
    "BaseSignalGenerator",
    "SignalContext",
    "SignalResult",
    "SignalError",
    "SignalValidationError",
    "InvalidSignalContextError",
    "InsufficientSignalDataError",
    "SignalGeneratorConfigurationError",
    "TechnicalSignalGenerator",
    "DEFAULT_AGGREGATOR_NAME",
    "SignalAggregator",
    "BaseSignalFilter",
    "FilterOutcome",
    "ConfidenceFilter",
    "DuplicateSignalFilter",
    "CooldownFilter",
    "ConflictFilter",
    "SignalFilterPipeline",
    "SignalFilterPipelineResult",
    "ValidationRule",
    "RuleOutcome",
    "SummaryContentRule",
    "RangeConsistencyRule",
    "DirectionStrengthConsistencyRule",
    "ConfidenceThresholdRule",
    "MetadataPresenceRule",
    "SignalValidationPipeline",
    "SignalValidationReport",
    "SignalValidator",
]
