# Project Oracle — Multi-Agent Dispatch Plan

**Date:** 2026-05-19 · **Owner:** Nav · **Architect:** Hermes / Claude Code
**Purpose:** Standing playbook for running 6–10 autonomous agents in parallel on the floww/Project Oracle codebase via Herder. Each track is bounded, file-disjoint with siblings, and self-contained.

This file is durable. Even if session memory wipes, the next architect can resume from this document alone.

---

## The regime

Project Oracle Phase 2 (math kernels) is **complete and validated**. The architect's role now is:

1. Direct **6–10 agents** running **2–4 hour autonomous tracks** in parallel
2. Use **Herder skills** (swarmclaw / kanban-codex / hermes-agent / etc.) for swarm coordination
3. Maintain memory continuity via `~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/` + Obsidian vault
4. Push commits as they land — never accumulate uncommitted work across sessions

Operating laws from `CLAUDE_REVIEW_PROMPT.md` + `project_oracle.md` are still in force (no synthetic data in production, truth-audit gated, no `--no-verify` / `--amend`, conventional commits).

---

## Agent roster (10 tracks)

### Tier 1 — Foundation completion (Phase 1 + Phase 3 polish)

#### Agent 1 — Schwab WebSocket → DuckDB live pipeline (3–4h)
- **Files:** `backend/services/schwab_streamer.py` (new), `backend/services/ingestion_pipeline.py` (new), `backend/services/mock_schwab_feed.py` (new), `backend/tests/services/test_ingestion_pipeline.py` (new)
- **Skills powering:** `swarmclaw:coding-agent` (the worker), `hermeshub:api-builder` (route surface), `software-development:confluence-decoder` (project conventions), `mem0:mem0-integrate` (cross-session memory)
- **Reference repo:** `tylerebowers/Schwabdev` (clone into `data/github-repos/cloned/` if not present via `scripts/clone_and_extract.py`)
- **Deliverable:** real WS feed pushing into DuckDB at 50ms batch intervals; mock feed for CI; 15+ tests

#### Agent 3 — Dash UI real-time data binding (3–4h)
- **Files:** `backend/services/dash_ui.py` (extend), `backend/tests/services/test_dash_ui.py` (new)
- **Skills powering:** `swarmclaw:coding-agent`, `creative:architecture-diagram` (for the Heatseeker layout sketches), `mlops:dspy` (only if dashboards need LLM-shaped explanations)
- **Tabs to make live:** Heatseeker (GEX heatmap + King Nodes + Air Pockets), Flowseeker (scrolling ticker), Toxicity Gauge (VPIN+QI), Vol Surface (3D SABR/SVI), Trinity Alignment
- **Deliverable:** /dashboard/ at parity with Skylit's commercial Heatseeker/Flowseeker

### Tier 2 — Advanced ML + research

#### Agent 2 — 1D-CNN anomaly detector training + HuggingFace asset acquisition (2–3h)
- **Files:** `scripts/acquire_hf_assets.py` (new), `scripts/train_anomaly_detector.py` (new), `scripts/validate_anomaly_detector.py` (new), `backend/tests/services/test_anomaly_training.py` (new), `./project_oracle/models/` (new dir), `./project_oracle/datasets/` (new dir)
- **Skills powering:** `mlops:dspy`, `mlops:evaluating-l...`, `mlops:audiocraft-audio-generation` (if signal-processing techniques transfer), `gbrain:academic-verify` (validate model claims)
- **HuggingFace targets:** PatchTST, Informer, Autoformer (forecasting); 1D-CNN AE, Transformer-AE (anomaly); DeepLOB, LiT, Neural Hawkes (LOB); FI-2010 dataset
- **Deliverable:** trained AE checkpoint, threshold calibrated to 95th percentile reconstruction error, recall ≥ 95% on injected toxicity

