# Trading Oracle

Autonomous NSE/BSE intraday research, signal, and **paper-trading** system.
Built against [`TRADING_ORACLE_v2_MASTER_SPEC.md`](./TRADING_ORACLE_v2_MASTER_SPEC.md) --
that document is the build contract; this README is a map of where the
project currently stands against it.

## What this is (and isn't)

This system generates research signals and simulates trades on paper. It
does not place real orders. Live execution is explicitly locked (spec
section 21) and will not be enabled implicitly, automatically, or on
request from within a chat session -- it requires a long list of
prerequisites the spec spells out, plus the operator's own explicit,
written go-ahead.

This is not investment advice. Intraday trading carries substantial risk of
loss, and most individual intraday traders in Indian equity markets lose
money over time. See section 22 of the master spec for the full disclaimer.

## Non-negotiables (why the code looks the way it does)

- **Python computes, the LLM narrates.** No indicator value, price, or
  statistic is ever produced by a language model (spec section 2).
- **No candle, no signal.** Stale, incomplete, or unadjusted data blocks
  the signal rather than degrading it (spec section 3).
- **NO TRADE is a valid, successful output.** The system never manufactures
  a setup because someone asked for one (spec section 14).
- **Every number in a rendered report must exist in the source JSON object**
  it was rendered from, or the output is rejected (spec section 13.1, 15.3).

## Phase status

Tracked against the roadmap in spec section 20. A phase is marked done only
when its exit criterion is demonstrably met -- not when it feels finished.

| Phase | Deliverable | Exit criterion | Status |
|---|---|---|---|
| 1 | Repo, config, logging | Config hashing works, logs reproducible | **Done** -- see `tests/unit/test_config.py`, `tests/unit/test_logging.py` |
| 2 | Data layer + integrity contract | All section 3.5 checks passing on live feed | **Code complete, awaiting your live run** -- `Bar` contract, all section 3.5 structural checks, freshness (3.2), the provider interface, `HistoricalCsvProvider`, and `ZerodhaKiteProvider` (instrument resolution + historical/latest fetch) are built and unit-tested (see `tests/unit/`). `ZerodhaKiteProvider`'s logic is proven against a fake Kite client in tests; the exit criterion itself -- checks passing *on a live feed* -- can only be confirmed by running it with your real credentials (`scripts/generate_kite_session.py`). |
| 3 | Indicators | Unit tests match reference values exactly | **Done** -- EMA, RSI, ATR, MACD, VWAP, RVOL, Bollinger, each cross-checked against an independently-written reference calculation in its test file. All warm-up thresholds from spec 6.1 enforced. |
| 4 | Gates | Every gate demonstrably blocks its condition | Not started |
| 5 | Scanner | Runs a full session without integrity failure | Not started |
| 6 | Strategies + regime gating | Each strategy fires only in permitted regimes | Not started |
| 7 | Risk + sizing engine | Limits provably unbreakable in tests | Not started |
| 8 | Execution realism | Slippage and gap-through-stop simulated | Not started |
| 9 | Paper trading | 60 sessions logged with full audit trail | Not started |
| 10 | Backtest harness | Walk-forward validation clean, no leakage | Not started |
| 11 | Analytics + review | Statistics carry samples and intervals | Not started |
| 12 | Dashboard | All health indicators live | Not started |

## Repository layout

