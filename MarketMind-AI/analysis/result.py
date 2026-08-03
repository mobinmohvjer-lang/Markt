"""
analysis/result.py

Defines `AnalysisResult`: the standardized output produced by every
`BaseAnalyzer.analyze()` call, regardless of whether the concrete
analyzer is technical, news-based, or AI-based.

Pure data container -- no calculation, no interpretation logic. This
lets `signals/` (a future consumer) depend on one stable shape instead
of a different result type per analyzer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from analysis.utils import (
    merge_metadata,
    utcnow,
    validate_confidence,
    validate_non_empty_str,
    validate_score,
)


@dataclass(frozen=True)
class AnalysisResult:
    """
    The standardized output of a single analyzer run.

    Attributes:
        analyzer_name: Name of the analyzer that produced this result
            (e.g. "TechnicalAnalyzer").
        symbol: Trading pair/instrument the analysis was performed for
            (e.g. "BTCUSDT").
        timeframe: Candle interval the analysis was performed on
            (e.g. "1h").
        score: Numeric assessment produced by the analyzer. Scale and
            meaning are analyzer-specific (e.g. -1.0..1.0 for
            bearish/bullish, or 0..100 for a strength score) and must be
            documented by each concrete analyzer.
        confidence: How confident the analyzer is in `score`, expressed
            as a float in the closed range [0.0, 1.0].
        summary: Short, human-readable explanation of the result.
        timestamp: When this result was produced. Defaults to the
            current UTC time if not provided.
        metadata: Analyzer-specific supporting details (e.g. parameters
            used, intermediate values), kept for traceability.
    """

    analyzer_name: str
    symbol: str
    timeframe: str
    score: float
    confidence: float
    summary: str
    timestamp: datetime = field(default_factory=utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # dataclass is frozen, so field re-assignment goes through
        # object.__setattr__ -- this only normalizes/validates values,
        # it never introduces new state.
        object.__setattr__(
            self, "analyzer_name", validate_non_empty_str(self.analyzer_name, name="analyzer_name")
        )
        object.__setattr__(self, "symbol", validate_non_empty_str(self.symbol, name="symbol"))
        object.__setattr__(
            self, "timeframe", validate_non_empty_str(self.timeframe, name="timeframe")
        )
        object.__setattr__(self, "summary", validate_non_empty_str(self.summary, name="summary"))
        object.__setattr__(self, "score", validate_score(self.score, name="score"))
        object.__setattr__(
            self, "confidence", validate_confidence(self.confidence, name="confidence")
        )
        if not isinstance(self.metadata, dict):
            raise TypeError(f"metadata must be a dict, got {type(self.metadata).__name__}")

    def with_metadata(self, **extra: Any) -> "AnalysisResult":
        """
        Return a new `AnalysisResult` with `extra` merged into `metadata`.

        Since `AnalysisResult` is immutable, this returns a new instance
        rather than mutating the existing one.
        """
        return AnalysisResult(
            analyzer_name=self.analyzer_name,
            symbol=self.symbol,
            timeframe=self.timeframe,
            score=self.score,
            confidence=self.confidence,
            summary=self.summary,
            timestamp=self.timestamp,
            metadata=merge_metadata(self.metadata, extra),
        )
