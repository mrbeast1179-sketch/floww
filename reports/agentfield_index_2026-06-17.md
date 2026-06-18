# AgentField Migration — Reading-Order INDEX (2026-06-17)

**Date:** 2026-06-17  •  **Repo:** `/Users/nav/Documents/GitHub/floww`  •  **Branch:** `main` (HEAD = `2ad47ae`)

This INDEX is the entry point for the four additive AgentField commits shipped 2026-06-17. It pins a reading order across the three evidence reports + adds how-to-trace commands + open audit gaps. Future readers can grasp the migration arc without stepping through `git show` invocations one at a time.

**Inherited disclosures.** All upstream disclosures from `./agentfield_poc_2026-06-17.md`, `./agentfield_poc_with_go_controlplane_2026-06-17.md`, and `./agentfield_consolidated_diff_2026-06-17.md` are inherited verbatim; this INDEX introduces no new disclosures.

**Living doc.** Canonical as of HEAD = `2ad47ae` (post-amend of the conventional-commits adapter commit). Future additive commits should update the reading-order table + cumulative numbers (top of "What each report contains") + the iter-3 gap claim (Open gaps §1).

---

## Reading order (recommended)

Read in this order; each step adds context used in the next.

| # | SHA | Subject | Report |
|---|---|---|---|
| 1 | `72dee2c` | feat(integrations/agentfield): additive bs_greeks AgentField reasoner PoC | [`reports/agentfield_poc_2026-06-17.md`](./agentfield_poc_2026-06-17.md) |
| 2 | `f6a6bc4` | feat(integrations/agentfield): iter-2 register bs_agent with real Go control plane (:8080) | [`reports/agentfield_poc_with_go_controlplane_2026-06-17.md`](./agentfield_poc_with_go_controlplane_2026-06-17.md) |
| 3 | `8581c1d` | chore(reports): add iter-1 AgentField PoC evidence report (evidence-only) | (this commit IS iter-1's evidence report — see #1) |
| 4 | `a4a991e` | feat(integrations/agentfield): add bs_vomma reasoner (∂²Price/∂σ² higher-order Greek) | **gap — no dedicated evidence report** (see Open gaps). Widens the dispatch surface from `{bs_quote}` to `{bs_quote, bs_vomma}` — both reasoners are co-registered on the same `floww_greeks` node and both appear in `GET :8080/api/v1/discovery/capabilities`. |
| 5 | (meta) | docs(reports): add consolidated side-by-side per-commit diff for the 4 AgentField SHAs | [`reports/agentfield_consolidated_diff_2026-06-17.md`](./agentfield_consolidated_diff_2026-06-17.md) |
| 6 | (meta) | chore(tools): add cz_customize adapter for conventional-commits enforcement | `/Users/nav/Documents/GitHub/floww/.cz.toml` (repo root) |

The first 4 SHAs are the **substantive** additive commits. The last 2 SHAs are **meta** — meta-reports and commit-lint tooling that documents / constrains the migration. Read 1→4 first (substantive), then 5→6 (meta).

---

## What each report contains

### `agentfield_poc_2026-06-17.md` — iter-1

Iter-1 ships a standalone `Agent(node_id="floww_greeks", dev_mode=True)` that wraps the existing read-only `backend/bs_greeks.py` as a single `@app.reasoner` (`bs_quote(kind, S, K, T_years, sigma, r=0.045, q=0.0) -> dict`). Because no Go toolchain is present in this environment, a **co-located** `/api/v1/execute/{node}.{func}` proxy is mounted on the Agent itself — it forwards into the Agent's own `_reasoner_registry` with the same dispatch logic the upstream Go control plane uses, only the dispatch location differs. Direct `uvicorn.run(...)` is used in place of `app.serve(port=...)` to bypass the `KeyError: 'websockets-sansio'` mismatch with `uvicorn 0.25.0` + `websockets 16.0` from the backend venv.

**Evidence:** 3 pytest scenarios PASSED in-process; 4 live curl scenarios against `:8002` (call@spot, 25-DTE 5-OTM put, 404-unknown, S=-1 degenerate); verbatim SDK `reasoner.started` / `reasoner.completed` log entries.

### `agentfield_poc_with_go_controlplane_2026-06-17.md` — iter-2

Iter-2 ships the same `bs_quote` reasoner wired against the **real** AgentField Go control plane on `:8080` (bring-up: `brew install go` + `~/GitHub/agentfield/control-plane` + `go run ./cmd/af dev --port 8080`). The co-located proxy from iter-1 is fully removed (not feature-flagged); an `@app.on_event("startup")` hook calls `app.agentfield_handler.register_with_agentfield_server(8002)` + `start_heartbeat()` against the Go plane. `dev_mode` is flipped to `False` for cleaner workflow logs.

**Evidence:** CP startup log (SQLite migrations 007–015, FTS5-degraded banner); agent registration log (`Registered node 'floww_greeks' ...`); 8 curl scenarios A–H against both `:8080` (CP) and `:8002` (agent); discovery `/api/v1/discovery/capabilities` payload showing `floww_greeks` with `bs_quote` registered.

**Five disclosures:** (1) gRPC :8180 stale-port collision after first run, fix is `rm -rf /tmp/agentfield_poc/* && afcp server ...`; (2) `app.connection_manager` not auto-started by direct `uvicorn.run(...)` — push WebSocket triggers unavailable, curl-driven dispatch works; (3) `/Users/nav/.local/bin/python` shim required for CP's `python` shell-out; (4) compat proxy from iter-1 fully removed, not feature-flagged; (5) CP fell back to SQLite (not BoltDB) due to YAML `database_path` defaulting to empty string.

### `agentfield_consolidated_diff_2026-06-17.md` — consolidated

A single side-by-side per-file diff table that consolidates the four SHAs. Numeric columns (Lines added / removed, Files Changed, Insertions / Deletions) come verbatim from `git show --numstat` and `git show --shortstat`. Behavioural-delta paragraphs are pull-quotes distilled from iter-1 / iter-2 reports and the docstrings on `bs_agent.py` itself.

**Cumulative additive footprint:** 10 file-touches, **+1206 / −204**, 6 NEW files, all under `integrations/agentfield/` + `reports/`. Pure additive — no edits to `backend/`, `frontend/`, `kanban/`, or `project_oracle/`.

This is the report to read if you want a one-stop overview of the migration arc.

### `.cz.toml` (commit-lint enforcement)

The four SHAs are formatted as conventional-commits subjects (feat / fix / chore / docs / refactor + optional `(scope)` + optional `!` + `:` + space + imperative subject). `.cz.toml` at the repo root configures `commitizen`'s `cz_customize` adapter to enforce this shape — every new commit subject must `re.fullmatch` against the `commit_parser` regex. Pre-existing legacy commits with non-conventional subjects (e.g. `Initial commit`, `auto-commit for <UUID>`, `type(mypy): strict 4 scripts...`) are NOT retroactively rewritten.

---

## Cross-references — single sources of truth

- **`bs_agent.py` module docstring is the canonical active-iteration dispatch path.** Iter-1's docstring describes the co-located proxy; iter-2's describes the real control-plane registration. If report prose contradicts the docstring, **trust the docstring**.
- **`backend/bs_greeks.py` is the upstream of `bs_quote` (and now `bs_vomma`).** The Agent adapter does not duplicate pricing logic; it forwards calls through the existing module so updates propagate.
- **`logs/integrations/agent_runtime.log`** is the canonical runtime log for the Agent. **`logs/integrations/agentfield_cp.log`** is the canonical runtime log for the Go control plane. Both are append-only audit trails.

---

## How to trace any claim back to source

```bash
cd /Users/nav/Documents/GitHub/floww

# Numeric claims (line counts)
git show --numstat <SHA>            # per-file added/removed
git show --shortstat <SHA>          # commit-level totals
git diff --stat <SHA>~1 <SHA>       # full per-file diff + summary line

# Document claims (subject / author / date)
git log --format='%H | %s | %an <%ae> | %ad' -1 <SHA>

# Behavioural claims (e.g. "the proxy was removed in iter-2")
git show f6a6bc4:integrations/agentfield/bs_agent.py | head -80

# Curl-response claims (e.g. "bs_call_price(100,100,1,0.2) = 10.18611055")
grep -n 'bs_call_price' backend/bs_greeks.py               # source-of-truth function in upstream
open reports/agentfield_poc_2026-06-17.md                  # iter-1 § "Server-based curl evidence" → §A
# The report quotes server output; the grep shows the formula. Both must agree.
```

---

## Open gaps (intentional, not regressions)

- **iter-3 (`a4a991e` `feat(integrations/agentfield): add bs_vomma`) does not have a dedicated evidence report.** The closest pickup item — composing `reports/agentfield_poc_bs_vomma_2026-06-17.md` mirroring iter-1 / iter-2's structure (PoC overview + Disclosures + pytest / curl evidence + Anti-skip gate + Environment snapshot + Reproduce) would close the audit trail for the 4th SHA. The consolidated-diff row `#4` already covers the per-file numeric columns but the live test-curl evidence is missing.
- **Push-style WebSocket triggers (CP → agent) are not exercised.** Iter-2 disclosure #2. A future iter-4 would fork `app.serve()` and patch the `ws="auto"` kwarg so `app.connection_manager` starts automatically under `uvicorn.run(...)`.
- **The pre-compat-proxy code paths are fully removed (not feature-flagged)** — iter-2 disclosure #4. Any client still pointing at `/api/v1/execute/{node}.{func}` on `:8002` will see `404` (curl-evidence in iter-2's section 3.4H). Clients must migrate to `:8080/api/v1/execute/...` once `af dev` is up.

---

## Forward-looking (suggested next shrinks)

- **Compose the iter-3 evidence report** (gap item above) — closes the 4-SHA audit trail.
- **Audit the whole floww repo** for other legacy compat layers that could similarly be replaced by real-dispatch upstream services; the consolidated-diff `verification matrix` is a starting checklist.
- **Tag a release once `cz bump` can succeed.** Today there's no git tag, so `cz changelog` returns empty — the first `cz bump --first-version=0.1.0` would seed the version audit trail.

---

## Reproduce (this INDEX)

```bash
cd /Users/nav/Documents/GitHub/floww

# 4 SHAs in chronological order
git log --oneline 2090178..HEAD -- 'integrations/agentfield/*' 'reports/agentfield*'

# Per-SHA numstat
for sha in 72dee2c f6a6bc4 8581c1d a4a991e; do
  echo "=== $sha ==="
  git show --numstat --no-color --format= "$sha"
done
```
