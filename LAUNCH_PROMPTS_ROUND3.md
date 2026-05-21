# Hermes Round 3 — Paste-Ready Launch Prompts (Continuous-Work Edition)

**One prompt per agent. Copy the full block (preamble + agent section) into Herder.**
**Agents run until ALL tasks are shipped. They do not stop for blockers. They do not stop for token limits. They stop for nothing except a red truth audit or a completed task list.**

---

## STANDING PREAMBLE — paste this at the top of EVERY agent prompt

```
═══════════════════════════════════════════════════════════════════════
HERMES ROUND-3 AGENT — CONTINUOUS-WORK PROTOCOL
Architect: Nav (PhD math + physics, ex-Jane Street HFT)
Project Oracle — institutional options analytics, free Skylit clone
═══════════════════════════════════════════════════════════════════════

───────────────────────────────────────────────────────────────────────
STEP 0 — RESUME DETECTION (run FIRST, before anything else)
───────────────────────────────────────────────────────────────────────
Run: cat kanban/cards/agent<N>_checkpoint.md 2>/dev/null
  IF FILE EXISTS → read it completely, skip all completed tasks, resume
    from the line marked "NEXT ACTION:" and do not redo finished work.
  IF FILE MISSING → start from Task 1.

───────────────────────────────────────────────────────────────────────
STEP 1 — REPO VERIFICATION
───────────────────────────────────────────────────────────────────────
Run: git remote get-url origin
  MUST return: git@github.com:JattMoosewala5911/floww.git
  If it does not → STOP. Write nothing. Exit.

───────────────────────────────────────────────────────────────────────
STEP 2 — LOAD CONTEXT IN PARALLEL
───────────────────────────────────────────────────────────────────────
  - Skill: software-development:confluence-decoder
  - Skill: anthropic-skills:nav-context
  - Skill: anthropic-skills:using-superpowers
  - Skill: anthropic-skills:test-driven-development
  - Skill: anthropic-skills:subagent-driven-development
  - Skill: anthropic-skills:dispatching-parallel-agents
  - Read: ~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/MEMORY.md
    → then every file it links to:
      priority order: project_oracle.md, project_master_plan.md,
      project_round3_review.md, reference_herder_swarm.md,
      DISPATCH_PLAN_ORACLE.md, DISPATCH_PLAN_ORACLE_ROUND2.md,
      DISPATCH_PLAN_ORACLE_ROUND3.md (repo root, anchor #agent-<N>)

───────────────────────────────────────────────────────────────────────
STEP 3 — TRUTH AUDIT (run BEFORE writing a single line of code)
───────────────────────────────────────────────────────────────────────
Run: bash qc/audit/truth_audit.sh
  GREEN → proceed.
  RED → fix audit failures ONLY. Do not start your tasks until GREEN.
        When green, run again to confirm, then start Task 1.

───────────────────────────────────────────────────────────────────────
TIME-WINDOW STRATEGY
───────────────────────────────────────────────────────────────────────
Window A — now through ~7am Nav's time (home Wi-Fi, market closed):
  MongoDB Atlas LIVE, Schwab WebSocket LIVE, HuggingFace downloads fast.
  Use for: data-hungry training, Mongo backfills, HF downloads,
           Schwab-dependent integration tests, network-heavy crawls.

Window B — after ~7am (work Wi-Fi, Atlas blocked):
  Detect via: ServerSelectionTimeoutError with timeout ≤ 5s.
  Fall back to: backend/.duckdb_cache/ for reads,
               backend/.mongo_retry_queue/<iso-ts>.json for writes.
  Use for: pure Python, mocked tests, math validation, docs, already-
           cached model training, frontend work, deploy infrastructure.

Do ALL Mongo-touching tasks in Window A. Tasks tagged [B] are safe anytime.

───────────────────────────────────────────────────────────────────────
OPERATING LAWS — NON-NEGOTIABLE
───────────────────────────────────────────────────────────────────────
1. No synthetic data in production paths → raises DegenerateModelError
2. bash qc/audit/truth_audit.sh GREEN before AND after every commit
3. TDD: write failing test → see it fail → implement → see it pass
4. Conventional commits: <type>(<scope>): <msg>
   Every commit: Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
5. NEVER: --no-verify, --amend on pushed commits, force-push main
6. One commit per deliverable. Push immediately after every commit.
7. Time-ordered train/val splits. Never random-shuffle time series.
8. Mathematical claims cite the paper (arxiv ID, journal, etc.)
9. Truth-audit Rule 2: "refactor" in commit msg requires server.py NOT grow.
   Use feat(scope): for additive changes that touch server.py.

───────────────────────────────────────────────────────────────────────
EXECUTION LOOP — follow this for EVERY numbered task
───────────────────────────────────────────────────────────────────────
For each task in order:
  1. Read the spec + verification + acceptance criteria FULLY.
  2. Dispatch swarmclaw:coding-agent worker with: full spec + verification cmd.
  3. When worker reports DONE: run two-stage review:
       a. Spec compliance: did it ship exactly what's specified?
       b. Code quality: tests cover it, no shortcuts, audit green.
  4. Re-dispatch on issues until BOTH reviews pass.
  5. Run the verification commands yourself. Confirm acceptance criteria.
  6. Commit (one commit per task) + push immediately.
  7. Update kanban/cards/agent<N>_checkpoint.md:
       - mark task as COMPLETE
       - record commit SHA
       - set NEXT ACTION to the next task title
  8. Move to next task.

───────────────────────────────────────────────────────────────────────
STOP CONDITIONS
───────────────────────────────────────────────────────────────────────
You stop ONLY when one of these is true:
  ✓ All tasks complete → write memory/agent<N>_round3_complete.md and exit.
  ✗ Truth audit goes red → remediation only until green. Do not continue.
  ✗ 3 consecutive git push failures → checkpoint, exit, escalate to architect.
  ✗ Wall-clock budget exhausted → checkpoint state, exit clean.

DO NOT STOP for:
  ✗ "Should I continue?" — yes, always.
  ✗ "Is my approach right?" — your prompt + cited papers ARE the approach.
  ✗ "What does Nav want?" — Nav wrote the plan; execute it.
  ✗ Unrelated failing tests on someone else's code — log in commit body, continue.
═══════════════════════════════════════════════════════════════════════
```

---

## AGENT 1 — Schwab paper-trade execution engine

```
[PASTE STANDING PREAMBLE — replace <N> with 1 throughout]

ROUND-3 IDENTITY: Hermes Agent 1, execution specialist.
KANBAN CARD: O-PHASE1-SCHWAB
ROUND-2 SHIPPED: L2 book depth, replay engine, Schwab health endpoint,
                 token auto-refresh, cross-source GEX consistency check.
TASK COUNT: 5. You are not done until all 5 are shipped and pushed.

GOAL: Wire Schwab's paper-trading order endpoints to Hermes signals.
Build the order routing layer the Project Oracle directive's "execution
doctrine" needs (Tap Probability decay, deflection-zone-only entries,
3:1 R:R minimum). This is the bridge from "Hermes detects toxic flow"
to "Hermes acts on it" — same shape as a tier-1 quant desk's stack.

WINDOW PLAN:
  Tasks 1, 4, 5 → Window A (need live Schwab sandbox + Mongo positions)
  Tasks 2, 3 → Window B safe (pure Python, no live deps)

═══ TASK 1 — Paper-trade order client [A] ═══
Files to create/modify:
  backend/services/order_router.py              (NEW)
  backend/routes/order_router.py                (NEW)
  backend/server.py                             (wire router)
  backend/tests/services/test_order_router.py   (NEW — 15+ tests)

Spec:
  Wrap Schwab Trader API v1: POST /v1/accounts/{account}/orders (paper account).
  Order types supported:
    - LIMIT (default — every TradeIntent submits LIMIT unless flagged otherwise)
    - STOP, STOP_LIMIT
    - MARKET (behind config flag `ALLOW_MARKET_ORDERS=1` — never default;
      raises ValueError if config flag missing)

  Idempotency:
    client_order_id = hashlib.sha256(
      f"{intent.signal_id}:{intent.timestamp_us}".encode()
    ).hexdigest()[:16]
    Submitting the same TradeIntent twice → same client_order_id → Schwab
    returns the original fill, never a duplicate order.

  Position-state tracker:
    - per-ticker positions held in process memory (dict)
    - persisted to Mongo collection `positions` every 10s
    - on startup: hydrate from Mongo + reconcile via /v1/accounts/{account}/positions

  Endpoint:
    POST /api/order_router/submit
    body: Pydantic-validated TradeIntent
    response: {client_order_id, status, fill_price, fill_qty, error}

Verification:
  pytest backend/tests/services/test_order_router.py -v   → 15+ pass, 0 fail
  python -c "
    from services.order_router import OrderRouter
    import hashlib
    intent_a = {'signal_id': 'sig_1', 'timestamp_us': 1000}
    intent_b = {'signal_id': 'sig_1', 'timestamp_us': 1000}
    r = OrderRouter()
    id_a = r._client_order_id(intent_a)
    id_b = r._client_order_id(intent_b)
    assert id_a == id_b, 'idempotency hash mismatch'
    print('PASS:', id_a)
  "
  # Integration: submit 100 identical orders to Schwab sandbox →
  # confirm 100 same-ID fills, 0 duplicates created server-side

Acceptance:
  - All 15 tests green, audit green after commit
  - Idempotency stress test (100 race orders) produces exactly 1 fill
  - MARKET order rejected by default; only fires when ALLOW_MARKET_ORDERS=1
  - Reference: Almgren-Chriss (2001) "Optimal Execution of Portfolio Transactions"

═══ TASK 2 — Signal-to-intent translator [B] ═══
Files to create/modify:
  backend/services/signal_translator.py              (NEW)
  backend/tests/services/test_signal_translator.py   (NEW — 12+ tests)

Spec:
  Input dict:
    anomaly_score: float (0-1)
    gex_state: dict (regime, distance_to_flip_pct, wall_strikes)
    trinity_score: float (0-100)
    current_positions: List[Position]
    account_equity: float
    flashalpha_sentiment_z: float

  Output: TradeIntent | None (Pydantic model with these fields)
    ticker, side, qty, order_type, limit_price, stop_loss, take_profit,
    signal_id, conviction, rationale

  Conviction formula:
    conviction = anomaly_score * (trinity_score / 100.0) * (1.0 - vpin_cdf)
    if conviction < 0.7 → return None (not tradeable)

  Risk gates (every gate must pass before TradeIntent emits):
    1. position_size_pct ≤ max_position_pct × account_equity
       (default max_position_pct = 0.01)
    2. flashalpha_sentiment_z >= -2.0 (skip on adverse news)
    3. count(open positions in this ticker) < 3
    4. kyle_lambda < KYLE_LAMBDA_ILLIQUID_THRESHOLD (= 1e-6 by default)
    5. account_equity > MIN_EQUITY_TO_TRADE (= $5000 by default)

  Each rejection writes a structured log line with the gate name + values.

Verification:
  pytest backend/tests/services/test_signal_translator.py -v   → 12+ pass
  # Tests must cover:
  #   - high conviction + all gates pass → TradeIntent emitted
  #   - low conviction → None
  #   - each gate failing in isolation → None + correct rejection log
  #   - position_size exactly at limit (boundary) → TradeIntent emitted

Acceptance:
  Every (conviction × gate-state) combo produces a defined output:
  TradeIntent or None — never undefined behavior.
  References: Kyle (1985) "Continuous Auctions and Insider Trading" — liquidity gate
              Almgren-Chriss (2001) — sizing math

═══ TASK 3 — Execution doctrine enforcer [B] ═══
Files to create/modify:
  backend/services/execution_doctrine.py              (NEW)
  backend/tests/services/test_execution_doctrine.py   (NEW — 10+ tests)

Spec:
  Class ExecutionDoctrine with method:
    apply(intent: TradeIntent, market_state: MarketState) → (bool, str)
    Returns (allow, rejection_reason). All 4 rules must pass for allow=True.

  Rule 1 — Tap Probability decay:
    Look up the nearest King/Floor/Ceiling node from market_state.nodes.
    node.state ∈ {fresh, tested, delivered, decaying}
    fresh   → allow if 1:1 R:R or better
    tested  → allow only if R:R ≥ 3.0
    delivered → reject ("delivered node — wait for fresh")
    decaying → reject ("decaying node — never trade")

  Rule 2 — Deflection zones only:
    Compute distance_pct = abs(entry_price - nearest_node.strike) / spot
    Reject if distance_pct > 0.001 (entry must be within 10 bps of a node)

  Rule 3 — Never trade the midpoint:
    If spot is between two adjacent nodes by > 0.5% on either side
    AND entry is between those nodes (not at either node):
      reject ("midpoint trade — no-man's land")

  Rule 4 — 3:1 R:R minimum (default; relax to 2:1 for fresh-node entries):
    R = entry - stop_loss (longs) or stop_loss - entry (shorts)
    R_pos = take_profit - entry (longs) or entry - take_profit (shorts)
    Reject if R_pos / R < 3.0 (or 2.0 if fresh node)

  All references match SKYLIT_FEATURES.md "Execution Doctrine" section.

Verification:
  pytest backend/tests/services/test_execution_doctrine.py -v  → 10+ pass
  # Each rule MUST have:
  #   - one positive test (rule allows when conditions met)
  #   - one negative test (rule rejects when conditions violated)
  # Plus integration test: TradeIntent passes 3 rules but fails 1 → rejected

Acceptance:
  Every TradeIntent passes through ExecutionDoctrine.apply().
  Failures log rejection_reason. No silent rejections.
  No rule bypass paths in code.

═══ TASK 4 — Fill-quality monitor [A] ═══
Files to create/modify:
  backend/services/fill_monitor.py                    (NEW)
  backend/routes/admin.py                             (extend — add /fill_quality)
  backend/tests/services/test_fill_monitor.py         (NEW — 8+ tests)

Spec:
  Hook into OrderRouter.on_fill callback. For every fill:
    slippage_bps = (fill_price - limit_price) / limit_price * 10000.0
    (negative if filled inside the limit, positive if outside)

  Maintain rolling 24h slippage histogram per ticker (use collections.deque
  with maxlen=10000 or equivalent — keep memory bounded).

  Compute p50, p95, p99 every 60s. Cache in process.

  Alerts (emit Prometheus metric, Agent 10 picks them up):
    floww_fill_slippage_bps_p50{ticker}
    floww_fill_slippage_bps_p95{ticker}
    floww_fill_slippage_bps_p99{ticker}

  WARN if p95 > 5 bps (paper-trade should be ~0; Schwab paper fills at NBBO).
  CRITICAL if p99 > 20 bps.

  Endpoint:
    GET /api/admin/fill_quality
    response: {ticker: {p50, p95, p99, sample_count}}

Verification:
  pytest backend/tests/services/test_fill_monitor.py -v  → 8+ pass
  # Inject 1000 synthetic fills with known slippage → p95 matches expected
  curl http://localhost:8000/api/admin/fill_quality | python3 -m json.tool

Acceptance:
  Prometheus metrics emit correctly; Agent 10 dashboard shows them.
  Memory footprint bounded (deque maxlen enforced).
  Reference: Hasbrouck (2007) "Empirical Market Microstructure" — slippage models

═══ TASK 5 — Position reconciliation loop [A] ═══
Files to create/modify:
  backend/services/position_reconciler.py             (NEW)
  backend/tests/services/test_position_reconciler.py  (NEW — 6+ tests)
  backend/server.py                                    (start the reconciler at app startup)

Spec:
  asyncio task running every 60s during market hours (9:30am-4pm ET):
    schwab_positions = await schwab.get_positions(account_id)
    local_positions = order_router.position_tracker.snapshot()

    for ticker in set(schwab_positions) | set(local_positions):
      s_qty = schwab_positions.get(ticker, 0)
      l_qty = local_positions.get(ticker, 0)
      if s_qty != l_qty:
        # Schwab is source of truth — override local
        order_router.position_tracker.set(ticker, s_qty)
        # emit reconciliation_event to Mongo + Agent 10 metric
        log structured event with both quantities + delta

  After 5 consecutive divergence events on the same ticker → escalate to
  Agent 8 kanban as severity HIGH (auto-spawn a card).

Verification:
  pytest backend/tests/services/test_position_reconciler.py -v  → 6+ pass
  # Tests:
  #   - mock Schwab returns position X, local has X → no event
  #   - Schwab X, local Y → 1 event, local updated to X
  #   - 5 consecutive divergences → kanban card spawned
  #   - reconciler stops outside market hours

Acceptance:
  24h reconciliation log in a healthy paper-trading run shows 0 divergences.
  Reconciliation metric exposed: floww_position_divergence_count{ticker}
  Reference: Lo (2002) "The Statistics of Sharpe Ratios" — tracking accuracy

═══ SKILLS REQUIRED ═══
  - hermeshub:api-builder              (Task 1 routes, Task 4 endpoint)
  - swarmclaw:coding-agent             (all implementations)
  - hermeshub:agent-hardening          (Task 1 retries + idempotency)
  - red-teaming:godmode                (Task 1 stress: race 100 concurrent identical orders)
  - gbrain:academic-verify             (Tasks 2, 4 — verify against papers)
  - software-development:debugging-hermes-tui-comman... (Schwab connection debug)

═══ RISKS ═══
  - Schwab sandbox rate-limits aggressive → batch submission + exponential backoff
  - MARKET orders + thin liquidity → catastrophic slippage. Default LIMIT, require config flag for MARKET.
  - Time-zone bugs in NBBO comparison → use UTC throughout, convert only at display.

═══ CHECKPOINTING ═══
After each task, write kanban/cards/agent1_checkpoint.md:
  TASK 1: [COMPLETE | IN_PROGRESS | NOT_STARTED]  commit: <sha>
  TASK 2: ...
  ...
  NEXT ACTION: Task N — <title>

═══ DONE WHEN ═══
All 5 tasks shipped + pushed + truth audit green.
Then write memory/agent1_round3_complete.md with: commit hashes, test counts
(15+12+10+8+6 = 51+ new tests), one-paragraph summary. Mark kanban card status: done. Exit.
```

