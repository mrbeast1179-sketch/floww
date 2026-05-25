# DeepSeek Round 8 — Compile-Error Fix (POST-HERMES CLEANUP)

> **HOW TO USE:** Copy below the `═══` line into DeepSeek v4 Pro. ~30 min.
> The Hermes fleet ran out of free-tier credits mid-work; their commits
> DID land on main, but three specific compile errors block React from
> rendering. Your job: fix exactly those three bugs and nothing else.

═══════════════════════════════════════════════════════════════════════════════

You are a senior frontend infrastructure engineer with PhD-level rigor.
Your ENTIRE mission is fixing three compile errors that are blocking the
Floww React app from rendering. Nothing else. No new features. No
"while you're in there" cleanup. No xfail/skip. No fabricated handoff docs.

═══════════════════════════════════════════════════════════════════════════════
THE EXACT THREE BUGS (verified by the architect — do not re-diagnose)
═══════════════════════════════════════════════════════════════════════════════

BUG #1 — frontend/src/components/CharmChart.jsx
  Line 16:  import { useMarketData } from "../../hooks/useMarketData";
  Line 17:  import { autoDecimate, isWebGLAvailable } from "../../utils/dataDecimator";
  Line 18:  import { ErrorState } from "../RetryButton";

  Wrong because:
  - "../../hooks/..." from a file in src/components/ resolves to src/../hooks
    which is OUTSIDE src/. CRA forbids imports outside src/.
  - "../RetryButton" resolves to src/RetryButton (doesn't exist).
  - Correct files DO exist at:
      frontend/src/hooks/useMarketData.js
      frontend/src/utils/dataDecimator.js
      frontend/src/components/RetryButton.js

  Correct imports:
    import { useMarketData } from "../hooks/useMarketData";
    import { autoDecimate, isWebGLAvailable } from "../utils/dataDecimator";
    import { ErrorState } from "./RetryButton";

BUG #2 — frontend/src/components/VannaChart.jsx
  Lines 15, 16, 17 — IDENTICAL bug pattern as CharmChart.
  Apply identical fix.

BUG #3 — frontend/src/App.css
  At approximately line 370, the selector `.heatseeker-sidebar-left {` opens
  a block that is never closed before the next section (`/* ===== PWA
  STANDALONE ===== */`). Two braces are unbalanced (102 opens vs 100 closes).
  Result: postcss-loader throws "Unclosed block" and webpack build fails.

  You will READ the file around line 370, determine the cleanest closure
  (likely delete the empty selector OR add `position: static !important; }`
  to mirror the adjacent `.heatseeker-sidebar-right.open` rule), and apply.

═══════════════════════════════════════════════════════════════════════════════
OPERATING RULES (violating = P0 incident)
═══════════════════════════════════════════════════════════════════════════════

  R1. pwd MUST equal /Users/nav/Documents/GitHub/floww — the CANONICAL
      clone. NOT /Users/nav/GitHub/floww (that is a stale parallel clone
      that has caused production incidents twice already). Verify with:
          pwd && git remote -v
      Else: HALT WRONG_CLONE.

  R2. NEVER run any of: --abort, --reset --hard, --force, --no-verify,
      git checkout ., git restore ., git clean -fd, rm -rf .git

  R3. You touch ONLY these files:
        frontend/src/components/CharmChart.jsx
        frontend/src/components/VannaChart.jsx
        frontend/src/App.css
        docs/ROUND8_COMPLETION_LOG.md  (append one line)
        kanban/cards/deepseek_compile_fix_$(date +%Y-%m-%d).md  (create)
      Any other file: HALT.

  R4. NEVER mark a test xfail/skip. NEVER fabricate completion claims.
      Every commit message MUST include a `grep` or `curl` output proving
      the claim. Defense against fabricated handoff docs (which has bitten
      this project before).

  R5. Halt format (use exactly this when halting):
        ──── HALT REPORT ────
        Phase: <n>  Step: <n.n>
        Reason: <one sentence>
        Output: <verbatim diagnostic>
        Question: <one specific yes/no or A/B question>
        ─────────────────────

  R6. Phases are sequential. Do not skip. Phase 4 verification must pass
      before Phase 5. If Phase 4 fails: HALT — do not invent fixes.

  R7. Restart Bash steps that fail with `cd ... &&` chain rather than
      relying on shell state — each new shell starts in /Users/nav/Documents/GitHub/floww.

═══════════════════════════════════════════════════════════════════════════════
PHASE 0 — SAFETY + SYNC
═══════════════════════════════════════════════════════════════════════════════

  S0.1  cd /Users/nav/Documents/GitHub/floww
        pwd && git remote -v
        Expected: /Users/nav/Documents/GitHub/floww + JattMoosewala5911/floww
        Else: HALT WRONG_CLONE.

  S0.2  Check for in-progress rebase:
          ls .git/rebase-merge/ .git/rebase-apply/ 2>&1
        Expected: both "No such file or directory". Else HALT.

  S0.3  Pull latest (this picks up all Hermes commits that landed):
          git pull --rebase origin main 2>&1 | tail -5
        On conflict: HALT.
        If you see "Already up to date" or successful rebase: PROCEED.

  S0.4  Capture starting state:
          git rev-parse HEAD > /tmp/dscompile_start.txt
          cat /tmp/dscompile_start.txt
          git branch backup/deepseek-compile-$(date +%Y%m%d-%H%M%S)
          git log --oneline -5

  S0.5  Confirm the three bugs are still present:
          echo "=== CharmChart imports (expect 3 wrong lines) ==="
          grep -n "useMarketData\|dataDecimator\|RetryButton" frontend/src/components/CharmChart.jsx
          echo ""
          echo "=== VannaChart imports (expect 3 wrong lines) ==="
          grep -n "useMarketData\|dataDecimator\|RetryButton" frontend/src/components/VannaChart.jsx
          echo ""
          echo "=== App.css brace balance ==="
          python3 -c "s=open('frontend/src/App.css').read(); o=s.count('{'); c=s.count('}'); print(f'opens={o} closes={c} diff={o-c}')"

        Expected:
          - CharmChart: 3 lines with "../../hooks", "../../utils", "../RetryButton"
          - VannaChart: same 3 wrong patterns
          - App.css: diff > 0 (probably 2)

        If diff == 0 in App.css: another agent already fixed it; SKIP Phase 3.
        If CharmChart/VannaChart already use correct paths: SKIP Phase 1/2 accordingly.

  PRINT "PHASE 0 COMPLETE — N bugs confirmed — PROCEED"

═══════════════════════════════════════════════════════════════════════════════
PHASE 1 — FIX CharmChart.jsx
═══════════════════════════════════════════════════════════════════════════════

  S1.1  Apply the three import fixes using sed (idempotent, safe):
          sed -i '' \
            -e 's|"../../hooks/useMarketData"|"../hooks/useMarketData"|' \
            -e 's|"../../utils/dataDecimator"|"../utils/dataDecimator"|' \
            -e 's|"../RetryButton"|"./RetryButton"|' \
            frontend/src/components/CharmChart.jsx

  S1.2  Verify all three lines now point correctly:
          grep -n "useMarketData\|dataDecimator\|RetryButton" frontend/src/components/CharmChart.jsx

        Expected (must match exactly):
          import { useMarketData } from "../hooks/useMarketData";
          import { autoDecimate, isWebGLAvailable } from "../utils/dataDecimator";
          import { ErrorState } from "./RetryButton";

        If any line still has "../../" or "../RetryButton": HALT — sed
        substitution failed.

  S1.3  Verify the target files truly exist (defense against bad fix):
          ls frontend/src/hooks/useMarketData.js
          ls frontend/src/utils/dataDecimator.js
          ls frontend/src/components/RetryButton.js

        All three must exist. Else HALT (a different fix is needed —
        perhaps the helper files have wrong extensions).

  PRINT "PHASE 1 COMPLETE — CharmChart fixed"

═══════════════════════════════════════════════════════════════════════════════
PHASE 2 — FIX VannaChart.jsx (identical to Phase 1)
═══════════════════════════════════════════════════════════════════════════════

  S2.1  Same sed command, different file:
          sed -i '' \
            -e 's|"../../hooks/useMarketData"|"../hooks/useMarketData"|' \
            -e 's|"../../utils/dataDecimator"|"../utils/dataDecimator"|' \
            -e 's|"../RetryButton"|"./RetryButton"|' \
            frontend/src/components/VannaChart.jsx

  S2.2  Verify:
          grep -n "useMarketData\|dataDecimator\|RetryButton" frontend/src/components/VannaChart.jsx
        Expected same three corrected lines as Phase 1.

  PRINT "PHASE 2 COMPLETE — VannaChart fixed"

═══════════════════════════════════════════════════════════════════════════════
PHASE 3 — FIX App.css UNCLOSED BLOCK
═══════════════════════════════════════════════════════════════════════════════

  S3.1  Read 25 lines around the bug for context:
          sed -n '355,385p' frontend/src/App.css

        Expected to see:
          - A `.heatseeker-sidebar-right.open { ... }` rule (around line 366-368)
          - Then `.heatseeker-sidebar-left {` (around line 370)
          - Then `/* ===== PWA STANDALONE ===== */` comment
          - Then `@media (display-mode: standalone) {` (new media query)

  S3.2  Decision tree based on what you see:

        Case A — `.heatseeker-sidebar-left {` is INSIDE an @media block
                 and is intended to mirror `.heatseeker-sidebar-right.open`:
        ACTION: Replace `  .heatseeker-sidebar-left {` with
                `  .heatseeker-sidebar-left.open {\n    position: static !important;\n  }`

        Case B — `.heatseeker-sidebar-left {` was a typo / leftover:
        ACTION: Delete that line entirely.

        Case C — Something else: HALT with the 25-line context dump.

        Preferred default: Case A (closes the brace AND adds a mirroring
        rule for symmetry with the right sidebar).

  S3.3  Apply the chosen fix. If Case A, use a python script (sed gets
        confused with multi-line replacements):

          python3 << 'PYEOF'
          from pathlib import Path
          p = Path("frontend/src/App.css")
          src = p.read_text()
          # Match exactly the empty selector + immediate comment that follows
          old = "  .heatseeker-sidebar-left {\n/* ===== PWA STANDALONE ===== */"
          new = "  .heatseeker-sidebar-left.open {\n    position: static !important;\n  }\n}\n\n/* ===== PWA STANDALONE ===== */"
          if old not in src:
              raise SystemExit("HALT: exact-match pattern not found; manual inspection required")
          src = src.replace(old, new, 1)
          p.write_text(src)
          print("App.css patched")
          PYEOF

        Note: the `new` string includes an extra closing `}` to close the
        PARENT @media block too. That's why we add TWO `}` total — one for
        the new rule, one for the parent media query.

        If that script raises SystemExit: HALT — the file has changed shape
        and needs manual review.

  S3.4  Verify braces are now balanced:
          python3 -c "s=open('frontend/src/App.css').read(); o=s.count('{'); c=s.count('}'); print(f'opens={o} closes={c} diff={o-c}')"
        Expected: "diff=0".
        If still > 0: revert and HALT.
            git checkout frontend/src/App.css

  PRINT "PHASE 3 COMPLETE — App.css braces balanced"

═══════════════════════════════════════════════════════════════════════════════
PHASE 4 — VERIFY REACT COMPILES
═══════════════════════════════════════════════════════════════════════════════

  S4.1  Check if React dev server is currently running:
          lsof -i :3000 -P -n 2>/dev/null | grep LISTEN | head -3

  S4.2  Kill any existing React process (so we get a fresh compile):
          PID=$(lsof -i :3000 -P -n 2>/dev/null | grep LISTEN | awk '{print $2}' | head -1)
          if [ -n "$PID" ]; then kill "$PID"; sleep 2; fi
          lsof -i :3000 -P -n 2>/dev/null | grep LISTEN | wc -l
        Expected: 0.

  S4.3  Start fresh in background:
          cd frontend
          nohup npm start > /tmp/react_compile_verify.log 2>&1 &
          cd ..
          sleep 35

  S4.4  Check for compile result:
          tail -30 /tmp/react_compile_verify.log

        SUCCESS markers (any of):
          "Compiled successfully!"
          "webpack compiled successfully"

        FAILURE markers (any of):
          "Failed to compile"
          "Module not found"
          "Unclosed block"
          "SyntaxError"

        If FAILURE: HALT with the relevant log lines. DO NOT proceed.
        If SUCCESS: PROCEED.

  PRINT "PHASE 4 COMPLETE — React compiles cleanly"

═══════════════════════════════════════════════════════════════════════════════
PHASE 5 — VERIFY PROXY STILL WORKS END-TO-END
═══════════════════════════════════════════════════════════════════════════════

  S5.1  Test proxy delivers JSON (not HTML):
          curl --max-time 30 -s -o /tmp/p.json -w "STATUS=%{http_code} CT=%{content_type} SZ=%{size_download}\n" http://localhost:3000/api/chain/SPY
          echo "FIRST 80 BYTES:"
          head -c 80 /tmp/p.json

        Expected: STATUS=200, CT=application/json, SIZE > 1000, body starts with `{`.

        If body starts with `<!doctype`: proxy is broken. Round 8 Phase 0
        proxy fix was reverted somehow. HALT.

  S5.2  Test a second endpoint:
          curl --max-time 30 -s -o /tmp/p2.json -w "STATUS=%{http_code} CT=%{content_type}\n" "http://localhost:3000/api/heatseeker/flip-zones?ticker=SPY"
          head -c 80 /tmp/p2.json

        Expected same JSON pattern.

  PRINT "PHASE 5 COMPLETE — dashboard serves JSON end-to-end"

═══════════════════════════════════════════════════════════════════════════════
PHASE 6 — COMMIT + CLOSURE + PUSH
═══════════════════════════════════════════════════════════════════════════════

  S6.1  Stage:
          git add frontend/src/components/CharmChart.jsx \
                  frontend/src/components/VannaChart.jsx \
                  frontend/src/App.css

  S6.2  Commit (heredoc to preserve formatting):
          git commit -m "$(cat <<'EOF'
fix(frontend-compile): correct three blocking compile errors in CharmChart, VannaChart, App.css

Three independent webpack compile errors prevented React from rendering:

1. CharmChart.jsx imports
   - "../../hooks/useMarketData"  → "../hooks/useMarketData"
   - "../../utils/dataDecimator"  → "../utils/dataDecimator"
   - "../RetryButton"             → "./RetryButton"
   (CRA forbids relative imports outside src/; RetryButton.js lives in same dir)

2. VannaChart.jsx — identical three-import fix.

3. App.css line ~370 — closed the orphaned ".heatseeker-sidebar-left {"
   selector that was leaving 2 braces unbalanced and breaking postcss.

Verification:
  $ grep -n "useMarketData\|dataDecimator\|RetryButton" frontend/src/components/CharmChart.jsx
  16:import { useMarketData } from "../hooks/useMarketData";
  17:import { autoDecimate, isWebGLAvailable } from "../utils/dataDecimator";
  18:import { ErrorState } from "./RetryButton";

  $ python3 -c "s=open('frontend/src/App.css').read(); o=s.count('{'); c=s.count('}'); print(f'diff={o-c}')"
  diff=0

  $ tail -3 /tmp/react_compile_verify.log
  Compiled successfully!
  webpack compiled successfully

  $ curl -s -w "%{http_code} %{content_type}\n" -o /dev/null http://localhost:3000/api/chain/SPY
  200 application/json

Co-Authored-By: DeepSeek <deepseek@floww.dev>
Co-Authored-By: Architect <architect@floww.dev>
EOF
)" 2>&1 | tail -3

  S6.3  Append closure entry to ROUND8_COMPLETION_LOG.md:
          cat >> docs/ROUND8_COMPLETION_LOG.md <<EOF

