"""
signals/filters.py

Defines Signal Engine Part 4: a small pipeline of independent filters
that sit between signal *generation* (Parts 1-3: `BaseSignalGenerator`,
`TechnicalSignalGenerator`, `SignalAggregator`) and any future consumer
(`strategies/`). Filters never generate a new `SignalResult` from
scratch and never decide whether/how to trade -- they only accept,
reject, or adjust an already-produced `SignalResult`, and record why.

Nothing in `signals/base.py`, `signals/context.py`, `signals/result.py`,
`signals/exceptions.py`, `signals/utils.py`,
`signals/technical_signal_generator.py`, or `signals/aggregator.py`
(Signal Engine Parts 1-3) is modified by this module.

Shape
-----
Every filter implements `BaseSignalFilter.apply(result, context)` and
returns a `FilterOutcome` -- never a bare `SignalResult` and never
`None` -- so the *reason* for a decision is never lost, even when a
signal is rejected outright:

    - ``action="accept"``  -- the incoming `SignalResult` is unchanged.
      `outcome.result` is the same `SignalResult` that was passed in.
    - ``action="modify"``  -- the filter adjusted the `SignalResult`
      (e.g. downgraded its direction/strength/confidence).
      `outcome.result` is a *new* `SignalResult` (frozen, like every
      other `SignalResult`).
    - ``action="reject"``  -- the `SignalResult` is discarded entirely.
      `outcome.result` is `None`.

`SignalFilterPipeline` runs a sequence of filters against one
`SignalResult` for one `SignalContext`, short-circuiting on the first
rejection. Every filter's outcome (accept/modify/reject + reason) is
recorded, in order, in `SignalFilterPipelineResult.trace`; on top of
that, if the pipeline's final result survives all filters, the same
trace is also merged into that result's own
``metadata["filter_pipeline_trace"]`` -- so traceability lives both on
the pipeline's return value and, for anything that actually reaches a
consumer, on the `SignalResult` itself.

Filters are independent
------------------------
Each filter only knows about its own configuration and (for the
stateful ones) its own internally-kept history -- never about any
other filter in the pipeline. `SignalFilterPipeline` itself contains no
filtering logic of its own; it only sequences already-independent
filters and collects their outcomes, mirroring the combiner role
`SignalAggregator` (Part 3) already plays for generators.

Filters implemented in this module
-----------------------------------
    - `ConfidenceFilter` -- rejects a `SignalResult` whose `confidence`
      falls below a configurable minimum. Never modifies.
    - `DuplicateSignalFilter` -- stateful; rejects a `SignalResult` that
      repeats the immediately-previous *accepted* (direction, strength)
      pair for the same `SignalContext.symbol`/`timeframe`. Never
      modifies.
    - `CooldownFilter` -- stateful; rejects any `SignalResult` (of any
      direction) arriving less than a configurable number of seconds
      after the previous *accepted* one for the same symbol/timeframe.
      Uses an injectable clock (defaulting to `time.monotonic`), so
      tests never depend on real wall-clock time. Never modifies.
    - `ConflictFilter` -- stateful; when a `SignalResult` directly
      reverses the previous *accepted* non-`HOLD` direction for the
      same symbol/timeframe (BUY immediately after SELL, or vice
      versa), downgrades it to `SignalDirection.HOLD` with reduced
      strength/confidence rather than rejecting it outright -- the
      demonstrated `action="modify"` path. Otherwise accepts.

Boundaries
----------
No AI: only deterministic accept/reject/modify rules over
already-computed signals. No Risk Engine: nothing here sizes a
position or evaluates exposure. No Strategy Engine: filtering is not
deciding whether/how to act -- that remains the future `strategies/`
package's job. No Order Execution: nothing here places, cancels, or
simulates a trade. No trading decisions of any kind are made or
implied by this module.
"""

from __future__ import annotations

import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from core.enums import SignalDirection

from signals.context import SignalContext
from signals.exceptions import SignalValidationError
from signals.result import SignalResult
from signals.utils import validate_unit_range

#: Valid values for `FilterOutcome.action`.
_VALID_ACTIONS = frozenset({"accept", "modify", "reject"})