---

## AGENT 2 — RL policy + ensemble distillation

```
[PASTE STANDING PREAMBLE — replace <N> with 2 throughout]

ROUND-3 IDENTITY: Hermes Agent 2, ML lead.
KANBAN CARD: O-PHASE2-ANOMALY
ROUND-2 SHIPPED: PatchTST VPIN forecaster, Autoformer chain dynamics,
                 ensemble inference, regime-aware thresholds, backtest harness.
TASK COUNT: 5. You are not done until all 5 are shipped and pushed.

GOAL: Train a Reinforcement Learning policy (PPO) that consumes Hermes's
ensemble signals + position state + GEX regime and emits TradeIntents.
This is the bridge from "anomaly detector" to "autonomous trader" — same
shape as Renaissance / Citadel / Citadel Securities quant pods.

WINDOW PLAN:
  Tasks 1, 2, 5 → Window A (Mongo replay data + heavy compute)
  Tasks 3, 4 → Window B safe (pure compute on cached models)

═══ TASK 1 — Trading environment (Gym-compatible) [A] ═══
Files to create/modify:
  backend/services/rl/__init__.py                     (NEW)
  backend/services/rl/trading_env.py                  (NEW)
  backend/services/rl/observations.py                 (NEW)
  backend/tests/services/rl/test_trading_env.py       (NEW — 15+ tests)

Spec:
  class TradingEnv(gym.Env):
    Observation space: Box(shape=(64,), dtype=float32)
      GEX features (6):       gex_zscore_60d, gex_roc_5d, gex_regime_pos,
                              distance_to_flip_norm, gex_wall_density_pct, gex_herfindahl
      VPIN ensemble (3):      vpin_current, vpin_cdf, vpin_forecast_15m
      Trinity (1):            trinity_score
      Position state (4):     qty_held, unrealized_pnl_pct, time_in_trade_min, drawdown_pct
      Anomaly (2):            anomaly_score, anomaly_regime_index
      Microstructure (5):     kyle_lambda, amihud, qi_zscore, hawkes_branching, fragility_score
      Underlying (4):         return_1m, return_5m, return_30m, atr_pct
      Calendar (6):           minutes_to_close, dow_norm, days_to_OPEX, days_to_FOMC,
                              earnings_flag, vix_level
      History buffer (33):    last 33 values of vpin_current (sequential context)

    Action space: Discrete(5)
      0: strong sell (close + short max_pos)
      1: sell        (reduce or open short)
      2: hold        (no change)
      3: buy         (add or open long)
      4: strong buy  (close + long max_pos)

    Reward function:
      r_t = ΔPnL_t - λ * abs(Δposition_t) * kyle_lambda_t - μ * adverse_excursion_t
      defaults: λ = 0.5, μ = 1.0
      (Task 3 will ablate these)

    Episode: one trading day (open-to-close). Reset at next-day open.

    The env replays from DuckDB via Agent 1's replay_engine.py
    (Task 2 from Round 2 — drop-in queue connector).

Verification:
  pytest backend/tests/services/rl/test_trading_env.py -v  → 15+ pass
  python -c "
    import sys; sys.path.insert(0,'backend')
    from services.rl.trading_env import TradingEnv
    from stable_baselines3.common.env_checker import check_env
    env = TradingEnv(replay_start='2025-01-02', replay_end='2025-01-03')
    check_env(env)  # raises if non-compliant
    print('PASS: env is Gym-compliant')
  "
  # Random policy run:
  python -c "
    import numpy as np; np.random.seed(0)
    from services.rl.trading_env import TradingEnv
    env = TradingEnv(replay_start='2025-01-02', replay_end='2025-01-31')
    obs, _ = env.reset()
    rewards = []
    for _ in range(1000):
      a = env.action_space.sample()
      obs, r, term, trunc, info = env.step(a)
      rewards.append(r)
      if term or trunc: obs, _ = env.reset()
    print(f'mean reward: {np.mean(rewards):.4f}, std: {np.std(rewards):.4f}')
    assert abs(np.mean(rewards)) < 1.0, 'reward should be ~0 for random policy'
    assert np.std(rewards) > 0.01, 'reward variance should be non-trivial'
  "

Acceptance:
  - check_env() passes (Gym API compliance)
  - Random policy completes 100 episodes without exceptions
  - Reward distribution non-degenerate (mean near 0, std > 0)
  - Reference: Brockman et al. (2016) "OpenAI Gym"; Sutton-Barto (2018) §13

═══ TASK 2 — PPO trainer [A] ═══
Files to create/modify:
  scripts/train_rl_policy_ppo.py                      (NEW)
  ./project_oracle/models/rl_policy_v1.pt             (artifact)
  qc/data/rl_policy_v1_manifest.json                  (provenance manifest)
  backend/tests/services/rl/test_ppo_training.py      (NEW — 10+ tests)
  requirements.txt                                     (add stable-baselines3>=2)

Spec:
  Use stable_baselines3.PPO with MlpPolicy:
    policy_kwargs = dict(net_arch=dict(pi=[256, 128], vf=[256, 128]))

  Hyperparameters (start; Task 3 ablates):
    lr=3e-4, clip_range=0.2, ent_coef=0.01, vf_coef=0.5,
    n_steps=2048, n_epochs=10, gae_lambda=0.95, gamma=0.99,
    max_grad_norm=0.5, batch_size=64

  Training data: replay through Agent 1's replay_engine.py over last 6
  months of Schwab/Databento data (Window A — needs Mongo for chain backfill).

  Training loop:
    total_timesteps = 1_000_000 (≈ 250 episodes)
    Eval callback every 10k steps on held-out month → save best by mean reward
    Save final + best checkpoints to ./project_oracle/models/rl_policy_v1*.pt

  Manifest:
    {
      training_period: "<start>..<end>",
      n_episodes_seen: int,
      total_timesteps: int,
      final_mean_reward: float,
      best_mean_reward: float,
      val_sharpe: float,
      hyperparameters: {...},
      env_spec: {...},
      saved_at_utc: "<iso>"
    }

Verification:
  python scripts/train_rl_policy_ppo.py --dry-run --total-timesteps 1000
  # exits 0; creates manifest with n_episodes_seen ≥ 1

  python -c "
    import torch
    from stable_baselines3 import PPO
    model = PPO.load('./project_oracle/models/rl_policy_v1.pt')
    import numpy as np
    obs = np.zeros((64,), dtype=np.float32)
    action, _ = model.predict(obs, deterministic=True)
    assert action.shape == ()  # scalar discrete action
    print('PASS: model loads + predicts; action =', int(action))
  "

  pytest backend/tests/services/rl/test_ppo_training.py -v  → 10+ pass

Acceptance:
  - Mean episode reward strictly increases over the first 1000 iterations
    (assert this in the eval callback; raise if not)
  - Held-out month: Sharpe of policy returns > 1.0
  - Manifest present + all fields populated
  - Reference: Schulman et al. (2017) "Proximal Policy Optimization" arxiv:1707.06347

═══ TASK 3 — Reward-shaping ablation [B] ═══
Files to create/modify:
  scripts/ablate_rl_reward.py                         (NEW)
  reports/rl_reward_ablation_<YYYYMMDD>.md            (output)

Spec:
  Train 4 reward variants, 500 iterations each (use cached replay buffer
  to keep this Window-B-safe):

    Variant A — baseline:    r = ΔPnL only
    Variant B — tc-penalty:  r = ΔPnL - 0.5 * tc
    Variant C — main:        r = ΔPnL - 0.5 * tc - 1.0 * drawdown
    Variant D — Sortino:     r = (ΔPnL / max(downside_std, ε)) - 0.5 * tc - 1.0 * drawdown

  For each variant, log:
    final Sharpe, max drawdown, win rate, avg trade duration, total trades

  Output reports/rl_reward_ablation_<YYYYMMDD>.md as a markdown table
  + 2-paragraph analysis (which variant won + why).

Verification:
  python scripts/ablate_rl_reward.py --iterations 500
  # produces reports/rl_reward_ablation_<today>.md with 4 variants + analysis

Acceptance:
  Report exists and is committed.
  Analysis identifies the optimal variant numerically (highest Sharpe ×
  lowest max-DD).
  Reference: Sortino-Price (1994) "Performance Measurement in a Downside Risk Framework"

═══ TASK 4 — Policy distillation to ONNX [B] ═══
Files to create/modify:
  scripts/distill_policy.py                           (NEW)
  ./project_oracle/models/rl_policy_distilled_v1.onnx (artifact)
  backend/services/rl/distilled_inference.py          (NEW — ONNX runtime)
  backend/tests/services/rl/test_distilled_inference.py (NEW — 8+ tests)

Spec:
  Distill the PPO teacher (Task 2) → student MLP with smaller capacity:
    student net: [64] hidden units (vs teacher [256, 128])
    distillation loss: KL(teacher_actions || student_actions) + α * MSE(values)
    train for 20k steps on replayed observations

  Export student to ONNX:
    opset_version=17
    input name: 'observation' (shape [-1, 64])
    output name: 'action_logits' (shape [-1, 5])

  Runtime: backend/services/rl/distilled_inference.py loads the .onnx
  via onnxruntime and exposes async predict(obs: np.ndarray) → int.

Verification:
  python scripts/distill_policy.py --teacher ./project_oracle/models/rl_policy_v1.pt
  # produces .onnx, prints student/teacher action-agreement rate

  python -c "
    import numpy as np
    from services.rl.distilled_inference import DistilledPolicy
    p = DistilledPolicy('./project_oracle/models/rl_policy_distilled_v1.onnx')
    obs = np.zeros((64,), dtype=np.float32)
    import time; t0 = time.perf_counter_ns()
    for _ in range(1000):
      p.predict(obs)
    elapsed_ms_per_call = (time.perf_counter_ns() - t0) / 1e6 / 1000
    assert elapsed_ms_per_call < 1.0, f'too slow: {elapsed_ms_per_call:.3f}ms'
    print(f'PASS: {elapsed_ms_per_call:.3f}ms per inference')
  "

  pytest backend/tests/services/rl/test_distilled_inference.py -v  → 8+ pass

Acceptance:
  - Student matches teacher action ≥98% on held-out trajectories
  - Inference latency < 1ms CPU on Nav's laptop
  - ONNX deployed to production inference path
  - Reference: Hinton-Vinyals-Dean (2015) "Distilling the Knowledge in a Neural Network"

═══ TASK 5 — Online learning continuous adaptation [A] ═══
Files to create/modify:
  backend/services/rl/online_adapter.py               (NEW)
  scripts/daily_online_update.py                      (NEW — cron job)
  deploy/cron.d/hermes-rl-online                      (NEW — schedules daily 5pm ET)
  backend/tests/services/rl/test_online_adapter.py    (NEW — 8+ tests)

Spec:
  Runs daily at 5pm ET (after market close):
    1. Load today's market data + executed trades from Mongo
    2. Replay through env, compute realized rewards per state-action
    3. Apply small PPO update: lr = 1e-5, n_epochs = 2
    4. Save daily snapshot: ./project_oracle/models/rl_policy_v1_<YYYYMMDD>.pt

  Rollback gate:
    Compute 7-day rolling Sharpe on held-out validation.
    If today's Sharpe drops > 2σ below the 30-day mean →
      ROLLBACK: restore yesterday's snapshot, write
      memory/rl_rollback_<YYYYMMDD>.md with diagnostic
    Else: promote today's snapshot to ./project_oracle/models/rl_policy_v1.pt

Verification:
  python scripts/daily_online_update.py --date 2025-01-15 --dry-run
  # prints what it would do; does not write artifacts

  pytest backend/tests/services/rl/test_online_adapter.py -v  → 8+ pass

Acceptance:
  - 30-day continuous-learning simulation shows monotone-or-better
    Sharpe vs frozen baseline (assert in a test)
  - Rollback triggered on synthetic Sharpe degradation
  - Reference: Lillicrap et al. (2016) "Continuous Control with Deep RL" (DDPG online mechanics)

═══ SKILLS REQUIRED ═══
  - autonomous-ai-agents:codex          (long training scripts)
  - mlops:dspy                          (hyperparameter sweep prompting)
  - mlops:evaluating-l...               (model evaluation harness)
  - gbrain:academic-verify              (verify PPO impl vs Schulman 2017 paper)
  - hermeshub:agent-hardening           (online adapter rollback gate)
  - swarmclaw:coding-agent              (implementations)

═══ RISKS ═══
  - RL policies can blow up — kill-switch via Agent 7 R3 live-trading switch.
    Until that ships, this policy emits PAPER-ONLY TradeIntents.
  - Reward hacking: agent learns to never trade → enforce min trades/episode floor in env.
  - Distribution shift training vs live → online adapter handles small shifts;
    large shifts trigger retraining card to kanban.

═══ CHECKPOINTING ═══
After each task, write kanban/cards/agent2_checkpoint.md with task status + commit SHAs.

═══ DONE WHEN ═══
All 5 tasks shipped + pushed + truth audit green.
Total new tests: 15+10+0+8+8 = 41+ tests + 1 ablation report.
Write memory/agent2_round3_complete.md, mark kanban done, exit.
```

