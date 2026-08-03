"""
signals/context.py

Defines `SignalContext`: the immutable bundle of data every
`BaseSignalGenerator` needs in order to produce a `SignalResult` for one
symbol/timeframe.

`SignalContext` consumes `AnalysisResult` objects produced by the
Analysis Engine (`analysis/`) -- individual `analysis.technical`
analyzer outputs, the merged `AnalysisAggregator` output, or both, since
both are the same `analysis.result.AnalysisResult` type. It introduces
no new domain concepts, keeping the Dependency Rule intact
(`signals` -> `analysis` -> `core`, never the reverse).

Pure data container -- no signal-generation logic. Assembling a
`SignalContext` from analyzer output is the responsibility of a future
`app/` use case.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from analysis.result import AnalysisResult

from signals.exceptions import InvalidSignalContextError, SignalValidationError
from signals.utils import validate_instance_list, validate_non_empty_str


@dataclass(frozen=True)
class SignalContext:
    """
    Everything a `BaseSignalGenerator` needs to generate a signal for one
    symbol/timeframe.

    Attributes:
        symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").
        timeframe: Candle interval this context is framed around
            (e.g. "1h").
        analysis_results: `AnalysisResult` objects available to the
            generator for this symbol/timeframe -- typically one or more
            individual `analysis.technical` analyzer outputs, the merged
            `AnalysisAggregator` output, or both.
    """

    symbol: str
    timeframe: str
    analysis_results: list[AnalysisResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "symbol", validate_non_empty_str(self.symbol, name="symbol"))
            object.__setattr__(
                self, "timeframe", validate_non_empty_str(self.timeframe, name="timeframe")
            )
            object.__setattr__(
                self,
                "analysis_results",
                validate_instance_list(
                    self.analysis_results, AnalysisResult, name="analysis_results"
                ),
            )
        except SignalValidationError as exc:
            raise InvalidSignalContextError(str(exc)) from exc

    def get_result(self, analyzer_name: str) -> AnalysisResult | None:
        """
        Return the first `AnalysisResult` whose `analyzer_name` matches,
        or `None` if no such result is present in this context.
        """
        for result in self.analysis_results:
            if result.analyzer_name == analyzer_name:
                return result
        return None

    def has_results(self) -> bool:
        """Whether this context carries any `AnalysisResult`s."""
        return len(self.analysis_results) > 0