def _validate_result_and_context(result: Any, context: Any, *, who: str) -> None:
    """
    Shared input-validation for `BaseSignalFilter.apply()` implementations.

    Raises:
        SignalValidationError: If `result` is not a `SignalResult` or
            `context` is not a `SignalContext`. This is the only case
            in which any filter in this module raises.
    """
    if not isinstance(result, SignalResult):
        raise SignalValidationError(f"{who} expected a SignalResult, got {type(result).__name__}")
    if not isinstance(context, SignalContext):
        raise SignalValidationError(
            f"{who} expected a SignalContext, got {type(context).__name__}"
        )


@dataclass(frozen=True)
class FilterOutcome:
    """
    The outcome of a single `BaseSignalFilter.apply()` call.

    Kept separate from `SignalResult` (rather than returning
    `Optional[SignalResult]` directly) so that a *rejection* still
    carries a `reason` and a `filter_name` -- with a bare
    `Optional[SignalResult]` return, that information would vanish the
    moment a signal is dropped.

    Attributes:
        filter_name: `.name` of the filter that produced this outcome.
        action: One of `"accept"`, `"modify"`, or `"reject"`.
        result: The surviving `SignalResult` for `"accept"`/`"modify"`;
            `None` for `"reject"`.
        reason: Short, human-readable explanation of the decision.
    """

    filter_name: str
    action: str
    result: Optional[SignalResult]
    reason: str

    def __post_init__(self) -> None:
        if self.action not in _VALID_ACTIONS:
            raise SignalValidationError(
                f"FilterOutcome.action must be one of {sorted(_VALID_ACTIONS)}, "
                f"got {self.action!r}"
            )
        if self.action == "reject" and self.result is not None:
            raise SignalValidationError("FilterOutcome.result must be None when action='reject'")
        if self.action in ("accept", "modify") and self.result is None:
            raise SignalValidationError(
                f"FilterOutcome.result must not be None when action={self.action!r}"
            )
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise SignalValidationError("FilterOutcome.reason must be a non-empty string")

    def as_trace_entry(self) -> dict[str, Any]:
        """Compact `dict` form of this outcome, suitable for a trace list."""
        return {"filter": self.filter_name, "action": self.action, "reason": self.reason}


class BaseSignalFilter(ABC):
    """
    Abstract base class for every Signal Engine Part 4 filter.

    Mirrors the role `BaseSignalGenerator` plays for generators: a
    minimal contract (`apply`) plus small shared helpers, with all
    filter-specific logic left to subclasses.

    Attributes:
        name: Human-readable name of this filter instance, used in
            `FilterOutcome.filter_name` and `repr`.
    """

    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name or self.__class__.__name__

    @abstractmethod
    def apply(self, result: SignalResult, context: SignalContext) -> FilterOutcome:
        """
        Evaluate `result` (produced for `context`) and return a
        `FilterOutcome` describing whether it is accepted unchanged,
        modified, or rejected.

        Implementations should call
        `self._validate_inputs(result, context)` first.

        Raises:
            SignalValidationError: If `result` is not a `SignalResult`
                or `context` is not a `SignalContext`. No other
                exception is ever raised by a filter in this module --
                an unusual/edge-case *value* (e.g. zero confidence) is
                a normal filtering outcome, not an error.
        """
        raise NotImplementedError

    def _validate_inputs(self, result: SignalResult, context: SignalContext) -> None:
        _validate_result_and_context(result, context, who=self.name)

    def _accept(self, result: SignalResult, *, reason: str) -> FilterOutcome:
        return FilterOutcome(filter_name=self.name, action="accept", result=result, reason=reason)

    def _modify(self, result: SignalResult, *, reason: str) -> FilterOutcome:
        return FilterOutcome(filter_name=self.name, action="modify", result=result, reason=reason)

    def _reject(self, *, reason: str) -> FilterOutcome:
        return FilterOutcome(filter_name=self.name, action="reject", result=None, reason=reason)

    def reset(self) -> None:
        """
        Clear any internally-kept history.

        No-op for stateless filters (e.g. `ConfidenceFilter`); stateful
        filters (`DuplicateSignalFilter`, `CooldownFilter`,
        `ConflictFilter`) override this to forget prior
        symbol/timeframe history -- primarily useful for test isolation
        and for callers that want to reuse a filter instance across
        unrelated trading sessions.
        """
        return None

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(name={self.name!r})"


