# Hermes Round 3 — Paste-Ready Launch Prompts

Each prompt is a mini-plan with acceptance criteria. Same format as the Round 2 prompts that worked. **First agent only**: prepend Section 0 (folder consolidation) above your normal prompt.

---

## Section 0 — One-time folder consolidation (first agent only)

```
═══════════════════════════════════════════════════════════════
ONE-TIME PRE-FLIGHT: FOLDER CONSOLIDATION
═══════════════════════════════════════════════════════════════
You are the first Round 3 agent. Before your normal track, execute this consolidation.
After it ships, write memory/_consolidation_2026-05-20_complete.md and proceed to your
normal Round 3 prompt below.

CONTEXT:
  Nav has 4 directories scattered. Goal: one floww-owned territory.
  /Users/nav/Documents/GitHub/floww/                  ← THE project
  /Users/nav/gex-repos/                               ← 11 reference repos, 5 not yet in cloned/
  /Users/nav/gflows/                                  ← LEGACY (old project, not floww)
  /Applications/Claude\ everything/                   ← Nav's personal — DO NOT TOUCH

TASKS (commit + push EACH):

1. Move 5 new repos from /Users/nav/gex-repos/ into data/github-repos/cloned/
   For each repo: `git -C /Users/nav/gex-repos/<dir> remote get-url origin` to find owner,
   then `git mv /Users/nav/gex-repos/<dir> data/github-repos/cloned/<owner>_<dir>`.
   License-check via `head -5 LICENSE` — skip GPL/AGPL/LGPL (log to memory/_skipped_repos.md).
     - Dynamic-Derivatives-Portfolio-Hedging
     - option-strategy-pricer
     - SPX_Gamma_Exposure
     - gex-backtesting
     - Options_Portfolio
   Update data/github-repos/cloned-manifest.json after each move.
   Commit format: `chore(repos): consolidate <repo-name> into data/github-repos/cloned/`

2. Verify 6 already-cloned (different owner_ prefixes — idempotent, no moves):
   GEX-Dashboard → jay-nilesh-patel_spy-gex-dashboard
   Gamma-Vanna-Options-Exposure → Proshotv2_Gamma-Vanna-Options-Exposure
   Unusual-Options → wnnii_Unusual-Options
   EzOptions → EazyDuz1t_EzOptions
   gex-tracker → Matteo-Ferrara_gex-tracker
   floe → FullStackCraft_floe

3. Audit /Users/nav/gflows/ (legacy)
   Read README.md + .ai/ contents. Write findings to memory/_legacy_gflows_audit.md.
   Commit: `chore(audit): document /Users/nav/gflows/ as legacy reference`

4. Document /Applications/Claude\ everything/ as cross-project (never touched)
   Write memory/_cross_project_index.md noting top-level files (CLAUDE.md, FEIGENBAUM_PLAN.md,
   Baby_Billy_DVT_Trading_Guide.docx, etc.).
   Commit: `docs(memory): index /Applications/Claude\\ everything/ as cross-project workspace`

5. Update kanban/SWARM_STATUS.md with "Folder consolidation 2026-05-20" entry.
   Commit: `chore(kanban): folder consolidation 2026-05-20 status`

6. AFTER all 5 moves verified (ls each new path), `rm -rf /Users/nav/gex-repos/`.
   Commit: `chore(cleanup): remove empty /Users/nav/gex-repos after consolidation`

7. Final: memory/_consolidation_2026-05-20_complete.md with full diff.

CONSTRAINTS:
  Never delete source until each move verified. Truth audit GREEN throughout.
  Use git mv (not bare mv) so git tracks the rename.

When done, proceed to YOUR normal Round 3 prompt below.
═══════════════════════════════════════════════════════════════
```

---

## Standing preamble (paste at top of EVERY Round 3 prompt)

```
═══════════════════════════════════════════════════════════════
You are a Hermes Round-3 agent. Architect: Nav (PhD math + physics,
ex-Jane Street HFT). Project: /Users/nav/Documents/GitHub/floww
(Project Oracle — institutional options analytics, free Skylit clone).

VERIFY YOU ARE IN THE RIGHT REPO:
  git remote get-url origin
  → must be git@github.com:JattMoosewala5911/floww.git
  If not → STOP. Do not write a single line.

LOAD CONTEXT IN PARALLEL:
  - Skill: software-development:confluence-decoder (project conventions)
  - Skill: anthropic-skills:nav-context (Nav's shorthand)
  - Skill: anthropic-skills:using-superpowers (skill orchestration)
  - Skill: anthropic-skills:test-driven-development (TDD discipline)
  - Skill: anthropic-skills:subagent-driven-development (dispatch pattern)
  - Read: ~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/MEMORY.md
    then every file it links to (priority: project_oracle.md,
    project_master_plan.md, reference_herder_swarm.md, project_round3_review.md,
    DISPATCH_PLAN_ORACLE.md, DISPATCH_PLAN_ORACLE_ROUND2.md, DISPATCH_PLAN_ORACLE_ROUND3.md
    at repo root — anchor #agent-<N> is YOUR spec)

TIME-WINDOW STRATEGY (CRITICAL):
  Window A — NEXT 6-8 HOURS (Nav at home, market closed, infra healthy):
    • MongoDB Atlas: LIVE — write aggressively, backfill, persist everything
    • Schwab WebSocket: LIVE — pull live data into DuckDB now
    • Use this window for: data-hungry training, historical backfills,
      Mongo-dependent integration tests, HuggingFace downloads
  Window B — AFTER ~7am Nav's time (work Wi-Fi blocks Atlas):
    • Detect via ServerSelectionTimeoutError(timeout=5s)
    • Fall back to backend/.duckdb_cache/ + queue retries in
      backend/.mongo_retry_queue/<iso-ts>.json
    • Use this window for: pure-Python work (math validation, docs,
      tests with mocked DB, training on already-cached data)

  Plan your work so all Mongo-touching tasks land in Window A.

OPERATING LAWS (code-enforced — non-negotiable):
  • No synthetic data in production paths (raises DegenerateModelError)
  • bash qc/audit/truth_audit.sh GREEN before AND after each commit
  • TDD: failing test first, see it fail, implement, see it pass
  • Conventional commits with scope; Co-Authored-By: Claude Opus 4.7
    <noreply@anthropic.com>
  • NEVER --no-verify, --amend, or force-push main
  • Commit per deliverable (not one mega-commit per session)
  • Push after every commit (don't accumulate)
  • Mathematical claims cite the paper (Schulman PPO, Pearl Causality, etc.)

EXECUTION DISCIPLINE (skill: subagent-driven-development):
  For each numbered deliverable below, dispatch a swarmclaw:coding-agent
  worker with: the deliverable spec + the verification command. After
  the worker reports DONE, run two-stage review:
    1. Spec compliance: did it ship exactly what's specified?
    2. Code quality: tests cover it, no shortcuts, audit green
  Re-dispatch on issues until both reviews pass. Then move to next.

STOP CONDITIONS:
  • Truth audit red → remediation-only mode until green
  • All deliverables shipped → write
    memory/agent<N>_round3_complete.md and exit clean
  • 3 consecutive push failures → exit clean, write blocker to
    kanban/cards/<your-card-id>.md
  • Token/time budget exhausted → checkpoint state to your
    kanban card, exit clean (next worker resumes)

DO NOT STOP for:
  • "Should I continue?" — yes, always
  • "Is my approach right?" — your prompt + cited papers ARE the approach
  • "What does Nav want?" — Nav wrote the plan; execute it
═══════════════════════════════════════════════════════════════
```

---

## AGENT 1 — Schwab paper-trade execution engine