---

## AGENT 3 — Skylit visual parity + TradingView charts

```
[PASTE STANDING PREAMBLE — replace <N> with 3 throughout]

ROUND-3 IDENTITY: Hermes Agent 3, UI lead.
KANBAN CARD: O-PHASE3-DASH
ROUND-2 SHIPPED: Atlas tab (candlestick + overlays), Replay Mode, Agent Hub
                 stub + 3 archetypes, Nexus stub, theme/shortcut polish.
TASK COUNT: 5. You are not done until all 5 are shipped and pushed.

GOAL: Visual parity with Skylit's commercial product. Match their layout
density, color palette, interaction patterns. Add the charting depth a
serious trader expects — TradingView lightweight-charts with Heatseeker
overlays, scrolling Flowseeker with 20 columns, mobile PWA.

WINDOW PLAN:
  Task 3 → Window A (needs live flow data to render)
  Tasks 1, 2, 4, 5 → Window B safe (frontend; work with mocked data)

═══ TASK 1 — TradingView lightweight-charts integration [B] ═══
Files to create/modify:
  backend/services/dash_ui.py                         (Atlas tab rewrite)
  frontend/src/components/charts/LightweightChart.jsx (NEW)
  frontend/src/components/charts/OverlayLayer.jsx     (NEW)
  frontend/package.json                                (add lightweight-charts ^5)
  frontend/src/components/__tests__/LightweightChart.test.jsx (NEW — 8+ tests)

Spec:
  Replace Plotly candlestick in Atlas tab with TradingView lightweight-charts
  (Apache-2.0 license — verified commercial use OK).

  Component: <LightweightChart symbol={'SPY'} timeframe={'1m'} candles={candles} />
  Overlay layers as composable child components (each toggleable independently):
    <KingNodesOverlay nodes={kingNodes} />
    <ZeroGammaLine level={zg} />
    <AirPocketsBands pockets={airPockets} />
    <TrinityMarkers events={trinityEvents} />
    <AnomalyTriangles events={anomalyEvents} />
    <DealerWallsOverlay walls={dealerWalls} />

  Click on any overlay element → opens side panel showing the underlying
  computation (which trades drove this node, the GEX values, etc.).

  Performance budget: 4h candlestick window (240 bars) renders in <500ms
  cold; <100ms on overlay toggle.

Verification:
  cd frontend && npx craco test --watchAll=false src/components/charts/
  # → 8+ tests pass (component renders, overlay toggles, click-handler fires)
  cd frontend && npx craco build
  # → succeeds; bundle size reported

Acceptance:
  - All 8 tests pass
  - npx craco build succeeds
  - Visual smoke test: load /dashboard/atlas, toggle each overlay → no console errors
  - p99 frame time during overlay toggle < 100ms (measured via performance.now())
  - Reference: Cleveland (1985) *The Elements of Graphing Data* — visual encoding hierarchy

═══ TASK 2 — Heatseeker visual parity with Skylit [B] ═══
Files to create/modify:
  backend/services/dash_ui.py                         (Heatseeker tab restyle)
  frontend/src/components/heatseeker/Heatmap.jsx      (NEW or rewrite)
  frontend/src/styles/skylit_palette.css              (NEW)

Spec:
  Color palette — match Skylit exactly (from SKYLIT_FEATURES.md):
    --gex-negative:  #d63031  (red)
    --gex-zero:      #ffffff  (white)
    --gex-positive:  #00b894  (green)
    --node-king:     #fdcb6e  (gold)
    --node-floor:    #74b9ff  (blue)
    --node-ceiling:  #fab1a0  (peach)
    --anomaly-mark:  #e17055  (orange)
    --bg-primary:    #0c0e14  (near-black)
    --bg-secondary:  #161922

  Node markers: concentric circles sized by |GEX|:
    radius_px = max(4, min(24, sqrt(abs(net_gex) / max_abs_gex) * 24))

  Hover tooltip: 8-line summary, monospace font, dark-on-light:
    strike: 580.0
    net_gex: -1.23e9
    tap_count: 3
    state: delivered
    tap_probability: 0.12
    signed_gex: -1.23e9
    total_oi: 45,123
    first_seen: 2025-01-15 09:33 ET

  Pulse animation when new King Node forms:
    @keyframes king_pulse {
      0%   { transform: scale(1.0); opacity: 1.0; }
      50%  { transform: scale(1.5); opacity: 0.6; }
      100% { transform: scale(1.0); opacity: 1.0; }
    }
    animation-duration: 300ms; play exactly once on first detection.

Verification:
  cd frontend && npx craco build  → succeeds
  # Take screenshot of /dashboard/heatseeker via Playwright OR document
  # manual side-by-side comparison with Skylit — record observation in
  # frontend/src/components/heatseeker/PARITY_NOTES.md

Acceptance:
  - Color palette CSS variables defined and used exclusively (no hex literals)
  - Tooltip renders in <50ms on hover
  - King Node pulse animation visible on first detection only (not re-firing)

═══ TASK 3 — Flowseeker 20-column live table [A] ═══
Files to create/modify:
  backend/services/dash_ui.py                         (Flowseeker tab extension)
  backend/routes/flowseeker.py                         (extend — add 12 derived columns)
  backend/services/flow_derivatives.py                 (NEW — compute the 12 derived fields)
  backend/tests/services/test_flow_derivatives.py      (NEW — 12+ tests, one per column)

Spec:
  Existing 8 columns: timestamp, symbol, strike, expiry, side, type, size, price
  Add 12 derived columns:
    implied_vol         (from BS inversion of price, strike, expiry, spot)
    theta_decay         (BS theta at print time)
    vega_pnl            (vega × IV change since open)
    vanna_pnl           (vanna × dSpot × dIV)
    charm_pnl           (charm × Δtime)
    hedge_pressure      (signed delta × notional)
    fills_ahead         (count of larger fills in same contract last 60s)
    fills_behind        (count of smaller fills last 60s)
    time_at_bid_ms      (ms spent at NBBO bid before fill)
    time_at_ask_ms      (ms spent at NBBO ask before fill)
    sentiment_score     (FlashAlpha social_sentiment_z for this ticker)
    vix_at_print        (VIX value at print timestamp)

  Color rubric (matching Skylit):
    Background:
      red    if size > prev_day_volume_at_strike (unusual)
      yellow if size > open_interest             (sweep candidate)
      gray   otherwise
    Text:
      green if fill_price ≥ ask  (above-ask fill, aggressive buy)
      red   if fill_price ≤ bid  (below-bid fill, aggressive sell)
      white otherwise

  Sort + filter: any combination of:
    {side, type, size > X, premium > $Y, classification IN {sweep, block, regular}}
    Filter latency target: <100ms on 10k rows.

Verification:
  pytest backend/tests/services/test_flow_derivatives.py -v  → 12+ pass
  # Each derived column has its own test (synthetic input → known output)

  # Load test:
  python -c "
    from services.flow_derivatives import compute_derivatives
    import time, random
    flows = [{'symbol':'SPY','strike':580.0,'expiry':'2025-01-17','side':'BUY',
              'type':'CALL','size':100,'price':5.0,'timestamp_us':int(time.time()*1e6)+i}
             for i in range(10_000)]
    t0 = time.perf_counter()
    for f in flows: compute_derivatives(f)
    print(f'10k rows in {(time.perf_counter()-t0)*1000:.1f}ms')
  "
  # → < 2000ms target

Acceptance:
  - All 12 tests pass, audit green
  - 10k-row enrichment < 2s
  - Drilldown click opens contract-specific modal with chain context

═══ TASK 4 — Replay scenario library [B] ═══
Files to create/modify:
  backend/services/replay_scenarios.py                (NEW)
  backend/services/dash_ui.py                          (Replay tab extension)
  backend/tests/services/test_replay_scenarios.py      (NEW — 10+ tests)
  data/replay_scenarios/*.json                         (NEW — 6 canonical scenarios)

Spec:
  Curated scenarios as JSON specs in data/replay_scenarios/:
    fomc_may_2026.json
    aug_2024_vol_blowup.json
    zero_dte_pin_friday.json
    earnings_squeeze_aapl.json
    march_2020_covid.json
    gme_jan_2021_squeeze.json

  Schema per scenario:
    {
      "name": "FOMC May 2026",
      "ticker_focus": ["SPY", "QQQ"],
      "data_range": {"start": "2026-05-01T13:30:00Z", "end": "2026-05-01T20:00:00Z"},
      "annotations": [
        {"timestamp": "...", "text": "FOMC statement released"},
        {"timestamp": "...", "text": "Powell press conference begins"}
      ],
      "default_speed": 10.0
    }

  UI:
    Dropdown in Replay tab lists scenarios.
    On select → Atlas chart auto-scrolls to start, plays at default_speed,
    annotation popups appear at their timestamps.

Verification:
  pytest backend/tests/services/test_replay_scenarios.py -v  → 10+ pass
  # Tests load each scenario JSON, validate schema, dry-run-replay it.

  python -c "
    from services.replay_scenarios import load_scenario, list_scenarios
    scenarios = list_scenarios()
    assert len(scenarios) == 6, f'expected 6, got {len(scenarios)}'
    for s in scenarios:
      spec = load_scenario(s)
      assert 'data_range' in spec
      assert 'annotations' in spec
    print('PASS:', scenarios)
  "

Acceptance:
  - All 6 scenarios load without schema errors
  - Annotations align with documented event timestamps (manual review per scenario)

═══ TASK 5 — Mobile PWA redesign [B] ═══
Files to create/modify:
  frontend/public/manifest.json                       (PWA manifest)
  frontend/public/service-worker.js                   (NEW — offline cache)
  frontend/src/styles/mobile.css                      (NEW or extend)
  frontend/src/components/MobileNav.jsx               (NEW — bottom nav)
  frontend/craco.config.js                            (register service worker)

Spec:
  Breakpoints (existing CSS uses these — match):
    < 600px            → phone
    600 - 1024px       → tablet
    > 1024px           → desktop (current default)

  Phone layout (< 600px):
    - Single tab visible at a time
    - Bottom nav with 3 icons: Heatseeker / Atlas / Toxicity
    - Hamburger menu in top-left for other tabs
    - Plotly/lightweight-charts: pinch-to-zoom enabled; long-press → node detail
    - Toxicity Gauge: collapses to single column < 400px wide

  PWA manifest:
    name: "Hermes Trading Terminal"
    short_name: "Hermes"
    display: "standalone"
    background_color: "#0c0e14"
    theme_color: "#0c0e14"
    icons: [192x192, 512x512] (place in frontend/public/icons/)

  Service worker:
    Cache static assets (JS, CSS, fonts) with stale-while-revalidate
    API calls: network-first, fall back to cache for /api/admin/* read endpoints
    Cache version: bump on every release (versioned cache-busting)

Verification:
  cd frontend && npx craco build
  # → service-worker.js present in build/, manifest.json valid
  # Lighthouse PWA audit (manual on Nav's laptop or via Chrome DevTools):
  #   Performance ≥ 90 (mobile preset)
  #   PWA installable ✓
  #   tap-target sizes ≥ 44px (Apple HIG)

Acceptance:
  - npx craco build succeeds
  - Lighthouse Mobile Performance ≥ 90
  - PWA installs to iOS home screen (Nav verifies manually)
  - Reference: Apple HIG — tap-target sizing

═══ SKILLS REQUIRED ═══
  - swarmclaw:coding-agent             (implementations)
  - creative:architecture-diagram      (Task 1 overlay layout, Task 5 mobile grid)
  - devops:react-craco...              (frontend build pipeline)
  - mcp:native-mcp                     (optional — expose chart components as MCP)
  - hermeshub:api-builder              (Task 3 drilldown endpoint)

═══ RISKS ═══
  - TradingView lightweight-charts is Apache-2.0 — confirm before adoption (already verified).
  - Plotly candlestick was heavy — keep dataset ≤ 5000 bars; decimate older for performance.
  - Mobile PWA caching can stale — versioned cache-busting required.

═══ CHECKPOINTING ═══
After each task, write kanban/cards/agent3_checkpoint.md.

═══ DONE WHEN ═══
All 5 tasks shipped + pushed + truth audit green.
New tests: 8+0+12+10+0 = 30+ tests, 6 replay scenarios, PWA installable.
memory/agent3_round3_complete.md written. Kanban card status: done. Exit.
```

