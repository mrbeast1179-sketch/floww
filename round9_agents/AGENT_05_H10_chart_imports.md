# Agent 05 (H10) — Verify CharmChart/VannaChart import paths + lint CI

> PASTE BELOW THE ═══ INTO ONE OWL ALPHA AGENT. Replace <YOUR_ID> with H10.
> Combined small task: verify + lint CI. Estimated 30 min.

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
    Agent:   H10
    Phase:   <step>
    Reason:  <one sentence>
    Output:  <verbatim>
    Question: <one specific yes/no or A/B>
    ─────────────────────
R7. 15-min status pulse to BOTH files (HARD RULE):
      kanban/cards/agent_H10_status.md
      /Users/nav/Documents/GitHub/Hermes/Daily Log.md
    Format: [<ISO8601-UTC>] H10 :: <status> :: <summary> :: HEAD=<sha7>
    If 15 min pass with no pulse: self-HALT with STALLED.

═══════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY (run once)
═══════════════════════════════════════════════════════════════════

cd /Users/nav/Documents/GitHub/floww
pwd && git remote -v
ls .git/rebase-merge/ 2>&1                  # MUST be "No such file or directory"
git pull --rebase origin main
git rev-parse HEAD > /tmp/r9_H10_start.txt
git branch backup/r9_H10_$(date +%Y%m%d-%H%M%S)
mkdir -p kanban/cards
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H10 :: launched :: Phase 0 OK :: HEAD=$(git rev-parse --short HEAD)" \
  | tee -a kanban/cards/agent_H10_status.md \
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
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H10 :: DONE :: pushed $SHA :: <summary>" \
  | tee -a kanban/cards/agent_H10_status.md \
  | tee -a "$HOME/Documents/GitHub/Hermes/Daily Log.md"

═══════════════════════════════════════════════════════════════════
YOUR_TASK — described below this line
═══════════════════════════════════════════════════════════════════

TASK A: Verify CharmChart/VannaChart imports are not regressed (5 min)

YOUR_FILES_A:
  frontend/src/components/CharmChart.jsx
  frontend/src/components/VannaChart.jsx

STEPS:

A1. Check current state:
     grep -n 'import' frontend/src/components/CharmChart.jsx frontend/src/components/VannaChart.jsx | grep -E 'useMarketData|dataDecimator|RetryButton'

A2. Expected (correct, post-DeepSeek-fix-edcf7a6):
     import { useMarketData } from "../hooks/useMarketData";
     import { autoDecimate, isWebGLAvailable } from "../utils/dataDecimator";
     import { ErrorState } from "./RetryButton";

A3. If you see "../../hooks" or "../RetryButton" (regression): apply sed fix:
     sed -i '' \
       -e 's|"../../hooks/useMarketData"|"../hooks/useMarketData"|' \
       -e 's|"../../utils/dataDecimator"|"../utils/dataDecimator"|' \
       -e 's|"../RetryButton"|"./RetryButton"|' \
       frontend/src/components/CharmChart.jsx frontend/src/components/VannaChart.jsx

A4. If no regression: note "no-op" and proceed to Task B.

═══════════════════════════════════════════════════════════════════════════════

TASK B: Lint CI gate (25 min)

YOUR_FILES_B:
  .github/workflows/lint.yml (NEW)
  backend/pyproject.toml (modify or create)

STEPS:

B1. Add [tool.ruff] section to backend/pyproject.toml (create if absent):

     [tool.ruff]
     line-length = 120
     target-version = "py312"

     [tool.ruff.lint]
     select = ["E", "F", "W", "I"]
     ignore = ["E501"]

     [tool.ruff.lint.per-file-ignores]
     "tests/*" = ["F401", "F811"]

B2. Create .github/workflows/lint.yml:

     name: lint
     on:
       pull_request:
         paths: ['backend/**', '.github/workflows/lint.yml']
       push:
         branches: [main]
         paths: ['backend/**']
     jobs:
       ruff:
         runs-on: ubuntu-latest
         steps:
           - uses: actions/checkout@v4
           - uses: actions/setup-python@v5
             with:
               python-version: '3.12'
           - run: pip install ruff
           - run: cd backend && ruff check .

B3. Validate workflow YAML:
     python3 -c "import yaml; yaml.safe_load(open('.github/workflows/lint.yml')); print('YAML valid')"

B4. Local ruff pass:
     cd backend && ruff check .

COMMIT MESSAGE TEMPLATE:

feat(round-9-H10): verify Charm/Vanna imports + add ruff lint CI gate

Task A (imports): verified \`../hooks/\` paths still correct from edcf7a6.
Task B (CI): ruff config in backend/pyproject.toml + .github/workflows/lint.yml.

Verification:
  \$ grep '../../hooks' frontend/src/components/{Charm,Vanna}Chart.jsx | wc -l
  0

  \$ python3 -c "import yaml; yaml.safe_load(open('.github/workflows/lint.yml'))"
  (no error)

  \$ cd backend && ruff check . 2>&1 | tail -1
  All checks passed!

Co-Authored-By: Owl Alpha (H10) <h10@floww.dev>

END OF TASK.
═══════════════════════════════════════════════════════════════════════════════
