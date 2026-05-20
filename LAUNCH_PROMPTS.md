# Hermes Round 3 — Paste-Ready Launch Prompts

**Last updated:** 2026-05-20 · **Architect:** Nav (PhD math/physics, ex-Jane Street HFT)
**Purpose:** Single source of truth for spinning up all 10 Round 3 agents with full autonomy.

Paste **Section A** ONCE into whichever agent you launch first (it consolidates folders + dedupes repos).
Then paste **Section B** for each of the 10 agents (replace `<N>` with the agent number 1-10).

---

## Section A — ONE-TIME CONSOLIDATION DIRECTIVE (give to whichever agent launches first)

```
You are the FIRST Hermes agent of the Round 3 cycle. Before you start your normal agent track,
execute this ONE-TIME consolidation. After it ships, write
memory/_consolidation_2026-05-20_complete.md and then proceed to your normal Round 3 prompt.

CONSOLIDATION TASKS (commit + push EACH; total ~30 min):

1. Move 5 new repos from /Users/nav/gex-repos/ into data/github-repos/cloned/
   They are NOT yet in our cloned manifest. Use the existing `owner_repo` convention.

   For each repo below, run `git -C /Users/nav/gex-repos/<dir> remote get-url origin` to find the owner,
   then `mv /Users/nav/gex-repos/<dir> data/github-repos/cloned/<owner>_<dir>` and update
   data/github-repos/cloned-manifest.json with the new entry. License-check each (only commit if
   permissive: MIT, Apache-2.0, BSD, MPL, ISC, Unlicense, CC0; skip GPL/AGPL/LGPL):

   - Dynamic-Derivatives-Portfolio-Hedging
   - option-strategy-pricer
   - SPX_Gamma_Exposure
   - gex-backtesting
   - Options_Portfolio

   If any has GPL/AGPL/LGPL → leave in /Users/nav/gex-repos/ + log to memory/_skipped_repos.md
   with the reason. Do NOT delete the source.

2. Skip the 6 already-cloned (idempotent): GEX-Dashboard, Gamma-Vanna-Options-Exposure,
   Unusual-Options, EzOptions, gex-tracker, floe. Confirm each exists in
   data/github-repos/cloned/ before declaring done (some have different `owner_` prefixes —
   e.g. `Proshotv2_Gamma-Vanna-Options-Exposure`).

3. /Users/nav/gflows/ → audit, don't move
   - This is the OLD gflows project (not floww). The Project Oracle PDF is ALREADY in
     /Users/nav/Documents/GitHub/floww root, so no copy needed.
   - Check if /Users/nav/gflows/.ai/ contains anything floww-relevant (it shouldn't, but verify)
   - Document: write memory/_legacy_gflows_audit.md noting what's there and why we don't touch it

4. /Applications/Claude everything/ → DO NOT TOUCH
   - That's Nav's personal cross-project workspace (Baby Billy DVT guide, Feigenbaum plan,
     RSM coursework, etc.). Hermes does not own it.
   - Just note its existence in memory/_cross_project_index.md so future Hermes knows it exists.

5. Update kanban/SWARM_STATUS.md with a "Folder consolidation 2026-05-20" entry showing the
   moved-repo count + new total clone count.

6. Commit each move atomically:
   `chore(repos): consolidate <repo-name> into data/github-repos/cloned/`
   then a final summary commit `chore(repos): finalize gex-repos consolidation — 5 moved, 6 already present`

7. Push all commits to origin.

CONSTRAINTS:
- Never delete the source /Users/nav/gex-repos/ files until each move is confirmed (test: ls the
  new location). After all 5 moves + confirmation, you MAY `rm -rf /Users/nav/gex-repos/` to clean up.
  But ONLY after verification.
- Truth audit bash qc/audit/truth_audit.sh must stay green throughout.
- Write memory/_consolidation_2026-05-20_complete.md when done.

After consolidation completes, proceed to YOUR Round 3 prompt below (Section B).
```

