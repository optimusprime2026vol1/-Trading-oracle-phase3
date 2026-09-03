# TRADING ORACLE — v2.0

### Autonomous NSE/BSE Intraday Research, Signal & Paper-Trading System
**Master Specification | Research & Paper Trading First**

---

## 0. READ THIS BEFORE ANYTHING ELSE

This document is a **build contract**, not a motivational brief.

Accuracy in a trading system does not come from clever instruction wording. It comes from four sources only:

| Source of accuracy | Weight in real outcomes |
|---|---|
| Data integrity (clean, timestamped, adjusted, non-stale) | Very high |
| Deterministic computation (Python, not language model) | Very high |
| Hard blocking gates before any signal is emitted | High |
| Honest statistical measurement of results | High |
| Prompt phrasing / persona | Near zero |

Every rule below exists to protect one of the first four. If a rule ever conflicts with "produce a trade recommendation," the rule wins.

**A signal that was never generated cannot lose money. A wrong signal can.**

---

## 1. AUTHORITY HIERARCHY

When any two rules conflict, the higher tier always overrides the lower. No exception, no operator override except where explicitly marked.

```
TIER 1  Legal & regulatory compliance
TIER 2  Data integrity contract
TIER 3  Risk engine limits
TIER 4  Deterministic computation results
TIER 5  Strategy logic
TIER 6  LLM interpretation & narration
TIER 7  Operator preference / request
```

Meaning in plain terms: if the operator asks for a trade idea on a stock whose data is 40 seconds stale, Tier 2 beats Tier 7. The answer is a refusal with a reason code, not a softened guess.

---

## 2. ROLE SEPARATION — THE SINGLE LARGEST ACCURACY FIX

The original version invited the model to "calculate RSI, ATR, EMA." That instruction is the biggest defect in the whole design. Language models approximate arithmetic; they do not compute it. Every number produced this way is a silent error waiting to appear in a trade log.

### 2.1 What Python code owns (LLM is forbidden to touch)

- All price, volume, and OHLC values
- Every indicator value without exception
- Support/resistance level detection
- Score arithmetic
- Entry, stop, target, quantity, risk-reward
- Profit and loss, costs, slippage
- All statistics and backtest results

### 2.2 What the language model owns

- Summarising news into a sentiment label with a cited source
- Explaining, in words, a decision the code already made
- Writing the daily review narrative
- Drafting code, tests, and documentation
- Flagging logical inconsistencies for human review

### 2.3 Enforcement rule

> The LLM receives a **finished, computed JSON object** and converts it into readable language. It never receives raw candles and never produces a numeral that was not present in its input.

If a number appears in narration that is absent from the input object, the output is rejected by a validator and logged as `HALLUCINATED_FIGURE`.

---

## 3. DATA INTEGRITY CONTRACT

No candle, no signal. This section is non-negotiable.

### 3.1 Mandatory fields on every bar

`symbol, exchange, timeframe, bar_open_time_ist, bar_close_time_ist, open, high, low, close, volume, source_id, fetched_at_ist, adjustment_status`

A bar missing any field is discarded, not patched.

### 3.2 Freshness thresholds

| Timeframe | Maximum acceptable data age | Action on breach |
|---|---|---|
| 1 min | 90 seconds | Block signal |
| 5 min | 5 minutes | Block signal |
| 15 min | 12 minutes | Block signal |
| Daily context | 1 trading day | Warn, allow research only |

Every emitted output carries `data_timestamp` and `data_age_seconds`. Absent values mean the signal is void.

### 3.3 Closed-bar rule (prevents look-ahead contamination)

All decisions use **completed candles only**. A forming candle may be displayed on screen but may never enter indicator computation or a trigger condition. This single rule removes the most common cause of a backtest that looks brilliant and trades terribly.

### 3.4 Corporate action adjustment

Splits, bonuses, and dividends corrupt historical series if unadjusted. Every historical fetch must record `adjustment_status` as `ADJUSTED`, `UNADJUSTED`, or `UNKNOWN`. `UNKNOWN` is treated as unusable for indicators.

### 3.5 Structural checks run on every fetch

- Missing bars inside a session
- Duplicate timestamps
- Zero-volume bars during active hours
- High < low, or close outside high-low range
- Price jump beyond the applicable circuit band
- Timezone drift (everything stored in IST, ISO-8601, explicit offset)

Any failure raises `DATA_INTEGRITY_FAIL` with the specific check name.

### 3.6 Provider transparency

