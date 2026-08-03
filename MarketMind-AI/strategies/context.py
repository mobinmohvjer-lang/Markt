"""
strategies/context.py

Defines `StrategyContext`: the immutable bundle of data every
`BaseStrategy` needs in order to produce a `StrategyResult` for one
symbol/timeframe.

`StrategyContext` composes the already-standardized outputs of the
three engines built so far -- `analysis.result.AnalysisResult`
(Analysis Engine), `signals.result.SignalResult` (Signal Engine), and
`strategies.risk_management.result.RiskResult` (Risk Engine) -- without
introducing any new domain concepts, keeping the Dependency Rule intact
(`strategies` -> `core`, `analysis`, `signals`, `events`; its own
`risk_management` subpackage is a sibling within the same top-level
package, not an outer-layer import).

Pure data container -- no strategy/decision logic. Assembling a
`StrategyContext` from real, end-to-end engine output remains a future
`app/` use case, the same gap `AnalysisContext`/`SignalContext`/
`RiskContext` already document.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from analysis.result import AnalysisResult
from signals.result import SignalResult
from strategies.risk_management.result import RiskResult

from strategies.exceptions import InvalidStrategyContextError, StrategyValidationError
from strategies.utils import validate_instance_list, validate_non_empty_str


@dataclass(frozen=True)
class StrategyContext:
    """
    Everything a `BaseStrategy` needs to decide on one symbol/timeframe.

    Attributes:
        symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").
        timeframe: Candle interval this context is framed around
            (e.g. "1h").
        analysis_results: `AnalysisResult` objects available for this
            symbol/timeframe -- individual `analysis.technical`
            analyzer outputs, the merged `AnalysisAggregator` output,
            or both, since both are the same `AnalysisResult` type.
        signal_result: The standardized `SignalResult` produced by the
            Signal Engine for this symbol/timeframe, if available. Its
            absence only limits what a strategy can decide -- it never
            invalidates the context.
        risk_result: The standardized `RiskResult` produced by the Risk
            Engine for this symbol/timeframe, if available. Its absence
            only limits what a strategy can decide -- it never
            invalidates the context.
        metadata: Free-form additional context supplied by the caller
            (e.g. upstream identifiers), kept for traceability. Not
            interpreted here.
    """

    symbol: str
    timeframe: str
    analysis_results: list[AnalysisResult] = field(default_factory=list)
    signal_result: Optional[SignalResult] = None
    risk_result: Optional[RiskResult] = None
    metadata: dict[str, Any] = field(default_factory=dict)

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
        except StrategyValidationError as exc:
            raise InvalidStrategyContextError(str(exc)) from exc

        if self.signal_result is not None and not isinstance(self.signal_result, SignalResult):
            raise InvalidStrategyContextError(
                f"signal_result must be a SignalResult or None, "
                f"got {type(self.signal_result).__name__}"
            )
        if self.risk_result is not None and not isinstance(self.risk_result, RiskResult):
            raise InvalidStrategyContextError(
                f"risk_result must be a RiskResult or None, got {type(self.risk_result).__name__}"
            )
        if not isinstance(self.metadata, dict):
            raise InvalidStrategyContextError(
                f"metadata must be a dict, got {type(self.metadata).__name__}"
            )

    def get_analysis_result(self, analyzer_name: str) -> Optional[AnalysisResult]:
        """
        Return the first `AnalysisResult` whose `analyzer_name` matches,
        or `None` if no such result is present in this context.
        """
        for result in self.analysis_results:
            if result.analyzer_name == analyzer_name:
                return result
        return None

    def has_analysis_results(self) -> bool:
        """Whether this context carries any `AnalysisResult`s."""
        return len(self.analysis_results) > 0

    def has_signal_result(self) -> bool:
        """Whether this context carries a `SignalResult`."""
        return self.signal_result is not None

    def has_risk_result(self) -> bool:
        """Whether this context carries a `RiskResult`."""
        return self.risk_result is not None
