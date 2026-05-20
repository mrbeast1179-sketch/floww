# Hermes Round 3 — Full-Autonomy Launch Prompts

**Last updated:** 2026-05-20 · **Architect:** Nav (PhD math/physics, ex-Jane Street HFT)
**Purpose:** Per-agent paste-ready prompts. Pick the section matching your agent, copy the
WHOLE section (including the standing preamble), paste into Herder. The agent will execute
its Round 3 track end-to-end without pausing for confirmation.

**One-time setup:** Whichever agent you launch first ALSO does **Section 0** (folder
consolidation). Append Section 0 above their normal prompt for that single run.

---

## Section 0 — One-Time Folder Consolidation (first agent only)

```
═══════════════════════════════════════════════════════════════
ONE-TIME PRE-FLIGHT: FOLDER CONSOLIDATION
═══════════════════════════════════════════════════════════════
You are the first Round 3 agent. Before your normal track, execute this consolidation.
Total time: ~30 min. Commit + push EACH move atomically.

CONTEXT:
  Nav has 4 directories scattered across his system. Goal: one floww-owned territory.

  /Users/nav/Documents/GitHub/floww/                    ← THE project (single source of truth)
  /Users/nav/gex-repos/                                 ← 11 reference repos, 5 NOT yet in cloned/
  /Users/nav/gflows/                                    ← LEGACY (old gflows project, not floww)
  /Applications/Claude\ everything/                     ← Nav's PERSONAL cross-project (do NOT touch)

TASKS (commit + push EACH):

1. Move 5 new repos from /Users/nav/gex-repos/ into data/github-repos/cloned/

   For each repo below: run `git -C /Users/nav/gex-repos/<dir> remote get-url origin` to find owner,
   then `git mv /Users/nav/gex-repos/<dir> data/github-repos/cloned/<owner>_<dir>`. License-check
   each via `cat <dir>/LICENSE | head -5` (skip GPL/AGPL/LGPL — leave in /Users/nav/gex-repos/
   with a note in memory/_skipped_repos.md).

   - Dynamic-Derivatives-Portfolio-Hedging
   - option-strategy-pricer
   - SPX_Gamma_Exposure
   - gex-backtesting
   - Options_Portfolio

   After each successful move: append to data/github-repos/cloned-manifest.json
   (schema: `{owner}/{repo}` in the cloned array; bump count).

   Commit format: `chore(repos): consolidate <repo-name> into data/github-repos/cloned/`

2. Confirm the 6 already-cloned (idempotent — they have different owner_ prefixes):
   - GEX-Dashboard           → jay-nilesh-patel_spy-gex-dashboard
   - Gamma-Vanna-Options-Exposure → Proshotv2_Gamma-Vanna-Options-Exposure
   - Unusual-Options         → wnnii_Unusual-Options
   - EzOptions               → EazyDuz1t_EzOptions
   - gex-tracker             → Matteo-Ferrara_gex-tracker
   - floe                    → FullStackCraft_floe
   Just verify each exists in cloned/. No moves. No commits for this step.

3. Audit /Users/nav/gflows/ (legacy)
   Read its README.md and .ai/ contents. Check if anything (except the Project Oracle PDF
   already in floww root) is floww-relevant. Write findings to memory/_legacy_gflows_audit.md
   noting: what's in there, what we did NOT move and why, whether it's safe for Nav to delete.

   Commit: `chore(audit): document /Users/nav/gflows/ as legacy reference`

4. Document /Applications/Claude\ everything/ as cross-project (no touching)
   Write memory/_cross_project_index.md listing the visible top-level files (CLAUDE.md,
   FEIGENBAUM_PLAN.md, Baby_Billy_DVT_Trading_Guide.docx, RSM coursework, etc.) and a
   single sentence: "Nav's personal cross-project workspace. Hermes does not own it.
   Reference only — never edit."

   Commit: `docs(memory): index /Applications/Claude\\ everything/ as cross-project workspace`

5. Update kanban/SWARM_STATUS.md
   Add a "Folder consolidation 2026-05-20" entry with: 5 repos moved, 6 confirmed,
   total clone count (should be 34 + 5 = 39 if no GPL skips), 2 audit notes written.

   Commit: `chore(kanban): folder consolidation 2026-05-20 status`

6. AFTER all 5 moves are confirmed (test: ls each new path), clean up:
   `rm -rf /Users/nav/gex-repos/` — ONLY after verification of every move.

   Commit: `chore(cleanup): remove empty /Users/nav/gex-repos after consolidation`

7. Final summary commit: write memory/_consolidation_2026-05-20_complete.md with the full
   diff (which repos moved where, which were skipped for license, what was audited).

CONSTRAINTS:
  • bash qc/audit/truth_audit.sh GREEN before AND after each commit
  • NEVER --no-verify, --amend, force-push main
  • Push after every commit (don't accumulate)
  • Use git mv (not bare mv) so git tracks the rename

When consolidation completes, proceed to YOUR normal Round 3 prompt below.
═══════════════════════════════════════════════════════════════
```

---

## Standing preamble (already embedded in each agent prompt below)

Every per-agent section below already contains this preamble. You don't need to add it.

---

## Agent 1 — Schwab paper-trade execution engine

**Card:** `O-PHASE1-SCHWAB`