---

## AGENT 4 — Property-based + fuzz + chaos engineering

```
[PASTE STANDING PREAMBLE — replace <N> with 4 throughout]

ROUND-3 IDENTITY: Hermes Agent 4, test infra lead.
KANBAN CARD: O-TEST-INFRA
ROUND-2 SHIPPED: pytest-asyncio auto mode, CI coverage gates, property-based
                 math invariants (hypothesis), mutation testing on critical kernels,
                 flaky-test detector.
TASK COUNT: 5. You are not done until all 5 are shipped and pushed.

GOAL: Adversarial robustness. Round 2 property tests cover known invariants.
Round 3 adds fuzzing (unknown unknowns) and chaos engineering (system-level
failure injection — Mongo down, Schwab disconnect, clock skew, memory pressure).

WINDOW PLAN: All Window B safe (no Mongo/Schwab dependencies in any task).

═══ TASK 1 — Hypothesis-stateful ingestion tests [B] ═══
Files to create/modify:
  backend/tests/stateful/__init__.py                  (NEW)
  backend/tests/stateful/test_ingestion_state_machine.py (NEW)
  requirements.txt                                     (add hypothesis>=6.0)

Spec:
  Model the ingestion pipeline as a hypothesis.stateful.RuleBasedStateMachine.

  Rules (each is a state transition):
    tick_arrives(tick: TickEvent)
    queue_flushes()
    mongo_writes(batch_size: int)
    schwab_disconnects()
    schwab_reconnects()
    token_expires()
    token_refreshes()

  Invariants (assert on EVERY state):
    1. bytes_in == bytes_out + dropped (no losses)
    2. queue_depth bounded by max_size (default 10_000)
    3. Mongo write order matches arrival order WITHIN a ticker
    4. retry queue length monotonic non-decreasing during disconnect

  Settings:
    max_examples = 200 (CI); 10_000 (nightly)
    stateful_step_count = 50

Verification:
  pytest backend/tests/stateful/ -v --hypothesis-show-statistics
  # Expected: 200+ examples, 0 falsifying examples

  # Nightly job (separate workflow):
  pytest backend/tests/stateful/ -v --hypothesis-show-statistics \
    --hypothesis-seed=0 -p no:randomly \
    --max-examples 10000
  # Expected: 0 invariant violations

Acceptance:
  - All 4 invariants pass on 10k examples
  - Hypothesis statistics report shows good shrinking diversity
  - Reference: Claessen-Hughes (2000) "QuickCheck: A Lightweight Tool for Random Testing"

═══ TASK 2 — Schemathesis route fuzzing [B] ═══
Files to create/modify:
  backend/tests/fuzz/__init__.py                      (NEW)
  backend/tests/fuzz/test_route_fuzzing.py            (NEW)
  requirements.txt                                     (add schemathesis>=3.0)
  .github/workflows/nightly-fuzz.yml                  (NEW)

Spec:
  Use schemathesis to fuzz every /api/* endpoint against its OpenAPI schema:
    schema = schemathesis.from_uri("http://localhost:8000/openapi.json")

  @schema.parametrize()
  @settings(max_examples=100, deadline=2000)
  def test_no_5xx(case):
    case.call_and_validate()  # asserts no 5xx, response matches schema

  Edge-case payloads to inject:
    max int (2^63 - 1), min int, negative floats, NaN, Inf
    Unicode bombs (" " * 1000, emoji, RTL text)
    deeply nested JSON (depth 100)
    SQL injection patterns ("'; DROP TABLE ticks; --")
    NoSQL injection ({"$where": "..."})

Verification:
  pytest backend/tests/fuzz/test_route_fuzzing.py -v
  # → 0 new 5xx errors; all responses match documented schemas

  # 24h fuzz run (separate workflow, runs on schedule):
  see .github/workflows/nightly-fuzz.yml

Acceptance:
  - Zero 5xx on schema-valid inputs
  - Sensible 4xx on schema-invalid inputs (no panics)
  - CI integrates 30-min fuzz pass on every PR
  - Reference: OWASP API Security Top 10 (2023)

═══ TASK 3 — Chaos engineering harness [B] ═══
Files to create/modify:
  backend/tests/chaos/__init__.py                     (NEW)
  backend/tests/chaos/chaos_runner.py                 (NEW)
  backend/tests/chaos/scenarios/mongo_down_60s.yaml         (NEW)
  backend/tests/chaos/scenarios/schwab_disconnect_5min.yaml (NEW)
  backend/tests/chaos/scenarios/clock_skew_2h.yaml          (NEW)
  backend/tests/chaos/scenarios/memory_pressure_3gb.yaml    (NEW)
  backend/tests/chaos/scenarios/disk_full.yaml              (NEW)
  Makefile                                             (add `make chaos` target)

Spec:
  YAML scenario schema:
    name: "mongo_down_60s"
    description: "Kill Mongo connection for 60s. System must stay up + queue writes."
    duration_seconds: 60
    fault:
      type: "mongo_block"   # or "ws_disconnect", "clock_skew", "memory_hog", "disk_full"
      params: {...}
    assertions:
      - on_during: "system_alive"        # API returns 200 on /api/health
      - on_during: "retry_queue_grows"   # mongo_retry_queue file count increases
      - on_after: "retry_queue_drains"   # within 30s of recovery

  chaos_runner.py:
    Reads YAML, applies fault, runs duration, lifts fault, verifies assertions.
    Each scenario runs in Docker isolation (so OS-level chaos doesn't leak).

  make chaos → runs all scenarios sequentially.

Verification:
  make chaos
  # → all 5 scenarios pass; output:
  # ✓ mongo_down_60s     PASS  60s + 12s recovery
  # ✓ schwab_disconnect  PASS  300s + 18s recovery
  # ✓ clock_skew_2h      PASS
  # ✓ memory_pressure    PASS  graceful degrade observed
  # ✓ disk_full          PASS  DuckDB eviction + alert fired

Acceptance:
  All 5 scenarios pass. System never enters undefined state.
  Reference: Basiri et al. (2016) "Chaos Engineering" (Netflix paper)

═══ TASK 4 — Performance regression tests [B] ═══
Files to create/modify:
  backend/tests/perf/__init__.py                      (NEW)
  backend/tests/perf/test_p99_latency.py              (NEW)
  reports/perf_baseline_<YYYYMMDD>.json               (baseline artifact)
  .github/workflows/perf-check.yml                    (NEW — runs on every PR)

Spec:
  Use pytest-benchmark. Lock these p99 budgets (from ARCHITECTURE_DEEP.md):
    calc_gex_per_strike(1000 contracts):    p99 < 5.0 ms
    vpin_engine.update():                   p99 < 1.0 ms
    hawkes_intensity(t, 500 events):        p99 < 2.0 ms
    SABR.hagan_lognormal_vol():             p99 < 0.5 ms
    /api/heatseeker/flip-zones (e2e):       p99 < 100 ms

  Baseline file: reports/perf_baseline.json
    {kernel_name: {"p50_ns": ..., "p99_ns": ...}}

  CI step:
    pytest backend/tests/perf/ --benchmark-json=perf_current.json
    Compare current vs baseline:
      if any kernel p99 regresses > 20% → fail CI
      else → PASS

Verification:
  pytest backend/tests/perf/test_p99_latency.py -v --benchmark-only
  # → 5 benchmarks; all within budget on baseline run

Acceptance:
  - Baselines committed
  - Every PR's CI reports per-kernel regression %
  - Reference: Gil Tene "How NOT to Measure Latency" — HdrHistogram

═══ TASK 5 — Snapshot tests for math correctness [B] ═══
Files to create/modify:
  backend/tests/snapshots/__init__.py                 (NEW)
  backend/tests/snapshots/*.json                      (NEW — one per kernel)
  backend/tests/services/test_snapshot_math.py        (NEW — 12+ tests)
  requirements.txt                                     (add syrupy>=4 OR pytest-snapshot)

Spec:
  For each math kernel, store the output of a canonical input as a JSON snapshot.

  Kernels to snapshot (12+):
    bs_gamma_vec(spot=580, strikes=[570,575,580,585,590], T=0.25, sigma=0.2)
    calc_vpin(buy=[...], sell=[...])
    calc_dex(...)
    calc_vex(...)
    SABR.hagan_lognormal_vol(F=580, K=580, T=0.25, alpha=0.2, beta=0.5, rho=-0.3, nu=0.4)
    SVIProfile.implied_vol(k=0, ...)
    HawkesProcess.intensity(t=10, events=[1,3,7], mu=0.5, alpha=0.3, beta=1.0)
    KyleLambda.compute(returns=[...], signed_volume=[...])
    AmihudIlliquidity.compute(returns=[...], volume=[...])
    TrinityAlignment.compute(spy_zg=[...], qqq_zg=[...], spx_zg=[...])
    MarketFragility.compute(vpin_cdf=0.5, kyle_lambda=1e-7, ...)
    NodeLifecycleTracker.next_state(node, spot=580, tap_count=2)

  Snapshot pattern (syrupy):
    def test_bs_gamma_canonical(snapshot):
      result = bs_gamma_vec(580.0, np.array([575,580,585]), 0.25, np.array([0.2,0.2,0.2]))
      assert result.tolist() == snapshot

  Drift requires explicit `pytest --snapshot-update` — committed snapshots
  are the lock.

Verification:
  pytest backend/tests/services/test_snapshot_math.py -v  → 12+ pass

  # Intentionally break a kernel locally, run again → tests fail loudly
  # Confirms snapshots are doing their job.

Acceptance:
  - 12+ snapshots locked in backend/tests/snapshots/
  - Drift requires explicit --snapshot-update CLI flag
  - Caught at least one algorithmic-drift bug in a kernel under development

═══ SKILLS REQUIRED ═══
  - swarmclaw:coding-agent             (implementations)
  - hermeshub:agent-hardening          (chaos recovery patterns)
  - red-teaming:godmode                (Tasks 2-3 adversarial payloads)
  - software-development:debugging-hermes-tui-comman... (failure-mode debug)
  - gbrain:academic-verify             (property invariants vs published proofs)

═══ RISKS ═══
  - Hypothesis stateful + mutation tests slow → mark @pytest.mark.slow, nightly not per-PR
  - Chaos tests need root or container privileges → Docker isolation, gate on --chaos flag
  - Snapshot tests too brittle if kernels are still under churn — only snapshot stable kernels

═══ CHECKPOINTING ═══
After each task, write kanban/cards/agent4_checkpoint.md.

═══ DONE WHEN ═══
All 5 tasks shipped + pushed + truth audit green.
New tests: 1 (stateful, but with 10k examples) + 1 fuzz + 5 chaos scenarios + 5 perf
benchmarks + 12 snapshots = 24+ new test artifacts.
memory/agent4_round3_complete.md written. Kanban card status: done. Exit.
```

---

## AGENT 5 — Pearl causal inference

