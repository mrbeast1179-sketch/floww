# swarmSPX forensic truth audit

Date: 2026-09-07 ET
Repository: `/Users/nav/GitHub/swarmSPX`
Mode: read-only repository inspection; no install, service start, live API, model invocation, mutation, commit, push, or deletion

## Executive verdict

swarmSPX is a real prototype with a 24-persona debate loop, provider adapters, DuckDB persistence, risk modules, a single-leg paper ledger, web/TUI surfaces, alerts, and two different backtest mechanisms. It is **not an evidenced trading system**. The most consequential claims in the Hermes inventory are stale or materially overstated:

1. The live ingest path is not public-only and still prefers Schwab. The only no-key fallback is Yahoo/yfinance. The dormant floww proxy is neither wired nor shape-compatible.
2. Four stored Finnhub snapshots are SPY-scale (`741.75–754.83`) while stored as `spx_price`; contemporaneous yfinance SPX rows are `7403.69–7474.07`. These cycles are not comparable and must not support performance claims.
3. Twenty-four agents are configured, but the current route is one OpenRouter model for all tribes and synthesis, not the README's 18 Llama + 6 Phi split. Six of 22 stored cycles contain 24/24 `NEUTRAL, 50` sentinel-shaped votes; 172/528 final-round votes have that exact fallback shape. The schema does not store model or error reason, so successful LLM participation is unproven.
4. The Kelly implementation is mathematically wrong for asymmetric payoff odds. With configured/default `p=0.40`, `b=3`, it computes zero risk; a fresh sizing lock therefore permits zero contracts. Risk P&L is still a fixed 2%-of-bankroll heuristic.
5. Paper trading excludes verticals/condors, has no leg/fill/fee/slippage representation, and converts a missing quote after hours into an expiry at zero. A missing chain is not evidence that a contract is worthless.
6. The headline backtest is circular synthetic Monte Carlo. The newer replay path uses SPY bar low/high as bid/ask, runs surrogate signals on SPX-equivalent moves, and does not exercise the 24-agent/risk/Kelly/paper production path. The local external Parquet fixtures are absent.
7. Friday Pin's published `14 trades / 100% / Sharpe 3.66` is a small SPY-price-proxy result, not an option-chain walk-forward result. The live helper cannot accumulate its required 30 bars, returns a short straddle rather than an iron condor, picks rounded spot rather than highest OI, is not wired to the engine/scheduler, and the scheduler runs at 15:45 rather than 15:30.
8. The working tree is not clean. `config/settings.yaml` is modified and removes the committed `risk` and `paper_trading` blocks while adding an inert, disabled `godmode` block. Runtime therefore falls back to different risk defaults and disables paper.

The audit supports immediate hardening and specification work. It does **not** support live trading, paid marketing claims, or porting the Friday strategy into floww as a “validated edge.”

## Repository state and instruction boundary

- Branch: `main`, HEAD `e6ea2f8`.
- Upstream: `origin/main` at `f9b7e7c`; local branch is 5 commits ahead, 0 behind.
- A second `upstream` remote exists and is on a different history; no fetch was performed.
- Tracked dirty state: only `M config/settings.yaml` at audit time.
- No `AGENTS.md`, `CLAUDE.md`, or `GEMINI.md` applies inside this repository. Neighboring repositories' guidance was not applied to swarmSPX.
- Security finding: `.git/config`'s `origin` URL contains an embedded credential. The value is intentionally omitted. Treat it as exposed local plaintext: revoke/rotate it and replace the URL with a credential-free remote before any sharing or log capture.
- `.env` is ignored and was inspected only for variable-name presence, never values. It contains a current model-key name and several data-provider key names, but no Schwab, FRED, Telegram, or Slack variable names. Presence does not prove validity, entitlement, or reachability.
- `.venv` is Python 3.11.15 while README asks for Python 3.12+. The system Python is newer; no environment was changed.

## Hermes inventory disposition (IDs preserved by supplied domain groups)

Legend: **source-confirmed** means directly present in code/config/git/local artifacts; **stale/wrong** means current source or local evidence contradicts the claim; **unknown** means it requires vendor entitlement, network/service health, a missing dataset, user intent, or empirical trading evidence. Mixed groups split those parts explicitly.

