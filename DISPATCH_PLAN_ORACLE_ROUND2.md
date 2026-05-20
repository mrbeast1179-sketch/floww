# Project Oracle — ROUND 2 Dispatch Plan

**Pairs with:** `DISPATCH_PLAN_ORACLE.md` (Round 1 — the foundational tracks)
**Triggered by:** each agent's `memory/agent<N>_round1_complete.md` file
**Coordinator:** Agent 8 (kanban) watches for completion files and auto-loads Round 2 prompts
**Time-window strategy:** Tasks marked `[A]` need network (Mongo + Schwab live). Tasks marked `[B]` are pure-compute and run anytime. Plan Window A work for ~6-8h evening session; Window B for after Nav goes to work.

---

## Standing preamble (every agent prepends this)

```
TIME-WINDOW STRATEGY:
  Window A — NEXT 6-8 HOURS: Mongo + Schwab LIVE. Do all data-hungry work now.
  Window B — AFTER 7am Nav's time: Atlas blocked by work Wi-Fi.
    Detect via ServerSelectionTimeoutError(5s); fall back to
    backend/.duckdb_cache/ + queue retries in backend/.mongo_retry_queue/.

OPERATING LAWS:
  • bash qc/audit/truth_audit.sh GREEN before AND after each commit
  • TDD: failing test first, see fail, implement, see pass
  • Conventional commits: <type>(scope): ...; Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  • NEVER --no-verify, --amend, force-push main
  • Commit per deliverable; push after every commit
  • No synthetic data in production paths

SUBAGENT-DRIVEN EXECUTION:
  Per deliverable: dispatch swarmclaw:coding-agent → spec review → quality review
  Re-dispatch on issues. Move to next when both reviews pass.

STOP CONDITIONS:
  • Truth audit red → remediation only
  • All deliverables shipped → write memory/agent<N>_round2_complete.md
  • 3 push failures → checkpoint to kanban card, exit clean
  • Token exhaustion → checkpoint, exit clean
```

---

## <a id="agent-1"></a>Agent 1 — Schwab WS extensions + replay (card: O-PHASE1-SCHWAB)

**Goal:** Hedge-fund-grade ingestion. Level-2 depth, historical replay, observable health, cross-source data quality.

### Tasks

**1. Level-2 order book depth `[A]`**
- Files: `backend/services/schwab_streamer.py` (extend), `backend/services/duckdb_engine.py` (add table), `backend/tests/services/test_lob_depth.py` (8+ tests)
- Subscribe to LEVEL_TWO_OPTIONS for top-10 levels per active strike
- DuckDB schema: `lob_depth(timestamp, symbol, expiry, strike, option_type, level, bid_size, bid_price, ask_size, ask_price)`
- Verification: schema check + 100-message mock-feed exercise
- Accept: live feed runs ≥30 min, zero schema errors

**2. Historical replay engine `[A]`**
- Files: `backend/services/replay_engine.py`, `backend/tests/services/test_replay_engine.py` (10+ tests), `backend/routes/replay.py`
- `ReplayEngine(start, end, speed)` reads from DuckDB+Mongo, pushes to same queue as live feed
- Speeds: 1x, 10x, 100x, "max"; routes: POST /api/replay/{start,stop}, GET /api/replay/status
- Accept: replayed Trinity score matches live Trinity for same window

**3. Schwab health endpoint `[B]`**
- Files: `backend/routes/admin.py`, `backend/tests/test_schwab_health.py` (5+ tests)
- GET /api/admin/schwab/health → `{connected, token_ttl_seconds, last_message_at, messages_per_minute_5min, reconnect_count_24h, lob_depth_rows_24h}`
- Accept: <50ms response even under heavy ingestion

**4. Token auto-refresh `[A]`**
- Files: `backend/services/schwab_streamer.py` (extend), `backend/tests/services/test_schwab_token.py` (6+ tests with mocked OAuth)
- TTL <300s → refresh; new token to backend/.env (chmod 0600); backoff 1/2/4/8/16/32s
- Accept: zero 401s over 24h smoke test

