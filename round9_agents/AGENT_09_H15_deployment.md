# Agent 09 (H15) — 6 deployment hygiene quick wins

> PASTE BELOW THE ═══ INTO ONE OWL ALPHA AGENT. Replace <YOUR_ID> with H15.
> Estimated 60 min.

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
    Agent:   H15
    Phase:   <step>
    Reason:  <one sentence>
    Output:  <verbatim>
    Question: <one specific yes/no or A/B>
    ─────────────────────
R7. 15-min status pulse to BOTH files (HARD RULE):
      kanban/cards/agent_H15_status.md
      /Users/nav/Documents/GitHub/Hermes/Daily Log.md
    Format: [<ISO8601-UTC>] H15 :: <status> :: <summary> :: HEAD=<sha7>
    If 15 min pass with no pulse: self-HALT with STALLED.

═══════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY (run once)
═══════════════════════════════════════════════════════════════════

cd /Users/nav/Documents/GitHub/floww
pwd && git remote -v
ls .git/rebase-merge/ 2>&1                  # MUST be "No such file or directory"
git pull --rebase origin main
git rev-parse HEAD > /tmp/r9_H15_start.txt
git branch backup/r9_H15_$(date +%Y%m%d-%H%M%S)
mkdir -p kanban/cards
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H15 :: launched :: Phase 0 OK :: HEAD=$(git rev-parse --short HEAD)" \
  | tee -a kanban/cards/agent_H15_status.md \
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
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H15 :: DONE :: pushed $SHA :: <summary>" \
  | tee -a kanban/cards/agent_H15_status.md \
  | tee -a "$HOME/Documents/GitHub/Hermes/Daily Log.md"

═══════════════════════════════════════════════════════════════════
YOUR_TASK — described below this line
═══════════════════════════════════════════════════════════════════

TASK: 6 deployment-config fixes (single commit)

YOUR_FILES:
  docker-compose.prod.yml
  infra/main.bicep (find with: find . -name "*.bicep" -not -path "*/.venv/*")
  docker-compose.yml
  .github/workflows/deploy.yml
  frontend/public/offline.html (NEW)
  .gitignore

FIXES:

1. docker-compose.prod.yml: \`dockerfile: Dockerfile\` → \`dockerfile: Dockerfile.backend\`
   for the backend service. Verify:
     docker compose -f docker-compose.prod.yml config 2>&1 | head -3

2. infra/main.bicep: dedupe duplicate \`capabilities: ['EnableMongo']\` AND
   duplicate subnet declaration. Use:
     grep -n 'EnableMongo\|subnet' infra/main.bicep | head -10
   Remove ONE of each pair.

3. docker-compose.yml line 39: \`3000:80\` → \`3000:3000\` (container serves on 3000).

4. .github/workflows/deploy.yml: \`app-name: confluence-decoder\` →
   \`app-name: floww-prod-app\` (match terraform/bicep naming).

5. Create frontend/public/offline.html (referenced by service worker but missing):

     <!DOCTYPE html>
     <html lang="en">
     <head>
       <meta charset="utf-8">
       <title>Confluence Decoder — Offline</title>
       <meta name="viewport" content="width=device-width, initial-scale=1">
       <style>
         body { background: #0a0a1a; color: #e0e0e0; font-family: monospace;
                text-align: center; padding: 60px 20px; margin: 0; }
         h1 { color: #34d399; font-size: 24px; }
         p { color: #94a3b8; font-size: 14px; }
         a { color: #34d399; }
       </style>
     </head>
     <body>
       <h1>Offline</h1>
       <p>The Confluence Decoder is currently offline.</p>
       <p>Cached data may still be available. Refresh when network returns.</p>
       <p><a href="/">Retry connection</a></p>
     </body>
     </html>

6. Add \`models/\` to .gitignore (stops tracking 11MB of binary artifacts going forward).

COMMIT (single commit, all 6 fixes):

fix(round-9-H15): 6 deployment hygiene quick wins

1. docker-compose.prod.yml backend dockerfile path corrected
2. infra/main.bicep duplicate EnableMongo + subnet removed
3. docker-compose.yml frontend port 3000:80 → 3000:3000
4. deploy.yml app-name matches terraform (floww-prod-app)
5. frontend/public/offline.html created (was referenced by SW, missing)
6. models/ added to .gitignore

Verification:
  \$ docker compose -f docker-compose.prod.yml config 2>&1 | head -1
  (valid config, no error)
  \$ grep -c 'EnableMongo' infra/main.bicep
  1 (was 2)
  \$ grep '3000:' docker-compose.yml
  - "3000:3000"
  \$ grep 'app-name' .github/workflows/deploy.yml
  app-name: floww-prod-app
  \$ ls frontend/public/offline.html
  frontend/public/offline.html
  \$ grep 'models/' .gitignore
  models/

Co-Authored-By: Owl Alpha (H15) <h15@floww.dev>

END OF TASK.
═══════════════════════════════════════════════════════════════════════════════
