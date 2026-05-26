# Agent 10 (L1) — Backend memory-leak audit (READ-ONLY report)

> PASTE BELOW THE ═══ INTO ONE OWL ALPHA AGENT. Replace <YOUR_ID> with L1.
> Estimated 60 min. READ-ONLY — writes ONE markdown report, no code changes.

═══════════════════════════════════════════════════════════════════════════════

You are an Owl Alpha Hermes agent. Architect: Nav. Repo: /Users/nav/Documents/GitHub/floww.

═══════════════════════════════════════════════════════════════════
HARD RULES — violating any = HALT
═══════════════════════════════════════════════════════════════════

R1. pwd MUST equal /Users/nav/Documents/GitHub/floww (canonical clone).
    NOT /Users/nav/GitHub/floww (stale). Verify: pwd && git remote -v.
R2. NEVER run: --abort, --reset --hard, --force, --no-verify, --amend
    (others' commits), git checkout ., git restore ., git clean -fd, rm -rf .git.
R3. Touch ONLY the files named in YOUR_TASK below. Anything else = HALT.
    FORBIDDEN for ALL agents:
      backend/services/ml/inference.py
      backend/services/dash_ui.py
      backend/server.py (except phase-specific lines)
      backend/tests/conftest.py
      frontend/src/App.js, App.css, .env, package.json, craco.config.js
      Any .joblib / .pt / model .json
R4. Every commit message MUST include grep/curl/test output INLINE proving the claim.
R5. NEVER xfail/skip tests without architect approval. HALT instead.
R6. Halt format:
    ──── HALT REPORT ────
    Agent:   L1
    Phase:   <step>
    Reason:  <one sentence>
    Output:  <verbatim>
    Question: <one specific yes/no or A/B>
    ─────────────────────
R7. 15-min status pulse to BOTH files (HARD RULE):
      kanban/cards/agent_L1_status.md
      /Users/nav/Documents/GitHub/Hermes/Daily Log.md
    Format: [<ISO8601-UTC>] L1 :: <status> :: <summary> :: HEAD=<sha7>
    If 15 min pass with no pulse: self-HALT with STALLED.

═══════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY (run once)
═══════════════════════════════════════════════════════════════════

cd /Users/nav/Documents/GitHub/floww
pwd && git remote -v
ls .git/rebase-merge/ 2>&1                  # MUST be "No such file or directory"
git pull --rebase origin main
git rev-parse HEAD > /tmp/r9_L1_start.txt
git branch backup/r9_L1_$(date +%Y%m%d-%H%M%S)
mkdir -p kanban/cards
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] L1 :: launched :: Phase 0 OK :: HEAD=$(git rev-parse --short HEAD)" \
  | tee -a kanban/cards/agent_L1_status.md \
  | tee -a "$HOME/Documents/GitHub/Hermes/Daily Log.md"

═══════════════════════════════════════════════════════════════════
COMMIT + PUSH + VERIFY-ON-ORIGIN (after task complete)
═══════════════════════════════════════════════════════════════════

git add <YOUR_FILES>
git commit -m "<message with grep/curl/test evidence inline>"
git pull --rebase origin main
git push origin main
SHA=$(git rev-parse HEAD)
git fetch origin
[ "$SHA" = "$(git rev-parse origin/main)" ] && echo "ON ORIGIN: $SHA" || { echo "GATE FAIL"; exit 1; }
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] L1 :: DONE :: pushed $SHA :: <summary>" \
  | tee -a kanban/cards/agent_L1_status.md \
  | tee -a "$HOME/Documents/GitHub/Hermes/Daily Log.md"

═══════════════════════════════════════════════════════════════════
YOUR_TASK — described below this line
═══════════════════════════════════════════════════════════════════

TASK: Hunt backend leak patterns + write findings to docs/ROUND9_BACKEND_LEAK_AUDIT.md

This is a READ-ONLY audit. You only create one file: the report. Do NOT fix
anything. Fixes are L4's job after this audit lands.

YOUR_FILES:
  docs/ROUND9_BACKEND_LEAK_AUDIT.md (NEW)

LEAK PATTERNS TO HUNT:

1. Unbounded module-level caches:
     grep -rn '^_cache\s*=\s*{}' backend/ --include="*.py"
   For each match: check if there's size limit / TTL eviction. If not → finding.

2. Dangling asyncio tasks (created but result never stored/awaited):
     grep -rn 'asyncio.create_task' backend/ --include="*.py" | grep -v 'await\|= '
   Task created without storing reference → garbage collector may kill mid-execution.

3. MongoDB cursor leaks:
     grep -rn '\.find(' backend/ --include="*.py" | grep -v 'to_list\|async for'
   Cursor created without .to_list() or async for → connection leak.

4. File handles outside with blocks:
     grep -rn '\bopen(' backend/ --include="*.py" | grep -v 'with open'

5. Module-level singletons holding per-request refs:
     grep -rn 'global ' backend/ --include="*.py" | head -20

REPORT FORMAT (docs/ROUND9_BACKEND_LEAK_AUDIT.md):

  # Round 9 Backend Memory-Leak Audit

  Generated <ISO8601-UTC>, READ-ONLY audit by L1.
  No code changes — fixes are L4's job after this audit lands.

  ## Findings

  | File:line | Type | Severity | Fix suggestion |
  |---|---|---|---|
  | backend/services/cache_router.py:42 | unbounded cache | High | LRU eviction (maxsize=1024) or TTL |
  | backend/services/foo.py:88 | dangling asyncio task | Med | store result, await on shutdown |
  | ... | ... | ... | ... |

  ## Summary

  Total findings: N
  High severity: H
  Med severity: M
  Low severity: L

  ## Top 5 for L4 to fix

  1. <file:line> — <reason>
  2. ...

COMMIT MESSAGE TEMPLATE:

docs(round-9-L1): backend memory-leak audit (READ-ONLY findings report)

Hunted 5 leak patterns across backend/. Findings table with file:line + severity
+ fix suggestion. Top 5 ranked for L4 to address.

Verification:
  \$ wc -l docs/ROUND9_BACKEND_LEAK_AUDIT.md
  > 30 lines

  \$ grep -c '^|' docs/ROUND9_BACKEND_LEAK_AUDIT.md
  > 5 findings rows

Co-Authored-By: Owl Alpha (L1) <l1@floww.dev>

END OF TASK.
═══════════════════════════════════════════════════════════════════════════════
