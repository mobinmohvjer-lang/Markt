"""
analysis package
-----------------
Purpose:
    Contains all logic that transforms raw market/news data into
    actionable insights, WITHOUT deciding what to actually do about them
    (that decision belongs to `strategies`).

Contents (Analysis Engine Part 1 -- foundation only):
    - base.py: `BaseAnalyzer`, the abstract base every concrete analyzer
      implements.
    - context.py: `AnalysisContext`, the immutable bundle of
      `MarketState` / `IndicatorResult` / `NewsItem` (+ symbol,
      timeframe) an analyzer consumes.
    - result.py: `AnalysisResult`, the standardized output every
      analyzer produces (`score`, `confidence`, `summary`, `metadata`).
    - exceptions.py: the `AnalysisError` hierarchy.
    - utils.py: shared validation helpers used across the package.

Also contains (Analysis Engine Part 4 -- aggregation):
    - aggregator.py: `AnalysisAggregator`, which combines the five
      independent `analysis.technical` analyzer outputs (`TrendAnalyzer`,
      `MomentumAnalyzer`, `VolatilityAnalyzer`, `VolumeAnalyzer`,
      `MarketStructureAnalyzer`) into a single final `AnalysisResult`.
      Unlike `analysis/technical/`, `AnalysisAggregator` is re-exported
      here since it is itself part of the foundation-level public API
      (a `BaseAnalyzer` consumers can use directly), not a sibling
      technical analyzer.

Planned contents (future Analysis Engine parts):
    - news/: news sentiment analysis (free news sources + free NLP
      models) to gauge market mood.
    - ai/: AI-based analysis combining technical and news signals into
      a higher-level market assessment (e.g. using a free/local LLM).

No AI, no signal generation, no trading logic implemented yet -- this
package only defines the shared foundation concrete analyzers (and, as
of Part 4, their aggregation) build on.
"""

from __future__ import annotations

from analysis.aggregator import AnalysisAggregator
from analysis.base import BaseAnalyzer
from analysis.context import AnalysisContext
from analysis.exceptions import (
    AnalysisError,
    AnalysisValidationError,
    AnalyzerConfigurationError,
    InsufficientDataError,
    InvalidAnalysisContextError,
)
from analysis.result import AnalysisResult

__all__ = [
    "BaseAnalyzer",
    "AnalysisContext",
    "AnalysisResult",
    "AnalysisAggregator",
    "AnalysisError",
    "AnalysisValidationError",
    "InvalidAnalysisContextError",
    "InsufficientDataError",
    "AnalyzerConfigurationError",
]