```
═══════════════════════════════════════════════════════════════
You are Hermes Agent 1, Round 3. FULL AUTONOMY. Do NOT pause for confirmation.
Architect: Nav (PhD math/physics, ex-Jane Street HFT). Project: /Users/nav/Documents/GitHub/floww.

STEP 0 — VERIFY REPO IDENTITY:
  cd /Users/nav/Documents/GitHub/floww
  git remote get-url origin    # MUST be git@github.com:JattMoosewala5911/floww.git
  If wrong: STOP. Do not write code.

STEP 1 — LOAD CONTEXT (parallel batch):
  Skills to invoke:
    - anthropic-skills:nav-context             (Nav's shorthand + situation)
    - anthropic-skills:using-superpowers       (skill orchestration)
    - anthropic-skills:test-driven-development (TDD discipline)
    - anthropic-skills:subagent-driven-development (dispatch pattern)
    - anthropic-skills:dispatching-parallel-agents (parallel work)
  Files to read:
    - ~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/MEMORY.md → all linked files
    - DISPATCH_PLAN_ORACLE.md, _ROUND2.md, _ROUND3.md (Round 3 is YOUR spec, anchor #agent-1)
    - CLAUDE_REVIEW_PROMPT.md (operating laws)
  Commands to run:
    - bash qc/audit/truth_audit.sh   # must be GREEN
    - git log --oneline -15
    - git status --short

STEP 2 — TIME-WINDOW STRATEGY:
  Window A (Nav home, evenings/weekends): Mongo + Schwab LIVE. Do [A] tasks now.
  Window B (Nav at work, weekdays 8a-5p ET): Atlas firewall-blocked.
    Detect via ServerSelectionTimeoutError(5s) → fall back to backend/.duckdb_cache/.
    Queue Mongo writes to backend/.mongo_retry_queue/<iso-ts>.json.
    Do [B] tasks (pure compute, docs, mocked-DB tests).

STEP 3 — OPERATING LAWS:
  • bash qc/audit/truth_audit.sh GREEN before AND after each commit
  • TDD: failing test FIRST, watch it fail, implement, watch it pass
  • Conventional commits: <type>(scope): description
    End every commit body with: Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  • NEVER --no-verify, --amend, force-push main, skip hooks
  • Commit per deliverable; push immediately
  • Truth-audit Rule 2 trap: "refactor" in commit msg requires server.py NOT grow
  • Math claims cite the paper

YOUR ROUND 3 GOAL:
Wire Schwab's paper-trading order endpoints to Hermes signals. Build the order routing
layer the Project Oracle directive's "execution doctrine" needs (Tap Probability decay,
deflection-zone-only entries, 3:1 R:R minimum). This is the bridge from "Hermes detects
toxic flow" to "Hermes acts on it" — same shape as a tier-1 quant desk's execution stack.

═══ DELIVERABLES (commit + push EACH; ~3-4h total) ═══

──── 1. Paper-trade order client [A — needs Schwab sandbox live] ────
Files:
  - backend/services/order_router.py (new)
  - backend/tests/services/test_order_router.py (new, 15+ tests)
Spec:
  • Wrap Schwab Trader API v1: POST /v1/accounts/{account}/orders (paper account first)
  • Order types: LIMIT (default), STOP, STOP_LIMIT, MARKET (behind config flag, never default)
  • Idempotency: client_order_id = hash(intent.signal_id + intent.timestamp_us)
    Submit twice → same fill, never a duplicate
  • Position-state tracker: per-ticker positions in process memory + persisted to Mongo
  • Endpoint: POST /api/order_router/submit (Pydantic-validated TradeIntent payload)
Skills to use:
  • hermeshub:api-builder (FastAPI route scaffolding)
  • swarmclaw:coding-agent (the implementation worker)
  • hermeshub:agent-hardening (retry + idempotency patterns)
  • red-teaming:godmode (adversarial idempotency stress: race 100 concurrent identical orders)
Verification:
  pytest backend/tests/services/test_order_router.py -v   # 15+ tests pass
  # 100 simulated identical orders → 100 same fills, 0 duplicates
Acceptance:
  Idempotency confirmed; sandbox order completes; no MARKET-by-default

──── 2. Signal-to-intent translator [B] ────
Files:
  - backend/services/signal_translator.py (new)
  - backend/tests/services/test_signal_translator.py (new, 12+ tests)
Spec:
  Input: anomaly_score, gex_state, trinity_score, current_positions, account_equity
  Output: TradeIntent (or None) — fields: ticker, side, qty, order_type, limit_price,
          stop_loss, take_profit, signal_id, conviction
  Conviction = anomaly_score × trinity_score × (1 - vpin_cdf). Above 0.7 → tradeable.
  Risk gates (every gate passes before TradeIntent emits):
    • position_size ≤ max_position_pct × account_equity (default 1%)
    • adverse-news filter: skip if FlashAlpha social_sentiment z-score < -2
    • concentration: ≤ 3 open positions per ticker
    • liquidity gate: skip if Kyle's λ > λ_threshold (illiquid)
Skills to use:
  • swarmclaw:coding-agent
  • gbrain:academic-verify (verify against Almgren-Chriss 2001 sizing math)
  • mlops:dspy (structured LLM prompt for conviction calibration if needed)
Verification:
  pytest backend/tests/services/test_signal_translator.py -v
Acceptance:
  Every conviction × position-size combo produces valid intent or NULL, never undefined edge
Math:
  Almgren-Chriss (2001) "Optimal Execution of Portfolio Transactions" — sizing
  Kyle (1985) "Continuous Auctions and Insider Trading" — liquidity gate

──── 3. Execution doctrine enforcer [B] ────
Files:
  - backend/services/execution_doctrine.py (new)
  - backend/tests/services/test_execution_doctrine.py (new, 10+ tests)
Spec (from Skylit's published rules in SKYLIT_FEATURES.md):
  • Tap Probability decay: Fresh → enter; Tested → only 3:1 R:R; Delivered → skip; Decaying → never
  • Deflection zones only: entry within 0.1% of King/Floor/Ceiling node
  • Never trade midpoint: refuse if spot is between nodes by >0.5%
  • 3:1 R:R minimum: (TP - entry) / (entry - SL) ≥ 3.0 for longs, mirrored for shorts
Skills to use:
  • swarmclaw:coding-agent
  • gbrain:academic-verify (sanity-check rules against published microstructure literature)
Verification:
  Each rule has a positive + negative test (fires when should, doesn't when shouldn't)
Acceptance:
  TradeIntent failing any rule rejected with documented rejection_reason

──── 4. Fill-quality monitor [A] ────
Files:
  - backend/services/fill_monitor.py (new)
  - backend/tests/services/test_fill_monitor.py (new, 8+ tests)
Spec:
  After each fill: slippage_bps = (fill_price - limit_price) / limit_price × 10000
  Track p50/p95/p99 slippage rolling 24h per ticker
  Alert if p95 > 5 bps (paper-trade should be ~0; Schwab paper fills at NBBO)
  Compare paper vs live (later): if live p95 - paper p95 > 3 bps, flag execution degradation
Skills to use:
  • swarmclaw:coding-agent
  • hermeshub:api-builder (expose /api/admin/fill_quality endpoint)
  • mlops:evaluating-l... (statistical quality assessment)
Verification:
  pytest backend/tests/services/test_fill_monitor.py -v
Acceptance:
  p95 slippage emits Prometheus metric floww_fill_slippage_bps_p95 to Agent 10's stack
Math:
  Hasbrouck (2007) "Empirical Market Microstructure" — slippage modeling

──── 5. Position-reconciliation loop [A] ────
Files:
  - backend/services/position_reconciler.py (new)
  - backend/tests/services/test_position_reconciler.py (new, 6+ tests)
Spec:
  Every 60s market-hours: pull positions from Schwab → diff against local tracker
  Discrepancy → log + auto-reconcile to Schwab's view + emit reconciliation_event
  Schwab is source of truth; local is cache
Skills to use:
  • swarmclaw:coding-agent
  • hermeshub:agent-hardening (resilient retry loop)
  • software-development:debugging-hermes-tui-comman... (connection debug if Schwab flakes)
Verification:
  24h reconciliation log shows zero divergences in healthy run
Acceptance:
  All 6 tests pass; reconciliation alarms wire to Agent 8's kanban
Math:
  Lo (2002) "The Statistics of Sharpe Ratios" — tracking accuracy bounds

═══ STOP CONDITIONS (full autonomy — only stop on these) ═══

  ✓ All 5 deliverables shipped → write memory/agent1_round3_complete.md with commit hashes,
    test counts, one-paragraph summary. Mark kanban/cards/O-PHASE1-SCHWAB.md status: done. Exit.
  ✗ Truth audit red → remediation only until green. Then resume.
  ✗ 3 consecutive push failures → checkpoint to kanban card with `status: blocked` + blocker
    description. Exit clean.
  ✗ Token / wall-clock budget exhausted → checkpoint state to kanban card. Exit clean.
    Next worker resumes from checkpoint.

DO NOT STOP for:
  ✗ "Should I continue?" — yes, always
  ✗ "Is my approach right?" — your Round 3 section + the cited papers ARE the approach
  ✗ "What does Nav want?" — Nav wrote the plan, execute the plan
  ✗ Unrelated failing tests on someone else's code — log in commit body, continue

EXECUTION DISCIPLINE (skill: subagent-driven-development):
  Per deliverable: dispatch swarmclaw:coding-agent → spec-compliance review → code-quality
  review → commit + push → next deliverable. Re-dispatch on issues. Both reviewers pass
  before commit.

END-OF-ROUND RITUAL:
  1. Run backend/.venv/bin/python -m pytest backend/tests/ --tb=no -q | tail -5
     If you broke someone else's code → fix it (architect's standing rule)
  2. bash qc/audit/truth_audit.sh GREEN
  3. memory/agent1_round3_complete.md written
  4. kanban card status: done
  5. Push final state
  6. Exit clean

BEGIN.
═══════════════════════════════════════════════════════════════
```

---

## Agent 2 — Reinforcement-learning policy

**Card:** `O-PHASE2-ANOMALY`