## Compile-error fix — $(date -u +%Y-%m-%dT%H:%M:%SZ)

DeepSeek (post-Hermes-exhaustion) fixed three webpack-blocking errors that
prevented React from serving the UI:
- CharmChart.jsx + VannaChart.jsx import paths (relative-outside-src violations)
- App.css unclosed \`.heatseeker-sidebar-left\` block (2 unbalanced braces)

Commit: $(git rev-parse HEAD)
React compile: SUCCESS
Proxy verification: 200 application/json
EOF

  S6.4  Closure kanban card:
          cat > kanban/cards/deepseek_compile_fix_$(date +%Y-%m-%d).md <<EOF
---
id: deepseek-compile-fix-$(date +%Y-%m-%d)
title: "DeepSeek post-Hermes — three compile-blocking fixes"
status: done
assignee: deepseek-v4-pro
acceptance: |
  React compiles successfully; localhost:3000/api/chain/SPY returns JSON.
---

## Commits
- $(git log -1 --pretty=%h) fix(frontend-compile): correct three blocking compile errors

## Verification
- CharmChart imports corrected (grep verified)
- VannaChart imports corrected (grep verified)
- App.css braces balanced (python brace-count returned diff=0)
- npm start: Compiled successfully + webpack compiled successfully
- curl localhost:3000/api/chain/SPY: 200 application/json
EOF
          git add docs/ROUND8_COMPLETION_LOG.md kanban/cards/deepseek_compile_fix_*.md
          git commit -m "docs(round-8): post-Hermes compile-fix closure entry

Co-Authored-By: DeepSeek <deepseek@floww.dev>"

  S6.5  Push:
          git pull --rebase origin main 2>&1 | tail -5
          git push origin main 2>&1 | tail -5
        Else HALT (do NOT --force).

  S6.6  PRINT FINAL REPORT:

        ──── DEEPSEEK COMPILE-FIX COMPLETE ────
        Start HEAD:        $(cat /tmp/dscompile_start.txt)
        Final HEAD:        $(git rev-parse HEAD)
        Bugs fixed:        3 (CharmChart, VannaChart, App.css)
        Compile result:    Compiled successfully!
        Proxy verification: 200 application/json
        Commits:           2 (fix + closure)
        ────────────────────────────────────────

  Final line: "DONE"

═══════════════════════════════════════════════════════════════════════════════
ANTI-DRIFT REMINDERS (re-read after every step)
═══════════════════════════════════════════════════════════════════════════════

  - You touch FIVE files: CharmChart.jsx, VannaChart.jsx, App.css, the log,
    the kanban card. Nothing else.
  - If you find a fourth compile error, HALT — do not invent more fixes.
  - If the proxy returns HTML in Phase 5, HALT — that's Round 8 Phase 0
    work that was reverted; needs architect re-engagement.
  - Do NOT touch any backend file. The ML pipeline + Round 8 Hermes work
    is DONE; backend is healthy.
  - Do NOT touch other React components. They will be Round 9.
  - Do NOT mark anything xfail/skip — if a test is broken, HALT and report.
  - Every commit message claim must be grep/curl-verified inline.
  - Phases are sequential. No skipping.

If you are unsure about any step: HALT with the diagnostic output and one
specific question. Do not improvise.

END OF PROMPT. BEGIN AT PHASE 0 STEP S0.1.
═══════════════════════════════════════════════════════════════════════════════
