"""
signals/base.py

Defines `BaseSignalGenerator`: the abstract base every concrete signal
generator implements in later Signal Engine parts.

Mirrors the role `analysis/base.py`'s `BaseAnalyzer` plays for
`analysis/`: `analysis/` interprets raw market/news data into scored
`AnalysisResult`s, `signals/` standardizes one or more `AnalysisResult`s
into a single `SignalResult` -- without deciding what to do about it
(that decision belongs to the future `strategies/` package).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from core.enums import SignalDirection

from signals.context import SignalContext
from signals.exceptions import InvalidSignalContextError
from signals.result import SignalResult


class BaseSignalGenerator(ABC):
    """
    Abstract base class for all signal generators.

    A concrete signal generator consumes a `SignalContext` (one or more
    `AnalysisResult`s for a symbol/timeframe) and produces a single
    `SignalResult`. Concrete generators must not place orders, manage
    risk, or make trading decisions -- that is the responsibility of the
    future `strategies/` package.

    Attributes:
        name: Human-readable name of this generator instance, used for
            logging/`repr`. Note `SignalResult` intentionally has no
            `generator_name` field (unlike `AnalysisResult`'s
            `analyzer_name`) -- a concrete generator may record `name`
            in its own `metadata` if traceability is needed.
    """

    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name or self.__class__.__name__

    # ------------------------------------------------------------------
    # Abstract API
    # ------------------------------------------------------------------
    @abstractmethod
    def generate(self, context: SignalContext) -> SignalResult:
        """
        Generate a `SignalResult` from `context`.

        Implementations should call `self.validate_context(context)`
        first, and are expected to raise `signals.exceptions.
        InsufficientSignalDataError` when `context` does not carry
        enough data (e.g. no `AnalysisResult`s) to produce a meaningful
        result.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def validate_context(self, context: SignalContext) -> SignalContext:
        """
        Validate that `context` is a usable `SignalContext` for this generator.

        Raises:
            InvalidSignalContextError: If `context` is not a
                `SignalContext` instance.
        """
        if not isinstance(context, SignalContext):
            raise InvalidSignalContextError(
                f"{self.name} expected a SignalContext, got {type(context).__name__}"
            )
        return context

    def _build_result(
        self,
        *,
        direction: SignalDirection,
        strength: float,
        confidence: float,
        summary: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> SignalResult:
        """
        Build a `SignalResult` using this generator's standard shape.

        Convenience helper so concrete generators don't repeat
        `SignalResult(...)` construction on every `generate()`
        implementation.
        """
        return SignalResult(
            direction=direction,
            strength=strength,
            confidence=confidence,
            summary=summary,
            metadata=metadata or {},
        )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(name={self.name!r})"