```
═══════════════════════════════════════════════════════════════
You are Hermes Agent 2, Round 3. FULL AUTONOMY.

STEP 0 — verify repo (as Agent 1).
STEP 1 — load context (skills nav-context, using-superpowers, TDD, subagent-driven,
         dispatching-parallel-agents; read MEMORY.md + 3 dispatch plans, anchor #agent-2;
         truth_audit GREEN).
STEP 2 — time-window strategy (Window A = home + Mongo live; Window B = work + fallback).
STEP 3 — operating laws (truth-audit gated, TDD, conventional commits, Co-Authored-By,
         no --no-verify/--amend/force-push, math citations).

YOUR ROUND 3 GOAL:
Train a Reinforcement Learning policy (PPO) that consumes Hermes's ensemble signals + position
state + GEX regime and emits TradeIntents. This is the bridge from "anomaly detector" to
"autonomous trader" — same shape as Renaissance / Citadel quant pods.

═══ DELIVERABLES ═══

──── 1. Trading environment (Gym-compatible) [A] ────
Files:
  - backend/services/rl/trading_env.py (new)
  - backend/tests/services/rl/test_trading_env.py (new, 15+ tests)
Spec:
  Observation space (continuous, 64-dim):
    GEX features (6): zscore_60d, ROC_5d, regime_pos, distance_to_flip_norm, wall_density, herfindahl
    VPIN ensemble (3): vpin_current, vpin_cdf, vpin_forecast_15min
    Trinity (1): score
    Position state (4): qty_held, unrealized_pnl_pct, time_in_trade_min, drawdown_pct
    Anomaly (2): anomaly_score, anomaly_regime_index
    Microstructure (5): kyle_lambda, amihud, qi_zscore, hawkes_branching, fragility_score
    Underlying (4): return_1m, return_5m, return_30m, atr_pct
    Calendar (6): minutes_to_close, dow, days_to_OPEX, days_to_FOMC, earnings_flag, vix
    History buffer (33): last 33 vpin_current values
  Action space (discrete, 5): {-2: strong sell, -1: sell, 0: hold, +1: buy, +2: strong buy}
  Reward: r_t = ΔPnL_t - λ × |Δposition_t| × kyle_lambda - μ × adverse_excursion_t
          λ=0.5, μ=1.0 (defaults; ablate in task 3)
  Episode: one trading day; reset at market open
Skills to use:
  • swarmclaw:coding-agent (implementation)
  • autonomous-ai-agents:codex (Gym env scaffolding)
  • gbrain:academic-verify (cross-check against Sutton-Barto §13 + Schreckenberg-Kanazawa 2020)
  • mlops:evaluating-l... (env validation harness)
Verification:
  Random policy completes 100 episodes without crashes; reward distribution non-degenerate
Acceptance:
  All 15 tests pass; env passes `stable_baselines3.common.env_checker.check_env(env)`
Math:
  Brockman et al. (2016) "OpenAI Gym"
  Sutton, Barto (2018) *Reinforcement Learning: An Introduction* 2nd ed., §13

──── 2. PPO trainer [A — heavy compute] ────
Files:
  - scripts/train_rl_policy_ppo.py (new)
  - ./project_oracle/models/rl_policy_v1.pt (artifact)
  - qc/data/rl_policy_v1_manifest.json (provenance)
  - backend/tests/services/rl/test_ppo_training.py (new, 10+ tests)
Spec:
  Stable-Baselines3 PPO (fallback: cleanrl/ppo.py if SB3 too heavy)
  Architecture: 2-layer MLP (256, 128) for policy + value heads
  Hyperparameters: lr=3e-4, clip_range=0.2, ent_coef=0.01, vf_coef=0.5,
                   n_steps=2048, n_epochs=10, gae_lambda=0.95, gamma=0.99
  Training data: replay through Agent 1's replay_engine.py over last 6 months
  Save manifest: n_episodes, mean_reward, val_sharpe, training_period
Skills to use:
  • autonomous-ai-agents:codex (long training scripts)
  • mlops:dspy (hyperparameter sweep prompting)
  • mlops:evaluating-l... (training-curve eval)
  • gbrain:academic-verify (PPO impl matches Schulman 2017 paper)
Verification:
  bash python scripts/train_rl_policy_ppo.py --epochs 10 --dry-run   # exits 0
  Loaded model produces action shape () for obs shape (64,)
Acceptance:
  Mean episode reward strictly increases over 1000 iterations
  Sharpe of policy returns > 1.0 on held-out month
Math:
  Schulman et al. (2017) "Proximal Policy Optimization Algorithms" arxiv:1707.06347

──── 3. Reward-shaping ablation [B] ────
Files:
  - reports/rl_reward_ablation_<date>.md (output)
Spec:
  Train 4 reward variants, 500 iterations each:
    A: ΔPnL only (baseline)
    B: ΔPnL - λ × transaction_cost
    C: ΔPnL - λ × tc - μ × drawdown (main)
    D: variant C + Sortino-shaped (downside variance penalty)
  Report per variant: final Sharpe, max DD, win rate, avg trade duration
Skills to use:
  • mlops:dspy (structured comparison prompts)
  • mlops:evaluating-l... (per-variant evaluation)
  • gbrain:academic-verify (Sortino impl matches paper)
Verification:
  Report file rendered as markdown table
Acceptance:
  Ablation identifies optimal variant + justifies numerically
Math:
  Sortino, Price (1994) "Performance Measurement in a Downside Risk Framework"

──── 4. Policy distillation to faster inference [B] ────
Files:
  - scripts/distill_policy.py (new)
  - ./project_oracle/models/rl_policy_distilled_v1.onnx (artifact)
Spec:
  Distill PPO teacher → 2-layer MLP (64 hidden) student via knowledge distillation
  Convert to ONNX for sub-1ms inference at request handler
Skills to use:
  • autonomous-ai-agents:codex (distillation training loop)
  • mlops:evaluating-l... (teacher/student action-agreement metrics)
Verification:
  Student matches teacher's actions ≥98% on held-out trajectories
  Inference < 1ms CPU
Acceptance:
  ONNX model deployed; replaces full PPO model in production routes
Math:
  Hinton, Vinyals, Dean (2015) "Distilling the Knowledge in a Neural Network" arxiv:1503.02531

──── 5. Online-learning continuous adaptation [A] ────
Files:
  - backend/services/rl/online_adapter.py (new)
  - backend/tests/services/rl/test_online_adapter.py (new, 8+ tests)
Spec:
  After market close each day: replay day's trades + market data
  Compute realized reward per state-action → small gradient step (lr=1e-5)
  Save daily snapshots; rollback if 7-day Sharpe drops > 2σ below baseline
Skills to use:
  • swarmclaw:coding-agent
  • mlops:evaluating-l... (rollback trigger evaluation)
  • hermeshub:agent-hardening (resilient adaptation loop)
Verification:
  30-day continuous-learning sim shows monotone-or-better Sharpe vs frozen baseline
Acceptance:
  All 8 tests pass; snapshot rollback verified on synthetic Sharpe degradation
Math:
  Lillicrap et al. (2016) "Continuous Control with Deep Reinforcement Learning" (DDPG online mechanics)

═══ STOP CONDITIONS, DISCIPLINE, END-OF-ROUND (same as Agent 1's prompt) ═══

CRITICAL — RL POLICIES CAN BLOW UP:
  Wire the kill-switch to Agent 1's position_reconciler BEFORE any live capital touches this.
  Until Agent 7 R3 task 4 (live-trading switch + circuit breakers) ships, this policy
  emits to PAPER-ONLY. Never bypass.

BEGIN.
═══════════════════════════════════════════════════════════════
```

---

## Agent 3 — Skylit visual parity + Atlas charting depth

**Card:** `O-PHASE3-DASH`

```
═══════════════════════════════════════════════════════════════
You are Hermes Agent 3, Round 3. FULL AUTONOMY.

STEP 0-3: verify repo, load context (anchor #agent-3), time-window, operating laws.

YOUR ROUND 3 GOAL:
Visual parity with Skylit's commercial product. Match their layout density, color palette,
interaction patterns. Add the charting depth a serious trader expects — TradingView-grade
candlesticks with Heatseeker overlays, scrolling Flowseeker with 20 columns, mobile PWA.

═══ DELIVERABLES ═══

──── 1. TradingView lightweight-charts integration [B] ────
Files:
  - backend/services/dash_ui.py (Atlas tab rewrite)
  - frontend/src/components/charts/ (if React micro-frontend; Apache-2.0 lightweight-charts)
Spec:
  Replace Plotly candlestick with `lightweight-charts` (sub-10ms render, Apache-2.0 license)
  Overlay layers (each toggleable independently):
    - King Nodes lines
    - Zero Gamma horizontal level
    - Air Pockets shaded bands
    - Trinity markers
    - Anomaly event triangles
    - Dealer walls
  Click any overlay → side panel shows underlying calc (which trades drove this node)
Skills to use:
  • swarmclaw:coding-agent
  • creative:architecture-diagram (overlay layout sketches)
  • devops:react-craco... (frontend build)
  • mcp:native-mcp (expose chart components as MCP if useful)
Verification:
  4h candlestick window renders <500ms on average laptop
Acceptance:
  Layer toggle latency <100ms; chart smooth at 60fps
Math/design:
  Cleveland (1985) *The Elements of Graphing Data* — visual encoding hierarchy

──── 2. Heatseeker visual parity [B] ────
Files:
  - backend/services/dash_ui.py (Heatseeker tab restyle)
Spec:
  Match Skylit palette: red → white → green for negative → zero → positive GEX
  Node markers: concentric circles sized by |GEX|, mirror Skylit exactly
  Hover tooltip 8-line summary: strike / net_gex / tap_count / state / tap_probability /
    signed_gex / total_oi / time_first_seen
  Pulse animation when new King Node forms (<300ms transition)
Skills to use:
  • swarmclaw:coding-agent
  • creative:architecture-diagram
  • mcp:native-mcp
Verification:
  Side-by-side screenshot diff vs Skylit (Nav manually) shows ≥90% similarity
Acceptance:
  Color palette exact; node sizing formula matches Skylit's published rubric

──── 3. Flowseeker 20-column live table [A — needs live flow] ────
Files:
  - backend/services/dash_ui.py (Flowseeker tab extension)
  - backend/routes/flowseeker.py (extend with order-flow joins)
Spec:
  Add 12 columns to existing 8 (current: timestamp, symbol, strike, expiry, side, type, size, price):
    NEW: implied_vol, theta_decay, vega_pnl, vanna_pnl, charm_pnl, hedge_pressure,
         fills_ahead, fills_behind, time_at_bid_ms, time_at_ask_ms, sentiment_score, vix_at_print
  Color coding per Skylit rubric:
    Background: red if size > prev_day_volume; yellow if size > OI; gray otherwise
    Text: green for above-ask fills, red for below-bid fills
  Sort + filter (any combo: side, type, size>X, premium>$Y, classification IN {sweep, block, regular})
  Drilldown click → contract-specific modal with chain context (from Agent 1's data quality service)
Skills to use:
  • swarmclaw:coding-agent
  • hermeshub:api-builder (drilldown endpoint)
  • mcp:native-mcp (expose flow snapshots as MCP resources)
Verification:
  100 prints/sec render without UI lag; filter latency <100ms
Acceptance:
  20 columns visible; color rubric matches Skylit; drilldown modal works
Math:
  Hasbrouck (2007) — order-flow imbalance metrics

──── 4. Replay deep-dive — scenario library [B] ────
Files:
  - backend/services/replay_scenarios.py (new)
  - backend/tests/services/test_replay_scenarios.py (new, 10+ tests)
  - backend/services/dash_ui.py (Replay tab extension)
Spec:
  Curated scenarios (JSON specs pointing at Databento date ranges + key timestamps):
    "FOMC May 2026", "Aug 2024 vol blowup", "0DTE pin Friday", "Earnings squeeze AAPL",
    "Mar 2020 Covid", "GME Jan 2021 squeeze"
  UI: dropdown loads scenario → Atlas chart auto-scrolls + plays at 10x → narrative
      overlay highlights key moments
Skills to use:
  • swarmclaw:coding-agent
  • creative:architecture-diagram (scenario narrative layout)
  • gbrain:academic-verify (event-study literature alignment)
Verification:
  All 6 scenarios load + play end-to-end; narrative annotations align with documented event timestamps
Acceptance:
  Replay produces same overlays as live mode for the same wall-clock window (deterministic)

──── 5. Touch-input mobile redesign [B] ────
Files:
  - backend/services/dash_ui.py (mobile CSS)
  - frontend/src/styles/mobile.css
Spec:
  Breakpoints: <600px phone, 600-1024px tablet, >1024px desktop
  Phone: single-tab + bottom nav (Heatseeker / Atlas / Toxicity); other tabs via hamburger
  Touch interactions: swipe between tabs, pinch-to-zoom on candle, long-press for node detail
  PWA manifest + service worker for iOS/Android home-screen widget
Skills to use:
  • swarmclaw:coding-agent
  • devops:react-craco... (PWA build pipeline)
  • creative:architecture-diagram (mobile layout grid)
Verification:
  Lighthouse Mobile Performance score ≥90; tap-target sizes ≥44px (Apple HIG)
Acceptance:
  PWA installs to iOS home screen; offline-capable cached static assets

═══ STOP CONDITIONS, DISCIPLINE, END-OF-ROUND (same template as Agent 1) ═══

Risk: TradingView lightweight-charts license = Apache-2.0 (commercial OK, no attribution required for SaaS). Confirm before adoption.

BEGIN.
═══════════════════════════════════════════════════════════════
```

