# Agent 04 (H9) — Replace empty catch (e) {} blocks with explicit logging

> PASTE BELOW THE ═══ INTO ONE OWL ALPHA AGENT. Replace <YOUR_ID> with H9.
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
    Agent:   H9
    Phase:   <step>
    Reason:  <one sentence>
    Output:  <verbatim>
    Question: <one specific yes/no or A/B>
    ─────────────────────
R7. 15-min status pulse to BOTH files (HARD RULE):
      kanban/cards/agent_H9_status.md
      /Users/nav/Documents/GitHub/Hermes/Daily Log.md
    Format: [<ISO8601-UTC>] H9 :: <status> :: <summary> :: HEAD=<sha7>
    If 15 min pass with no pulse: self-HALT with STALLED.

═══════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY (run once)
═══════════════════════════════════════════════════════════════════

cd /Users/nav/Documents/GitHub/floww
pwd && git remote -v
ls .git/rebase-merge/ 2>&1                  # MUST be "No such file or directory"
git pull --rebase origin main
git rev-parse HEAD > /tmp/r9_H9_start.txt
git branch backup/r9_H9_$(date +%Y%m%d-%H%M%S)
mkdir -p kanban/cards
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H9 :: launched :: Phase 0 OK :: HEAD=$(git rev-parse --short HEAD)" \
  | tee -a kanban/cards/agent_H9_status.md \
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
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H9 :: DONE :: pushed $SHA :: <summary>" \
  | tee -a kanban/cards/agent_H9_status.md \
  | tee -a "$HOME/Documents/GitHub/Hermes/Daily Log.md"

═══════════════════════════════════════════════════════════════════
YOUR_TASK — described below this line
═══════════════════════════════════════════════════════════════════

TASK: Stop silently swallowing errors in 6 React components

Empty catch blocks hide every error from the user. For a TRADING app this is
the most dangerous antipattern — user sees blank panel, doesn't know if API
is down, network is down, no data exists, or code has a bug.

YOUR_FILES:
  Find with: grep -rln 'catch (e) {}' frontend/src/components/
  (audit identified ~6 files)

STEPS:

1. List the offenders:
     grep -rln 'catch (e) {}' frontend/src/components/

2. For each file, read it. Find each empty catch. Look for existing error-state
   patterns nearby (setError, setErr, useState for error).

3. Replace pattern:
     // OLD:
     catch (e) {}
     // NEW (minimal):
     catch (e) {
       console.error("<ComponentName> <operation> failed:", e);
       // if component has error state already wired:
       setError(e?.message || String(e));
     }

4. Verify zero remaining:
     grep -rn 'catch (e) {}' frontend/src/components/
   MUST return empty.

5. Verify React compiles:
     sleep 12 && tail -10 /tmp/react_decoder.log 2>/dev/null

COMMIT MESSAGE TEMPLATE:

fix(round-9-H9): replace empty catch (e) {} with explicit logging in 6 components

Empty catch blocks hid every API/network/code failure from the user.
Now each catch logs to console (minimum) and where possible sets component
error state for user-visible feedback.

Verification:
  \$ grep -rln 'catch (e) {}' frontend/src/components/ | wc -l
  Before: 6 (or whatever count)
  After:  0

  \$ grep -rn 'catch (e) {}' frontend/src/components/
  (empty)

Co-Authored-By: Owl Alpha (H9) <h9@floww.dev>

END OF TASK.
═══════════════════════════════════════════════════════════════════════════════
