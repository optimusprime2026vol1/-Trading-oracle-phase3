"""
Moving Average Convergence Divergence (MACD).

Master spec reference: section 6 -- "MACD | 12 / 26 / 9, EMA-based,
histogram = MACD - signal."

Spec section 6.1 gives an explicit warm-up rule for EMA generally ("EMA(n):
minimum 3n bars before the value is trusted") but does not give a specific
number for MACD itself, since MACD is composite (spec: "EMA-based"). This
module applies that same 3n rule to each EMA MACD is built from:

  - macd_line is trusted once its slower/dominant component (the 26-EMA)
    would itself be trusted on its own: index >= 3*slow - 1.
  - signal_line (itself an EMA, of the MACD line) is trusted once *it*
    has seen 3*signal genuine MACD-line inputs, counting from the first
    index the raw MACD line exists (slow - 1).

These are documented, reasoned extensions of the spec's stated rule, not
arbitrary numbers -- see MacdResult docstring for the exact thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from src.data.contracts import Bar
from src.indicators._core import seeded_ema_series

DEFAULT_FAST = 12
DEFAULT_SLOW = 26
DEFAULT_SIGNAL = 9


@dataclass(frozen=True)
class MacdResult:
    macd_line: list[float | None]
    signal_line: list[float | None]
    histogram: list[float | None]


def macd(
    bars: Sequence[Bar],
    fast: int = DEFAULT_FAST,
    slow: int = DEFAULT_SLOW,
    signal: int = DEFAULT_SIGNAL,
) -> MacdResult:
    if fast >= slow:
        raise ValueError("fast period must be less than slow period")

    n = len(bars)
    closes = [b.close for b in bars]

    raw_fast = seeded_ema_series(closes, fast)
    raw_slow = seeded_ema_series(closes, slow)

    raw_macd: list[float | None] = [None] * n
    for i in range(n):
        if raw_fast[i] is not None and raw_slow[i] is not None:
            raw_macd[i] = raw_fast[i] - raw_slow[i]

    slow_start = slow - 1  # raw_macd is dense (no gaps) from here onward
    dense_macd = [v for v in raw_macd[slow_start:] if v is not None]
    raw_signal_dense = seeded_ema_series(dense_macd, signal)

    raw_signal: list[float | None] = [None] * n
    for j, v in enumerate(raw_signal_dense):
        raw_signal[slow_start + j] = v

    macd_trust_from = 3 * slow - 1
    signal_trust_from = slow_start + (3 * signal - 1)

    macd_line: list[float | None] = [None] * n
    signal_line: list[float | None] = [None] * n
    histogram: list[float | None] = [None] * n

    for i in range(n):
        if i >= macd_trust_from:
            macd_line[i] = raw_macd[i]
        if i >= signal_trust_from:
            signal_line[i] = raw_signal[i]
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram[i] = macd_line[i] - signal_line[i]

    return MacdResult(macd_line=macd_line, signal_line=signal_line, histogram=histogram)