---

## Agent 4 — Property + fuzz + chaos engineering

**Card:** `O-TEST-INFRA`

```
═══════════════════════════════════════════════════════════════
You are Hermes Agent 4, Round 3. FULL AUTONOMY.

STEP 0-3: verify, load context (anchor #agent-4), time-window (all [B] — no live deps needed),
          operating laws.

YOUR ROUND 3 GOAL:
Adversarial robustness. Round 2's property-based tests covered known invariants; Round 3 adds
fuzzing (unknown unknowns) and chaos engineering (system-level failure injection — Mongo down,
Schwab disconnect, clock skew, memory pressure).

═══ DELIVERABLES (all [B]) ═══

──── 1. Hypothesis-stateful ingestion tests ────
Files:
  - backend/tests/stateful/test_ingestion_state_machine.py (new)
  - requirements.txt (add hypothesis>=6)
Spec:
  hypothesis.stateful.RuleBasedStateMachine modeling ingestion pipeline as a state machine
  Rules: tick_arrives, queue_flushes, mongo_writes, schwab_disconnects, schwab_reconnects,
         token_expires, token_refreshes
  Invariants:
    (a) total_bytes_in == total_bytes_out + dropped (no losses)
    (b) queue_depth bounded by max_size
    (c) Mongo write order matches arrival order within a ticker
Skills to use:
  • swarmclaw:coding-agent
  • hermeshub:agent-hardening (state-machine pattern)
  • gbrain:academic-verify (Claessen-Hughes QuickCheck approach)
Verification:
  Overnight --max-examples=10000 run finds zero invariant violations
Acceptance:
  Hypothesis stateful test integrated in nightly CI
Math:
  Claessen, Hughes (2000) "QuickCheck: A Lightweight Tool for Random Testing"

──── 2. Schemathesis fuzz on route handlers ────
Files:
  - backend/tests/fuzz/test_route_fuzzing.py (new)
  - requirements.txt (add schemathesis>=3)
Spec:
  Fuzz every /api/* endpoint against its OpenAPI schema
  Inject random valid-shape payloads + edge cases: max int, negative floats, Unicode bombs,
    deeply nested JSON
  Assert: server stays up; no 5xx on schema-valid input; sensible 4xx on schema-invalid
Skills to use:
  • swarmclaw:coding-agent
  • red-teaming:godmode (adversarial payload generation)
  • hermeshub:api-builder (schema validation)
Verification:
  24h fuzz run produces zero new 5xx errors; all responses match documented schemas
Acceptance:
  CI integrates 30-min fuzz pass on every PR
Math:
  OWASP API Security Top 10 (2023)

──── 3. Chaos engineering harness ────
Files:
  - backend/tests/chaos/chaos_runner.py (new)
  - backend/tests/chaos/scenarios/*.yaml (new)
Spec:
  YAML-defined scenarios:
    mongo_down_60s.yaml — kill Mongo for 60s; assert system stays up + queue+drain
    schwab_disconnect_5min.yaml — drop WS 5min; assert reconnect + no data loss
    clock_skew_2h.yaml — bump process clock +2h; assert TTL-sensitive things behave
    memory_pressure_3gb.yaml — spawn hog consuming 3GB; assert graceful degrade
    disk_full.yaml — fill /tmp; assert DuckDB cache eviction + alert
Skills to use:
  • swarmclaw:coding-agent
  • red-teaming:godmode (chaos injection patterns)
  • hermeshub:agent-hardening (recovery + escalation)
  • software-development:debugging-hermes-tui-comman... (failure-mode debug)
Verification:
  All 5 scenarios pass; system never enters undefined state
Acceptance:
  `make chaos` runs all 5 locally; CI nightly job runs them
Math:
  Basiri et al. (2016) "Chaos Engineering" (Netflix paper)

──── 4. Performance regression tests ────
Files:
  - backend/tests/perf/test_p99_latency.py (new)
  - reports/perf_<date>.md (output)
Spec:
  Hot-path benchmarks (within ARCHITECTURE_DEEP.md budgets):
    calc_gex_per_strike(1000 contracts): p99 < 5ms
    vpin_engine.update: p99 < 1ms
    hawkes_intensity(t, 500 events): p99 < 2ms
    SABR.hagan_lognormal_vol: p99 < 0.5ms
    /api/heatseeker/flip-zones e2e: p99 < 100ms
  pytest-benchmark; CI fails on regression >20% vs baseline
Skills to use:
  • swarmclaw:coding-agent
  • mlops:evaluating-l... (regression detection statistics)
Verification:
  Baselines locked; CI reports regression % per PR
Acceptance:
  All 5 benchmarks within budget on baseline run
Math:
  Gil Tene "How NOT to Measure Latency" — HdrHistogram methodology

──── 5. Snapshot tests for math correctness ────
Files:
  - backend/tests/snapshots/*.json (snapshots)
  - backend/tests/services/test_snapshot_math.py (new, 12+ tests)
Spec:
  For each math kernel, store canonical-input output as JSON snapshot
  Test re-runs kernel + asserts bit-for-bit match
  Use syrupy or pytest-snapshot
  Catches algorithmic drift property + parity tests might miss
Skills to use:
  • swarmclaw:coding-agent
  • gbrain:academic-verify (canonical inputs from Hull textbook)
Verification:
  12+ snapshots locked
Acceptance:
  Drift requires explicit `pytest --snapshot-update`

═══ STOP CONDITIONS, DISCIPLINE, END-OF-ROUND (same template) ═══

Risks:
  • Mutation + stateful tests slow → mark @pytest.mark.slow, nightly not per-PR
  • Chaos tests need privileges → Docker isolation, gate on --chaos flag

BEGIN.
═══════════════════════════════════════════════════════════════
```

---

## Agent 5 — Pearl causal inference

**Card:** `O-MATH-VALID`

