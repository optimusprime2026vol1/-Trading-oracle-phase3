"""
Gate runner: bundles every gate's inputs into one context object and runs
all 13 gates in spec section-4 table order.

Master spec reference: section 4 ("All must return TRUE or the system
returns a NO-TRADE code") and section 14 (NO-TRADE output uses the first
failing gate's code as the reason).

`evaluate_gates` always runs every gate, even after an earlier one fails --
so a health dashboard (Phase 12) can show the state of all 13 checks at
once, not just "blocked, reason unknown until you fix the first thing."
The NO-TRADE code a caller should actually emit is `report.first_failure`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.data.contracts import Bar
from src.gates import gates as g
from src.gates.types import (
    ExposureState,
    GateReport,
    GateResult,
    LiquidityMetrics,
    RestrictionStatus,
    RiskState,
    SurveillanceStatus,
    TradingWindow,
)


@dataclass(frozen=True)
class GateContext:
    """Every input every gate needs, in one place. Optional/defaulted
    fields correspond to checks that pass by default until the
    infrastructure that would populate them (Phase 5 scanner, Phase 7 risk
    engine, Phase 9 paper trading engine) exists."""

    # Gate 1 -- STALE_DATA
    latest_bar: Bar
    now_ist: datetime
    freshness_seconds: dict[str, float]

    # Gate 2 -- DATA_INTEGRITY_FAIL
    bars: list[Bar]
    session_start: datetime
    session_end: datetime
    circuit_band_pct: float
    expected_interval: timedelta

    # Gate 3 -- INSUFFICIENT_HISTORY
    required_indicator_values: dict[str, float | None]

    # Gate 12 -- RR_BELOW_MIN
    net_risk_reward: float
    min_risk_reward_net_of_costs: float

    # Gate 8 -- OUTSIDE_WINDOW
    trading_window: TradingWindow

    # Config-driven thresholds (gates 6, 7, 10, 11)
    min_avg_traded_value_inr: float
    min_avg_bar_volume: float
    max_position_fraction_of_adv: float
    max_spread_pct: float
    max_daily_loss_pct: float
    max_open_positions: int
    max_sector_exposure_pct: float

    # Gates 4, 5, 6, 7, 9, 10, 11, 13 -- default to the passing state until
    # real infrastructure supplies these.
    restriction_status: RestrictionStatus = RestrictionStatus()
    surveillance_status: SurveillanceStatus = SurveillanceStatus()
    liquidity_metrics: LiquidityMetrics | None = None
    spread_pct: float = 0.0
    has_blocking_event: bool = False
    event_detail: str = ""
    risk_state: RiskState | None = None
    exposure_state: ExposureState | None = None
    cooldown_active_until: datetime | None = None


def evaluate_gates(ctx: GateContext) -> GateReport:
    """Runs all 13 gates in spec table order and returns a full report."""
    liquidity_metrics = ctx.liquidity_metrics or LiquidityMetrics(
        avg_traded_value_20d_inr=ctx.min_avg_traded_value_inr,
        avg_bar_volume=ctx.min_avg_bar_volume,
    )
    risk_state = ctx.risk_state or RiskState(daily_pnl_inr=0.0, paper_capital_inr=1.0)
    exposure_state = ctx.exposure_state or ExposureState(
        open_positions_count=0, sector_exposure_pct={}, candidate_sector=""
    )

    results: list[GateResult] = [
        g.check_data_freshness(ctx.latest_bar, ctx.now_ist, ctx.freshness_seconds),
        g.check_data_integrity(
            ctx.bars,
            session_start=ctx.session_start,
            session_end=ctx.session_end,
            circuit_band_pct=ctx.circuit_band_pct,
            expected_interval=ctx.expected_interval,
        ),
        g.check_indicator_warmup(ctx.required_indicator_values),
        g.check_symbol_not_restricted(ctx.restriction_status),
        g.check_not_under_surveillance(ctx.surveillance_status),
        g.check_liquidity_floor(
            liquidity_metrics,
            min_avg_traded_value_inr=ctx.min_avg_traded_value_inr,
            min_avg_bar_volume=ctx.min_avg_bar_volume,
            max_position_fraction_of_adv=ctx.max_position_fraction_of_adv,
        ),
        g.check_spread_band(ctx.spread_pct, max_spread_pct=ctx.max_spread_pct),
        g.check_trading_window(ctx.now_ist, ctx.trading_window),
        g.check_no_event_risk(ctx.has_blocking_event, detail=ctx.event_detail),
        g.check_daily_loss_limit(risk_state, max_daily_loss_pct=ctx.max_daily_loss_pct),
        g.check_exposure_available(
            exposure_state,
            max_open_positions=ctx.max_open_positions,
            max_sector_exposure_pct=ctx.max_sector_exposure_pct,
        ),
        g.check_risk_reward_minimum(
            ctx.net_risk_reward, min_risk_reward_net_of_costs=ctx.min_risk_reward_net_of_costs
        ),
        g.check_cooldown_not_active(ctx.now_ist, ctx.cooldown_active_until),
    ]

    first_failure = next((r for r in results if not r.passed), None)
    return GateReport(
        results=tuple(results),
        passed=first_failure is None,
        first_failure=first_failure,
    )
