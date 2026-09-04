"""
Phase 4 exit criterion: "Every gate demonstrably blocks its condition."

Each test below starts from a fully-passing baseline context and mutates
exactly one input, then asserts that (a) the target gate fails with its
spec-4 fail code and (b) every other gate still passes -- proving the gate
is specifically responsible for that condition, not just that "something"
failed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.data.contracts import AdjustmentStatus, Bar, Exchange, Timeframe
from src.gates.gates import (
    check_cooldown_not_active,
    check_daily_loss_limit,
    check_data_freshness,
    check_data_integrity,
    check_exposure_available,
    check_indicator_warmup,
    check_liquidity_floor,
    check_no_event_risk,
    check_not_under_surveillance,
    check_risk_reward_minimum,
    check_spread_band,
    check_symbol_not_restricted,
    check_trading_window,
)
from src.gates.runner import GateContext, evaluate_gates
from src.gates.types import (
    ExposureState,
    GateCode,
    LiquidityMetrics,
    RestrictionStatus,
    RiskState,
    SurveillanceStatus,
    TradingWindow,
)

IST = timezone(timedelta(hours=5, minutes=30))


def _bar(open_time, close_time, *, close=100.0) -> Bar:
    return Bar(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        timeframe=Timeframe.FIVE_MIN,
        bar_open_time_ist=open_time,
        bar_close_time_ist=close_time,
        open=close,
        high=close + 0.5,
        low=close - 0.5,
        close=close,
        volume=6000,
        source_id="test",
        fetched_at_ist=close_time,
        adjustment_status=AdjustmentStatus.ADJUSTED,
    )


def _baseline_context(now_ist: datetime, **overrides) -> GateContext:
    """A context where all 13 gates pass. `bars`/`latest_bar` are always
    built relative to `now_ist` so freshness (gate 1) passes regardless of
    which `now_ist` a test picks for its own purposes."""
    day = now_ist.date()
    session_start = datetime(day.year, day.month, day.day, 9, 15, tzinfo=IST)
    session_end = datetime(day.year, day.month, day.day, 15, 30, tzinfo=IST)

    last_close = now_ist - timedelta(seconds=60)
    bars = [
        _bar(last_close - timedelta(minutes=10), last_close - timedelta(minutes=5), close=100.0),
        _bar(last_close - timedelta(minutes=5), last_close, close=101.0),
    ]
    latest_bar = bars[-1]

    trading_window = TradingWindow(
        normal_open=datetime(day.year, day.month, day.day, 9, 15, tzinfo=IST),
        square_off_time=datetime(day.year, day.month, day.day, 15, 15, tzinfo=IST),
        no_new_entry_buffer_minutes=10,
    )

    defaults = dict(
        latest_bar=latest_bar,
        now_ist=now_ist,
        freshness_seconds={"5min": 300},
        bars=bars,
        session_start=session_start,
        session_end=session_end,
        circuit_band_pct=20.0,
        expected_interval=timedelta(minutes=5),
        required_indicator_values={"ema_200": 100.0, "atr_14": 1.5},
        net_risk_reward=2.0,
        min_risk_reward_net_of_costs=1.8,
        trading_window=trading_window,
        min_avg_traded_value_inr=5_000_000.0,
        min_avg_bar_volume=5000,
        max_position_fraction_of_adv=0.01,
        max_spread_pct=0.5,
        max_daily_loss_pct=3.0,
        max_open_positions=3,
        max_sector_exposure_pct=40.0,
        restriction_status=RestrictionStatus(),
        surveillance_status=SurveillanceStatus(),
        liquidity_metrics=LiquidityMetrics(avg_traded_value_20d_inr=6_000_000.0, avg_bar_volume=6000),
        spread_pct=0.2,
        has_blocking_event=False,
        risk_state=RiskState(daily_pnl_inr=0.0, paper_capital_inr=100_000.0),
        exposure_state=ExposureState(
            open_positions_count=0, sector_exposure_pct={}, candidate_sector="IT"
        ),
        cooldown_active_until=None,
    )
    defaults.update(overrides)
    return GateContext(**defaults)


def _assert_only_this_gate_fails(ctx: GateContext, code: GateCode) -> None:
    report = evaluate_gates(ctx)
    assert not report.passed
    assert report.first_failure is not None
    assert report.first_failure.gate == code
    failing = [r.gate for r in report.results if not r.passed]
    assert failing == [code], f"expected only {code} to fail, got {failing}"


def test_baseline_context_passes_every_gate() -> None:
    ctx = _baseline_context(datetime(2026, 8, 18, 11, 0, tzinfo=IST))
    report = evaluate_gates(ctx)
    assert report.passed
    assert report.first_failure is None
    assert len(report.results) == 13


# --- Gate 1: STALE_DATA ------------------------------------------------------


def test_gate1_stale_data_blocks() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    ctx = _baseline_context(now)
    stale_close = now - timedelta(seconds=600)  # exceeds 300s threshold
    stale_bar = _bar(stale_close - timedelta(minutes=5), stale_close, close=101.0)
    ctx = _baseline_context(now, latest_bar=stale_bar)
    _assert_only_this_gate_fails(ctx, GateCode.STALE_DATA)


def test_gate1_fresh_data_passes_in_isolation() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    bar = _bar(now - timedelta(minutes=5), now - timedelta(seconds=30), close=100.0)
    result = check_data_freshness(bar, now, {"5min": 300})
    assert result.passed


# --- Gate 2: DATA_INTEGRITY_FAIL ---------------------------------------------


def test_gate2_data_integrity_blocks() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    open_t = now - timedelta(minutes=10)
    close_t = now - timedelta(minutes=5)
    bad_bar = Bar(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        timeframe=Timeframe.FIVE_MIN,
        bar_open_time_ist=open_t,
        bar_close_time_ist=close_t,
        open=100.0,
        high=90.0,  # corrupt: high < low
        low=95.0,
        close=100.0,
        volume=6000,
        source_id="test",
        fetched_at_ist=close_t,
        adjustment_status=AdjustmentStatus.ADJUSTED,
    )
    good_bar = _bar(now - timedelta(minutes=5), now - timedelta(seconds=60), close=101.0)
    ctx = _baseline_context(now, bars=[bad_bar, good_bar], latest_bar=good_bar)
    _assert_only_this_gate_fails(ctx, GateCode.DATA_INTEGRITY_FAIL)


# --- Gate 3: INSUFFICIENT_HISTORY --------------------------------------------


def test_gate3_insufficient_history_blocks() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    ctx = _baseline_context(now, required_indicator_values={"ema_200": None, "atr_14": 1.5})
    _assert_only_this_gate_fails(ctx, GateCode.INSUFFICIENT_HISTORY)


def test_gate3_reports_which_indicators_are_missing() -> None:
    result = check_indicator_warmup({"ema_200": None, "rsi_14": 55.0, "atr_14": None})
    assert not result.passed
    assert "ema_200" in result.detail
    assert "atr_14" in result.detail
    assert "rsi_14" not in result.detail


# --- Gate 4: SYMBOL_RESTRICTED ------------------------------------------------


def test_gate4_halted_symbol_blocks() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    ctx = _baseline_context(now, restriction_status=RestrictionStatus(is_halted=True))
    _assert_only_this_gate_fails(ctx, GateCode.SYMBOL_RESTRICTED)


def test_gate4_circuit_limit_blocks() -> None:
    result = check_symbol_not_restricted(RestrictionStatus(at_circuit_limit=True))
    assert not result.passed


# --- Gate 5: SURVEILLANCE_LIST -----------------------------------------------


def test_gate5_t2t_blocks() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    ctx = _baseline_context(now, surveillance_status=SurveillanceStatus(in_t2t=True))
    _assert_only_this_gate_fails(ctx, GateCode.SURVEILLANCE_LIST)


def test_gate5_asm_and_gsm_both_reported() -> None:
    result = check_not_under_surveillance(SurveillanceStatus(in_asm=True, in_gsm=True))
    assert not result.passed
    assert "ASM" in result.detail and "GSM" in result.detail


# --- Gate 6: ILLIQUID ---------------------------------------------------------


def test_gate6_low_traded_value_blocks() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    ctx = _baseline_context(
        now,
        liquidity_metrics=LiquidityMetrics(avg_traded_value_20d_inr=1_000_000.0, avg_bar_volume=6000),
    )
    _assert_only_this_gate_fails(ctx, GateCode.ILLIQUID)


def test_gate6_market_impact_cap_blocks() -> None:
    result = check_liquidity_floor(
        LiquidityMetrics(
            avg_traded_value_20d_inr=10_000_000.0,
            avg_bar_volume=6000,
            candidate_position_value_inr=500_000.0,
            avg_daily_traded_value_inr=10_000_000.0,  # 5% of ADV
        ),
        min_avg_traded_value_inr=5_000_000.0,
        min_avg_bar_volume=5000,
        max_position_fraction_of_adv=0.01,  # cap is 1%
    )
    assert not result.passed


# --- Gate 7: WIDE_SPREAD -------------------------------------------------------


def test_gate7_wide_spread_blocks() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    ctx = _baseline_context(now, spread_pct=1.5)
    _assert_only_this_gate_fails(ctx, GateCode.WIDE_SPREAD)


def test_gate7_boundary_spread_passes() -> None:
    result = check_spread_band(0.5, max_spread_pct=0.5)
    assert result.passed


# --- Gate 8: OUTSIDE_WINDOW ----------------------------------------------------


def test_gate8_before_open_blocks() -> None:
    now = datetime(2026, 8, 18, 9, 0, tzinfo=IST)  # before 09:15 open
    ctx = _baseline_context(now)
    _assert_only_this_gate_fails(ctx, GateCode.OUTSIDE_WINDOW)


def test_gate8_within_square_off_buffer_blocks() -> None:
    now = datetime(2026, 8, 18, 15, 10, tzinfo=IST)  # within 10-min buffer before 15:15
    ctx = _baseline_context(now)
    _assert_only_this_gate_fails(ctx, GateCode.OUTSIDE_WINDOW)


def test_gate8_mid_session_passes() -> None:
    window = TradingWindow(
        normal_open=datetime(2026, 8, 18, 9, 15, tzinfo=IST),
        square_off_time=datetime(2026, 8, 18, 15, 15, tzinfo=IST),
        no_new_entry_buffer_minutes=10,
    )
    result = check_trading_window(datetime(2026, 8, 18, 12, 0, tzinfo=IST), window)
    assert result.passed


# --- Gate 9: EVENT_RISK --------------------------------------------------------


def test_gate9_blocking_event_blocks() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    ctx = _baseline_context(now, has_blocking_event=True, event_detail="earnings today")
    _assert_only_this_gate_fails(ctx, GateCode.EVENT_RISK)


def test_gate9_no_event_passes() -> None:
    result = check_no_event_risk(False)
    assert result.passed


# --- Gate 10: RISK_LIMIT_HIT ----------------------------------------------------


def test_gate10_daily_loss_limit_blocks() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    ctx = _baseline_context(
        now, risk_state=RiskState(daily_pnl_inr=-3500.0, paper_capital_inr=100_000.0)
    )  # -3.5% loss, limit is 3.0%
    _assert_only_this_gate_fails(ctx, GateCode.RISK_LIMIT_HIT)


def test_gate10_profitable_day_passes() -> None:
    result = check_daily_loss_limit(
        RiskState(daily_pnl_inr=2000.0, paper_capital_inr=100_000.0), max_daily_loss_pct=3.0
    )
    assert result.passed


# --- Gate 11: EXPOSURE_FULL ------------------------------------------------------


def test_gate11_max_positions_blocks() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    ctx = _baseline_context(
        now,
        exposure_state=ExposureState(
            open_positions_count=3, sector_exposure_pct={}, candidate_sector="IT"
        ),
    )
    _assert_only_this_gate_fails(ctx, GateCode.EXPOSURE_FULL)


def test_gate11_sector_cap_blocks() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    ctx = _baseline_context(
        now,
        exposure_state=ExposureState(
            open_positions_count=1, sector_exposure_pct={"BANKING": 45.0}, candidate_sector="BANKING"
        ),
    )
    _assert_only_this_gate_fails(ctx, GateCode.EXPOSURE_FULL)


# --- Gate 12: RR_BELOW_MIN --------------------------------------------------------


def test_gate12_low_risk_reward_blocks() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    ctx = _baseline_context(now, net_risk_reward=1.1)
    _assert_only_this_gate_fails(ctx, GateCode.RR_BELOW_MIN)


def test_gate12_at_minimum_passes() -> None:
    result = check_risk_reward_minimum(1.8, min_risk_reward_net_of_costs=1.8)
    assert result.passed


# --- Gate 13: COOLDOWN_ACTIVE -----------------------------------------------------


def test_gate13_active_cooldown_blocks() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    ctx = _baseline_context(now, cooldown_active_until=now + timedelta(minutes=30))
    _assert_only_this_gate_fails(ctx, GateCode.COOLDOWN_ACTIVE)


def test_gate13_expired_cooldown_passes() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    result = check_cooldown_not_active(now, now - timedelta(minutes=1))
    assert result.passed


# --- Runner ordering ----------------------------------------------------------


def test_first_failure_is_earliest_in_table_order_when_multiple_fail() -> None:
    now = datetime(2026, 8, 18, 11, 0, tzinfo=IST)
    ctx = _baseline_context(
        now,
        net_risk_reward=1.0,  # would fail gate 12
        restriction_status=RestrictionStatus(is_halted=True),  # would fail gate 4
    )
    report = evaluate_gates(ctx)
    assert not report.passed
    assert report.first_failure.gate == GateCode.SYMBOL_RESTRICTED  # gate 4 precedes gate 12
    failing_codes = {r.gate for r in report.results if not r.passed}
    assert failing_codes == {GateCode.SYMBOL_RESTRICTED, GateCode.RR_BELOW_MIN}