```
═══════════════════════════════════════════════════════════════
You are Hermes Agent 5, Round 3. FULL AUTONOMY.

STEP 0-3: verify, load context (anchor #agent-5), operating laws.
Time-window: mostly [B]; task 2 (ATE) needs Mongo for historical backfill = [A].

YOUR ROUND 3 GOAL:
Move from descriptive ("VPIN is high") to causal ("a 1bp move in VPIN CAUSES a 0.3bp move
in spread, controlling for vol regime"). Implement Pearl-style do-calculus on the dealer-
hedging system. This is what separates Renaissance from retail.

═══ DELIVERABLES ═══

──── 1. Causal DAG of the dealer-hedging system [B] ────
Files:
  - docs/causal/dag.md (Mermaid diagram)
  - backend/services/causal/dag.py (new)
  - backend/tests/services/causal/test_dag.py (new, 8+ tests)
Spec:
  Nodes (observable signals): spot, GEX, VPIN, QI, kyle_lambda, dealer_hedge_pressure,
    realized_vol, anomaly_score
  Edges (causal arrows from theory):
    spot → GEX (mechanical)
    GEX → dealer_hedge_pressure (theoretical)
    dealer_hedge_pressure → spot (feedback)
    VPIN → spread → kyle_lambda
    realized_vol ↔ dealer_hedge_pressure (mutual)
  Validate via dowhy.causal_graph.CausalGraph (add to requirements)
Skills to use:
  • swarmclaw:coding-agent
  • gbrain:academic-verify (DAG conforms to Pearl 2009)
  • creative:architecture-diagram (mermaid render)
  • data-science:jupyter-live-kernel (DAG visualization notebook)
Verification:
  DAG passes acyclicity check; renders cleanly in mkdocs
Acceptance:
  Documented assumptions file at docs/causal/ASSUMPTIONS.md (no unobserved confounders, etc.)
Math:
  Pearl (2009) *Causality: Models, Reasoning, and Inference*, 2nd ed., Cambridge UP
  Schölkopf et al. (2021) "Toward Causal Representation Learning"

──── 2. ATE estimation [A] ────
Files:
  - backend/services/causal/ate_estimator.py (new)
  - backend/tests/services/causal/test_ate.py (new, 10+ tests)
Spec:
  For each (treatment, outcome) pair, compute ATE via:
    - propensity score + IPTW (dowhy library)
    - OR EconML.dml.LinearDML for double machine learning
  Confidence intervals via bootstrap (B=1000)
  Treatments: "GEX flips negative", "VPIN crosses 0.7", "Trinity score > 80",
    "Anomaly threshold breached", "Hawkes branching > 0.8"
  Outcomes: "realized_vol_30min", "spread_15min", "max_drawdown_60min"
Skills to use:
  • autonomous-ai-agents:codex (long DML training)
  • mlops:dspy (structured treatment-outcome enumeration)
  • mlops:evaluating-l... (CI estimation)
  • gbrain:academic-verify (Chernozhukov DML implementation)
  • data-science:jupyter-live-kernel (ATE viz notebook)
Verification:
  reports/causal_ate_<date>.md with ATE point estimates + 95% CIs for 5 treatments
Acceptance:
  Sample sizes adequate; CIs non-degenerate
Math:
  Imbens, Rubin (2015) *Causal Inference for Statistics, Social, and Biomedical Sciences*
  Chernozhukov et al. (2018) "Double/Debiased Machine Learning" *Econometrics J.*

──── 3. Counterfactual scenario engine [B] ────
Files:
  - backend/services/causal/counterfactual.py (new)
  - backend/tests/services/causal/test_counterfactual.py (new, 8+ tests)
Spec:
  API: simulate_counterfactual(observation, intervention) → counterfactual_outcome
  Example: "given the May 15 2025 observation, what would happen if VPIN had been 50% lower?"
  Use DAG + learned structural equations (dowhy.gcm)
Skills to use:
  • swarmclaw:coding-agent
  • gbrain:academic-verify (Pearl's twin-network counterfactual algorithm)
  • mlops:dspy (counterfactual prompt generation)
Verification:
  3 named counterfactuals execute end-to-end; results match published economic intuition
Acceptance:
  Endpoint GET /api/causal/counterfactual returns deterministic outputs
Math:
  Pearl (2018) *The Book of Why* §4 — counterfactuals
  Pearl (2009) ch.7 — structural causal models

──── 4. Granger-causality for Trinity Alignment [A] ────
Files:
  - backend/services/causal/granger.py (new)
  - backend/tests/services/causal/test_granger.py (new, 8+ tests)
  - docs/THEORY.md (extend Trinity section)
Spec:
  Does SPX's GEX Granger-cause SPY's GEX? QQQ's?
  statsmodels.tsa.stattools.grangercausalitytests with lags 1, 5, 15 min
  Multivariate VAR fit on all 3 series; ADF stationarity check first
Skills to use:
  • swarmclaw:coding-agent
  • gbrain:academic-verify (Granger 1969 + Hamilton 1994 Ch.11)
  • mlops:evaluating-l... (statistical inference)
  • data-science:jupyter-live-kernel (causality plot)
Verification:
  Granger p-values + F-stats per pair logged
Acceptance:
  Trinity "leading-lagging" score added to /api/heatseeker/trinity-confluence
Math:
  Granger (1969) "Investigating Causal Relations" *Econometrica*
  Hamilton (1994) *Time Series Analysis*, Ch.11

──── 5. Causal-validated trade rationale [A] ────
Files:
  - backend/services/causal/trade_rationale.py (new)
  - backend/routes/causal.py (new)
  - backend/tests/services/causal/test_trade_rationale.py (new, 8+ tests)
Spec:
  For each TradeIntent from Agent 2's RL policy: query causal model for 1-sentence explanation
  Output: {intent_id, primary_cause: "negative GEX (z=-2.1) + VPIN spike (cdf=0.87)",
           supporting_evidence: [...], counterfactual: "if VPIN had been at median, intent would not have fired"}
  Endpoint: GET /api/causal/explain/{intent_id}
Skills to use:
  • swarmclaw:coding-agent
  • mlops:dspy (LLM-shaped rationale generation, structured)
  • hermeshub:api-builder (endpoint scaffolding)
  • gbrain:academic-verify (rationale cites actual causal relationship from DAG)
Verification:
  Every TradeIntent gets rationale within 100ms
Acceptance:
  Rationale is human-readable + cites primary cause + supporting evidence + counterfactual

═══ STOP CONDITIONS, DISCIPLINE, END-OF-ROUND (same template) ═══

Risks:
  • Causal inference assumes no unobserved confounders — document explicitly in ASSUMPTIONS.md
  • Granger ≠ Pearl causation — use Granger only as preliminary screen

BEGIN.
═══════════════════════════════════════════════════════════════
```

---

## Agent 6 — Knowledge graph + LLM-augmented research

**Card:** `O-RESEARCH-LOOP`

```
═══════════════════════════════════════════════════════════════
You are Hermes Agent 6, Round 3. FULL AUTONOMY. CONTINUOUS LOOP.

STEP 0-3: verify, load context (anchor #agent-6), operating laws.
Time-window: mixed — task 1 [A] (Neo4j needs Mongo for embedding storage),
             tasks 2/3/4 [B], task 5 [A] (HF rate limits eased in Window A).

YOUR ROUND 3 GOAL:
Build a knowledge graph of every paper / repo / technique / author. LLM-augmented Q&A:
when Nav asks "what does Skylit do about pin risk?" the system answers from the graph + cites
sources. This is the difference between "we have papers" and "we know what the papers say."

═══ DELIVERABLES ═══

──── 1. Neo4j knowledge graph schema [A] ────
Files:
  - infra/neo4j/docker-compose.neo4j.yml (new)
  - backend/services/research/knowledge_graph.py (new)
  - backend/tests/services/research/test_kg.py (new, 10+ tests)
Spec:
  Nodes: Paper, Author, Concept, Implementation (repo), Technique, Hermes_Service
  Edges: AUTHORED, CITES, IMPLEMENTS, USES_TECHNIQUE, PORTED_TO, EXTENDS, CRITIQUES
  Populate from existing data:
    - 200+ arxiv papers in data/external_research/
    - 30+ cloned repos in data/github-repos/cloned/
    - 18 Hermes services in backend/services/
Skills to use:
  • swarmclaw:coding-agent
  • gbrain:archive-crawler (paper ingestion)
  • gbrain:article-enric... (citation enrichment)
  • gbrain:academic-verify (graph integrity)
  • hermeshub:api-builder (Neo4j Cypher API wrapper)
Verification:
  5000+ nodes + 20k+ edges populated
  Query `MATCH (h:Hermes_Service)-[:IMPLEMENTS]->(t:Technique)<-[:USES_TECHNIQUE]-(p:Paper) RETURN h, p` returns sensible joins
Acceptance:
  Docker compose brings up Neo4j locally; KG persists across restarts
Math:
  Robinson, Webber (2015) *Graph Databases*

──── 2. LLM-augmented research Q&A [B] ────
Files:
  - backend/services/research/qa_engine.py (new)
  - backend/routes/research.py (extend)
  - backend/tests/services/research/test_qa.py (new, 12+ tests)
Spec:
  Endpoint: POST /api/research/ask {"question": "..."}
  Pipeline: NL question → Cypher generation (via OpenRouter Claude) → KG query →
            retrieved nodes/papers → LLM synthesis with citations
  Every answer: 3+ paper citations + Hermes code pointer + confidence score
Skills to use:
  • swarmclaw:coding-agent
  • mlops:dspy (DSPy pipeline — structured prompting)
  • mlops:evaluating-l... (Q&A quality eval harness)
  • mcp:native-mcp (expose ask-research as MCP tool for cross-tool use)
  • research:llm-wiki... (LLM-augmented retrieval pattern)
Verification:
  10 benchmark questions → correct + cited answers
  Latency <3s end-to-end
Acceptance:
  Q&A integrated into ask-hermes CLI (Agent 9's deliverable)
Math:
  Khattab et al. (2023) "DSPy: Compiling Declarative Language Model Calls"

──── 3. Citation network analysis [B] ────
Files:
  - scripts/citation_analysis.py (new)
  - reports/citation_network_<date>.md (output)
Spec:
  Build paper citation graph (Semantic Scholar API; rate-limit aware)
  Compute: PageRank, betweenness centrality, community detection (Louvain)
  Identify: most-cited papers in our scope, bridge papers, emerging clusters
Skills to use:
  • swarmclaw:coding-agent
  • gbrain:archive-crawler (Semantic Scholar bulk pull)
  • gbrain:academic-verify (graph metrics correctness)
  • research:llm-wiki... (background on emerging topics)
Verification:
  Report ranks top 20 papers by influence; identifies 3+ emerging-cluster topics
Acceptance:
  Citation network exported to Neo4j as Paper-CITES-Paper edges
Math:
  Newman (2010) *Networks: An Introduction*

──── 4. Auto-port v2 with semantic similarity [B] ────
Files:
  - scripts/auto_port_v2.py (new)
  - backend/services/research/semantic_search.py (new)
Spec:
  For each unported repo: embed (sentence-transformers all-MiniLM-L6-v2) README + key docstrings
  Match against embeddings of Hermes service docstrings
  Top-3 closest Hermes services = candidate integration points
  Generate port proposal: which Hermes file to extend, what function to add, paper citations
Skills to use:
  • swarmclaw:coding-agent
  • mlops:dspy (port proposal generation)
  • gbrain:academic-verify (verify ported math matches source)
  • autonomous-ai-agents:codex (port implementation)
Verification:
  5 ports proposed end-to-end with semantic-match scores
Acceptance:
  Nav manually approves; merged ports get integration tests
Math:
  Reimers, Gurevych (2019) "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks"

──── 5. Author influence tracker [A] ────
Files:
  - backend/services/research/author_influence.py (new)
  - memory/author_influence_<date>.md (output)
Spec:
  Tracked authors: Asness, LdP, Gatheral, Carreira, Diehl, Doloc, Brown
  Pull h-index, recent paper count, last-published date
  Auto-detect new publications → digest with abstract + Hermes-relevance score
Skills to use:
  • swarmclaw:coding-agent
  • hermeshub:arxiv-watcher (continuous monitoring)
  • gbrain:archive-crawler (SSRN/arXiv pulls)
  • gbrain:article-enric... (abstract enrichment)
  • research:arxiv, research:blogwatcher (multi-source)
Verification:
  Weekly digest includes 5+ author updates with relevance ranking
Acceptance:
  Author alerts surface as kanban cards when new papers published

═══ CONTINUOUS LOOP — KEEP RUNNING ═══

This agent is the ONLY one with `stop_condition: never`. Other agents complete their
Round 3 and exit; you keep running the research → KG → port loop indefinitely.

When token/wall-clock exhausts: checkpoint to kanban/cards/O-RESEARCH-LOOP.md with current
loop position. Next worker picks up from checkpoint.

═══ STOP CONDITIONS (modified for continuous loop) ═══
  ✗ Truth audit red → fix immediately
  ✗ 3 push failures → checkpoint + blocker
  ✗ Token budget → checkpoint, next worker resumes
  ✓ Round 3 deliverables (tasks 1-5) all shipped → continue the LOOP, do NOT exit

BEGIN.
═══════════════════════════════════════════════════════════════
```