| Inventory IDs | Disposition | Source-limited finding |
|---|---|---|
| **1–5 — ingestion / public-only / Schwab** | **Source-confirmed:** direct adapters and priority chains exist. **Stale/wrong:** public-only, floww-first, or Schwab-deleted descriptions. **Unknown:** live health and vendor entitlements. | Quotes are Schwab → Finnhub → Alpha Vantage → yfinance; options are Schwab → Polygon → Tradier → Yahoo; exit-premium lookup omits Polygon. Schwab remains first and its client remains in `swarmspx/ingest/schwab.py`, although it is not locally configured and `schwab-py` is absent from `requirements.txt`. `swarmspx/ingest/floww_proxy.py` is never imported. Finnhub and Alpha Vantage fetch SPY but write it as SPX without normalization. Yahoo's ability to supply **12 months of 1-minute bars is unknown**; current code requests five days only. Whether the configured Polygon plan supplies SPX snapshots/full Greeks is **unknown**; source comments disagree (`real-time` versus `delayed`) and no live call was permitted. “Free tier with full Greeks” must not be treated as verified entitlement. |
| **6–10 — Friday Pin** | **Source-confirmed:** class, time/range/calendar checks, and the claimed numbers as prose. **Stale/wrong:** validated edge, live wiring, high-OI condor, auto-fire. **Unknown:** real option expectancy. | `swarmspx/strategies/friday_pin.py` gates Friday 15:30–15:40 and 30 recent prices, but returns `SHORT_STRADDLE` at rounded spot. It does not select highest OI or build condor legs. `generate_live_signal()` constructs a fresh object and can never have 30 observations. No engine/scheduler import was found; the scheduled close cycle is 15:45. The 14-trade result uses SPY 1-minute price bars ×10 with approximate basis-point exits, not historical option books. Calendar code exists, but real FRED behavior is unknown and is fail-open when data is unavailable. |
| **11–17 — agents and models** | **Source-confirmed:** 24 configured personas, four tribes, three rounds, batch size six, peer summaries, and current model route. **Stale/wrong:** README model split and any implication of 24 independently successful models/calls. **Unknown:** current OpenRouter/Owl availability and local service health. | `config/agents.yaml` contains 24 base agents. `TradingPit` runs all agents in three rounds, but later prompts see vote counts plus only the strongest bull/bear snippets, not every peer transcript. Both committed and dirty settings route all tribes and synthesis to `openrouter/owl-alpha`; Ollama/Claude entries in the dirty file are unused by current routing. `TraderAgent.think()` catches every provider/parse error and returns `NEUTRAL/50`; storage drops reasoning/model/error. Six stored cycles are entirely sentinel-shaped. `SwarmSPXEngine(settings_path=...)` still creates `AgentForge()` without forwarding that path, so custom settings do not control agent routing. Ollama and Claude CLIs are installed locally, but no model/API was invoked; no local Ollama model manifest was found. |
| **18–20 — risk / Kelly** | **Source-confirmed:** gate, kill switch, sizing lock, configured limits. **Stale/wrong:** correct Kelly sizing, `$475` current sizing, and ledger-backed loss bands. **Unknown:** empirical win probability/payoff inputs. | `swarmspx/risk/sizer.py` uses `(2p-1)/b`; the binary Kelly fraction for net odds `b` is `p-(1-p)/b`. At `p=.40,b=3`, source clamps to zero rather than the positive 0.20 full-Kelly fraction. The committed config says 0.50 fractional Kelly; the dirty working config deletes the risk block, causing engine fallback 0.10. Both yield zero under the implemented formula. `risk/gate.py` and `engine.py` multiply signal outcome percentages by a fixed `.02`; open-position count is pending signals, not the paper ledger. Committed staleness is 86,400 seconds, inappropriate as a fresh 0DTE quote contract; dirty omission restores 30 seconds. |
| **21–23 — paper trading** | **Source-confirmed:** a persistent single-leg paper broker and unit tests exist. **Stale/wrong:** full pipeline/spread support, realistic fills, clean 30-day evidence. **Unknown:** any executable expectancy. | `swarmspx/paper.py` stores one strike/type/premium, with no legs, NBBO-at-decision, fill status, fees, or slippage. `_extract_strategy_meta()` deliberately emits no strike/type for verticals/condors, and engine open conditions therefore exclude them. Entries use ask; exits use later mid/bid. `None` after hours becomes `expired_no_chain_eod` at zero, conflating outage/missing contract with worthlessness. Four closed/manual historical single-leg records exist, zero open; the working config currently disables paper by omission. |
| **24–28 — backtest** | **Source-confirmed:** synthetic Monte Carlo, a replay scaffold/fill model, baseline surrogate runner, metric helpers, and walk-forward window generation exist. **Stale/wrong:** “honest real-options backtest,” same production path, or +4–6% evidence. **Unknown:** results on a valid point-in-time options dataset. | `backtest/engine.py` bakes regime accuracies into agents and then rediscovers them. `/api/backtest` also fabricates random votes/outcomes. `backtest/replay.py` loads the whole Parquet despite “lazy” prose, assigns minute-bar low/high as bid/ask, and gives exchange/arrival the same timestamp. `backtest/runner.py` uses SMA/fade surrogates and SPX-move P&L; despite its header, it does not import/use the production risk gate, Kelly sizer, paper broker, strategy selector, or LLM pit. D2DT Parquet fixtures referenced at `/home/dhawal/...` are absent here. |
| **29–31 — DuckDB / persistence** | **Source-confirmed:** persistence and local artifacts. **Stale/wrong:** current, clean, point-in-time evidence or trustworthy dashboard win rate. **Unknown:** edge. | Read-only aggregates show 23 market snapshots, 22 simulation results, 528 vote rows (22×24), 4 paper positions, and data ending 2026-06-16. Source mix is yfinance or Finnhub quote + yfinance options; no stored Schwab/Polygon/Tradier/Alpha/FlashAlpha/floww-produced cycle was observed. `get_signal_stats()` treats every non-pending row—including `gated` and `closed`—as resolved, diluting win rate. Schema lacks provider entitlement/model-call success and market-event arrival-time provenance needed for point-in-time research. |
| **32–34 — web / TUI / CLI** | **Source-confirmed:** FastAPI/static/WebSocket dashboard, Textual TUI, and CLI commands exist. **Stale/wrong:** production-ready/secure implication. **Unknown:** runtime UX/availability. | CLI help imports successfully. Services were not started. Web defaults document binding `0.0.0.0`; cycle trigger, risk reset/trip, and custom-agent mutation routes have no authentication boundary visible in the router. The dashboard backtest endpoint is synthetic. |
| **35–37 — alerts** | **Source-confirmed:** Telegram/Slack formatters, senders, dispatcher, and unit tests exist; web lifespan starts/stops its dispatcher. **Stale/wrong:** scheduler alert delivery as currently wired. **Unknown:** real delivery. | `SwarmScheduler.__init__` creates `AlertDispatcher` but never calls `.start()` or `.stop()`, even though comments assume it is consuming the event bus. Alert variable names are absent from the local `.env` scan, so sender functions would no-op/fail-soft here. No external message was sent. |
| **38–39 — schedulers** | **Source-confirmed:** an ET-aware five-slot scheduler and a second interval loop exist. **Stale/wrong:** Friday Pin auto-schedule and market-hours-safe root scheduler. **Unknown:** deployed cron/process uptime. | `swarmspx/scheduler.py` schedules 08:00, 09:35, 11:30, 14:00, 15:45 ET and does not invoke Friday Pin. Its daily-summary filtering/label uses naive local `datetime.now()` despite the main loop using ET. Root `scheduler.py` runs forever at the configured interval with no market-hours guard. Morning briefing is Schwab-centric, so its usefulness without Schwab is unproven. |
| **40–42 — configuration** | **Source-confirmed:** dirty-state and runtime drift. **Stale/wrong:** clean/consistent/current documentation. **Unknown:** whether the dirty edit is intentional. | The committed file is OpenRouter-only plus explicit risk and enabled paper. The working file adds unused legacy/local/Claude definitions, keeps Owl routing, removes risk/paper, and adds disabled inert `godmode`. `.env.example` omits the currently required OpenRouter variable and newer provider names, while advertising Alpaca settings unused by swarmSPX. Do not overwrite the dirty file until its owner resolves intent. |
| **43–48 — tests / baseline** | **Source-confirmed:** 23 test files and 324 collected cases. **Stale/wrong:** “~20 tests” if meant as cases, and all-green/current baseline. **Unknown:** full suite and live integration. | Collection completed (`324 tests collected`). A bounded 107-test audit selection produced **100 passed, 4 failed, 3 skipped**. Failures: two stale/direct AgentForge tests (missing loaded OpenRouter env and old Llama/Phi expectations), one network-dependent yfinance ingest test, and one wall-clock-dependent engine outcome test that becomes scratch after EOD. Three replay/runner tests skip because hard-coded D2DT Parquet is absent. No full suite was run. |
| **49–53 — marketing / product claims** | **Source-confirmed:** marketing assets and the claims themselves exist. **Stale/wrong:** live-source, validated-edge, honest-backtest, 30-day-paper, and weekly-walk-forward claims. **Unknown:** pricing, demand, and operational service. | `marketing/index.html` says live Schwab/Tradier, free CBOE OI + Schwab Greeks, honest Polygon-derived execution backtest, documented Friday edge, every-signal shadow positions, and weekly walk-forward reports. Current source/artifacts do not substantiate those claims. Repository prose saying NVDA/TSLA produces “4×” opportunity is an arithmetic hypothesis (more names/events), **not tested alpha or return evidence**; the available naive single-name baselines are negative. |
| **54 — godmode** | **Source-confirmed:** a disabled YAML block exists. **Stale/wrong:** implemented capability. **Unknown:** product intent. | No Python, test, prompt builder, or import references `godmode`. Adding the block while removing risk/paper makes the dirty config operationally worse even though the block is inert. Keep it outside production trading scope. |
| **55–61 — remove/demote recommendations** | **Source-confirmed as candidates, not as completed work.** **Unknown:** final product decisions. | Source supports demoting synthetic backtest results, Friday Pin “validated” status, Godmode, dead floww proxy prose, stale model/provider documentation, and unauthenticated/public marketing. Removing Schwab/direct providers is **not safe as an isolated deletion** until a replacement data contract passes fixtures. Deletion/demotion choices are recommendations requiring an owner decision; no source inspection can mark them completed. |
| **62 — 30-day paper gate** | **Stale/wrong if claimed met.** | Only four historical single-leg paper records exist, none open, and the database ends 2026-06-16. Execution lacks spread legs/slippage/fees and current working config disables paper. This gate is unmet. |
| **63 — option-chain walk-forward gate** | **Stale/wrong if claimed met.** **Unknown:** future result. | Window-generation tests exist, but no local point-in-time historical option-chain dataset or production-path walk-forward result exists. SPY-bar proxy results do not satisfy this gate. Polygon historical/options entitlement is unknown and must be verified contractually, not inferred from a key name. |
| **64 — 0.1× live gate / exclusion** | **Source-confirmed as excluded from current readiness; unmet as a promotion gate.** | There is no live execution adapter in the engine path; `.env.example` calls Alpaca “future auto-execution.” Given gates 62–63 are unmet, 0.1× live execution must remain excluded. Its eventual safety/performance is unknown. |