**5. Cross-source GEX consistency `[A]`**
- Files: `backend/services/data_quality.py`, `backend/tests/services/test_data_quality.py` (8+ tests)
- Every 5 min: compare Schwab GEX vs yfinance GEX; rel-err >5% warns, >20% kanban-card HIGH
- Accept: catches injected stale-spot bug; 24h median rel-err <1%

### Skills
`hermeshub:api-builder`, `swarmclaw:coding-agent`, `data-science:jupyter-live-kernel`, `software-development:debugging-hermes-tui-comman...`, `hermeshub:agent-hardening`

### Risks
Level-2 entitlement may be missing → downgrade to LEVELONE_OPTIONS. lob_depth table grows fast → add 24h retention cron.

---

## <a id="agent-2"></a>Agent 2 — Forecasting ensemble + regime thresholds (card: O-PHASE2-ANOMALY)

**Goal:** Calibrated ensemble with regime-aware decisions (tier-1 quant desk shape).

### Tasks

**1. PatchTST VPIN forecaster `[A]`**
- Files: `scripts/train_patchtst_vpin.py`, `./project_oracle/models/patchtst_vpin_v1.pt`, `qc/data/patchtst_vpin_v1_manifest.json`, `backend/tests/services/test_patchtst_inference.py` (8+ tests)
- Backbone: `ibm-granite/granite-timeseries-patchtst`; predict next 15×1min VPIN from last 60×1min
- Train data: gex_history Mongo (Window A!); fallback synthetic GBM trajectories marked v0
- Time-ordered 80/20 split (no shuffle); MSE on z-scored VPIN
- Accept: val MSE < persistence baseline; <20ms CPU inference

**2. Autoformer chain dynamics `[A]`**
- Files: `scripts/train_autoformer_chains.py`, model + manifest, `backend/tests/services/test_autoformer_inference.py` (8+ tests)
- Multivariate forecast (strikes as channels): next 5×1min GEX surface from last 30×1min
- Accept: FOMC-day pred/realized correlation > 0.5

**3. Ensemble inference `[B]`**
- Files: `backend/services/ml_ensemble.py`, `backend/routes/anomaly.py` (extend), `backend/tests/services/test_ml_ensemble.py` (12+ tests)
- Combines (a) 1D-CNN AE reconstruction (b) PatchTST forecast residual (c) statistical detector
- Platt/isotonic calibration; output P(toxic in N min), N∈{1,5,15,60}
- Endpoint: GET /api/anomaly/ensemble?ticker=&horizon_minutes=
- Accept: ensemble Brier score < any component's individually

**4. Regime-aware thresholds `[B]`**
- Files: `backend/services/anomaly_detector.py` (extend), `backend/tests/services/test_regime_thresholds.py` (8+ tests)
- Regimes by 30d realized-vol percentile: calm (<33rd) →99th-pct threshold; active (33-95th)→95th; urgent (>95th)→90th
- Accept: 30d calm-regime backtest FPR <1%

**5. Backtest `[A]`**
- Files: `scripts/backtest_ml_models.py`, `reports/backtest_ml_<date>.md`
- Walk-forward on longest gex_history window; inject 50 synthetic events (seed=42); surface real FOMC/NFP/OPEX
- Accept: F1 >0.6 synthetic, recall >0.5 real FOMC

### Skills
`mlops:dspy`, `mlops:evaluating-l...`, `gbrain:academic-verify`, `autonomous-ai-agents:codex`, `swarmclaw:coding-agent`

### Risks
HuggingFace rate-limit → fallback to lighter LSTM baseline. Sparse gex_history → bootstrap synthetic, mark v0, schedule retrain.

---