---

## Agent 7 — Production deployment + live-trading enablement

**Card:** `O-SECURITY`

```
═══════════════════════════════════════════════════════════════
You are Hermes Agent 7, Round 3. FULL AUTONOMY.

STEP 0-3: verify, load context (anchor #agent-7), operating laws.
Time-window: all [B] (deployment work, no live deps).

YOUR ROUND 3 GOAL:
Production deployment to Azure ($100 student credit). HTTPS + monitoring + SLA enforcement
+ live-trading switch (gated behind every safety check). This is what makes the difference
between "Hermes works on Nav's laptop" and "Hermes runs reliably in production."

═══ DELIVERABLES (all [B]) ═══

──── 1. Azure deployment via Terraform ────
Files:
  - infra/terraform/main.tf, variables.tf, outputs.tf (new)
Spec:
  Resources: App Service Plan (B1, ~$13/mo), App Service (FastAPI),
             Azure Container Registry, Azure Cosmos DB (Mongo API tier, free 400 RU/s)
  Networking: VNet + private endpoint for Cosmos (no public DB access)
  Secrets: Azure Key Vault, referenced via Managed Identity (no .env in container)
Skills to use:
  • swarmclaw:coding-agent
  • hermeshub:agent-hardening (cloud retry + secret rotation)
  • red-teaming:godmode (security review of Terraform plan)
  • devops:react-craco... (if frontend deployed to Azure Static Web Apps)
Verification:
  `terraform apply` provisions full stack <10min
  `curl https://hermes.<your>.azurewebsites.net/api/health` → 200
Acceptance:
  Production endpoint live; cost <$30/mo within Azure free tier + B1
Math/practice:
  Terraform Azure provider docs; Microsoft Cloud Adoption Framework

──── 2. HTTPS + Caddy reverse proxy ────
Files:
  - infra/caddy/Caddyfile (new)
  - docker-compose.prod.yml (new)
Spec:
  Auto-HTTPS via Let's Encrypt (Caddy handles natively)
  HSTS preload, CSP `default-src 'self'`, X-Frame-Options DENY
  Static files cached 1y immutable; API routes proxy to localhost:8000
Skills to use:
  • swarmclaw:coding-agent
  • red-teaming:godmode (header policy review)
  • hermeshub:agent-hardening (cert rotation patterns)
Verification:
  SSL Labs Server Test → A+
  securityheaders.com → A+
Acceptance:
  HTTPS green padlock; HSTS preload eligible

──── 3. SLO + error-budget tracking ────
Files:
  - backend/services/slo_tracker.py (new)
  - grafana/dashboards/slo.json (new)
  - prometheus/recording_rules/slo.yml (new)
Spec:
  SLOs:
    API availability 99.9% (43.2 min/mo budget)
    API p99 latency < 200ms
    Schwab ingestion uptime 99% market-hours
    WS message delivery 99.99%
  Error-budget burn rate alert: if monthly budget consumed in <50% of month
Skills to use:
  • swarmclaw:coding-agent
  • mlops:evaluating-l... (SLO statistical formulation)
  • hermeshub:agent-hardening (burn-rate detection)
Verification:
  4 SLOs tracked in Grafana; burn-rate alerts fire correctly on synthetic test
Acceptance:
  Wires into Agent 10's alert routing
Math:
  Beyer et al. (2016) *Site Reliability Engineering* Ch.4 — SLOs

──── 4. LIVE-TRADING SWITCH (with circuit breakers) ────
Files:
  - backend/services/live_trading_switch.py (new)
  - backend/routes/admin.py (extend)
  - backend/tests/services/test_live_trading_switch.py (new, 15+ tests)
Spec:
  States: OFF → PAPER_ONLY → LIVE_TINY ($1k max) → LIVE_NORMAL → LIVE_FULL
  Every transition requires: 2FA confirm (Nav phone + email) + audit-log entry
  Circuit breakers (any trip → demote one state, no transitions for 24h):
    daily P&L drawdown > -2% → demote
    >5 rejected fills in 1h → demote
    reconciliation discrepancy from Agent 1 → demote
    Agent 10 SLA breach → demote
Skills to use:
  • swarmclaw:coding-agent
  • red-teaming:godmode (test the 2FA + breaker logic for bypass paths)
  • hermeshub:agent-hardening (resilient state machine)
  • hermeshub:api-builder (admin endpoints)
Verification:
  Can transition OFF→PAPER via 2FA; can't skip states; every breaker has regression test
Acceptance:
  Live-trading switch defaults to OFF; only Nav can flip; full audit trail
Reference:
  SEC Rule 15c3-5 (Risk Management Controls for Brokers)

──── 5. Compliance audit trail ────
Files:
  - backend/services/audit_trail.py (new)
  - backend/tests/services/test_audit_trail.py (new, 10+ tests)
