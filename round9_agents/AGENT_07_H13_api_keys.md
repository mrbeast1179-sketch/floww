# Agent 07 (H13) — Move API keys out of URL query params

> PASTE BELOW THE ═══ INTO ONE OWL ALPHA AGENT. Replace <YOUR_ID> with H13.
> Estimated 30 min.

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
    Agent:   H13
    Phase:   <step>
    Reason:  <one sentence>
    Output:  <verbatim>
    Question: <one specific yes/no or A/B>
    ─────────────────────
R7. 15-min status pulse to BOTH files (HARD RULE):
      kanban/cards/agent_H13_status.md
      /Users/nav/Documents/GitHub/Hermes/Daily Log.md
    Format: [<ISO8601-UTC>] H13 :: <status> :: <summary> :: HEAD=<sha7>
    If 15 min pass with no pulse: self-HALT with STALLED.

═══════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY (run once)
═══════════════════════════════════════════════════════════════════

cd /Users/nav/Documents/GitHub/floww
pwd && git remote -v
ls .git/rebase-merge/ 2>&1                  # MUST be "No such file or directory"
git pull --rebase origin main
git rev-parse HEAD > /tmp/r9_H13_start.txt
git branch backup/r9_H13_$(date +%Y%m%d-%H%M%S)
mkdir -p kanban/cards
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H13 :: launched :: Phase 0 OK :: HEAD=$(git rev-parse --short HEAD)" \
  | tee -a kanban/cards/agent_H13_status.md \
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
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H13 :: DONE :: pushed $SHA :: <summary>" \
  | tee -a kanban/cards/agent_H13_status.md \
  | tee -a "$HOME/Documents/GitHub/Hermes/Daily Log.md"

═══════════════════════════════════════════════════════════════════
YOUR_TASK — described below this line
═══════════════════════════════════════════════════════════════════

TASK: Stop leaking Alpha Vantage API keys via URL query params

API keys in URL leak to: server logs, browser history, proxy caches,
observability platforms.

YOUR_FILES:
  backend/routes/alpha_advantage.py

STEPS:

1. Locate query-param usage:
     grep -n 'apikey\|API_KEY' backend/routes/alpha_advantage.py

2. Alpha Vantage's free tier requires \`?apikey=...\` for most endpoints.
   If that's the only supported auth method for the endpoint you call:
     a. Ensure the key is read from env var (not hardcoded)
     b. Strip apikey from any logged URL strings
     c. Add a code comment explaining the upstream constraint
   If header auth IS available for any endpoint you call: prefer header.

3. Verify:
     grep -n 'apikey=' backend/routes/alpha_advantage.py
   Either: empty, OR only inside comments explaining the upstream constraint.

COMMIT MESSAGE TEMPLATE:

fix(round-9-H13): document/strip Alpha Vantage API keys from URLs

Alpha Vantage free tier requires apikey query param for most endpoints.
Confirmed env-var sourcing + logging-strip + added comment documenting
the upstream constraint.

Verification:
  \$ grep -n 'apikey=' backend/routes/alpha_advantage.py
  <only matches inside comments>

Co-Authored-By: Owl Alpha (H13) <h13@floww.dev>

END OF TASK.
═══════════════════════════════════════════════════════════════════════════════