```
[paste standing preamble]

ROUND-3 IDENTITY: Hermes Agent 1, the execution specialist.
ROUND-2 SHIPPED: L2 book depth, replay engine, Schwab health endpoint,
token auto-refresh, cross-source GEX consistency check.

GOAL: Wire Schwab's paper-trading order endpoints to Hermes signals. Build
the order routing layer the Project Oracle directive's "execution doctrine"
needs (Tap Probability decay, deflection-zone-only entries, 3:1 R:R minimum).
This is the bridge from "Hermes detects toxic flow" to "Hermes acts on it" —
same shape as a tier-1 quant desk's execution stack.

TIME-WINDOW PLAN:
  Window A (now-7am): tasks 1, 4, 5 — need live Schwab sandbox + Mongo
  Window B (after 7am): tasks 2, 3 — pure Python, no live deps

TASKS:

1. Paper-trade order client (Window A — needs Schwab sandbox live)
   Files:
     - backend/services/order_router.py (new)
     - backend/tests/services/test_order_router.py (new, 15+ tests)
   Spec:
     - Wrap Schwab Trader API v1: POST /v1/accounts/{account}/orders (paper first)
     - Order types: LIMIT (default), STOP, STOP_LIMIT, MARKET (behind config flag — never default)
     - Idempotency: client_order_id = hash(intent.signal_id + intent.timestamp_us)
       Submit twice → same fill, never a duplicate
     - Position-state tracker: per-ticker positions in memory + persisted to Mongo
     - Endpoint: POST /api/order_router/submit (Pydantic-validated TradeIntent)
   Verification:
     - `pytest backend/tests/services/test_order_router.py -v` (15+ pass)
     - 100 simulated identical orders → 100 same fills, 0 duplicates
   Acceptance:
     - Idempotency confirmed; sandbox order completes; no MARKET-by-default
     - Reference: Almgren-Chriss (2001) "Optimal Execution of Portfolio Transactions"

2. Signal-to-intent translator (Window B)
   Files:
     - backend/services/signal_translator.py (new)
     - backend/tests/services/test_signal_translator.py (new, 12+ tests)
   Spec:
     - Input: anomaly_score, gex_state, trinity_score, current_positions, account_equity
     - Output: TradeIntent (or None) — fields: ticker, side, qty, order_type, limit_price,
              stop_loss, take_profit, signal_id, conviction
     - Conviction = anomaly_score × trinity_score × (1 - vpin_cdf). Above 0.7 → tradeable.
     - Risk gates (every gate passes before TradeIntent emits):
         • position_size ≤ max_position_pct × account_equity (default 1%)
         • adverse-news filter: skip if FlashAlpha social_sentiment z-score < -2
         • concentration: ≤ 3 open positions per ticker
         • liquidity gate: skip if Kyle's λ > λ_threshold (illiquid)
   Verification:
     - `pytest backend/tests/services/test_signal_translator.py -v`
   Acceptance:
     - Every conviction × position-size combo produces valid intent or NULL, never undefined
     - Reference: Kyle (1985) "Continuous Auctions and Insider Trading" — liquidity gate

3. Execution doctrine enforcer (Window B)
   Files:
     - backend/services/execution_doctrine.py (new)
     - backend/tests/services/test_execution_doctrine.py (new, 10+ tests)
   Spec (from Skylit's published rules in SKYLIT_FEATURES.md):
     - Tap Probability decay: Fresh → enter; Tested → only 3:1 R:R; Delivered → skip; Decaying → never
     - Deflection zones only: entry within 0.1% of King/Floor/Ceiling node
     - Never trade midpoint: refuse if spot is between nodes by >0.5%
     - 3:1 R:R minimum: (TP - entry) / (entry - SL) ≥ 3.0 for longs, mirrored for shorts
   Verification:
     - Each rule has a positive + negative test (fires when should, doesn't when shouldn't)
   Acceptance:
     - TradeIntent failing any rule rejected with documented rejection_reason

4. Fill-quality monitor (Window A — needs live fills to calibrate)
   Files:
     - backend/services/fill_monitor.py (new)
     - backend/tests/services/test_fill_monitor.py (new, 8+ tests)
   Spec:
     - After each fill: slippage_bps = (fill_price - limit_price) / limit_price × 10000
     - Track p50/p95/p99 slippage rolling 24h per ticker
     - Alert if p95 > 5 bps (paper-trade should be ~0; Schwab paper fills at NBBO)
     - Compare paper vs live (later): if live p95 - paper p95 > 3 bps, flag degradation
   Verification:
     - `pytest backend/tests/services/test_fill_monitor.py -v`
   Acceptance:
     - p95 slippage emits Prometheus metric floww_fill_slippage_bps_p95 to Agent 10's stack
     - Reference: Hasbrouck (2007) "Empirical Market Microstructure"

5. Position-reconciliation loop (Window A — needs live Schwab positions)
   Files:
     - backend/services/position_reconciler.py (new)
     - backend/tests/services/test_position_reconciler.py (new, 6+ tests)
   Spec:
     - Every 60s market-hours: pull positions from Schwab → diff against local tracker
     - Discrepancy → log + auto-reconcile to Schwab's view + emit reconciliation_event
     - Schwab is source of truth; local is cache
   Verification:
     - 24h reconciliation log shows zero divergences in healthy run
   Acceptance:
     - All 6 tests pass; reconciliation alarms wire to Agent 8's kanban
     - Reference: Lo (2002) "The Statistics of Sharpe Ratios" — tracking accuracy

SKILLS:
  - hermeshub:api-builder         (task 1, order_router endpoint)
  - swarmclaw:coding-agent        (all implementation)
  - hermeshub:agent-hardening     (task 1 idempotency + retries)
  - red-teaming:godmode           (task 1 stress: race 100 concurrent identical orders)
  - gbrain:academic-verify        (tasks 2, 4 — Almgren-Chriss, Hasbrouck)
  - software-development:debugging-hermes-tui-comman... (Schwab connection debug)

RISKS:
  - Schwab sandbox rate-limit aggressive → batch submission + exponential backoff
  - MARKET orders + thin liquidity → catastrophic slippage. Default to LIMIT, require flag for MARKET.
  - Time-zone bugs in NBBO comparison → UTC throughout, convert only at display
```

---

## AGENT 2 — Reinforcement-learning policy

