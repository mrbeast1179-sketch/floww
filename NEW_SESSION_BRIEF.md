# Hermes — New-Session Brief

**Paste this entire file into the first message of a fresh Claude/Hermes session.**
The recipient will know: who you are, what's been built, what's queued, how to resume.

---

## 1. WHO YOU ARE TALKING TO

**Architect:** Nav (Navdeep Kumar) — PhD-level math + physics + software, ex-Jane-Street-style HFT framing. Email `erenyeager6245@gmail.com`. Currently a Jefferson MRI student graduating Aug 13 2026, learning the Baby Billy DVT 4.5 trading system in parallel, working Dow Chemical shifts. Nav uses voice-to-text shorthand — expect run-on sentences and casual punctuation; don't correct him, just understand.

**Your role (Claude):** Top architect for **Project Oracle / Hermes / floww** — Nav's free open-source clone of Skylit.ai's institutional options analytics platform. You direct an army of 10 autonomous Hermes agents running in Nav's "Herder" orchestrator. You commit and push code, write durable architectural docs, and consolidate memory across sessions.

---

## 2. WHAT THIS PROJECT IS

| | |
|---|---|
| **Project name (interchangeable):** | Hermes = floww = Confluencer Decoder = Project Oracle |
| **Repo:** | `/Users/nav/Documents/GitHub/floww` |
| **Origin:** | `git@github.com:JattMoosewala5911/floww.git` |
| **Stack:** | FastAPI + MongoDB (Atlas) + DuckDB (in-process OLAP) + React + ML (PyTorch/Numba) + Plotly Dash |
| **Goal:** | Match Skylit.ai's commercial Heatseeker/Flowseeker/Atlas/Agent-Hub for free; trade options autonomously |
| **Data sources:** | Schwab (WebSocket), Databento ($125 credits), Polygon, FlashAlpha (81 endpoints), Alpha Vantage, Finnhub, yfinance |
| **Authoritative plan:** | `CLAUDE_REVIEW_PROMPT.md` superseded by `project_oracle.md` (memory) + the "From Concept to Code" PDF at repo root |

---

## 3. STATE OF THE WORLD (as of this brief)

### Phase progress

```
Math kernels (Phase 2)         ████████████████████  95%   ← VPIN/Hawkes/SABR/SVI/Kyle/Amihud all live
Backend services + routes      █████████████████░░░  85%   ← 18 services, 19 route modules, 800+ tests
Dashboard UI (Skylit parity)   ███████████░░░░░░░░░  55%   ← 5-9 Dash tabs; Round 3 Agent 3 brings TV charts
Live ingestion (Schwab → DuckDB) ██████████████░░░░░░  70%   ← Streamer + replay live; needs Nav's L2 entitlement
ML / autonomous trading        ███████░░░░░░░░░░░░░  35%   ← Anomaly+GEX features done; RL policy is Round 3
Production deployment          █████░░░░░░░░░░░░░░░  25%   ← Azure Terraform + HTTPS + live-trading switch all R3
Research → KG pipeline         ████████████░░░░░░░░  60%   ← 200+ papers, 30+ repos; KG is Round 3
Observability + alerts         ███████████████░░░░░  75%   ← Prom+Grafana+Twilio shipped; predictive R3

OVERALL TERMINAL                █████████████░░░░░░░  60-65%
```

### Recent git activity

Last 5 commits (`git log --oneline -5`):
```
c356f81 docs(launch): Round 3 prompts in the cleaner Round 2 format Nav prefers
31cd1e7 docs(launch): comprehensive per-agent Round 3 prompts with full skill mapping
3caee8a docs(launch): paste-ready Round 3 launch prompts + folder consolidation directive
5748960 docs(dispatch): Project Oracle Round 3 dispatch plan — PhD-level rigor
3d1c149 docs(ops): morning checklist — 60-second swarm status review
```

Working tree: clean. `origin/main`: synced 0/0. Truth audit: GREEN (12-15 PASS / 0 FAIL).

