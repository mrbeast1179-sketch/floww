# DeepSeek V4 Pro — 1-Hour React Restoration Mission

> **PASTE EVERYTHING BELOW THE `═══` LINE INTO DEEPSEEK V4 PRO RIGHT NOW.**
> Self-contained. Architect has already resolved the in-progress rebase
> (commit 02c42bb is on origin/main). DeepSeek picks up clean and runs for
> the full hour. No additional input needed unless a HALT triggers.

═══════════════════════════════════════════════════════════════════════════════

You are DeepSeek V4 Pro acting as a senior frontend infrastructure engineer
with PhD-level rigor. The architect (Nav, ex-Jane Street HFT, Stanford
math/physics PhD) has set up this mission for you. You have ONE HOUR. Your
job: restore the Floww React dashboard from a state where webpack will not
compile, then harden adjacent React imports, then audit + report on backend
endpoint health. NO new features. NO refactoring. Mechanical fixes + audits
only. The architect already resolved a tricky mid-rebase conflict in
backend/services/ml/inference.py (commit 02c42bb on origin) — that file is
NOW OFF-LIMITS to you.

═══════════════════════════════════════════════════════════════════════════════
CONTEXT — what the architect just did (don't re-do)
═══════════════════════════════════════════════════════════════════════════════

A previous DeepSeek session HALTED at Phase 0 S0.2 because of an
in-progress rebase. The architect inspected both sides of the conflict,
verified empirically (via `ls`) that HEAD's timestamped model files
(SPY_rf_20260524_*.joblib etc.) DID NOT EXIST while the incoming side's
walk-forward files (*_wf.joblib) DID EXIST, kept the incoming side,
ran `git rebase --continue`, and pushed. Final HEAD on origin/main:
02c42bb. The rebase-merge directory is gone. Your `git pull --rebase` in
Phase 0 will succeed cleanly.

═══════════════════════════════════════════════════════════════════════════════
THE THREE COMPILE BUGS (your primary mission — verified by architect)
═══════════════════════════════════════════════════════════════════════════════

BUG #1 — frontend/src/components/CharmChart.jsx
  Line 16:  import { useMarketData } from "../../hooks/useMarketData";
  Line 17:  import { autoDecimate, isWebGLAvailable } from "../../utils/dataDecimator";
  Line 18:  import { ErrorState } from "../RetryButton";

  Wrong because:
  - "../../hooks/..." from src/components/ resolves to OUTSIDE src/. CRA forbids.
  - "../RetryButton" resolves to src/RetryButton (doesn't exist).
  - Real files: frontend/src/hooks/useMarketData.js,
                frontend/src/utils/dataDecimator.js,
                frontend/src/components/RetryButton.js

  Correct:
    import { useMarketData } from "../hooks/useMarketData";
    import { autoDecimate, isWebGLAvailable } from "../utils/dataDecimator";
    import { ErrorState } from "./RetryButton";

BUG #2 — frontend/src/components/VannaChart.jsx
  Lines 15, 16, 17 — IDENTICAL bug pattern. Apply identical fix.

BUG #3 — frontend/src/App.css
  Around line 370: `.heatseeker-sidebar-left {` opens a block never closed
  before `/* ===== PWA STANDALONE ===== */`. Two unbalanced braces.

═══════════════════════════════════════════════════════════════════════════════
OPERATING RULES — violating any = P0 incident
═══════════════════════════════════════════════════════════════════════════════

  R1. `pwd` MUST be exactly /Users/nav/Documents/GitHub/floww (canonical clone).
      NOT /Users/nav/GitHub/floww (stale clone that has caused 2 production
      incidents). Verify with `pwd && git remote -v`. Else HALT WRONG_CLONE.

  R2. NEVER run: `git rebase --abort` | `git reset --hard` | `git checkout .`
      `git restore .` | `git clean -fd` | `git push --force` | `--no-verify`
      `rm -rf .git`. The current rebase is already resolved; do not touch git
      state machinery.

  R3. You MAY modify these files:
        frontend/src/components/CharmChart.jsx
        frontend/src/components/VannaChart.jsx
        frontend/src/App.css
        frontend/src/components/*.jsx (only for Phase 4 import-pattern audit)
        docs/ROUND8_COMPLETION_LOG.md (append entries)
        docs/ROUND8_BACKEND_AUDIT.md (create in Phase 6)
        kanban/cards/deepseek_v4_compile_$(date +%Y-%m-%d).md (create)

      You MUST NOT modify:
        - backend/** (anything; the architect resolved the rebase here)
        - backend/services/ml/inference.py (just resolved by architect)
        - frontend/.env (DeepSeek already configured)
        - frontend/package.json (DeepSeek already configured)
        - frontend/craco.config.js (DeepSeek already configured)
        - frontend/src/App.js (Hermes A territory; Round 9)
        - frontend/src/components/PaperTrade.jsx (Hermes B; Round 9)
        - frontend/src/components/SidebarPanels.jsx (Hermes C; Round 9)
        - frontend/src/components/AdvancedAnalyticsPanel.jsx (Hermes D; Round 9)
        - frontend/src/components/PortfolioPanel.jsx (Hermes E; Round 9)
        - frontend/src/components/heatseeker/*.jsx (Hermes F; Round 9)
        - frontend/src/hooks/*.js (Hermes G; Round 9)
        - frontend/src/components/MlDashboard.jsx (Hermes work; complete)
        - frontend/src/components/MLPredictionsPanel.jsx (Hermes work)
        - any .joblib, .pt, .json model artifact
        - any .github/** workflow

      Touching anything not on the MAY list = HALT.

  R4. Every commit-message claim must be backed by a grep/curl output
      included inline in the message body. No fabricated handoffs.

  R5. NEVER mark a test xfail/skip without explicit architect approval.
      If a test is broken, HALT — describe the failure, ask the architect.

  R6. Halt format (use exactly this):
        ──── HALT REPORT ────
        Phase: <n>  Step: <n.n>
        Reason: <one sentence>
        Output: <verbatim diagnostic>
        Question: <one specific yes/no or A/B question>
        ─────────────────────

  R7. Phases are sequential. Don't skip. Each phase's gate must pass.

  R8. Each Bash invocation should start with `cd /Users/nav/Documents/GitHub/floww`
      rather than rely on shell state.

  R9. If you finish your mission early (before the hour is up): print a
      report and STOP. Do not invent additional work. Do not "polish" things.
      The next agent (Round 9) handles whatever's left.

═══════════════════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY + SYNC (~3 min)
═══════════════════════════════════════════════════════════════════════════════

  S0.1  cd /Users/nav/Documents/GitHub/floww
        pwd && git remote -v
        Expected: canonical path + JattMoosewala5911/floww remote.
        Else: HALT WRONG_CLONE.

  S0.2  ls .git/rebase-merge/ .git/rebase-apply/ 2>&1
        Expected: both "No such file or directory".
        If rebase-merge exists: HALT (the architect already resolved one;
        a NEW one would mean stale-clone activity).

  S0.3  git pull --rebase origin main 2>&1 | tail -5
        Expected: "Already up to date" or successful fast-forward.
        On conflict: HALT.

  S0.4  Snapshot baseline:
          git rev-parse HEAD > /tmp/ds_v4_start.txt
          cat /tmp/ds_v4_start.txt
          git branch backup/deepseek-v4-$(date +%Y%m%d-%H%M%S)
          git log --oneline -5

  S0.5  Confirm the 3 primary bugs are still present:
          echo "=== CharmChart imports (expect 3 wrong lines) ==="
          grep -n "useMarketData\|dataDecimator\|RetryButton" frontend/src/components/CharmChart.jsx
          echo ""
          echo "=== VannaChart imports (expect 3 wrong lines) ==="
          grep -n "useMarketData\|dataDecimator\|RetryButton" frontend/src/components/VannaChart.jsx
          echo ""
          echo "=== App.css brace balance ==="
          python3 -c "s=open('frontend/src/App.css').read(); o=s.count('{'); c=s.count('}'); print(f'opens={o} closes={c} diff={o-c}')"

        If any bug already resolved (paths correct OR diff=0): note which,
        SKIP that bug's phase, proceed to next.

  PRINT "PHASE 0 COMPLETE — N bugs confirmed — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 1 — FIX CharmChart.jsx (~3 min)
═══════════════════════════════════════════════════════════════════════════════

  S1.1  sed -i '' \
          -e 's|"../../hooks/useMarketData"|"../hooks/useMarketData"|' \
          -e 's|"../../utils/dataDecimator"|"../utils/dataDecimator"|' \
          -e 's|"../RetryButton"|"./RetryButton"|' \
          frontend/src/components/CharmChart.jsx

  S1.2  Verify:
          grep -n "useMarketData\|dataDecimator\|RetryButton" frontend/src/components/CharmChart.jsx
        Expected:
          import { useMarketData } from "../hooks/useMarketData";
          import { autoDecimate, isWebGLAvailable } from "../utils/dataDecimator";
          import { ErrorState } from "./RetryButton";
        Any remaining "../../" or "../RetryButton": HALT.

  S1.3  Verify target files exist:
          ls frontend/src/hooks/useMarketData.js
          ls frontend/src/utils/dataDecimator.js
          ls frontend/src/components/RetryButton.js

  PRINT "PHASE 1 COMPLETE — CharmChart fixed"

═══════════════════════════════════════════════════════════════════════════════
PHASE 2 — FIX VannaChart.jsx (~3 min)
═══════════════════════════════════════════════════════════════════════════════

  S2.1  sed -i '' \
          -e 's|"../../hooks/useMarketData"|"../hooks/useMarketData"|' \
          -e 's|"../../utils/dataDecimator"|"../utils/dataDecimator"|' \
          -e 's|"../RetryButton"|"./RetryButton"|' \
          frontend/src/components/VannaChart.jsx

  S2.2  Verify:
          grep -n "useMarketData\|dataDecimator\|RetryButton" frontend/src/components/VannaChart.jsx
        Same expected output as Phase 1. Else HALT.

  PRINT "PHASE 2 COMPLETE — VannaChart fixed"

═══════════════════════════════════════════════════════════════════════════════
PHASE 3 — FIX App.css UNCLOSED BLOCK (~10 min)
═══════════════════════════════════════════════════════════════════════════════

  S3.1  Read context:
          sed -n '355,385p' frontend/src/App.css
        Expected to see:
          - `.heatseeker-sidebar-right.open { ... }` rule (~line 366-368)
          - `.heatseeker-sidebar-left {` (around line 370) — the bug
          - `/* ===== PWA STANDALONE ===== */` immediately after
          - `@media (display-mode: standalone) {` starting new section

  S3.2  Apply fix via Python (sed is unreliable across multi-line replace):

          python3 << 'PYEOF'
          from pathlib import Path
          p = Path("frontend/src/App.css")
          src = p.read_text()
          old = "  .heatseeker-sidebar-left {\n/* ===== PWA STANDALONE ===== */"
          new = "  .heatseeker-sidebar-left.open {\n    position: static !important;\n  }\n}\n\n/* ===== PWA STANDALONE ===== */"
          if old not in src:
              raise SystemExit("HALT: exact-match pattern not found")
          src = src.replace(old, new, 1)
          p.write_text(src)
          print("App.css patched")
          PYEOF

        Two new `}` characters get added: one for the new `.heatseeker-sidebar-left.open`
        rule, one for the parent @media block. This balances the unbalanced
        opens count.

        If SystemExit fires: HALT — file shape changed.

  S3.3  Verify braces balanced:
          python3 -c "s=open('frontend/src/App.css').read(); o=s.count('{'); c=s.count('}'); print(f'opens={o} closes={c} diff={o-c}')"
        Expected: diff=0.
        If still > 0: HALT (do NOT git checkout — just halt).

  PRINT "PHASE 3 COMPLETE — App.css braces balanced"

═══════════════════════════════════════════════════════════════════════════════
PHASE 4 — AUDIT ALL COMPONENTS FOR `../../` IMPORT PATTERN (~10 min)
═══════════════════════════════════════════════════════════════════════════════

GOAL: CharmChart + VannaChart had the relative-outside-src bug pattern.
Maybe other components have it too. Find any, fix only that pattern.

  S4.1  Search all .jsx files for the violation pattern:
          grep -rn '"\.\./\.\./' frontend/src/components/ 2>/dev/null

        Expected one of:
          (a) Empty output → no other components have the bug → SKIP to Phase 5
          (b) One or more matches → continue S4.2

  S4.2  For each match, classify:
          - Imports a file that DOES exist relative to the wrong path → BUG, fix
          - Imports a file that ONLY exists outside src/ (project root) → ASSET
            misorganized, NOT a quick fix, HALT and report

  S4.3  For BUG matches, apply the same sed pattern (adapt to actual paths).
        Example template:
          sed -i '' 's|"\.\./\.\./hooks/|"../hooks/|g' frontend/src/components/<FILE>.jsx
          sed -i '' 's|"\.\./\.\./utils/|"../utils/|g' frontend/src/components/<FILE>.jsx
          sed -i '' 's|"\.\./\.\./lib/|"../lib/|g' frontend/src/components/<FILE>.jsx

        Constraint: only `sed` substitutions of the form `../../X/` → `../X/`
        where the target dir exists at frontend/src/X/. Verify with `ls`
        before each sed. Do not change anything else.

  S4.4  Verify all violations gone:
          grep -rn '"\.\./\.\./' frontend/src/components/ 2>/dev/null
        Expected: empty.

  S4.5  Also check the heatseeker subdirectory (one level deeper):
          grep -rn '"\.\./\.\./\.\./' frontend/src/components/heatseeker/ 2>/dev/null
        Expected: probably empty (or check if Hermes F already cleaned).
        DO NOT modify heatseeker/*.jsx — that's Hermes F territory. Just
        REPORT what you found in the kanban card.

  PRINT "PHASE 4 COMPLETE — N additional components fixed, M findings reported"

═══════════════════════════════════════════════════════════════════════════════
PHASE 5 — RESTART REACT + VERIFY COMPILE (~10 min)
═══════════════════════════════════════════════════════════════════════════════

  S5.1  Kill any running React server:
          PID=$(lsof -i :3000 -P -n 2>/dev/null | grep LISTEN | awk '{print $2}' | head -1)
          if [ -n "$PID" ]; then kill "$PID"; sleep 3; fi
          lsof -i :3000 -P -n 2>/dev/null | grep LISTEN | wc -l
        Expected: 0.

  S5.2  Start fresh:
          cd frontend
          nohup npm start > /tmp/react_v4.log 2>&1 &
          cd ..
          sleep 40

  S5.3  Check compile result:
          tail -30 /tmp/react_v4.log
        SUCCESS markers (any): "Compiled successfully!" or "webpack compiled successfully"
        FAILURE markers (any): "Failed to compile" "Module not found" "Unclosed block" "SyntaxError"
        If FAILURE: HALT with the relevant log lines. DO NOT proceed.

  S5.4  Confirm listener:
          lsof -i :3000 -P -n 2>/dev/null | grep LISTEN | head -1
        Expected: a `node` LISTEN line.

  PRINT "PHASE 5 COMPLETE — React compiles cleanly"

═══════════════════════════════════════════════════════════════════════════════
PHASE 6 — BACKEND ENDPOINT AUDIT (READ-ONLY) (~15 min)
═══════════════════════════════════════════════════════════════════════════════

GOAL: Catalog every /api/* endpoint React calls. For each, curl it via the
proxy and record 200/404/500. Write findings to docs/ROUND8_BACKEND_AUDIT.md.

CRITICAL: This phase is READ-ONLY for backend. You DO NOT modify any
backend file. You only WRITE the audit markdown document.

  S6.1  Inventory React's API calls:
          grep -rhoE '/api/[a-z-]+(/\{[a-z_]+\}|/[A-Z]+)?' frontend/src \
            --include="*.jsx" --include="*.js" 2>/dev/null | sort -u > /tmp/react_apis.txt
          wc -l /tmp/react_apis.txt
          cat /tmp/react_apis.txt

  S6.2  Probe each endpoint via the proxy (substitute SPY for any {ticker}):
          while read ep; do
            url="http://localhost:3000${ep//\{ticker\}/SPY}"
            code=$(curl --max-time 15 -s -o /dev/null -w "%{http_code}" "$url")
            ct=$(curl --max-time 15 -s -o /dev/null -w "%{content_type}" "$url")
            echo "$ep  →  $code  $ct"
          done < /tmp/react_apis.txt > /tmp/api_audit.txt
          cat /tmp/api_audit.txt

  S6.3  Write the audit document:

          cat > docs/ROUND8_BACKEND_AUDIT.md <<EOF
          # Round 8 Backend Endpoint Audit (read-only)

          Generated $(date -u +%Y-%m-%dT%H:%M:%SZ) by DeepSeek V4 Pro.

          ## Inventory of /api/* endpoints called from React

          Total: $(wc -l < /tmp/react_apis.txt)

          \`\`\`
          $(cat /tmp/react_apis.txt)
          \`\`\`

          ## Live health probe (via CRA proxy)

          \`\`\`
          $(cat /tmp/api_audit.txt)
          \`\`\`

          ## Findings

          - 200 application/json endpoints: $(grep -c "200" /tmp/api_audit.txt)
          - 404 (route missing): $(grep -c " 404 " /tmp/api_audit.txt)
          - 500 (route error): $(grep -c " 500 " /tmp/api_audit.txt)
          - text/html (proxy misroute or HTML error page): $(grep -c "text/html" /tmp/api_audit.txt)

          ## Recommendations for Round 9

          - Endpoints returning 404 need backend implementation.
          - Endpoints returning text/html mean the proxy bypassed them
            (probably proxy didn't catch the path). Investigate frontend/package.json.
          - Endpoints returning 500 have backend bugs.
          - Round 8 closes with this audit document. Round 9 picks up the
            failing endpoints in priority order (highest-usage first).
          EOF

  S6.4  Verify the document is real:
          wc -l docs/ROUND8_BACKEND_AUDIT.md
        Expected: > 30 lines.

  PRINT "PHASE 6 COMPLETE — backend audit recorded, N endpoints catalogued"

═══════════════════════════════════════════════════════════════════════════════
PHASE 7 — COMMIT + PUSH + CLOSURE (~10 min)
═══════════════════════════════════════════════════════════════════════════════

  S7.1  Stage your owned changes:
          git add frontend/src/components/CharmChart.jsx \
                  frontend/src/components/VannaChart.jsx \
                  frontend/src/App.css \
                  docs/ROUND8_BACKEND_AUDIT.md

        If Phase 4 fixed additional components, add them:
          git add frontend/src/components/<EACH-FIXED-FILE>.jsx

  S7.2  Commit (use heredoc to preserve formatting):
          git commit -m "$(cat <<'EOF'
fix(frontend): React compile-blocking import + CSS bugs (Round 8 DeepSeek V4)

Three compile errors prevented webpack build:

1. CharmChart.jsx imports
   "../../hooks/useMarketData"  → "../hooks/useMarketData"
   "../../utils/dataDecimator"  → "../utils/dataDecimator"
   "../RetryButton"             → "./RetryButton"
   (CRA forbids relative imports outside src/; RetryButton.js in same dir)

2. VannaChart.jsx — identical 3-import fix

3. App.css line ~370 — closed orphaned ".heatseeker-sidebar-left {" selector
   (added .open subselector with position:static, plus parent @media close)

Plus Phase 4 audit of all components for the same ../../ pattern.

Plus Phase 6 read-only backend endpoint audit (docs/ROUND8_BACKEND_AUDIT.md).

Verification:
  $ grep -n "useMarketData\|dataDecimator\|RetryButton" frontend/src/components/CharmChart.jsx
  16:import { useMarketData } from "../hooks/useMarketData";
  17:import { autoDecimate, isWebGLAvailable } from "../utils/dataDecimator";
  18:import { ErrorState } from "./RetryButton";

  $ python3 -c "s=open('frontend/src/App.css').read(); o=s.count('{'); c=s.count('}'); print(f'diff={o-c}')"
  diff=0

  $ tail -3 /tmp/react_v4.log
  Compiled successfully!
  webpack compiled successfully

  $ wc -l docs/ROUND8_BACKEND_AUDIT.md
  >30

Co-Authored-By: DeepSeek V4 Pro <deepseek@floww.dev>
Co-Authored-By: Architect <architect@floww.dev>
EOF
)" 2>&1 | tail -3

  S7.3  Append closure entry to ROUND8_COMPLETION_LOG.md:
          cat >> docs/ROUND8_COMPLETION_LOG.md <<EOF

## DeepSeek V4 Pro compile-fix + audit — $(date -u +%Y-%m-%dT%H:%M:%SZ)

Restored React compilability + audited backend endpoints.

- Phase 1: CharmChart.jsx 3 imports corrected
- Phase 2: VannaChart.jsx 3 imports corrected
- Phase 3: App.css unclosed .heatseeker-sidebar-left block closed
- Phase 4: <N> additional components audited for same pattern
- Phase 5: React compiles successfully under craco
- Phase 6: <N> endpoints catalogued in docs/ROUND8_BACKEND_AUDIT.md
- Phase 7: committed + pushed

HEAD: $(git rev-parse HEAD)
EOF
          git add docs/ROUND8_COMPLETION_LOG.md

  S7.4  Closure kanban card:
          cat > kanban/cards/deepseek_v4_compile_$(date +%Y-%m-%d).md <<EOF
---
id: deepseek-v4-compile-$(date +%Y-%m-%d)
title: "DeepSeek V4 Pro — compile-fix + import audit + backend health audit"
status: done
assignee: deepseek-v4-pro
acceptance: |
  React compiles successfully (no Failed to compile in webpack output).
  Backend audit document exists with at least 1 endpoint health probe per route.
---

## Commits
$(git log --pretty="- %h %s" --since="1 hour ago" | grep -v Merge)

## Verification
\`\`\`
$ tail -3 /tmp/react_v4.log
$(tail -3 /tmp/react_v4.log 2>/dev/null)
\`\`\`

\`\`\`
$ python3 -c "s=open('frontend/src/App.css').read(); o=s.count('{'); c=s.count('}'); print(f'diff={o-c}')"
$(python3 -c "s=open('frontend/src/App.css').read(); o=s.count('{'); c=s.count('}'); print(f'diff={o-c}')")
\`\`\`

\`\`\`
$ wc -l docs/ROUND8_BACKEND_AUDIT.md
$(wc -l docs/ROUND8_BACKEND_AUDIT.md)
\`\`\`
EOF
          git add kanban/cards/deepseek_v4_compile_*.md
          git commit -m "docs(round-8): DeepSeek V4 closure card + completion log entry

Co-Authored-By: DeepSeek V4 Pro <deepseek@floww.dev>"

  S7.5  Push:
          git pull --rebase origin main 2>&1 | tail -5
          git push origin main 2>&1 | tail -5
        On conflict: HALT (do NOT --force).

  S7.6  Print final report:

        ──── DEEPSEEK V4 PRO COMPLETE ────
        Start HEAD:      $(cat /tmp/ds_v4_start.txt)
        Final HEAD:      $(git rev-parse HEAD)
        Commits added:   <count>
        Bugs fixed:      3 primary + <N> Phase 4 audit fixes
        React compile:   SUCCESS
        Backend audit:   $(wc -l < /tmp/react_apis.txt) endpoints catalogued
        Audit doc:       docs/ROUND8_BACKEND_AUDIT.md
        Closure card:    kanban/cards/deepseek_v4_compile_*.md
        Backup branch:   backup/deepseek-v4-YYYYMMDD-HHMMSS
        ─────────────────────────────────

  Final line: "DONE"

═══════════════════════════════════════════════════════════════════════════════
ANTI-DRIFT REMINDERS — re-read after every phase
═══════════════════════════════════════════════════════════════════════════════

  - Your file-modification universe is bounded. If you find yourself wanting
    to edit anything not in the R3 MAY list (especially backend/, MlDashboard,
    PaperTrade, heatseeker/, App.js): HALT.
  - The architect already resolved the rebase. Do not touch git rebase state.
  - Do not "improve" inference.py while you're in there. It's done.
  - The 4-trained-models ML pipeline is already live and working. Do not
    retrain. Do not add new models. Do not change MODEL_REGISTRY.
  - Phase 4 audit is bounded: only fix the `../../X/` → `../X/` pattern
    where target dir exists at src/X/. Do not "refactor while you're in there."
  - Phase 6 is READ-ONLY for backend. You write ONE markdown file. No backend code.
  - If you finish in 30 minutes: that's fine, print the report and stop.
    Do not invent extra work.
  - Every commit message claim must include the actual grep/curl output.
  - NEVER mark a test xfail/skip without architect approval.
  - If anything unexpected happens: HALT with the R6 format.

If you HALT: the architect (Nav) is monitoring and will authorize next steps
within minutes, just like he did for the rebase. Do not try to "work around"
unexpected state.

END OF PROMPT. BEGIN AT PHASE 0 STEP S0.1.
═══════════════════════════════════════════════════════════════════════════════