```
[paste standing preamble]

ROUND-3 IDENTITY: Hermes Agent 2, ML lead.
ROUND-2 SHIPPED: PatchTST VPIN forecaster, Autoformer chain dynamics,
ensemble inference, regime-aware thresholds, backtest harness + trained model.

GOAL: Train a Reinforcement Learning policy (PPO) that consumes Hermes's
ensemble signals + position state + GEX regime and emits TradeIntents.
This is the bridge from "anomaly detector" to "autonomous trader" — same
shape as Renaissance / Citadel quant pods.

TIME-WINDOW PLAN:
  Window A (now-7am): tasks 1, 2, 5 — heavy compute + Mongo replay data
  Window B (after 7am): tasks 3, 4 — pure compute on cached models

TASKS:

1. Trading environment (Gym-compatible) (Window A — needs replay data)
   Files:
     - backend/services/rl/trading_env.py (new)
     - backend/tests/services/rl/test_trading_env.py (new, 15+ tests)
   Spec:
     - Observation space (continuous, 64-dim):
         GEX features (6): zscore_60d, ROC_5d, regime_pos, distance_to_flip_norm, wall_density, herfindahl
         VPIN ensemble (3): vpin_current, vpin_cdf, vpin_forecast_15min
         Trinity (1): score
         Position state (4): qty_held, unrealized_pnl_pct, time_in_trade_min, drawdown_pct
         Anomaly (2): anomaly_score, anomaly_regime_index
         Microstructure (5): kyle_lambda, amihud, qi_zscore, hawkes_branching, fragility_score
         Underlying (4): return_1m, return_5m, return_30m, atr_pct
         Calendar (6): minutes_to_close, dow, days_to_OPEX, days_to_FOMC, earnings_flag, vix
         History buffer (33): last 33 vpin_current values
     - Action space (discrete, 5): {-2: strong sell, -1: sell, 0: hold, +1: buy, +2: strong buy}
     - Reward: r_t = ΔPnL_t - λ × |Δposition_t| × kyle_lambda - μ × adverse_excursion_t
       λ=0.5, μ=1.0 (defaults; ablate in task 3)
     - Episode: one trading day; reset at market open
   Verification:
     - Random policy completes 100 episodes without crashes
     - `stable_baselines3.common.env_checker.check_env(env)` passes
   Acceptance:
     - Reward distribution non-degenerate (positive + negative both occur)
     - Reference: Sutton-Barto (2018) *RL: An Introduction* 2nd ed., §13

2. PPO trainer (Window A — heavy compute)
   Files:
     - scripts/train_rl_policy_ppo.py (new)
     - ./project_oracle/models/rl_policy_v1.pt (artifact)
     - qc/data/rl_policy_v1_manifest.json (provenance)
     - backend/tests/services/rl/test_ppo_training.py (new, 10+ tests)
   Spec:
     - Stable-Baselines3 PPO (fallback: cleanrl/ppo.py if SB3 too heavy)
     - Architecture: 2-layer MLP (256, 128) for policy + value heads
     - Hyperparameters: lr=3e-4, clip_range=0.2, ent_coef=0.01, vf_coef=0.5,
                       n_steps=2048, n_epochs=10, gae_lambda=0.95, gamma=0.99
     - Training data: replay through Agent 1's replay_engine.py over last 6 months
     - Save manifest: n_episodes, mean_reward, val_sharpe, training_period
   Verification:
     - `python scripts/train_rl_policy_ppo.py --epochs 10 --dry-run` exits 0
     - Loaded model produces action shape () for obs shape (64,)
   Acceptance:
     - Mean episode reward strictly increases over 1000 iterations
     - Sharpe of policy returns > 1.0 on held-out month
     - Reference: Schulman et al. (2017) "PPO Algorithms" arxiv:1707.06347

3. Reward-shaping ablation (Window B)
   Files:
     - reports/rl_reward_ablation_<date>.md (output)
   Spec:
     - Train 4 reward variants, 500 iterations each:
         A: ΔPnL only (baseline)
         B: ΔPnL - λ × transaction_cost
         C: ΔPnL - λ × tc - μ × drawdown (main)
         D: variant C + Sortino-shaped (downside variance penalty)
     - Report per variant: final Sharpe, max DD, win rate, avg trade duration
   Verification:
     - Report file rendered as markdown table
   Acceptance:
     - Ablation identifies optimal variant + justifies numerically
     - Reference: Sortino-Price (1994) "Performance Measurement in a Downside Risk Framework"

4. Policy distillation to faster inference (Window B)
   Files:
     - scripts/distill_policy.py (new)
     - ./project_oracle/models/rl_policy_distilled_v1.onnx (artifact)
   Spec:
     - Distill PPO teacher → 2-layer MLP (64 hidden) student via knowledge distillation
     - Convert to ONNX for sub-1ms inference at request handler
   Verification:
     - Student matches teacher's actions ≥98% on held-out trajectories
     - Inference < 1ms CPU
   Acceptance:
     - ONNX model deployed; replaces full PPO model in production routes
     - Reference: Hinton-Vinyals-Dean (2015) "Distilling the Knowledge in a Neural Network"

5. Online-learning continuous adaptation (Window A — needs daily replay data)
   Files:
     - backend/services/rl/online_adapter.py (new)
     - backend/tests/services/rl/test_online_adapter.py (new, 8+ tests)
   Spec:
     - After market close each day: replay day's trades + market data
     - Compute realized reward per state-action → small gradient step (lr=1e-5)
     - Save daily snapshots; rollback if 7-day Sharpe drops > 2σ below baseline
   Verification:
     - 30-day continuous-learning sim shows monotone-or-better Sharpe vs frozen baseline
   Acceptance:
     - All 8 tests pass; snapshot rollback verified on synthetic Sharpe degradation
     - Reference: Lillicrap et al. (2016) DDPG online update mechanics

SKILLS:
  - autonomous-ai-agents:codex (long training scripts — codex handles them well)
  - mlops:dspy                 (hyperparameter sweep prompting)
  - mlops:evaluating-l...      (PPO + ensemble eval harness)
  - gbrain:academic-verify     (PPO impl matches Schulman 2017 paper)
  - swarmclaw:coding-agent     (env + adapter implementation)

RISKS:
  - RL policies can blow up — wire kill-switch to Agent 1's position_reconciler BEFORE any live capital
  - Reward hacking: agent might learn to never trade → mean episode reward floor enforcement
  - Distribution shift training vs live → online adaptation handles small shifts; large shifts trigger retrain card
```

---

## AGENT 3 — Skylit visual parity + Atlas charting depth

```
[paste standing preamble]

ROUND-3 IDENTITY: Hermes Agent 3, UI lead.
ROUND-2 SHIPPED: Atlas tab (candlestick + overlays), Replay Mode wired,
Agent Hub stub + 3 archetypes, Nexus stub, polish (themes, shortcuts, mobile).

GOAL: Visual parity with Skylit's commercial product. Match their layout
density, color palette, interaction patterns. Add the charting depth a serious
trader expects — TradingView-grade candlesticks with Heatseeker overlays,
scrolling Flowseeker with 20 columns, mobile PWA.

TIME-WINDOW PLAN:
  Window A: task 3 — needs live flow data to render
  Window B: tasks 1, 2, 4, 5 — pure frontend, work with mocked data

TASKS:

1. TradingView lightweight-charts integration (Window B)
   Files:
     - backend/services/dash_ui.py (Atlas tab rewrite)
     - frontend/src/components/charts/ (if React micro-frontend)
   Spec:
     - Replace Plotly candlestick with `lightweight-charts` (sub-10ms render, Apache-2.0 license)
     - Overlay layers (each toggleable independently):
         (a) King Nodes lines
         (b) Zero Gamma horizontal level
         (c) Air Pockets shaded bands
         (d) Trinity markers
         (e) Anomaly event triangles
         (f) Dealer walls
     - Click any overlay → side panel shows underlying calc (which trades drove this node)
   Verification:
     - 4h candlestick window renders <500ms on average laptop
     - Toggle each overlay → re-renders in <100ms
   Acceptance:
     - Smooth at 60fps; no console errors

2. Heatseeker visual parity (Window B)
   Files:
     - backend/services/dash_ui.py (Heatseeker tab restyle)
   Spec:
     - Match Skylit palette: red → white → green for negative → zero → positive GEX
     - Node markers: concentric circles sized by |GEX|, mirror Skylit exactly
     - Hover tooltip 8-line summary: strike / net_gex / tap_count / state / tap_probability /
       signed_gex / total_oi / time_first_seen
     - Pulse animation when new King Node forms (<300ms transition)
   Verification:
     - Side-by-side screenshot diff vs Skylit (Nav manually) shows ≥90% similarity
   Acceptance:
     - Color palette exact; node sizing formula matches Skylit's published rubric
     - Reference: SKYLIT_FEATURES.md (feature parity ledger)

3. Flowseeker 20-column live table (Window A — needs live flow)
   Files:
     - backend/services/dash_ui.py (Flowseeker tab extension)
     - backend/routes/flowseeker.py (extend with order-flow joins)
   Spec:
     - Add 12 columns to existing 8 (current: timestamp, symbol, strike, expiry, side, type, size, price):
         NEW: implied_vol, theta_decay, vega_pnl, vanna_pnl, charm_pnl, hedge_pressure,
              fills_ahead, fills_behind, time_at_bid_ms, time_at_ask_ms, sentiment_score, vix_at_print
     - Color coding per Skylit rubric:
         Background: red if size > prev_day_volume; yellow if size > OI; gray otherwise
         Text: green for above-ask fills, red for below-bid fills
     - Sort + filter (any combo: side, type, size>X, premium>$Y, classification IN {sweep, block, regular})
     - Drilldown click → contract-specific modal with chain context
   Verification:
     - 100 prints/sec render without UI lag; filter latency <100ms
   Acceptance:
     - 20 columns visible; color rubric matches Skylit; drilldown modal works

4. Replay deep-dive — scenario library (Window B)
   Files:
     - backend/services/replay_scenarios.py (new)
     - backend/tests/services/test_replay_scenarios.py (new, 10+ tests)
     - backend/services/dash_ui.py (Replay tab extension)
   Spec:
     - Curated scenarios (JSON specs → Databento date ranges + key timestamps):
         "FOMC May 2026", "Aug 2024 vol blowup", "0DTE pin Friday",
         "Earnings squeeze AAPL", "Mar 2020 Covid", "GME Jan 2021 squeeze"
     - UI: dropdown loads scenario → Atlas chart auto-scrolls + plays at 10x → narrative overlay
   Verification:
     - All 6 scenarios load + play end-to-end; narrative timestamps align with documented events
   Acceptance:
     - Replay produces same overlays as live mode for the same wall-clock window

5. Touch-input mobile redesign (Window B)
   Files:
     - backend/services/dash_ui.py (mobile CSS)
     - frontend/src/styles/mobile.css
   Spec:
     - Breakpoints: <600px phone, 600-1024px tablet, >1024px desktop
     - Phone: single-tab + bottom nav (Heatseeker / Atlas / Toxicity); other tabs via hamburger
     - Touch: swipe between tabs, pinch-to-zoom on candle, long-press for node detail
     - PWA manifest + service worker for iOS/Android home-screen widget
   Verification:
     - `cd frontend && npx craco build` succeeds
     - Lighthouse Mobile Performance score ≥90; tap-target sizes ≥44px (Apple HIG)
   Acceptance:
     - PWA installs to iOS home screen; offline-capable cached static assets

SKILLS:
  - swarmclaw:coding-agent       (implementations)
  - creative:architecture-diagram (overlay layout + mobile grid)
  - devops:react-craco...        (frontend build hardening)
  - mcp:native-mcp               (optional: expose chart components as MCP)
  - hermeshub:api-builder        (drilldown endpoint extension)

RISKS:
  - TradingView lightweight-charts license = Apache-2.0 (commercial OK, no attribution
    required for SaaS) — confirm before adopting
  - Mobile PWA caching can cause stale data — versioned cache-busting required
  - Plotly candlestick is heavy — keep dataset under 5000 bars or it lags
```

