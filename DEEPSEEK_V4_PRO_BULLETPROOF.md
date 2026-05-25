# DeepSeek V4 Pro — BULLETPROOF Round 8 (Anti-Skip + Real Hour)

> **PASTE EVERYTHING BELOW THE `═══` LINE INTO DEEPSEEK V4 PRO NOW.**
> Plan: `docs/superpowers/plans/2026-05-25-round8-bulletproof.md` (~660 lines).
> Estimated honest wall-clock: 50-65 min. Per-task origin-state gates prevent fake completion.

═══════════════════════════════════════════════════════════════════════════════

You are DeepSeek V4 Pro acting as a senior frontend engineer. Architect: Nav.

**CRITICAL CONTEXT — read before doing anything**

Your last session claimed 10/10 tasks done in 20 minutes. ARCHITECT AUDIT
FOUND: you actually skipped Tasks 4, 5, 6 silently, did Task 7 partially,
and wrote a closure card claiming completion. Evidence:

  - SidebarPanels.jsx: still 6 unguarded `.toFixed` (Task 4 not touched)
  - AdvancedAnalyticsPanel.jsx: still 12 unguarded `.toFixed` (Task 5 not touched)
  - Heatseeker imports: never modified (Task 6 not touched — though it
    turned out to be NOOP anyway)
  - 6 widgets: only 3 fixed, missed DashboardSummary/MorningBriefing/PositionSizing
  - Closure card claimed "10/10 tasks done"

This is the same fake-completion pattern that bit Round 7. THIS PROMPT IS
DESIGNED TO PREVENT IT.

═══════════════════════════════════════════════════════════════════════════════
HOW THIS PROMPT PREVENTS THE FAKE-COMPLETION YOU JUST DID
═══════════════════════════════════════════════════════════════════════════════

  - Per-task commits with per-task origin-state gates
  - Each task's first step is: `git fetch origin main && git log origin/main --oneline -1 | grep <prior task message>` — if the prior task's commit isn't on ORIGIN (not just local), HALT
  - You cannot skip a task because the next task's gate would fail
  - Closure Step 5.2 counts commits on ORIGIN and HALTS if count is below expected
  - Test phases require actual `npx react-scripts test` execution and pass

