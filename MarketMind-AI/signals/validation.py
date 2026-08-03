"""
signals/validation.py

Defines Signal Engine Part 5: signal *validation* -- a small, independent
system of rules that inspect an already-produced `SignalResult` (Parts
1-3: `BaseSignalGenerator`, `TechnicalSignalGenerator`, `SignalAggregator`)
and, optionally, an already-filtered one (Part 4: `SignalFilterPipeline`)
for internal consistency and quality, collecting *errors* and *warnings*
rather than accepting/rejecting/modifying the signal itself.

This is deliberately a different boundary than `signals/filters.py`:

    - `filters.py` (Part 4) decides whether a signal is *worth passing
      on* to a future consumer (accept/modify/reject).
    - `validation.py` (Part 5) decides whether a signal is *internally
      well-formed and trustworthy* (errors/warnings), and never itself
      discards, mutates the decision content of, or rejects a signal --
      it only reports findings and, when asked, annotates the result's
      own `metadata` with those findings for traceability. Whether a
      `SignalResult` failing validation should then be discarded is a
      decision left to the caller (or a later Signal Engine part /
      `strategies/`), not to this module.

Nothing in `signals/base.py`, `signals/context.py`, `signals/result.py`,
`signals/exceptions.py`, `signals/utils.py`,
`signals/technical_signal_generator.py`, `signals/aggregator.py`, or
`signals/filters.py` (Signal Engine Parts 1-4) is modified by this
module.

Shape
-----
Every rule implements `ValidationRule.evaluate(result, context)` and
returns a `RuleOutcome` -- never a bare `bool` and never `None` -- so
the *reason* a rule passed, warned, or errored is never lost:

    - ``passed=True``   -- the rule found nothing to flag. `severity` is
      `None`.
    - ``passed=False``, ``severity="warning"`` -- the rule flagged a
      quality concern that does not make the signal unusable.
    - ``passed=False``, ``severity="error"``   -- the rule flagged a
      correctness/consistency problem.

`SignalValidationPipeline` runs a sequence of rules against one
`SignalResult` for one `SignalContext`, in a caller-configurable order.
Unlike `SignalFilterPipeline` (Part 4), it never short-circuits --
validation is about collecting *every* finding, not stopping at the
first one -- so every rule in the pipeline always runs and contributes
to the final `SignalValidationReport` (`is_valid`, `errors`, `warnings`,
`trace`).

`SignalValidator` is the convenience facade most callers use directly
(mirroring the role `TechnicalSignalGenerator` plays over
`BaseSignalGenerator`, and `SignalAggregator` plays over injected
generators): it wraps a `SignalValidationPipeline` -- defaulting to a
sensible built-in rule set when none is supplied -- and additionally
offers `validate_and_annotate()`, which merges the resulting
`SignalValidationReport` into a **new** `SignalResult`'s own
``metadata["signal_validation"]`` (via `SignalResult.with_metadata`,
never mutating the original), so validation findings stay traceable on
the signal itself for anything that reaches a future consumer -- the
same traceability convention `SignalFilterPipeline` already established
for ``metadata["filter_pipeline_trace"]``.

Rules are independent
----------------------
Each rule only knows about its own configuration -- never about any
other rule in the pipeline, and never about `SignalValidationPipeline`
or `SignalValidator` itself. `SignalValidationPipeline` contains no
validation logic of its own; it only sequences already-independent
rules (in a configurable order) and collects their outcomes, mirroring
the combiner/sequencer role `SignalAggregator` (Part 3) and
`SignalFilterPipeline` (Part 4) already play one layer up.

Rules implemented in this module
---------------------------------
    - `SummaryContentRule` -- errors when `summary` is blank/whitespace
      (defensive -- `SignalResult` already guarantees this at
      construction, but a rule catches it regardless of how the result
      was built) or warns when it is suspiciously short.
    - `RangeConsistencyRule` -- errors when `strength`/`confidence` fall
      outside `[0.0, 1.0]` (defensive, same rationale as above); warns
      when `confidence` is exactly `0.0` ("no confidence at all").
    - `DirectionStrengthConsistencyRule` -- errors when a directional
      signal (`BUY`/`SELL`) carries zero `strength` (a directional call
      with no strength is self-contradictory); warns when a `HOLD`
      signal carries unusually high `strength`.
    - `ConfidenceThresholdRule` -- warns (never errors) when
      `confidence` falls below a configurable minimum. Distinct from
      `signals.filters.ConfidenceFilter`, which *rejects* below its own
      minimum -- this rule only reports a quality concern.
    - `MetadataPresenceRule` -- warns when `metadata` is empty, since an
      empty `metadata` dict undermines the traceability every other
      `signals/` module relies on.

Boundaries
----------
No AI: only deterministic, rule-based checks over already-computed
signals. No Risk Engine: nothing here sizes a position or evaluates
exposure. No Strategy Engine: validation is not deciding whether/how to
act -- that remains the future `strategies/` package's job. No Order
Execution: nothing here places, cancels, or simulates a trade. No
trading decisions of any kind are made or implied by this module. Only
`SignalResult` objects (for one `SignalContext`) are validated here --
this module never inspects `analysis.result.AnalysisResult`,
`core.entities.signal.Signal`, or any other type directly.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from core.enums import SignalDirection

from signals.context import SignalContext
from signals.exceptions import SignalValidationError
from signals.result import SignalResult
from signals.utils import validate_unit_range

#: Valid values for `RuleOutcome.severity` when `passed` is `False`.
_VALID_SEVERITIES = frozenset({"error", "warning"})


def _validate_result_and_context(result: Any, context: Any, *, who: str) -> None:
    """
    Shared input-validation for `ValidationRule.evaluate()` implementations.

    Raises:
        SignalValidationError: If `result` is not a `SignalResult` or
            `context` is not a `SignalContext`. This is the only case in
            which any rule in this module raises -- an unusual *value*
            (e.g. zero strength, empty metadata) is a normal validation
            finding (a warning or error in the report), never a raised
            exception.
    """
    if not isinstance(result, SignalResult):
        raise SignalValidationError(f"{who} expected a SignalResult, got {type(result).__name__}")
    if not isinstance(context, SignalContext):
        raise SignalValidationError(
            f"{who} expected a SignalContext, got {type(context).__name__}"
        )


@dataclass(frozen=True)
class RuleOutcome:
    """
    The outcome of a single `ValidationRule.evaluate()` call.

    Kept separate from a bare `bool` so that a finding always carries a
    `rule_name` and a `message` -- with a bare `bool` return, that
    explanation would be lost the moment the result is collected into a
    report.

    Attributes:
        rule_name: `.name` of the rule that produced this outcome.
        passed: Whether the rule found nothing to flag.
        severity: One of `"error"` or `"warning"` when `passed` is
            `False`; `None` when `passed` is `True`.
        message: Short, human-readable explanation of the finding (or,
            when `passed` is `True`, of what was checked and found fine).
    """

    rule_name: str
    passed: bool
    severity: Optional[str]
    message: str

    def __post_init__(self) -> None:
        if self.passed:
            if self.severity is not None:
                raise SignalValidationError(
                    "RuleOutcome.severity must be None when passed=True, "
                    f"got {self.severity!r}"
                )
        else:
            if self.severity not in _VALID_SEVERITIES:
                raise SignalValidationError(
                    f"RuleOutcome.severity must be one of {sorted(_VALID_SEVERITIES)} "
                    f"when passed=False, got {self.severity!r}"
                )
        if not isinstance(self.message, str) or not self.message.strip():
            raise SignalValidationError("RuleOutcome.message must be a non-empty string")

    def as_trace_entry(self) -> dict[str, Any]:
        """Compact `dict` form of this outcome, suitable for a trace list."""
        return {
            "rule": self.rule_name,
            "passed": self.passed,
            "severity": self.severity,
            "message": self.message,
        }


class ValidationRule(ABC):
    """
    Abstract base class for every Signal Engine Part 5 validation rule.

    Mirrors the role `BaseSignalFilter` plays for filters: a minimal
    contract (`evaluate`) plus small shared helpers, with all
    rule-specific logic left to subclasses.

    Attributes:
        name: Human-readable name of this rule instance, used in
            `RuleOutcome.rule_name` and `repr`.
    """

    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name or self.__class__.__name__

    @abstractmethod
    def evaluate(self, result: SignalResult, context: SignalContext) -> RuleOutcome:
        """
        Evaluate `result` (produced for `context`) and return a
        `RuleOutcome` describing whether it passed, or the severity and
        reason for a finding.

        Implementations should call
        `self._validate_inputs(result, context)` first.

        Raises:
            SignalValidationError: If `result` is not a `SignalResult`
                or `context` is not a `SignalContext`. No other
                exception is ever raised by a rule in this module -- an
                unusual/edge-case *value* is a normal validation
                finding, not an error.
        """
        raise NotImplementedError

    def _validate_inputs(self, result: SignalResult, context: SignalContext) -> None:
        _validate_result_and_context(result, context, who=self.name)

    def _pass(self, *, message: str) -> RuleOutcome:
        return RuleOutcome(rule_name=self.name, passed=True, severity=None, message=message)

    def _warn(self, *, message: str) -> RuleOutcome:
        return RuleOutcome(
            rule_name=self.name, passed=False, severity="warning", message=message
        )

    def _fail(self, *, message: str) -> RuleOutcome:
        return RuleOutcome(rule_name=self.name, passed=False, severity="error", message=message)

    def reset(self) -> None:
        """
        Clear any internally-kept state.

        No-op by default -- every rule shipped in this module is
        stateless. Provided for parity with `BaseSignalFilter.reset()`
        and for any future stateful rule.
        """
        return None

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(name={self.name!r})"


class SummaryContentRule(ValidationRule):
    """
    Flags a `SignalResult.summary` that is blank/whitespace (an error --
    defensive, since `SignalResult` already guarantees a non-empty
    summary at construction) or suspiciously short (a warning).

    Parameters:
        min_length: Minimum number of non-whitespace characters in
            `summary` before it is considered adequately descriptive.
            Default `10`.
        name: Rule name, forwarded to `ValidationRule`.

    Raises:
        SignalValidationError: If `min_length` is not a non-negative
            `int`.
    """

    def __init__(self, min_length: int = 10, *, name: Optional[str] = None) -> None:
        super().__init__(name=name)
        if isinstance(min_length, bool) or not isinstance(min_length, int):
            raise SignalValidationError(f"min_length must be an int, got {type(min_length).__name__}")
        if min_length < 0:
            raise SignalValidationError(f"min_length must be >= 0, got {min_length}")
        self.min_length = min_length

    def evaluate(self, result: SignalResult, context: SignalContext) -> RuleOutcome:
        self._validate_inputs(result, context)
        stripped = result.summary.strip()
        if not stripped:
            return self._fail(message="summary is blank or whitespace-only")
        if len(stripped) < self.min_length:
            return self._warn(
                message=(
                    f"summary is only {len(stripped)} characters long "
                    f"(recommended minimum {self.min_length})"
                )
            )
        return self._pass(message=f"summary is {len(stripped)} characters long")


class RangeConsistencyRule(ValidationRule):
    """
    Re-checks `strength`/`confidence` are finite numbers within
    `[0.0, 1.0]` (an error otherwise -- defensive, since `SignalResult`
    already enforces this at construction); warns when `confidence` is
    exactly `0.0` ("no confidence at all" is unusual enough to flag even
    though it is technically in-range).

    Parameters:
        name: Rule name, forwarded to `ValidationRule`.
    """

    def evaluate(self, result: SignalResult, context: SignalContext) -> RuleOutcome:
        self._validate_inputs(result, context)
        for field_name, value in (("strength", result.strength), ("confidence", result.confidence)):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return self._fail(message=f"{field_name} must be numeric, got {type(value).__name__}")
            if not math.isfinite(float(value)):
                return self._fail(message=f"{field_name} must be finite, got {value}")
            if not (0.0 <= float(value) <= 1.0):
                return self._fail(message=f"{field_name} {value} is outside [0.0, 1.0]")

        if result.confidence == 0.0:
            return self._warn(message="confidence is exactly 0.0 (no confidence at all)")

        return self._pass(
            message=(
                f"strength={result.strength:.3f} and confidence={result.confidence:.3f} "
                "are within [0.0, 1.0]"
            )
        )


class DirectionStrengthConsistencyRule(ValidationRule):
    """
    Flags an internal inconsistency between `direction` and `strength`:

        - A directional signal (`BUY`/`SELL`) with `strength == 0.0` is
          self-contradictory (a call with no strength behind it) --
          flagged as an error.
        - A `HOLD` signal with `strength` above a configurable
          threshold is unusual (a "do nothing" call carrying a strong
          strength reading) -- flagged as a warning.

    Parameters:
        hold_strength_warn_threshold: `strength` above which a `HOLD`
            signal is flagged as a warning. Must be within
            `[0.0, 1.0]`. Default `0.5`.
        name: Rule name, forwarded to `ValidationRule`.

    Raises:
        SignalValidationError: If `hold_strength_warn_threshold` is not
            a finite number within `[0.0, 1.0]`.
    """

    def __init__(
        self, hold_strength_warn_threshold: float = 0.5, *, name: Optional[str] = None
    ) -> None:
        super().__init__(name=name)
        self.hold_strength_warn_threshold = validate_unit_range(
            hold_strength_warn_threshold, name="hold_strength_warn_threshold"
        )

    def evaluate(self, result: SignalResult, context: SignalContext) -> RuleOutcome:
        self._validate_inputs(result, context)

        if result.direction in (SignalDirection.BUY, SignalDirection.SELL):
            if result.strength == 0.0:
                return self._fail(
                    message=(
                        f"direction={result.direction.value} carries strength=0.0 "
                        "(a directional signal with no strength)"
                    )
                )
            return self._pass(
                message=(
                    f"direction={result.direction.value} carries strength="
                    f"{result.strength:.3f} (consistent)"
                )
            )

        # HOLD
        if result.strength > self.hold_strength_warn_threshold:
            return self._warn(
                message=(
                    f"direction=hold carries strength={result.strength:.3f}, above the "
                    f"expected threshold {self.hold_strength_warn_threshold:.3f}"
                )
            )
        return self._pass(
            message=f"direction=hold carries strength={result.strength:.3f} (consistent)"
        )


class ConfidenceThresholdRule(ValidationRule):
    """
    Warns (never errors) when `SignalResult.confidence` falls below a
    configurable minimum.

    Distinct from `signals.filters.ConfidenceFilter`: that filter
    *rejects* a signal below its own minimum, discarding it from any
    consumer entirely; this rule only reports a quality concern in the
    validation report/metadata, leaving the signal itself untouched.

    Parameters:
        min_confidence: Minimum `SignalResult.confidence` before this
            rule warns, in the closed range `[0.0, 1.0]`. Default `0.3`.
        name: Rule name, forwarded to `ValidationRule`.

    Raises:
        SignalValidationError: If `min_confidence` is not a finite
            number within `[0.0, 1.0]`.
    """

    def __init__(self, min_confidence: float = 0.3, *, name: Optional[str] = None) -> None:
        super().__init__(name=name)
        self.min_confidence = validate_unit_range(min_confidence, name="min_confidence")

    def evaluate(self, result: SignalResult, context: SignalContext) -> RuleOutcome:
        self._validate_inputs(result, context)
        if result.confidence < self.min_confidence:
            return self._warn(
                message=(
                    f"confidence {result.confidence:.3f} is below the recommended minimum "
                    f"{self.min_confidence:.3f}"
                )
            )
        return self._pass(
            message=(
                f"confidence {result.confidence:.3f} meets the recommended minimum "
                f"{self.min_confidence:.3f}"
            )
        )


class MetadataPresenceRule(ValidationRule):
    """
    Warns when `SignalResult.metadata` is empty, since an empty
    `metadata` dict undermines the traceability convention every other
    `signals/` module relies on (e.g. `TechnicalSignalGenerator`'s
    `source_analyzer`/`source_score`/..., `SignalFilterPipeline`'s
    ``filter_pipeline_trace``).

    Parameters:
        name: Rule name, forwarded to `ValidationRule`.
    """

    def evaluate(self, result: SignalResult, context: SignalContext) -> RuleOutcome:
        self._validate_inputs(result, context)
        if not result.metadata:
            return self._warn(message="metadata is empty (no supporting details for traceability)")
        return self._pass(message=f"metadata carries {len(result.metadata)} key(s)")


@dataclass(frozen=True)
class SignalValidationReport:
    """
    The outcome of running a `SignalValidationPipeline` (or
    `SignalValidator`) once.

    Attributes:
        is_valid: Whether zero rules reported an `"error"` (warnings
            alone do not affect this).
        errors: Ordered list of `RuleOutcome.message` for every rule
            outcome with `severity="error"`.
        warnings: Ordered list of `RuleOutcome.message` for every rule
            outcome with `severity="warning"`.
        trace: Ordered list of every rule's `RuleOutcome`, as `dict`s
            (`RuleOutcome.as_trace_entry()`) -- every rule always runs,
            so this always has one entry per rule in the pipeline,
            regardless of pass/fail.
    """

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)

    def as_metadata(self) -> dict[str, Any]:
        """Compact `dict` form suitable for merging into `SignalResult.metadata`."""
        return {
            "is_valid": self.is_valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "trace": [dict(entry) for entry in self.trace],
        }


class SignalValidationPipeline:
    """
    Runs a sequence of independent `ValidationRule`s against one
    `SignalResult`/`SignalContext` pair, in a caller-configurable order,
    never short-circuiting -- every rule always runs and contributes to
    the final `SignalValidationReport`.

    Contains no validation logic of its own -- it only sequences
    already-independent rules and collects their `RuleOutcome`s,
    mirroring the combiner/sequencer role `SignalAggregator` (Part 3)
    and `SignalFilterPipeline` (Part 4) already play one layer up.

    Parameters:
        rules: The `ValidationRule` instances to run, in order.
            Defaults to an empty pipeline (every `SignalResult` is
            reported valid, with an empty trace) when omitted.
        name: Human-readable name of this pipeline instance.

    Raises:
        SignalValidationError: If `rules` contains a non-
            `ValidationRule` item, or if two rules share the same
            `.name` (required for `reorder()` to be unambiguous).
    """

    def __init__(
        self,
        rules: Optional[Sequence[ValidationRule]] = None,
        *,
        name: Optional[str] = None,
    ) -> None:
        self.name = name or self.__class__.__name__
        self.rules: list[ValidationRule] = self._validate_rules(rules)

    def run(self, result: SignalResult, context: SignalContext) -> SignalValidationReport:
        """
        Run every rule, in order, against `result`/`context`.

        Unlike `SignalFilterPipeline.run()`, this never short-circuits:
        every rule in the pipeline is always evaluated, so a caller
        sees the complete set of errors/warnings in one pass rather
        than only the first one encountered.

        Raises:
            SignalValidationError: If `result` is not a `SignalResult`
                or `context` is not a `SignalContext`, or if any
                individual rule raises it for the same reason.
        """
        _validate_result_and_context(result, context, who=self.name)

        trace: list[dict[str, Any]] = []
        errors: list[str] = []
        warnings: list[str] = []

        for rule in self.rules:
            outcome = rule.evaluate(result, context)
            trace.append(outcome.as_trace_entry())
            if outcome.severity == "error":
                errors.append(outcome.message)
            elif outcome.severity == "warning":
                warnings.append(outcome.message)

        return SignalValidationReport(
            is_valid=(len(errors) == 0), errors=errors, warnings=warnings, trace=trace
        )

    def reorder(self, rule_names: Sequence[str]) -> None:
        """
        Reorder this pipeline's rules to match `rule_names`.

        Lets a caller configure rule execution order after construction
        without rebuilding the pipeline. `rule_names` must be a
        permutation of the `.name` of every rule currently in the
        pipeline -- exactly once each.

        Raises:
            SignalValidationError: If `rule_names` does not contain
                exactly the same set of names as `self.rules`, each
                exactly once.
        """
        current_by_name = {rule.name: rule for rule in self.rules}
        requested = list(rule_names)

        if sorted(requested) != sorted(current_by_name.keys()):
            raise SignalValidationError(
                "reorder() requires exactly the current rule names, each once: "
                f"expected a permutation of {sorted(current_by_name.keys())}, got {requested}"
            )

        self.rules = [current_by_name[name] for name in requested]

    def reset(self) -> None:
        """Reset every rule in this pipeline (see `ValidationRule.reset`)."""
        for rule in self.rules:
            rule.reset()

    @staticmethod
    def _validate_rules(rules: Optional[Sequence[ValidationRule]]) -> list[ValidationRule]:
        items = list(rules) if rules is not None else []
        seen_names: set[str] = set()
        for index, item in enumerate(items):
            if not isinstance(item, ValidationRule):
                raise SignalValidationError(
                    f"rules[{index}] must be a ValidationRule, got {type(item).__name__}"
                )
            if item.name in seen_names:
                raise SignalValidationError(
                    f"rules[{index}] has duplicate name {item.name!r}; rule names must be "
                    "unique within a SignalValidationPipeline"
                )
            seen_names.add(item.name)
        return items

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(name={self.name!r}, rules={self.rules!r})"


def _default_rules() -> list[ValidationRule]:
    """Build a fresh instance of this module's default rule set, in a sensible order."""
    return [
        SummaryContentRule(),
        RangeConsistencyRule(),
        DirectionStrengthConsistencyRule(),
        ConfidenceThresholdRule(),
        MetadataPresenceRule(),
    ]


