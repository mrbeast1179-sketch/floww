# Agent 06 (H11) — Add auth to 6 leaky admin trading routes

> PASTE BELOW THE ═══ INTO ONE OWL ALPHA AGENT. Replace <YOUR_ID> with H11.
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
    Agent:   H11
    Phase:   <step>
    Reason:  <one sentence>
    Output:  <verbatim>
    Question: <one specific yes/no or A/B>
    ─────────────────────
R7. 15-min status pulse to BOTH files (HARD RULE):
      kanban/cards/agent_H11_status.md
      /Users/nav/Documents/GitHub/Hermes/Daily Log.md
    Format: [<ISO8601-UTC>] H11 :: <status> :: <summary> :: HEAD=<sha7>
    If 15 min pass with no pulse: self-HALT with STALLED.

═══════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY (run once)
═══════════════════════════════════════════════════════════════════

cd /Users/nav/Documents/GitHub/floww
pwd && git remote -v
ls .git/rebase-merge/ 2>&1                  # MUST be "No such file or directory"
git pull --rebase origin main
git rev-parse HEAD > /tmp/r9_H11_start.txt
git branch backup/r9_H11_$(date +%Y%m%d-%H%M%S)
mkdir -p kanban/cards
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H11 :: launched :: Phase 0 OK :: HEAD=$(git rev-parse --short HEAD)" \
  | tee -a kanban/cards/agent_H11_status.md \
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
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H11 :: DONE :: pushed $SHA :: <summary>" \
  | tee -a kanban/cards/agent_H11_status.md \
  | tee -a "$HOME/Documents/GitHub/Hermes/Daily Log.md"

═══════════════════════════════════════════════════════════════════
YOUR_TASK — described below this line
═══════════════════════════════════════════════════════════════════

TASK: Add auth dependency to 6 admin trading routes that leak state

ROUTES TO PROTECT (no auth currently):
  /api/admin/trading/status
  /api/admin/trading/circuit-breaker/log
  /api/admin/trading/circuit-breaker/reset
  /api/admin/trading/circuit-breaker/trip
  /api/admin/trading/transition
  /api/admin/schwab/health

YOUR_FILES:
  backend/routes/admin.py
  backend/tests/routes/test_admin_auth.py (NEW)

STEPS:

1. Find existing auth dep:
     grep -rn 'verify_api_key\|def verify_api_key' backend/ --include="*.py" | head -5
   You should find verify_api_key in backend/auth.py (or similar).

2. Add to top of admin.py if not present:
     from auth import verify_api_key
     from fastapi import Depends

3. Add \`_: bool = Depends(verify_api_key)\` to each of the 6 route function signatures.

4. Restart backend, test 401/200 for each:
     kill \$(lsof -i :8000 -t) 2>/dev/null && sleep 2
     cd backend && source .venv/bin/activate
     nohup uvicorn server:app --port 8000 > /tmp/uvicorn_h11.log 2>&1 &
     sleep 6
     for ep in trading/status trading/circuit-breaker/log schwab/health; do
       no_key=\$(curl --max-time 5 -s -o /dev/null -w "%{http_code}" "http://localhost:8000/api/admin/\$ep")
       with_key=\$(curl --max-time 5 -s -o /dev/null -w "%{http_code}" -H "X-API-Key: test-secret-key" "http://localhost:8000/api/admin/\$ep")
       echo "\$ep: no_key=\$no_key with_key=\$with_key"
     done

5. Create backend/tests/routes/test_admin_auth.py with 12 tests (6 routes × 401/200):

     from fastapi.testclient import TestClient
     from server import app
     client = TestClient(app)
     ROUTES = ["/api/admin/trading/status", "/api/admin/trading/circuit-breaker/log", ...]
     def test_each_requires_auth():
         for ep in ROUTES:
             r = client.get(ep) if "log" in ep or "status" in ep or "health" in ep else client.post(ep, json={})
             assert r.status_code == 401, f"{ep} should be 401 without key"

6. Run tests:
     cd backend && python -m pytest tests/routes/test_admin_auth.py -v | tail -10

COMMIT MESSAGE TEMPLATE:

fix(round-9-H11): add auth to 6 leaky admin trading routes

Endpoints previously exposed trading state, circuit breaker logs, and Schwab
connection health to anyone who could find the URL. Each now requires
X-API-Key header via Depends(verify_api_key).

Verification (curl outputs):
  /api/admin/trading/status            no_key=401 with_key=200
  /api/admin/trading/circuit-breaker/log no_key=401 with_key=200
  /api/admin/schwab/health             no_key=401 with_key=200

  \$ pytest backend/tests/routes/test_admin_auth.py -v | tail -2
  12 passed in 0.Ns

Co-Authored-By: Owl Alpha (H11) <h11@floww.dev>

END OF TASK.
═══════════════════════════════════════════════════════════════════════════════
