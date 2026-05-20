# Project Oracle — ROUND 3 Dispatch Plan

**Pairs with:** `DISPATCH_PLAN_ORACLE.md` (Round 1 — foundation), `DISPATCH_PLAN_ORACLE_ROUND2.md` (Round 2 — advancement)
**Triggered by:** each agent's `memory/agent<N>_round2_complete.md` file
**Coordinator:** Agent 8 (kanban) watches `kanban/SWARM_STATUS.md` for Round 2 → Round 3 transitions
**Architect framing:** PhD math/physics, ex-Jane Street HFT. Every task cites the paper/theory it implements.

---

## Standing preamble (prepend to every Round 3 prompt)

```
TIME-WINDOW STRATEGY:
  Window A — when Nav is home (evenings/weekends): Mongo + Schwab LIVE.
    Do all data-hungry work, live training, backfills, network-dependent tests.
  Window B — Nav at work (~8am-5pm ET weekdays): Atlas SSL blocked.
    Detect via ServerSelectionTimeoutError(5s). Fall back to:
      • backend/.duckdb_cache/ for persistence
      • backend/.mongo_retry_queue/<iso-ts>.json for deferred writes
    Continue Window-B-safe tasks (pure compute, docs, math validation).

OPERATING LAWS (code-enforced):
  • bash qc/audit/truth_audit.sh GREEN before AND after each commit
  • TDD: failing test first, see fail, implement, see pass
  • Conventional commits: <type>(scope): ...
    Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  • NEVER --no-verify, --amend, force-push main
  • Commit per deliverable; push immediately
  • No synthetic data in production paths
  • Mathematical claims cite the paper

EXECUTION DISCIPLINE (skill: subagent-driven-development):
  Per deliverable: dispatch swarmclaw:coding-agent worker → spec review → quality review.
  Re-dispatch on issues. Both reviews must pass before next deliverable.

STOP CONDITIONS:
  • Truth audit red → remediation only
  • Deliverables all shipped → memory/agent<N>_round3_complete.md, exit
  • 3 push failures → checkpoint to kanban card, exit clean
  • Token exhaustion → checkpoint, exit; next worker resumes
```

---

## <a id="agent-1"></a>Agent 1 — Round 3: paper-trade execution engine (card: O-PHASE1-SCHWAB)

**Round 1 shipped:** schwab_streamer.py, ingestion_pipeline.py, mock_schwab_feed.py
**Round 2 shipped:** L2 depth, replay engine, Schwab health endpoint, token refresh, cross-source GEX consistency
**Round 3 goal:** Wire Schwab's paper-trading order endpoints to Hermes signals. Build the **order routing layer** that the Project Oracle directive's "execution doctrine" needs (Tap Probability decay, deflection-zone-only entries, 3:1 R:R minimum).

### Tasks

**1. Paper-trade order client `[A]`**
- Files: `backend/services/order_router.py`, `backend/tests/services/test_order_router.py` (15+ tests)
- Wrap Schwab's `/v1/accounts/{account}/orders` endpoint (paper account first)
- Order types supported: LIMIT (default), STOP, STOP_LIMIT, MARKET (gated behind config flag — never default)
- Idempotency: every `TradeIntent` generates a deterministic `client_order_id = hash(intent.signal_id + intent.timestamp_us)`. Submit twice → server returns same fill, never duplicates.
- Position-state tracker (in-process + Mongo persistence): current positions per ticker, P&L unrealized, P&L realized 24h
- Reference: Schwab Trader API v1 docs
- **Verification:** integration test against Schwab's sandbox endpoint
- **Acceptance:** 100 simulated orders → 100 distinct fills, 0 duplicates, idempotency confirmed

**2. Signal-to-intent translator `[B]`**
- Files: `backend/services/signal_translator.py`, `backend/tests/services/test_signal_translator.py` (12+ tests)
- Input: anomaly_score, gex_state, trinity_score, current positions
- Output: `TradeIntent` (or None) — explicit fields: ticker, side, qty, order_type, limit_price, stop_loss, take_profit, signal_id, conviction
- Conviction = function of (anomaly_score × trinity_score × inverse_VPIN). Above 0.7 → tradeable.
- Risk gates (every gate must pass before TradeIntent emitted):
  - Position size ≤ max_position_pct × account_equity (default 1%)
  - Adverse-news filter: skip if FlashAlpha social_sentiment z-score < -2
  - Concentration limit: ≤ 3 open positions per ticker
  - Liquidity gate: skip if Kyle's λ > λ_threshold (illiquid market)
- **Reference:** Almgren-Chriss (2001) "Optimal Execution of Portfolio Transactions" for sizing
- **Acceptance:** every conviction × position-size combination produces a valid intent or NULL, never an undefined edge

**3. Execution doctrine enforcer `[B]`**
- Files: `backend/services/execution_doctrine.py`, `backend/tests/services/test_execution_doctrine.py` (10+ tests)
- Implements Skylit's published rules (also in `SKYLIT_FEATURES.md`):
  - **Tap Probability decay:** if node is Fresh → enter; Tested → only if 3:1 R:R; Delivered → skip; Decaying → never
  - **Deflection zones only:** entry must be within 0.1% of a King/Floor/Ceiling node
  - **Never trade the midpoint:** if spot is between nodes by >0.5%, refuse
  - **3:1 R:R minimum:** (take_profit - entry) / (entry - stop_loss) ≥ 3.0 for longs, mirrored for shorts
- **Verification:** for each rule, write a positive + negative test (rule fires when it should, doesn't when it shouldn't)
- **Acceptance:** A `TradeIntent` that fails any rule is rejected with a documented `rejection_reason`