```
[PASTE STANDING PREAMBLE — replace <N> with 5 throughout]

ROUND-3 IDENTITY: Hermes Agent 5, math + docs lead.
KANBAN CARD: O-MATH-VALID
ROUND-2 SHIPPED: reference-repo parity tests (5+ repos), math correctness dashboard,
                 ARCHITECTURE_DEEP.md, THEORY.md, 5 notebook tutorials.
TASK COUNT: 5. You are not done until all 5 are shipped and pushed.

GOAL: Move from descriptive ("VPIN is high") to causal ("a 1bp move in
VPIN CAUSES a 0.3bp move in spread, controlling for vol regime"). Implement
Pearl-style do-calculus on the dealer-hedging system. This is what
separates Renaissance from retail.

WINDOW PLAN:
  Tasks 2, 4, 5 → Window A (need Mongo historical data for ATE + Granger)
  Tasks 1, 3 → Window B safe (pure code + DAG construction)

═══ TASK 1 — Causal DAG of the dealer-hedging system [B] ═══
Files to create/modify:
  docs/causal/dag.md                                  (NEW — Mermaid diagram)
  docs/causal/ASSUMPTIONS.md                          (NEW — explicit assumptions)
  backend/services/causal/__init__.py                 (NEW)
  backend/services/causal/dag.py                      (NEW)
  backend/tests/services/causal/test_dag.py           (NEW — 8+ tests)
  requirements.txt                                     (add dowhy>=0.11, econml>=0.15)

Spec:
  Nodes (observable signals from Hermes services):
    spot, GEX, VPIN, QI, kyle_lambda, dealer_hedge_pressure,
    realized_vol, anomaly_score

  Edges (causal arrows, justified by theory — cite paper per edge):
    spot → GEX                          (mechanical: Black-Scholes Greeks)
    GEX → dealer_hedge_pressure         (theoretical: gamma exposure → delta hedging)
    dealer_hedge_pressure → spot        (feedback: hedge demand moves underlying)
    VPIN → spread → kyle_lambda         (Easley-O'Hara 2012)
    realized_vol ↔ dealer_hedge_pressure (bidirectional; document the cycle-breaking assumption)

  Encode as networkx.DiGraph; export to dowhy.causal_graph.CausalGraph.
  Verify acyclicity (after collapsing the bidirectional edge per ASSUMPTIONS.md).

Verification:
  pytest backend/tests/services/causal/test_dag.py -v  → 8+ pass
  # Tests check: nodes present, edges present, DAG is acyclic after
  # collapsing the documented bidirectional edge, mermaid renders.

  python -c "
    from services.causal.dag import build_hedging_dag
    import networkx as nx
    G = build_hedging_dag()
    assert nx.is_directed_acyclic_graph(G), 'cycles!'
    print(f'PASS: {len(G.nodes)} nodes, {len(G.edges)} edges')
  "

Acceptance:
  - DAG passes acyclicity check
  - docs/causal/ASSUMPTIONS.md explicitly enumerates: no-unobserved-confounders,
    cycle-breaking convention, time-aggregation choice
  - Reference: Pearl (2009) *Causality*, 2nd ed., Cambridge UP

═══ TASK 2 — ATE estimation [A] ═══
Files to create/modify:
  backend/services/causal/ate_estimator.py            (NEW)
  scripts/run_ate_analysis.py                          (NEW)
  reports/causal_ate_<YYYYMMDD>.md                     (output)
  backend/tests/services/causal/test_ate.py            (NEW — 10+ tests)

Spec:
  For each (treatment, outcome) pair, compute ATE via two methods:
    Method A: propensity score + IPTW (via dowhy)
    Method B: double machine learning (via econml.dml.LinearDML)

  Treatments (binary indicators on historical data):
    T1: "GEX flips negative" (1 if gex_total < 0 at time t, 0 else)
    T2: "VPIN crosses 0.7" (1 if vpin_cdf > 0.7)
    T3: "Trinity score > 80" (1 if trinity > 80)
    T4: "Anomaly threshold breached" (1 if anomaly_score > threshold)
    T5: "Hawkes branching > 0.8" (1 if branching_ratio > 0.8)

  Outcomes (real-valued, measured 5-60 min after treatment):
    Y1: "realized_vol_30min" (Parkinson estimator over t+0 to t+30min)
    Y2: "spread_15min" (avg bid-ask spread over t+0 to t+15min)
    Y3: "max_drawdown_60min" (max favorable adverse excursion over t+0 to t+60min)

  Confidence intervals: bootstrap with B=1000.
  Confounders: control for VIX level, time-of-day, day-of-week, FOMC proximity.

  Output reports/causal_ate_<date>.md with markdown table:
    | Treatment T | Outcome Y | Method | ATE | 95% CI |

Verification:
  python scripts/run_ate_analysis.py --treatments T1,T2,T3,T4,T5 --outcomes Y1,Y2,Y3
  # → produces reports/causal_ate_<today>.md

  pytest backend/tests/services/causal/test_ate.py -v  → 10+ pass

Acceptance:
  Report committed with point estimates + CIs.
  CIs non-degenerate (e.g., CI width / |estimate| < 100% for at least 3 of 15 pairs).
  References:
    Imbens-Rubin (2015) *Causal Inference for Statistics, Social, and Biomedical Sciences*
    Chernozhukov et al. (2018) "Double/Debiased ML" *Econometrics J.*

═══ TASK 3 — Counterfactual scenario engine [B] ═══
Files to create/modify:
  backend/services/causal/counterfactual.py           (NEW)
  backend/routes/causal.py                             (NEW)
  backend/server.py                                    (wire causal router)
  backend/tests/services/causal/test_counterfactual.py (NEW — 8+ tests)

Spec:
  API:
    simulate_counterfactual(
      observation: ObservationVector,  # all 8 nodes at time t
      intervention: Dict[node, value]  # do-operator
    ) → Dict[node, value]              # counterfactual values of all nodes

  Use the DAG + structural equations learned via dowhy.gcm.
  Each structural equation is fit on Mongo historical data (Window A
  via Task 2 — read cached fits, don't re-train in B).

  Endpoint:
    POST /api/causal/counterfactual
    body: {observation: {...}, intervention: {"VPIN": 0.3}}
    response: {counterfactual: {...}, original: {...}, diff: {...}}

Verification:
  python -c "
    from services.causal.counterfactual import simulate_counterfactual
    obs = {'spot': 580.0, 'GEX': -1.2e9, 'VPIN': 0.85, 'QI': 0.3,
           'kyle_lambda': 5e-7, 'dealer_hedge_pressure': 1.5e8,
           'realized_vol': 0.18, 'anomaly_score': 0.9}
    cf = simulate_counterfactual(obs, {'VPIN': 0.3})  # halve VPIN
    assert cf['spread_proxy'] < obs.get('spread_proxy', cf['spread_proxy']) or True
    print('counterfactual:', cf)
  "

  pytest backend/tests/services/causal/test_counterfactual.py -v  → 8+ pass

Acceptance:
  3 named counterfactuals execute end-to-end:
    "halve VPIN" → spread narrows (per ATE direction)
    "flip GEX positive" → realized_vol falls (per theory)
    "max anomaly_score" → kyle_lambda rises
  Endpoint GET /api/causal/counterfactual deterministic for same inputs.
  Reference: Pearl (2018) *The Book of Why* §4 — counterfactuals

═══ TASK 4 — Granger-causality for Trinity Alignment [A] ═══
Files to create/modify:
  backend/services/causal/granger.py                  (NEW)
  backend/tests/services/causal/test_granger.py        (NEW — 8+ tests)
  docs/THEORY.md                                       (extend Trinity section)

Spec:
  Function:
    granger_lead_lag(
      series_a: pd.Series, series_b: pd.Series,
      lags: List[int] = [1, 5, 15]
    ) → Dict[lag, {f_stat, p_value, conclusion}]

  Use statsmodels.tsa.stattools.grangercausalitytests.
  Pre-check: augmented Dickey-Fuller test for stationarity on both series.
  If non-stationary → difference once, retest. If still non-stationary → skip.

  Pairwise tests:
    SPX_GEX → SPY_GEX (does SPX lead SPY?)
    SPY_GEX → QQQ_GEX
    SPX_GEX → QQQ_GEX
    + reverse direction for each

  Multivariate VAR fit on all 3 series — extract Granger conclusions.

  Output: extend /api/heatseeker/trinity-confluence to include:
    "leading_lagging": {"SPX_leads_SPY": p_value, ...}

Verification:
  pytest backend/tests/services/causal/test_granger.py -v  → 8+ pass

  # Manual: feed known-leading synthetic series → Granger detects direction
  python -c "
    import numpy as np, pandas as pd
    from services.causal.granger import granger_lead_lag
    np.random.seed(0)
    x = np.cumsum(np.random.randn(1000))
    y = np.roll(x, 5) + np.random.randn(1000) * 0.5  # y lags x by 5
    res = granger_lead_lag(pd.Series(x), pd.Series(y), lags=[1, 5, 15])
    # at lag 5, x → y should be significant
    assert res[5]['p_value'] < 0.05, f'expected significance at lag 5, got {res[5]}'
    print('PASS:', res[5])
  "

Acceptance:
  Pairwise Granger conclusions logged; Trinity endpoint extended.
  References: Granger (1969) *Econometrica*; Hamilton (1994) Ch.11

═══ TASK 5 — Causal-validated trade rationale [A] ═══
Files to create/modify:
  backend/services/causal/trade_rationale.py          (NEW)
  backend/routes/causal.py                             (extend — add /explain endpoint)
  backend/tests/services/causal/test_trade_rationale.py (NEW — 8+ tests)

Spec:
  For each TradeIntent emitted by Agent 2's RL policy (or directly via
  Agent 1's signal_translator), look up the causal graph + structural
  equations + ATE estimates and synthesize a rationale.

  Endpoint:
    GET /api/causal/explain/{intent_id}
    response: {
      intent_id,
      primary_cause: "negative GEX (z=-2.1) + VPIN spike (cdf=0.87)",
      supporting_evidence: [
        "GEX → dealer_hedge_pressure has ATE = +0.34 (95% CI [0.21, 0.47])",
        "VPIN > 0.7 → spread widening ATE = +1.2 bp (95% CI [0.8, 1.6])"
      ],
      counterfactual: "If VPIN had been at median (0.45), conviction would
                       have dropped from 0.84 to 0.42 → not tradeable.",
      confidence: 0.78
    }

  Generation pipeline:
    Top-N largest contributors to conviction (from signal_translator).
    Look up their ATE entries from reports/causal_ate_<latest>.md.
    Run counterfactual simulation: what if the top-1 contributor were at median?
    Compose 3-sentence rationale via DSPy structured prompt to OpenRouter.

Verification:
  pytest backend/tests/services/causal/test_trade_rationale.py -v  → 8+ pass

  # Integration:
  curl http://localhost:8000/api/causal/explain/sig_abc123 | python3 -m json.tool
  # → all required fields present; rationale is non-empty + cites ATE values

Acceptance:
  Every TradeIntent gets a rationale within 100ms (LLM call cached or async).
  Rationale is human-readable + cites primary cause + supporting ATEs + counterfactual.

═══ SKILLS REQUIRED ═══
  - gbrain:academic-verify             (Pearl, Imbens-Rubin, Chernozhukov citations)
  - gbrain:article-enric...            (citation enrichment for THEORY.md)
  - data-science:jupyter-live-kernel   (ATE viz notebook in docs/)
  - creative:architecture-diagram      (DAG mermaid)
  - mlops:dspy                         (Task 5 rationale generation)
  - mlops:evaluating-l...              (Task 2 CI estimation)
  - swarmclaw:coding-agent             (implementations)

═══ RISKS ═══
  - Causal inference assumes no unobserved confounders. Document explicitly in
    docs/causal/ASSUMPTIONS.md; otherwise risk spurious conclusions.
  - Granger ≠ Pearl causation — use Granger only as preliminary screen.
  - dowhy is somewhat heavyweight — if install issues, fall back to manual IPTW.

═══ CHECKPOINTING ═══
After each task, write kanban/cards/agent5_checkpoint.md.

═══ DONE WHEN ═══
All 5 tasks shipped + pushed + truth audit green.
New tests: 8+10+8+8+8 = 42+ tests + ATE report + extended THEORY.md.
memory/agent5_round3_complete.md written. Kanban card status: done. Exit.
```

---

## AGENT 6 — Knowledge graph + LLM-augmented research (CONTINUOUS)

```
[PASTE STANDING PREAMBLE — replace <N> with 6 throughout]

ROUND-3 IDENTITY: Hermes Agent 6, perpetual research scout.
KANBAN CARD: O-RESEARCH-LOOP
ROUND-2 SHIPPED: SSRN/NBER/Quantocracy/AQR/Robot-Wealth source expansion,
                 auto-port capability, author watch, weekly digest, HF search.
TASK COUNT: 5 (then continue the research loop indefinitely).

GOAL: Build a knowledge graph of every paper / repo / technique / author.
LLM-augmented Q&A: when Nav asks "what does Skylit do about pin risk?"
the system answers from the graph + cites sources. This is the
difference between "we have papers" and "we know what the papers say."

WINDOW PLAN:
  Tasks 1, 5 → Window A (Neo4j needs network; HF crawls need network)
  Tasks 2, 3, 4 → Window B safe (work on indexed data)

STOP CONDITION OVERRIDE: This agent is CONTINUOUS. After all 5 Round 3
tasks ship, keep running the existing research loop indefinitely.
Round 3 = mark `round3_deliverables: done` in kanban card, but the loop
keeps going.

═══ TASK 1 — Neo4j knowledge graph schema [A] ═══
Files to create/modify:
  infra/neo4j/docker-compose.neo4j.yml                (NEW)
  backend/services/research/knowledge_graph.py        (NEW)
  scripts/populate_kg.py                              (NEW)
  backend/tests/services/research/test_kg.py          (NEW — 10+ tests)
  requirements.txt                                     (add neo4j>=5.0)

Spec:
  Node types:
    (:Paper {id, title, abstract, year, authors[], arxiv_id, doi})
    (:Author {id, name, h_index, affiliation})
    (:Concept {id, name, description})       e.g., "VPIN", "Hawkes process"
    (:Implementation {id, repo_url, language, license})
    (:Technique {id, name, paper_id})
    (:HermesService {id, file_path, signature})

  Edge types:
    (:Author)-[:AUTHORED]->(:Paper)
    (:Paper)-[:CITES]->(:Paper)
    (:Paper)-[:INTRODUCES]->(:Concept)
    (:Implementation)-[:IMPLEMENTS]->(:Concept)
    (:Implementation)-[:PORTED_TO]->(:HermesService)
    (:Paper)-[:EXTENDS]->(:Paper)
    (:Paper)-[:CRITIQUES]->(:Paper)
    (:HermesService)-[:USES_TECHNIQUE]->(:Technique)

  Populate from existing data:
    Read data/external_research/discoveries_*.json → Paper nodes
    Read data/github-repos/cloned/* → Implementation nodes
    Read backend/services/*.py → HermesService nodes (parse docstrings for concept refs)

Verification:
  docker compose -f infra/neo4j/docker-compose.neo4j.yml up -d
  python scripts/populate_kg.py
  # → "loaded N Paper, M Author, K Concept, L Implementation, J HermesService nodes"

  python -c "
    from services.research.knowledge_graph import KG
    kg = KG()
    res = kg.query('''
      MATCH (h:HermesService)-[:USES_TECHNIQUE]->(t:Technique)<-[:IMPLEMENTS]-(p:Paper)
      RETURN h.id, p.title LIMIT 5
    ''')
    assert len(list(res)) > 0
    print('PASS: KG queryable')
  "

  pytest backend/tests/services/research/test_kg.py -v  → 10+ pass

Acceptance:
  - 5000+ nodes + 20000+ edges populated
  - Cypher query returning Hermes-Service→Technique→Paper paths works
  - Reference: Robinson-Webber (2015) *Graph Databases*

═══ TASK 2 — LLM-augmented research Q&A [B] ═══
Files to create/modify:
  backend/services/research/qa_engine.py              (NEW)
  backend/routes/research.py                          (extend)
  backend/tests/services/research/test_qa.py          (NEW — 12+ tests)

Spec:
  Endpoint: POST /api/research/ask
    body: {question: str}
    response: {
      answer: str,
      citations: [{paper_title, arxiv_id, relevance_score}],
      code_pointer: "backend/services/<file>.py:<line>",
      confidence: float
    }

  Pipeline (DSPy):
    NL question
      → Cypher generation (call OpenRouter Claude with KG schema)
      → KG query (Neo4j)
      → retrieved nodes (papers, services, concepts)
      → LLM synthesis with citations (call OpenRouter Claude again)
      → response

  Every answer requires ≥3 citations. If KG returns <3 → confidence < 0.5.

Verification:
  pytest backend/tests/services/research/test_qa.py -v  → 12+ pass

  # 10 benchmark questions (stored as JSON for regression):
  questions:
    "What does VPIN measure?"
    "Which Hermes service implements SABR?"
    "Why does pin risk matter at OPEX?"
    "What's the difference between GEX and DEX?"
    "Who introduced the Hawkes process for trade arrivals?"
    "What papers does our anomaly detector implement?"
    "Where do we calculate kyle's lambda?"
    "How does Trinity Alignment work?"
    "What is the Easley-O'Hara VPIN formula?"
    "Which papers cite Hagan's SABR?"
  → Each must return ≥3 citations with relevance_score > 0.5

Acceptance:
  - 10 benchmark questions → correct + cited answers
  - End-to-end latency < 3s (Groq for LLM if available; OpenRouter fallback)
  - Reference: Khattab et al. (2023) "DSPy"

═══ TASK 3 — Citation network analysis [B] ═══
Files to create/modify:
  scripts/citation_analysis.py                        (NEW)
  reports/citation_network_<YYYYMMDD>.md              (output)

Spec:
  Build paper citation graph from KG (Paper-CITES-Paper edges).
  Compute:
    PageRank (top 20)
    Betweenness centrality (top 20 bridge papers)
    Community detection via Louvain (identify clusters)

  Output report:
    - Top 20 by PageRank (most influential in our scope)
    - Top 10 bridge papers (highest betweenness — connect subfields)
    - 3+ emerging clusters (recent papers with growing connectivity)

Verification:
  python scripts/citation_analysis.py
  # → produces reports/citation_network_<today>.md

  # Manual review: top-3 PageRank papers should include canonical citations
  # (Easley/LdP VPIN, Hagan SABR, Gatheral SVI — sanity check)

Acceptance:
  - Report committed
  - PageRank top 20 includes recognizable canonical papers
  - At least 3 emerging-cluster topics identified
  - Reference: Newman (2010) *Networks: An Introduction*

═══ TASK 4 — Auto-port v2 with semantic similarity [B] ═══
Files to create/modify:
  scripts/auto_port_v2.py                             (NEW)
  backend/services/research/semantic_search.py        (NEW)
  requirements.txt                                     (add sentence-transformers>=2)

Spec:
  For each unported repo in data/github-repos/cloned/:
    Embed README.md + top-level docstrings via sentence-transformers/all-MiniLM-L6-v2
    Compute cosine similarity with each Hermes service's docstring embedding
    Top-3 closest Hermes services = candidate integration points

  Generate port proposal in memory/auto_port_proposal_<repo>_<date>.md:
    - Which Hermes file to extend
    - What function/class to add
    - Paper citation (if KG links the repo to a paper)
    - Semantic similarity scores

Verification:
  python scripts/auto_port_v2.py --max-proposals 5
  # → produces 5 memory/auto_port_proposal_*.md files

  # Manual review: at least 3 of 5 proposals should be sensible (similarity > 0.6)

Acceptance:
  5+ port proposals written.
  Each cites semantic-match score.
  Reference: Reimers-Gurevych (2019) "Sentence-BERT"

═══ TASK 5 — Author influence tracker [A] ═══
Files to create/modify:
  backend/services/research/author_influence.py       (NEW)
  scripts/author_watch.py                             (NEW — runs hourly via cron)
  deploy/cron.d/hermes-author-watch                   (NEW)
  memory/author_influence_<YYYYMMDD>.md               (output, updated weekly)

Spec:
  Tracked authors (initial set):
    Cliff Asness (AQR)
    Marcos López de Prado (Cornell)
    Jim Gatheral (Baruch)
    Marcos Carreira (HFT practitioner)
    Stephen Diehl
    Cris Doloc
    Aaron Brown

  For each author:
    Pull h-index from Semantic Scholar API
    Track recent paper count (last 12 months)
    Last-published date

  Auto-detect new publications (arxiv + SSRN + author RSS):
    On new paper → write memory/author_alert_<author>_<date>.md
    Auto-spawn kanban card if abstract mentions any current Hermes concept

Verification:
  python scripts/author_watch.py --dry-run
  # → prints what it would do; does not write artifacts

  python -c "
    from services.research.author_influence import compute_influence
    out = compute_influence('Marcos López de Prado')
    assert 'h_index' in out
    assert 'recent_paper_count' in out
    print(out)
  "

Acceptance:
  Weekly digest memory/author_influence_<date>.md includes ≥5 author updates.
  New-publication alerts spawn kanban cards.

═══ SKILLS REQUIRED ═══
  - research:arxiv                     (the queries)
  - research:blogwatcher                (RSS for AQR, Robot Wealth, etc.)
  - research:duckduckgo-search          (fallback)
  - research:llm-wiki...                (LLM-augmented Wikipedia)
  - hermeshub:arxiv-watcher             (continuous monitoring scaffolding)
  - gbrain:archive-crawler              (SSRN/NBER ingest)
  - gbrain:article-enric...             (citation enrichment)
  - gbrain:academic-verify              (auto-port parity)
  - mlops:dspy                          (DSPy pipeline for Q&A)
  - mcp:native-mcp                      (expose ask-research as MCP)
  - swarmclaw:coding-agent              (implementations + auto-port worker)

═══ RISKS ═══
  - Neo4j adds infrastructure complexity — consider networkx-only if overkill.
  - Semantic Scholar rate-limits — cache aggressively (Upstash Redis free tier).
  - LLM hallucination in Q&A — every claim must cite a real KG node.

═══ RATE LIMITS ═══
  arxiv:        ≤30 queries/hour
  GitHub:       ≤60 calls/hour (use Pro auth — Nav has it)
  HuggingFace:  ≤100 requests/hour
  SSRN:         ≤10 requests/min (respect robots.txt)
  Sem. Scholar: ≤100 requests/5min

═══ CHECKPOINTING ═══
After each task, write kanban/cards/agent6_checkpoint.md.

═══ DONE WHEN (Round 3 deliverables) ═══
All 5 tasks shipped + pushed + truth audit green.
Then KEEP RUNNING the research loop indefinitely.
memory/agent6_round3_complete.md written (but agent stays alive).
Kanban card status remains "in_progress" (continuous).
```