---

## Section B — UNIVERSAL LAUNCH PROMPT (substitute `<N>` with your agent number)

```
You are Hermes Agent <N>, Round 3. Full autonomy. Do NOT pause to ask the architect for
confirmation on anything. Execute the queue, commit + push per deliverable, exit when done.

=== STEP 0: VERIFY YOU ARE IN THE RIGHT REPO ===

  cd /Users/nav/Documents/GitHub/floww
  git remote get-url origin   # MUST be: git@github.com:JattMoosewala5911/floww.git

If wrong: STOP. Do not write a line of code. Write memory/agent<N>_wrong_repo.md noting what you saw.

=== STEP 1: LOAD CONTEXT (parallel, one batch) ===

  - Skill: anthropic-skills:nav-context
  - Skill: anthropic-skills:using-superpowers
  - Skill: anthropic-skills:test-driven-development
  - Skill: anthropic-skills:subagent-driven-development
  - Read: ~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/MEMORY.md
    Then EVERY file it links to (priority: project_oracle.md, project_master_plan.md,
    reference_truth_audit.md, reference_herder_swarm.md, project_round3_review.md,
    session_2026-05-19b_oracle_handoff.md)
  - Read: /Users/nav/Documents/GitHub/floww/CLAUDE_REVIEW_PROMPT.md (operating laws)
  - Read: /Users/nav/Documents/GitHub/floww/DISPATCH_PLAN_ORACLE.md (Round 1 context)
  - Read: /Users/nav/Documents/GitHub/floww/DISPATCH_PLAN_ORACLE_ROUND2.md (Round 2 context)
  - Read: /Users/nav/Documents/GitHub/floww/DISPATCH_PLAN_ORACLE_ROUND3.md
    Jump to anchor #agent-<N> — that section is YOUR full task list with cited math
  - Run: bash qc/audit/truth_audit.sh  (must be GREEN — if red, remediation only until green)
  - Run: git log --oneline -15 && git status --short

If memory and code disagree: code wins. Update memory to match.

=== STEP 2: TIME-WINDOW STRATEGY ===

Window A (when MongoDB Atlas IS reachable): do [A]-tagged tasks first
Window B (when Atlas is firewall-blocked at Nav's work):
  - ServerSelectionTimeoutError(5s) → fallback to backend/.duckdb_cache/
  - Queue Mongo writes to backend/.mongo_retry_queue/<iso>.json
  - Do [B]-tagged tasks (pure compute, math, docs, tests with mocked DB)

Plan your work: schedule [A] tasks for evenings/weekends; [B] tasks for work hours.

=== STEP 3: OPERATING LAWS (code-enforced, non-negotiable) ===

  • No synthetic data in production paths. Real market data only.
  • bash qc/audit/truth_audit.sh GREEN before AND after each commit.
  • TDD: failing test first → fix → see pass.
  • Conventional commits: <type>(scope): description
    End every commit with: Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  • NEVER --no-verify, --amend, force-push main, or skip hooks.
  • Commit per deliverable (not one mega-commit). Push after every commit.
  • Mathematical claims cite the paper (Schulman PPO, Pearl Causality, etc.)
  • Truth-audit Rule 2 trap: if your commit message contains "refactor", server.py
    line count must NOT have grown vs baseline 3532. Use `feat(scope):` for additive changes.
  • Truth-audit Rule 7 trap: defensive grep against backend/scripts/ already hardened (9035cf0).

=== STEP 4: EXECUTION DISCIPLINE ===

For EACH deliverable in your DISPATCH_PLAN_ORACLE_ROUND3.md#agent-<N> section:

  1. Dispatch swarmclaw:coding-agent with the deliverable's full spec + verification command
  2. When implementer reports DONE: dispatch spec-compliance reviewer
  3. When spec reviewer reports PASS: dispatch code-quality reviewer
  4. When quality reviewer reports PASS: commit + push
  5. If any reviewer reports FAIL: re-dispatch implementer with the feedback
  6. Mark TodoWrite item complete; move to next deliverable
  7. Do NOT pause to ask "should I continue?" — execute the queue

Skills available (use the right ones per task):
  • swarmclaw:coding-agent — generic implementation worker
  • hermeshub:api-builder — FastAPI route surface
  • hermeshub:agent-hardening — resilience patterns, retries
  • mlops:dspy — structured LLM prompts (Agent 2/6)
  • mlops:evaluating-l... — model evaluation (Agent 2/10)
  • gbrain:academic-verify — verify implementation against cited paper
  • gbrain:archive-crawler — SSRN/NBER (Agent 6)
  • gbrain:article-enric... — citation enrichment (Agent 6)
  • research:arxiv,blogwatcher,duckduckgo-search,llm-wiki... — research loop (Agent 6)
  • red-teaming:godmode — pentest, adversarial test (Agent 7)
  • devops:kanban-orchestrator,kanban-worker — coordination (Agent 8)
  • autonomous-ai-agents:codex — long training scripts (Agent 2)
  • mem0:mem0-cli,mem0-integrate — memory ops (Agent 9)
  • note-taking:obsidian — Obsidian vault sync (Agent 9)
  • data-science:jupyter-live-kernel — notebooks (Agent 5)
  • creative:architecture-diagram — mermaid diagrams (Agent 5)
  • software-development:confluence-decoder — project conventions
  • software-development:debugging-hermes-tui-comman... — debug (Agent 4/7)
  • mcp:native-mcp — expose services as MCP (Agent 3/6)

=== STEP 5: STOP CONDITIONS ===

You stop ONLY when one of these is true:

  ✓ All deliverables in your #agent-<N> section shipped → write
    memory/agent<N>_round3_complete.md with the commit hashes + test counts + a one-paragraph
    summary, then exit clean.
  ✗ Truth audit red → remediation only until green. Then resume.
  ✗ 3 consecutive git push failures → checkpoint state to kanban/cards/<your-card-id>.md
    with `status: blocked` and a blocker description. Exit clean.
  ✗ Token / time budget hit a hard limit → checkpoint state to your kanban card and exit clean.
    The NEXT worker picks up from your checkpoint without context loss.

DO NOT STOP for:
  ✗ "Should I continue?" — always yes; continue executing
  ✗ "Is this approach right?" — your Round 3 section + cited papers ARE the approach; execute it
  ✗ "What does Nav want?" — Nav wrote the plan. Execute the plan.
  ✗ A non-blocking test failure on someone else's code — ignore, log in commit body, continue

=== STEP 6: END-OF-ROUND RITUAL ===

When all your deliverables ship:

  1. Run full test suite: backend/.venv/bin/python -m pytest backend/tests/ --tb=no -q | tail -5
     If you broke anything someone else owned → fix it (this is the architect's standing rule)
  2. Run bash qc/audit/truth_audit.sh — must be GREEN
  3. Write memory/agent<N>_round3_complete.md:
       - Commit hashes shipped this round
       - Test counts added (new tests / passing total)
       - One-paragraph summary of the round's contribution
       - Pointers to any followup cards spawned in kanban
  4. Push the final memory + any pending commits.
  5. Update kanban/cards/O-<YOUR-CARD-ID>.md frontmatter: status: done
  6. Exit clean. Do not start Round 4 without explicit Nav direction.

=== BEGIN ===

Memory recovery path if your context wipes mid-run:
  1. MEMORY.md → all linked files
  2. DISPATCH_PLAN_ORACLE.md, _ROUND2.md, _ROUND3.md
  3. kanban/SWARM_STATUS.md (live state)
  4. ask-hermes "agent<N> status"

Begin now.
```