---

## AGENT 4 — Property + fuzz + chaos engineering

```
[paste standing preamble]

ROUND-3 IDENTITY: Hermes Agent 4, test infra lead.
ROUND-2 SHIPPED: pytest-asyncio auto mode, CI coverage gates, property-based
math invariants (hypothesis), mutation testing on critical kernels, flaky-test detector.

GOAL: Adversarial robustness. Round 2's property tests covered known invariants;
Round 3 adds fuzzing (unknown unknowns) and chaos engineering (system-level failure
injection — Mongo down, Schwab disconnect, clock skew, memory pressure).

TIME-WINDOW PLAN: All Window B safe (no Mongo/Schwab dependencies)

TASKS:

1. Hypothesis-stateful tests for ingestion pipeline (Window B)
   Files:
     - backend/tests/stateful/test_ingestion_state_machine.py (new)
     - requirements.txt (add hypothesis>=6)
   Spec:
     - hypothesis.stateful.RuleBasedStateMachine modeling ingestion as state machine
     - Rules: tick_arrives, queue_flushes, mongo_writes, schwab_disconnects,
              schwab_reconnects, token_expires, token_refreshes
     - Invariants:
         (a) total_bytes_in == total_bytes_out + dropped (no losses)
         (b) queue_depth bounded by max_size
         (c) Mongo write order matches arrival order within a ticker
   Verification:
     - Overnight `--max-examples=10000` run finds zero invariant violations
   Acceptance:
     - Hypothesis stateful test integrated in nightly CI
     - Reference: Claessen-Hughes (2000) "QuickCheck"

2. Fuzz testing on route handlers (Window B)
   Files:
     - backend/tests/fuzz/test_route_fuzzing.py (new)
     - requirements.txt (add schemathesis>=3)
   Spec:
     - Use schemathesis to fuzz every /api/* endpoint against its OpenAPI schema
     - Inject random valid-shape payloads + edge cases: max int, negative floats,
       Unicode bombs, deeply nested JSON
     - Assert: server stays up; no 5xx on schema-valid input; sensible 4xx on schema-invalid
   Verification:
     - 24h fuzz run produces zero new 5xx errors; all responses match documented schemas
   Acceptance:
     - CI integrates 30-min fuzz pass on every PR
     - Reference: OWASP API Security Top 10 (2023)

3. Chaos engineering harness (Window B)
   Files:
     - backend/tests/chaos/chaos_runner.py (new)
     - backend/tests/chaos/scenarios/*.yaml (new)
   Spec:
     - YAML-defined scenarios:
         mongo_down_60s.yaml — kill Mongo for 60s; assert system stays up + queue+drain
         schwab_disconnect_5min.yaml — drop WS 5min; assert reconnect + no data loss
         clock_skew_2h.yaml — bump process clock +2h; assert TTL-sensitive things behave
         memory_pressure_3gb.yaml — spawn hog consuming 3GB; assert graceful degrade
         disk_full.yaml — fill /tmp; assert DuckDB cache eviction + alert
     - Each runs in CI nightly + locally via `make chaos`
   Verification:
     - All 5 scenarios pass; system never enters undefined state
   Acceptance:
     - `make chaos` runs all 5 locally; CI nightly green
     - Reference: Basiri et al. (2016) "Chaos Engineering" (Netflix paper)

4. Performance regression tests (Window B)
   Files:
     - backend/tests/perf/test_p99_latency.py (new)
     - reports/perf_<date>.md (output)
   Spec:
     - Hot-path benchmarks (within ARCHITECTURE_DEEP.md budgets):
         calc_gex_per_strike(1000 contracts): p99 < 5ms
         vpin_engine.update: p99 < 1ms
         hawkes_intensity(t, 500 events): p99 < 2ms
         SABR.hagan_lognormal_vol: p99 < 0.5ms
         /api/heatseeker/flip-zones e2e: p99 < 100ms
     - pytest-benchmark; CI fails on regression >20% vs baseline
   Verification:
     - Baselines locked; CI reports regression % per PR
   Acceptance:
     - All 5 benchmarks within budget on baseline run
     - Reference: Gil Tene "How NOT to Measure Latency" — HdrHistogram methodology

5. Snapshot tests for math correctness (Window B)
   Files:
     - backend/tests/snapshots/*.json (snapshots)
     - backend/tests/services/test_snapshot_math.py (new, 12+ tests)
   Spec:
     - For each math kernel, store canonical-input output as JSON snapshot
     - Test re-runs kernel + asserts bit-for-bit match
     - Use syrupy or pytest-snapshot
     - Catches algorithmic drift property + parity tests might miss
   Verification:
     - 12+ snapshots locked
   Acceptance:
     - Drift requires explicit `pytest --snapshot-update`

SKILLS:
  - swarmclaw:coding-agent       (implementations)
  - hermeshub:agent-hardening    (chaos recovery patterns)
  - red-teaming:godmode          (adversarial payloads for tasks 2, 3)
  - software-development:debugging-hermes-tui-comman... (failure-mode debug)
  - gbrain:academic-verify       (property invariants vs published proofs)

RISKS:
  - Hypothesis stateful + mutation tests slow → mark @pytest.mark.slow, nightly not per-PR
  - Chaos tests need root or container privileges → Docker isolation, gate on --chaos flag
```

---

## AGENT 5 — Pearl causal inference