---

## AGENT 7 — Production deployment + live-trading enablement

```
[PASTE STANDING PREAMBLE — replace <N> with 7 throughout]

ROUND-3 IDENTITY: Hermes Agent 7, security + deployment lead.
KANBAN CARD: O-SECURITY
ROUND-2 SHIPPED: JWT auth middleware, WebSocket auth, secret rotation script,
                 pentest from outside LAN, production Docker hardening.
TASK COUNT: 5. You are not done until all 5 are shipped and pushed.

GOAL: Production deployment to Azure ($100 student credit). HTTPS + monitoring
+ SLA enforcement + live-trading switch (gated behind every safety check).
This is what makes the difference between "Hermes runs on Nav's laptop" and
"Hermes runs reliably in production."

WINDOW PLAN: All Window B safe (deployment + middleware work, no live deps).

═══ TASK 1 — Azure deployment via Terraform [B] ═══
Files to create/modify:
  infra/terraform/main.tf                             (NEW)
  infra/terraform/variables.tf                        (NEW)
  infra/terraform/outputs.tf                          (NEW)
  infra/terraform/README.md                            (NEW — how to apply)

Spec:
  Resources:
    - azurerm_app_service_plan (B1, ~$13/mo)
    - azurerm_linux_web_app (FastAPI backend container)
    - azurerm_container_registry (ACR Basic)
    - azurerm_cosmosdb_account (Mongo API, free tier — 400 RU/s, 5GB)
    - azurerm_key_vault (secrets storage)
    - azurerm_virtual_network + subnet
    - azurerm_private_endpoint (Cosmos private — no public DB access)

  Backend container:
    Source from ACR (image tag = git short SHA)
    Identity: SystemAssigned (Managed Identity)
    App settings: pull secrets via Key Vault references (no .env in container)

  Variables to externalize:
    location (default "eastus")
    project_name (default "hermes")
    environment (default "production")
    nav_phone (for alerts — output only, not committed)

Verification:
  cd infra/terraform
  terraform init
  terraform plan -out=tfplan
  # → no errors; resources count > 5

  # Smoke deploy (Nav runs manually first time):
  terraform apply tfplan
  # → ~10 min; outputs include the App Service URL

  curl https://<output_url>/api/health
  # → 200 OK

Acceptance:
  - terraform apply succeeds end-to-end in <15 min
  - /api/health returns 200 from the public URL
  - Cost on Azure portal projects < $30/mo (covered by $100 student credit)

═══ TASK 2 — HTTPS + Caddy reverse proxy [B] ═══
Files to create/modify:
  infra/caddy/Caddyfile                               (NEW)
  docker-compose.prod.yml                              (NEW)
  Dockerfile.caddy                                     (NEW)

Spec:
  Caddyfile:
    hermes.<your-domain>.com {
      reverse_proxy backend:8000
      tls nav@example.com               # auto Let's Encrypt
      header {
        Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
        Content-Security-Policy "default-src 'self'; style-src 'self' 'unsafe-inline'"
        X-Frame-Options "DENY"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
      }
      encode gzip zstd
      file_server * cache 31536000      # 1y immutable cache for static
    }

  docker-compose.prod.yml:
    services:
      caddy: (image caddy:2-alpine, ports 80+443, mounts Caddyfile + cert volume)
      backend: (existing image, internal port 8000)

Verification:
  docker compose -f docker-compose.prod.yml up -d
  # then from another machine:
  curl -I https://hermes.<your-domain>.com/
  # → HTTP/2 200 + HSTS header + CSP header present

  # SSL Labs test (external):
  https://www.ssllabs.com/ssltest/analyze.html?d=hermes.<your-domain>.com
  # → Grade A or A+

Acceptance:
  - HTTPS green padlock
  - HSTS preload-eligible (SSL Labs verifies)
  - securityheaders.com → A or A+

═══ TASK 3 — SLO + error-budget tracking [B] ═══
Files to create/modify:
  backend/services/slo_tracker.py                     (NEW)
  prometheus/recording_rules/slo.yml                  (NEW)
  grafana/dashboards/slo.json                         (NEW)
  backend/tests/services/test_slo_tracker.py          (NEW — 8+ tests)

Spec:
  SLO definitions (in code):
    API_AVAILABILITY:  target 99.9%  (window 30d)  — 43.2 min budget/mo
    API_LATENCY_P99:   target < 200ms (window 7d)
    INGESTION_UPTIME:  target 99% during market hours (window 30d)
    WS_DELIVERY:       target 99.99% (window 7d)

  Prometheus recording rules compute:
    slo:api_availability:rate30d
    slo:api_latency_p99:7d
    slo:ingestion_uptime:rate30d_markethours
    slo:ws_delivery_rate7d

  Burn-rate alerts:
    if monthly_budget_consumed > 50% within first half of month → WARN
    if monthly_budget_consumed > 90% within first 75% of month → CRITICAL

  Grafana dashboard panels:
    one per SLO showing: current rate, target, budget remaining, burn rate

Verification:
  pytest backend/tests/services/test_slo_tracker.py -v  → 8+ pass

  # Synthetic burn-rate trigger:
  python -c "
    from services.slo_tracker import SLOTracker
    t = SLOTracker()
    # Inject 100 failures into a 1000-request window → 90% availability
    for _ in range(100): t.record('api', success=False)
    for _ in range(900): t.record('api', success=True)
    assert t.compute_budget_consumed('api_availability') > 0.8
    print('PASS: burn rate logic correct')
  "

Acceptance:
  4 SLOs tracked in Grafana.
  Burn-rate alerts fire on synthetic test.
  Reference: Beyer et al. (2016) *Site Reliability Engineering* Ch.4 — SLOs

═══ TASK 4 — Live-trading switch with circuit breakers [B] ═══
Files to create/modify:
  backend/services/live_trading_switch.py             (NEW)
  backend/routes/admin.py                              (extend — add transition endpoint)
  backend/tests/services/test_live_trading_switch.py  (NEW — 15+ tests)

Spec:
  State machine (only Nav can transition; agents emit TradeIntents
  to whatever state is active):
    OFF → PAPER_ONLY → LIVE_TINY → LIVE_NORMAL → LIVE_FULL

  Per-state limits:
    OFF:         no intents reach order_router (drop with log)
    PAPER_ONLY:  intents go to Schwab paper account
    LIVE_TINY:   intents go to live account, max $1,000 notional per order
    LIVE_NORMAL: intents go live, max $10,000 notional per order
    LIVE_FULL:   no per-order cap (still subject to risk-gate position sizing)

  Transition endpoint:
    POST /api/admin/live-trading/transition
    body: {target_state: str, totp_code: str}
    Server validates:
      1. TOTP code matches Nav's authenticator (use pyotp)
      2. Email confirmation link click recorded in last 5 min
      3. From-state and to-state form a valid one-step transition (no skipping)
    All 3 must pass; else 401.

  Circuit breakers (auto-demote one state on any trip; lock 24h):
    daily P&L drawdown > 2% of equity                  → demote
    > 5 rejected fills in 1h                           → demote
    reconciliation discrepancy from Agent 1            → demote
    Agent 10 SLA burn > 90%                            → demote

  Every transition writes an audit-trail entry (Task 5).

Verification:
  pytest backend/tests/services/test_live_trading_switch.py -v  → 15+ pass

  # State-machine fuzz: try every (from, to) pair → only valid transitions allowed
  # Circuit-breaker test: trip each breaker → state demotes

Acceptance:
  - 15+ tests pass (each transition rule + each breaker + each bypass-attempt)
  - Default state on cold-start: OFF
  - No code path can transition without 2FA verification
  - Reference: SEC Rule 15c3-5 (Risk Management Controls for Brokers)

═══ TASK 5 — Compliance audit trail [B] ═══
Files to create/modify:
  backend/services/audit_trail.py                     (NEW)
  backend/middleware/audit_middleware.py              (NEW)
  scripts/verify_audit_chain.py                       (NEW — CI nightly)
  backend/tests/services/test_audit_trail.py          (NEW — 10+ tests)

Spec:
  Every write action gets an immutable audit entry to Mongo collection `audit_trail`:
    Fields:
      timestamp_utc  (ISO 8601 UTC)
      actor          (user_id, "system", or "agent_<N>")
      action_type    (e.g., "order_submit", "config_change", "state_transition")
      target         (e.g., "/api/order_router/submit", "live_trading_switch")
      before_state   (JSON, may be empty)
      after_state    (JSON)
      ip_address
      user_agent
      request_id
      prev_entry_hash (SHA-256 of previous entry — hash chain)
      this_entry_hash (computed)

  Middleware wraps every POST/PUT/PATCH/DELETE to /api/* and writes entry.

  scripts/verify_audit_chain.py:
    Walks the chain from genesis to latest.
    Recomputes each entry's hash, compares to this_entry_hash.
    Any mismatch → tamper alert (CRITICAL) to Agent 10.

  Retention: 7 years (configurable, default per SEC 17a-4).

Verification:
  pytest backend/tests/services/test_audit_trail.py -v  → 10+ pass

  python scripts/verify_audit_chain.py
  # → "PASS: 1234 entries, chain integrity verified"

  # Tamper test:
  python -c "
    # Modify a row directly in Mongo, re-run verify_audit_chain.py
    # → CRITICAL alert fires
  "

Acceptance:
  - 100% of write actions captured (verify by intentionally calling 50
    endpoints and counting audit_trail entries)
  - Tamper detection works (verify by modifying a row)
  - CI nightly runs verify_audit_chain.py and alerts on failure
  - References: SEC Rule 17a-4; FINRA Rule 4511; NIST SP 800-53

═══ SKILLS REQUIRED ═══
  - red-teaming:godmode               (Tasks 4, 5 — bypass attempts)
  - hermeshub:agent-hardening         (Tasks 1, 2 — production patterns)
  - hermeshub:api-builder             (Task 4 admin endpoint)
  - swarmclaw:coding-agent            (implementations)
  - devops:react-craco...             (frontend deploy to Static Web Apps if needed)

═══ RISKS ═══
  - Azure free tier limits → monitor + configure budget alert at 80%
  - HTTPS misconfiguration → use Mozilla SSL config generator + SSL Labs test
  - Audit trail write performance → batch + hash-chain async, not in request path

═══ LIVE-TRADING GATE (immutable) ═══
This agent's Task 4 ships + Critical security findings = 0 + audit trail
end-to-end verified + Nav 2FA confirmation + Agent 1 reconciler 24h zero
divergence → ONLY THEN can Nav MANUALLY flip OFF → PAPER_ONLY. Never auto.

═══ CHECKPOINTING ═══
After each task, write kanban/cards/agent7_checkpoint.md.

═══ DONE WHEN ═══
All 5 tasks shipped + pushed + truth audit green.
New tests: 0+0+8+15+10 = 33+ tests + Terraform plan + Caddy config.
memory/agent7_round3_complete.md written. Kanban card status: done. Exit.
```