**4. Fill-quality monitor `[A]`**
- Files: `backend/services/fill_monitor.py`, `backend/tests/services/test_fill_monitor.py` (8+ tests)
- After each fill: compute slippage_bps = (fill_price - limit_price) / limit_price × 10000
- Track p50/p95/p99 slippage rolling 24h per ticker
- Alert if p95 > 5 bps (paper-trade should be ~0 since Schwab's paper engine fills at NBBO)
- Compare paper vs live (later): if live p95 - paper p95 > 3 bps, flag execution-quality degradation
- **Acceptance:** p95 slippage tracker emits Prometheus metric `floww_fill_slippage_bps_p95` to Agent 10's dashboard

**5. Position-reconciliation loop `[A]`**
- Files: `backend/services/position_reconciler.py`, `backend/tests/services/test_position_reconciler.py` (6+ tests)
- Every 60s during market hours: pull positions from Schwab → compare to local position tracker
- Discrepancies (Schwab says we own 100 SPY, local says 80) → log + auto-reconcile to Schwab's view + emit reconciliation_event
- **Reference:** Lo (2002) "The Statistics of Sharpe Ratios" for tracking accuracy
- **Acceptance:** 24h reconciliation log shows zero divergences in a healthy run

### Skills
`hermeshub:api-builder`, `swarmclaw:coding-agent`, `hermeshub:agent-hardening`, `red-teaming:godmode` (for the idempotency stress test)

### Risks
- Schwab sandbox may rate-limit aggressively → batch submission, exponential backoff
- `MARKET` orders + thin liquidity → catastrophic slippage. Default to LIMIT, require explicit flag to enable MARKET.
- Time-zone bugs in fill-quality NBBO comparison → use UTC throughout, convert only at display

### Math citations
- **Almgren, Chriss (2001):** "Optimal Execution of Portfolio Transactions" — risk-adjusted execution
- **Lo (2002):** "The Statistics of Sharpe Ratios" — reconciliation tracking
- **Hasbrouck (2007):** "Empirical Market Microstructure" — slippage modeling

---

## <a id="agent-2"></a>Agent 2 — Round 3: Reinforcement-learning policy (card: O-PHASE2-ANOMALY)

**Round 1 shipped:** 1D-CNN AE, HuggingFace asset acquisition, regime-aware thresholds
**Round 2 shipped:** PatchTST VPIN forecaster, Autoformer chain dynamics, ensemble inference, backtest, trained model checkpoint
**Round 3 goal:** Train an **RL policy** that consumes the ensemble signals + position state + GEX regime, and outputs `TradeIntent`s. This is the bridge from "anomaly detector" to "autonomous trader" — same shape as Renaissance/Citadel quant pods.

### Tasks

**1. Trading environment (Gym-compatible) `[A]`**
- Files: `backend/services/rl/trading_env.py`, `backend/tests/services/rl/test_trading_env.py` (15+ tests)
- Observation space (continuous, 64-dim):
  - GEX features (6): zscore_60d, ROC_5d, regime_pos, distance_to_flip_norm, wall_density_pct, herfindahl
  - VPIN ensemble (3): vpin_current, vpin_cdf, vpin_forecast_15min
  - Trinity (1): score
  - Position state (4): qty_held, unrealized_pnl_pct, time_in_trade_minutes, drawdown_pct
  - Anomaly (2): anomaly_score, anomaly_regime_index
  - Microstructure (5): kyle_lambda, amihud, qi_zscore, hawkes_branching_ratio, fragility_score
  - Underlying (4): return_1min, return_5min, return_30min, atr_pct
  - Calendar (6): minutes_to_close, day_of_week, days_to_OPEX, days_to_FOMC, earnings_flag, vix_level
  - History buffer (33): last 33 observations of vpin_current (for sequential context)
- Action space (discrete, 5): {-2: strong sell, -1: sell, 0: hold, +1: buy, +2: strong buy}
- Reward function (per `Schreckenberg & Kanazawa 2020`):
  - r_t = ΔPnL_t - λ × |Δposition_t| × kyle_lambda - μ × adverse_excursion_t
  - λ = 0.5 (transaction cost weight), μ = 1.0 (drawdown weight)
- Episode: one trading day. Reset at market open.
- **Reference:** Brockman et al. (2016) "OpenAI Gym"; Sutton-Barto (2018) §13
- **Acceptance:** Random policy completes 100 episodes without crashes; reward distribution non-degenerate

**2. PPO trainer `[A]`**
- Files: `scripts/train_rl_policy_ppo.py`, `./project_oracle/models/rl_policy_v1.pt`, `qc/data/rl_policy_v1_manifest.json`, `backend/tests/services/rl/test_ppo_training.py` (10+ tests)
- Use Stable-Baselines3 PPO (or `cleanrl/ppo.py` if SB3 too heavy)
- Architecture: 2-layer MLP (256, 128) for policy + value heads
- Hyperparameters (start; tune later):
  - lr=3e-4, clip_range=0.2, ent_coef=0.01, vf_coef=0.5
  - n_steps=2048, n_epochs=10, gae_lambda=0.95, gamma=0.99
- Train data: replay through Agent 1's `replay_engine.py` over last 6 months of Schwab/Databento data
- **Reference:** Schulman et al. (2017) "Proximal Policy Optimization"
- **Acceptance:** mean episode reward strictly increases over 1000 iterations; Sharpe of policy returns > 1.0 on held-out month

**3. Reward-shaping ablation `[B]`**
- Files: `reports/rl_reward_ablation_<date>.md`
- Try 4 reward variants, train each for 500 iterations:
  - Variant A: ΔPnL only (baseline)
  - Variant B: ΔPnL - λ × transaction_cost
  - Variant C: ΔPnL - λ × tc - μ × drawdown (main)
  - Variant D: variant C + Sortino-shaped (downside variance penalty)
- Report: final Sharpe, max DD, win rate, avg trade duration per variant
- **Reference:** Sortino-Price (1994) "Performance Measurement in a Downside Risk Framework"
- **Acceptance:** ablation report identifies the optimal variant + justifies it numerically

**4. Policy distillation to faster inference `[B]`**
- Files: `scripts/distill_policy.py`, `./project_oracle/models/rl_policy_distilled_v1.onnx`
- Take the trained PPO policy → distill to a 2-layer MLP (64 hidden units) with knowledge distillation
- Convert to ONNX for sub-1ms inference at the request handler
- **Reference:** Hinton, Vinyals, Dean (2015) "Distilling the Knowledge in a Neural Network"
- **Acceptance:** distilled policy matches teacher's actions ≥98% of the time on held-out trajectories; inference <1ms CPU

**5. Online-learning continuous adaptation `[A]`**
- Files: `backend/services/rl/online_adapter.py`, `backend/tests/services/rl/test_online_adapter.py` (8+ tests)
- After market close each day: replay the day's trades + market data
- Compute realized reward per state-action pair → small gradient step on the policy (lr=1e-5)
- Save daily snapshots; rollback if 7-day Sharpe drops below baseline by 2σ
- **Reference:** Lillicrap et al. (2016) "Continuous Control with Deep Reinforcement Learning" (DDPG online update mechanics)
- **Acceptance:** 30-day continuous-learning run shows monotone-or-better Sharpe vs frozen-policy baseline

### Skills
`mlops:dspy` (structured prompts for RL hyperparameter sweep), `mlops:evaluating-l...`, `autonomous-ai-agents:codex` (long training scripts), `gbrain:academic-verify` (cross-check PPO impl against Schulman paper)

### Risks
- RL policies can blow up — wire the kill-switch to position_reconciler (Agent 1) before any live capital touches this
- Reward hacking: agent might learn to never trade → mean episode reward floor enforcement
- Distribution shift between training (Databento replay) and live (Schwab WS) → online adaptation handles small shifts; large shifts trigger retraining card

### Math citations
- **Schulman et al. (2017):** "Proximal Policy Optimization Algorithms"
- **Sutton, Barto (2018):** *Reinforcement Learning: An Introduction*, 2nd ed.
- **Sortino, Price (1994):** "Performance Measurement in a Downside Risk Framework"
- **Hinton, Vinyals, Dean (2015):** "Distilling the Knowledge in a Neural Network"

---

## <a id="agent-3"></a>Agent 3 — Round 3: Skylit visual parity + Atlas charting depth (card: O-PHASE3-DASH)

**Round 1 shipped:** 5 Dash tabs (Heatseeker, Flowseeker, Toxicity, Vol Surface, Trinity)
**Round 2 shipped:** Atlas tab, Replay Mode, Agent Hub stub, Nexus stub, polish (themes, shortcuts, mobile)
**Round 3 goal:** **Visual parity with Skylit's commercial product.** Match their layout density, color palette, interaction patterns. Add the charting depth a serious trader expects (Heatseeker overlays on TradingView-grade candlesticks).

### Tasks

**1. TradingView lightweight-charts integration `[B]`**
- Files: `backend/services/dash_ui.py` (Atlas tab rewrite), `frontend/src/components/charts/` (if React micro-frontend)
- Replace Plotly candlestick with `lightweight-charts` (Apache-2.0 license, sub-10ms render)
- Overlays as separate layers (toggle independently): King Nodes, ZG levels, Air Pockets, Trinity markers, anomaly events, dealer-walls
- Interaction: click any overlay → side panel shows the underlying calculation (which trades drove this King Node etc.)
- **Reference:** TradingView lightweight-charts docs
- **Acceptance:** 4-hour candlestick window renders in <500ms on average laptop

**2. Heatseeker visual parity `[B]`**
- Files: `backend/services/dash_ui.py` (Heatseeker tab restyle)
- Match Skylit's color palette: red→white→green for negative→zero→positive GEX
- Node markers: Skylit uses concentric circles sized by |GEX| — replicate exactly
- Hover tooltip shape: 8-line summary (strike / net_gex / tap_count / state / tap_probability / signed_gex / total_oi / time_first_seen)
- Animation: when a new King Node forms, brief pulse animation (transitions <300ms)
- **Reference:** SKYLIT_FEATURES.md (the feature parity ledger)
- **Acceptance:** side-by-side screenshot diff with Skylit (Nav manually) shows ≥90% layout similarity

**3. Flowseeker 20-column live table `[A]`**
- Files: `backend/services/dash_ui.py` (Flowseeker tab extension), `backend/routes/flowseeker.py` (extend with order-flow joins)
- Add 12 more columns to the existing 8: implied_vol, theta_decay, vega_pnl, vanna_pnl, charm_pnl, hedge_pressure, fills_ahead, fills_behind, time_at_bid_ms, time_at_ask_ms, sentiment_score, vix_at_print
- Color-coding per Skylit's rubric:
  - Background: red if size > previous_day_volume; yellow if size > OI; gray otherwise
  - Text: green for above-ask fills, red for below-bid fills
- Sort + filter (any combination of: side, type, size>X, premium>$Y, classification IN {sweep, block, regular})
- Drilldown click: open contract-specific modal with chain context (from Agent 1's data quality service)
- **Acceptance:** 100 prints/sec rendering without UI lag; filter latency <100ms

**4. Replay deep-dive — scenario library `[B]`**
- Files: `backend/services/replay_scenarios.py`, `backend/tests/services/test_replay_scenarios.py` (10+ tests), `backend/services/dash_ui.py` (Replay tab extension)
- Curated scenarios: "FOMC May 2026", "Aug 2024 vol blowup", "0DTE pin Friday", "Earnings squeeze AAPL", "Mar 2020 Covid", "GME Jan 2021 squeeze"
- Each scenario: a JSON spec pointing at the Databento data range + key timestamps to annotate
- UI: dropdown loads scenario → Atlas chart auto-scrolls + plays at 10x → narrative overlay highlights key moments
- **Reference:** behavioral-finance literature on canonical event studies
- **Acceptance:** 6 scenarios load + play end-to-end; narrative annotations align with the documented event timestamps

**5. Touch-input mobile redesign `[B]`**
- Files: `backend/services/dash_ui.py` (mobile CSS), `frontend/src/styles/mobile.css`
- Breakpoints: <600px (phone), 600-1024px (tablet), >1024px (desktop)
- Phone: single-tab view with bottom nav (Heatseeker / Atlas / Toxicity); other tabs accessible from hamburger
- Touch interactions: swipe-left-right between tabs, pinch-to-zoom on candlestick, long-press for node detail
- PWA manifest + service worker for offline-capable widget on iOS/Android home screen
- **Acceptance:** Lighthouse Mobile Performance score ≥90; tap-target sizes ≥44px (Apple HIG)

### Skills
`swarmclaw:coding-agent`, `creative:architecture-diagram` (overlay design), `devops:react-craco...` (frontend builds), `mcp:native-mcp` (expose dashboard components as MCP)

### Risks
- TradingView lightweight-charts license check: Apache-2.0, free for commercial use, no attribution required for SaaS — confirm before adopting
- Mobile PWA caching can cause stale data — versioned cache-busting required

### Math/design citations
- **Cleveland (1985):** *The Elements of Graphing Data* (visual encoding hierarchy)
- **Skylit feature ledger:** `SKYLIT_FEATURES.md`
- **Apple HIG:** touch-target sizing

---

## <a id="agent-4"></a>Agent 4 — Round 3: Property-based + fuzz testing + chaos engineering (card: O-TEST-INFRA)

**Round 1 shipped:** conftest motor refresh, AsyncClient migration, 14 event-loop failures resolved
**Round 2 shipped:** pytest-asyncio auto mode, coverage gates, property-based tests, mutation testing, flaky detector
**Round 3 goal:** **Adversarial robustness.** Property-based testing (Round 2) covers known invariants; Round 3 adds fuzzing (find unknown unknowns) and chaos engineering (system-level failure injection — Mongo down, Schwab disconnect, clock skew, memory pressure).

### Tasks

**1. Hypothesis-stateful tests for the ingestion pipeline `[B]`**
- Files: `backend/tests/stateful/test_ingestion_state_machine.py`, requirements.txt (add `hypothesis>=6`)
- Use `hypothesis.stateful.RuleBasedStateMachine` to model the ingestion pipeline as a state machine
- Rules: `tick_arrives`, `queue_flushes`, `mongo_writes`, `schwab_disconnects`, `schwab_reconnects`, `token_expires`, `token_refreshes`
- Invariants: (a) total bytes in == total bytes out + dropped (no losses), (b) queue depth bounded by max_size, (c) Mongo write order matches arrival order within a ticker
- Hypothesis runs ~10000 random rule sequences; surfaces ordering bugs no human would think to test
- **Reference:** Claessen, Hughes (2000) "QuickCheck"; Hypothesis docs
- **Acceptance:** stateful test finds zero invariant violations on overnight `--max-examples=10000` run

**2. Fuzz testing on the route handlers `[B]`**
- Files: `backend/tests/fuzz/test_route_fuzzing.py`, requirements.txt (add `schemathesis>=3`)
- Use `schemathesis` to fuzz every `/api/*` endpoint against its OpenAPI schema
- Inject random valid-shape payloads + edge cases (max int, negative floats, Unicode bombs, deeply nested JSON)
- Assert: server stays up; no 5xx errors on schema-valid input; sensible 4xx on schema-invalid input
- **Reference:** schemathesis docs; OWASP API Security Top 10
- **Acceptance:** 24h fuzz run produces zero new 5xx errors; all responses match documented schemas

**3. Chaos engineering harness `[B]`**
- Files: `backend/tests/chaos/chaos_runner.py`, `backend/tests/chaos/scenarios/*.yaml`
- YAML-defined chaos scenarios:
  - `mongo_down_60s.yaml`: kill Mongo connection for 60s, assert system stays up, writes queue + drain
  - `schwab_disconnect_5min.yaml`: drop WS for 5 min, assert reconnect + no data loss
  - `clock_skew_2h.yaml`: bump process clock 2h forward; assert TTL-sensitive things behave (token, cache)
  - `memory_pressure_3gb.yaml`: spawn a hog that consumes 3GB; assert process degrades gracefully
  - `disk_full.yaml`: fill `/tmp`; assert DuckDB cache eviction + alert
- Each runs in CI nightly + locally via `make chaos`
- **Reference:** Basiri et al. (2016) "Chaos Engineering" (Netflix paper)
- **Acceptance:** all 5 scenarios pass; system never enters undefined state

**4. Performance regression tests `[B]`**
- Files: `backend/tests/perf/test_p99_latency.py`, `reports/perf_<date>.md`
- Hot-path benchmarks (each must stay within budget per `ARCHITECTURE_DEEP.md`):
  - `calc_gex_per_strike(1000 contracts)`: p99 < 5ms
  - `vpin_engine.update`: p99 < 1ms
  - `hawkes_intensity(t, 500 events)`: p99 < 2ms
  - `SABR.hagan_lognormal_vol`: p99 < 0.5ms (per call)
  - `/api/heatseeker/flip-zones` end-to-end: p99 < 100ms
- Use `pytest-benchmark`; CI fails if any metric regresses >20% vs baseline
- **Reference:** Gil Tene "How NOT to Measure Latency" (HdrHistogram)
- **Acceptance:** baselines locked; every PR's CI reports regression %

**5. Snapshot tests for math correctness `[B]`**
- Files: `backend/tests/snapshots/*.json`, `backend/tests/services/test_snapshot_math.py` (12+ tests)
- For each math kernel, store the output of a canonical input (e.g., Hull textbook example) as a JSON snapshot
- Test re-runs the kernel and asserts output matches snapshot bit-for-bit
- Use `syrupy` or `pytest-snapshot`
- **Why:** catches accidental algorithmic drift that property tests + parity tests might miss (e.g. someone refactors and changes float precision)
- **Acceptance:** 12+ snapshots locked; any drift requires explicit snapshot update via `--snapshot-update`

### Skills
`hermeshub:agent-hardening`, `swarmclaw:coding-agent`, `gbrain:academic-verify` (for property invariants vs published proofs)

### Risks
- Hypothesis stateful tests can slow CI → mark as `@pytest.mark.slow`, run nightly not on every PR
- Chaos tests need root or container privileges → run in Docker, gate on `--chaos` flag

### Citations
- **Claessen, Hughes (2000):** "QuickCheck: A Lightweight Tool for Random Testing of Haskell Programs"
- **Basiri et al. (2016):** "Chaos Engineering"
- **Gil Tene:** "How NOT to Measure Latency" (talk + HdrHistogram)

---

## <a id="agent-5"></a>Agent 5 — Round 3: Causal inference + counterfactual reasoning (card: O-MATH-VALID)

**Round 1 shipped:** ARCHITECTURE.md, RUNBOOK.md, math validation extension, API docs, notebook tutorial
**Round 2 shipped:** reference-repo parity (5+ repos), math correctness dashboard, ARCHITECTURE_DEEP.md, THEORY.md, 5 notebook tutorials
**Round 3 goal:** Move from **descriptive** ("VPIN is high") to **causal** ("a 1bp move in VPIN *causes* a 0.3bp move in spread, controlling for vol regime"). Implement Pearl-style do-calculus on the dealer-hedging system.

### Tasks

**1. Causal DAG of the dealer-hedging system `[B]`**
- Files: `docs/causal/dag.md` (Mermaid diagram), `backend/services/causal/dag.py`, `backend/tests/services/causal/test_dag.py` (8+ tests)
- Nodes (each observable Hermes signal): spot, GEX, VPIN, QI, kyle_lambda, dealer_hedge_pressure, realized_vol, anomaly_score
- Edges (causal arrows from theory):
  - spot → GEX (mechanical), GEX → dealer_hedge_pressure (theoretical)
  - dealer_hedge_pressure → spot (feedback), VPIN → spread → kyle_lambda
  - realized_vol ↔ dealer_hedge_pressure (mutual)
- Validate DAG via `dowhy.causal_graph.CausalGraph` (add to requirements)
- **Reference:** Pearl (2009) *Causality*, 2nd ed; Schölkopf, Locatello, Bauer, Ke, Kalchbrenner, Goyal, Bengio (2021) "Toward Causal Representation Learning"
- **Acceptance:** DAG passes acyclicity check; renders cleanly in mkdocs

**2. Average treatment effect (ATE) estimation `[A]`**
- Files: `backend/services/causal/ate_estimator.py`, `backend/tests/services/causal/test_ate.py` (10+ tests)
- For each treatment (e.g. "GEX flips negative") and outcome (e.g. "realized vol increases over next 30 min"):
  - Use `dowhy` library to compute ATE via propensity score + IPTW
  - Or use `EconML.dml.LinearDML` for double machine learning
  - Confidence intervals via bootstrap (B=1000)
- Run on historical Databento data (Window A — needs Mongo backfill)
- **Reference:** Imbens, Rubin (2015) *Causal Inference for Statistics, Social, and Biomedical Sciences*; Chernozhukov et al. (2018) "Double/Debiased Machine Learning"
- **Acceptance:** ATE point estimates + 95% CIs for 5 named treatments → `reports/causal_ate_<date>.md`

**3. Counterfactual scenario engine `[B]`**
- Files: `backend/services/causal/counterfactual.py`, `backend/tests/services/causal/test_counterfactual.py` (8+ tests)
- API: `simulate_counterfactual(observation, intervention) → counterfactual_outcome`
- Example: "given the May 15 2025 observation, what would happen if VPIN had been 50% lower?"
- Use the DAG + learned structural equations (from `dowhy.gcm`)
- **Reference:** Pearl (2018) *The Book of Why* §4 (counterfactuals)
- **Acceptance:** 3 named counterfactuals execute end-to-end; results match published economic intuition (e.g. lower VPIN → tighter spread)

**4. Granger-causality for Trinity Alignment `[A]`**
- Files: `backend/services/causal/granger.py`, `backend/tests/services/causal/test_granger.py` (8+ tests), `docs/THEORY.md` (extend Trinity section)
- Test: does SPX's GEX Granger-cause SPY's GEX? QQQ's?
- Use `statsmodels.tsa.stattools.grangercausalitytests` with lags 1, 5, 15 min
- Multivariate VAR fit on all 3 series; check stationarity (ADF test) first
- **Reference:** Granger (1969); Hamilton (1994) *Time Series Analysis* Ch. 11
- **Acceptance:** Granger p-values + F-stats for each pair; if SPX→SPY p<0.01, Trinity gets a "leading-lagging" score

**5. Causal-validated trade rationale `[A]`**
- Files: `backend/services/causal/trade_rationale.py`, `backend/routes/causal.py`, `backend/tests/services/causal/test_trade_rationale.py` (8+ tests)
- For each TradeIntent emitted by Agent 2's RL policy: query the causal model for a 1-sentence explanation
- Output shape: `{intent_id, primary_cause: "negative GEX (z=-2.1) + VPIN spike (cdf=0.87)", supporting_evidence: [...], counterfactual: "if VPIN had been at median, intent would not have fired"}`
- Endpoint: GET /api/causal/explain/{intent_id} → returns the rationale
- **Acceptance:** every RL TradeIntent gets a causal rationale within 100ms; rationale is human-readable

### Skills
`gbrain:academic-verify` (Pearl, Imbens, Chernozhukov citations), `mlops:dspy` (LLM-shaped rationale generation), `data-science:jupyter-live-kernel` (notebook for ATE viz), `creative:architecture-diagram` (DAG mermaid)

### Risks
- Causal inference requires strong assumptions (no unobserved confounders, etc.) — document explicitly in `docs/causal/ASSUMPTIONS.md`; otherwise risk of spurious conclusions
- Granger causality ≠ causation in Pearl's sense — paper acknowledges; use Granger only as preliminary screen

### Citations (PhD-level rigor)
- **Pearl (2009):** *Causality: Models, Reasoning, and Inference*, 2nd ed., Cambridge UP
- **Pearl (2018):** *The Book of Why*, Basic Books
- **Imbens, Rubin (2015):** *Causal Inference for Statistics, Social, and Biomedical Sciences*, Cambridge UP
- **Chernozhukov et al. (2018):** "Double/Debiased Machine Learning for Treatment and Structural Parameters" — *Econometrics Journal*
- **Granger (1969):** "Investigating Causal Relations by Econometric Models and Cross-Spectral Methods" — *Econometrica*
- **Schölkopf et al. (2021):** "Toward Causal Representation Learning"

---

## <a id="agent-6"></a>Agent 6 — Round 3: Knowledge graph + LLM-augmented research (card: O-RESEARCH-LOOP)

**Round 1 shipped:** continuous arxiv loop, clone-and-extract pipeline
**Round 2 shipped:** expanded sources (SSRN, NBER, Quantocracy, AQR, Robot Wealth), auto-port capability, author watch, weekly digest
**Round 3 goal:** Build a **knowledge graph** of every paper, repo, technique, author. LLM-augmented: when Nav asks "what does Skylit do about pin risk?" the system answers from the graph + cited sources.

### Tasks

**1. Neo4j knowledge graph schema `[A]`**
- Files: `infra/neo4j/docker-compose.neo4j.yml`, `backend/services/research/knowledge_graph.py`, `backend/tests/services/research/test_kg.py` (10+ tests)
- Nodes: Paper, Author, Concept, Implementation (repo), Technique, Hermes_Service
- Edges: AUTHORED, CITES, IMPLEMENTS, USES_TECHNIQUE, PORTED_TO, EXTENDS, CRITIQUES
- Populate from existing data:
  - 200+ arxiv papers in `data/external_research/`
  - 30+ cloned repos in `data/github-repos/cloned/`
  - 18 Hermes services in `backend/services/`
- **Reference:** Robinson, Webber (2015) *Graph Databases*
- **Acceptance:** Neo4j container runs locally; 5000+ nodes + 20k+ edges populated; queries like `MATCH (h:Hermes_Service)-[:IMPLEMENTS]->(t:Technique)<-[:USES_TECHNIQUE]-(p:Paper) RETURN h, p` return expected results

**2. LLM-augmented research Q&A `[B]`**
- Files: `backend/services/research/qa_engine.py`, `backend/routes/research.py` (extend), `backend/tests/services/research/test_qa.py` (12+ tests)
- Endpoint: POST /api/research/ask `{"question": "..."}`
- Pipeline: NL question → SPARQL/Cypher generation (via OpenRouter Claude) → KG query → retrieved nodes/papers → LLM synthesis with citations
- Every answer includes: 3+ paper citations + Hermes code pointer + confidence score
- **Reference:** Khattab et al. (2023) "DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines"
- **Acceptance:** 10 benchmark questions get correct + cited answers; latency <3s end-to-end

**3. Citation network analysis `[B]`**
- Files: `scripts/citation_analysis.py`, `reports/citation_network_<date>.md`
- Build the paper citation graph (use Semantic Scholar API for citations; rate-limit aware)
- Compute: PageRank, betweenness centrality, community detection (Louvain)
- Identify: most-cited papers in our scope, "bridge" papers connecting subfields, emerging clusters
- **Reference:** Newman (2010) *Networks: An Introduction*
- **Acceptance:** report ranks top 20 papers by influence; identifies 3+ emerging-cluster topics

**4. Auto-port v2 with semantic similarity `[A]`**
- Files: `scripts/auto_port_v2.py`, `backend/services/research/semantic_search.py`
- For each unported repo, compute embedding (sentence-transformers `all-MiniLM-L6-v2`) of README + key file docstrings
- Match against embeddings of Hermes service docstrings
- Top-3 closest Hermes services = candidate integration points
- Generate port proposal: which Hermes file to extend, what function to add, paper citations
- **Reference:** Reimers, Gurevych (2019) "Sentence-BERT"
- **Acceptance:** 5 ports proposed end-to-end with semantic-match scores; Nav manually approves merges

**5. Author influence tracker `[A]`**
- Files: `backend/services/research/author_influence.py`, `memory/author_influence_<date>.md`
- For each tracked author (Asness, LdP, Gatheral, etc.): pull h-index, recent paper count, last-published date
- Detect: "Gatheral published a new SVI extension yesterday" → auto-generate a digest with the paper's abstract + Hermes-relevance score
- **Acceptance:** weekly digest includes 5+ author updates with relevance ranking

### Skills
`research:arxiv,blogwatcher,duckduckgo-search,llm-wiki...`, `gbrain:archive-crawler,article-enric...,academic-verify`, `mlops:dspy` (DSPy for QA pipeline), `mcp:native-mcp` (expose research Q&A as MCP tool)

### Risks
- Neo4j adds infrastructure complexity — consider in-memory networkx if Neo4j is overkill
- Semantic Scholar rate-limits — cache aggressively
- LLM hallucination in Q&A — every claim must cite a real KG node

### Citations
- **Robinson, Webber (2015):** *Graph Databases*
- **Khattab et al. (2023):** "DSPy: Compiling Declarative Language Model Calls"
- **Newman (2010):** *Networks: An Introduction*
- **Reimers, Gurevych (2019):** "Sentence-BERT"

---

## <a id="agent-7"></a>Agent 7 — Round 3: Production deployment + live-trading enablement (card: O-SECURITY)

**Round 1 shipped:** SECURITY_AUDIT.md with severity-tagged findings
**Round 2 shipped:** JWT middleware, WS auth, secret rotation, pentest, Dockerfile hardening
**Round 3 goal:** **Production deployment to Azure** ($100 student credit). HTTPS + monitoring + SLA enforcement + live-trading switch (gated behind every safety check).

### Tasks

**1. Azure deployment via Terraform `[B]`**
- Files: `infra/terraform/main.tf`, `infra/terraform/variables.tf`, `infra/terraform/outputs.tf`
- Resources: App Service Plan (B1, ~$13/mo), App Service (FastAPI), Azure Container Registry, Azure Cosmos DB (Mongo API tier, free tier 400 RU/s)
- Networking: VNet + private endpoint for Cosmos (no public DB access)
- Secrets: Azure Key Vault, referenced via Managed Identity (no `.env` in container)
- **Reference:** Terraform Azure provider docs
- **Acceptance:** `terraform apply` provisions full stack in <10min; `curl https://hermes.<your>.azurewebsites.net/api/health` returns 200

**2. HTTPS + Caddy reverse proxy `[B]`**
- Files: `infra/caddy/Caddyfile`, `docker-compose.prod.yml`
- Auto-HTTPS via Let's Encrypt (Caddy handles this natively)
- HSTS preload, CSP `default-src 'self'`, X-Frame-Options DENY
- Static file serving (Dash + frontend assets) cached 1y with immutable
- API routes proxy to localhost:8000
- **Acceptance:** SSL Labs Server Test → A+ rating; securityheaders.com → A+

**3. SLO + error budget tracking `[B]`**
- Files: `backend/services/slo_tracker.py`, `grafana/dashboards/slo.json`, `prometheus/recording_rules/slo.yml`
- SLOs:
  - API availability: 99.9% (43.2 min downtime/month budget)
  - API latency: p99 < 200ms (per ARCHITECTURE_DEEP.md)
  - Schwab ingestion uptime: 99% during market hours
  - WebSocket message delivery: 99.99%
- Error budget burn rate: alert if monthly budget consumed in <50% of month
- **Reference:** Google SRE Book Ch. 4 "Service Level Objectives"
- **Acceptance:** 4 SLOs tracked in Grafana; burn-rate alerts fire correctly

**4. Live-trading switch (with circuit breakers) `[B]`**
- Files: `backend/services/live_trading_switch.py`, `backend/routes/admin.py` (extend), `backend/tests/services/test_live_trading_switch.py` (15+ tests)
- Switch states: OFF → PAPER_ONLY → LIVE_TINY (max $1000 notional) → LIVE_NORMAL → LIVE_FULL
- Each state transition requires: 2-factor confirm (Nav's phone + email) + audit-log entry
- Circuit breakers (any trips → demote one state level, no transitions for 24h):
  - Daily P&L drawdown > -2% of account → demote
  - >5 rejected fills in 1h → demote
  - Reconciliation discrepancy from Agent 1 → demote
  - Agent 10 SLA breach → demote
- **Reference:** SEC Rule 15c3-5 (Risk Management Controls for Brokers)
- **Acceptance:** can transition OFF→PAPER_ONLY via 2FA; can't skip states; every circuit breaker has a regression test

**5. Compliance audit trail `[A]`**
- Files: `backend/services/audit_trail.py`, `backend/tests/services/test_audit_trail.py` (10+ tests)
- For EVERY action (login, API call, order submitted, position changed, config edited): immutable log entry to Mongo `audit_trail` collection
- Fields: timestamp_utc, actor (user_id or "system" or "agent_<N>"), action_type, target, before_state, after_state, ip_address, user_agent, request_id
- Retention: 7 years (SEC requirement for broker-dealer records, though Hermes isn't a broker — still good practice)
- Hash-chain: each entry contains hash of previous → tamper-evident
- **Reference:** SEC Rule 17a-4 (records preservation); FINRA Rule 4511
- **Acceptance:** audit trail captures 100% of write actions; chain verification script runs in CI nightly

### Skills
`red-teaming:godmode` (verify production stack against new attack surface), `hermeshub:agent-hardening`, `swarmclaw:coding-agent`, `devops:react-craco...` (if any frontend deployment work)

### LIVE-TRADING GATE
Round 3 deliverables shipped + circuit-breaker tests passing + audit trail verified + Nav's 2FA confirmed → Nav MANUALLY toggles `OFF → PAPER_ONLY`. No auto-flip ever.

### Risks
- Azure free tier limits — monitor and configure budget alerts
- HTTPS misconfiguration → use Mozilla SSL config generator + test against SSL Labs
- Audit trail performance — write-batch + hash-chain async

### Citations
- **Google SRE Book** (Beyer et al., 2016): Ch. 4 "Service Level Objectives"
- **SEC Rule 15c3-5:** Risk Management Controls
- **SEC Rule 17a-4:** Records Preservation
- **NIST SP 800-53:** access control + audit logging baselines

---

## <a id="agent-8"></a>Agent 8 — Round 3: ML-driven kanban + capacity planning (card: O-KANBAN-ORCH, CONTINUOUS)

**Round 1 shipped:** kanban board, 10 cards, watcher loop, 23 tests
**Round 2 shipped:** inter-agent messaging, auto-spawn follow-ups, phone alerts, sprint planner, architect brief
**Round 3 goal:** **Predictive coordination.** Use historical agent throughput data to forecast completion times, identify bottleneck patterns, suggest capacity reallocation.

### Tasks

**1. Agent throughput model `[A]`**
- Files: `backend/services/kanban/throughput_model.py`, `backend/tests/services/kanban/test_throughput.py` (10+ tests)
- Train a simple Poisson regression on historical card-completion times (since kanban inception 2026-05-19)
- Features: agent_id, card_priority, lines_changed, files_touched, test_count_required, time_of_day, day_of_week
- Output: P(card_completes_within_T_hours | features)
- **Reference:** Hyndman, Athanasopoulos (2018) *Forecasting: Principles and Practice* §3 (regression-based forecasting)
- **Acceptance:** model trained on 100+ historical cards; cross-validated MAE < 1.5 hours

**2. Bottleneck detector `[B]`**
- Files: `backend/services/kanban/bottleneck.py`, `backend/tests/services/kanban/test_bottleneck.py` (8+ tests)
- Every 30 min: compute per-agent metrics (cards-in-flight, avg-time-per-card, blocker-rate, push-failure-rate)
- Identify bottlenecks: any agent with `cards_in_flight > 3 × median` OR `blocker_rate > 2 × median`
- Surface to ARCHITECT_BRIEF.md
- **Acceptance:** bottleneck detector correctly flags a deliberately overloaded agent in synthetic test

**3. Capacity rebalancing recommender `[B]`**
- Files: `backend/services/kanban/rebalancer.py`, `backend/tests/services/kanban/test_rebalancer.py` (8+ tests)
- When bottleneck detected: recommend which cards to reassign + to which agent
- Reassignment scoring: match card.required_skills to agent.skills (TF-IDF over historical commit messages); prefer agents with `cards_in_flight < median`
- Output: `kanban/REBALANCE_PROPOSAL.md` for Nav to chop
- **Acceptance:** 3 synthetic bottleneck scenarios each produce a sensible reassignment proposal

**4. Sprint retrospective generator `[B]`**
- Files: `scripts/generate_retro.py`, `kanban/RETRO_<date>.md`
- End of each sprint (weekly): aggregate completed cards + close-time stats + blockers encountered
- Generate retrospective with: what went well, what didn't, action items
- LLM-augmented via OpenRouter Claude (DSPy pipeline)
- **Acceptance:** retro identifies 3+ improvement areas per sprint; action items get auto-spawned as kanban cards

**5. Multi-repo coordination `[A]`**
- Files: `backend/services/kanban/multi_repo.py`, `kanban/multi_repo_status.md`
- Nav has multiple projects (floww, gflows, baby-billy-dvt). Some kanban cards span repos.
- Schema extension: cards can declare `affects_repos: [floww, gflows]`; watcher monitors all listed repos
- Cross-repo SWARM_STATUS.md aggregates state from all
- **Acceptance:** card affecting 2 repos correctly shows commits from both

### Skills
`devops:kanban-orchestrator`, `devops:kanban-worker`, `autonomous-ai-agents:kanban-codex-...`, `mlops:dspy` (retro generation), `hermeshub:agent-hardening`

### Risks
- Throughput model with only 100 data points — small sample; quantify uncertainty bands
- LLM-generated retros risk hallucination — every claim must cite a kanban card ID

### Citations
- **Hyndman, Athanasopoulos (2018):** *Forecasting: Principles and Practice* (open-source online textbook)
- **Brooks (1975):** *The Mythical Man-Month* — Brooks's Law on capacity rebalancing

---

## <a id="agent-9"></a>Agent 9 — Round 3: Federated memory + multi-modal embeddings (card: O-MEMORY-UNIFY)

**Round 1 shipped:** mem0 migration, Obsidian bridge
**Round 2 shipped:** daily consolidation, auto-tagging, ask-hermes CLI, pruning, cross-project memory
**Round 3 goal:** **Federated memory across Hermes instances** (laptop, work machine, future cloud deployment) + **multi-modal embeddings** (text, code, charts, audio notes).

### Tasks

**1. Federated mem0 sync `[A]`**
- Files: `scripts/mem0_federate.py`, `backend/services/memory/federation.py`, `backend/tests/services/memory/test_federation.py` (10+ tests)
- Multiple mem0 instances (Nav's laptop, work machine, future cloud) share state via a central message queue (Azure Service Bus or Redis pub-sub)
- Conflict resolution: last-writer-wins per entry; tombstones for deletes
- Replication lag SLA: <30s steady-state
- **Reference:** Bailis et al. (2013) "Eventual Consistency Today: Limitations, Extensions, and Beyond"
- **Acceptance:** 2-node simulation shows convergence after writes from both sides; 100 concurrent updates converge to consistent state

**2. Code embeddings `[B]`**
- Files: `scripts/embed_codebase.py`, `backend/services/memory/code_embeddings.py`
- For every `.py`, `.ts`, `.js` file: embed via CodeBERT or `microsoft/codebert-base`
- Store in vector DB (use mem0's built-in if it supports vectors; else Qdrant)
- `ask-hermes "where is GEX calculated?"` returns top-3 code pointers with snippets
- **Reference:** Feng et al. (2020) "CodeBERT: A Pre-Trained Model for Programming and Natural Languages"
- **Acceptance:** semantic code search returns expected results for 10 benchmark queries

**3. Chart screenshot embeddings `[B]`**
- Files: `scripts/embed_screenshots.py`, `backend/services/memory/chart_embeddings.py`
- For every screenshot Nav takes (via `/screenshots/`): embed via CLIP (`openai/clip-vit-base-patch32`)
- Use case: "show me the Heatseeker view from last Tuesday morning" → text query → CLIP retrieves matching screenshot
- **Reference:** Radford et al. (2021) "Learning Transferable Visual Models From Natural Language Supervision" (CLIP)
- **Acceptance:** 5 benchmark text queries return the correct screenshot

**4. Voice memo transcription + embedding `[A]`**
- Files: `scripts/transcribe_voice_memos.py`, `backend/services/memory/voice_embeddings.py`
- Whisper (local, `whisper-base`) transcribes Nav's voice memos from iOS Voice Memos app sync folder
- Transcript → mem0 with tag `source:voice_memo`
- **Reference:** Radford et al. (2022) "Robust Speech Recognition via Large-Scale Weak Supervision" (Whisper)
- **Acceptance:** sample voice memo transcribes correctly; searchable via ask-hermes

**5. Memory health monitor `[B]`**
- Files: `backend/services/memory/health.py`, `backend/tests/services/memory/test_health.py` (8+ tests)
- Metrics: entry count, query latency p99, embedding-cache hit rate, federation lag
- Endpoint: GET /api/admin/memory/health
- Wire into Agent 10's Grafana
- **Acceptance:** health endpoint < 50ms; all metrics surface in Grafana

### Skills
`mem0:mem0-cli,mem0-integrate,mem0-test-integration...`, `note-taking:obsidian`, `swarmclaw:coding-agent`, `mlops:dspy` (if any LLM pipeline)

### Risks
- Federation introduces consistency complexity — over-engineer at your peril; start with last-writer-wins
- Multi-modal embeddings: Whisper + CLIP + CodeBERT = ~3GB model footprint; consider remote inference

### Citations
- **Bailis et al. (2013):** "Eventual Consistency Today" — *CACM*
- **Feng et al. (2020):** "CodeBERT"
- **Radford et al. (2021):** "CLIP"
- **Radford et al. (2022):** "Whisper"

---

## <a id="agent-10"></a>Agent 10 — Round 3: ML-driven alerting + chaos forecasting (card: O-OBSERVABILITY)

**Round 1 shipped:** Prometheus + Grafana stack, oracle dashboards, alert rules
**Round 2 shipped:** Twilio phone alerting, meta-anomaly on metrics, SLA + cost dashboards, incident post-mortem template
**Round 3 goal:** **Predictive alerting.** Move from "alert when threshold breached" to "alert when we predict a threshold will be breached in N minutes." Plus chaos-event forecasting.

### Tasks

**1. Predictive alert engine `[A]`**
- Files: `backend/services/observability/predictive_alerts.py`, `./project_oracle/models/predictive_alert_v1.pt`, `backend/tests/services/observability/test_predictive_alerts.py` (10+ tests)
- For each critical metric (ingestion_rate, queue_depth, vpin_current, p99_latency): train a forecasting model (PatchTST or LSTM)
- Predict next 15 min; alert if any forecast point breaches threshold
- Two-tier alerts: WARNING (predicted breach in 5-15 min), CRITICAL (predicted breach <5 min OR already breached)
- **Reference:** Hochreiter, Schmidhuber (1997) "Long Short-Term Memory"; Nie et al. (2022) "PatchTST"
- **Acceptance:** 80%+ recall on actual breaches with ≤10% false-positive rate

**2. Anomaly forecasting for the trading system itself `[A]`**
- Files: `backend/services/observability/system_health_forecaster.py`, `backend/tests/services/observability/test_system_forecaster.py` (8+ tests)
- Predict: "system likely to enter degraded state within next hour" based on metric trends
- Inputs: 60-min history of ALL metrics (multivariate)
- Output: degradation_probability per service over next [5, 15, 30, 60] min
- **Reference:** Salinas et al. (2020) "DeepAR: Probabilistic forecasting with autoregressive recurrent networks"
- **Acceptance:** on a held-out 30-day window with known incidents, model predicts the incident ≥10 min in advance ≥70% of the time

**3. Incident similarity search `[B]`**
- Files: `backend/services/observability/incident_similarity.py`, `backend/routes/incidents.py` (extend)
- For each new incident: embed (Sentence-BERT) → search past incidents for similar
- Output: top-3 past incidents + their resolutions
- **Reference:** Reimers, Gurevych (2019) "Sentence-BERT"
- **Acceptance:** for 5 synthetic test incidents, similarity search returns the expected related historical incidents

**4. Cost forecasting + budget protection `[A]`**
- Files: `backend/services/observability/cost_forecaster.py`, `grafana/dashboards/cost_forecast.json`
- Forecast: end-of-month cost based on current burn rate (exponential smoothing)
- Auto-action: if forecasted cost > 110% of budget → throttle non-critical workloads (Agent 6 research loop slows from 60min to 240min cycle)
- **Reference:** Hyndman, Athanasopoulos (2018) §7 (exponential smoothing)
- **Acceptance:** $-dashboard shows forecasted EoM cost; auto-throttle triggers on synthetic over-budget scenario

**5. Self-healing runbook automation `[B]`**
- Files: `backend/services/observability/auto_remediation.py`, `docs/INCIDENTS/runbooks/*.yaml`
- YAML-defined runbooks for known incidents (e.g., "Mongo connection storm"):
  - Detection signature (which metrics, what pattern)
  - Automatic remediation steps (restart this, clear that cache, etc.)
  - Human confirmation gate before destructive actions
- **Reference:** Beyer et al. (2016) *Site Reliability Engineering* Ch. 12 "Effective Troubleshooting"
- **Acceptance:** 3 runbooks defined; one auto-remediates without human intervention in synthetic test

### Skills
`swarmclaw:coding-agent`, `mlops:evaluating-l...`, `mlops:dspy` (LLM-augmented runbook synthesis), `hermeshub:agent-hardening`

### Risks
- Predictive alerts that fire too early erode trust (cry-wolf) — calibrate against historical FPR
- Auto-remediation in production = scary — human-in-the-loop gate for any destructive action

### Citations
- **Hochreiter, Schmidhuber (1997):** "Long Short-Term Memory"
- **Nie et al. (2022):** "A Time Series is Worth 64 Words" (PatchTST)
- **Salinas et al. (2020):** "DeepAR: Probabilistic Forecasting with Autoregressive Recurrent Networks"
- **Beyer et al. (2016):** *Site Reliability Engineering*

---

## Deployment notes

### Window-A-heavy tasks (need Mongo + Schwab live; do these in evening/weekend windows)
- Agent 1: tasks 1, 4, 5
- Agent 2: tasks 1, 2, 5
- Agent 5: tasks 2, 4, 5
- Agent 6: tasks 1, 4, 5
- Agent 9: tasks 1, 4
- Agent 10: tasks 1, 2, 4

### Window-B-safe tasks (Nav at work; Mongo Atlas blocked is OK)
- Agent 1: tasks 2, 3
- Agent 2: tasks 3, 4
- Agent 3: all (UI work doesn't need live data; uses replay)
- Agent 4: all (tests + infra)
- Agent 5: tasks 1, 3
- Agent 6: tasks 2, 3
- Agent 7: all
- Agent 8: tasks 2, 3, 4
- Agent 9: tasks 2, 3, 5
- Agent 10: tasks 3, 5

### Sprint cadence (4 weeks expected for Round 3 across all agents)
- Week 1: agents 1, 2, 3 (highest-leverage user-facing features)
- Week 2: agents 4, 7 (production readiness gates)
- Week 3: agents 5, 6 (causal layer + KG)
- Week 4: agents 8, 9, 10 (coordination + memory + observability polish)

### Memory recovery path
1. `~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/MEMORY.md`
2. `/Users/nav/Documents/GitHub/floww/DISPATCH_PLAN_ORACLE.md` (Round 1)
3. `/Users/nav/Documents/GitHub/floww/DISPATCH_PLAN_ORACLE_ROUND2.md` (Round 2)
4. `/Users/nav/Documents/GitHub/floww/DISPATCH_PLAN_ORACLE_ROUND3.md` (Round 3 — this file)
5. `/Users/nav/Documents/GitHub/floww/kanban/SWARM_STATUS.md` (live state)
6. `ask-hermes "what's the status of <agent>?"`

### Live-trading gate
Until **Agent 7 Round 3 task 4 (live-trading switch with circuit breakers)** ships AND every circuit-breaker test passes AND Nav's 2FA confirms, the system remains in PAPER_ONLY mode. No live capital, regardless of Round 1/2/3 progress on other agents.