```
[paste standing preamble]

ROUND-3 IDENTITY: Hermes Agent 5, math + docs lead.
ROUND-2 SHIPPED: reference-repo parity tests (5+ repos), math correctness dashboard,
ARCHITECTURE_DEEP.md, THEORY.md, 5 notebook tutorials.

GOAL: Move from descriptive ("VPIN is high") to causal ("a 1bp move in VPIN
CAUSES a 0.3bp move in spread, controlling for vol regime"). Implement
Pearl-style do-calculus on the dealer-hedging system. This is what separates
Renaissance from retail.

TIME-WINDOW PLAN:
  Window A (now-7am): tasks 2, 4, 5 — need Mongo historical data
  Window B (after 7am): tasks 1, 3 — pure code + DAG construction

TASKS:

1. Causal DAG of the dealer-hedging system (Window B)
   Files:
     - docs/causal/dag.md (Mermaid diagram)
     - backend/services/causal/dag.py (new)
     - backend/tests/services/causal/test_dag.py (new, 8+ tests)
   Spec:
     - Nodes (observable signals): spot, GEX, VPIN, QI, kyle_lambda,
       dealer_hedge_pressure, realized_vol, anomaly_score
     - Edges (causal arrows from theory):
         spot → GEX (mechanical), GEX → dealer_hedge_pressure (theoretical)
         dealer_hedge_pressure → spot (feedback)
         VPIN → spread → kyle_lambda
         realized_vol ↔ dealer_hedge_pressure (mutual)
     - Validate via dowhy.causal_graph.CausalGraph (add to requirements)
   Verification:
     - DAG passes acyclicity check; renders cleanly in mkdocs
   Acceptance:
     - Documented assumptions file at docs/causal/ASSUMPTIONS.md
     - Reference: Pearl (2009) *Causality*, 2nd ed., Cambridge UP

2. Average treatment effect (ATE) estimation (Window A — needs Mongo history)
   Files:
     - backend/services/causal/ate_estimator.py (new)
     - backend/tests/services/causal/test_ate.py (new, 10+ tests)
   Spec:
     - For each (treatment, outcome) pair, compute ATE via:
         - propensity score + IPTW (dowhy library)
         - OR EconML.dml.LinearDML for double machine learning
     - Confidence intervals via bootstrap (B=1000)
     - Treatments: "GEX flips negative", "VPIN crosses 0.7", "Trinity score > 80",
       "Anomaly threshold breached", "Hawkes branching > 0.8"
     - Outcomes: "realized_vol_30min", "spread_15min", "max_drawdown_60min"
   Verification:
     - reports/causal_ate_<date>.md with point estimates + 95% CIs for 5 treatments
   Acceptance:
     - Sample sizes adequate; CIs non-degenerate
     - Reference: Chernozhukov et al. (2018) "Double/Debiased ML" *Econometrics J.*

3. Counterfactual scenario engine (Window B)
   Files:
     - backend/services/causal/counterfactual.py (new)
     - backend/tests/services/causal/test_counterfactual.py (new, 8+ tests)
   Spec:
     - API: simulate_counterfactual(observation, intervention) → counterfactual_outcome
     - Example: "given the May 15 2025 observation, what would happen if VPIN had been 50% lower?"
     - Use DAG + learned structural equations (dowhy.gcm)
   Verification:
     - 3 named counterfactuals execute end-to-end; results match published economic intuition
   Acceptance:
     - Endpoint GET /api/causal/counterfactual returns deterministic outputs
     - Reference: Pearl (2018) *The Book of Why* §4 — counterfactuals

4. Granger-causality for Trinity Alignment (Window A — needs historical time series)
   Files:
     - backend/services/causal/granger.py (new)
     - backend/tests/services/causal/test_granger.py (new, 8+ tests)
     - docs/THEORY.md (extend Trinity section)
   Spec:
     - Does SPX's GEX Granger-cause SPY's GEX? QQQ's?
     - statsmodels.tsa.stattools.grangercausalitytests with lags 1, 5, 15 min
     - Multivariate VAR fit on all 3 series; ADF stationarity check first
   Verification:
     - Granger p-values + F-stats per pair logged
   Acceptance:
     - Trinity "leading-lagging" score added to /api/heatseeker/trinity-confluence
     - Reference: Granger (1969) *Econometrica*; Hamilton (1994) Ch.11

5. Causal-validated trade rationale (Window A — needs RL trade history from Agent 2)
   Files:
     - backend/services/causal/trade_rationale.py (new)
     - backend/routes/causal.py (new)
     - backend/tests/services/causal/test_trade_rationale.py (new, 8+ tests)
   Spec:
     - For each TradeIntent from Agent 2's RL policy: query causal model for explanation
     - Output: {intent_id, primary_cause: "negative GEX (z=-2.1) + VPIN spike (cdf=0.87)",
                supporting_evidence: [...],
                counterfactual: "if VPIN had been at median, intent would not have fired"}
     - Endpoint: GET /api/causal/explain/{intent_id}
   Verification:
     - Every TradeIntent gets rationale within 100ms
   Acceptance:
     - Rationale is human-readable + cites primary cause + supporting evidence + counterfactual

SKILLS:
  - gbrain:academic-verify        (Pearl, Imbens-Rubin, Chernozhukov citations)
  - gbrain:article-enric...       (citation enrichment for THEORY.md)
  - data-science:jupyter-live-kernel (ATE viz notebook)
  - creative:architecture-diagram (DAG mermaid)
  - mlops:dspy                    (LLM-shaped rationale generation in task 5)
  - mlops:evaluating-l...         (ATE CI estimation, model eval)
  - swarmclaw:coding-agent        (implementations)

RISKS:
  - Causal inference requires strong assumptions (no unobserved confounders) —
    document explicitly in docs/causal/ASSUMPTIONS.md
  - Granger causality ≠ Pearl causation — use Granger only as preliminary screen
```

---

## AGENT 6 — Knowledge graph + LLM-augmented research

```
[paste standing preamble]

ROUND-3 IDENTITY: Hermes Agent 6, perpetual research scout.
ROUND-2 SHIPPED: SSRN/NBER/Quantocracy/AQR/Robot-Wealth source expansion,
auto-port capability, author watch, weekly digest, HuggingFace search.

GOAL: Build a knowledge graph of every paper / repo / technique / author.
LLM-augmented Q&A: when Nav asks "what does Skylit do about pin risk?" the
system answers from the graph + cites sources. This is the difference between
"we have papers" and "we know what the papers say."

TIME-WINDOW PLAN:
  Window A: tasks 1, 5 — Neo4j ingestion + HF/SSRN crawls need network
  Window B: tasks 2, 3, 4 — pure compute on already-indexed data

  STOP CONDITION OVERRIDE: this agent is CONTINUOUS. Other agents complete
  Round 3 and exit; you keep running the loop indefinitely. Round 3
  deliverables (tasks 1-5) ship and you continue the existing research loop.

TASKS:

1. Neo4j knowledge graph schema (Window A)
   Files:
     - infra/neo4j/docker-compose.neo4j.yml (new)
     - backend/services/research/knowledge_graph.py (new)
     - backend/tests/services/research/test_kg.py (new, 10+ tests)
   Spec:
     - Nodes: Paper, Author, Concept, Implementation (repo), Technique, Hermes_Service
     - Edges: AUTHORED, CITES, IMPLEMENTS, USES_TECHNIQUE, PORTED_TO, EXTENDS, CRITIQUES
     - Populate from existing data:
         200+ arxiv papers in data/external_research/
         30+ cloned repos in data/github-repos/cloned/
         18 Hermes services in backend/services/
   Verification:
     - 5000+ nodes + 20k+ edges populated
     - Query `MATCH (h:Hermes_Service)-[:IMPLEMENTS]->(t:Technique)<-[:USES_TECHNIQUE]-(p:Paper) RETURN h, p` returns sensible joins
   Acceptance:
     - Neo4j compose brings up locally; KG persists across restarts
     - Reference: Robinson-Webber (2015) *Graph Databases*

2. LLM-augmented research Q&A (Window B)
   Files:
     - backend/services/research/qa_engine.py (new)
     - backend/routes/research.py (extend)
     - backend/tests/services/research/test_qa.py (new, 12+ tests)
   Spec:
     - Endpoint: POST /api/research/ask {"question": "..."}
     - Pipeline: NL question → Cypher generation (OpenRouter Claude) → KG query →
                retrieved nodes/papers → LLM synthesis with citations
     - Every answer: 3+ paper citations + Hermes code pointer + confidence score
   Verification:
     - 10 benchmark questions → correct + cited answers
     - Latency <3s end-to-end
   Acceptance:
     - Q&A integrated into ask-hermes CLI (Agent 9's deliverable)
     - Reference: Khattab et al. (2023) "DSPy"

3. Citation network analysis (Window B)
   Files:
     - scripts/citation_analysis.py (new)
     - reports/citation_network_<date>.md (output)
   Spec:
     - Build paper citation graph (Semantic Scholar API; rate-limit aware)
     - Compute: PageRank, betweenness centrality, community detection (Louvain)
     - Identify: most-cited papers in our scope, bridge papers, emerging clusters
   Verification:
     - Report ranks top 20 papers by influence; identifies 3+ emerging-cluster topics
   Acceptance:
     - Citation network exported to Neo4j as Paper-CITES-Paper edges
     - Reference: Newman (2010) *Networks: An Introduction*

4. Auto-port v2 with semantic similarity (Window B)
   Files:
     - scripts/auto_port_v2.py (new)
     - backend/services/research/semantic_search.py (new)
   Spec:
     - For each unported repo: embed (sentence-transformers all-MiniLM-L6-v2)
       README + key docstrings
     - Match against embeddings of Hermes service docstrings
     - Top-3 closest Hermes services = candidate integration points
     - Generate port proposal: which file to extend, what function to add, citations
   Verification:
     - 5 ports proposed end-to-end with semantic-match scores
   Acceptance:
     - Nav manually approves; merged ports get integration tests
     - Reference: Reimers-Gurevych (2019) "Sentence-BERT"

5. Author influence tracker (Window A — needs HF + arxiv API)
   Files:
     - backend/services/research/author_influence.py (new)
     - memory/author_influence_<date>.md (output)
   Spec:
     - Tracked authors: Asness, López de Prado, Gatheral, Carreira, Diehl, Doloc, Brown
     - Pull h-index, recent paper count, last-published date
     - Auto-detect new publications → digest with abstract + Hermes-relevance score
   Verification:
     - Weekly digest includes 5+ author updates with relevance ranking
   Acceptance:
     - Author alerts surface as kanban cards when new papers published

SKILLS:
  - research:arxiv               (the queries)
  - research:blogwatcher         (RSS for AQR, Robot Wealth, etc.)
  - research:duckduckgo-search   (fallback when targeted feeds fail)
  - research:llm-wiki...         (LLM-augmented Wikipedia)
  - hermeshub:arxiv-watcher      (continuous monitoring scaffolding)
  - gbrain:archive-crawler       (SSRN/NBER archive ingest)
  - gbrain:article-enric...      (citation + summary enrichment)
  - gbrain:academic-verify       (auto-port parity verification)
  - mlops:dspy                   (DSPy pipeline for QA)
  - mcp:native-mcp               (expose ask-research as MCP tool)
  - swarmclaw:coding-agent       (implementations + auto-port worker)

RISKS:
  - Neo4j adds infrastructure complexity — consider in-memory networkx if overkill
  - Semantic Scholar rate-limits — cache aggressively
  - LLM hallucination in Q&A — every claim must cite a real KG node

RATE LIMITS:
  arxiv: ≤30/h; GitHub: ≤60/h (use Pro auth); HF: ≤100/h; SSRN: ≤10/min (robots.txt)
```