class SignalValidator:
    """
    Convenience facade over `SignalValidationPipeline`, mirroring the
    role `TechnicalSignalGenerator` plays over `BaseSignalGenerator` and
    `SignalAggregator` plays over injected generators: most callers use
    this class directly rather than building a `SignalValidationPipeline`
    by hand.

    Defaults to a sensible built-in rule set (`SummaryContentRule`,
    `RangeConsistencyRule`, `DirectionStrengthConsistencyRule`,
    `ConfidenceThresholdRule`, `MetadataPresenceRule`) when neither
    `rules` nor `pipeline` is supplied.

    Parameters:
        rules: `ValidationRule` instances to validate with, in order.
            Ignored if `pipeline` is also supplied.
        pipeline: A pre-built `SignalValidationPipeline` to use instead
            of constructing one from `rules`. Takes precedence over
            `rules` when both are given.
        name: Human-readable name of this validator instance.

    Raises:
        SignalValidationError: If both `rules` and `pipeline` construct
            an invalid rule set (see `SignalValidationPipeline`).
    """

    def __init__(
        self,
        rules: Optional[Sequence[ValidationRule]] = None,
        *,
        pipeline: Optional[SignalValidationPipeline] = None,
        name: Optional[str] = None,
    ) -> None:
        self.name = name or self.__class__.__name__
        if pipeline is not None:
            self.pipeline = pipeline
        else:
            self.pipeline = SignalValidationPipeline(
                rules if rules is not None else _default_rules(),
                name=f"{self.name}.pipeline",
            )

    def validate(self, result: SignalResult, context: SignalContext) -> SignalValidationReport:
        """
        Run every configured rule against `result`/`context` and return
        the resulting `SignalValidationReport`. Never raises for a
        validation finding -- only for malformed input (see
        `SignalValidationPipeline.run`).
        """
        return self.pipeline.run(result, context)

    def validate_and_annotate(self, result: SignalResult, context: SignalContext) -> SignalResult:
        """
        Validate `result`/`context` and return a **new** `SignalResult`
        with the resulting `SignalValidationReport` merged into
        ``metadata["signal_validation"]`` (via `SignalResult.with_metadata`),
        so the findings stay traceable on the signal itself for any
        future consumer -- the same convention `SignalFilterPipeline`
        already established for ``metadata["filter_pipeline_trace"]``.

        The original `result` is never mutated (it is frozen); this
        always returns the annotated signal regardless of whether it is
        valid -- `SignalValidator` never discards or executes a trade
        on a signal, it only reports and annotates. Whether a caller
        acts on `report.is_valid` being `False` is left entirely to
        that caller.
        """
        report = self.validate(result, context)
        return result.with_metadata(signal_validation=report.as_metadata())

    def reset(self) -> None:
        """Reset every rule in the underlying pipeline (see `ValidationRule.reset`)."""
        self.pipeline.reset()

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(name={self.name!r}, pipeline={self.pipeline!r})"