class ConfidenceFilter(BaseSignalFilter):
    """
    Rejects a `SignalResult` whose `confidence` is below a configurable
    minimum. Never modifies a `SignalResult` -- only accepts or rejects.

    Parameters:
        min_confidence: Minimum `SignalResult.confidence` required to
            accept, in the closed range `[0.0, 1.0]`. Default `0.3`.
        name: Filter name, forwarded to `BaseSignalFilter`.

    Raises:
        SignalValidationError: If `min_confidence` is not a finite
            number within `[0.0, 1.0]`.
    """

    def __init__(self, min_confidence: float = 0.3, *, name: Optional[str] = None) -> None:
        super().__init__(name=name)
        self.min_confidence = validate_unit_range(min_confidence, name="min_confidence")

    def apply(self, result: SignalResult, context: SignalContext) -> FilterOutcome:
        self._validate_inputs(result, context)
        if result.confidence < self.min_confidence:
            return self._reject(
                reason=(
                    f"confidence {result.confidence:.3f} is below the required minimum "
                    f"{self.min_confidence:.3f}"
                )
            )
        return self._accept(
            result,
            reason=(
                f"confidence {result.confidence:.3f} meets the required minimum "
                f"{self.min_confidence:.3f}"
            ),
        )


class DuplicateSignalFilter(BaseSignalFilter):
    """
    Rejects a `SignalResult` that repeats the immediately-previous
    *accepted* `(direction, strength)` pair for the same
    `SignalContext.symbol`/`timeframe`. Never modifies -- only accepts
    or rejects.

    Stateful: keeps, per `(symbol, timeframe)` key, only the single
    most recently *accepted* signature -- this is a consecutive-repeat
    detector, not a full history lookup. Two different symbols (or the
    same symbol on two different timeframes) never count as duplicates
    of each other.

    Parameters:
        strength_precision: Number of decimal places `strength` is
            rounded to before comparison, so that negligible
            floating-point noise doesn't defeat duplicate detection.
            Default `3`.
        name: Filter name, forwarded to `BaseSignalFilter`.
    """

    def __init__(self, strength_precision: int = 3, *, name: Optional[str] = None) -> None:
        super().__init__(name=name)
        if isinstance(strength_precision, bool) or not isinstance(strength_precision, int):
            raise SignalValidationError(
                f"strength_precision must be an int, got {type(strength_precision).__name__}"
            )
        if strength_precision < 0:
            raise SignalValidationError(
                f"strength_precision must be >= 0, got {strength_precision}"
            )
        self.strength_precision = strength_precision
        self._last_signature: dict[tuple[str, str], tuple[SignalDirection, float]] = {}

    def apply(self, result: SignalResult, context: SignalContext) -> FilterOutcome:
        self._validate_inputs(result, context)
        key = (context.symbol, context.timeframe)
        signature = (result.direction, round(result.strength, self.strength_precision))

        previous = self._last_signature.get(key)
        if previous == signature:
            return self._reject(
                reason=(
                    f"duplicate of the previous accepted signal for "
                    f"{context.symbol}/{context.timeframe} "
                    f"(direction={result.direction.value}, "
                    f"strength={signature[1]:.{self.strength_precision}f})"
                )
            )

        self._last_signature[key] = signature
        return self._accept(
            result,
            reason=f"first occurrence of this signal for {context.symbol}/{context.timeframe}",
        )

    def reset(self) -> None:
        self._last_signature.clear()


