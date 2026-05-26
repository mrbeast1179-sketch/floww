# Agent 01 (H6) — useMarketData fetch timeout fix

> PASTE EVERYTHING BELOW THE ═══ LINE INTO ONE HERMES OWL ALPHA AGENT.
> Replace every occurrence of `<YOUR_ID>` with `H6` before pasting (or after, in Hermes).
> Estimated 20 min.

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
    Agent:   H6
    Phase:   <step>
    Reason:  <one sentence>
    Output:  <verbatim>
    Question: <one specific yes/no or A/B>
    ─────────────────────
R7. 15-min status pulse to BOTH files (HARD RULE):
      kanban/cards/agent_H6_status.md
      /Users/nav/Documents/GitHub/Hermes/Daily Log.md
    Format: [<ISO8601-UTC>] H6 :: <status> :: <summary> :: HEAD=<sha7>
    If 15 min pass with no pulse: self-HALT with STALLED.

═══════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY (run once)
═══════════════════════════════════════════════════════════════════

cd /Users/nav/Documents/GitHub/floww
pwd && git remote -v
ls .git/rebase-merge/ 2>&1                  # MUST be "No such file or directory"
git pull --rebase origin main
git rev-parse HEAD > /tmp/r9_H6_start.txt
git branch backup/r9_H6_$(date +%Y%m%d-%H%M%S)
mkdir -p kanban/cards
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H6 :: launched :: Phase 0 OK :: HEAD=$(git rev-parse --short HEAD)" \
  | tee -a kanban/cards/agent_H6_status.md \
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
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H6 :: DONE :: pushed $SHA :: <summary>" \
  | tee -a kanban/cards/agent_H6_status.md \
  | tee -a "$HOME/Documents/GitHub/Hermes/Daily Log.md"

═══════════════════════════════════════════════════════════════════
YOUR_TASK — described below this line
═══════════════════════════════════════════════════════════════════

TASK: Replace fetch(url, { timeout: 30000 }) with AbortSignal.timeout(30000)

The `timeout` option is NOT in the browser Fetch API spec — browsers silently
ignore it. Result: requests can hang indefinitely. Fix uses AbortSignal.timeout
which IS standard.

YOUR_FILES:
  frontend/src/hooks/useMarketData.js
  (+ any other hook found via grep — see step 3)

STEPS:

1. Read frontend/src/hooks/useMarketData.js. Find the fetch() call around line 124.
   Current pattern: fetch(url, { signal: controller.signal, timeout: 30000 })

2. Replace with combined-signal pattern:
     const timeoutSignal = AbortSignal.timeout(30000);
     const combinedSignal = AbortSignal.any([controller.signal, timeoutSignal]);
     const res = await fetch(url, { signal: combinedSignal });

3. Check for the same pattern in other hooks:
     grep -rn 'timeout: [0-9]' frontend/src/hooks/
   Fix every match the same way. (If there are none beyond useMarketData, that's fine.)

4. Verify zero remaining:
     grep -rn 'timeout: [0-9]' frontend/src/hooks/
   MUST return empty.

5. Verify React still compiles (wait 12s for CRA hot-reload):
     sleep 12 && tail -10 /tmp/react_decoder.log 2>/dev/null || tail -10 /tmp/react_pwa.log 2>/dev/null
   MUST show "Compiled successfully" or "webpack compiled successfully" near bottom.
   If "Failed to compile" appears: HALT and revert.

COMMIT MESSAGE TEMPLATE:

fix(round-9-H6): useMarketData fetch timeout → AbortSignal.timeout

The fetch() option timeout:30000 is not in browser Fetch API spec and was
being silently ignored, allowing requests to hang indefinitely. Replaced with
AbortSignal.timeout() combined with the existing user-cancel signal via
AbortSignal.any().

Affects CharmChart, VannaChart, and any other component using useMarketData.

Verification:
  \$ grep -rn 'timeout: [0-9]' frontend/src/hooks/
  (empty — all instances replaced with AbortSignal.timeout)

  \$ grep -c 'AbortSignal.timeout' frontend/src/hooks/useMarketData.js
  1

  \$ tail -3 /tmp/react_decoder.log
  webpack compiled successfully

Co-Authored-By: Owl Alpha (H6) <h6@floww.dev>

END OF TASK. Run commit + push + verify-on-origin block above. Then STOP.
═══════════════════════════════════════════════════════════════════════════════