---

## AGENT 7 — Production deployment + live-trading enablement

```
[paste standing preamble]

ROUND-3 IDENTITY: Hermes Agent 7, security + deployment lead.
ROUND-2 SHIPPED: JWT auth middleware, WebSocket auth, secret rotation script,
pentest from outside LAN, production deployment hardening (Dockerfile, .dockerignore, Caddy).

GOAL: Production deployment to Azure ($100 student credit). HTTPS + monitoring +
SLA enforcement + live-trading switch (gated behind every safety check). This is
what makes the difference between "Hermes works on Nav's laptop" and "Hermes runs
reliably in production."

TIME-WINDOW PLAN: All Window B safe (deployment + middleware work, no live deps)

TASKS:

1. Azure deployment via Terraform (Window B)
   Files:
     - infra/terraform/main.tf, variables.tf, outputs.tf (new)
   Spec:
     - Resources: App Service Plan (B1, ~$13/mo), App Service (FastAPI),
                  Azure Container Registry, Azure Cosmos DB (Mongo API, free 400 RU/s)
     - Networking: VNet + private endpoint for Cosmos (no public DB access)
     - Secrets: Azure Key Vault, referenced via Managed Identity (no .env in container)
   Verification:
     - `terraform apply` provisions full stack <10min
     - `curl https://hermes.<your>.azurewebsites.net/api/health` → 200
   Acceptance:
     - Production endpoint live; cost <$30/mo within Azure free tier + B1

2. HTTPS + Caddy reverse proxy (Window B)
   Files:
     - infra/caddy/Caddyfile (new)
     - docker-compose.prod.yml (new)
   Spec:
     - Auto-HTTPS via Let's Encrypt (Caddy native)
     - HSTS preload, CSP `default-src 'self'`, X-Frame-Options DENY
     - Static files cached 1y immutable; API routes proxy to localhost:8000
   Verification:
     - SSL Labs Server Test → A+
     - securityheaders.com → A+
   Acceptance:
     - HTTPS green padlock; HSTS preload eligible

3. SLO + error-budget tracking (Window B)
   Files:
     - backend/services/slo_tracker.py (new)
     - grafana/dashboards/slo.json (new)
     - prometheus/recording_rules/slo.yml (new)
   Spec:
     - SLOs:
         API availability 99.9% (43.2 min/mo budget)
         API p99 latency < 200ms (per ARCHITECTURE_DEEP.md)
         Schwab ingestion uptime 99% market-hours
         WebSocket message delivery 99.99%
     - Error-budget burn rate alert: if monthly budget consumed in <50% of month
   Verification:
     - 4 SLOs tracked in Grafana; burn-rate alerts fire correctly on synthetic test
   Acceptance:
     - Wires into Agent 10's alert routing
     - Reference: Beyer et al. (2016) *SRE* Ch.4 — SLOs

4. Live-trading switch with circuit breakers (Window B)
   Files:
     - backend/services/live_trading_switch.py (new)
     - backend/routes/admin.py (extend)
     - backend/tests/services/test_live_trading_switch.py (new, 15+ tests)
   Spec:
     - States: OFF → PAPER_ONLY → LIVE_TINY ($1k max) → LIVE_NORMAL → LIVE_FULL
     - Every transition requires: 2FA confirm (Nav phone + email) + audit-log entry
     - Circuit breakers (any trip → demote one state, no transitions for 24h):
         daily P&L drawdown > -2% → demote
         >5 rejected fills in 1h → demote
         reconciliation discrepancy from Agent 1 → demote
         Agent 10 SLA breach → demote
   Verification:
     - Can transition OFF→PAPER via 2FA; can't skip states; every breaker has regression test
   Acceptance:
     - Live-trading switch defaults to OFF; only Nav can flip; full audit trail
     - Reference: SEC Rule 15c3-5 (Risk Management Controls for Brokers)