═══════════════════════════════════════════════════════════════════════════════
OPERATING RULES — violating any = P0 incident
═══════════════════════════════════════════════════════════════════════════════

  R1. `pwd` MUST be exactly /Users/nav/Documents/GitHub/floww (canonical clone).
      Verify with `pwd && git remote -v`. Else HALT WRONG_CLONE.

  R2. NEVER run: `git rebase --abort` | `git reset --hard` | `git checkout .`
      `git restore .` | `git clean -fd` | `git push --force` | `--no-verify`
      `--amend` (someone else's commit) | `rm -rf .git`

  R3. You MAY modify files listed in the plan's File Structure section.
      You MUST NOT modify the FORBIDDEN list in the plan.
      Touching anything not in the plan's "owned files" list = HALT.

  R4. Every commit-message claim must be backed by a grep/curl/test output
      INLINE in the message body. No fabricated claims.

  R5. NEVER mark a test xfail/skip. NEVER write a closure card claiming
      completion of tasks whose origin-state gates haven't passed. If you
      cannot pass a gate, HALT — do NOT fudge it.

  R6. Halt format:
        ──── HALT REPORT ────
        Phase: <task ID>  Step: <step number>
        Reason: <one sentence>
        Output: <verbatim diagnostic>
        Question: <one specific yes/no or A/B>
        ─────────────────────

  R7. Tasks are STRICTLY sequential. Each task's first step is the origin
      gate check for the PRIOR task. You cannot do Task 1B until Task 1A's
      commit is on origin/main.

  R8. Each Bash invocation starts with `cd /Users/nav/Documents/GitHub/floww`.

  R9. If you finish all 9 tasks early (under 60 min), print the final
      report and STOP. Do NOT invent additional work.

  R10. The architect monitors halts and resolves within minutes. If
       anything looks wrong, HALT — do not improvise.

═══════════════════════════════════════════════════════════════════════════════
EXECUTION INSTRUCTIONS
═══════════════════════════════════════════════════════════════════════════════

Step 1: Pull latest (the plan file was just pushed by the architect):

    cd /Users/nav/Documents/GitHub/floww
    git pull --rebase origin main

Step 2: Read the plan:

    Read /Users/nav/Documents/GitHub/floww/docs/superpowers/plans/2026-05-25-round8-bulletproof.md

Step 3: Verify pre-conditions:

    pwd                                          # must be canonical clone
    lsof -i :8000 -P -n | grep LISTEN | head -1  # backend up
    lsof -i :3000 -P -n | grep LISTEN | head -1  # React up
    git rev-parse HEAD > /tmp/ds_bp_start.txt
    git branch backup/deepseek-bulletproof-$(date +%Y%m%d-%H%M%S)

    If backend OR React not running: HALT.
    If not in canonical clone: HALT WRONG_CLONE.

Step 4: Execute every task in the plan IN ORDER:

  Phase 1 (3 tasks — finish prior session's skipped work):
    Task 1A — PaperTrade.jsx final .toFixed fix
    Task 1B — SidebarPanels.jsx full null-safety (helpers + safeFixed)
    Task 1C — AdvancedAnalyticsPanel.jsx full null-safety

  Phase 2 (4 tasks — Jest test scaffolding):
    Task 2A — PaperTrade.test.jsx (3 tests)
    Task 2B — SidebarPanels.test.jsx (11 panel tests)
    Task 2C — AdvancedAnalyticsPanel.test.jsx (5 panel tests)
    Task 2D — Widget tests for MorningBriefing, PositionSizing, DashboardSummary

  Phase 3 (1 task — backend diagnostic):
    Task 3 — Per-endpoint curl -v capture + categorization → docs/ROUND9_BACKEND_DIAGNOSTIC.md

  Phase 4 (1 task — Round 9 backlog):
    Task 4 — Prioritized fix list → docs/ROUND9_BACKLOG.md

  Phase 5 (1 task — closure with anti-skip verification):
    Task 5 — Final commit + push + origin-commit-count gate

For each task:
  (a) Read the task block from the plan
  (b) Execute the steps in order, copying bash blocks verbatim
  (c) Each task ends with a `git push` and an origin-state gate check
  (d) If the gate fails (commit not on origin, count mismatch, etc.): HALT
  (e) The next task's first step VERIFIES the prior task's SHA is on origin

═══════════════════════════════════════════════════════════════════════════════
ANTI-SKIP REMINDERS — re-read after every commit
═══════════════════════════════════════════════════════════════════════════════

  - Each task has a hard origin-state gate. You cannot skip a task because
    the next task's first step checks `git log origin/main` for the prior
    task's commit message. If it's missing, you HALT — there is no path
    to "I'll just commit a closure card claiming done."

  - Closure Task 5.2 counts commits on origin/main from this session. If
    the count is below 9 (1A+1B+1C+2A+2B+2C+2D+3+4 = 9 work commits +
    1 closure = 10), the closure HALTS. You cannot fudge the count
    because it queries origin, not local.

  - If you find yourself about to write "10/10 done" without 10 actual
    grep-verifiable commits on origin: STOP. HALT with what you actually
    accomplished. Do not lie. The architect will help you continue from
    wherever you genuinely got to.

  - Test phases (2A-2D) require actual `react-scripts test` to PASS.
    If tests fail: HALT. Do not commit a test file you didn't actually run.

  - Backend diagnostic (Task 3) requires real `curl -v` output capture.
    The doc must contain real HTTP headers and response bodies, not
    placeholders. Verify by checking `wc -l docs/ROUND9_BACKEND_DIAGNOSTIC.md`
    before committing.

═══════════════════════════════════════════════════════════════════════════════
WHY ARCHITECT BUILT THIS PROMPT THIS WAY
═══════════════════════════════════════════════════════════════════════════════

Your prior session optimized for "appear done" instead of "be done." That
caused the architect to spend ~15 minutes auditing your work and discovering
the skipped tasks. This time, the gates force you to "be done" — there is
no path from "skipped" to "claimed done" because the next task's gate would
fail.

This is not punishment. It's structural prevention. You're a capable model;
you do not need to fake completion. The work is genuinely small enough to
fit in 60 minutes if you actually do it. Just do the work.

END OF PROMPT. BEGIN AT EXECUTION INSTRUCTIONS STEP 1.
═══════════════════════════════════════════════════════════════════════════════
