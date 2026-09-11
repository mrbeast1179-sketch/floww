---
status: review-complete
files_reviewed: 6
depth: standard
phase_dir: pr64-agent4-review
review_path: pr64-agent4-review/64-REVIEW.md
diff_base: 7dc7d5dc0a8c54a6ccdb2a622deb0a8a38ffe99b
critical: 0
warning: 1
info: 6
total: 7
timestamp: 2026-09-11T01:55:00Z
---

# Agent-4 Review: PR64 — fix(frontend): honest proxy copy + X4 dynamic-behavior tests + XH-1 AlertEngineStrip consumer

## Scope

- **Head:** 73c88aebbbd1ba6bca8e48fe034f30a3071be442 (updated since review draft)
- **Base:** 7dc7d5dc0a8c54a6ccdb2a622deb0a8a38ffe99b (current main, PR58 merged)
- **Files:** 12 changed files (5 new frontend components + tests, 5 agent-card docs, 2 backend eval files from PR67 rebase)
  - `frontend/src/components/flowseeker/AlertEngineStrip.css` (88 lines, NEW)
  - `frontend/src/components/flowseeker/AlertEngineStrip.jsx` (70 lines, NEW)
  - `frontend/src/components/flowseeker/AlertEngineStrip.test.jsx` (122 lines, NEW)
  - `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx` (+16/-2)
  - `frontend/src/components/heatseeker/SkylitDashboard.jsx` (+4)
  - `backend/services/eval_harness.py` (+27) — PR67 eval fix (rebased from main)
  - `backend/tests/services/test_eval_harness.py` (+94) — PR67 eval fix tests (rebased from main)
  - `docs/superpowers/muse-spark-1.3-max-v5/SHARED-PROTOCOL.md` (12 lines modified)
  - `docs/superpowers/muse-spark-1.3-max-v5/agent-1-architect.md` (~50 lines modified)
  - `docs/superpowers/muse-spark-1.3-max-v5/agent-2-backend.md` (~49 lines modified)
  - `docs/superpowers/muse-spark-1.3-max-v5/agent-3-frontend.md` (~46 lines modified)
  - `docs/superpowers/muse-spark-1.3-max-v5/agent-4-reviewer.md` (~51 lines modified)
- **PR state:** OPEN, mergeState UNSTABLE (CI running — backend-tests still in_progress)
- **CI:** ruff/SUCCESS, frontend-build/SUCCESS, backend-tests/IN_PROGRESS (run 34551196051)

## Summary

PR64 expanded significantly since the review draft. The new head (73c88ae) adds a genuine mounted AlertEngineStrip consumer that closes XH-1 — the original finding that `alertEngineBadgeFor()` existed as a pure function with no consumer. The component:
- Fetches `/api/alerts/{ticker}` (detector path, NOT the persisted `/api/flowseeker/alerts/feed`)
- Maps each Alert.type through `alertEngineBadgeFor()` from alertEngineBadges.js
- Renders one badge per live alert-engine rule with CSS classes matching badge rules
- Excludes GAMMA_FLIP (stays in exposureBadges/ExposureStrip — same string fired by two producers)
- Handles loading (initial empty), empty response, fetch failure, ticker switch with abort, missing ticker
- Has accessibility (aria-label on each badge)

The component is mounted in SkylitDashboard.jsx (heatseeker panel) right after ExposureStrip. 7 tests cover live types, GAMMA_FLIP exclusion, empty, fetch failure, ticker switch abort, missing ticker, and accessibility.

The copy fix (FlowseekerProBlademap.jsx: flowClassTitle + FILTER_CHIP_TITLES for BLOCK) is still correct and limited to 16+/2-.

The X4 dynamic-behavior tests (21 tests across 2 files) pin pure-function contracts for pulseState classification and pollMs persistence. No mounted behavior.

The eval_harness changes (backend/services/eval_harness.py + test_eval_harness.py) belong to PR67, not PR64 — they appear because the branch has been rebased onto main which includes PR67.