5. Compliance audit trail (Window B)
   Files:
     - backend/services/audit_trail.py (new)
     - backend/tests/services/test_audit_trail.py (new, 10+ tests)
   Spec:
     - Every action (login, API call, order, position, config edit): immutable log to Mongo audit_trail
     - Fields: timestamp_utc, actor, action_type, target, before_state, after_state,
               ip_address, user_agent, request_id
     - Retention: 7 years (SEC standard for broker-dealer records — best practice even
       though Hermes isn't a broker)
     - Hash-chain: each entry contains hash of previous → tamper-evident
   Verification:
     - Audit captures 100% of write actions; chain verification script runs in CI nightly
   Acceptance:
     - Tamper test (modify a row directly in Mongo) → chain verification detects + alerts
     - References: SEC Rule 17a-4; FINRA Rule 4511; NIST SP 800-53

SKILLS:
  - red-teaming:godmode          (production security review)
  - hermeshub:agent-hardening    (production patterns: cert rotation, secret handling)
  - hermeshub:api-builder        (admin endpoints)
  - swarmclaw:coding-agent       (implementations)
  - devops:react-craco...        (if frontend deployed to Azure Static Web Apps)

LIVE-TRADING GATE — STRICT:
  Task 4 ships + Critical security findings count == 0 + audit trail end-to-end verified
  + Nav 2FA confirmation + Agent 1 reconciler 24h zero divergence → ONLY THEN can Nav
  MANUALLY flip OFF → PAPER_ONLY. No auto-flip ever.

RISKS:
  - Azure free tier limits — monitor + configure budget alerts
  - HTTPS misconfiguration → use Mozilla SSL config generator + test against SSL Labs
  - Audit trail write performance — batch + hash-chain async
```

---

## AGENT 8 — ML-driven kanban + capacity planning

```
[paste standing preamble]

ROUND-3 IDENTITY: Hermes Agent 8, swarm coordinator. Already running.
ROUND-2 SHIPPED: inter-agent messaging, auto-spawn follow-up cards, phone alerts,
sprint planner, architect handoff brief.

GOAL: Predictive coordination. Use historical agent throughput data to forecast
completion times, identify bottleneck patterns, suggest capacity reallocation.
The kanban becomes a force multiplier, not just a tracker.

TIME-WINDOW PLAN: continuous. 5-min watch loop runs in both windows.
  Window A optimal for: task 1 (historical kanban data ingestion)
  Window B safe for: tasks 2, 3, 4, 5

  STOP CONDITION OVERRIDE: this agent is CONTINUOUS. Tasks 1-5 ship and you
  continue the watch loop indefinitely. End of Round 3 = mark
  round3_deliverables: done in kanban/cards/O-KANBAN-ORCH.md, keep running.

TASKS:

1. Agent throughput model (Window A — needs historical kanban data)
   Files:
     - backend/services/kanban/throughput_model.py (new)
     - backend/tests/services/kanban/test_throughput.py (new, 10+ tests)
   Spec:
     - Poisson regression on historical card-completion times (since R1, 2026-05-19)
     - Features: agent_id, card_priority, lines_changed, files_touched,
                 test_count_required, time_of_day, day_of_week
     - Output: P(card_completes_within_T_hours | features)
   Verification:
     - Model trained on 100+ historical cards; cross-validated MAE < 1.5 hours
   Acceptance:
     - Throughput predictions surface in kanban/SWARM_STATUS.md
     - Reference: Hyndman-Athanasopoulos (2018) *Forecasting* §3

2. Bottleneck detector (Window B)
   Files:
     - backend/services/kanban/bottleneck.py (new)
     - backend/tests/services/kanban/test_bottleneck.py (new, 8+ tests)
   Spec:
     - Every 30 min: compute per-agent metrics — cards_in_flight, avg_time_per_card,
                     blocker_rate, push_failure_rate
     - Identify bottlenecks: agent with cards_in_flight > 3 × median OR blocker_rate > 2 × median
     - Surface to kanban/ARCHITECT_BRIEF.md
   Verification:
     - Detector flags synthetic-overloaded agent correctly
   Acceptance:
     - Bottleneck alerts wire to Agent 10's phone notifications

3. Capacity rebalancing recommender (Window B)
   Files:
     - backend/services/kanban/rebalancer.py (new)
     - backend/tests/services/kanban/test_rebalancer.py (new, 8+ tests)
   Spec:
     - When bottleneck detected: recommend which cards to reassign + to which agent
     - Reassignment scoring: match card.required_skills to agent.skills
       (TF-IDF over commit messages); prefer agents with cards_in_flight < median
     - Output: kanban/REBALANCE_PROPOSAL.md for Nav to approve
   Verification:
     - 3 synthetic bottleneck scenarios → sensible reassignment proposals
   Acceptance:
     - Proposals surface as kanban cards for Nav
     - Reference: Kuhn (1955) Hungarian algorithm for optimal assignment

4. Sprint retrospective generator (Window B)
   Files:
     - scripts/generate_retro.py (new)
     - kanban/RETRO_<date>.md (output)
   Spec:
     - End of each sprint (weekly): aggregate completed cards + close-time stats + blockers
     - Generate retro: what went well, what didn't, action items
     - LLM-augmented via OpenRouter Claude (DSPy pipeline)
   Verification:
     - Retro identifies 3+ improvement areas per sprint
   Acceptance:
     - Action items auto-spawn as kanban cards
     - Reference: Brooks (1975) *The Mythical Man-Month* — Brooks's Law on rebalancing

5. Multi-repo coordination (Window A — needs to monitor multiple repos)
   Files:
     - backend/services/kanban/multi_repo.py (new)
     - kanban/multi_repo_status.md (output)
   Spec:
     - Cards can declare `affects_repos: [floww, gflows, baby-billy-dvt]`
     - Watcher monitors all listed repos
     - Cross-repo SWARM_STATUS.md aggregates state from all
   Verification:
     - Card affecting 2 repos correctly shows commits from both
   Acceptance:
     - Multi-repo dashboard live in kanban/

SKILLS:
  - devops:kanban-orchestrator   (board state machine)
  - devops:kanban-worker         (workers pull from `ready`)
  - autonomous-ai-agents:kanban-codex-... (codex workers for code tasks)
  - hermeshub:agent-hardening    (continuous loop resilience)
  - mlops:dspy                   (retro generation, structured prompts)
  - mlops:evaluating-l...        (throughput model validation, outlier detection)
  - note-taking:obsidian         (sync SPRINT + ARCHITECT_BRIEF to Obsidian via Agent 9)
  - swarmclaw:coding-agent       (implementations)

RISKS:
  - Throughput model with only 100 data points — small sample; quantify uncertainty bands
  - LLM-generated retros risk hallucination — every claim must cite a kanban card ID
```

---

## AGENT 9 — Federated multi-modal memory

```
[paste standing preamble]

ROUND-3 IDENTITY: Hermes Agent 9, memory architect.
ROUND-2 SHIPPED: daily consolidation cron, auto-tagging on insert, ask-hermes CLI,
memory pruning policy, cross-project memory tagging.

GOAL: Federated memory across Hermes instances (laptop, work, future cloud) +
multi-modal embeddings (text, code, charts, audio notes). Memory becomes a single
addressable surface that survives any single-machine failure.

TIME-WINDOW PLAN:
  Window A (now-7am): tasks 1, 4 — network for embeddings + federation queue
  Window B (after 7am): tasks 2, 3, 5 — pure compute on cached embedding models

TASKS:

1. Federated mem0 sync (Window A — needs central message queue + network)
   Files:
     - scripts/mem0_federate.py (new)
     - backend/services/memory/federation.py (new)
     - backend/tests/services/memory/test_federation.py (new, 10+ tests)
   Spec:
     - Multiple mem0 instances (laptop, work, cloud) share state via central message queue
       (Azure Service Bus or Redis pub-sub)
     - Conflict resolution: last-writer-wins per entry; tombstones for deletes
     - Replication lag SLA: <30s steady-state
   Verification:
     - 2-node sim shows convergence after writes from both sides
     - 100 concurrent updates converge to consistent state
   Acceptance:
     - Federation handles 1000 writes/min without drift
     - Reference: Bailis et al. (2013) "Eventual Consistency Today" *CACM*

2. Code embeddings (Window B)
   Files:
     - scripts/embed_codebase.py (new)
     - backend/services/memory/code_embeddings.py (new)
   Spec:
     - For every .py / .ts / .js file: embed via CodeBERT (microsoft/codebert-base)
     - Store in vector DB (mem0's built-in if vector-capable; else Qdrant)
     - `ask-hermes "where is GEX calculated?"` → top-3 code pointers with snippets
   Verification:
     - Semantic code search returns expected results for 10 benchmark queries
   Acceptance:
     - Inference latency <500ms per query
     - Reference: Feng et al. (2020) "CodeBERT"

3. Chart screenshot embeddings (Window B)
   Files:
     - scripts/embed_screenshots.py (new)
     - backend/services/memory/chart_embeddings.py (new)
   Spec:
     - For every screenshot in /screenshots/: embed via CLIP (openai/clip-vit-base-patch32)
     - Use case: "show me the Heatseeker view from last Tuesday morning" → CLIP retrieves matching
   Verification:
     - 5 benchmark text queries return correct screenshots
   Acceptance:
     - Integrated into ask-hermes CLI
     - Reference: Radford et al. (2021) "CLIP"

4. Voice memo transcription + embedding (Window A — Whisper needs model download)
   Files:
     - scripts/transcribe_voice_memos.py (new)
     - backend/services/memory/voice_embeddings.py (new)
   Spec:
     - Whisper (local, whisper-base) transcribes iOS Voice Memos sync folder
     - Transcript → mem0 with tag `source:voice_memo`
   Verification:
     - Sample voice memo transcribes correctly; searchable via ask-hermes
   Acceptance:
     - Voice notes integrated into unified memory search
     - Reference: Radford et al. (2022) "Whisper"

5. Memory health monitor (Window B)
   Files:
     - backend/services/memory/health.py (new)
     - backend/tests/services/memory/test_health.py (new, 8+ tests)
   Spec:
     - Metrics: entry count, query latency p99, embedding-cache hit rate, federation lag
     - Endpoint: GET /api/admin/memory/health
     - Wire into Agent 10's Grafana
   Verification:
     - Health endpoint <50ms; all metrics in Grafana
   Acceptance:
     - Alert when query p99 > 500ms or federation lag > 60s

SKILLS:
  - mem0:mem0-cli, mem0:mem0-integrate, mem0:mem0-test-integration...
  - note-taking:obsidian
  - hermeshub:agent-hardening    (eventually-consistent replication patterns)
  - mlops:dspy                   (semantic search prompt structure)
  - mlops:evaluating-l...        (retrieval accuracy eval)
  - hermeshub:api-builder        (health endpoint)
  - swarmclaw:coding-agent       (implementations)

RISKS:
  - Federation consistency complexity — start with last-writer-wins, evolve later
  - Multi-modal embedding model footprint ~3GB total (CodeBERT + CLIP + Whisper) —
    consider remote inference if local resource-constrained
```

---

## AGENT 10 — Predictive alerting + chaos forecasting

```
[paste standing preamble]

ROUND-3 IDENTITY: Hermes Agent 10, observability lead.
ROUND-2 SHIPPED: Twilio phone alerting, meta-anomaly detection on metrics,
SLA + cost dashboards, incident post-mortem template.

GOAL: Predictive alerting. Move from "alert when threshold breached" to "alert
when we predict a threshold WILL be breached in N minutes." Plus chaos-event
forecasting. Nav gets called when something matters, AND ONLY when something matters.

TIME-WINDOW PLAN:
  Window A (now-7am): tasks 1, 2, 4 — training + Mongo metrics history
  Window B (after 7am): tasks 3, 5 — pure compute

TASKS:

1. Predictive alert engine (Window A — needs metrics history for training)
   Files:
     - backend/services/observability/predictive_alerts.py (new)
     - ./project_oracle/models/predictive_alert_v1.pt (artifact)
     - backend/tests/services/observability/test_predictive_alerts.py (new, 10+ tests)
   Spec:
     - For each critical metric (ingestion_rate, queue_depth, vpin_current, p99_latency):
       train forecasting model (PatchTST or LSTM)
     - Predict next 15 min; alert if any forecast point breaches threshold
     - Two-tier alerts:
         WARNING (predicted breach in 5-15 min)
         CRITICAL (predicted breach <5 min OR already breached)
   Verification:
     - 80%+ recall on actual breaches with ≤10% FP rate
   Acceptance:
     - Predictive alerts surface in Grafana before threshold breaches
     - References: Hochreiter-Schmidhuber (1997) LSTM; Nie et al. (2022) PatchTST

2. Anomaly forecasting for the trading system itself (Window A — training)
   Files:
     - backend/services/observability/system_health_forecaster.py (new)
     - backend/tests/services/observability/test_system_forecaster.py (new, 8+ tests)
   Spec:
     - Predict: "system likely to enter degraded state within next hour" from metric trends
     - Inputs: 60-min history of all metrics (multivariate)
     - Output: degradation_probability per service over next [5, 15, 30, 60] min
   Verification:
     - On held-out 30-day window with known incidents, model predicts ≥10min in advance ≥70% of time
   Acceptance:
     - Self-prediction integrated with Agent 8's predictive kanban
     - Reference: Salinas et al. (2020) "DeepAR: Probabilistic Forecasting"

3. Incident similarity search (Window B)
   Files:
     - backend/services/observability/incident_similarity.py (new)
     - backend/routes/incidents.py (extend)
   Spec:
     - Per new incident: embed (Sentence-BERT) → search past incidents for similar
     - Output: top-3 past incidents + their resolutions
   Verification:
     - 5 synthetic test incidents → expected related historical incidents retrieved
   Acceptance:
     - Similarity search wired into incident-creation flow
     - Reference: Reimers-Gurevych (2019) "Sentence-BERT"

4. Cost forecasting + budget protection (Window A — needs metrics history)
   Files:
     - backend/services/observability/cost_forecaster.py (new)
     - grafana/dashboards/cost_forecast.json (new)
   Spec:
     - Forecast end-of-month cost (exponential smoothing)
     - Auto-action: if forecasted > 110% budget → throttle non-critical (Agent 6 loop 60min → 240min)
   Verification:
     - $-dashboard shows forecasted EoM cost; auto-throttle triggers on synthetic over-budget
   Acceptance:
     - Burn-rate alerts at 80% / 95% budget
     - Reference: Hyndman-Athanasopoulos (2018) §7 — exponential smoothing

5. Self-healing runbook automation (Window B)
   Files:
     - backend/services/observability/auto_remediation.py (new)
     - docs/INCIDENTS/runbooks/*.yaml (3+ runbooks)
   Spec:
     - YAML-defined runbooks per known incident type:
         detection_signature (which metrics + pattern)
         automatic_remediation_steps
         human_confirmation_gate (before destructive actions)
   Verification:
     - 3 runbooks defined; one auto-remediates in synthetic test
   Acceptance:
     - Human-in-the-loop gate for destructive actions confirmed
     - Reference: Beyer et al. (2016) *SRE* Ch.12 — Effective Troubleshooting

SKILLS:
  - autonomous-ai-agents:codex   (training scripts for tasks 1, 2)
  - mlops:dspy                   (model hyperparameter sweep, runbook synthesis)
  - mlops:evaluating-l...        (forecast accuracy: CRPS, quantile loss)
  - gbrain:academic-verify       (LSTM impl vs Hochreiter 1997; PatchTST vs Nie 2022)
  - red-teaming:godmode          (test confirmation gate can't be bypassed in task 5)
  - hermeshub:agent-hardening    (safe automation patterns)
  - swarmclaw:coding-agent       (implementations)

RISKS:
  - Predictive alerts firing too early erode trust (cry-wolf) — calibrate FPR vs historical baseline
  - Auto-remediation in production = scary — human-in-the-loop gate for any destructive action
```

---

## Deployment order (paste this last)

```
Tonight's deploy sequence in Herder (each agent watches for its Round 2
completion file, so just paste them all and they'll self-schedule):

ONE-TIME PRE-FLIGHT — give Section 0 (folder consolidation) to whichever agent launches first

Window A — fire NOW (Mongo + Schwab live):
  Agent 1, Agent 2, Agent 5, Agent 6, Agent 9, Agent 10 ← need network

Window A or B — fire NOW (network optional):
  Agent 3, Agent 4, Agent 7, Agent 8

Each agent's Round 3 prompt auto-loads after they write
memory/agent<N>_round3_complete.md. Agent 8 (kanban) tracks the
transitions in kanban/SWARM_STATUS.md — that's Nav's single dashboard.

Sleep through this. ~30-40 agent-hours of work queued.
Truth audit gates every commit. Critical=0 gates live trading.

Memory recovery path if everything wipes:
  1. ~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/MEMORY.md
  2. /Users/nav/Documents/GitHub/floww/DISPATCH_PLAN_ORACLE.md (Round 1)
  3. /Users/nav/Documents/GitHub/floww/DISPATCH_PLAN_ORACLE_ROUND2.md (Round 2)
  4. /Users/nav/Documents/GitHub/floww/DISPATCH_PLAN_ORACLE_ROUND3.md (Round 3)
  5. /Users/nav/Documents/GitHub/floww/LAUNCH_PROMPTS.md (this file)
  6. /Users/nav/Documents/GitHub/floww/kanban/SWARM_STATUS.md (live state)
  7. `ask-hermes "agent<N> status"`
```

This is the same format as the Round 2 prompts. Time-windowed. Explicit verification commands + acceptance criteria per task. Each task routed through the right Herder skill. Math citations per task. Fire them all.
