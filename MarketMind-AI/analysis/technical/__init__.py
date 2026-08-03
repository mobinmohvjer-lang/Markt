"""
analysis/technical package
---------------------------
Purpose:
    Analysis Engine Parts 2, 3A, 3B, and 3C -- the concrete, real
    analyzers. Interprets indicator (or, for Part 3C, swing-point) data
    already computed elsewhere into standardized
    `analysis.AnalysisResult` objects. No AI, no news, no signal
    generation, no trading decisions: those remain the responsibility
    of `analysis/ai/`, `analysis/news/`, `signals/`, and `strategies/`
    respectively (all still unbuilt).

Contents:
    - utils.py: shared, dependency-light score/confidence normalization
      helpers used by every analyzer in this package (`clip`,
      `normalize_diff`, `normalize_center`, `normalize_scaled`,
      `weighted_average`, `mean_abs`, `completeness_ratio`,
      `score_label`).
    - trend_analyzer.py: `TrendAnalyzer` -- interprets SMA/EMA
      relationships, MACD, and ADX into a single trend `AnalysisResult`.
    - momentum_analyzer.py: `MomentumAnalyzer` -- interprets RSI, ROC,
      Stochastic, and the MACD histogram into a single momentum
      `AnalysisResult`.
    - volatility_analyzer.py: `VolatilityAnalyzer` (Part 3A) --
      interprets ATR, Bollinger Bands, Keltner Channel, and Donchian
      Channel into a single volatility-regime `AnalysisResult` (score
      measures expansion/contraction, not bullish/bearish direction).
    - volume_analyzer.py: `VolumeAnalyzer` (Part 3B) -- interprets OBV,
      VWAP, and Volume SMA (plus the latest candle already carried on
      `AnalysisContext.market_state`) into a single volume
      `AnalysisResult` (score measures bullish/bearish volume flow,
      alongside confirmation/divergence, buying/selling pressure,
      volume trend, participation strength, and price-vs-VWAP metadata).
    - market_structure_analyzer.py: `MarketStructureAnalyzer` (Part 3C)
      -- interprets swing-point structure (plus the latest candle
      already carried on `AnalysisContext.market_state`) into a single
      market-structure `AnalysisResult` (score measures bullish/bearish
      structure, alongside HH/HL/LH/LL classification, swing high/low
      values, BOS, CHOCH, trend continuation/reversal, and market
      regime).

All five analyzers subclass `analysis.base.BaseAnalyzer` and are fully
independent of each other -- none imports or depends on another.

This package does not modify, import into, or re-export through
`analysis/__init__.py` (the Part 1 foundation package init); import
directly from here, e.g.:

    from analysis.technical import (
        TrendAnalyzer,
        MomentumAnalyzer,
        VolatilityAnalyzer,
        VolumeAnalyzer,
        MarketStructureAnalyzer,
    )
"""

from __future__ import annotations

from analysis.technical.market_structure_analyzer import MarketStructureAnalyzer
from analysis.technical.momentum_analyzer import MomentumAnalyzer
from analysis.technical.trend_analyzer import TrendAnalyzer
from analysis.technical.volatility_analyzer import VolatilityAnalyzer
from analysis.technical.volume_analyzer import VolumeAnalyzer

__all__ = [
    "TrendAnalyzer",
    "MomentumAnalyzer",
    "VolatilityAnalyzer",
    "VolumeAnalyzer",
    "MarketStructureAnalyzer",
]