## <a id="agent-3"></a>Agent 3 — Atlas + replay + Agent Hub + polish (card: O-PHASE3-DASH)

**Goal:** Close visible Skylit-parity gap — Atlas chart, replay, Agent Hub scaffolding, daily-driver polish.

### Tasks

**1. Atlas tab — candlestick + overlays `[A]`**
- Files: `backend/services/dash_ui.py` (extend), `backend/services/atlas_overlays.py`, `backend/tests/services/test_atlas_overlays.py` (10+ tests)
- Plotly candlestick SPY/QQQ/SPX (1m bars), window selector 1h/4h/1d/1w/1mo
- Overlays (each toggleable): King Node lines, Zero-Gamma line, Air Pockets bands, anomaly markers, Trinity sparkline
- Accept: 5s refresh; <300ms overlay re-render

**2. Replay Mode in Atlas `[A]`**
- Files: `backend/services/dash_ui.py` (extend Atlas)
- Date+time picker + Play/Pause/Speed controls; hits Agent 1's POST /api/replay/start
- Accept: replay overlays match live overlays deterministically

**3. Agent Hub stub `[B]`**
- Files: `backend/services/agent_hub/{__init__.py,archetypes/*.yaml,runtime.py}`, `backend/routes/agent_hub.py`, `backend/services/dash_ui.py` (new tab), `backend/tests/services/test_agent_hub.py` (12+ tests)
- YAML schema: name, description, triggers[{metric,op,value,window_seconds}], logic, action{type,params}
- Runtime evaluates on every snapshot; emits to /ws/agent_hub
- Ship 3 archetypes: Squeeze Hunter, Trend Day Confirmer, Pin Risk Notifier
- Accept: <10ms snapshot eval overhead

**4. Nexus stub `[B]`**
- Files: `backend/services/dash_ui.py` (new tab), `backend/routes/nexus.py` (empty CRUD scaffolds)
- Empty leaderboard + comment-thread scaffolds + private-beta banner
- Accept: tab loads, UI footprint locked

**5. Polish `[B]`**
- Files: `backend/services/dash_ui.py`, `frontend/src/` (if React widgets)
- Dark theme default + light toggle; shortcuts 1-5/R/M/?; mobile-responsive Toxicity Gauge; browser Notifications for HIGH anomalies
- Accept: `npx craco build` succeeds; shortcuts work per ? overlay

### Skills
`swarmclaw:coding-agent`, `creative:architecture-diagram`, `devops:react-craco...`, `mcp:native-mcp`, `hermeshub:api-builder`

### Risks
Plotly candlestick heavy → keep <5000 bars (decimate). Browser Notifications need HTTPS in prod → document in RUNBOOK.

---

## <a id="agent-4"></a>Agent 4 — Test infra hardening + property + mutation (card: O-TEST-INFRA)

**Goal:** From "passes" to "enforces correctness." Property-based invariants, mutation testing, CI gates.

### Tasks (all `[B]`)

**1. Pytest-asyncio mode auto** — `backend/pytest.ini` set `asyncio_mode = auto`; remove redundant `@pytest.mark.asyncio`. Accept: zero PytestDeprecationWarnings.

**2. CI coverage gates** — `.github/workflows/ci.yml` + `.coveragerc`. Thresholds: services/ 90%, routes/ 70%, backend overall 80%. Accept: CI fails on threshold breach.

**3. Property-based math** — `backend/tests/services/test_microstructure_property.py` using `hypothesis`. Invariants: VPIN buy+sell==volume bit-exact; GEX linear in OI; SABR ATM Bachelier↔Black agreement near T→0; Kyle's λ unique; Hawkes intensity([])==μ; Hawkes α=0 → Poisson. Accept: zero counterexamples on 10-min deep search.

**4. Mutation testing** — `mutmut run --paths-to-mutate=backend/services/{vpin_engine,hawkes_process,stochastic_vol,gex_aggregator}.py`. Goal mutation score >80%. Report at `reports/mutation_<date>.md`. Add tests for escaped mutations.

