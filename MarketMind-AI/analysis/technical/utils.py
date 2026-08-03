"""
analysis/technical/utils.py

Shared, dependency-light math helpers used by the concrete technical
analyzers in this package (`TrendAnalyzer`, `MomentumAnalyzer`, and any
future addition to `analysis/technical/`).

These are intentionally separate from `analysis/utils.py`: the parent
module's helpers are generic validation/formatting utilities used by the
Analysis Engine foundation (Part 1) and must not be touched by this
package. Everything here is specific to turning raw indicator values
into a bounded `[-1.0, 1.0]` score / `[0.0, 1.0]` confidence -- the
concern of concrete technical analyzers (Part 2), not the foundation.

No trading/AI/signal logic lives here -- only small, pure, unit-tested
numeric helpers.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence


def clip(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    """Clamp `value` to the closed range `[lo, hi]`."""
    if lo > hi:
        raise ValueError(f"lo ({lo}) must be <= hi ({hi})")
    return max(lo, min(hi, float(value)))


def normalize_diff(fast: float, slow: float) -> float:
    """
    Score the relationship between a "fast" and a "slow" value (e.g. a
    fast/slow moving average pair, or a MACD line vs. its signal line)
    as a bounded `[-1.0, 1.0]` trend score.

    Computed as the relative difference `(fast - slow) / abs(slow)`,
    clipped to `[-1.0, 1.0]`. A positive score means `fast` is above
    `slow` (bullish relationship); negative means `fast` is below `slow`
    (bearish relationship).

    When `slow` is exactly `0.0` (relative difference is undefined), the
    score falls back to the sign of `fast - slow` (`1.0`, `-1.0`, or
    `0.0`), so the function never raises or returns a non-finite value.
    """
    diff = float(fast) - float(slow)
    if slow == 0:
        if diff > 0:
            return 1.0
        if diff < 0:
            return -1.0
        return 0.0
    return clip(diff / abs(float(slow)))


def normalize_center(value: float, *, center: float = 50.0, scale: float = 50.0) -> float:
    """
    Score a bounded oscillator reading (e.g. RSI, Stochastic `%K`/`%D`,
    typically on a `0..100` scale) as a `[-1.0, 1.0]` momentum score.

    Computed as `(value - center) / scale`, clipped to `[-1.0, 1.0]`.
    With the defaults (`center=50.0`, `scale=50.0`), a reading of `100`
    maps to `+1.0` (strong bullish momentum), `0` maps to `-1.0` (strong
    bearish momentum), and `50` maps to `0.0` (neutral).

    Raises:
        ValueError: If `scale` is `0`.
    """
    if scale == 0:
        raise ValueError("scale must be non-zero")
    return clip((float(value) - center) / scale)


def normalize_scaled(value: float, scale: float) -> float:
    """
    Score an unbounded, unit-dependent reading (e.g. ROC as a percentage,
    or a MACD histogram value) as a `[-1.0, 1.0]` momentum score.

    Computed as `value / scale`, clipped to `[-1.0, 1.0]`. `scale`
    represents "the magnitude that counts as a full-strength (+/-1.0)
    reading" and is caller/analyzer-configurable since it is inherently
    unit- and asset-dependent (e.g. a MACD histogram of `50` means very
    different things for a $1 altcoin vs. BTC).

    Raises:
        ValueError: If `scale` is `0`.
    """
    if scale == 0:
        raise ValueError("scale must be non-zero")
    return clip(float(value) / float(scale))


def weighted_average(components: Sequence[tuple[float, float]]) -> float:
    """
    Combine `(score, weight)` pairs into a single weighted-average score.

    Returns `0.0` (neutral) if `components` is empty or every weight is
    `0.0`, rather than raising a division-by-zero error.
    """
    total_weight = sum(weight for _, weight in components)
    if total_weight == 0:
        return 0.0
    return sum(score * weight for score, weight in components) / total_weight


def mean_abs(values: Iterable[float]) -> float:
    """
    Return the mean of the absolute values in `values` ("conviction"):
    how far, on average, a set of `[-1.0, 1.0]` component scores lean
    away from neutral, regardless of direction.

    Returns `0.0` for an empty input.
    """
    values = list(values)
    if not values:
        return 0.0
    return sum(abs(v) for v in values) / len(values)


def completeness_ratio(available: int, expected: int) -> float:
    """
    Fraction of expected inputs that were actually available, clipped to
    `[0.0, 1.0]`. Used as a confidence multiplier: an analyzer that only
    had 1 of 4 expected indicators should never report high confidence.

    Returns `0.0` if `expected <= 0`.
    """
    if expected <= 0:
        return 0.0
    return clip(available / expected, 0.0, 1.0)


def score_label(score: float) -> str:
    """
    Translate a `[-1.0, 1.0]` score into a short, human-readable label
    for use in `AnalysisResult.summary` text.

    Thresholds: `>= 0.5` strong bullish, `>= 0.15` mild bullish,
    `> -0.15` neutral, `> -0.5` mild bearish, otherwise strong bearish.
    """
    if score >= 0.5:
        return "strong bullish"
    if score >= 0.15:
        return "mild bullish"
    if score > -0.15:
        return "neutral"
    if score > -0.5:
        return "mild bearish"
    return "strong bearish"


def is_finite_number(value: object) -> bool:
    """Whether `value` is an `int`/`float` (excluding `bool`) and finite."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))