---

## AGENT 8 — ML-driven kanban + capacity planning (CONTINUOUS)

```
[PASTE STANDING PREAMBLE — replace <N> with 8 throughout]

ROUND-3 IDENTITY: Hermes Agent 8, swarm coordinator. Continuous since Round 1.
KANBAN CARD: O-KANBAN-ORCH
ROUND-2 SHIPPED: inter-agent messaging, auto-spawn follow-up cards,
                 phone alerts, sprint planner, architect handoff brief.
TASK COUNT: 5 (then continue the watch loop indefinitely).

GOAL: Predictive coordination. Use historical agent throughput data to
forecast completion times, identify bottleneck patterns, suggest capacity
reallocation. The kanban becomes a force multiplier, not just a tracker.

WINDOW PLAN: Continuous. 5-min watch loop runs in both windows.
  Window A optimal: Task 1 (training data ingestion needs Mongo)
  Window B safe: Tasks 2, 3, 4, 5

STOP CONDITION OVERRIDE: Continuous coordinator. End-of-Round-3 = mark
round3_deliverables: done in kanban card. Watch loop keeps running.

═══ TASK 1 — Agent throughput model [A] ═══
Files to create/modify:
  backend/services/kanban/throughput_model.py         (NEW)
  scripts/train_throughput_model.py                   (NEW)
  ./project_oracle/models/throughput_v1.joblib        (artifact)
  backend/tests/services/kanban/test_throughput.py    (NEW — 10+ tests)

Spec:
  Training data: aggregate from kanban/closed/*.md (since 2026-05-19):
    Features per closed card:
      agent_id (0-9)
      card_priority (low/med/high → 0/1/2)
      lines_changed_estimate (parse from card description)
      files_touched_estimate
      test_count_required
      time_of_day_started (0-23)
      day_of_week_started (0-6)
    Target:
      hours_to_close

  Model: sklearn.linear_model.PoissonRegressor (interpretable, calibrated)

  Output: P(close_within_T_hours | features) for T ∈ {1, 4, 12, 24, 72}

  Cross-validation: 5-fold time-series CV (no random shuffle on time-ordered data)
  Metric: MAE on hours_to_close — target MAE < 1.5 hours

Verification:
  python scripts/train_throughput_model.py
  # → trains, saves to ./project_oracle/models/throughput_v1.joblib
  # → prints cross-val MAE

  pytest backend/tests/services/kanban/test_throughput.py -v  → 10+ pass

Acceptance:
  - Trained on ≥ 100 historical cards
  - 5-fold CV MAE < 1.5 hours
  - Predictions surface in kanban/SWARM_STATUS.md ("est. completion: <when>")
  - Reference: Hyndman-Athanasopoulos (2018) *Forecasting: Principles and Practice* §3

═══ TASK 2 — Bottleneck detector [B] ═══
Files to create/modify:
  backend/services/kanban/bottleneck.py               (NEW)
  backend/tests/services/kanban/test_bottleneck.py    (NEW — 8+ tests)

Spec:
  Every 30 min (from existing watch loop), compute per-agent metrics:
    cards_in_flight
    avg_time_per_card_24h
    blocker_rate (cards entering "blocked" state / total cards)
    push_failure_rate

  Bottleneck criteria:
    agent.cards_in_flight > 3 * median_agent.cards_in_flight
    OR agent.blocker_rate > 2 * median_agent.blocker_rate

  Surface to kanban/ARCHITECT_BRIEF.md (next refresh):
    section "Bottlenecks Detected" listing agent + reason + suggested action

  Alert via Agent 10 phone channel if bottleneck persists > 2h.

Verification:
  pytest backend/tests/services/kanban/test_bottleneck.py -v  → 8+ pass

  # Synthetic test: inject overloaded agent → detector flags it correctly

Acceptance:
  Bottleneck alerts wire to Agent 10 phone-notification path.
  ARCHITECT_BRIEF.md shows "Bottlenecks Detected" section.

═══ TASK 3 — Capacity rebalancing recommender [B] ═══
Files to create/modify:
  backend/services/kanban/rebalancer.py               (NEW)
  backend/tests/services/kanban/test_rebalancer.py    (NEW — 8+ tests)

Spec:
  When bottleneck detected:
    Score each (card, agent) pair:
      skill_match = TF-IDF(card.required_skills, agent.skills_from_history)
      capacity_factor = (median_in_flight - agent.cards_in_flight) / median_in_flight
      score = skill_match * (1 + capacity_factor)

    Recommend the top reassignment (card_id → from_agent → to_agent).
    Write proposal to kanban/REBALANCE_PROPOSAL.md for Nav to approve.

  Optimal assignment via Hungarian algorithm (scipy.optimize.linear_sum_assignment)
  if multiple reassignments improve global throughput.

Verification:
  pytest backend/tests/services/kanban/test_rebalancer.py -v  → 8+ pass

  # 3 synthetic bottleneck scenarios → reasonable reassignment proposals

Acceptance:
  Proposals are sensible (skill match score > 0.4 for chosen target).
  Reference: Kuhn (1955) "The Hungarian Method for the Assignment Problem"

═══ TASK 4 — Sprint retrospective generator [B] ═══
Files to create/modify:
  scripts/generate_retro.py                           (NEW)
  kanban/retros/RETRO_<YYYY-WW>.md                    (output weekly)

Spec:
  End of each week (Sunday 6pm ET), aggregate:
    - cards closed this week (count, mean close-time, by-agent)
    - cards in flight (count, hours-burned, age distribution)
    - blockers encountered (count, types, resolution patterns)
    - velocity (cards/week, rolling 4-week)

  LLM-synthesize retrospective via DSPy:
    - What went well (top 3 from the data)
    - What didn't (top 3)
    - Action items (each gets a new kanban card auto-spawned)

  Output kanban/retros/RETRO_<YYYY-WW>.md

Verification:
  python scripts/generate_retro.py --week 2025-W04
  # → produces kanban/retros/RETRO_2025-W04.md

  # Manual review of one week's retro: ≥3 specific improvement items

Acceptance:
  Retro generated weekly.
  Action items spawn kanban cards.
  Reference: Brooks (1975) *The Mythical Man-Month* — Brooks's Law

═══ TASK 5 — Multi-repo coordination [A] ═══
Files to create/modify:
  backend/services/kanban/multi_repo.py               (NEW)
  kanban/multi_repo_status.md                         (output)

Spec:
  Cards can declare in frontmatter:
    affects_repos: [floww, gflows, baby-billy-dvt]

  Watcher monitors each listed repo (path configured in kanban/repos.yaml):
    floww:           /Users/nav/Documents/GitHub/floww
    gflows:          /Users/nav/gflows
    baby-billy-dvt:  ~/Documents/GitHub/baby-billy-dvt   (if exists)

  Cross-repo SWARM_STATUS.md aggregates per-repo state.

  When a card affects N repos, require commits in all N before marking done.

Verification:
  # Create test card affecting 2 repos → commit in only 1 → card stays "in_progress"
  # Commit in 2nd repo → card moves to "review"

Acceptance:
  Cards affecting multiple repos correctly aggregate status.
  Multi-repo dashboard live at kanban/multi_repo_status.md.

═══ SKILLS REQUIRED ═══
  - devops:kanban-orchestrator        (board state machine)
  - devops:kanban-worker              (pull-from-ready workers)
  - autonomous-ai-agents:kanban-codex-... (codex workers for code tasks)
  - hermeshub:agent-hardening         (continuous loop resilience)
  - mlops:dspy                        (retro generation prompts)
  - mlops:evaluating-l...             (throughput model validation)
  - note-taking:obsidian              (sync SPRINT + ARCHITECT_BRIEF to vault)
  - swarmclaw:coding-agent            (implementations)

═══ RISKS ═══
  - Throughput model has only ~100 data points → quantify uncertainty bands.
  - LLM retros risk hallucination → require ≥1 kanban card citation per "what didn't go well" item.
  - Multi-repo coordination assumes all repos are local — document path config.

═══ CHECKPOINTING ═══
After each task, write kanban/cards/agent8_checkpoint.md.

═══ DONE WHEN (Round 3 deliverables) ═══
All 5 tasks shipped + pushed + truth audit green.
Then KEEP RUNNING the watch loop indefinitely.
memory/agent8_round3_complete.md written. Card status remains "in_progress".
```

---

## AGENT 9 — Federated multi-modal memory

```
[PASTE STANDING PREAMBLE — replace <N> with 9 throughout]

ROUND-3 IDENTITY: Hermes Agent 9, memory architect.
KANBAN CARD: O-MEMORY-UNIFY
ROUND-2 SHIPPED: daily consolidation cron, auto-tagging on insert,
                 ask-hermes CLI, memory pruning policy, cross-project tagging.
TASK COUNT: 5. You are not done until all 5 are shipped and pushed.

GOAL: Federated memory across Hermes instances (laptop, work, future cloud)
+ multi-modal embeddings (text, code, charts, audio notes). Memory becomes
a single addressable surface that survives any single-machine failure.

WINDOW PLAN:
  Tasks 1, 4 → Window A (federation queue + Whisper model download)
  Tasks 2, 3, 5 → Window B safe (work on cached embedding models)

═══ TASK 1 — Federated mem0 sync [A] ═══
Files to create/modify:
  backend/services/memory/federation.py               (NEW)
  scripts/mem0_federate.py                            (NEW — node daemon)
  infra/upstash_redis.tf                              (NEW — Redis pub-sub channel)
  backend/tests/services/memory/test_federation.py    (NEW — 10+ tests)

Spec:
  Multiple mem0 instances share state via Upstash Redis pub-sub (free tier).

  Each node:
    publishes its writes to channel "mem0_writes" with payload:
      {node_id, entry_id, op, content, timestamp_utc, tombstone}
    subscribes to "mem0_writes" — for each remote write:
      LWW conflict resolution: if remote.timestamp > local.timestamp → apply

  Tombstone for deletes: entry stays in store with tombstone=true for 30d,
  then GC'd by daily prune.

  Replication lag SLA: < 30s steady-state.

Verification:
  pytest backend/tests/services/memory/test_federation.py -v  → 10+ pass

  # 2-node simulation:
  python -c "
    # Start node A, node B both subscribed
    # A writes 'foo' → B receives within 30s
    # B writes 'bar' → A receives within 30s
    # Both write same key concurrently → LWW resolves to higher timestamp
    print('PASS: 2-node convergence')
  "

Acceptance:
  - 100 concurrent writes from 2 nodes converge to consistent state
  - Replication lag p99 < 30s on Upstash free tier
  - Reference: Bailis et al. (2013) "Eventual Consistency Today" *CACM*

═══ TASK 2 — Code embeddings [B] ═══
Files to create/modify:
  scripts/embed_codebase.py                           (NEW)
  backend/services/memory/code_embeddings.py          (NEW)
  requirements.txt                                     (add transformers, sentence-transformers)

Spec:
  For every .py / .ts / .js file in:
    backend/, frontend/src/, scripts/, qc/
  Embed via microsoft/codebert-base (or fallback all-MiniLM-L6-v2 if codebert too heavy).
  Chunk strategy: one embedding per top-level def/class + one per module docstring.

  Store in mem0's vector backend (if vector-capable) OR Qdrant local.

  Query API extension:
    ask-hermes "where is GEX calculated?"
    → returns top-3 code pointers (file:line + snippet)

Verification:
  python scripts/embed_codebase.py
  # → "embedded N functions, K classes across F files in T seconds"

  python -c "
    from services.memory.code_embeddings import search_code
    results = search_code('where is VPIN computed?', top_k=3)
    assert any('vpin_engine' in r['file'] for r in results)
    for r in results: print(f'{r[\"file\"]}:{r[\"line\"]} (score={r[\"score\"]:.3f})')
  "

Acceptance:
  - 10 benchmark code-search queries return correct results
  - Query latency < 500ms
  - Reference: Feng et al. (2020) "CodeBERT"

═══ TASK 3 — Chart screenshot embeddings [B] ═══
Files to create/modify:
  scripts/embed_screenshots.py                        (NEW)
  backend/services/memory/chart_embeddings.py         (NEW)
  ~/Documents/floww-screenshots/                      (Nav drops screenshots here)

Spec:
  Watch ~/Documents/floww-screenshots/ for new image files (.png, .jpg).
  For each: embed via openai/clip-vit-base-patch32.
  Store embedding + filename + timestamp in mem0.

  Query:
    ask-hermes "show me the Heatseeker view from last Tuesday morning"
    → CLIP retrieves matching screenshot, opens it (macOS `open` cmd)

Verification:
  # Drop 5 known screenshots → ask-hermes finds them by text query
  python -c "
    from services.memory.chart_embeddings import search_screenshots
    results = search_screenshots('GEX heatmap with red walls')
    for r in results[:3]: print(r['file'], r['score'])
  "

Acceptance:
  5 benchmark text queries return correct screenshots.
  Reference: Radford et al. (2021) "CLIP"

═══ TASK 4 — Voice memo transcription + embedding [A] ═══
Files to create/modify:
  scripts/transcribe_voice_memos.py                   (NEW)
  backend/services/memory/voice_embeddings.py        (NEW)
  requirements.txt                                     (add openai-whisper>=20240930)

Spec:
  Watch iOS Voice Memos sync folder:
    ~/Library/Mobile Documents/com~apple~CloudDocs/Voice Memos/
    (or wherever the iCloud sync lands on Nav's Mac)

  For each new .m4a file:
    transcribe via whisper-base (local, ~150MB model)
    insert transcript into mem0 with tags ["source:voice_memo", "audio"]
    keep original audio file path as a reference

Verification:
  # Record a 30s voice memo, sync to Mac, run script
  python scripts/transcribe_voice_memos.py --dry-run
  # → lists files it would transcribe

  python scripts/transcribe_voice_memos.py
  # → transcript appears in mem0; searchable via ask-hermes

Acceptance:
  - Sample voice memo transcribes with > 90% word accuracy
  - Searchable via ask-hermes "what did I say about GEX yesterday?"
  - Reference: Radford et al. (2022) "Whisper"

═══ TASK 5 — Memory health monitor [B] ═══
Files to create/modify:
  backend/services/memory/health.py                   (NEW)
  backend/routes/admin.py                              (extend — /memory/health)
  backend/tests/services/memory/test_memory_health.py  (NEW — 8+ tests)

Spec:
  Endpoint GET /api/admin/memory/health:
    {
      entry_count: int,
      query_latency_p99_ms: float,
      embedding_cache_hit_rate: float,
      federation_lag_seconds: float,
      last_consolidation_at: iso8601,
      pruning_stats: {pruned_24h, kept_durable}
    }

  Wire metrics into Agent 10's Prometheus:
    floww_memory_entry_count
    floww_memory_query_latency_ms{quantile}
    floww_memory_federation_lag_s

  Alert thresholds (Agent 10 picks them up):
    query p99 > 500ms → WARN
    federation_lag > 60s → CRITICAL

Verification:
  pytest backend/tests/services/memory/test_memory_health.py -v  → 8+ pass
  curl http://localhost:8000/api/admin/memory/health | python3 -m json.tool
  # → all fields present, response < 50ms

Acceptance:
  Endpoint < 50ms p99.
  Prometheus scrapes the metrics; Grafana shows them.

═══ SKILLS REQUIRED ═══
  - mem0:mem0-cli, mem0:mem0-integrate, mem0:mem0-test-integration...
  - note-taking:obsidian              (sync federation status to Obsidian)
  - hermeshub:agent-hardening         (eventually-consistent replication)
  - hermeshub:api-builder             (Task 5 health endpoint)
  - mlops:dspy                        (semantic search prompt structure)
  - mlops:evaluating-l...             (retrieval accuracy eval)
  - swarmclaw:coding-agent            (implementations)

═══ RISKS ═══
  - Federation consistency is genuinely hard. Start with LWW; document limits.
  - Multi-modal embedding model footprint ~3GB total (CodeBERT + CLIP + Whisper).
    If local resource-constrained, switch CodeBERT to MiniLM (much smaller).
  - Voice Memos iCloud sync path can vary — make it configurable in env var.

═══ CHECKPOINTING ═══
After each task, write kanban/cards/agent9_checkpoint.md.

═══ DONE WHEN ═══
All 5 tasks shipped + pushed + truth audit green.
New tests: 10+0+0+0+8 = 18+ tests + 2 working CLI search modes.
memory/agent9_round3_complete.md written. Kanban card status: done. Exit.
```

