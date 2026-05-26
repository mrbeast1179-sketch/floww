# Agent 02 (H7) — AlertOverlay connect() ReferenceError fix

> PASTE BELOW THE ═══ INTO ONE OWL ALPHA AGENT. Replace <YOUR_ID> with H7.
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
    Agent:   H7
    Phase:   <step>
    Reason:  <one sentence>
    Output:  <verbatim>
    Question: <one specific yes/no or A/B>
    ─────────────────────
R7. 15-min status pulse to BOTH files (HARD RULE):
      kanban/cards/agent_H7_status.md
      /Users/nav/Documents/GitHub/Hermes/Daily Log.md
    Format: [<ISO8601-UTC>] H7 :: <status> :: <summary> :: HEAD=<sha7>
    If 15 min pass with no pulse: self-HALT with STALLED.

═══════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY (run once)
═══════════════════════════════════════════════════════════════════

cd /Users/nav/Documents/GitHub/floww
pwd && git remote -v
ls .git/rebase-merge/ 2>&1                  # MUST be "No such file or directory"
git pull --rebase origin main
git rev-parse HEAD > /tmp/r9_H7_start.txt
git branch backup/r9_H7_$(date +%Y%m%d-%H%M%S)
mkdir -p kanban/cards
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H7 :: launched :: Phase 0 OK :: HEAD=$(git rev-parse --short HEAD)" \
  | tee -a kanban/cards/agent_H7_status.md \
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
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H7 :: DONE :: pushed $SHA :: <summary>" \
  | tee -a kanban/cards/agent_H7_status.md \
  | tee -a "$HOME/Documents/GitHub/Hermes/Daily Log.md"

═══════════════════════════════════════════════════════════════════
YOUR_TASK — described below this line
═══════════════════════════════════════════════════════════════════

TASK: Fix AlertOverlay.js connect() ReferenceError on tab visibility change

Bug: connect() is defined inside one useEffect's closure but called from
another useEffect. When the browser tab changes visibility, the visibility
handler throws "ReferenceError: connect is not defined" and crashes the
WebSocket reconnection logic.

YOUR_FILES:
  frontend/src/components/AlertOverlay.js  (or .jsx — check extension)

STEPS:

1. Find the actual filename:
     ls frontend/src/components/AlertOverlay.* 2>/dev/null

2. Read it. Identify connect() and both useEffects.

3. Refactor connect() to component scope using useCallback. Pattern:
     const connect = useCallback(() => {
       // websocket setup
     }, [/* state deps */]);

     useEffect(() => {
       connect();
       return () => /* cleanup */;
     }, [connect]);

     useEffect(() => {
       const onVisibilityChange = () => {
         if (document.visibilityState === 'visible') connect();
       };
       document.addEventListener('visibilitychange', onVisibilityChange);
       return () => document.removeEventListener('visibilitychange', onVisibilityChange);
     }, [connect]);

4. Verify connect is at component scope, not inside an effect:
     grep -nB 1 'const connect =' frontend/src/components/AlertOverlay.*
   Should show "const connect = useCallback(" at top-level component body.

5. Verify React still compiles (wait 12s):
     sleep 12 && tail -10 /tmp/react_decoder.log 2>/dev/null

COMMIT MESSAGE TEMPLATE:

fix(round-9-H7): AlertOverlay connect() lifted to useCallback (component scope)

Bug: connect() was defined inside one useEffect's closure but called from
another useEffect (visibility-change handler), causing ReferenceError when
the browser tab returned from background and tried to reconnect the WebSocket.

Fix: lifted connect to a useCallback at component scope; both useEffects
now reference it via deps array.

Verification:
  \$ grep -nB 1 'const connect =' frontend/src/components/AlertOverlay.*
  (shows "const connect = useCallback(" at component scope, not inside useEffect)

  \$ tail -3 /tmp/react_decoder.log
  webpack compiled successfully

Co-Authored-By: Owl Alpha (H7) <h7@floww.dev>

END OF TASK. Run commit + push + verify-on-origin block above. Then STOP.
═══════════════════════════════════════════════════════════════════════════════