---

## 4. THE AGENTS (10 of them)

Each agent owns a kanban card in `kanban/cards/`. They run autonomously in Herder, commit per deliverable, push immediately, exit clean on stop conditions.

| `<N>` | Card ID | Scope (current Round 3 focus) |
|---|---|---|
| 1 | `O-PHASE1-SCHWAB` | Paper-trade execution engine + signal translator + execution doctrine + reconciliation |
| 2 | `O-PHASE2-ANOMALY` | RL policy (PPO + Gym env + reward ablation + distillation + online learning) |
| 3 | `O-PHASE3-DASH` | TradingView lightweight-charts + Skylit visual parity + 20-col Flowseeker + replay scenarios + mobile PWA |
| 4 | `O-TEST-INFRA` | Hypothesis stateful + schemathesis fuzz + chaos engineering + perf regression + snapshot tests |
| 5 | `O-MATH-VALID` | Pearl causal DAG + ATE via dowhy/EconML + counterfactuals + Granger + causal trade rationale |
| 6 | `O-RESEARCH-LOOP` | Neo4j knowledge graph + LLM-augmented Q&A + citation network + semantic auto-port + author influence — **CONTINUOUS** |
| 7 | `O-SECURITY` | Azure Terraform deploy + Caddy HTTPS + SLO/error budget + **LIVE-TRADING SWITCH** + audit trail |
| 8 | `O-KANBAN-ORCH` | ML-driven kanban (throughput model, bottleneck detector, capacity rebalancer, sprint retro) — **CONTINUOUS** |
| 9 | `O-MEMORY-UNIFY` | Federated mem0 + CodeBERT + CLIP + Whisper embeddings + memory health monitor |
| 10 | `O-OBSERVABILITY` | Predictive alerts (PatchTST/LSTM) + system health forecasting + incident similarity + cost forecasting + self-healing runbooks |

**Agent quality assessment:** Genuinely strong. Across this session arc they shipped 30+ commits with TDD discipline, recovered from rate-limit interruptions without losing work, and caught real production bugs (e.g. `calc_trinity_confluence` "missing" sentinel false-alignment). Their main failure mode is rate-limits, not code quality.

---

## 5. KEY ARTIFACTS AT REPO ROOT

These five files are the architect's surface — read them in order to absorb the project:

```
DISPATCH_PLAN_ORACLE.md          Round 1 plan (foundation tracks, 230 lines)
DISPATCH_PLAN_ORACLE_ROUND2.md   Round 2 plan (advancement tracks, 348 lines)
DISPATCH_PLAN_ORACLE_ROUND3.md   Round 3 plan (PhD-rigor continuation, 759 lines, math citations)
LAUNCH_PROMPTS.md                Round 3 paste-ready prompts in clean per-agent format (1240 lines)
MORNING_CHECKLIST.md             60-second daily triage when Nav wakes up
NEW_SESSION_BRIEF.md             ← THIS FILE
```

Plus:
```
docs/ARCHITECTURE.md             High-level system design
docs/ARCHITECTURE_DEEP.md        Latency/memory/failure-mode taxonomy
docs/THEORY.md                   Trading-system theory bible (VPIN, SABR, SVI, Hawkes, Kyle, etc.)
docs/math_validation/INDEX.md    Per-formula correctness verdicts vs reference repos
RUNBOOK.md                       How to operate the system
SECURITY_AUDIT.md                Findings ledger from Agent 7
kanban/SWARM_STATUS.md           Live state of the 10 agents (auto-generated by Agent 8)
kanban/ARCHITECT_BRIEF.md        Auto-refreshed every 4h with decisions needed
```

---

## 6. MEMORY SYSTEM

**Two-tier:**
1. **Persistent Hermes memory:** `~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/` (25+ files; index at MEMORY.md)
2. **Obsidian vault:** `~/Documents/GitHub/Hermes/` (bidirectionally synced by Agent 9 via mem0)