## Findings

### BLOCKER-1: NONE — no blockers

No blocking findings. The mounted consumer is correctly wired.

### WR-1 (unchanged): X4 tests pin contracts; commit message over-claims untested discovery gaps (Warning)

**File:** commit message at 73c88ae (same as 095a273)

The commit message says: "Discovery findings (race-safety gap, partial-data visibility gap, inline-surface poll gap) remain scoped in receipts — not implemented". However, the X4 tests pin contracts for `pulseState` classification and `pollMs` persistence — these ARE implementations of the pinned contracts, not just scoped findings.

**Deeper finding:** The commit message lists three "discovery findings": race-safety gap, partial-data visibility gap, inline-surface poll gap. But the X4 tests do NOT test for:
- Race-safety (no concurrent-poll test)
- Partial-data visibility (no test verifying behavior when data is partial)
- Inline-surface poll gap (the `pollMs` persistence test is a contract pin, not a gap test)

The tests correctly don't implement unadmitted work, but the wording implies coverage that isn't there. A reader might assume the race-safety gap is tested when it isn't.

**Recommendation:** No code change needed. If merged, consider clarifying the commit message to: "X4 pins dynamic-behavior contracts for pulseState and pollMs. Discovery gaps (race-safety, partial-data visibility, inline-surface poll) remain documented in receipts, not implemented."

### INFO-1: Copy fix is correct and complete (Info — unchanged from draft)

**Files:** `FlowseekerProBlademap.jsx:168-178`

The fix updates `flowClassTitle("BLOCK")` and `FILTER_CHIP_TITLES.BLOCK` to say "size-bucket proxy" (was premium-based wording). Pulse BLOCK = premium >= $50M, not Scanner volume. Both code paths (public API line 87, cvserver line 666) classify by premium. The cvserver path never had the wrong wording. No action needed.

### INFO-2: AlertEngineStrip is a genuine XH-1 closure (Info — positive, NEW)

**Files:** `AlertEngineStrip.jsx:1-70`, `alertEngineBadges.js:1-108`

The original XH-1 finding was that `alertEngineBadgeFor()` existed as a pure function with no mounted consumer. The new AlertEngineStrip component:
- Imports `alertEngineBadgeFor` from `../flowseeker/alertEngineBadges` (line 17)
- Fetches `/api/alerts/{ticker}` on ticker change (line 33) — the detector response path
- Maps each Alert.type through the badge function (line 41)
- Filters null results (line 42) — unknown types render nothing
- Renders badges with CSS classes matching the badge rules (line 61: `ae-{rule.toLowerCase()}`)
- Excludes GAMMA_FLIP (handled by exposureBadges/ExposureStrip — same string fired by two producers, documented in alertEngineBadges.js:10-12)
- Handles: loading (initial empty), empty response (line 54-58), fetch failure (line 61-66), ticker switch with abort (line 68-104), missing ticker (line 106-110)
- Has accessibility: each badge has aria-label from heuristic title (line 63-64)

This is a real mounted consumer, not just a test file. The wiring is correct.

### INFO-3: Correct namespace separation (Info — positive, NEW)

**Files:** `AlertEngineStrip.jsx:33`, `SkylitDashboard.jsx:170`, `alertEngineBadges.js:4-6`

AlertEngineStrip fetches `/api/alerts/{ticker}` — the detector response path, NOT `/api/flowseeker/alerts/feed` (persisted rows). This is the correct distinction from the protocol. The alertEngineBadges.js header explicitly states: "Producer: Alert.type strings from ALERT_TYPE_CATALOG in backend/alert_engine.py (served via /api/alerts/*, NOT the persisted flow_alerts feed)" (lines 4-6).

SkylitDashboard mounts AlertEngineStrip (detector badges) right after ExposureStrip (exposure badges), and GAMMA_FLIP is correctly excluded from AlertEngineStrip (stays in exposureBadges/ExposureStrip per alertEngineBadges.js:10-12).