#### Agent 6 — Continuous autonomous research loop (4–6h, restart daily)
- **Files:** `data/external_research/*.json` + `*.md`, `data/github-repos/cloned/*` (new clones), `memory/research_digest_<date>.md` (new daily)
- **Skills powering:** `research:arxiv`, `research:blogwatcher`, `research:duckduckgo-search`, `research:llm-wiki...`, `gbrain:academic-verify`, `gbrain:archive-crawler`, `gbrain:article-enric...`, `hermeshub:arxiv-watcher`
- **Loop:** discover arxiv → extract code URLs → clone → license check → port-recommendation digest → HuggingFace search every 2h → daily digest every 4h
- **Cadence:** continuous; rate-limit conscious (≤30 arxiv/hour, ≤60 GH API/hour)

### Tier 3 — Quality and infrastructure

#### Agent 4 — Test infrastructure: close remaining 14 event-loop failures (2h)
- **Files:** `backend/tests/conftest.py` (extend), `backend/tests/test_portfolio.py` (convert to AsyncClient), `backend/tests/test_v3_costsave.py` (same), `backend/tests/test_heatseeker_v2.py` (same)
- **Skills powering:** `swarmclaw:coding-agent`, `software-development:debugging-hermes-tui-comman...`, `hermeshub:agent-hardening`
- **Diagnosis:** singleton in `backend/data_providers.py` (likely a `RateLimiter` with `asyncio.Lock` baked in at module load) holds stale loop ref
- **Deliverable:** 581 pass / 0 fail / 15 skipped + CI coverage gate at 70%

#### Agent 5 — Mathematical validation + ARCHITECTURE.md + RUNBOOK.md (2–3h)
- **Files:** `backend/tests/services/test_microstructure_math.py` (extend), `ARCHITECTURE.md` (new), `RUNBOOK.md` (new), `docs/api/openapi.json` (new), `docs/api/README.md` (new), `docs/notebooks/oracle_walkthrough.ipynb` (new)
- **Skills powering:** `gbrain:academic-verify`, `data-science:jupyter-live-kernel`, `creative:architecture-diagram` (data-flow mermaid diagrams), `software-development:confluence-decoder`
- **Validation gaps:** node lifecycle state machine, MarketFragilityIndex composite, anomaly detector recall, Trinity (2 skipped tests now know the signature), GEX zero-gamma detection, VolSurfaceConstructor term structure monotonicity

### Tier 4 — Security and hardening (new — uses red-teaming skills)

#### Agent 7 — Security audit / godmode red-team pass (2–3h)
- **Files:** `SECURITY_AUDIT.md` (extend), `qc/audit/security_*.sh` (new), `backend/middleware/` (potentially new)
- **Skills powering:** `red-teaming:godmode`, `hermeshub:agent-hardening`
- **Scope:** Before any live Schwab connection, audit:
  - .env exposure (already fixed historically but verify; `git log --all --full-history -- backend/.env`)
  - All routes for auth/authz gaps (mutating endpoints especially)
  - Rate-limiter resilience (race conditions, bypass paths)
  - Input validation on every POST/PUT/PATCH (Pydantic models present?)
  - CORS configuration (no `*` with credentials)
  - WebSocket auth (the new `/ws/{topic}` endpoint must authenticate)
  - Mongo/Schwab credential handling in process memory
  - Dash UI access control (anyone on the LAN should not see Schwab data)
- **Deliverable:** SECURITY_AUDIT.md updated with findings + severity (Critical / High / Medium / Low) + concrete fixes for Criticals + Highs

### Tier 5 — Coordination and continuity

#### Agent 8 — Kanban orchestrator + agent-hardening continuous loop (background)
- **Files:** `kanban/board.yaml` (new), `kanban/cards/*.md` (new), `kanban/closed/*.md` (new)
- **Skills powering:** `devops:kanban-orchestrator`, `devops:kanban-worker`, `autonomous-ai-agents:kanban-codex-...`, `hermeshub:agent-hardening`
- **Job:** pulls tasks from the kanban board, dispatches to swarm workers, tracks completion, archives done cards. Acts as the persistent coordinator so Nav doesn't have to manually dispatch — Agent 8 watches the board and assigns idle workers.
- **Deliverable:** auto-scheduling kanban workflow that survives Nav going to sleep