## Recorded artifact facts (read-only DuckDB)

- `market_snapshots`: 23; `simulation_results`: 22; `agent_vote_history`: 528; `paper_positions`: 4.
- Snapshot interval: 2026-05-23 through 2026-06-16; stale by the audit date.
- Provider combinations: 11 yfinance/yfinance, 8 yfinance/no-options-source, 4 Finnhub/yfinance.
- Finnhub-labeled `spx_price`: 741.75–754.83; yfinance-labeled `spx_price`: 7403.69–7474.07. This is direct evidence of proxy-unit contamination.
- Outcomes: 13 gated, 4 closed, 3 win, 1 loss, 1 scratch. Those categories must not share a “resolved” denominator.
- Final-round votes: BULL 193, BEAR 51, NEUTRAL 284. Exactly 172 are `NEUTRAL/50`; cycles 1–3 and 11–13 contain 24/24 of that sentinel. Because reasoning/error fields are not stored, this is strong fallback-pattern evidence, not proof of each root cause.
- No row proves which model/provider answered, whether calls succeeded, or which vendor entitlement supplied any individual quote.

## Relationship to floww and scope decision

Canonical floww is `/Users/nav/Documents/GitHub/floww`. Its accepted data-source ADR says Public.com brokerage API → cvserver/CVForge → yfinance + Databento overlay. “Public API” there means **Public.com**, which requires a key; it does not mean unauthenticated/public-domain data. Recent floww policy tests require no Schwab/Alpha Vantage live routes, although legacy Schwab-named harness/tests remain.