Never blend providers inside one calculation. Never substitute cached data for live data silently. If the primary source fails and a fallback is used, the output must state `SOURCE_FALLBACK_ACTIVE` and reduce the score by a configured penalty.

---

## 4. PRE-FLIGHT GATES

Deterministic boolean checks. **All must return TRUE** or the system returns a NO-TRADE code. These run in Python before any strategy is consulted.

| # | Gate | Fail code |
|---|---|---|
| 1 | Data fresh within threshold | `STALE_DATA` |
| 2 | Data integrity checks passed | `DATA_INTEGRITY_FAIL` |
| 3 | Indicator warm-up satisfied | `INSUFFICIENT_HISTORY` |
| 4 | Symbol not halted / not at circuit | `SYMBOL_RESTRICTED` |
| 5 | Symbol not in ASM / GSM / T2T / trade-to-trade surveillance | `SURVEILLANCE_LIST` |
| 6 | Liquidity floor met (see 5.4) | `ILLIQUID` |
| 7 | Spread within acceptable band | `WIDE_SPREAD` |
| 8 | Within permitted trading window | `OUTSIDE_WINDOW` |
| 9 | No blocking scheduled event | `EVENT_RISK` |
| 10 | Daily loss limit not reached | `RISK_LIMIT_HIT` |
| 11 | Position and sector caps available | `EXPOSURE_FULL` |
| 12 | Risk-reward meets minimum after costs | `RR_BELOW_MIN` |
| 13 | Consecutive-loss breaker not tripped | `COOLDOWN_ACTIVE` |

---

## 5. INDIA MARKET REALITY LAYER

Generic trading logic fails here because Indian market mechanics are specific. These constraints are structural, not preferences.

### 5.1 Session map (IST)

- Pre-open call auction: 09:00 – 09:08, order matching 09:08 – 09:12
- Normal session: 09:15 – 15:30
- Closing session: 15:40 – 16:00
- Intraday square-off by broker: typically 15:10 – 15:20, broker-dependent — must be a config value, never hardcoded

No new intraday entry within the configured buffer before square-off unless the strategy explicitly permits it.

### 5.2 Short selling constraints

In the cash segment, short positions must be squared off the same day. Carrying a short overnight in cash equity is not permitted; naked shorts risk auction settlement penalties. The system must therefore mark every SHORT signal as intraday-only and enforce forced exit.

### 5.3 Restriction checks before any signal

- Circuit band per symbol (2%, 5%, 10%, 20%, or no band)
- ASM / GSM stage, and periodic call auction status
- Trade-to-trade (T2T) segment — intraday not allowed
- F&O ban period status if the derivative is relevant
- Corporate action ex-date on the trading day

### 5.4 Liquidity floor (configurable defaults)

- Minimum 20-day average traded value
- Minimum average bar volume on the decision timeframe
- Maximum position size as a fraction of average daily volume (market-impact cap)
- Maximum acceptable bid-ask spread as a percentage of price

### 5.5 Realistic cost model — must be applied before risk-reward is judged

Model all of: brokerage, STT, exchange transaction charge, SEBI turnover fee, stamp duty, GST on charges, and slippage. Intraday equity STT applies on the sell side. A setup that shows 1:2 on gross prices and 1:1.1 after costs is **not** a 1:2 setup. Only post-cost risk-reward is ever displayed.

---

## 6. INDICATOR SPECIFICATION

Same indicator name, different formula, different result. Ambiguity here is a silent accuracy leak. Fix the definitions once.

| Indicator | Exact definition |
|---|---|
| EMA | Standard exponential, α = 2/(n+1), seeded with SMA of first n bars |
| RSI | Wilder smoothing, period 14 |
| ATR | Wilder true range, period 14 |
| MACD | 12 / 26 / 9, EMA-based, histogram = MACD − signal |
| VWAP | Session-anchored, resets at 09:15, typical price = (H+L+C)/3, cumulative Σ(TP×Vol)/Σ(Vol) |
| RVOL | Current cumulative volume ÷ median cumulative volume at same clock time over 20 sessions |
| Bollinger | SMA 20, 2 standard deviations, population sigma |

### 6.1 Warm-up requirements

An indicator returns `None`, never a partial value, until it has enough history.

- EMA(n): minimum 3n bars before the value is trusted
- RSI(14) / ATR(14): minimum 100 bars
- EMA200 on 5-minute: minimum 600 bars of same-timeframe history
- VWAP: minimum 5 completed bars in the current session

Insufficient history triggers gate 3, not a degraded estimate.

### 6.2 NaN policy

Never forward-fill prices. Never interpolate volume. Missing input means missing output means blocked signal.

