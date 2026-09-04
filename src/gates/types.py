"""
Shared types for the pre-flight gates.

Master spec reference: TRADING_ORACLE_v2_MASTER_SPEC.md, section 4
(Pre-flight Gates): "Deterministic boolean checks. All must return TRUE or
the system returns a NO-TRADE code. These run in Python before any
strategy is consulted."

`GateCode` is the exact 13-row table from section 4 -- the fail code is
part of the spec's contract (it shows up in the output schema, section 13),
so these string values must match verbatim, not be paraphrased.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class GateCode(str, Enum):
    """The 13 fail codes from spec section 4, in table order."""

    STALE_DATA = "STALE_DATA"
    DATA_INTEGRITY_FAIL = "DATA_INTEGRITY_FAIL"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    SYMBOL_RESTRICTED = "SYMBOL_RESTRICTED"
    SURVEILLANCE_LIST = "SURVEILLANCE_LIST"
    ILLIQUID = "ILLIQUID"
    WIDE_SPREAD = "WIDE_SPREAD"
    OUTSIDE_WINDOW = "OUTSIDE_WINDOW"
    EVENT_RISK = "EVENT_RISK"
    RISK_LIMIT_HIT = "RISK_LIMIT_HIT"
    EXPOSURE_FULL = "EXPOSURE_FULL"
    RR_BELOW_MIN = "RR_BELOW_MIN"
    COOLDOWN_ACTIVE = "COOLDOWN_ACTIVE"


# Gate table order (spec section 4, column "#") -- the runner evaluates and
# reports in exactly this order, since gate 1-3 (data-related) logically
# gate everything after them.
GATE_ORDER: tuple[GateCode, ...] = (
    GateCode.STALE_DATA,
    GateCode.DATA_INTEGRITY_FAIL,
    GateCode.INSUFFICIENT_HISTORY,
    GateCode.SYMBOL_RESTRICTED,
    GateCode.SURVEILLANCE_LIST,
    GateCode.ILLIQUID,
    GateCode.WIDE_SPREAD,
    GateCode.OUTSIDE_WINDOW,
    GateCode.EVENT_RISK,
    GateCode.RISK_LIMIT_HIT,
    GateCode.EXPOSURE_FULL,
    GateCode.RR_BELOW_MIN,
    GateCode.COOLDOWN_ACTIVE,
)


@dataclass(frozen=True)
class GateResult:
    """Outcome of one gate. `code` and `detail` are None/"" when passed --
    a passing gate has nothing to report."""

    gate: GateCode
    passed: bool
    detail: str = ""

    @staticmethod
    def ok(gate: GateCode) -> "GateResult":
        return GateResult(gate=gate, passed=True, detail="")

    @staticmethod
    def fail(gate: GateCode, detail: str) -> "GateResult":
        return GateResult(gate=gate, passed=False, detail=detail)


@dataclass(frozen=True)
class GateReport:
    """Full result of running all 13 gates, in spec table order.

    `passed` is True only if every gate passed. `first_failure` is the
    lowest-numbered failing gate -- the one that determines the NO-TRADE
    code (spec section 14) -- but `results` retains every gate's outcome
    so a dashboard (Phase 12) can show which checks are currently healthy
    even when one has failed.
    """

    results: tuple[GateResult, ...]
    passed: bool
    first_failure: GateResult | None


# --- small input dataclasses shared by multiple gates -----------------------


@dataclass(frozen=True)
class RestrictionStatus:
    """Spec 4 gate 4 / 5.3: exchange-level trading restrictions on a symbol."""

    is_halted: bool = False
    at_circuit_limit: bool = False


@dataclass(frozen=True)
class SurveillanceStatus:
    """Spec 4 gate 5 / 5.3: SEBI/exchange surveillance framework membership."""

    in_asm: bool = False
    in_gsm: bool = False
    in_t2t: bool = False  # spec 5.3: "Trade-to-trade (T2T) segment -- intraday not allowed"


@dataclass(frozen=True)
class LiquidityMetrics:
    """Spec 4 gate 6 / 5.4: liquidity floor inputs for one symbol."""

    avg_traded_value_20d_inr: float
    avg_bar_volume: float
    candidate_position_value_inr: float | None = None
    avg_daily_traded_value_inr: float | None = None


@dataclass(frozen=True)
class ExposureState:
    """Spec 4 gate 11 / section 9: current portfolio exposure, for checking
    against config caps before adding a new position."""

    open_positions_count: int
    sector_exposure_pct: dict[str, float]
    candidate_sector: str


@dataclass(frozen=True)
class RiskState:
    """Spec 4 gate 10 / section 9: today's paper-trading P&L state."""

    daily_pnl_inr: float
    paper_capital_inr: float


@dataclass(frozen=True)
class TradingWindow:
    """Spec 5.1 session map, resolved to today's concrete clock times."""

    normal_open: datetime
    square_off_time: datetime
    no_new_entry_buffer_minutes: int
