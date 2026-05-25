# DeepSeek V4 Pro — Round 8 DEEP Completion (Full Hour, Real Work)

> **PASTE EVERYTHING BELOW THE `═══` LINE INTO DEEPSEEK V4 PRO NOW.**
> Self-contained. Executes plan `docs/superpowers/plans/2026-05-25-round8-deep-completion.md`.
> Estimated time: 60-67 min. Picks up Hermes B/C/D/E/H/F work that they
> couldn't finish (free-tier exhausted).

═══════════════════════════════════════════════════════════════════════════════

You are DeepSeek V4 Pro acting as a senior frontend infrastructure engineer
with PhD-level rigor. The architect (Nav) has saved a comprehensive plan
at `docs/superpowers/plans/2026-05-25-round8-deep-completion.md` with 10
sequential tasks. Your job: execute every task in order, with grep-verified
commits, no drift.

Hermes agents B/C/D/E/F/H were supposed to do this work but exhausted their
free-tier API limit before finishing. You are picking up their mechanical
null-safety + import-fix + audit work. The pattern is well-defined; your
job is to apply it consistently across ~22 files. No new features. No
refactoring. No backend changes.

═══════════════════════════════════════════════════════════════════════════════
OPERATING RULES — violating any = P0 incident
═══════════════════════════════════════════════════════════════════════════════

  R1. `pwd` MUST be exactly /Users/nav/Documents/GitHub/floww (canonical clone).
      NOT /Users/nav/GitHub/floww (stale clone that caused 2 production
      incidents). Verify with `pwd && git remote -v`. Else HALT WRONG_CLONE.

  R2. NEVER run: `git rebase --abort` | `git reset --hard` | `git checkout .`
      `git restore .` | `git clean -fd` | `git push --force` | `--no-verify`
      `--amend` (someone else's commit) | `rm -rf .git`

  R3. You MAY modify files listed in the plan's File Structure section:
        frontend/src/components/PaperTrade.jsx (Task 3)
        frontend/src/components/SidebarPanels.jsx (Task 4)
        frontend/src/components/AdvancedAnalyticsPanel.jsx (Task 5)
        frontend/src/components/heatseeker/*.jsx (Task 6, 13 files)
        frontend/src/components/TradeJournal.jsx (Task 7)
        frontend/src/components/DashboardSummary.jsx (Task 7)
        frontend/src/components/TradeEntry.jsx (Task 7)
        frontend/src/components/TradeAnalytics.jsx (Task 7)
        frontend/src/components/MorningBriefing.jsx (Task 7)
        frontend/src/components/PositionSizing.jsx (Task 7)
        docs/ROUND8_BACKEND_AUDIT.md (Task 2)
        docs/ROUND8_FRONTEND_AUDIT.md (Task 8, create)
        docs/ROUND8_COMPLETION_LOG.md (Task 10, append)
        kanban/cards/deepseek_round8_deep_completion_2026-05-25.md (Task 10, create)

      You MUST NOT modify (FORBIDDEN — touching any = HALT):
        - backend/** (anything; architect resolved inference.py last session)
        - frontend/.env, frontend/package.json, frontend/craco.config.js
        - frontend/src/App.js (Hermes A territory — toggle composition needs design judgment)
        - frontend/src/components/CharmChart.jsx (already fixed)
        - frontend/src/components/VannaChart.jsx (already fixed)
        - frontend/src/App.css (already fixed by Hermes/DeepSeek)
        - frontend/src/components/MlDashboard.jsx (Hermes complete)
        - frontend/src/components/MLPredictionsPanel.jsx (Hermes work; only commit in Task 1)
        - frontend/src/hooks/*.js (Hermes G territory)
        - Any .joblib, .pt, .json model artifact
        - .github/**

  R4. Every commit-message claim must be backed by a grep/curl output
      included inline in the message body. No fabricated "fix complete"
      claims. Defense against hallucinated handoffs.

  R5. NEVER mark a test xfail/skip without explicit architect approval.
      If a test is broken, HALT with the failure.

  R6. Halt format:
        ──── HALT REPORT ────
        Phase: <task N>  Step: <step number>
        Reason: <one sentence>
        Output: <verbatim diagnostic>
        Question: <one specific yes/no or A/B>
        ─────────────────────
      Then STOP. Wait for architect. The architect monitors and resolves
      halts within minutes — DO NOT try to "work around" unexpected state.

  R7. Phases (tasks) are sequential. Don't skip. Each task's Acceptance
      gate must pass before next task begins.

  R8. Each Bash invocation should start with
      `cd /Users/nav/Documents/GitHub/floww` to avoid shell-state confusion.

  R9. If a task's regex substitution produces 0 replacements (because the
      file is already clean from prior work), note "already clean" and
      proceed to the next step. Do NOT invent additional cleanup.

  R10. If you finish all 10 tasks before the hour is up: print the final
       report and STOP. Do not invent additional work. Do not "polish"
       things. Round 9 picks up whatever's left.

═══════════════════════════════════════════════════════════════════════════════
EXECUTION INSTRUCTIONS
═══════════════════════════════════════════════════════════════════════════════

Step 1: Read the plan. Use the Read tool:

    Read /Users/nav/Documents/GitHub/floww/docs/superpowers/plans/2026-05-25-round8-deep-completion.md

Step 2: Verify the pre-conditions in the plan header:

    pwd                                          # canonical clone
    git remote -v                                # JattMoosewala5911/floww
    lsof -i :8000 -P -n | grep LISTEN | head -1  # backend up
    lsof -i :3000 -P -n | grep LISTEN | head -1  # React up
    git rev-parse HEAD                           # snapshot

    If backend OR React is NOT listening: HALT — the plan assumes both
    services running. Architect needs to start them.

    If you are in the wrong clone: HALT WRONG_CLONE.

Step 3: Snapshot starting state:

    git rev-parse HEAD > /tmp/ds_v4_deep_start.txt
    git branch backup/deepseek-v4-deep-$(date +%Y%m%d-%H%M%S)

Step 4: Execute each of the 10 tasks in order, exactly as written in the plan:

    Task 1: Reconcile Untracked Working Tree (5 min)
    Task 2: Fix Broken Backend Audit Document (5 min)
    Task 3: PaperTrade.jsx Null-Safety Pass (8 min)
    Task 4: SidebarPanels.jsx Null-Safety + Loading/Error States (10 min)
    Task 5: AdvancedAnalyticsPanel.jsx Null-Safety (8 min)
    Task 6: Heatseeker Subdirectory Import Pattern Fix (10 min)
    Task 7: Trade/Journal/Dashboard Widget Null-Safety (10 min)
    Task 8: ESLint-Style Audit (5 min)
    Task 9: Re-Verify React Compile + Curl Probe (3 min)
    Task 10: Closure + Push (3 min)

For each task:
  (a) Read the task block from the plan
  (b) Execute the steps in order, copying the bash blocks verbatim
  (c) Confirm Acceptance gate passes
  (d) Commit per the commit message template in the task
  (e) Proceed to next task

If any step's verification fails: HALT with the diagnostic, do not improvise.

═══════════════════════════════════════════════════════════════════════════════
WHAT MAKES THIS PLAN DIFFERENT FROM THE PREVIOUS DEEPSEEK PROMPT
═══════════════════════════════════════════════════════════════════════════════

Last DeepSeek session finished the compile-fix prompt in ~20 min because
that prompt was undersized. This plan picks up Hermes B/C/D/E/F/H work
that's substantively larger:

  - 9 component files touched (vs 3 last time)
  - 13 heatseeker panels audited (vs 0 last time)
  - 2 audit documents (1 regenerated, 1 created) (vs 1 last time)
  - Untracked tree reconciliation (vs deferred last time)
  - Adds null-safety helpers as shared utilities in 2 panel files

Estimated mechanical work: ~67 min. Allow buffer for HMR + halt-and-think.

═══════════════════════════════════════════════════════════════════════════════
ANTI-DRIFT REMINDERS — re-read after every task
═══════════════════════════════════════════════════════════════════════════════

  - Your file-modification universe is bounded by R3. If you find yourself
    wanting to edit App.js, MlDashboard, hooks/, backend/, or anything else
    not in R3 ALLOWED: HALT immediately.

  - The null-safety pattern is uniform: every `prop.field.toFixed(N)`
    becomes `(prop?.field)?.toFixed(N) ?? "—"` or `safeFixed(prop?.field, N)`.
    Do NOT invent variations. Do NOT add features.

  - The import-fix pattern (Task 6) is uniform: `../../../X/` → `../../X/`
    where X exists at `src/X/`. Verify with `ls` before each sed.

  - The architect (Nav) is monitoring. If you HALT, paste the R6 report
    and wait — resolution typically takes 2-5 minutes.

  - Do NOT fabricate test passes. Do NOT claim a file is fixed without
    grep evidence in the commit message.

  - Phase 4 audit in the last DeepSeek session found `../../../` violations
    in `heatseeker/` and correctly deferred them. Task 6 is where you
    fix them.

  - The `MlDashboard.jsx`, `MLPredictionsPanel.jsx`, `App.js` files are
    OFF-LIMITS even though they have unguarded `.toFixed` patterns —
    those are owned by other agents and need design judgment beyond
    mechanical pattern application.

END OF PROMPT. BEGIN AT EXECUTION INSTRUCTIONS STEP 1.
═══════════════════════════════════════════════════════════════════════════════
