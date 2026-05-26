# Agent 08 (H14) — SECRET_KEY hard-fail in production

> PASTE BELOW THE ═══ INTO ONE OWL ALPHA AGENT. Replace <YOUR_ID> with H14.
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
    Agent:   H14
    Phase:   <step>
    Reason:  <one sentence>
    Output:  <verbatim>
    Question: <one specific yes/no or A/B>
    ─────────────────────
R7. 15-min status pulse to BOTH files (HARD RULE):
      kanban/cards/agent_H14_status.md
      /Users/nav/Documents/GitHub/Hermes/Daily Log.md
    Format: [<ISO8601-UTC>] H14 :: <status> :: <summary> :: HEAD=<sha7>
    If 15 min pass with no pulse: self-HALT with STALLED.

═══════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY (run once)
═══════════════════════════════════════════════════════════════════

cd /Users/nav/Documents/GitHub/floww
pwd && git remote -v
ls .git/rebase-merge/ 2>&1                  # MUST be "No such file or directory"
git pull --rebase origin main
git rev-parse HEAD > /tmp/r9_H14_start.txt
git branch backup/r9_H14_$(date +%Y%m%d-%H%M%S)
mkdir -p kanban/cards
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H14 :: launched :: Phase 0 OK :: HEAD=$(git rev-parse --short HEAD)" \
  | tee -a kanban/cards/agent_H14_status.md \
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
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H14 :: DONE :: pushed $SHA :: <summary>" \
  | tee -a kanban/cards/agent_H14_status.md \
  | tee -a "$HOME/Documents/GitHub/Hermes/Daily Log.md"

═══════════════════════════════════════════════════════════════════
YOUR_TASK — described below this line
═══════════════════════════════════════════════════════════════════

TASK: Refuse to start if SECRET_KEY is missing in production

Currently defaults to "dev-only-key" if SECRET_KEY env var is missing, even
in production. Architect-approved decision: hard-fail in production/staging.

YOUR_FILES:
  Find with: grep -rln 'SECRET_KEY' backend/config/ backend/ --include="*.py" | head -3
  Likely: backend/config/secrets.py

STEPS:

1. Find file:
     grep -rln 'SECRET_KEY' backend/config/ backend/ --include="*.py" | head -3

2. Replace SECRET_KEY definition pattern:

     import os, sys

     ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev").lower()
     SECRET_KEY = os.environ.get("SECRET_KEY")

     if not SECRET_KEY:
         if ENVIRONMENT in {"production", "staging"}:
             sys.exit(
                 "FATAL: SECRET_KEY env var is required when ENVIRONMENT="
                 f"{ENVIRONMENT!r}. Refusing to start with default dev key."
             )
         SECRET_KEY = "dev-only-key"

3. Verify:
     cd backend && source .venv/bin/activate
     # Should EXIT with FATAL:
     ENVIRONMENT=production SECRET_KEY= python -c "from config.secrets import SECRET_KEY" 2>&1 | head -3
     echo "Exit code: \$?"
     # Should WORK:
     ENVIRONMENT=dev SECRET_KEY= python -c "from config.secrets import SECRET_KEY; print('OK:', SECRET_KEY[:10])"

COMMIT MESSAGE TEMPLATE:

fix(round-9-H14): hard-fail on missing SECRET_KEY in production/staging

App refuses to start when ENVIRONMENT=production/staging AND SECRET_KEY env
var is missing. Default "dev-only-key" still allowed when ENVIRONMENT=dev.

Verification:
  \$ ENVIRONMENT=production SECRET_KEY= python -c "from config.secrets import SECRET_KEY"
  FATAL: SECRET_KEY env var is required when ENVIRONMENT='production'...
  Exit code: 1

  \$ ENVIRONMENT=dev SECRET_KEY= python -c "from config.secrets import SECRET_KEY; print(SECRET_KEY[:10])"
  OK: dev-only-k

Co-Authored-By: Owl Alpha (H14) <h14@floww.dev>

END OF TASK.
═══════════════════════════════════════════════════════════════════════════════