The overlap is substantial: provider adapters, chain normalization, GEX, risk, paper execution, replay, scheduling, and web surfaces. swarmSPX's `floww_proxy.py` is dead code and incompatible with `OptionContract.from_raw`: it emits top-level Greeks and `oi`, while the parser expects nested `greeks` and `open_interest`; it also returns `spot` where engine snapshots require `spx_price`. Adding another provider stack to swarmSPX would deepen duplication.

Recommended ownership boundary:

- **floww owns market-data acquisition, licensing/entitlements, normalization, GEX, and historical point-in-time chain storage.**
- **swarmSPX owns agent orchestration, consensus/audit semantics, strategy research, and a consumer-side risk/paper experiment until promotion.**
- Exchange a versioned, read-only snapshot contract containing canonical instrument identity (`SPX index` versus `SPY ETF`), units/multiplier, exchange and arrival timestamps, source/entitlement class, delayed/stale flags, expiration, OCC identity, NBBO, OI, nested Greeks, and provenance.

This audit and contract definition fit the present four-agent audit scope. Cross-repository implementation, provider deletion, historical data acquisition, and strategy promotion are a **separate program** with explicit ownership, licensing, and migration gates. Do not delete Schwab in swarmSPX merely because floww deleted its brokerage surface; first choose whether swarmSPX becomes a thin floww consumer or remains standalone.