**Canonical mem0 backend** — Honcho + PLUR archived. 303 entries tagged by project (floww / gflows / baby-billy-dvt / personal).

**Query tool:** `ask-hermes "any question"` — semantic search across mem0 + git log + kanban + memory files. Returns top 3 with citations.

---

## 7. SKILLS THE AGENTS USE (Herder skill arsenal)

| Namespace | Key skills |
|---|---|
| `autonomous-ai-agents` | claude-code, codex, hermes-agent, kanban-codex-* |
| `swarmclaw` | coding-agent (the worker), nano-banana-pro, openai-image-gen |
| `devops` | kanban-orchestrator, kanban-worker, react-craco |
| `hermeshub` | agent-hardening, api-builder, arxiv-watcher |
| `mlops` | dspy, evaluating-l..., audiocraft-audio-generation |
| `gbrain` | academic-verify, archive-crawler, article-enric... |
| `research` | arxiv, blogwatcher, duckduckgo-search, llm-wiki... |
| `red-teaming` | godmode (security audit + pentest) |
| `mem0` | mem0-cli, mem0-integrate, mem0-test-integration... |
| `note-taking` | obsidian |
| `software-development` | confluence-decoder, debugging-hermes-tui-comman... |
| `data-science` | jupyter-live-kernel |
| `creative` | architecture-diagram |
| `mcp` | native-mcp |

Reference: `~/.claude/projects/.../memory/reference_herder_swarm.md` for the full intent → skill map.

---

## 8. OPERATING LAWS (code-enforced — non-negotiable)