#### Agent 9 — Obsidian bidirectional sync + memory unification (1–2h, then continuous lightweight)
- **Files:** `scripts/obsidian_sync.py` (new), `~/Obsidian-Vault/floww/*.md` (write), `~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/*.md` (read/write)
- **Skills powering:** `note-taking:obsidian`, `honcho:honcho-memory`, `plur:plur-memory`, `mem0:mem0-cli`, `mem0:mem0-integrate`
- **Job:** Reconcile the three memory systems (honcho / plur / mem0) into one canonical surface. Bidirectionally sync Claude Code memory dir ↔ Obsidian vault. When Nav adds a note in Obsidian, it flows to memory; when an agent updates memory, it flows to Obsidian.
- **Deliverable:** one-way-of-doing-memory; pick mem0 OR honcho OR plur (recommend mem0 — most mature in the ecosystem) and migrate everything to it

#### Agent 10 — Observability + alerting (2–3h)
- **Files:** `backend/services/observability.py` (new), `docker-compose.observability.yml` (new), Prometheus/Grafana configs
- **Skills powering:** `swarmclaw:coding-agent`, `devops:react-craco...` (if frontend metrics dashboard), `mlops:evaluating-l...`
- **Scope:** Prometheus metrics endpoints, Grafana dashboards for: messages/sec ingested, DuckDB queue depth, VPIN current value per ticker, Trinity score, anomaly detector latency, FastAPI request rate + p99 latency
- **Deliverable:** `docker-compose up observability` brings Prometheus + Grafana with pre-built Oracle dashboards

---

## Skill → Agent map (Herder dispatch reference)

| Herder skill | Used by | Why |
|---|---|---|
| `swarmclaw:coding-agent` | 1, 3, 4, 7, 10 | Generic implementation worker |
| `swarmclaw:nano-banana-pro` | (visual assets if needed) | Image generation for dashboard mockups |
| `swarmclaw:openai-image-gen` | (visual assets) | Same |
| `autonomous-ai-agents:hermes-agent` | All | Project-aware agent shell |
| `autonomous-ai-agents:claude-code` | 1, 3, 4, 7, 10 | Claude as the worker |
| `autonomous-ai-agents:codex` | 2, 5 | Codex for ML training scripts / docs |
| `autonomous-ai-agents:kanban-codex-...` | 8 | Kanban-driven codex workers |
| `devops:kanban-orchestrator` | 8 | Board management |
| `devops:kanban-worker` | 8 (sub-workers) | Pull-from-board workers |
| `devops:react-craco...` | 10 (frontend dashboards) | React + craco builds |
| `hermes-skill-factory:Skill Factory` | (architect) | Build new skills when gaps surface |
| `hermeshub:agent-hardening` | 4, 7, 8 | Make agents more robust |
| `hermeshub:api-builder` | 1 (ingestion routes), 10 (observability) | FastAPI scaffolding |
| `hermeshub:arxiv-watcher` | 6 | Continuous arxiv monitoring |
| `hermeshub:da...` | TBD | (truncated in screenshot) |
| `mlops:dspy` | 2, 3 (if LLM explanations needed) | DSPy structured prompting |
| `mlops:evaluating-l...` | 2, 10 | Model evaluation |
| `mlops:audiocraft-audio-generation` | (signal-processing transfer) | Sometimes audio DSP transfers to financial DSP |
| `gbrain:academic-verify` | 2, 5, 6 | Verify implementations against papers |
| `gbrain:archive-crawler` | 6 | Bulk paper archive ingestion |
| `gbrain:article-enric...` | 6 | Enrich raw arxiv with citations + summaries |
| `research:arxiv` | 6 | Arxiv API client |
| `research:blogwatcher` | 6 | Quant-finance blog monitoring |
| `research:duckduckgo-search` | 6 | General web search |
| `research:llm-wiki...` | 6 | LLM-augmented Wikipedia lookup |
| `red-teaming:godmode` | 7 | Security audit + penetration techniques |
| `note-taking:obsidian` | 9 | Read/write Obsidian vault |
| `honcho:honcho-memory` | 9 (migration target) | One of the memory backends being evaluated |
| `plur:plur-memory` | 9 (migration target) | Another memory backend |
| `mem0:mem0-cli` | 9 (recommended target) | mem0 CLI |
| `mem0:mem0-integrate` | 9 | mem0 SDK integration |
| `mem0:mem0-test-integration...` | 9 | mem0 test suite |
| `software-development:confluence-decoder` | All | Project-specific conventions for floww |
| `software-development:debugging-hermes-tui-comman...` | 4, 7 | Hermes TUI debug commands |
| `data-science:jupyter-live-kernel` | 5 (notebook tutorial) | Live notebook execution |
| `creative:architecture-diagram` | 5 (ARCHITECTURE.md mermaid) | Diagram generation |
| `mcp:native-mcp` | (if exposing services as MCP) | Make Oracle services MCP-compliant |

