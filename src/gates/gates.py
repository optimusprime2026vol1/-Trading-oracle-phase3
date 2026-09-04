"""
The 13 pre-flight gates.

Master spec reference: section 4 (Pre-flight Gates) for the gate list and
fail codes, section 5 (India Market Reality Layer) for the restriction,
surveillance, liquidity, and session-window rules each gate enforces, and
section 9 (Risk Engine) for the daily-loss, exposure, and cooldown gates.

Every function here is pure: given the same inputs it always returns the
same GateResult, and it never reaches into global state, the clock (except
where a `now_ist` is passed in explicitly), or a file. This is what makes
"every gate demonstrably blocks its condition" (Phase 4 exit criterion)
testable -- each gate can be independently driven to fail while every
other input stays in its passing state.

Several gates (SYMBOL_RESTRICTED, SURVEILLANCE_LIST, EVENT_RISK, and the
position-sizing inputs to ILLIQUID) depend on live infrastructure that
doesn't exist yet (a halt/circuit feed, an ASM/GSM/T2T list, an economic
calendar, a sizing engine) -- those gates take already-resolved status
objects as input rather than fetching anything themselves. Wiring a real
data source behind those inputs is Phase 5 (scanner) and Phase 7 (risk
engine) work; the gate logic itself is complete and correct today.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from src.data.contracts import Bar
from src.data.integrity import (
    DataIntegrityFail,
    FreshnessResult,
    check_freshness,
    run_structural_checks,
)
from src.gates.types import (
    ExposureState,
    GateCode,
    GateResult,
    LiquidityMetrics,
    RestrictionStatus,
    RiskState,
    SurveillanceStatus,
    TradingWindow,
)


# --- Gate 1: STALE_DATA ------------------------------------------------------


def check_data_freshness(
    latest_bar: Bar, now_ist: datetime, freshness_seconds: dict[str, float]
) -> GateResult:
    """Spec 4 gate 1. Reuses integrity.check_freshness (spec 3.2) rather
    than re-implementing the age calculation."""
    result: FreshnessResult = check_freshness(latest_bar, now_ist, freshness_seconds)
    if result.is_fresh:
        return GateResult.ok(GateCode.STALE_DATA)
    return GateResult.fail(
        GateCode.STALE_DATA,
        f"data_age_seconds={result.data_age_seconds:.0f} exceeds "
        f"threshold={result.threshold_seconds:.0f} for {latest_bar.symbol}",
    )


# --- Gate 2: DATA_INTEGRITY_FAIL --------------------------------------------


def check_data_integrity(
    bars: list[Bar],
    *,
    session_start: datetime,
    session_end: datetime,
    circuit_band_pct: float,
    expected_interval: timedelta,
) -> GateResult:
    """Spec 4 gate 2. Runs every spec-3.5 structural check via
    integrity.run_structural_checks and converts the first failure (if
    any) into this gate's result."""
    try:
        run_structural_checks(
            bars,
            session_start=session_start,
            session_end=session_end,
            circuit_band_pct=circuit_band_pct,
            expected_interval=expected_interval,
        )
    except DataIntegrityFail as exc:
        return GateResult.fail(
            GateCode.DATA_INTEGRITY_FAIL, f"{exc.check_name}: {exc.detail}"
        )
    return GateResult.ok(GateCode.DATA_INTEGRITY_FAIL)


# --- Gate 3: INSUFFICIENT_HISTORY -------------------------------------------


def check_indicator_warmup(required_indicator_values: dict[str, float | None]) -> GateResult:
    """Spec 4 gate 3. `required_indicator_values` is the set of indicator
    outputs the candidate strategy needs at the current bar (e.g.
    {"ema_200": ema_series[-1], "atr_14": atr_series[-1]}). Every
    indicator in this package already returns None until its own warm-up
    threshold (spec 6.1) is satisfied, so this gate is just: are any of
    the values the strategy actually needs still None."""
    missing = sorted(name for name, value in required_indicator_values.items() if value is None)
    if missing:
        return GateResult.fail(
            GateCode.INSUFFICIENT_HISTORY, f"not yet warmed up: {', '.join(missing)}"
        )
    return GateResult.ok(GateCode.INSUFFICIENT_HISTORY)


# --- Gate 4: SYMBOL_RESTRICTED ----------------------------------------------