## Prioritized contract-ready work slices

### P0 — credential containment (operations, independent)

Targets: `/Users/nav/GitHub/swarmSPX/.git/config`, credential provider settings.
Acceptance: embedded credential revoked/rotated; `origin` URL contains no userinfo/token; a redacted check proves it; no secret added to shell history/report.
Dependency/gate: repository owner access. This does not wait for architecture work.

### P0 — instrument identity and ingest fail-closed contract

Targets: `swarmspx/ingest/market_data.py`, `finnhub.py`, `alpha_vantage.py`, `options.py`, new offline fixtures/tests under `tests/`.
Acceptance: every snapshot declares symbol, asset type, price unit/multiplier, source, as-of and received time; SPY can never populate an SPX field without explicit tested conversion or rejection; quote/chain symbol mismatches reject; no premium lookup converts “not found” to worthless. Provider order is one documented table used for quote, chain, and mark lookup.
Dependency/gate: choose standalone versus floww-consumer architecture; vendor entitlement remains outside unit tests.

### P0 — correct sizing and execution invariant

Targets: `swarmspx/risk/sizer.py`, `risk/gate.py`, `engine.py`, `tests/test_risk.py`, `tests/test_engine_wiring.py`.
Acceptance: Kelly formula is tested for asymmetric payoffs, zero/negative edge, caps, and bankroll units; no trade-card dispatch/paper open when contracts are zero; risk limits use actual ledger dollars; staleness is appropriate for 0DTE; sizing locks include formula/input/schema version and cannot silently preserve obsolete logic.
Dependency/gate: risk owner signs off on `p`, payoff convention, fractional Kelly, and max-loss policy. No empirical estimate means fail closed.

### P0 — reconcile configuration and startup preflight

Targets: `config/settings.yaml` (preserve owner changes), `.env.example`, `swarmspx/providers.py`, `agents/forge.py`, `engine.py`, README, config tests.
Acceptance: one schema-valid configuration; explicit paper/risk state; custom `settings_path` reaches forge/reporter/engine; startup preflight reports missing providers/models without exposing values; docs match actual route; inert Godmode is removed from production config or isolated in an experimental file.
Dependency/gate: owner resolves dirty-file intent and chooses supported model provider. Do not overwrite first.

### P1 — agent-call truth and consensus quorum

Targets: `swarmspx/agents/base.py`, `simulation/pit.py`, `db.py`, schema migration, web state/tests.
Acceptance: each vote records provider/model, attempt status, latency, parse status, and a redacted error code; fallback sentinel is not counted as successful participation; consensus requires a configured success quorum and reports degraded cycles; no 24-row count can masquerade as 24 successful agents.
Dependency/gate: P0 config preflight and a backward-compatible DuckDB migration.

### P1 — strategy-capable paper ledger