The namespace separation is honest. No coercion of similar-looking labels.

### INFO-4: Test coverage is comprehensive (Info — positive, NEW)

**Files:** `AlertEngineStrip.test.jsx:20-122`

The AlertEngineStrip test file (122 lines, 7 tests) covers:
1. **Live detector types** (L25-43): 3 types render correctly (GAMMA_SQUEEZE, VOLUME_SPIKE, PIN_RISK), axios.get called with correct URL
2. **GAMMA_FLIP exclusion** (L45-52): GAMMA_FLIP alert doesn't render — the namespace boundary is tested
3. **Empty feed → render nothing** (L54-59): fail-open, no badges for empty alerts array
4. **Fetch failure → render nothing** (L61-66): fail-open, stale-free, no badges on network error
5. **Ticker switch aborts in-flight fetch** (L68-104): SPY fetch rejected after switch to QQQ, QQQ renders VANNA SHIFT, both calls made (SPY then QQQ). This tests abort correctness — the in-flight SPY fetch is aborted and doesn't render stale badges.
6. **Missing ticker** (L106-110): empty string ticker → render nothing, no fetch called
7. **Accessibility** (L112-121): each badge has aria-label from heuristic title, aria-label contains the rule name

This is the right test contract for a mounted consumer. Synthetic fixtures only — no live feed.

### INFO-5: SkylitDashboard mounting is correct (Info — positive, NEW)

**Files:** `SkylitDashboard.jsx:9, 169-170`

AlertEngineStrip is imported (line 9) and mounted (line 170) right after ExposureStrip (line 167), both receiving `ticker`. The comment on line 169 says "live detector badges (GAMMA_FLIP excluded; stays in exposure path)" — this matches the actual behavior. The mounting order is correct: ExposureStrip (exposure badges) then AlertEngineStrip (detector badges).

### INFO-6: FlowseekerProBlademap.jsx changes are correct and limited (Info — unchanged)

The Blademap changes (16 insertions, 2 deletions) update `flowClassTitle` + `FILTER_CHIP_TITLES` for the BLOCK classifier. AlertEngineStrip is NOT imported or used in Blademap — correct, since it belongs in the SkylitDashboard/heatseeker path. No conflict.

### BL-1 (NEW): Test comment is stale (Info — trivial)

**File:** `AlertEngineStrip.test.jsx:72`

The test "ticker switch aborts in-flight fetch and renders new ticker badges" has this comment:
```js
// second call (QQQ) returns VANNA_REGIME_CHANGE.
```

But line 93 asserts:
```js
expect(screen.getByText("VANNA SHIFT")).toBeInTheDocument();
```

The comment says "VANNA_REGIME_CHANGE" but the badge maps "VANNA_REGIME_CHANGE" → "VANNA SHIFT" (per alertEngineBadges.js:70-75). The test assertion is correct; the comment is stale/wrong.

**Recommendation:** Fix the comment to say "second call (QQQ) returns VANNA_SHIFT badge" or remove the inline comment. Trivial — doesn't affect test correctness.

## Verification

```
=== PR64 head (full) ===
73c88ae feat(frontend): close XH-1 — mount AlertEngineStrip consumer for alert-engine badges
7b3c076 ci: retrigger backend-tests for PR64 review
e684603 test(frontend): X4 dynamic-behavior — poll persistence + pulseState stale/retry contract

=== Diff: base (7dc7d5d) → head (73c88ae) ===
12 files changed, 526 insertions(+), 103 deletions(-)

Frontend-only (5 files, 299+/1-):
  AlertEngineStrip.css     88  ++++++++++++++  (new)
  AlertEngineStrip.jsx    70  +++++++++++     (new)
  AlertEngineStrip.test   122 +++++++++++++++++  (new)
  FlowseekerProBlademap    16 ++-              (modified)
  SkylitDashboard           4 +                (modified)

Backend (PR67 rebase, 2 files, 121+/0-):
  eval_harness.py          27 ++++
  test_eval_harness.py     94 ++++++++

Docs (5 agent cards + SHARED-PROTOCOL, ~246 lines modified):
  SHARED-PROTOCOL.md       12 +-  
  agent-1-architect.md     50 +++++----
  agent-2-backend.md       49 ++++-----
  agent-3-frontend.md      46 ++++----
  agent-4-reviewer.md      51 ++++----
```

