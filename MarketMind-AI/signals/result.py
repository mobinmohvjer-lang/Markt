"""
signals/result.py

Defines `SignalResult`: the standardized output produced by every
`BaseSignalGenerator.generate()` call, regardless of which concrete
generator produced it.

Pure data container -- no scoring/generation logic. This lets a future
`strategies/` package (a consumer) depend on one stable shape instead of
a different result type per generator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.enums import SignalDirection

from signals.utils import (
    merge_metadata,
    validate_direction,
    validate_non_empty_str,
    validate_unit_range,
)


@dataclass(frozen=True)
class SignalResult:
    """
    The standardized output of a single signal generator run.

    Intentionally minimal: this is *not* `core.entities.signal.Signal`
    (which carries an id, source, timestamp, symbol, timeframe, and is
    meant to represent a persisted/actionable trading signal). Building
    a `Signal` from one or more `SignalResult`s -- and deciding whether
    it is actionable -- belongs to a later Signal Engine part / the
    future `strategies/` package, not to this foundation.

    Attributes:
        direction: Directional meaning of the signal (buy/sell/hold),
            reusing `core.enums.SignalDirection` rather than inventing a
            new enum.
        strength: How strong the signal is, expressed as a float in the
            closed range [0.0, 1.0] (0.0 = negligible, 1.0 = maximal).
            Distinct from `confidence`: `strength` is "how big a move
            this looks like", `confidence` is "how sure the generator is
            about `direction`/`strength`".
        confidence: How confident the generator is in this result,
            expressed as a float in the closed range [0.0, 1.0].
        summary: Short, human-readable explanation of the result.
        metadata: Generator-specific supporting details (e.g. which
            `AnalysisResult`s contributed, intermediate values), kept
            for traceability.
    """

    direction: SignalDirection
    strength: float
    confidence: float
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # dataclass is frozen, so field re-assignment goes through
        # object.__setattr__ -- this only normalizes/validates values,
        # it never introduces new state.
        object.__setattr__(self, "direction", validate_direction(self.direction))
        object.__setattr__(self, "strength", validate_unit_range(self.strength, name="strength"))
        object.__setattr__(
            self, "confidence", validate_unit_range(self.confidence, name="confidence")
        )
        object.__setattr__(self, "summary", validate_non_empty_str(self.summary, name="summary"))
        if not isinstance(self.metadata, dict):
            raise TypeError(f"metadata must be a dict, got {type(self.metadata).__name__}")

    def with_metadata(self, **extra: Any) -> "SignalResult":
        """
        Return a new `SignalResult` with `extra` merged into `metadata`.

        Since `SignalResult` is immutable, this returns a new instance
        rather than mutating the existing one.
        """
        return SignalResult(
            direction=self.direction,
            strength=self.strength,
            confidence=self.confidence,
            summary=self.summary,
            metadata=merge_metadata(self.metadata, extra),
        )