Targets: `swarmspx/paper.py`, `engine._extract_strategy_meta`, DB schema, `tests/test_paper.py`, strategy fixtures.
Acceptance: normalized order/position/leg/fill tables support straight, vertical, and condor structures; entry/exit use timestamped NBBO with explicit fill policy, fees and slippage; missing quote stays `unpriced` and never means worthless; expiry is established from contract identity/calendar; reconciliation is reproducible.
Dependency/gate: P0 ingest contract and correct sizer. Only after this can the 30-day clock start.

### P1 — honest historical-options replay and Friday Pin falsification

Targets: `swarmspx/backtest/replay.py`, `runner.py`, `strategies/friday_pin.py`, tests and immutable result manifest; deprecate `backtest/engine.py` and `/api/backtest` as evidence.
Acceptance: point-in-time SPX and option NBBO/OI/Greeks with arrival timestamps; real condor legs; commissions/slippage; event exclusions; at least 50 Fridays; time-ordered walk-forward/embargo; frozen holdout; reproducible dataset hash/config/commit/result; compare against no-trade and simple baselines. Result may be REJECT.
Dependency/gate: licensed historical data and P1 paper/execution semantics. Yahoo 12-month 1-minute availability and Polygon free/full-Greeks access cannot be assumed.

### P1 — scheduler/alert and surface safety

Targets: `swarmspx/scheduler.py`, root `scheduler.py`, `alerts/dispatcher.py`, `web/app.py`, `web/routes.py`, tests.
Acceptance: dispatcher lifecycle is started/stopped exactly once; all dates/slots are ET; duplicate schedule implementations consolidated; market calendar/holiday guard; stateful strategy receives its history; mutation/risk endpoints require auth; localhost is default bind; offline lifecycle tests prove dispatch and no double-fire.
Dependency/gate: no live message/service in unit tests; Friday Pin remains disabled until its evidence gate passes.

### P2 — floww ↔ swarmSPX snapshot contract (separate cross-repo program)

Targets: swarm `ingest/floww_proxy.py` and parser; floww versioned read-only endpoint/fixtures/ADR.
Acceptance: shared JSON-schema/typed fixture; SPX/SPY identity and units; nested Greeks/OI naming parity; provenance/delay/entitlement fields; timeout/circuit behavior; consumer contract tests run offline in both repos; direct provider removal occurs only after parity and rollback plan.
Dependency/gate: owner/API/auth/licensing/SLA decision. If “public-only” means no authenticated/proprietary feeds, Public.com/cvserver/Databento do not satisfy that wording and yfinance limitations must be explicit.

### P2 — evidence-aware DuckDB/dashboard/marketing

Targets: `swarmspx/db.py`, schema migrations, `web/routes.py`, dashboard labels, README, `marketing/index.html`, `.review` result notes.
Acceptance: stats denominator is explicit; gated/scratch/closed/unpriced separated; corrupt SPY-as-SPX rows quarantined rather than silently mixed; model/data/execution provenance visible; synthetic/demo results labeled and excluded from performance; unsupported live/edge/paper/walk-forward statements removed or qualified.
Dependency/gate: migration plan preserves the existing ignored local DB; marketing cannot lead evidence.

## Promotion gates

1. **Research-only now:** no provider/model/paper result in this audit establishes alpha.
2. **Start 30-day paper clock only after** source identity, correct sizing, multi-leg fills, fees/slippage, quote-outage semantics, and immutable audit provenance pass offline tests.
3. **Run options walk-forward only after** point-in-time historical option-chain rights and dataset integrity are documented. A SPY price proxy is insufficient.
4. **Keep 0.1× live excluded** until 30-day reconciled paper evidence and the options walk-forward gate both pass, followed by explicit human authorization and operational chaos/idempotency checks.

## Verification performed

- Fresh git branch/status/upstream/ahead checks; remote names only in output.
- Source searches and line-level inspection across ingest, agents/providers, engine/risk/paper, replay/backtest, Friday Pin, DB, scheduler/alerts, web/TUI, README/docs/marketing, requirements, and config diff.
- Read-only DuckDB queries (`read_only=True`) for schema, counts, source/scale ranges, outcomes, paper rows, and vote-shape aggregates.
- Local executable/version/import checks only; no model invocation or daemon/service start.
- Pytest collection only plus the bounded targeted baseline summarized above; no full suite.
- No repository file was changed by this audit. The sole report artifact is this file under `/private/tmp`.