**5. Flaky-test detector** — `backend/tests/_flaky_detector.py` (pytest plugin), `.github/workflows/flaky.yml` nightly. Output `reports/flaky_<date>.md`. CI WARN (not fail) on flakies.

### Skills
`swarmclaw:coding-agent`, `hermeshub:agent-hardening`, `software-development:debugging-hermes-tui-comman...`, `gbrain:academic-verify`

### Risks
Mutation testing slow (~30 min) → nightly only. Coverage may dip during Agent 1/2/3 work → 24h grace period (warn don't fail).

---

## <a id="agent-5"></a>Agent 5 — Reference parity + theory bible (card: O-MATH-VALID)

**Goal:** Cross-validate Hermes math against 30+ cloned reference repos. Ship the theory bible.

### Tasks (all `[B]`)

**1. Reference parity tests** — `backend/tests/services/test_reference_parity.py`, `docs/math_validation/INDEX.md`, `docs/math_validation/<repo>.md`. Pairings: iAmGiG_gex-llm-patterns↔gex_aggregator; FullStackCraft_floe↔stochastic_vol (hand-translate 1-2 cases); Matteo-Ferrara_gex-tracker↔gex_aggregator; boyac_pyOptionPricing↔numba_greeks; EsterHlav_Black-Scholes↔numba_greeks (Hull); FlashAlpha-lab_gex-explained↔gex_aggregator; MattL922_implied-volatility↔numba_greeks (IV). Assert rel-err <1e-4. Accept: ≥5 repos GREEN.

**2. Math correctness dashboard** — `mkdocs.yml`, `docs/math_validation/<formula>.md` per kernel. LaTeX-rendered formula + paper citation + Hermes file:line + reference file:line + parity verdict + commit-SHA pin. Accept: every kernel has a doc.

**3. Long-form architecture** — `docs/ARCHITECTURE_DEEP.md`. Latency budget (p50/p95/p99 per stage). Memory footprint (DuckDB cache, motor pool, Numba JIT cache, Dash callback). Failure-mode taxonomy table. Happy-path mermaid sequence diagram. Accept: 3am-recoverable.

**4. Theory bible** — `docs/THEORY.md`. One section per concept (VPIN/SABR/SVI/Hawkes/Kyle/Amihud/Trinity/Fragility). Format per section: intuition¶ + math¶ + Hermes code pointer¶. Accept: 600-800 lines; Jane Street intern readable in 90min.

**5. Notebook tutorials** — `docs/notebooks/0{1..5}_*.ipynb` covering: GEX from chain, VPIN walkthrough, SABR calibration, Trinity on real data, anomaly detector in action. Each runs clean: `pip install -r requirements.txt && jupyter nbconvert --execute`. Accept: all 5 execute end-to-end.

### Skills
`gbrain:academic-verify`, `gbrain:article-enric...`, `data-science:jupyter-live-kernel`, `creative:architecture-diagram`, `software-development:confluence-decoder`

### Risks
mkdocs may not be installed → fallback to plain markdown + cross-links. Reference license issues → document in math_validation doc.

---

## <a id="agent-6"></a>Agent 6 — Research loop expansion (card: O-RESEARCH-LOOP, CONTINUOUS)

**Goal:** Perpetual knowledge acquisition. Every cycle pushes the reference frontier outward.

### Loop cadence (~60 min/cycle)

**1. Source expansion** — arxiv (existing) + SSRN + NBER + ResearchGate + Quantocracy + AQR blog + Robot Wealth. Append to `data/external_research/discoveries_<date>.json`.

**2. Code-link extraction** — `scripts/extract_code_links.py` (existing).

**3. Selective cloning** — `scripts/clone_and_extract.py --execute --yes --license-allow MIT,Apache-2.0,BSD-3-Clause,MPL-2.0`. Skip GPL/AGPL/LGPL. Skip >1GB.

**4. AUTO-PORT (new)** — for each newly cloned repo with <500 LOC Python + benchmark + known dataset:
- Run their benchmark → record numbers
- Hand-port (or `swarmclaw:coding-agent`) the kernel into Hermes style (typed, docstring with paper citation, Numba where vectorizable)
- Run OUR port vs THEIR benchmark
- rel-err <1e-4 → write `memory/auto_port_proposal_<repo>_<date>.md` for Nav review
- rel-err ≥1e-4 → write divergence report

**5. Author watch (every 4h)** — Cliff Asness, López de Prado, Gatheral, Carreira, Diehl, Doloc, Brown. Append to `memory/author_alert_<author>_<date>.md`.

**6. HuggingFace watch (every 6h)** — tags: time-series, anomaly-detection, finance, options, lob. New uploads with >100 likes or from verified labs → `./project_oracle/MANIFEST.json`.

**7. Weekly digest (Mondays 6am)** — `memory/weekly_digest_<date>.md`. Top 3 papers / repos / HF assets ranked by relevance to current Phase.

### Skills
`research:arxiv,blogwatcher,duckduckgo-search,llm-wiki...`, `hermeshub:arxiv-watcher`, `gbrain:archive-crawler,article-enric...,academic-verify`, `swarmclaw:coding-agent` (auto-port worker)

### Rate limits
arxiv ≤30/h; GitHub ≤60/h (use Pro auth); HF ≤100/h; SSRN ≤10/min (respect robots.txt).

### Stop condition
Never (until Nav stops). Token exhaustion → checkpoint to kanban/cards/O-RESEARCH-LOOP.md, exit; next worker resumes.

---

## <a id="agent-7"></a>Agent 7 — Security remediations + pentest (card: O-SECURITY)

**Goal:** Implement every CRITICAL+HIGH from Round 1 audit. Pentest from outside LAN. Harden production. Gate live-trading switch.

### Tasks (all `[B]`)

**1. JWT auth middleware** — `backend/middleware/auth.py`, `backend/server.py` (wire), `backend/tests/test_auth_middleware.py` (15+ tests). HS256 + JWT_SECRET env (refuse to start if missing). 15-min access TTL, 7d refresh. Refresh-token rotation. `TESTING=1` bypass. `@require_auth(scopes=["trade","read"])` decorator. Accept: every CRITICAL unauthenticated mutating route now requires auth.

**2. WebSocket auth on /ws/{topic}** — `backend/services/websocket_streamer.py` (extend), `backend/tests/services/test_ws_auth.py` (8+ tests). First message must be `{"type":"auth","token":"<jwt>"}` within 5s; else close 1008. Max 5 concurrent WS per JWT sub. Accept: anonymous WS impossible from outside.

**3. Secret-rotation script** — `scripts/rotate_secrets.py`, `docs/SECRETS_RUNBOOK.md`. Rotate all 12 providers via their APIs; validate via read-only call; chmod 0600 backend/.env. Schedule via Agent 8 monthly card. Accept: dry-run produces sane plan.

**4. Pentest from outside LAN** — skill: `red-teaming:godmode`. Document each: WS without auth → 1008; /api/admin/* without auth → 401; race rate limiter (100 concurrent) → 429s; SQL/NoSQL injection patterns; CORS bypass via Origin spoofing; JWT tampering → 401; WS flooding (10k subscribe) → server stays responsive. `reports/pentest_<date>.md`; each successful exploit → CRITICAL kanban card. Accept: zero successful exploits.

**5. Production deployment hardening** — `Dockerfile.backend/frontend` (rewrite if needed); `.dockerignore` excludes .env/.git/tests/qc/docs/.venv; `docker-compose.prod.yml` with read-only rootfs (writable volumes for cache/duckdb/logs); `infra/caddy/Caddyfile` HTTPS via Let's Encrypt + HSTS + CSP. Backend runs as `app` uid=1000. Accept: Trivy/Grype scan zero CRITICAL CVEs.

### Skills
`red-teaming:godmode`, `hermeshub:agent-hardening`, `swarmclaw:coding-agent`, `hermeshub:api-builder`

### LIVE-TRADING GATE
ALL Round 2 deliverables ship AND `reports/pentest_<date>.md` CRITICAL count == 0 → Nav MANUALLY flips live-trading. No auto-flip.

---

## <a id="agent-8"></a>Agent 8 — Kanban evolution (card: O-KANBAN-ORCH, CONTINUOUS)

**Goal:** Tracker → force multiplier. Inter-agent messaging, auto-spawn follow-ups, phone alerts, sprint planning, architect brief.

### Behaviors (continuous, 5-min watch loop)

**1. Inter-agent messaging** — watch commit bodies for `cc: agent<N>` lines; append to `kanban/messages/agent<N>_inbox.md`. Read-receipt moves to `kanban/messages/_seen/`.

**2. Auto-spawn follow-ups** — watch for `TODO:`, `FIXME:`, `follow-up:`, `XXX:` in commits + code comments. Dedupe by content-hash. Create `kanban/cards/auto_<hash[:8]>.md` in `ready`. Don't duplicate within 7d window.

**3. Phone alerts** — `kanban/alerts.py`. Webhook URL in backend/.env (ALERT_WEBHOOK_URL). Triggers (CRITICAL): new vuln from Agent 7; truth audit red on main; anomaly detector real fire during market hours; ingestion stall >5min during market hours; 3 consecutive push failures. POST structured payload (severity/source/summary/deep-link). Accept: zero spurious in 24h quiet period.

**4. Sprint planner** — `kanban/SPRINT.md` regenerated Mondays 8am. Sections: completed-7d (count+hours), in-flight, proposed-this-week, velocity rolling-4w.

**5. Architect brief** — `kanban/ARCHITECT_BRIEF.md` every 4h. Sections: in-flight summary (line/agent: last-commit/last-update/blocker); decisions needed (review-column items); red lights (audit state, recent failures, security findings); green lights (recent wins). Accept: Nav 60s-scannable.

### Skills
`devops:kanban-orchestrator`, `devops:kanban-worker`, `autonomous-ai-agents:kanban-codex-...`, `hermeshub:agent-hardening`, `note-taking:obsidian` (sync via Agent 9)

---

## <a id="agent-9"></a>Agent 9 — mem0 Round 2 + cross-project + ask-Hermes (card: O-MEMORY-UNIFY)

**Goal:** Memory queryable, deduplicated, cross-project, CLI-accessible.

### Tasks

**1. Daily consolidation cron `[A]` (embeddings need network)** — `scripts/consolidate_memory_daily.py`, `deploy/cron.d/hermes-memory`. 4am daily: pull last-24h mem0 entries; dedup via embedding cosine-sim >0.95; merge duplicates; flag stale refs; diff to `memory/_consolidation_log_<date>.md`. Accept: entry-count grows sublinearly.

**2. Auto-tagging `[A]`** — `memory/_tag_taxonomy.yaml`, `scripts/auto_tag_memory.py`. Embed entry → K nearest tags → top 3 proposals. >0.8 confidence auto-apply; else queue for review. Controlled vocabulary (no free-form). Accept: 80% auto-tagged correctly on sampled audit.

**3. "ask-hermes" CLI `[B]`** — `scripts/ask_hermes.py`, `pip install -e .` makes `ask-hermes` shell command. Semantic search across mem0 + git log --grep + kanban cards. Returns top 3 + 1-paragraph synthesis. `--json` for piping. Accept: sub-1s on laptop.

**4. Memory pruning `[B]`** — `scripts/prune_memory.py` nightly cron. type=session >30d → `memory/_archive/<year>/<month>/`. Maintain `memory/_archive/INDEX.md`. Durable types never pruned. Accept: active dir <50 files long-term.

**5. Cross-project memory `[B]`** — mem0 multi-project mode. Tag each entry: floww | gflows | baby-billy-dvt | personal. `ask-hermes --project=floww "GEX"` filters; no filter searches all. Financial queries default to current project unless `--all-projects`. Accept: project filter works; defaults safe.

### Skills
`mem0:mem0-cli`, `mem0:mem0-integrate`, `mem0:mem0-test-integration...`, `note-taking:obsidian`, `swarmclaw:coding-agent`

---

## <a id="agent-10"></a>Agent 10 — Phone alerts + meta-anomaly + cost/SLA (card: O-OBSERVABILITY)

**Goal:** Nav gets called when something matters, AND only when something matters.

### Tasks

**1. Phone alerting `[B]`** — `backend/services/observability.py` (extend), env: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, NAV_PHONE_NUMBER. CRITICAL → SMS + voice call. Quiet hours 10pm-6am ET except market hours (DST-aware). Override for live-trading risk. 15-min dedup cooldown per alert-ID. Accept: 24h burn test zero spurious.

**2. Meta-anomaly on metrics `[A]` (training needs metrics history)** — `backend/services/meta_observability.py`, `./project_oracle/models/meta_anomaly_v1.pt`, `backend/tests/services/test_meta_observability.py` (10+ tests). Isolation forest on 30d Prometheus metrics. Inputs: ingestion_rate, queue_depth, vpin_current per ticker, p99_latency, ws_connections. Detects time-of-day baseline deviations (Tue 2pm now vs Tue 2pm avg). Surfaces as LOW-severity warnings. Accept: 7d held-out FPR <5%.

**3. SLA dashboard `[B]`** — `grafana/dashboards/sla.json`. Uptime % per service 24h/7d/30d (target: ingestion 99%, API 99.9%). p99 latency same windows (target: API <200ms, WS <50ms). Trade success rate when live. Error budget remaining. Accept: each panel has documented target+escalation.

**4. Cost dashboard `[B]`** — `grafana/dashboards/cost.json`. Databento credit burn (vs DATABENTO_BUDGET_USD); Schwab calls vs daily limit; HF bandwidth 7d; LLM tokens (OpenRouter/Anthropic/OpenAI); total $/day projected to month-end. Alerts: 80% any budget MEDIUM (kanban); 95% CRITICAL (phone). Accept: at-a-glance burn rate.

**5. Post-mortem template `[B]`** — `docs/INCIDENTS/_template.md`, `scripts/start_incident.py`. Fields: title/date/severity/services-affected/detection/timeline/root-cause/remediation/action-items (each links to kanban card). Automation: CRITICAL fires + Nav resolves via phone-callback URL → auto-run start_incident.py with pre-filled detection+timeline. Accept: first real incident gets templated skeleton automatically.

### Skills
`swarmclaw:coding-agent`, `mlops:evaluating-l...`, `hermeshub:agent-hardening`, `devops:react-craco...` (if SLA panel becomes React micro-frontend)

---

## Deployment

In Herder, paste each agent's Round 1 prompt. Each agent watches for its Round 1 completion file (`memory/agent<N>_round1_complete.md`) and auto-loads its Round 2 section here.

Agent 8's kanban tracks transitions in `kanban/SWARM_STATUS.md` — Nav's single dashboard.

**Memory recovery path** if context wipes:
1. `~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/MEMORY.md`
2. `/Users/nav/Documents/GitHub/floww/DISPATCH_PLAN_ORACLE.md` (Round 1)
3. `/Users/nav/Documents/GitHub/floww/DISPATCH_PLAN_ORACLE_ROUND2.md` (this file)
4. `/Users/nav/Documents/GitHub/floww/kanban/SWARM_STATUS.md` (live state)
