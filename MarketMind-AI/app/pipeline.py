"""
app/pipeline.py

Defines `MarketPipeline`: the first concrete `app/`-layer use case. It
wires four already-implemented layers together, in this fixed order,
for one symbol/timeframe:

    1. Data       -- `data.engine.DataEngine.load_history()` loads
                      already-downloaded candles.
    2. Indicators -- a configurable set of `indicators.BaseIndicator`
                      instances (defaulting to exactly the indicator
                      names `analysis.technical`'s five analyzers
                      already expect by default -- see
                      `docs/ARCHITECTURE.md`/`PROJECT_STATE.md`) is run
                      once over that candle history; the latest value
                      of each becomes a
                      `core.entities.indicator_result.IndicatorResult`.
    3. Analysis   -- those `IndicatorResult`s, plus a `MarketState`
                      snapshot built from the same candles, are
                      combined into an `analysis.context.AnalysisContext`
                      and run through an injected `analysis.base.
                      BaseAnalyzer` (defaults to
                      `analysis.aggregator.AnalysisAggregator`).
    4. Signals    -- the resulting `AnalysisResult` is wrapped into a
                      `signals.context.SignalContext` and run through
                      an injected `signals.base.BaseSignalGenerator`
                      (defaults to `signals.aggregator.SignalAggregator`).

Scope (deliberately bounded)
-----------------------------
Only the four stages above are wired. No `strategies/` (trading
decisions), no risk/portfolio management, no backtesting, no order
execution, no AI, no news -- those remain future `app/` use cases (see
`PROJECT_STATE.md`, open item 8). This module adds no new
calculation/interpretation/decision logic of its own: every stage's
actual work still happens inside the package that already owns it
(`indicators/`, `analysis/`, `signals/`); this only sequences the
existing calls, matching the "conductor" role `app/__init__.py`
already documents.

Placement note -- why `app/`, not `services/`
------------------------------------------------
This orchestration lives in `app/`, not `services/`, because
`PROJECT_RULES.md` Section 4's dependency table only allows `services/`
to import `core`/`events` -- it may not import `data`, `indicators`,
`analysis`, or `signals` at all. `app/` is the one layer explicitly
allowed to import all of the above, and its documented role
(`app/__init__.py`) is exactly this "when and in what order" wiring.
Connecting Data -> Indicators -> Analysis -> Signals inside `services/`
would violate the Dependency Rule (`PROJECT_RULES.md` Section 1.1)
this project already enforces elsewhere.

Two different, unrelated "Part 2B"s
--------------------------------------
`PROJECT_STATE.md` already uses the name "Services Part 2B" for a
different, narrower piece of unfinished work: giving
`services.signal_engine.SignalEngine.execute()` a real body (build/
validate a `core.entities.signal.Signal` from `ServiceContext.payload`,
apply `SignalEngine.config`, publish via an injected `EventBus`, return
a `ServiceResult`). That work is untouched by this module -- `services/`
is not imported here, and `SignalEngine.execute()` still raises
`NotImplementedError` exactly as Part 2A left it. This module instead
implements the pipeline-wiring task requested, in the layer where that
task belongs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional, Sequence

import pandas as pd

from analysis.aggregator import AnalysisAggregator
from analysis.base import BaseAnalyzer
from analysis.context import AnalysisContext
from analysis.exceptions import AnalysisError
from analysis.result import AnalysisResult

from core.entities.candle import Candle as CoreCandle
from core.entities.indicator_result import IndicatorResult as CoreIndicatorResult
from core.entities.market_state import MarketState

from data.engine import DataEngine
from data.models import Candle as DataCandle

from indicators.base import BaseIndicator
from indicators.adx import ADX
from indicators.atr import ATR
from indicators.bollinger_bands import BollingerBands
from indicators.donchian_channel import DonchianChannel
from indicators.ema import EMA
from indicators.keltner_channel import KeltnerChannel
from indicators.macd import MACD
from indicators.obv import OBV
from indicators.roc import ROC
from indicators.rsi import RSI
from indicators.sma import SMA
from indicators.stochastic import Stochastic
from indicators.vwap import VWAP
from indicators.volume_sma import VolumeSMA

from signals.aggregator import SignalAggregator
from signals.base import BaseSignalGenerator
from signals.context import SignalContext
from signals.exceptions import SignalError
from signals.result import SignalResult

from app.exceptions import (
    PipelineAnalysisError,
    PipelineConfigurationError,
    PipelineDataError,
    PipelineSignalError,
)


def _default_indicator_specs() -> list[tuple[BaseIndicator, dict[str, str]]]:
    """
    Build a fresh set of indicator instances (never shared across
    `MarketPipeline` instances, so no incremental state leaks between
    runs), paired with the extra `calculate()` kwargs each one needs
    when fed a single OHLCV `pandas.DataFrame`.

    Names/defaults match exactly what `analysis.technical`'s five
    analyzers already look for by default (`SMA_20`/`SMA_50`,
    `EMA_12`/`EMA_26`, `MACD_12_26_9`, `ADX_14`, `RSI_14`, `ROC_12`,
    `Stochastic_14_3`, `ATR_14`, `BollingerBands_20`,
    `KeltnerChannel_20`, `DonchianChannel_20`, `OBV_1`, `VWAP_14`,
    `VolumeSMA_20`) -- see each analyzer's module docstring.
    """
    return [
        (SMA(20), {"column": "close"}),
        (SMA(50), {"column": "close"}),
        (EMA(12), {"column": "close"}),
        (EMA(26), {"column": "close"}),
        (MACD(), {"column": "close"}),
        (ADX(14), {}),
        (RSI(14), {"column": "close"}),
        (ROC(12), {"column": "close"}),
        (Stochastic(14, 3), {}),
        (ATR(14), {}),
        (BollingerBands(20), {"column": "close"}),
        (KeltnerChannel(20), {}),
        (DonchianChannel(20), {}),
        (OBV(), {}),
        (VWAP(14), {}),
        (VolumeSMA(20), {}),
    ]


def _candles_to_dataframe(candles: Sequence[DataCandle]) -> pd.DataFrame:
    """Build the single OHLCV `DataFrame` every indicator is run against."""
    return pd.DataFrame(
        {
            "open": [c.open for c in candles],
            "high": [c.high for c in candles],
            "low": [c.low for c in candles],
            "close": [c.close for c in candles],
            "volume": [c.volume for c in candles],
        }
    )


def _to_core_candle(candle: DataCandle) -> CoreCandle:
    """Translate a `data.models.Candle` (float/epoch-ms) into a `core.entities.candle.Candle` (Decimal/datetime)."""
    return CoreCandle(
        symbol=candle.symbol,
        timeframe=candle.timeframe,
        open_time=datetime.fromtimestamp(candle.open_time / 1000, tz=timezone.utc),
        close_time=datetime.fromtimestamp(candle.close_time / 1000, tz=timezone.utc),
        open=Decimal(str(candle.open)),
        high=Decimal(str(candle.high)),
        low=Decimal(str(candle.low)),
        close=Decimal(str(candle.close)),
        volume=Decimal(str(candle.volume)),
        quote_volume=Decimal(str(candle.quote_volume)) if candle.quote_volume else None,
        number_of_trades=candle.trades or None,
    )


def _to_core_indicator_result(
    raw_result: Any, *, symbol: str, timeframe: str, timestamp: datetime
) -> CoreIndicatorResult:
    """
    Translate an `indicators.base.IndicatorResult` (numpy-backed, whole
    history) into a `core.entities.indicator_result.IndicatorResult`
    (a single point-in-time reading), taking the latest value(s).
    """
    if raw_result.is_multi_output:
        values = {key: float(arr[-1]) for key, arr in raw_result.values.items()}
    else:
        values = {"value": float(raw_result.values[-1])}

    return CoreIndicatorResult(
        indicator_name=raw_result.name,
        symbol=symbol,
        timeframe=timeframe,
        timestamp=timestamp,
        values=values,
        parameters=dict(raw_result.metadata),
    )


@dataclass(frozen=True)
class PipelineResult:
    """
    Everything produced by one `MarketPipeline.run()` call, one entry
    per stage, for traceability.

    Attributes:
        symbol: Trading pair/instrument the pipeline ran for.
        timeframe: Candle interval the pipeline ran on.
        candle_count: Number of candles the Data stage loaded.
        market_state: The `MarketState` snapshot assembled from those
            candles (Data stage output, consumed by Analysis).
        indicator_results: `IndicatorResult`s successfully computed by
            the Indicators stage.
        indicator_errors: `{indicator_name: error message}` for any
            configured indicator that failed to compute (e.g. not
            enough candle history) -- mirrors the "absence only lowers
            confidence" convention `AnalysisAggregator` already uses,
            rather than failing the whole pipeline over one indicator.
        analysis_result: The Analysis stage's merged `AnalysisResult`.
        signal_result: The Signals stage's final `SignalResult`.
    """

    symbol: str
    timeframe: str
    candle_count: int
    market_state: MarketState
    indicator_results: list[CoreIndicatorResult]
    indicator_errors: dict[str, str]
    analysis_result: AnalysisResult
    signal_result: SignalResult
    metadata: dict[str, Any] = field(default_factory=dict)


class MarketPipeline:
    """
    Runs Data -> Indicators -> Analysis -> Signals for one
    symbol/timeframe, using dependency injection for every stage
    (matching this project's DI convention -- see `PROJECT_RULES.md`
    Section 5).
    """

    def __init__(
        self,
        data_engine: DataEngine,
        *,
        indicator_specs: Optional[Sequence[tuple[BaseIndicator, dict[str, str]]]] = None,
        analyzer: Optional[BaseAnalyzer] = None,
        signal_generator: Optional[BaseSignalGenerator] = None,
    ) -> None:
        if not isinstance(data_engine, DataEngine):
            raise PipelineConfigurationError(
                f"data_engine must be a DataEngine, got {type(data_engine).__name__}"
            )
        self.data_engine = data_engine

        specs = list(indicator_specs) if indicator_specs is not None else _default_indicator_specs()
        for indicator, kwargs in specs:
            if not isinstance(indicator, BaseIndicator):
                raise PipelineConfigurationError(
                    f"indicator_specs entries must wrap a BaseIndicator, got {type(indicator).__name__}"
                )
            if not isinstance(kwargs, dict):
                raise PipelineConfigurationError(
                    f"indicator_specs kwargs must be a dict, got {type(kwargs).__name__}"
                )
        self.indicator_specs = specs

        self.analyzer = analyzer if analyzer is not None else AnalysisAggregator()
        if not isinstance(self.analyzer, BaseAnalyzer):
            raise PipelineConfigurationError(
                f"analyzer must be a BaseAnalyzer, got {type(self.analyzer).__name__}"
            )

        self.signal_generator = signal_generator if signal_generator is not None else SignalAggregator()
        if not isinstance(self.signal_generator, BaseSignalGenerator):
            raise PipelineConfigurationError(
                f"signal_generator must be a BaseSignalGenerator, got {type(self.signal_generator).__name__}"
            )

    def run(self, symbol: str, timeframe: str, *, limit: Optional[int] = None) -> PipelineResult:
        """
        Execute the full pipeline for one symbol/timeframe.

        Parameters
        ----------
        symbol, timeframe:
            Identify which already-downloaded candle series to run
            against (see `DataEngine.download_history`/`update_latest`).
        limit:
            Optional cap on how many of the most recent candles to load
            (forwarded to `DataEngine.load_history`).

        Raises
        ------
        PipelineDataError
            No candle history is available for `symbol`/`timeframe`.
        PipelineAnalysisError
            The Analysis stage could not produce an `AnalysisResult`
            (wraps the underlying `analysis.exceptions.AnalysisError`).
        PipelineSignalError
            The Signals stage could not produce a `SignalResult` (wraps
            the underlying `signals.exceptions.SignalError`).
        """
        if not isinstance(symbol, str) or not symbol.strip():
            raise PipelineConfigurationError(f"symbol must be a non-empty str, got {symbol!r}")
        if not isinstance(timeframe, str) or not timeframe.strip():
            raise PipelineConfigurationError(f"timeframe must be a non-empty str, got {timeframe!r}")
        symbol = symbol.upper()

        # 1. Data
        candles = self.data_engine.load_history(symbol, timeframe, limit=limit)
        if not candles:
            raise PipelineDataError(
                f"No candle history available for {symbol}/{timeframe}; "
                "download/update it via DataEngine first."
            )
        core_candles = [_to_core_candle(candle) for candle in candles]
        latest_timestamp = core_candles[-1].close_time

        # 2. Indicators
        frame = _candles_to_dataframe(candles)
        indicator_results: list[CoreIndicatorResult] = []
        indicator_errors: dict[str, str] = {}
        for indicator, extra_kwargs in self.indicator_specs:
            try:
                raw_result = indicator.calculate(frame, **extra_kwargs)
                indicator_results.append(
                    _to_core_indicator_result(
                        raw_result, symbol=symbol, timeframe=timeframe, timestamp=latest_timestamp
                    )
                )
            except Exception as exc:  # noqa: BLE001 - one bad indicator must not sink the pipeline
                indicator_errors[indicator.name] = str(exc)

        market_state = MarketState(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=latest_timestamp,
            latest_candle=core_candles[-1],
            indicators=indicator_results,
        )

        # 3. Analysis
        analysis_context = AnalysisContext(
            symbol=symbol,
            timeframe=timeframe,
            market_state=market_state,
            indicators=indicator_results,
        )
        try:
            analysis_result = self.analyzer.analyze(analysis_context)
        except AnalysisError as exc:
            raise PipelineAnalysisError(str(exc)) from exc

        # 4. Signals
        signal_context = SignalContext(
            symbol=symbol,
            timeframe=timeframe,
            analysis_results=[analysis_result],
        )
        try:
            signal_result = self.signal_generator.generate(signal_context)
        except SignalError as exc:
            raise PipelineSignalError(str(exc)) from exc

        return PipelineResult(
            symbol=symbol,
            timeframe=timeframe,
            candle_count=len(core_candles),
            market_state=market_state,
            indicator_results=indicator_results,
            indicator_errors=indicator_errors,
            analysis_result=analysis_result,
            signal_result=signal_result,
        )
