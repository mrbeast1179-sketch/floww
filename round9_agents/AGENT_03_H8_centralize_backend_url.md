# Agent 03 (H8) — Centralize REACT_APP_BACKEND_URL with fallback

> PASTE BELOW THE ═══ INTO ONE OWL ALPHA AGENT. Replace <YOUR_ID> with H8.
> Estimated 45 min.

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
    Agent:   H8
    Phase:   <step>
    Reason:  <one sentence>
    Output:  <verbatim>
    Question: <one specific yes/no or A/B>
    ─────────────────────
R7. 15-min status pulse to BOTH files (HARD RULE):
      kanban/cards/agent_H8_status.md
      /Users/nav/Documents/GitHub/Hermes/Daily Log.md
    Format: [<ISO8601-UTC>] H8 :: <status> :: <summary> :: HEAD=<sha7>
    If 15 min pass with no pulse: self-HALT with STALLED.

═══════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY (run once)
═══════════════════════════════════════════════════════════════════

cd /Users/nav/Documents/GitHub/floww
pwd && git remote -v
ls .git/rebase-merge/ 2>&1                  # MUST be "No such file or directory"
git pull --rebase origin main
git rev-parse HEAD > /tmp/r9_H8_start.txt
git branch backup/r9_H8_$(date +%Y%m%d-%H%M%S)
mkdir -p kanban/cards
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H8 :: launched :: Phase 0 OK :: HEAD=$(git rev-parse --short HEAD)" \
  | tee -a kanban/cards/agent_H8_status.md \
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
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H8 :: DONE :: pushed $SHA :: <summary>" \
  | tee -a kanban/cards/agent_H8_status.md \
  | tee -a "$HOME/Documents/GitHub/Hermes/Daily Log.md"

═══════════════════════════════════════════════════════════════════
YOUR_TASK — described below this line
═══════════════════════════════════════════════════════════════════

TASK: Stop "undefined/api/..." network calls when REACT_APP_BACKEND_URL is missing

16+ files reference process.env.REACT_APP_BACKEND_URL directly. When the env
var is missing (e.g., production deploys without .env), the value is undefined,
so \`\${BACKEND_URL}/api\` becomes "undefined/api/..." → real HTTP calls to a
URL containing the literal string "undefined" → blank panels.

YOUR_FILES:
  frontend/src/config/api.js (NEW)
  + every file in: grep -rln 'REACT_APP_BACKEND_URL' frontend/src/
  EXCEPT frontend/src/App.js (FORBIDDEN — leave it alone, document exclusion)

STEPS:

1. Find all callers:
     grep -rln 'REACT_APP_BACKEND_URL' frontend/src/
   Capture the count.

2. Create frontend/src/config/api.js:

     /**
      * Single source of truth for backend URL configuration.
      * Falls back to localhost:8000 when REACT_APP_BACKEND_URL is missing,
      * preventing "undefined/api/..." bug. Added Round 9 H8.
      */
     export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
     export const API = \`\${BACKEND_URL}/api\`;

3. For each caller (EXCEPT App.js), replace:
     // OLD:
     const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
     const API = \`\${BACKEND_URL}/api\`;
     // NEW (relative path depends on file's depth):
     import { BACKEND_URL, API } from "<correct relative path>/config/api";

   Path examples:
     from frontend/src/components/Foo.jsx          → "../config/api"
     from frontend/src/components/heatseeker/Foo.jsx → "../../config/api"
     from frontend/src/hooks/Foo.js                → "../config/api"

4. Verify only config/api.js (and possibly App.js) reference the env var:
     grep -rn 'process.env.REACT_APP_BACKEND_URL' frontend/src/
   Expected: 1 line in config/api.js (and 1 in App.js if you correctly excluded it).

5. Verify React compiles:
     sleep 12 && tail -10 /tmp/react_decoder.log 2>/dev/null

COMMIT MESSAGE TEMPLATE:

fix(round-9-H8): centralize REACT_APP_BACKEND_URL with localhost fallback

Created frontend/src/config/api.js as single source of truth. Updated N callers
to import BACKEND_URL/API from it. Now when REACT_APP_BACKEND_URL env var is
missing, falls back to http://localhost:8000 instead of building URLs containing
the literal string "undefined".

App.js excluded (FORBIDDEN this round — owner: future Hermes A track).

Verification:
  \$ grep -rln 'REACT_APP_BACKEND_URL' frontend/src/ | wc -l
  Before: 16
  After:  1 (or 2 if App.js still references it)

  \$ grep -rn 'process.env.REACT_APP_BACKEND_URL' frontend/src/ | grep -v config/api.js
  (only App.js, if any)

  \$ tail -3 /tmp/react_decoder.log
  webpack compiled successfully

Co-Authored-By: Owl Alpha (H8) <h8@floww.dev>

END OF TASK.
═══════════════════════════════════════════════════════════════════════════════
