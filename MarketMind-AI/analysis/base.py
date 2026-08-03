"""
analysis/base.py

Defines `BaseAnalyzer`: the abstract base every concrete analyzer
(technical, news, AI, ...) implements in later Analysis Engine parts.

Mirrors the role `indicators/base.py`'s `BaseIndicator` plays for
`indicators/`: `indicators/` calculates raw values, `analysis/`
interprets those values (plus news and market state) into a single
standardized `AnalysisResult` -- without deciding what to do about it
(that decision belongs to the future `strategies/` package).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from analysis.context import AnalysisContext
from analysis.exceptions import InvalidAnalysisContextError
from analysis.result import AnalysisResult


class BaseAnalyzer(ABC):
    """
    Abstract base class for all analyzers.

    A concrete analyzer consumes an `AnalysisContext` (market state,
    indicators, news, symbol, timeframe) and produces a single
    `AnalysisResult`. Concrete analyzers must not generate trading
    signals or decisions -- that is the responsibility of the future
    `signals/` and `strategies/` packages.

    Attributes:
        name: Human-readable name of this analyzer instance, used to
            populate `AnalysisResult.analyzer_name`. Defaults to the
            concrete class name.
    """

    def __init__(self, name: Optional[str] = None) -> None:
        self.name = name or self.__class__.__name__

    # ------------------------------------------------------------------
    # Abstract API
    # ------------------------------------------------------------------
    @abstractmethod
    def analyze(self, context: AnalysisContext) -> AnalysisResult:
        """
        Analyze `context` and return a single `AnalysisResult`.

        Implementations should call `self.validate_context(context)`
        first, and are expected to raise `analysis.exceptions.
        InsufficientDataError` when `context` does not carry enough data
        (e.g. a required indicator is missing) to produce a meaningful
        result.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def validate_context(self, context: AnalysisContext) -> AnalysisContext:
        """
        Validate that `context` is a usable `AnalysisContext` for this analyzer.

        Raises:
            InvalidAnalysisContextError: If `context` is not an
                `AnalysisContext` instance.
        """
        if not isinstance(context, AnalysisContext):
            raise InvalidAnalysisContextError(
                f"{self.name} expected an AnalysisContext, got {type(context).__name__}"
            )
        return context

    def _build_result(
        self,
        context: AnalysisContext,
        *,
        score: float,
        confidence: float,
        summary: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AnalysisResult:
        """
        Build an `AnalysisResult` for `context` using this analyzer's `name`.

        Convenience helper so concrete analyzers don't repeat
        `analyzer_name`/`symbol`/`timeframe` wiring on every `analyze()`
        implementation.
        """
        return AnalysisResult(
            analyzer_name=self.name,
            symbol=context.symbol,
            timeframe=context.timeframe,
            score=score,
            confidence=confidence,
            summary=summary,
            metadata=metadata or {},
        )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.__class__.__name__}(name={self.name!r})"