---

## 7. SCORING — REBUILT AS TWO STAGES

The original single 0–100 score mixed mandatory conditions with preference weights. That lets a stock pass on style points while failing something essential.

### Stage A — Binary qualifiers (all mandatory)

Trend structure defined, volume confirmation present, VWAP relationship consistent with direction, market and sector not opposing, valid structural stop available, post-cost risk-reward above minimum. **Any failure = rejection, regardless of other strengths.**

### Stage B — Ranking score (only for candidates that cleared Stage A)

| Component | Points |
|---|---|
| Trend quality across timeframes | 20 |
| Relative volume strength | 15 |
| Structure / breakout quality | 15 |
| Momentum agreement | 10 |
| Market alignment | 10 |
| Sector alignment | 10 |
| Volatility suitability (not extreme, not dead) | 10 |
| Post-cost risk-reward | 10 |
| **Total** | **100** |

Penalties subtract: source fallback active, elevated data age, event proximity, prior failed breakout on the same level today.

### 7.1 Score honesty rule

The score is an **ordinal ranking device**, nothing more. It is not a probability, not a confidence percentage, not an edge estimate.

Permitted phrasing: `Setup Score: 82/100 (rank ordering only — not a probability)`
Forbidden phrasing: "82% chance of success," "high probability trade," "strong likelihood."

A historical win rate may be shown alongside **only** when at least 100 closed trades exist for that exact strategy in a comparable market regime, and it must be presented with a confidence interval.

---

## 8. STATISTICAL HONESTY LAYER

This is where most retail systems deceive their own builders.

- **Minimum samples:** below 30 closed trades, report raw counts only — no win rate, no expectancy, no profit factor.
- **Multiple-testing discipline:** testing 10 strategies across parameter grids will produce an impressive winner by chance alone. Apply a correction, report the number of configurations tested alongside every result, and treat any strategy discovered through heavy search as unproven until it survives fresh out-of-sample data.
- **Interval reporting:** point estimates are banned. Report ranges.
- **Regime tagging:** every statistic is stored with its market regime label. Blended all-weather statistics mislead.
- **Primacy of expectancy:** expectancy per rupee risked outranks win rate permanently. A 42% win rate with 2.5R average winners beats a 68% win rate with 0.6R winners.
- **Degradation monitor:** compare live paper results against backtest expectations continuously. Divergence beyond a configured threshold triggers `STRATEGY_DEGRADATION_ALERT` and suspension pending review.

---

## 9. RISK ENGINE — HARD LIMITS

Enforced in code, above strategy logic, not overridable by the model or by a request.

- Maximum risk per trade (percentage of paper capital)
- Maximum daily loss → hard stop, no new entries for the session
- Maximum simultaneous open positions
- Maximum single-sector exposure
- Maximum correlated exposure (two banking stocks are close to one doubled position)
- Consecutive-loss breaker → mandatory cooldown period
- Maximum trades per day (guards against overtrading during choppy sessions)

**Absolute prohibitions:** no averaging down into a loser, no widening a stop after entry, no re-entry into the same symbol and direction more than the configured limit per session, no position sizing that exceeds the market-impact cap.

### 9.1 Position sizing

```
Risk per share      = |Entry − Stop| + expected slippage + per-share cost
Rupee risk allowed  = Paper capital × Max risk %
Raw quantity        = Rupee risk allowed ÷ Risk per share
Final quantity      = min(raw, liquidity cap, exposure cap, capital cap)
```

Always round down. Never round up to a convenient lot.

---

## 10. EXECUTION REALISM MODEL

Paper trading that assumes perfect fills produces fictional profits.

- **Slippage:** modelled by liquidity bucket, not a single flat number. Wider on breakout entries, wider again at open and near close.
- **Stops are not guaranteed:** if the next bar gaps beyond the stop, the fill is the gap price. Simulate this honestly.
- **Partial fills:** for larger sizes relative to volume, simulate incomplete execution.
- **Entry realism:** assume the fill occurs at the worse end of the entry zone, not the ideal price.
- **Square-off:** any open intraday position at the configured square-off time is closed at the prevailing price, profit or loss.

Record MFE and MAE for every trade — these reveal whether stops are too tight or targets too greedy, which raw P&L hides.

---

## 11. STRATEGY LIBRARY

Each strategy is a separate module carrying its own preconditions, regime map, statistics, and retirement criteria.

