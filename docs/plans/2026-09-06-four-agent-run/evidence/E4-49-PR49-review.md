# E4-49 — Agent-4 review of PR49 (a3/alert-engine-badges)

## PR
[#49](https://github.com/mrbeast1179-sketch/floww/pull/49) — `feat(agent3): alert-engine badge mapper (1c) + CLUSTER badge`

- State: OPEN (stacked: base is `a3/alert-surfacing`, NOT main)
- Head: `18ee54f0803abcb6e406694cceaaceb92c15cd65` (re-fetched before reading, exact head)
- Base: `a3/alert-surfacing` at `4d7172e` (PR48 head — PR49 cannot merge before PR48)
- CI at head: NO checks reported on the stacked branch (verified via `gh pr checks 49`)

## Fresh reproduction at exact head

Reused detached worktree `/tmp/agent4-pr48` (node_modules already installed),
checked out `18ee54f`, ran the touched suites:

```text
cd frontend && CI=true npx craco test --watchAll=false --runInBand \
  --testPathPattern='alertEngineBadges|exposureBadges'
PASS src/components/flowseeker/alertEngineBadges.test.js
PASS src/components/flowseeker/exposureBadges.test.js
Test Suites: 2 passed, 2 total
Tests:       27 passed, 27 total
Time:        1.605 s
```

27/27 green. (Lockfile modifications in the worktree are local install
artifacts — the PR payload vs `4d7172e` is exactly 4 files.)

## Payload vs base `4d7172e`

4 files, +194/-2:

| File | Type | Lines |
|---|---|---|
| `frontend/src/components/flowseeker/alertEngineBadges.js` | new | 108 |
| `frontend/src/components/flowseeker/alertEngineBadges.test.js` | new | 67 |
| `frontend/src/components/flowseeker/exposureBadges.js` | patched | +10/-0 |
| `frontend/src/components/flowseeker/exposureBadges.test.js` | patched | +11/-2 |

No Blademap/ExposureStrip/SkylitDashboard changes. No backend. No App.js.

## Source verification

### CLUSTER placement (verified)
`_mk_alert(best, "CLUSTER", ...)` confirmed at `backend/services/flow_alerts.py:836`
on `origin/main`. CLUSTER is a flow_alerts feed `rule` sharing the persisted
feed `rule` column, so both existing badge call sites already see it. Placement
in `exposureBadges.js` (not the new module) is correct. Test added:
CLUSTER renders with heuristic disclaimer.

### 11 priorities (all verified against backend source)
Every priority in the new module matches `ALERT_TYPE_CATALOG`
(`backend/alert_engine.py` L81-94) and the `detect_alerts()` fire sites:

| Rule | Module | Backend | Match |
|---|---|---|---|
| GAMMA_SQUEEZE | HIGH | L82 catalog, L177 fire | yes |
| MOMENTUM_EXTREME | HIGH | L84 catalog, L189-204 fire | yes |
| WALL_BREACH | MEDIUM | L85 catalog, L211-228 fire | yes |
| GEX_MAGNITUDE_SHIFT | MEDIUM | L86 catalog, L235-245 fire | yes |
| GAMMA_FLIP_PROXIMITY | MEDIUM | L87 catalog, L251-257 fire | yes |
| PIN_RISK | LOW | L88 catalog, L262-268 fire | yes |
| CHARM_PINNING | HIGH | L89 catalog, L382-388 fire | yes |
| VANNA_REGIME_CHANGE | HIGH | L90 catalog, L403-409 fire | yes |
| UNUSUAL_PC_OI_RATIO | MEDIUM | L91 catalog, L423-430 fire | yes |
| MAX_PAIN_MAGNET | LOW | L92 catalog, L439-446 fire | yes |
| VOLUME_SPIKE | MEDIUM | L93 catalog, L292-302 fire | yes |

GAMMA_FLIP exclusion rationale is sound: the same string is fired by two
producers (alert_engine regime change + exposure proximity path) and cannot be
split on the string alone. CLUSTER exclusion from the new module is sound:
it is a feed `rule`, not an `Alert.type`.

### Title accuracy (9 clean, 2 flags)

Clean (thresholds match backend constants): WALL_BREACH, GEX_MAGNITUDE_SHIFT
(>40% = `GEX_MAGNITUDE_SHIFT_PCT`), GAMMA_FLIP_PROXIMITY (0.3% =
`GAMMA_FLIP_PROXIMITY_PCT`, plus explicit regime-change disambiguation),
PIN_RISK, CHARM_PINNING (0DTE + CHARM_PIN disambiguation), VANNA_REGIME_CHANGE,
UNUSUAL_PC_OI_RATIO (>2x = ratio gate L422), MAX_PAIN_MAGNET (1% + positive
gamma = L434-438), VOLUME_SPIKE (3x real contract volume =
`REAL_VOLUME_SPIKE_MULTIPLIER`, near-ATM = `REAL_VOLUME_SPIKE_BAND_PCT`).

FLAG 1 — MOMENTUM_EXTREME title: "conviction score at an extreme, crowded
tape". Backend input is `momentum_score` (`detect_alerts(ticker,
momentum_score=50)`, gates L189/L197 at >80/<20). There is no conviction
input. "Conviction score" misattributes the signal; "crowded tape" appears
nowhere in backend. Must read "momentum score at an extreme" with no tape
claim.

FLAG 2 — GAMMA_SQUEEZE title: "dealers chasing price". Backend message
(L180) says "volume spiking"; nothing says dealers chase price — that is
invented flow language with directional flavor. Must drop "chasing price"
and name the actual third condition (volume spike), which the title
currently omits.

### Wiring (the blocking structural finding)

`alertEngineBadgeFor` / `ALERT_ENGINE_RULES` have NO call site. Verified via
`git grep` at `18ee54f`: the only references are the module itself and its
own test file. No Blademap, ExposureStrip, SkylitDashboard, or other UI
imports it. The 11 mappings are tested but unrendered — dead code on arrival.
Per the E4-32 scope-vs-title loop rule, a badge mapper with no rendering path
is not mergeable product. Either wire it in this PR or hold PR49 until the
wiring unit lands.

## Verdict

**REWORK.** Two title fixes (MOMENTUM_EXTREME attribution, GAMMA_SQUEEZE
invention) + wire the mapper to a call site or hold for the wiring unit.
Mapper structure, GAMMA_FLIP/CLUSTER boundary decisions, priorities, and the
CLUSTER placement are all correct — the rework is small and precisely scoped.

No GitHub mutations (Nav-gated). No merge (stacked on unmerged PR48 + no CI
+ unwired + 2 copy flags).
