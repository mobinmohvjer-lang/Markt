"""
analysis/context.py

Defines `AnalysisContext`: the immutable bundle of data every
`BaseAnalyzer` needs in order to produce an `AnalysisResult` for one
symbol/timeframe.

`AnalysisContext` only composes entities that already exist in `core/`
(`MarketState`, `IndicatorResult`, `NewsItem`) -- it introduces no new
domain concepts, keeping the Dependency Rule intact
(`analysis` -> `core`, never the reverse).

Pure data container -- no fetching, no aggregation logic. Assembling an
`AnalysisContext` from live data is the responsibility of a future
`app/` use case.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.entities.indicator_result import IndicatorResult
from core.entities.market_state import MarketState
from core.entities.news_item import NewsItem

from analysis.exceptions import AnalysisValidationError, InvalidAnalysisContextError
from analysis.utils import validate_instance_list, validate_non_empty_str


@dataclass(frozen=True)
class AnalysisContext:
    """
    Everything a `BaseAnalyzer` needs to analyze one symbol/timeframe.

    Attributes:
        symbol: Trading pair/instrument identifier (e.g. "BTCUSDT").
        timeframe: Candle interval this context is framed around
            (e.g. "1h").
        market_state: Aggregated, point-in-time market snapshot (latest
            candle, ticker, order book, recent trades, ...).
        indicators: Precomputed technical indicator results available to
            the analyzer for this symbol/timeframe.
        news: News items considered relevant to this analysis.
    """

    symbol: str
    timeframe: str
    market_state: MarketState
    indicators: list[IndicatorResult] = field(default_factory=list)
    news: list[NewsItem] = field(default_factory=list)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "symbol", validate_non_empty_str(self.symbol, name="symbol"))
            object.__setattr__(
                self, "timeframe", validate_non_empty_str(self.timeframe, name="timeframe")
            )
            object.__setattr__(
                self,
                "indicators",
                validate_instance_list(self.indicators, IndicatorResult, name="indicators"),
            )
            object.__setattr__(
                self, "news", validate_instance_list(self.news, NewsItem, name="news")
            )
        except AnalysisValidationError as exc:
            raise InvalidAnalysisContextError(str(exc)) from exc

        if not isinstance(self.market_state, MarketState):
            raise InvalidAnalysisContextError(
                f"market_state must be a MarketState, got {type(self.market_state).__name__}"
            )

    def get_indicator(self, indicator_name: str) -> IndicatorResult | None:
        """
        Return the first `IndicatorResult` whose `indicator_name` matches,
        or `None` if no such indicator is present in this context.
        """
        for indicator in self.indicators:
            if indicator.indicator_name == indicator_name:
                return indicator
        return None

    def has_news(self) -> bool:
        """Whether this context carries any news items."""
        return len(self.news) > 0
