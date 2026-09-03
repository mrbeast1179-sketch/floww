# Phase 9 — REQUIREMENTS (Academy Flow Build)

Parent: PLAN.md (same dir). R = requirement, M = measurable acceptance.

| ID | Requirement | Wave | Acceptance (M) |
|---|---|---|---|
| R9.0 | Spikes resolve unknowns before product code | W0 | go/no-go recorded per spike (OPTION bars, [2] heat inputs, yfinance fields) |
| R9.1 | Spread bar + Fill on every Pulse row from existing quote fields | W1 | bar position == (last-bid)/(ask-bid) on 20 sampled rows; ±1% |
| R9.2 | Overview bar: NetPrem, P/C, FIR (defined), session label; RVOL honest-empty until baselines exist | W1 | values reproduce from same payload ±1%; RVOL shows "building n/20" pre-cadence |
| R9.3 | Earnings proximity col + filter; sector/industry filter | W2 | 5 sampled tickers match Finnhub calendar/profile; cached (no per-poll fetch) |
| R9.4 | ΔOI col per contract from OI history | W2 | matches next-day exchange truth on 5 sampled contracts |
| R9.5 | Strategy badge on Pulse path (spread legs flagged, not directional) | W2 | synthetic vertical/straddle fixtures badge correctly; legs never WHALE alone |
| R9.6 | Chart modal v1: Contract history + Net Premium; candle→prints bridge | W3 | opens from any Pulse row; NetPrem default view; figures match tape |
| R9.7 | Tracker v1: bookmark, live P/L, STILL-IN/PARTIAL/EXITED via OI drift | W3 | P/L within a tick of mark; staged close detected on fixture drift |
| R9.8 | Highlighting Size>OI / Vol>OI, per-tab persisted | W3 | 100% fire on synthetic fixtures incl. OI=0 edge (documented, not "fixed") |
| R9.9 | ONE per-tab substrate (tabs+cols+highlight+filters), ticker !exclude, cap/sort, CSV | W4 | prefs survive reload; 10-tab render perf unchanged; CSV round-trips |
| R9.10 | NetPrem trend + Strike distribution + Vol/OI-14d (fixture-first, live on cadence) | W4 | reproduce from snapshots on demand; placement note until B1 lands |
| R9.11 | Signed score spec + display-only + backtest harness | W5 | sign matrix unit-tested incl. put-ASK/hedge; Sharpe-gated reports |
| R9.12 | Every signal ships its evaluator; per-tag 30-min outcomes | all | evaluator file per signal; tag hit-rates visible in outcomes |
| R9.13 | Backend proposals B1–B5 tracked for lane owner; dark-pool context panel specced (FINRA ETL) | — | proposals filed with file:line; no free-data live-tape claims anywhere |

Non-requirements: paid keys, live OPRA/TRF, mobile layouts, Discord/image export,
strategy-leg modal, CBOE scraping, repo clones.