| ID | Strategy | Suited regime |
|---|---|---|
| S01 | Opening Range Breakout | Trending, expanding volatility |
| S02 | VWAP Reclaim | Trending up, recovering |
| S03 | VWAP Rejection | Trending down |
| S04 | Momentum Continuation | Strong trend |
| S05 | Volume Breakout | Expansion phase |
| S06 | EMA Trend Continuation | Established trend |
| S07 | Support/Resistance Reversal | Range bound |
| S08 | Gap-and-Go | Gap sessions with follow-through |
| S09 | Failed Breakout Reversal | Choppy, trap-prone |
| S10 | Relative Strength Momentum | Broad directional market |

**Regime gating:** a strategy may only fire in its permitted regimes. A mean-reversion setup during a strong trend is a losing trade waiting to happen.

**Retirement rule:** a strategy that stays below its expectancy floor over a minimum sample gets disabled automatically. Losing strategies are removed, never hidden inside an aggregate.

---

## 12. MARKET REGIME DETECTION

Classify per session and re-check periodically: `TRENDING_UP`, `TRENDING_DOWN`, `RANGE_BOUND`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`, `EVENT_DRIVEN`, `UNCERTAIN`.

Classification must be rule-based and reproducible from stored inputs. `UNCERTAIN` maps to no trading. A regime change mid-session raises an alert and re-validates all open positions against their strategy's permitted regimes.

---

## 13. OUTPUT SCHEMA

Machine-readable first, human-readable second. The narration is rendered *from* this object.

```json
{
  "signal_id": "uuid",
  "generated_at_ist": "2026-08-18T10:22:00+05:30",
  "data_timestamp_ist": "2026-08-18T10:20:00+05:30",
  "data_age_seconds": 120,
  "data_source": "provider_id",
  "source_fallback_active": false,
  "config_hash": "sha256:...",
  "code_version": "v2.0.3",
  "symbol": "EXAMPLE",
  "exchange": "NSE",
  "mode": "PAPER",
  "direction": "LONG",
  "strategy_id": "S01",
  "status": "WATCH",
  "ltp": 0.0,
  "entry_zone": {"low": 0.0, "high": 0.0},
  "trigger_condition": "5-min close above X with RVOL above threshold",
  "stop_loss": 0.0,
  "stop_basis": "structural swing low below breakout level",
  "target_1": 0.0,
  "target_2": 0.0,
  "rr_gross": 0.0,
  "rr_net_of_costs": 0.0,
  "position_size": 0,
  "risk_amount": 0.0,
  "setup_score": 0,
  "score_disclaimer": "Ordinal ranking only. Not a probability.",
  "indicators": {"rsi_14": null, "atr_14": null, "vwap": null, "rvol": null},
  "market_regime": "TRENDING_UP",
  "market_alignment": "ALIGNED",
  "sector_alignment": "ALIGNED",
  "news_status": "NEWS_DATA_UNAVAILABLE",
  "gates_passed": [1,2,3,4,5,6,7,8,9,10,11,12,13],
  "reasoning": ["...", "..."],
  "invalidation": "...",
  "expected_holding_period": "...",
  "warnings": []
}
```

### 13.1 Human rendering

Rendered text may contain only values present in the object above. A post-render validator compares every numeral in the narration against the source object and rejects mismatches.

---

## 14. NO-TRADE OUTPUT

```
ORACLE DECISION: NO TRADE
Symbol:        ...
Reason code:   RR_BELOW_MIN
Explanation:   Post-cost risk-reward 1:1.2 against configured minimum 1:1.8
Gates failed:  [12]
Next review:   11:15 IST
```

NO TRADE is a successful output, not a failure. The system must never manufacture a setup because the operator asked for one. Requests such as "just give me something to trade today" are answered with a reason code.

---

## 15. ANTI-HALLUCINATION ENFORCEMENT

### 15.1 Never fabricate

Prices, OHLC, volume, indicator values, news, source citations, API responses, fills, backtest outcomes, win rates, or historical statistics.

### 15.2 Required refusal outputs

```
LIVE DATA UNAVAILABLE — SIGNAL NOT GENERATED
STALE DATA — SIGNAL BLOCKED
NEWS DATA UNAVAILABLE
INSUFFICIENT HISTORY — INDICATOR NOT COMPUTED
INSUFFICIENT SAMPLE — STATISTIC WITHHELD
```

### 15.3 Automated validator (runs on every output before display)

1. Does every numeral appear in the source object?
2. Does every news claim carry a source, URL, and timestamp?
3. Is the data age within threshold?
4. Are all gate results recorded?
5. Is any probability language present? → reject
6. Are all statistics accompanied by sample size?

Failing any check blocks the output and writes to the error log.

### 15.4 Banned vocabulary

"Guaranteed," "sure shot," "confirmed profit," "cannot fail," "risk-free," and any percentage chance of a price outcome.

---

## 16. AUDIT & REPRODUCIBILITY

Every signal must be reconstructable months later from stored records alone.

Log with each decision: config hash, code commit, data snapshot identifier, random seed, complete input series reference, gate results, intermediate indicator values, and final output.

Test suite requirement: unit tests for every indicator against known reference values, integration tests for gates, and regression tests comparing outputs across code versions.

---

## 17. FAILURE MODES TO GUARD AGAINST

| Failure | Guard |
|---|---|
| Look-ahead bias | Closed-bar rule, section 3.3 |
| Survivorship bias | Use historical index constituents, not today's list |
| Overfitting | Walk-forward, out-of-sample, parameter-count discipline |
| Data leakage | Strict train/test separation with time ordering |
| Silent data staleness | Age stamp on every output |
| Cost blindness | Post-cost risk-reward only |
| Fill fantasy | Execution realism model, section 10 |
| Regime blindness | Strategy-regime gating |
| Model arithmetic drift | Code computes, model narrates |
| Overtrading | Daily trade cap, cooldown breaker |
| Curve-fitted confidence | Statistical honesty layer, section 8 |

---

## 18. DASHBOARD

Streamlit or equivalent. Pages: Market Overview, Scanner, Stock Lab, Paper Trading, Performance, Trade Journal, System Health.

Every page displays data timestamp and data age in a fixed position. Any stale panel renders greyed out with the reason shown. Charts never draw fabricated candles — gaps in data appear as gaps.

System Health must surface: provider status, last successful fetch, latency, failed request count, gate rejection breakdown, active alerts, and current risk-limit consumption.

---

## 19. REPOSITORY STRUCTURE

```
trading-oracle/
├── app/                  dashboard and pages
├── src/
│   ├── data/             providers, contracts, validators
│   ├── indicators/       deterministic, unit-tested
│   ├── gates/            pre-flight blocking checks
│   ├── scanners/
│   ├── strategies/       one module per strategy
│   ├── regime/
│   ├── risk/             hard limits, sizing
│   ├── execution/        slippage, fills, costs
│   ├── paper_trading/
│   ├── backtesting/      walk-forward harness
│   ├── news/
│   ├── analytics/
│   ├── validators/       output validator, anti-hallucination
│   └── utils/
├── config/               versioned, hashed
├── database/             SQLite initially
├── tests/                unit, integration, regression
├── logs/
├── scripts/
├── .github/workflows/
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

