"""
Phase 3 exit criterion: Bollinger against population-stdev reference
(statistics.pstdev, not the sample-stdev stdev()) and warm-up gating.
"""

from __future__ import annotations

import statistics

import pytest

from tests.unit.indicator_test_helpers import make_bars
from src.indicators.bollinger import bollinger


def test_bollinger_matches_population_stdev_reference() -> None:
    closes = [100 + ((i * 17) % 13) - 6 for i in range(40)]
    bars = make_bars([float(c) for c in closes])
    result = bollinger(bars, period=20, num_std=2.0)

    for i in range(19, len(bars)):
        window = closes[i - 19 : i + 1]
        mean = statistics.mean(window)
        pstd = statistics.pstdev(window)  # population, matches spec "population sigma"
        assert result.middle[i] == pytest.approx(mean, abs=1e-9)
        assert result.upper[i] == pytest.approx(mean + 2 * pstd, abs=1e-9)
        assert result.lower[i] == pytest.approx(mean - 2 * pstd, abs=1e-9)


def test_bollinger_none_before_period_bars() -> None:
    closes = [100.0] * 25
    bars = make_bars(closes)
    result = bollinger(bars, period=20)
    assert all(v is None for v in result.middle[:19])
    assert all(v is not None for v in result.middle[19:])


def test_bollinger_bands_symmetric_around_middle() -> None:
    closes = [100 + ((i * 3) % 7) for i in range(30)]
    bars = make_bars([float(c) for c in closes])
    result = bollinger(bars, period=20)
    for i in range(19, len(bars)):
        upper_dist = result.upper[i] - result.middle[i]
        lower_dist = result.middle[i] - result.lower[i]
        assert upper_dist == pytest.approx(lower_dist, abs=1e-9)


def test_bollinger_zero_variance_gives_zero_width_bands() -> None:
    closes = [100.0] * 25
    bars = make_bars(closes)
    result = bollinger(bars, period=20)
    assert result.upper[-1] == pytest.approx(100.0)
    assert result.lower[-1] == pytest.approx(100.0)