Spec:
  Every action (login, API call, order, position change, config edit):
  immutable log entry to Mongo audit_trail collection
  Fields: timestamp_utc, actor, action_type, target, before_state, after_state,
          ip_address, user_agent, request_id
  Retention: 7 years (SEC standard, even though Hermes isn't a broker — best practice)
  Hash-chain: each entry contains hash of previous → tamper-evident
Skills to use:
  • swarmclaw:coding-agent
  • red-teaming:godmode (tamper attempt tests)
  • hermeshub:agent-hardening (immutability guarantees)
  • software-development:confluence-decoder (project conventions)
Verification:
  Audit captures 100% of write actions; chain verification script runs in CI nightly
Acceptance:
  Tamper test (modify a row directly in Mongo) → chain verification detects + alerts
References:
  SEC Rule 17a-4; FINRA Rule 4511; NIST SP 800-53 (audit logging baselines)

═══ STOP CONDITIONS, DISCIPLINE, END-OF-ROUND (same template) ═══

LIVE-TRADING GATE — STRICT:
  This agent's task 4 + Critical security finding count == 0 + audit trail verified +
  Nav 2FA confirmation + Agent 1 reconciler running 24h with zero divergence →
  ONLY THEN can Nav MANUALLY flip OFF → PAPER_ONLY. No auto-flip ever.

BEGIN.
═══════════════════════════════════════════════════════════════
```

---

## Agent 8 — ML-driven kanban + capacity planning

**Card:** `O-KANBAN-ORCH`

```
═══════════════════════════════════════════════════════════════
You are Hermes Agent 8, Round 3. CONTINUOUS COORDINATOR (already running from R1/R2).

STEP 0-3: verify, load context (anchor #agent-8), operating laws.
Time-window: continuous; 5-min watch loop runs in both windows.

YOUR ROUND 3 GOAL:
Predictive coordination. Use historical agent throughput data to forecast completion times,
identify bottleneck patterns, suggest capacity reallocation. The kanban becomes a force
multiplier, not just a tracker.

═══ DELIVERABLES ═══

──── 1. Agent throughput model [A — needs historical kanban data] ────
Files:
  - backend/services/kanban/throughput_model.py (new)
  - backend/tests/services/kanban/test_throughput.py (new, 10+ tests)
Spec:
  Poisson regression on historical card-completion times (since R1, 2026-05-19)
  Features: agent_id, card_priority, lines_changed, files_touched, test_count_required,
            time_of_day, day_of_week
  Output: P(card_completes_within_T_hours | features)
Skills to use:
  • swarmclaw:coding-agent
  • mlops:evaluating-l... (regression validation)
  • mlops:dspy (feature engineering prompts)
  • gbrain:academic-verify (Poisson regression vs Hyndman §3)
Verification:
  Model trained on 100+ historical cards; cross-validated MAE < 1.5 hours
Acceptance:
  Throughput predictions surface in kanban/SWARM_STATUS.md
Math:
  Hyndman, Athanasopoulos (2018) *Forecasting: Principles and Practice* §3

──── 2. Bottleneck detector [B] ────
Files:
  - backend/services/kanban/bottleneck.py (new)
  - backend/tests/services/kanban/test_bottleneck.py (new, 8+ tests)
Spec:
  Every 30 min: compute per-agent metrics — cards-in-flight, avg-time-per-card,
                blocker-rate, push-failure-rate
  Identify bottlenecks: agent with cards_in_flight > 3 × median OR blocker_rate > 2 × median
  Surface to kanban/ARCHITECT_BRIEF.md
Skills to use:
  • swarmclaw:coding-agent
  • mlops:evaluating-l... (outlier detection)
  • hermeshub:agent-hardening (continuous loop resilience)
Verification:
  Detector flags synthetic-overloaded agent correctly
Acceptance:
  Bottleneck alerts wire to Agent 10's phone notifications

──── 3. Capacity rebalancing recommender [B] ────
Files:
  - backend/services/kanban/rebalancer.py (new)
  - backend/tests/services/kanban/test_rebalancer.py (new, 8+ tests)
Spec:
  When bottleneck detected: recommend which cards to reassign + to which agent
  Reassignment scoring: match card.required_skills to agent.skills (TF-IDF over commit messages)
  Prefer agents with cards_in_flight < median
  Output: kanban/REBALANCE_PROPOSAL.md for Nav to approve
Skills to use:
  • swarmclaw:coding-agent
  • mlops:dspy (skill-matching prompts)
  • mlops:evaluating-l... (assignment quality metric)
  • devops:kanban-orchestrator (board manipulation)
Verification:
  3 synthetic bottleneck scenarios → sensible reassignment proposals
Acceptance:
  Proposals surface as kanban cards for Nav
Math:
  Hungarian algorithm for optimal assignment (Kuhn 1955)

──── 4. Sprint retrospective generator [B] ────
Files:
  - scripts/generate_retro.py (new)
  - kanban/RETRO_<date>.md (output)
Spec:
  End of each sprint (weekly): aggregate completed cards + close-time stats + blockers
  Generate retro: what went well, what didn't, action items
  LLM-augmented via OpenRouter Claude (DSPy pipeline)
Skills to use:
  • swarmclaw:coding-agent
  • mlops:dspy (structured retro prompt)
  • autonomous-ai-agents:kanban-codex-... (codex worker for retro analysis)
Verification:
  Retro identifies 3+ improvement areas per sprint
Acceptance:
  Action items auto-spawn as kanban cards
Math:
  Brooks (1975) *The Mythical Man-Month* — Brooks's Law on rebalancing

──── 5. Multi-repo coordination [A] ────
Files:
  - backend/services/kanban/multi_repo.py (new)
  - kanban/multi_repo_status.md (output)
Spec:
  Cards can declare `affects_repos: [floww, gflows, baby-billy-dvt]`
  Watcher monitors all listed repos
  Cross-repo SWARM_STATUS.md aggregates state from all
Skills to use:
  • swarmclaw:coding-agent
  • devops:kanban-orchestrator
  • note-taking:obsidian (sync cross-repo status to Obsidian)
Verification:
  Card affecting 2 repos correctly shows commits from both
Acceptance:
  Multi-repo dashboard live in kanban/

═══ CONTINUOUS — DO NOT EXIT ═══

Like Agent 6, you keep running. End-of-Round-3 means: all 5 new behaviors integrated,
mark `round3_deliverables: done` in kanban/cards/O-KANBAN-ORCH.md, but the watch loop
keeps running. Next worker resumes from kanban state.

BEGIN.
═══════════════════════════════════════════════════════════════
```

---

## Agent 9 — Federated multi-modal memory

**Card:** `O-MEMORY-UNIFY`

```
═══════════════════════════════════════════════════════════════
You are Hermes Agent 9, Round 3. FULL AUTONOMY.

STEP 0-3: verify, load context (anchor #agent-9), operating laws.
Time-window: tasks 1, 4 = [A] (network/embeddings); tasks 2, 3, 5 = [B].

YOUR ROUND 3 GOAL:
Federated memory across Hermes instances (laptop, work, future cloud) + multi-modal
embeddings (text, code, charts, audio notes). Memory becomes a single addressable surface
that survives any single-machine failure.

═══ DELIVERABLES ═══

──── 1. Federated mem0 sync [A] ────
Files:
  - scripts/mem0_federate.py (new)
  - backend/services/memory/federation.py (new)
  - backend/tests/services/memory/test_federation.py (new, 10+ tests)
Spec:
  Multiple mem0 instances (laptop, work, cloud) share state via central message queue
  (Azure Service Bus or Redis pub-sub)
  Conflict resolution: last-writer-wins per entry; tombstones for deletes
  Replication lag SLA: <30s steady-state
Skills to use:
  • swarmclaw:coding-agent
  • mem0:mem0-cli, mem0-integrate, mem0-test-integration...
  • hermeshub:agent-hardening (eventually-consistent replication)
  • gbrain:academic-verify (eventual consistency patterns)
Verification:
  2-node sim shows convergence after writes from both sides
  100 concurrent updates converge to consistent state
Acceptance:
  Federation handles 1000 writes/min without drift
Math:
  Bailis et al. (2013) "Eventual Consistency Today: Limitations, Extensions, and Beyond" *CACM*

──── 2. Code embeddings [B] ────
Files:
  - scripts/embed_codebase.py (new)
  - backend/services/memory/code_embeddings.py (new)
Spec:
  For every .py / .ts / .js file: embed via CodeBERT (microsoft/codebert-base)
  Store in vector DB (mem0's built-in if vector-capable; else Qdrant)
  `ask-hermes "where is GEX calculated?"` → top-3 code pointers with snippets
Skills to use:
  • swarmclaw:coding-agent
  • mem0:mem0-integrate (vector storage)
  • mlops:dspy (code-search prompt structure)
  • software-development:confluence-decoder
Verification:
  Semantic code search returns expected results for 10 benchmark queries
Acceptance:
  Inference latency <500ms per query
Math:
  Feng et al. (2020) "CodeBERT: A Pre-Trained Model for Programming and Natural Languages"

──── 3. Chart screenshot embeddings [B] ────
Files:
  - scripts/embed_screenshots.py (new)
  - backend/services/memory/chart_embeddings.py (new)
Spec:
  For every screenshot in /screenshots/: embed via CLIP (openai/clip-vit-base-patch32)
  Use case: "show me the Heatseeker view from last Tuesday morning" → CLIP retrieves matching screenshot
Skills to use:
  • swarmclaw:coding-agent
  • mem0:mem0-integrate
  • mlops:evaluating-l... (CLIP retrieval eval)
Verification:
  5 benchmark text queries return correct screenshots
Acceptance:
  Integrated into ask-hermes CLI
Math:
  Radford et al. (2021) "Learning Transferable Visual Models From Natural Language Supervision" (CLIP)

──── 4. Voice memo transcription + embedding [A — Whisper needs network for model dl] ────
Files:
  - scripts/transcribe_voice_memos.py (new)
  - backend/services/memory/voice_embeddings.py (new)
Spec:
  Whisper (local, whisper-base) transcribes iOS Voice Memos sync folder
  Transcript → mem0 with tag `source:voice_memo`
Skills to use:
  • swarmclaw:coding-agent
  • mem0:mem0-integrate
  • mlops:dspy (post-transcription enrichment)
Verification:
  Sample voice memo transcribes correctly; searchable via ask-hermes
Acceptance:
  Voice notes integrated into unified memory search
Math:
  Radford et al. (2022) "Robust Speech Recognition via Large-Scale Weak Supervision" (Whisper)

──── 5. Memory health monitor [B] ────
Files:
  - backend/services/memory/health.py (new)
  - backend/tests/services/memory/test_health.py (new, 8+ tests)
Spec:
  Metrics: entry count, query latency p99, embedding-cache hit rate, federation lag
  Endpoint: GET /api/admin/memory/health
  Wire into Agent 10's Grafana
Skills to use:
  • swarmclaw:coding-agent
  • hermeshub:api-builder
  • hermeshub:agent-hardening
Verification:
  Health endpoint <50ms; all metrics in Grafana
Acceptance:
  Alert when query p99 > 500ms or federation lag > 60s

═══ STOP CONDITIONS, DISCIPLINE, END-OF-ROUND (same template) ═══

Risk: Multi-modal embedding model footprint ~3GB. Consider remote inference if local resource-constrained.

BEGIN.
═══════════════════════════════════════════════════════════════
```

---

## Agent 10 — Predictive alerting + chaos forecasting

**Card:** `O-OBSERVABILITY`

```
═══════════════════════════════════════════════════════════════
You are Hermes Agent 10, Round 3. FULL AUTONOMY.

STEP 0-3: verify, load context (anchor #agent-10), operating laws.
Time-window: tasks 1, 2, 4 = [A] (training needs metrics history); tasks 3, 5 = [B].

YOUR ROUND 3 GOAL:
Predictive alerting. Move from "alert when threshold breached" to "alert when we predict
a threshold WILL be breached in N minutes." Plus chaos-event forecasting. Nav gets called
when something matters, AND ONLY when something matters.

═══ DELIVERABLES ═══

──── 1. Predictive alert engine [A] ────
Files:
  - backend/services/observability/predictive_alerts.py (new)
  - ./project_oracle/models/predictive_alert_v1.pt (artifact)
  - backend/tests/services/observability/test_predictive_alerts.py (new, 10+ tests)
Spec:
  For each critical metric (ingestion_rate, queue_depth, vpin_current, p99_latency):
  train forecasting model (PatchTST or LSTM)
  Predict next 15 min; alert if any forecast point breaches threshold
  Two-tier alerts:
    WARNING (predicted breach in 5-15 min)
    CRITICAL (predicted breach <5 min OR already breached)
Skills to use:
  • autonomous-ai-agents:codex (training scripts)
  • mlops:dspy (model hyperparameter sweep)
  • mlops:evaluating-l... (forecast accuracy metrics)
  • gbrain:academic-verify (LSTM impl vs Hochreiter 1997; PatchTST vs Nie 2022)
Verification:
  80%+ recall on actual breaches with ≤10% FP rate
Acceptance:
  Predictive alerts surface in Grafana before threshold breaches
Math:
  Hochreiter, Schmidhuber (1997) "Long Short-Term Memory"
  Nie et al. (2022) "A Time Series is Worth 64 Words" (PatchTST)

──── 2. Anomaly forecasting for the trading system itself [A] ────
Files:
  - backend/services/observability/system_health_forecaster.py (new)
  - backend/tests/services/observability/test_system_forecaster.py (new, 8+ tests)
Spec:
  Predict: "system likely to enter degraded state within next hour" from metric trends
  Inputs: 60-min history of all metrics (multivariate)
  Output: degradation_probability per service over next [5, 15, 30, 60] min
Skills to use:
  • autonomous-ai-agents:codex
  • mlops:evaluating-l... (probabilistic forecast eval — CRPS, quantile loss)
  • gbrain:academic-verify (DeepAR impl vs Salinas 2020)
Verification:
  On held-out 30-day window with known incidents, model predicts ≥10min in advance ≥70% of time
Acceptance:
  Self-prediction integrated with Agent 8's predictive kanban
Math:
  Salinas et al. (2020) "DeepAR: Probabilistic Forecasting with Autoregressive Recurrent Networks"

──── 3. Incident similarity search [B] ────
Files:
  - backend/services/observability/incident_similarity.py (new)
  - backend/routes/incidents.py (extend)
Spec:
  Per new incident: embed (Sentence-BERT) → search past incidents for similar
  Output: top-3 past incidents + their resolutions
Skills to use:
  • swarmclaw:coding-agent
  • mlops:evaluating-l... (retrieval accuracy)
  • mem0:mem0-integrate (incident corpus storage)
Verification:
  5 synthetic test incidents → expected related historical incidents retrieved
Acceptance:
  Similarity search wired into incident-creation flow
Math:
  Reimers, Gurevych (2019) "Sentence-BERT"

──── 4. Cost forecasting + budget protection [A] ────
Files:
  - backend/services/observability/cost_forecaster.py (new)
  - grafana/dashboards/cost_forecast.json (new)
Spec:
  Forecast end-of-month cost (exponential smoothing)
  Auto-action: if forecasted > 110% budget → throttle non-critical (Agent 6 loop 60min → 240min)
Skills to use:
  • swarmclaw:coding-agent
  • mlops:evaluating-l... (forecast accuracy)
  • mlops:dspy (throttling decision prompt)
Verification:
  $-dashboard shows forecasted EoM cost; auto-throttle triggers on synthetic over-budget
Acceptance:
  Burn-rate alerts at 80% / 95% budget
Math:
  Hyndman, Athanasopoulos (2018) §7 — exponential smoothing methods

──── 5. Self-healing runbook automation [B] ────
Files:
  - backend/services/observability/auto_remediation.py (new)
  - docs/INCIDENTS/runbooks/*.yaml (3+ runbooks)
Spec:
  YAML-defined runbooks per known incident type:
    detection_signature (which metrics + pattern)
    automatic_remediation_steps
    human_confirmation_gate (before destructive actions)
Skills to use:
  • swarmclaw:coding-agent
  • mlops:dspy (runbook synthesis from past incidents)
  • hermeshub:agent-hardening (safe automation patterns)
  • red-teaming:godmode (test that confirmation gate can't be bypassed)
Verification:
  3 runbooks defined; one auto-remediates in synthetic test
Acceptance:
  Human-in-the-loop gate for destructive actions confirmed
Math/practice:
  Beyer et al. (2016) *SRE* Ch.12 — Effective Troubleshooting

═══ STOP CONDITIONS, DISCIPLINE, END-OF-ROUND (same template) ═══

Risk: Predictive alerts firing too early erode trust (cry-wolf). Calibrate FPR against historical baseline.

BEGIN.
═══════════════════════════════════════════════════════════════
```

---

## Quick reference

### Agent → Card → Window summary

| `<N>` | Kanban Card | Window | Continuous? |
|---|---|---|---|
| 1 | `O-PHASE1-SCHWAB` | mostly [A] | no |
| 2 | `O-PHASE2-ANOMALY` | mixed | no |
| 3 | `O-PHASE3-DASH` | all [B] | no |
| 4 | `O-TEST-INFRA` | all [B] | no |
| 5 | `O-MATH-VALID` | mixed | no |
| 6 | `O-RESEARCH-LOOP` | mixed | **yes** |
| 7 | `O-SECURITY` | all [B] | no |
| 8 | `O-KANBAN-ORCH` | continuous | **yes** |
| 9 | `O-MEMORY-UNIFY` | mixed | no |
| 10 | `O-OBSERVABILITY` | mixed | no |

### Live-trading gate (immutable)

PAPER_ONLY until ALL of:
- Agent 7 task 4 (live-trading switch + circuit breakers) shipped
- Critical security findings count == 0
- Audit trail end-to-end verified (Agent 7 task 5)
- Reconciliation loop (Agent 1 task 5) running 24h with zero divergence
- Nav 2FA confirmation

Then Nav MANUALLY flips OFF → PAPER_ONLY. Never auto.

### Memory recovery path (if context wipes)

1. `~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/MEMORY.md`
2. `DISPATCH_PLAN_ORACLE.md`, `_ROUND2.md`, `_ROUND3.md` at repo root
3. `LAUNCH_PROMPTS.md` (this file)
4. `kanban/SWARM_STATUS.md` (live state)
5. `ask-hermes "agent<N> status"`

### Folder map (post-consolidation, after Section 0 runs once)

```
/Users/nav/Documents/GitHub/floww/                       ← THE project (only floww-owned dir)
~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/   ← persistent Hermes memory
~/Documents/GitHub/Hermes/                               ← Obsidian vault (Agent 9 syncs)
/Users/nav/gflows/                                       ← LEGACY (audited, not touched)
/Applications/Claude\ everything/                        ← Nav's personal (Hermes never edits)
[/Users/nav/gex-repos/                                   ← REMOVED after consolidation]
```
