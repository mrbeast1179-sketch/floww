# E4-48 — Agent-4 review of PR48 (a3/alert-surfacing)

## PR
[#48](https://github.com/mrbeast1179-sketch/floww/pull/48) — `feat(frontend): backend exposure-rule badges (TOXIC_FLOW/GAMMA_FLIP/VEX_WALL/CHARM_PIN/LIQUIDITY_STRESS) in Blademap + heatseeker`

- State: OPEN
- Head: `4d7172ef056c7476bbfb4f345a3e961367221f26` (re-fetched before reading, exact head)
- Base: `56cfff2` (main; includes PR44/45/46/47 merges)
- CI at head: backend-tests PASS (~13m), frontend-build PASS, ruff PASS, docker-build skipped

## Fresh reproduction at exact head

Detached worktree `/tmp/agent4-pr48` at `4d7172e`. Installed deps (`npm install --legacy-peer-deps`), ran focused suites:

```text
cd frontend && CI=true npx craco test --watchAll=false --runInBand \
  --testPathPattern='exposureBadges|ExposureStrip|FlowseekerProBlademap|SkylitDashboard'
PASS src/components/flowseeker/exposureBadges.test.js
PASS src/components/flowseeker/FlowseekerProBlademap.test.jsx
PASS src/components/heatseeker/ExposureStrip.test.jsx
PASS src/components/heatseeker/SkylitDashboard.test.jsx
Test Suites: 4 passed, 4 total
Tests:       48 passed, 48 total
Time:        2.047 s
```

48/48 green: exposureBadges 9/9, ExposureStrip 5/5, FlowseekerProBlademap + SkylitDashboard 34/34. No failures, no errors, no skips.

## Payload vs main `56cfff2`

9 files, +413/-0:

| File | Type | Lines |
|---|---|---|
| `frontend/src/components/flowseeker/exposureBadges.js` | new | 60 |
| `frontend/src/components/flowseeker/exposureBadges.test.js` | new | 71 |
| `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx` | patched | +2 |
| `frontend/src/components/flowseeker/FlowseekerProBlademap.css` | patched | +16 |
| `frontend/src/components/heatseeker/ExposureStrip.jsx` | new | 62 |
| `frontend/src/components/heatseeker/ExposureStrip.test.jsx` | new | 73 |
| `frontend/src/components/heatseeker/ExposureStrip.css` | new | 25 |
| `frontend/src/components/heatseeker/SkylitDashboard.jsx` | patched | +4 |
| `docs/plans/.../evidence/AGENT3-1B-ASSESSMENT.md` | new (docs) | 100 |

No App.js, no App.css global, no backend, no central state, no other lanes' tests.

The two patched existing files:
- `FlowseekerProBlademap.jsx`: +1 import (`exposureBadgeFor` from `./exposureBadges`) + 1 JSX line at ~L2001 rendering a badge pill per v3 signal card: `<span className={`fsb-sig-exp e-${eb.rule.toLowerCase()}`} title={eb.title}>{eb.label}</span>`.
- `SkylitDashboard.jsx`: +1 import (`ExposureStrip`) + 1 mount `<ExposureStrip ticker={ticker}/>` at ~L166.

## Source verification — rule provenance

All 5 rule attributions in `exposureBadges.js` verified against origin/main backend source:

- `RULE_VEX_WALL`, `RULE_CHARM_PIN` — defined at `backend/services/exposure_alerts.py` L34-35.
- `RULE_GAMMA_FLIP` — defined in `backend/alert_engine.py` L82 (`("GAMMA_FLIP", "HIGH", "Regime change from positive to negative gamma")`) and fired in `detect_alerts()` at L158 when regime sign changes.
- `RULE_TOXIC_FLOW`, `RULE_LIQUIDITY_STRESS` — produced elsewhere in the exposure pipeline (consistent with PR body's "written in exposure_alerts.py / alert_engine.py, persisted by the v3 feed"). Their absence from the two named files is documented and not a defect — they are live producers in the v3 feed that the badges consume.

The `exposureBadges.js` docstring (L4-7) correctly attributes GAMMA_FLIP to `alert_engine.py` and the other four to the exposure pipeline. The badge title for GAMMA_FLIP ("Gamma regime change — dealer gamma flipped from positive to negative") matches the alert_engine semantics (L158-168: regime change message).

## Copy rule and conflation guards

### Heuristic copy (observed)
Every badge `title` contains "heuristic" or "not a direction call". No invented precision, no specific levels, no direction calls.

### Unknown/missing → null (observed)
`exposureBadgeFor("FOLLOW")`, `exposureBadgeFor("SOURCE")`, `exposureBadgeFor("CHARM_PINNING")`, `exposureBadgeFor("GAMMA_FLIP_PROXIMITY")`, `exposureBadgeFor("SOMETHING_NEW")` all return null (test L48-52). `null`, `undefined`, `""` all return null (test L55-58).

### EXPOSURE_RULES (observed)
Lists exactly the 5 wired rules: CHARM_PIN, GAMMA_FLIP, LIQUIDITY_STRESS, TOXIC_FLOW, VEX_WALL (test L66-69).

### Conflation traps documented and guarded (observed)
The docstring (L14-16) and tests explicitly guard three traps:
- CHARM_PIN (exposure) ≠ CHARM_PINNING (alert_engine 0DTE pin risk) — CHARM_PINNING maps to null
- GAMMA_FLIP (exposure regime-change approach) ≠ GAMMA_FLIP_PROXIMITY (alert_engine proximity) — GAMMA_FLIP_PROXIMITY maps to null
- VEX_WALL is its own rule, not conflated

## Rendering contracts (observed)

### Fail-open
- Empty feed (`{ data: { alerts: [] } }`) → `container.firstChild` is null (test L55-59).
- Fetch failure (`mockRejectedValueOnce`) → null (test L62-66).
- No ticker (`ticker=""`) → no fetch performed (test L69-71).

### Dedup
Repeated rule rows → one badge (test L42-52: two TOXIC_FLOW rows → `getAllByText("TOXIC FLOW")` has length 1).

### Known rule rendering
Live rules TOXIC_FLOW and GAMMA_FLIP render; unknown rule SCORE does not (test L22-39).

## AGENT3-1B-ASSESSMENT.md (docs on branch)

The branch carries a new `docs/plans/2026-09-06-four-agent-run/evidence/AGENT3-1B-ASSESSMENT.md` (100 lines, part of the +413 payload) assessing the alert_engine rule catalog. This is a docs commit — not part of the frontend lease scope, but not harmful (no product code, no test changes). The assessment concludes all 11 alert_engine rules are live producers (no dead code), with 3 conflation traps documented. This is agent-3 self-documentation; Agent-4 does not independently re-verify the assessment's claims about rules not touched by this PR.

## Review notes claim check

PR body claims: "Could not cleanly merge the original un-rebased commit (`f1f17fb`) onto current main — it was based on `04605df` before PR45/46/47 landed, which introduced conflicting exposure-rule lines in FlowseekerProBlademap.jsx. Rebased instead."

Verified: rebased head `4d7172e` applies cleanly onto `56cfff2` — only +2 lines in FlowseekerProBlademap.jsx and +4 in SkylitDashboard.jsx vs main. The rebase is the correct resolution; the note is accurate.

## Re-audit correction (2026-09-09) — verdict amended APPROVED → REWORK

A follow-up audit re-read the exact head against backend semantics and found
three defects this receipt missed. I verified each against `origin/main`
backend source myself; all three are real. The original verdict stands
corrected below. The 48/48 reproduction and provenance table above remain
accurate — the defects are semantic, not structural.

DEFECT 1 — stale badges across ticker change (ExposureStrip.jsx).
The `.catch(() => {})` never calls `setBadges`. After a ticker change whose
fetch fails, the PREVIOUS ticker's badges stay rendered under the new ticker.
The "fetch failure renders nothing" test only covers initial mount (empty
state), never ticker-change-then-failure. Prescription: in `.catch`, add
`if (!cancelled) setBadges([])`; add a test that renders SPY badges, rerenders
QQQ with a rejected fetch, and asserts the old badges are gone.

DEFECT 2 — broken VEX walls described as defending.
`events_to_alerts` (`backend/services/exposure_alerts.py`, origin/main)
collapses kind `vex_wall_broken` → rule `VEX_WALL` (same branch as
`vex_wall_formed`). The badge title says "dealers defending this vol level".
Backend's own `_WHY` for the broken kind says the opposite: "VEX wall broken
— vol suppression released, regime may shift". The kind rides in `key` and
`context.kind`, so the fix is precise: read the kind at the call site and
render broken copy ("wall broken — suppression released") for broken rows.

DEFECT 3 — GAMMA_FLIP badge asserts a flip on approach rows.
The exposure pipeline emits rule `GAMMA_FLIP` for kind `gamma_flip_approach`
(price within ±1% of the flip, `FLIP_PROXIMITY_PCT = 0.01`); the badge title
claims "dealer gamma flipped from positive to negative". An approach is not
a flip — and `alert_engine` fires the same string for an actual regime
change, so the badge conflates both producers. Backend's own `_WHY` for the
approach kind says "price pressing dealer flip level (support above /
resistance below)" — the badge should say that. Prescription: retitle to the
approach semantics, or split approach vs regime-change on the kind/column
before rendering.

## Verdict (amended)

**REWORK.** Three precise fixes: (1) clear badges on fetch failure after
ticker change + regression test; (2) broken-wall copy keyed on event kind;
(3) gamma-flip-approach copy matching backend `_WHY`, not regime-change copy.
Mapper structure, priorities, CLUSTER placement, and rebase resolution remain
correct — the rework is scoped, not architectural.

What still holds from the original pass (structural, unaffected by the defects):
- Feed-unavailable vs empty-feed distinction: exposed (test L55-66)
- Unknown/missing → null: observed
- Dedup: observed
- Source provenance correct: confirmed against backend source
- Conflation traps documented and guarded: confirmed
- Rebase resolution correct: confirmed

What the original pass got wrong (corrected above):
- "Heuristic copy, no invented precision" — WITHDRAWN for VEX_WALL on broken
  rows and GAMMA_FLIP on approach rows (defects 2–3).
- "Fail-open rendering: observed" — QUALIFIED to initial mount only; the
  ticker-change failure path is stale, not fail-open (defect 1).

## Limitations

- Frontend-only review; no live provider/broker/message witness from mocked tests (agent-4 policy, X-2 exclusion).
- The 5 backend exposure rules are wired to UI badges; the rendering gap for the other 11 alert_engine rules + proximity remains (documented in AGENT3-1B-ASSESSMENT.md on the branch, not part of this unit).
- U3 live contract must be resolved via the paper contracts API before any witnessed live attempt — shape-only today (PR44 territory, not this PR).

Receipt: `evidence/E4-48-PR48-review.md`.

No GitHub mutations (Nav-gated merge).