Secrets live in `.env` locally and GitHub Secrets in CI. `.env` stays in `.gitignore` permanently.

---

## 20. PHASED ROADMAP WITH EXIT CRITERIA

A phase is complete only when its criterion is met — not when it feels done.

| Phase | Deliverable | Exit criterion |
|---|---|---|
| 1 | Repo, config, logging | Config hashing works, logs reproducible |
| 2 | Data layer + integrity contract | All section 3.5 checks passing on live feed |
| 3 | Indicators | Unit tests match reference values exactly |
| 4 | Gates | Every gate demonstrably blocks its condition |
| 5 | Scanner | Runs a full session without integrity failure |
| 6 | Strategies + regime gating | Each strategy fires only in permitted regimes |
| 7 | Risk + sizing engine | Limits provably unbreakable in tests |
| 8 | Execution realism | Slippage and gap-through-stop simulated |
| 9 | Paper trading | 60 sessions logged with full audit trail |
| 10 | Backtest harness | Walk-forward validation clean, no leakage |
| 11 | Analytics + review | Statistics carry samples and intervals |
| 12 | Dashboard | All health indicators live |

---

## 21. LIVE MODE — LOCKED

Live execution remains disabled. It requires, at minimum: authenticated broker API, independent risk service, hard position limits, manual kill switch, tested reconnection handling, order reconciliation, an audited paper record of at least six months across varied regimes, and explicit written operator authorisation.

**The system must never transition from PAPER to LIVE automatically, implicitly, or on request within a chat session.**

---

## 22. DISCLAIMER

This system produces research and simulated trades. It is not investment advice, and it is not a recommendation to buy or sell any security. I'm not a financial advisor. Intraday trading carries substantial risk of loss, and the majority of individual intraday traders in Indian equity markets lose money over time. Any real capital deployment is the operator's decision and responsibility alone, and should follow independent professional consultation.

---

*End of specification.*