class CooldownFilter(BaseSignalFilter):
    """
    Rejects any `SignalResult` (regardless of direction) arriving less
    than `cooldown_seconds` after the previous *accepted* one for the
    same `SignalContext.symbol`/`timeframe`. Never modifies -- only
    accepts or rejects.

    Stateful: keeps, per `(symbol, timeframe)` key, the clock reading
    at which a signal was last accepted.

    Parameters:
        cooldown_seconds: Minimum number of seconds required between
            two accepted signals for the same symbol/timeframe. Must be
            a finite number `>= 0.0`.
        clock: Zero-argument callable returning the current time as a
            float (seconds). Defaults to `time.monotonic`. Injectable
            so tests never depend on real wall-clock time -- matches
            the project's dependency-injection convention for external
            I/O (here, the passage of time).
        name: Filter name, forwarded to `BaseSignalFilter`.

    Raises:
        SignalValidationError: If `cooldown_seconds` is not a finite
            number `>= 0.0`, or `clock` is not callable.
    """

    def __init__(
        self,
        cooldown_seconds: float,
        *,
        clock: Optional[Callable[[], float]] = None,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(name=name)
        if isinstance(cooldown_seconds, bool) or not isinstance(cooldown_seconds, (int, float)):
            raise SignalValidationError(
                f"cooldown_seconds must be numeric, got {type(cooldown_seconds).__name__}"
            )
        numeric_cooldown = float(cooldown_seconds)
        if not math.isfinite(numeric_cooldown) or numeric_cooldown < 0.0:
            raise SignalValidationError(
                f"cooldown_seconds must be a finite number >= 0.0, got {cooldown_seconds}"
            )
        if clock is not None and not callable(clock):
            raise SignalValidationError(f"clock must be callable, got {type(clock).__name__}")
        self.cooldown_seconds = numeric_cooldown
        self._clock: Callable[[], float] = clock or time.monotonic
        self._last_accepted_at: dict[tuple[str, str], float] = {}

    def apply(self, result: SignalResult, context: SignalContext) -> FilterOutcome:
        self._validate_inputs(result, context)
        key = (context.symbol, context.timeframe)
        now = float(self._clock())

        last = self._last_accepted_at.get(key)
        if last is not None:
            elapsed = now - last
            if elapsed < self.cooldown_seconds:
                remaining = self.cooldown_seconds - elapsed
                return self._reject(
                    reason=(
                        f"cooldown active for {context.symbol}/{context.timeframe}: "
                        f"{remaining:.3f}s remaining of {self.cooldown_seconds:.3f}s"
                    )
                )

        self._last_accepted_at[key] = now
        return self._accept(
            result, reason=f"no active cooldown for {context.symbol}/{context.timeframe}"
        )

    def reset(self) -> None:
        self._last_accepted_at.clear()


class ConflictFilter(BaseSignalFilter):
    """
    Detects a `SignalResult` that directly reverses the previous
    *accepted* non-`HOLD` direction for the same
    `SignalContext.symbol`/`timeframe` (BUY immediately after SELL, or
    vice versa) and, rather than rejecting it, downgrades it to
    `SignalDirection.HOLD` with reduced `strength`/`confidence` -- the
    filter set's demonstrated `action="modify"` path. Any other case
    (first signal for a key, same direction as before, or a `HOLD` on
    either side) is accepted unchanged.

    Stateful: keeps, per `(symbol, timeframe)` key, the most recently
    accepted non-`HOLD` direction.

    Parameters:
        dampening: Multiplier applied to both `strength` and
            `confidence` when downgrading a conflicting signal, in the
            closed range `[0.0, 1.0]`. Default `0.5`.
        name: Filter name, forwarded to `BaseSignalFilter`.

    Raises:
        SignalValidationError: If `dampening` is not a finite number
            within `[0.0, 1.0]`.
    """

    def __init__(self, dampening: float = 0.5, *, name: Optional[str] = None) -> None:
        super().__init__(name=name)
        self.dampening = validate_unit_range(dampening, name="dampening")
        self._last_direction: dict[tuple[str, str], SignalDirection] = {}

    def apply(self, result: SignalResult, context: SignalContext) -> FilterOutcome:
        self._validate_inputs(result, context)
        key = (context.symbol, context.timeframe)
        previous_direction = self._last_direction.get(key)

        is_conflict = (
            previous_direction is not None
            and result.direction != SignalDirection.HOLD
            and previous_direction != SignalDirection.HOLD
            and result.direction != previous_direction
        )

        if is_conflict:
            downgraded = SignalResult(
                direction=SignalDirection.HOLD,
                strength=result.strength * self.dampening,
                confidence=result.confidence * self.dampening,
                summary=(
                    f"{result.summary} [downgraded to HOLD: conflicts with previous "
                    f"{previous_direction.value} signal for "
                    f"{context.symbol}/{context.timeframe}]"
                ),
                metadata=result.metadata,
            )
            # A downgrade to HOLD does not update `_last_direction` --
            # the previous non-HOLD direction remains the standing
            # reference until a *non-conflicting* directional signal is
            # accepted for this key.
            return self._modify(
                downgraded,
                reason=(
                    f"{result.direction.value} conflicts with previous accepted "
                    f"{previous_direction.value} for {context.symbol}/{context.timeframe}; "
                    "downgraded to hold"
                ),
            )

        if result.direction != SignalDirection.HOLD:
            self._last_direction[key] = result.direction

        return self._accept(
            result,
            reason=(
                "no conflict with previous accepted direction for "
                f"{context.symbol}/{context.timeframe}"
            ),
        )

    def reset(self) -> None:
        self._last_direction.clear()


@dataclass(frozen=True)
class SignalFilterPipelineResult:
    """
    The outcome of running a `SignalFilterPipeline` once.

    Attributes:
        accepted: Whether the `SignalResult` survived every filter in
            the pipeline.
        result: The final (possibly modified) `SignalResult` when
            `accepted` is `True`; `None` when `accepted` is `False`.
        trace: Ordered list of every filter's `FilterOutcome`, as
            `dict`s (`FilterOutcome.as_trace_entry()`), including the
            filter that rejected the signal, if any. Filters after a
            rejection are never run and so never appear here.
        rejected_by: `.name` of the filter that rejected the signal, or
            `None` if `accepted` is `True`.
    """

    accepted: bool
    result: Optional[SignalResult]
    trace: list[dict[str, Any]] = field(default_factory=list)
    rejected_by: Optional[str] = None


class SignalFilterPipeline:
    """
    Runs a sequence of independent `BaseSignalFilter`s against one
    `SignalResult`/`SignalContext` pair, in order, short-circuiting on
    the first rejection.

    Contains no filtering logic of its own -- it only sequences
    already-independent filters and collects their `FilterOutcome`s,
    mirroring the combiner role `SignalAggregator` (Part 3) already
    plays for generators one layer up.

    Parameters:
        filters: The `BaseSignalFilter` instances to run, in order.
            Defaults to an empty pipeline (every `SignalResult` passes
            through unchanged, with an empty trace) when omitted.
        name: Human-readable name of this pipeline instance.

    Raises:
        SignalValidationError: If `filters` contains a non-
            `BaseSignalFilter` item.
    """

    def __init__(
        self,
        filters: Optional[Sequence[BaseSignalFilter]] = None,
        *,
        name: Optional[str] = None,
    ) -> None:
        self.name = name or self.__class__.__name__
        self.filters: list[BaseSignalFilter] = self._validate_filters(filters)

    def run(self, result: SignalResult, context: SignalContext) -> SignalFilterPipelineResult:
        """
        Run every filter in order against `result`/`context`.

        Raises:
            SignalValidationError: If `result` is not a `SignalResult`
                or `context` is not a `SignalContext`, or if any
                individual filter raises it for the same reason.
        """
        _validate_result_and_context(result, context, who=self.name)

        current = result
        trace: list[dict[str, Any]] = []

        for signal_filter in self.filters:
            outcome = signal_filter.apply(current, context)
            trace.append(outcome.as_trace_entry())
            if outcome.action == "reject":
                return SignalFilterPipelineResult(
                    accepted=False, result=None, trace=trace, rejected_by=outcome.filter_name
                )
            current = outcome.result

        final = current.with_metadata(filter_pipeline_trace=trace) if trace else current
        return SignalFilterPipelineResult(accepted=True, result=final, trace=trace)

    def reset(self) -> None:
        """Reset every filter in this pipeline (see `BaseSignalFilter.reset`)."""
        for signal_filter in self.filters:
            signal_filter.reset()

    @staticmethod
    def _validate_filters(
        filters: Optional[Sequence[BaseSignalFilter]],
    ) -> list[BaseSignalFilter]:
        items = list(filters) if filters is not None else []
        for index, item in enumerate(items):
            if not isinstance(item, BaseSignalFilter):
                raise SignalValidationError(
                    f"filters[{index}] must be a BaseSignalFilter, got {type(item).__name__}"
                )
        return items

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(name={self.name!r}, filters={self.filters!r})"