1. **No synthetic data in production paths** — raises `DegenerateModelError`
2. **Truth audit gates every commit** — `bash qc/audit/truth_audit.sh` must be GREEN before AND after
3. **TDD discipline** — failing test first, then implement, then see it pass
4. **Conventional commits** — `<type>(scope): description` + `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`
5. **NEVER** `--no-verify` / `--amend` / force-push main / skip hooks
6. **Commit per deliverable**, push immediately (don't accumulate)
7. **Math claims cite the paper** (arxiv ID, journal citation, etc.)

---

## 9. TIME-WINDOW STRATEGY (CRITICAL)

```
Window A (Nav home, market closed, infra healthy — typically 6-8h evening blocks):
  • MongoDB Atlas: LIVE
  • Schwab WebSocket: LIVE
  • Use for: data-hungry training, historical backfills, Mongo-dependent integration tests
Window B (Nav at work — Atlas blocked by firewall):
  • Detect via ServerSelectionTimeoutError(timeout=5s)
  • Fall back to backend/.duckdb_cache/ + retry queue at backend/.mongo_retry_queue/
  • Use for: pure-Python work (math, docs, mocked-DB tests, cached-model training)
```

Each Round 3 task in `LAUNCH_PROMPTS.md` is tagged `[A]` or `[B]` so agents schedule themselves.

---

## 10. LIVE-TRADING GATE (immutable)

System stays in **PAPER_ONLY** until ALL of:
- Agent 7 Round 3 Task 4 (live-trading switch with circuit breakers) ships
- Critical security findings count = 0
- Audit trail end-to-end verified (Agent 7 Task 5)
- Agent 1 Task 5 reconciliation loop running 24h with zero divergence
- Nav 2FA confirmation

Then **Nav MANUALLY** flips `OFF → PAPER_ONLY → LIVE_TINY → LIVE_NORMAL → LIVE_FULL`. Never auto-flip.

---

## 11. WHAT'S BEEN BUILT (cumulative across all rounds)

**Round 1 — Foundation (May 18-19)**
- Schwab WebSocket streamer + ingestion pipeline + mock feed
- 1D-CNN anomaly autoencoder trained on real data
- Dash terminal at `/dashboard/` with 5 tabs (Heatseeker, Flowseeker, Toxicity, VolSurface, Trinity)
- Conftest motor-refresh fix (resolved 14 event-loop test failures)
- ARCHITECTURE.md + RUNBOOK.md + API docs + 5 notebook tutorials
- Autonomous research orchestrator (continuous arxiv → clone → extract loop)
- SECURITY_AUDIT.md with severity-tagged findings
- Kanban board + 10 cards + 23 tests + SWARM_STATUS.md watcher
- mem0 migration (303 entries, multi-project tagging)
- Prometheus + Grafana + Oracle dashboards + Twilio phone alerts

**Round 2 — Advancement (May 19-20)**
- L2 book depth subscription + replay engine
- PatchTST VPIN forecaster + Autoformer chain dynamics + ensemble inference
- Atlas tab with overlays + Replay Mode + Agent Hub stub + Nexus stub + mobile polish
- Property-based math tests (hypothesis) + mutation testing + flaky detector
- Reference-repo parity tests (5+ repos validated)
- Math correctness dashboard + THEORY.md (8 sections)
- SSRN/NBER/Quantocracy/AQR source expansion + auto-port capability
- JWT auth middleware + WebSocket auth + secret rotation + pentest + Docker hardening
- Inter-agent messaging + auto-spawn follow-up cards + sprint planner + architect brief
- Daily memory consolidation cron + auto-tagging + ask-hermes CLI
- Meta-anomaly detection + SLA dashboard + cost dashboard + incident template

**Round 3 — PLANNED, not yet executed (in LAUNCH_PROMPTS.md ready to dispatch)**
- Schwab paper-trade order routing + execution doctrine + reconciliation
- PPO RL policy + Gym env + reward ablation + distillation + online learning
- TradingView lightweight-charts + Skylit visual parity + 20-col Flowseeker + mobile PWA
- Hypothesis stateful + schemathesis fuzz + chaos engineering + perf regression + snapshot tests
- Pearl causal DAG + ATE estimation + counterfactual engine + Granger causality + causal trade rationale
- Neo4j knowledge graph + LLM-augmented Q&A + citation network + auto-port v2 + author influence
- Azure Terraform deploy + Caddy HTTPS + SLO tracking + **LIVE-TRADING SWITCH** + compliance audit trail
- ML-driven kanban (throughput model, bottleneck detector, capacity rebalancer, sprint retro)
- Federated mem0 + CodeBERT + CLIP + Whisper embeddings
- Predictive alerts (PatchTST/LSTM) + system health forecasting + incident similarity + cost forecasting + self-healing runbooks

---

## 12. REFERENCE REPOS (39 cloned in data/github-repos/cloned/)

Coverage by domain:
- **GEX:** 6 repos (jay-nilesh-patel_spy-gex-dashboard, Proshotv2_Gamma-Vanna-Options-Exposure, Matteo-Ferrara_gex-tracker, iAmGiG_gex-llm-patterns, FlashAlpha-lab_gex-explained, SPX_Gamma_Exposure)
- **Greeks / BSM:** 5 (boyac_pyOptionPricing, EsterHlav_Black-Scholes, MattL922_implied-volatility, kyosenergy_options-calculator, yzoz_python-option-calculator)
- **Vol surface:** 3 (FullStackCraft_floe, EazyDuz1t_EzOptions, Schwab variant)
- **Hawkes / VPIN:** 2 each
- **Order flow:** 4 (Buzzfund_UnusualOptions, wnnii_Unusual-Options, fintools-ai_mcp-options-order-flow-server, michael-kupa_options-flow)
- **Sentiment:** 2 (shirosaidev_stocksight, alvarobartt_twitter-stock-recommendation)
- **ML / prediction:** 3 (jasti_Stock-Predictor, kaushikjadhav01_Stock-Market-Prediction-Web-App, Andrew-Reis-SMU-2022_Options_Based_Trading)
- **Plus 12 more** (UOA detectors, IV solvers, GEX backtesters, portfolio hedgers, etc.)

**Verdict:** Plenty for current scope. The only gap I'd actively hunt: **LOB simulator** (queue-position-aware backtesting) + **FinRL/TensorTrade** (RL trading framework for Agent 2 head-starts). Agent 6's auto-port loop will surface these naturally.

---

## 13. KNOWN BUGS / GATES (things in flight)

- 2 Obsidian vault files have uncommitted edits (`Daily Log.md`, `Trading Terminal.md`) — Agent 9 sync work; safe to commit anytime
- Live-trading gate (see §10) — biggest blocker; needs Agent 7 R3 + Nav 2FA
- Mongo Atlas blocked at Nav's work Wi-Fi (Window B fallback handles)
- Schwab Level-2 entitlement may not be on Nav's account (Agent 1 Task 1 R3 has fallback to LEVEL_ONE)

---

## 14. HOW TO RESUME (the actual paste prompt)

Paste THIS section into the new session as your first message:

```
You are taking over as architect for the Hermes / floww / Project Oracle project at
/Users/nav/Documents/GitHub/floww. Architect framing: PhD math/physics, ex-Jane Street HFT.

1. Verify repo identity:
   cd /Users/nav/Documents/GitHub/floww && git remote get-url origin
   → must be git@github.com:JattMoosewala5911/floww.git

2. Load context (parallel batch):
   - Skill: anthropic-skills:nav-context
   - Skill: anthropic-skills:using-superpowers
   - Read: ~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/MEMORY.md
     (then every file it links to)
   - Read: /Users/nav/Documents/GitHub/floww/NEW_SESSION_BRIEF.md (this file)
   - Read: LAUNCH_PROMPTS.md, DISPATCH_PLAN_ORACLE.md, _ROUND2.md, _ROUND3.md
   - Read: kanban/SWARM_STATUS.md (live state)
   - Read: MORNING_CHECKLIST.md (60-second triage)
   - Run: bash qc/audit/truth_audit.sh   (must be GREEN)
   - Run: git log --oneline -10

3. Resume as architect. Don't re-explain context — it's all on disk. Continue what's
   queued in LAUNCH_PROMPTS.md / kanban / Nav's most recent message.

State recap when this brief was written:
  - 60-65% complete trading terminal
  - Round 3 is PLANNED but not yet executed (10 prompts ready in LAUNCH_PROMPTS.md)
  - 39 reference repos cloned (plenty)
  - Live trading GATED until Agent 7 R3 task 4 + Nav 2FA
  - 7 Hermes agents alive in Nav's terminal panes (may have changed by now)
  - Truth audit GREEN, working tree CLEAN, origin synced 0/0

The architect's job from here:
  - Dispatch Round 3 agents (LAUNCH_PROMPTS.md is paste-ready)
  - Or pick the highest-leverage single move — Agent 7 R3 (Azure deploy + live-trading switch)
    is the bottleneck for everything else
```

That's the full handoff. New-session Claude reads this brief, knows everything.

---

## 15. ARCHITECT'S OPINION (Nav asked, this is my honest answer)

**Single highest-leverage next move:** Agent 7 Round 3 — Azure deploy + live-trading switch with circuit breakers. The math is done, the UI is good enough for now, the bottleneck is **shipping it**. Every other agent's work is academic until the system runs in production and Nav can actually trade.

**Two-week roadmap if you ran the agents continuously:**
- Days 1-3: Agent 7 Round 3 (deploy + live-trading switch)
- Days 4-6: Agent 1 Round 3 (paper-trade execution) + Agent 2 Round 3 (RL policy)
- Days 7-9: Agent 3 Round 3 (TradingView + visual parity) + Agent 4 Round 3 (chaos + fuzz)
- Days 10-12: Agent 5 Round 3 (causal layer) + Agent 6 Round 3 (Neo4j KG)
- Days 13-14: Polish, end-to-end paper-trade dry-run, security pentest, FLIP THE SWITCH

After that: 30-day paper-trade calibration → LIVE_TINY → scale up if Sharpe holds.

This is doable. Repo is in genuinely good shape. The agents work.

End of brief.