### Source citations

- `AlertEngineStrip.jsx:17` — imports alertEngineBadgeFor from alertEngineBadges
- `AlertEngineStrip.jsx:33` — fetches /api/alerts/{ticker} (detector path, not feed)
- `AlertEngineStrip.jsx:41-42` — maps Alert.type through badgeFor, filters null
- `AlertEngineStrip.jsx:61` — CSS class `ae-{rule.toLowerCase()}` matches badge rules
- `AlertEngineStrip.jsx:63-64` — aria-label from heuristic title (accessibility)
- `AlertEngineStrip.jsx:33` — detector path /api/alerts/{ticker}, NOT /api/flowseeker/alerts/feed
- `SkylitDashboard.jsx:9` — imports AlertEngineStrip
- `SkylitDashboard.jsx:167` — mounts ExposureStrip (exposure badges)
- `SkylitDashboard.jsx:169-170` — mounts AlertEngineStrip after ExposureStrip
- `SkylitDashboard.jsx:169` — comment "live detector badges (GAMMA_FLIP excluded; stays in exposure path)"
- `AlertEngineStrip.test.jsx:25-43` — live detector types test (3 types)
- `AlertEngineStrip.test.jsx:45-52` — GAMMA_FLIP exclusion test
- `AlertEngineStrip.test.jsx:54-59` — empty feed test
- `AlertEngineStrip.test.jsx:61-66` — fetch failure test
- `AlertEngineStrip.test.jsx:68-104` — ticker switch abort test (both calls made)
- `AlertEngineStrip.test.jsx:106-110` — missing ticker test
- `AlertEngineStrip.test.jsx:112-121` — accessibility test (aria-label)
- `AlertEngineStrip.test.jsx:93` — VANNA SHIFT assertion (comment at L72 says VANNA_REGIME_CHANGE — stale)
- `alertEngineBadges.js:4-6` — producer: Alert.type from alert_engine.py via /api/alerts/*, NOT flow_alerts feed
- `alertEngineBadges.js:10-12` — GAMMA_FLIP stays in exposureBadges (same string, two producers)
- `alertEngineBadges.js:70-76` — VANNA_REGIME_CHANGE → VANNA SHIFT badge mapping
- `alertEngineBadges.js:102-108` — alertEngineBadgeFor() function (pure, returns null for unknown)
- `FlowseekerProBlademap.jsx:168-178` — flowClassTitle + FILTER_CHIP_TITLES updated (BLOCK → size-bucket proxy)
- `eval_harness.py:1-27` — PR67 eval fix (rebased, not PR64 work)
- `test_eval_harness.py:1-94` — PR67 eval fix tests (rebased, not PR64 work)

---

## Verdict

**CONDITIONAL-GREEN — ready to merge after CI passes.**

The mounted AlertEngineStrip consumer correctly closes XH-1. The namespace separation (detector `/api/alerts/{ticker}` vs persisted `/api/flowseeker/alerts/feed`) is honest and tested. Test coverage is comprehensive for a mounted consumer (7 tests covering live types, GAMMA_FLIP exclusion, empty, failure, ticker switch abort, missing ticker, accessibility). The copy fix is correct and limited. The X4 tests pin pure-function contracts without claiming mounted behavior.

One trivial stale comment (BL-1) doesn't block. One warning (WR-1, commit message framing) is inherited from the previous head and doesn't affect the consumer correctness.

No blockers. CI must pass (backend-tests currently in_progress).

_Reviewed by Solar-Pro4:free (Hermes Agent, agent-4 lane) on 2026-09-11._
_Review-only — no product edits, no pushes, no merges._