```
trading-oracle/
├── config/               versioned, hashed behavioural config
├── src/
│   ├── data/
│   │   ├── contracts.py       Bar dataclass, mandatory fields (spec 3.1)
│   │   ├── integrity.py       structural (3.5) + freshness (3.2) checks
│   │   └── providers/
│   │       ├── base.py            DataProvider interface
│   │       ├── historical_csv.py  offline provider, no credentials needed
│   │       └── zerodha_kite.py    live provider, needs .env credentials
│   ├── indicators/
│   │   ├── _core.py           shared seeded-EMA math
│   │   ├── ema.py, atr.py, rsi.py, macd.py
│   │   └── vwap.py, bollinger.py, rvol.py
│   └── utils/            config loader + hasher, structured logging
├── tests/unit/           unit tests proving each phase's exit criterion
├── scripts/              generate_kite_session.py (run locally, daily)
├── logs/                 runtime logs (git-ignored, folder tracked)
├── database/             reserved for Phase 9 (paper trading records)
├── .github/workflows/    CI: install deps, run tests, on every push
├── requirements.txt
├── .env.example          copy to .env, fill in real values, never commit it
└── pytest.ini
```

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real values when Phase 2 needs them
pytest -v
```

## Data layer (Phase 2)

Every provider implements `DataProvider` (`src/data/providers/base.py`), so
strategies, gates, and the backtest harness never need to know which one
produced a bar.

- **`HistoricalCsvProvider`** reads bars from
  `<data_dir>/<EXCHANGE>/<SYMBOL>_<timeframe>.csv` and needs no
  credentials -- use it to build and test every later phase against
  offline data. CSV columns:
  `bar_open_time_ist,bar_close_time_ist,open,high,low,close,volume,adjustment_status`,
  timestamps as ISO-8601 with an explicit offset
  (`2026-08-18T09:15:00+05:30`).
- **`ZerodhaKiteProvider`** wraps live Kite Connect. Setup:
  1. `pip install kiteconnect --break-system-packages` (uncomment it in
     `requirements.txt` first).
  2. `cp .env.example .env`, fill in `ZERODHA_API_KEY` and
     `ZERODHA_API_SECRET` from your Kite Connect app.
  3. Run `python scripts/generate_kite_session.py` -- it prints a login
     URL, you log in in a browser, paste back the `request_token` it
     redirects you with, and it writes today's `ZERODHA_ACCESS_TOKEN`
     into `.env`. **Run this once per trading day** -- Kite access tokens
     expire daily by design, this is not a one-time setup.
  4. `provider = ZerodhaKiteProvider()` now works. It lazily loads and
     caches the full instrument dump (`kite.instruments(exchange)`) the
     first time it needs to resolve a symbol on that exchange, then reuses
     the cache for the life of the provider instance.

  Never commit `.env` or paste its contents anywhere -- it's already
  git-ignored. This provider's own test suite
  (`tests/unit/test_zerodha_kite_provider.py`) never touches the network
  or real credentials; it injects a fake Kite client to prove the mapping
  logic is correct. Verifying it against Zerodha's actual servers can only
  happen on your machine, with your real session.

All bars, from either provider, pass through `src/data/integrity.py`
before anything downstream may use them (spec section 3.5).

## Indicators (Phase 3)

`src/indicators/` implements all 7 spec section 6 indicators as pure
functions over a `Sequence[Bar]`, each returning one value per input bar
(`None` until its warm-up threshold from spec 6.1 is met):

- `ema.ema(bars, period)` -- EMA, seeded EMA, 3n warm-up
- `atr.atr(bars, period=14)` -- Wilder ATR, 100-bar warm-up
- `rsi.rsi(bars, period=14)` -- Wilder RSI, 100-bar warm-up
- `macd.macd(bars)` -- returns `MacdResult(macd_line, signal_line, histogram)`
- `vwap.vwap(bars)` -- session-anchored, resets on day change
- `bollinger.bollinger(bars, period=20)` -- returns `BollingerResult(middle, upper, lower)`, population sigma
- `rvol.rvol(current_session_bars, historical_sessions)` -- needs 20 prior sessions or returns all `None`

Each has its own test file cross-checked against an independently-written
reference calculation (not a call back into the module under test).

## Config and hashing

`config/default.yaml` holds all behavioural settings (risk limits, session
times, cost model, freshness thresholds). `src/utils/config.py` loads it and
computes a deterministic SHA-256 hash (`config_hash`) that will be stamped
on every signal and log record once signal generation exists (Phase 5+),
so any decision can be traced back to the exact config that produced it.

Secrets never enter the hashed config -- they live only in `.env` /
GitHub Secrets, referenced via `src/utils/config.get_env()`.