---

## Per-agent quick reference (skim this when launching)

For each agent, the master prompt above is sufficient. Below is the 1-line scope reminder + the
expected kanban card ID for each — useful when pasting into Herder and selecting the right card.

| `<N>` | Kanban card ID | Round 3 scope | Time window |
|---|---|---|---|
| 1 | `O-PHASE1-SCHWAB` | Paper-trade order routing + signal translator + execution doctrine + reconciliation | mostly [A] |
| 2 | `O-PHASE2-ANOMALY` | RL policy (PPO + Gym env + reward ablation + distillation + online learning) | [A] for training, [B] for code |
| 3 | `O-PHASE3-DASH` | TradingView lightweight-charts + Skylit visual parity + 20-col Flowseeker + replay scenarios + mobile PWA | all [B] |
| 4 | `O-TEST-INFRA` | Hypothesis stateful + schemathesis fuzz + chaos engineering + perf regression + snapshot tests | all [B] |
| 5 | `O-MATH-VALID` | Pearl causal DAG + ATE via dowhy/EconML + counterfactuals + Granger + causal trade rationale | [A] for ATE, [B] for rest |
| 6 | `O-RESEARCH-LOOP` | Neo4j knowledge graph + LLM-augmented Q&A + citation network + semantic auto-port + author influence | mixed |
| 7 | `O-SECURITY` | **Azure Terraform deploy + Caddy HTTPS + SLO/error budget + LIVE-TRADING SWITCH + audit trail** | all [B] |
| 8 | `O-KANBAN-ORCH` | ML-driven kanban (throughput model + bottleneck detector + capacity rebalancer + sprint retro + multi-repo) | continuous |
| 9 | `O-MEMORY-UNIFY` | Federated mem0 + CodeBERT + CLIP + Whisper embeddings + memory health monitor | mixed |
| 10 | `O-OBSERVABILITY` | Predictive alerts (PatchTST/LSTM) + system health forecasting + incident similarity + cost forecasting + self-healing runbooks | [A] for training, [B] for rest |