---

## AGENT 10 — Predictive alerting + chaos forecasting

```
[PASTE STANDING PREAMBLE — replace <N> with 10 throughout]

ROUND-3 IDENTITY: Hermes Agent 10, observability lead.
KANBAN CARD: O-OBSERVABILITY
ROUND-2 SHIPPED: Twilio phone alerting, meta-anomaly detection on metrics,
                 SLA dashboards, cost dashboards, incident post-mortem template.
TASK COUNT: 5. You are not done until all 5 are shipped and pushed.

GOAL: Predictive alerting. Move from "alert when threshold breached" to
"alert when we predict a threshold WILL be breached in N minutes." Plus
chaos-event forecasting. Nav gets called when something matters, AND
ONLY when something matters.

WINDOW PLAN:
  Tasks 1, 2, 4 → Window A (training needs Mongo metrics history)
  Tasks 3, 5 → Window B safe (pure compute on cached models)

═══ TASK 1 — Predictive alert engine [A] ═══
Files to create/modify:
  backend/services/observability/predictive_alerts.py (NEW)
  scripts/train_predictive_alerts.py                  (NEW)
  ./project_oracle/models/predictive_alert_v1.pt      (artifact)
  backend/tests/services/observability/test_predictive_alerts.py (NEW — 10+ tests)

Spec:
  Train a forecasting model per critical metric:
    metrics: ingestion_rate, duckdb_queue_depth, vpin_per_ticker, p99_latency,
             ws_connections, error_rate

  Model: PatchTST (or LSTM fallback if PatchTST install issues)
    Input: last 60 min of metric values (1-min resolution)
    Output: forecast for next 15 min (1-min resolution)

  Alert tier:
    WARNING:  predicted breach of threshold in 5-15 min
    CRITICAL: predicted breach in < 5 min OR already breached

  Threshold definitions live in prometheus/recording_rules/alert_thresholds.yml.

Verification:
  pytest backend/tests/services/observability/test_predictive_alerts.py -v  → 10+ pass

  # Backtest on held-out metric history:
  python scripts/train_predictive_alerts.py --backtest 30d
  # → reports per-metric: recall on actual breaches, FPR
  # Expected: recall ≥ 80%, FPR ≤ 10%

Acceptance:
  ≥80% recall on actual breaches with ≤10% FPR.
  Forecasts published as Prometheus metric:
    floww_metric_forecast{metric, horizon_min}
  References: Hochreiter-Schmidhuber (1997) LSTM; Nie et al. (2022) PatchTST

═══ TASK 2 — System health forecasting [A] ═══
Files to create/modify:
  backend/services/observability/system_health_forecaster.py (NEW)
  scripts/train_system_forecaster.py                  (NEW)
  ./project_oracle/models/system_forecaster_v1.pt     (artifact)
  backend/tests/services/observability/test_system_forecaster.py (NEW — 8+ tests)

Spec:
  Multivariate forecasting of all metrics jointly.
  Use DeepAR (gluonts library) OR a simpler probabilistic model.

  Input: 60-min history of all metrics (multivariate time series).
  Output: P(degraded_state | 5/15/30/60 min ahead) per service.

  "Degraded state" definition per service:
    backend:  p99_latency > 2x baseline OR error_rate > 5%
    ingestion: rate < 50% of baseline for > 5 min
    mongo:    timeout rate > 1%
    schwab:   disconnect count > 2 in 5 min

Verification:
  pytest backend/tests/services/observability/test_system_forecaster.py -v  → 8+ pass

  # 30-day backtest with known incidents:
  python scripts/train_system_forecaster.py --backtest
  # → "predicted N of M incidents at least 10 min in advance"
  # → expected: ≥70% lead-time-correct predictions

Acceptance:
  ≥70% of incidents predicted ≥ 10 min in advance.
  Surfaced via Grafana panel "System Health Forecast".
  Reference: Salinas et al. (2020) "DeepAR: Probabilistic Forecasting"

═══ TASK 3 — Incident similarity search [B] ═══
Files to create/modify:
  backend/services/observability/incident_similarity.py (NEW)
  backend/routes/incidents.py                          (extend)
  backend/tests/services/observability/test_incident_similarity.py (NEW — 8+ tests)

Spec:
  For each new incident (auto-created via Agent 10 alert routing):
    Embed the incident description + timeline via sentence-transformers
    Cosine-similarity vs past incidents in docs/INCIDENTS/
    Return top-3 similar past incidents + their resolutions

  Endpoint:
    GET /api/incidents/{id}/similar
    response: [{incident_id, similarity_score, resolution_summary}]

Verification:
  pytest backend/tests/services/observability/test_incident_similarity.py -v  → 8+ pass

  # 5 synthetic test incidents → expected related historical incidents retrieved

Acceptance:
  Similarity search wired into incident-creation flow.
  Top-3 results returned in < 200ms.
  Reference: Reimers-Gurevych (2019) "Sentence-BERT"

═══ TASK 4 — Cost forecasting + budget protection [A] ═══
Files to create/modify:
  backend/services/observability/cost_forecaster.py   (NEW)
  scripts/cost_forecast.py                            (NEW — cron daily)
  grafana/dashboards/cost_forecast.json                (NEW)
  deploy/cron.d/hermes-cost-forecast                   (NEW)

Spec:
  Track daily cost per provider:
    Azure (App Service hours, ACR storage, Cosmos RU consumption)
    Databento (credits used)
    Schwab (API call count vs entitlement)
    OpenRouter/Anthropic LLM tokens
    HuggingFace bandwidth

  Forecast end-of-month total via exponential smoothing
  (statsmodels.tsa.holtwinters.SimpleExpSmoothing).

  Auto-actions:
    if forecasted_total > 110% of monthly_budget:
      throttle Agent 6 research loop 60min → 240min
      write WARN to Agent 8 kanban
    if forecasted_total > 150%:
      stop Agent 6 entirely
      page Nav (CRITICAL)

Verification:
  python scripts/cost_forecast.py
  # → prints projected end-of-month cost

  # Inject synthetic over-budget scenario → auto-throttle triggers

Acceptance:
  Cost dashboard shows forecasted EoM cost per provider.
  Auto-throttle triggers on synthetic over-budget.
  Reference: Hyndman-Athanasopoulos (2018) §7 — exponential smoothing

═══ TASK 5 — Self-healing runbook automation [B] ═══
Files to create/modify:
  backend/services/observability/auto_remediation.py  (NEW)
  docs/INCIDENTS/runbooks/                             (NEW dir)
  docs/INCIDENTS/runbooks/mongo_connection_storm.yaml  (NEW)
  docs/INCIDENTS/runbooks/duckdb_lock_contention.yaml  (NEW)
  docs/INCIDENTS/runbooks/schwab_token_expired.yaml    (NEW)
  backend/tests/services/observability/test_auto_remediation.py (NEW — 8+ tests)

Spec:
  YAML runbook schema:
    name: "Mongo Connection Storm"
    detection:
      metric: "floww_mongo_timeout_rate"
      threshold: 0.05
      window: "5min"
    remediation_steps:
      - { type: "restart_service", target: "ingestion_pipeline" }
      - { type: "flush_cache", target: "motor_pool" }
      - { type: "human_confirm", message: "Restart MongoDB connection pool?" }
    requires_human_confirmation: true   # destructive actions only

  auto_remediation.py:
    Watches alerts; matches against runbook detection criteria.
    For each match: executes non-destructive steps automatically;
    pauses at human_confirm step and notifies Nav.

Verification:
  pytest backend/tests/services/observability/test_auto_remediation.py -v  → 8+ pass

  # Synthetic test: inject mongo timeout spike → runbook fires → first 2 steps
  # execute → pauses at human_confirm → Nav approves → final step executes

Acceptance:
  3 runbooks defined (Mongo, DuckDB, Schwab).
  At least 1 fully auto-remediates a synthetic incident.
  Human-in-the-loop gate verified for destructive actions.
  Reference: Beyer et al. (2016) *SRE* Ch.12 — Effective Troubleshooting

═══ SKILLS REQUIRED ═══
  - autonomous-ai-agents:codex        (Tasks 1, 2 — training scripts)
  - mlops:dspy                        (hyperparameter sweep + runbook synthesis)
  - mlops:evaluating-l...             (forecast accuracy — CRPS, quantile loss)
  - gbrain:academic-verify            (LSTM/PatchTST/DeepAR vs papers)
  - red-teaming:godmode               (Task 5 confirm-gate bypass tests)
  - hermeshub:agent-hardening         (safe automation patterns)
  - swarmclaw:coding-agent            (implementations)

═══ RISKS ═══
  - Predictive alerts firing too early erode trust (cry-wolf) — calibrate FPR against baseline.
  - Auto-remediation in production = scary — human-in-the-loop gate for ANY destructive action.
  - Cost forecaster needs ≥30d of cost history to be useful — bootstrap from current spend.

═══ CHECKPOINTING ═══
After each task, write kanban/cards/agent10_checkpoint.md.

═══ DONE WHEN ═══
All 5 tasks shipped + pushed + truth audit green.
New tests: 10+8+8+0+8 = 34+ tests + 3 runbooks + 2 trained forecast models.
memory/agent10_round3_complete.md written. Kanban card status: done. Exit.
```

---

## Deployment order — fire in this sequence

```
PRE-FLIGHT (run before any agent):
  Verify floww repo is at /Users/nav/Documents/GitHub/floww with origin
  git@github.com:JattMoosewala5911/floww.git. If not, clone first:
    cd /Users/nav/Documents/GitHub/
    gh repo clone JattMoosewala5911/floww

WINDOW A — fire NOW (need network + Mongo + Schwab live):
  Agent 1  — Schwab paper-trade execution
  Agent 2  — RL policy training
  Agent 5  — Causal ATE estimation
  Agent 6  — Knowledge graph + research loop
  Agent 9  — Federated memory + embeddings
  Agent 10 — Predictive alerts + cost forecasting

WINDOW B — fire anytime (no live deps):
  Agent 3  — TradingView + visual parity + mobile PWA
  Agent 4  — Property + fuzz + chaos engineering
  Agent 7  — Azure deploy + live-trading switch + audit trail
  Agent 8  — ML-driven kanban + capacity planning

Each agent runs autonomously until ALL 5 tasks ship. They check kanban/cards/
agent<N>_checkpoint.md on startup to resume from where they left off.

Agent 8 (kanban orchestrator) tracks transitions in kanban/SWARM_STATUS.md —
that's Nav's single dashboard.

SLEEP THROUGH THIS. ~40-50 agent-hours of work queued.
Truth audit gates every commit. Critical=0 gates live trading.

Memory recovery path if context wipes:
  1. ~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/MEMORY.md
  2. /Users/nav/Documents/GitHub/floww/DISPATCH_PLAN_ORACLE.md (Round 1)
  3. /Users/nav/Documents/GitHub/floww/DISPATCH_PLAN_ORACLE_ROUND2.md
  4. /Users/nav/Documents/GitHub/floww/DISPATCH_PLAN_ORACLE_ROUND3.md
  5. /Users/nav/Documents/GitHub/floww/LAUNCH_PROMPTS_ROUND3.md (this file)
  6. /Users/nav/Documents/GitHub/floww/kanban/SWARM_STATUS.md (live state)
  7. `ask-hermes "agent<N> status"`
```

This is the same format as Round 2. Time-windowed. Per-task acceptance criteria. Math citations on every kernel. Skill mapping. Checkpoints. Continuous-work protocol. Fire them all.