Productivity / personal skills (apple-notes / linear / notion / airtable / maps / spotify / etc.) are **out of scope** for the Oracle build — those are for Nav's personal workflow, not the agents'.

---

## Kanban orchestration pattern (Agent 8's job)

Board layout (`kanban/board.yaml`):

```yaml
columns:
  - id: backlog
    title: Backlog
    wip_limit: null
  - id: ready
    title: Ready for swarm
    wip_limit: 20
  - id: in_progress
    title: In progress
    wip_limit: 6   # max 6 concurrent workers
  - id: review
    title: Awaiting architect review
    wip_limit: 4
  - id: done
    title: Done (archive after 24h)
    wip_limit: null

cards:
  - id: O-PHASE1-SCHWAB
    title: Phase 1 — Schwab WS ingestion
    assignee: Agent 1
    skill: swarmclaw:coding-agent + hermeshub:api-builder
    estimate: 3-4h
    dependencies: []
    status: ready
  # ... etc
```

Cards move automatically based on git activity:
- A new commit referencing the card ID in its message → `in_progress`
- Card's deliverable tests passing on CI → `review`
- Architect approval (Nav's manual chop or audit-check) → `done`

Agent 8 watches and assigns. Idle workers pull from `ready`. WIP-limit enforcement prevents 12 agents from trying to run at once.

---

## Failure modes and recovery

| Failure | Detection | Recovery |
|---|---|---|
| Agent stalls > 30min | Kanban card "last update" > 30min ago | Agent 8 marks BLOCKED; routes to architect (Nav) |
| Two agents touch the same file | git push fails with merge conflict | Loser's agent pulls, rebases, retries; if conflict persists, escalate |
| Truth audit goes red | CI red on push | Auto-revert + open a remediation card in `ready` column |
| Mongo/Schwab credential leak | Agent 7 godmode pass | Auto-rotate, force-push history rewrite, alert Nav |
| Token budget exhausted mid-task | Anthropic 429 | Agent persists state to `kanban/cards/<id>.md`, exits clean. Next worker picks up from state. |
| Rate-limited on arxiv/GitHub | Agent 6's request fails | Exponential backoff; queue the request; continue with other topics |

---

## Stop conditions

Each agent stops when:
1. **All deliverables shipped + tests green + pushed.** Move card to `review`.
2. **BLOCKED on something architect-only** (credentials, deployment access, policy decision). Write to `memory/agent<N>_blocker_<date>.md` and pause.
3. **Token / time budget exhausted.** Persist state to its kanban card and exit clean.

Architect (Nav) checks in periodically to:
- Approve `review` cards → move to `done`
- Triage BLOCKED cards
- Adjust priorities by reordering `ready`

---

## What this dispatch does NOT cover

- **Live trading enablement.** Agent 7's security audit must pass first, then a manual decision by Nav.
- **GPU procurement for ML training.** 1D-CNN AE fits on CPU; bigger models (Autoformer / PatchTST fine-tuning) would need a separate decision.
- **Mobile UI.** Oracle is a desktop trader terminal. Mobile is out of scope until commercial users emerge.
- **Productivity-skill workflows** (apple-notes, linear, notion, calendar sync) — those are Nav's personal layer.

---

## Memory pointer

For the next architect: read `~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/MEMORY.md`, then `project_oracle.md`, then this file. That's the full state recovery path.