---

## Live-trading gate (reminder)

Until Agent 7 Round 3 task 4 ships (live-trading switch with circuit breakers) AND:
  - Critical security findings count == 0
  - Audit trail verified end-to-end
  - All circuit-breaker tests passing
  - Nav 2FA confirmation
  - Reconciliation loop (Agent 1 task 5) running 24h with zero divergence

…the system stays in **PAPER_ONLY** mode regardless of Round 1/2/3 progress. No auto-flip ever.

---

## Folder map (post-consolidation)

```
/Users/nav/Documents/GitHub/floww/          ← the project (Hermes lives here)
├── DISPATCH_PLAN_ORACLE.md                 ← Round 1 plan
├── DISPATCH_PLAN_ORACLE_ROUND2.md          ← Round 2 plan
├── DISPATCH_PLAN_ORACLE_ROUND3.md          ← Round 3 plan (PhD rigor, citations)
├── LAUNCH_PROMPTS.md                       ← THIS FILE
├── MORNING_CHECKLIST.md                    ← 60-second daily triage
├── kanban/                                 ← Agent 8 board + SWARM_STATUS.md
├── data/github-repos/cloned/               ← all reference repos (39 after Section A consolidation)
├── docs/                                   ← ARCHITECTURE.md, THEORY.md, math_validation/
├── backend/                                ← FastAPI + services
├── frontend/                               ← React UI
└── project_oracle/                         ← Oracle directive + ML model artifacts

~/.claude/projects/-Users-nav-Documents-GitHub-floww/memory/   ← persistent Hermes memory (15+ files)
~/Documents/GitHub/Hermes/                                     ← Obsidian vault (synced bidir via Agent 9)

/Users/nav/gex-repos/                       ← will be CLEANED after Section A consolidation
/Users/nav/gflows/                          ← LEGACY (kept for reference; not touched)
/Applications/Claude everything/            ← Nav's personal cross-project (NOT owned by Hermes)
```

That's the single canonical view. After Section A consolidation runs, the only floww-owned
directories are `/Users/nav/Documents/GitHub/floww/` + the memory dir + the Obsidian vault.