def check_symbol_not_restricted(status: RestrictionStatus) -> GateResult:
    """Spec 4 gate 4: symbol not halted / not at circuit."""
    if status.is_halted:
        return GateResult.fail(GateCode.SYMBOL_RESTRICTED, "symbol is halted")
    if status.at_circuit_limit:
        return GateResult.fail(GateCode.SYMBOL_RESTRICTED, "symbol is at circuit limit")
    return GateResult.ok(GateCode.SYMBOL_RESTRICTED)


# --- Gate 5: SURVEILLANCE_LIST ----------------------------------------------


def check_not_under_surveillance(status: SurveillanceStatus) -> GateResult:
    """Spec 4 gate 5 / 5.3: ASM / GSM / T2T surveillance framework."""
    reasons = []
    if status.in_asm:
        reasons.append("ASM")
    if status.in_gsm:
        reasons.append("GSM")
    if status.in_t2t:
        reasons.append("T2T (intraday not allowed, spec 5.3)")
    if reasons:
        return GateResult.fail(GateCode.SURVEILLANCE_LIST, ", ".join(reasons))
    return GateResult.ok(GateCode.SURVEILLANCE_LIST)


# --- Gate 6: ILLIQUID --------------------------------------------------------


def check_liquidity_floor(
    metrics: LiquidityMetrics,
    *,
    min_avg_traded_value_inr: float,
    min_avg_bar_volume: float,
    max_position_fraction_of_adv: float,
) -> GateResult:
    """Spec 4 gate 6 / 5.4: 20-day average traded value, average bar
    volume, and the market-impact cap (position size as a fraction of
    average daily volume). The market-impact check only runs when both
    `candidate_position_value_inr` and `avg_daily_traded_value_inr` are
    supplied -- before a candidate position size exists (pre-sizing), this
    gate still enforces the first two floors."""
    if metrics.avg_traded_value_20d_inr < min_avg_traded_value_inr:
        return GateResult.fail(
            GateCode.ILLIQUID,
            f"avg_traded_value_20d_inr={metrics.avg_traded_value_20d_inr:.0f} "
            f"below floor {min_avg_traded_value_inr:.0f}",
        )
    if metrics.avg_bar_volume < min_avg_bar_volume:
        return GateResult.fail(
            GateCode.ILLIQUID,
            f"avg_bar_volume={metrics.avg_bar_volume:.0f} below floor {min_avg_bar_volume:.0f}",
        )
    if (
        metrics.candidate_position_value_inr is not None
        and metrics.avg_daily_traded_value_inr is not None
        and metrics.avg_daily_traded_value_inr > 0
    ):
        fraction = metrics.candidate_position_value_inr / metrics.avg_daily_traded_value_inr
        if fraction > max_position_fraction_of_adv:
            return GateResult.fail(
                GateCode.ILLIQUID,
                f"position would be {fraction:.4f} of ADV, "
                f"exceeds market-impact cap {max_position_fraction_of_adv:.4f}",
            )
    return GateResult.ok(GateCode.ILLIQUID)


# --- Gate 7: WIDE_SPREAD -----------------------------------------------------


def check_spread_band(spread_pct: float, *, max_spread_pct: float) -> GateResult:
    """Spec 4 gate 7 / 5.4: bid-ask spread as a percentage of price."""
    if spread_pct > max_spread_pct:
        return GateResult.fail(
            GateCode.WIDE_SPREAD, f"spread_pct={spread_pct:.3f} exceeds max {max_spread_pct:.3f}"
        )
    return GateResult.ok(GateCode.WIDE_SPREAD)


# --- Gate 8: OUTSIDE_WINDOW --------------------------------------------------


def check_trading_window(now_ist: datetime, window: TradingWindow) -> GateResult:
    """Spec 4 gate 8 / 5.1: entry only permitted within the normal session,
    and never inside the configured buffer before square-off ("No new
    intraday entry within the configured buffer before square-off unless
    the strategy explicitly permits it" -- the override is a strategy-level
    decision, so it is not modelled in this generic gate)."""
    if now_ist < window.normal_open:
        return GateResult.fail(
            GateCode.OUTSIDE_WINDOW, f"{now_ist.time()} is before session open {window.normal_open.time()}"
        )
    last_entry_time = window.square_off_time - timedelta(minutes=window.no_new_entry_buffer_minutes)
    if now_ist > last_entry_time:
        return GateResult.fail(
            GateCode.OUTSIDE_WINDOW,
            f"{now_ist.time()} is within {window.no_new_entry_buffer_minutes} min of "
            f"square-off {window.square_off_time.time()}",
        )
    return GateResult.ok(GateCode.OUTSIDE_WINDOW)


# --- Gate 9: EVENT_RISK ------------------------------------------------------


def check_no_event_risk(has_blocking_event: bool, *, detail: str = "") -> GateResult:
    """Spec 4 gate 9: no blocking scheduled event (earnings, major
    macro release, etc.). The event calendar itself is future
    infrastructure (Phase 5 scanner); this gate is the enforcement point."""
    if has_blocking_event:
        return GateResult.fail(GateCode.EVENT_RISK, detail or "blocking scheduled event")
    return GateResult.ok(GateCode.EVENT_RISK)


# --- Gate 10: RISK_LIMIT_HIT -------------------------------------------------


def check_daily_loss_limit(state: RiskState, *, max_daily_loss_pct: float) -> GateResult:
    """Spec 4 gate 10 / section 9: daily loss limit -> hard stop, no new
    entries for the session."""
    if state.paper_capital_inr <= 0:
        return GateResult.fail(GateCode.RISK_LIMIT_HIT, "paper_capital_inr must be positive")
    loss_pct = max(0.0, -state.daily_pnl_inr) / state.paper_capital_inr * 100
    if loss_pct >= max_daily_loss_pct:
        return GateResult.fail(
            GateCode.RISK_LIMIT_HIT,
            f"daily_loss_pct={loss_pct:.2f} has reached limit {max_daily_loss_pct:.2f}",
        )
    return GateResult.ok(GateCode.RISK_LIMIT_HIT)


# --- Gate 11: EXPOSURE_FULL --------------------------------------------------


def check_exposure_available(
    state: ExposureState, *, max_open_positions: int, max_sector_exposure_pct: float
) -> GateResult:
    """Spec 4 gate 11 / section 9: max simultaneous open positions and max
    single-sector exposure."""
    if state.open_positions_count >= max_open_positions:
        return GateResult.fail(
            GateCode.EXPOSURE_FULL,
            f"open_positions_count={state.open_positions_count} "
            f"has reached max {max_open_positions}",
        )
    current_sector_pct = state.sector_exposure_pct.get(state.candidate_sector, 0.0)
    if current_sector_pct >= max_sector_exposure_pct:
        return GateResult.fail(
            GateCode.EXPOSURE_FULL,
            f"sector {state.candidate_sector!r} exposure {current_sector_pct:.2f}% "
            f"has reached max {max_sector_exposure_pct:.2f}%",
        )
    return GateResult.ok(GateCode.EXPOSURE_FULL)


# --- Gate 12: RR_BELOW_MIN ---------------------------------------------------


def check_risk_reward_minimum(
    net_risk_reward: float, *, min_risk_reward_net_of_costs: float
) -> GateResult:
    """Spec 4 gate 12 / 5.5: risk-reward after realistic costs must meet
    the configured minimum. `net_risk_reward` must already be computed net
    of brokerage/STT/slippage/etc (spec 5.5: "Only post-cost risk-reward is
    ever displayed") -- that cost model is Phase 10 (execution realism);
    this gate is the comparison, not the cost calculation."""
    if net_risk_reward < min_risk_reward_net_of_costs:
        return GateResult.fail(
            GateCode.RR_BELOW_MIN,
            f"net_risk_reward={net_risk_reward:.2f} below minimum {min_risk_reward_net_of_costs:.2f}",
        )
    return GateResult.ok(GateCode.RR_BELOW_MIN)


# --- Gate 13: COOLDOWN_ACTIVE ------------------------------------------------


def check_cooldown_not_active(
    now_ist: datetime, cooldown_active_until: datetime | None
) -> GateResult:
    """Spec 4 gate 13 / section 9: consecutive-loss breaker. The trigger
    logic (counting consecutive losses and setting `cooldown_active_until`)
    belongs to the paper-trading engine (Phase 9), which owns trade
    history; this gate only checks whether a previously-set cooldown
    window is still in effect."""
    if cooldown_active_until is not None and now_ist < cooldown_active_until:
        return GateResult.fail(
            GateCode.COOLDOWN_ACTIVE, f"cooldown active until {cooldown_active_until.isoformat()}"
        )
    return GateResult.ok(GateCode.COOLDOWN_ACTIVE)
