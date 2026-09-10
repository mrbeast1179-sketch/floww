# Recovery queue v2 — current state (main d4a5b1f)

`QUEUE.md` retains the full P1–P7, D1–D7, X1–X5, and E1–E5 contracts. This
file tracks current candidate heads and the live backlog. Status is evidence-based
as of 2026-09-08.

## CLOSED as a merge queue

Main is `d5dbd7d` (was `12c53d8`; PR54 order-safety merged 2026-09-10T01:44:39Z;
PR48/49/50/51/52/53/54 all in main). Merged, in order: PR28 (D7 parity), PR29 (X1 journal),
PR30 (P1 silent-except gate), PR31 (A3 conviction wiring), PR33 (T1-only),
PR34 (H1 strike-truth fixture), PR35 (F0 wave + clock fix), PR36 (H2-partial),
PR37 (GEX date-string fix), PR38 (dead-code removal + kanban datetime fix),
PR39 (provider cap + deepen + enrich, merged by Nav), PR40 (honesty labels),
PR41 (strike floor), PR42 (T2 full universe + order-key 401 fix), PR43
(honesty citations), PR45 (TOXIC_FLOW alerts), PR46 (GAMMA_FLIP alerts),
PR47 (numba charm vec + liquidity-stress alerts), PR51 (signal-truth repair:
charm type normalization + liquidity interval flow, merged d4a5b1f,
E4-51 APPROVED post-merge), PR50 (kind-aware badge copy + stale-strip fix,
merged 2026-09-09T15:35:57Z), PR52 (vomma-walls alerts, merged 2026-09-09T23:19:09Z),
PR53 (gamma-vanna-vec wiring, merged 2026-09-09T23:19:09Z), PR48 (alert-surfacing,
MERGED 2026-09-09T23:19:09Z into main `12c53d8`), PR49 (alert-engine-badges,
MERGED 2026-09-09T17:08:59Z into a3/alert-surfacing parent lineage), PR54 (order-safety:
idempotency key reuse + paper-order venue-idempotent retries, merged `d5dbd7d` 2026-09-10T01:44:39Z),
PR56 (P2 dependency pins: FastAPI 0.141.1 + Starlette 1.6.0 + PyMongo 4.6.3 +
cryptography 50.0.1 + 4 route-inventory assertion adaptations, MERGED 2026-09-10T02:15:08Z).
PR48 (a3/alert-surfacing, head `9eb5e7d567f56180a25723bb07b363a0562149a5`, E4-48d APPROVED at 2f57bea3d — 49/49 green, frontend-only, MERGED to main `12c53d8` 2026-09-09T23:19:09Z. PR48 is **MERGED** on GitHub [#48](https://github.com/mrbeast1179-sketch/floww/pull/48).
PR49 (a3/alert-engine-badges, head `8ed71c2857030fc2e132c160e4b65763d175379d`, E4-49 APPROVED-conditional —
29/29 green, MERGED (closed 2026-09-09T17:08:59Z, merge commit `480e953`), now part of `a3/alert-surfacing` parent lineage;
wiring gap holds).
**OPEN**: PR55 `fix(frontend): restore kind-aware exposure badge truth` (architect/pr48-semantic-main-v1, head `7481f72`, E4-55 APPROVED below). Tasked by agent-4.
6 superseded branches deleted after patch-id proof (product identical to main;
docs in archive). Every merge verified: green required CI on the merged head +
local reproduction where applicable. Full receipt trail in GSD-PASSES.md
take-over section + lane receipts + evidence/DEEP-SWEEP-2026-09-08.md.

## Remaining (gated — no executable builder work left ungated)

| ID | State | Gate |
|---|---|---|---|
| O-2 reuse-or-remove | QUEUED with spec | Cross-key cache surgery or swing-depth product call — Nav's |
| O-4/O-5 failover order | QUEUED with spec | Provider sandbox + product sign-off — Nav's |
|| P2 upgrades | PINNED — DONE (agent-2, phase9/g1-reads-witness) | pymongo==4.6.3 (CVE-2024-5629 closed), starlette==1.6.0 + fastapi==0.141.1 (all 8 starlette CVEs closed), cryptography==50.0.1 (CVE-2026-69247 closed); nltk==3.10.3 upgraded but CVE-2026-81726 has fix_versions=[] (unfixable by version). 14 advisories remain on unpinned transitive deps (aiohttp, ecdsa, pip, pyasn1, pypdf2, setuptools, torch) — advisory-only, not blocked |
| P6 rotation | Inventory done | Real credential rotation — Nav's secrets |
| P7 Oracle | Runbook ready | VM provisioning — Nav's |
| Azure deploy | Workflow red, code-innocent | `azure/login` credentials missing in repo secrets — Nav's (`Deploy to Azure` fails on every main push with "No credentials found"; pre-existing, unrelated to merges) |
| GSD-8 | BLOCKED | X credits |
| App.js standing waiver | Ungranted, scoped | T1 28-line scope shipped under 2026-09-08 take-over order; a STANDING waiver for future App.js work is still explicitly ungranted |
| PRODUCTION CUTOVER (do NOT do unilaterally) | REQUIRED for any user-visible fix | Production runs canonical `phase9/g1-reads-witness` (pre-T1!). Main has everything; canonical does not. Evidence of a possible parallel actor on canonical (unexplained merge commits 4665c77/3617c46 in my message phrasing, 2026-09-07 ~20:16-20:52 EDT) + Nav's live IDE work there. SINGLE-WRITER RULE: coordinate first. G1 WIP preserved at `d39c37a` (pushed). Cutover sketch (Nav-approved only): verify canonical clean, `git checkout main`, `git pull --ff-only`, frontend rebuild, backend restart per ~/.hermes/scripts/confluence-decoder-start.sh, verify :3000/:8000 + KYTX strikes + paper order probe. |
| G3-SALVAGE (PR44) | MERGED + witness pending | PR44 `astra/g3-paper-loop` @ `bffa5deb` (base `a6e6f79`, merged main `56cfff2` 2026-09-08T11:48:51Z). Offline GATE-2 proof at exact head (56/56 green, ruff clean, no code blocker). Witness gate (external G-WITNESS) still pending; merge already landed without it. No further Agent-4 merge authority; re-verify at any new head before any witnessed attempt. |

## Admission order

All September 6-8 recovery work is merged. No active builder admissions.

PR44 merged main 56cfff2 2026-09-08T11:48:51Z; witness gate (external G-WITNESS) is Nav/owner-gated, no Agent-4 merge authority.

### Agent 2 backlog (items 1–2 DONE via PR47; rest queued)

1. **Numba Greeks wiring — DONE (PR47, main `56cfff2`).** Charm-vec wired,
   identical totals, 1.7x on 15k chains. Remaining vecs (`bs_vomma_vec`,
   `bs_delta_vec`, `bs_vega_vec`, `bs_zomma_vec`) still unused — future unit
   only on a fresh Agent-1 admission with its own red/green proof.

2. **Kyle/Amihud regime alerts — DONE (PR47, main `56cfff2`).**
   LIQUIDITY_STRESS live via exposure pipeline, TOXIC_FLOW pattern copied.

3. **OFI/multi-level assessment.** `multi_level_ofi.py`, `composite_flow_score.py`,
   `hmm_regime.py`, `chain_replay.py` exist; assess which computes a
   tradeable signal vs research scaffolding. Report (receipt) before code:
   keep/wire/drop per module with evidence. Only wire what has tests.

4. **F2/F13 weights + F8/F10/F12/F14.** Weights need an A3-SCORE decision on
   record — without it, touch nothing. Paper items need the papers.

5. **O-2.** CLOSED (obsolete under Public-unlimited). Reopen only with a
   measured binding Public quota.

### Agent 3 backlog (admitted)

1. **Alert surfacing — the known orphan gap.** Backend emits rules the UI
   never renders. Priority order with exact strings to wire:
   a. `TOXIC_FLOW` (new) + `GAMMA_FLIP` proximity (new): pills/badges in the
      Blademap feed AND heatseeker; reuse the SIDE/SIGNAL dash pattern for
      unknowns; copy keeps proxy disclaimers (F5/F6/F11/F19 style — no
      invented precision, heuristic labels).
   b. `VEX_WALL` (+formed/broken), `CHARM_PIN` (+formed/shifted): same
      treatment. (UI `vex` viewMode and `CHARM_PINNING` are DIFFERENT rules —
      do not conflate; read both sides first.)
   c. `GAMMA_FLIP_PROXIMITY`, `VOLUME_SPIKE` (alert_engine), `CLUSTER`
      (flow_alerts): assess producer liveness first (fire them in tests?);
      surface only live ones, report dead ones instead of wiring corpses.
   d. Do NOT invent UI for `FOLLOW`/`SOURCE` (UI-only, no backend producer).
   Tests for every badge (incl. no-quote/unknown rendering); full-suite green.
    Status: **DONE via PR48** (a3/alert-surfacing, head `9eb5e7d567f56180a25723bb07b363a0562149a5`, PR48 is **MERGED** to main `12c53d8` 2026-09-09T23:19:09Z on GitHub [#48](https://github.com/mrbeast1179-sketch/floww/pull/48)). E4-48d
    APPROVED (2026-09-09 re-review: 49/49 green; frontend-only; MERGED to main
    `12c53d8` 2026-09-09T23:19:09Z).
    Receipt: evidence/E4-48d-PR48-rereview.md.

  1b. **Alert-engine mapper (1c)** — `alertEngineBadges.js` (11 catalog types,
    TDD RED-first, 17 tests) + CLUSTER badge in exposureBadges (feed-proven).
    No UI wiring yet (alert_engine serves via /api/alerts/*, design = 1d).
    Status: **DONE via PR49** (a3/alert-engine-badges, head `8ed71c285`, PR49 is **MERGED** (closed 2026-09-09T17:08:59Z, merge commit `480e953`), now part of `a3/alert-surfacing` parent lineage). 29/29 green. E4-49 verdict: APPROVED-conditional (wiring gap holds; 1c mapper unrendered — 108-line new file exists in main's merge tree but no render call site in ExposureStrip/Blademap). Receipt: evidence/E4-49-PR49-review.md. Note: E4-48d-PR48-rereview.md also carries the PR49 section; E4-48c receipt (73533e1 state) is superseded.
- KIND_TITLES kind-aware refinement: **NOW DELIVERED via PR55** (MERGED 2026-09-10T02:44:15Z, merge commit `7a0a16aed`). KIND_TITLES + `exposureKindOf` + two-arg `exposureBadgeFor` + 5 pin tests now in main (`2c33de0`). See E4-55 receipt. This closes the orphan gap documented in E4-48d/E4-49.

2. **XH-1** — UI quote/side/sweep/block copy preserves unknowns, labels proxies.
   Status: **ADMITTED** — task card `XH-1.md` written; discovery phase pending
   agent-3 boot + Agent-1 go-ahead.

3. **X2** — mounted Phase9 consumer + responsive acceptance.
   Status: **ADMITTED** — task card `X2.md` written; discovery phase pending
   agent-3 boot + Agent-1 go-ahead.

4. **X4** — poll/remount/race/partial-data stability.
   Status: **ADMITTED** — task card `X4.md` written; discovery phase pending
   agent-3 boot + Agent-1 go-ahead.

5. **RT-1 / RH-2** — only on fresh Agent-1 contracts.

### Agent 4 standing review

- PR44 G3-salvage: E4-44 APPROVED-conditional, MERGED to main 56cfff2. Witness
  gate pending; re-verify at any new head before any witnessed attempt.
- PR48 alert-surfacing: E4-48d APPROVED at `2f57bea3d56a075692339051525cb73d97d99513` (49/49 green; frontend-only; MERGED to main `12c53d8` 2026-09-09T23:19:09Z on GitHub [#48](https://github.com/mrbeast1179-sketch/floww/pull/48)). PR48 merges WITHOUT KIND_TITLES to main — only 10-line CLUSTER addition landed from the PR49 merge commit; the 108-line alertEngineBadges.js (PR49 payload) is in the merge tree but not wired to any UI call site (1c mapper unrendered). KIND_TITLES (PR50 payload) exists only in `origin/a3/pr48-semantic-fixes`.
- PR49 alert-engine-badges: E4-49 APPROVED-conditional at `8ed71c2857030fc2e132c160e4b65763d175379d` (29/29 green; MERGED (closed 2026-09-09T17:08:59Z, merge commit `480e953`); PR49 is **MERGED** on GitHub [#49](https://github.com/mrbeast1179-sketch/floww/pull/49)); now part of `a3/alert-surfacing` parent lineage. Wiring gap holds (1c mapper unrendered).
- PR50 kind-aware badge copy: **MERGED** (closed 2026-09-09T15:35:57Z into a3/alert-surfacing, merge commit 81255b8 **ORPHANED**). KIND_TITLES is **NOT** in main (verified: 0 occurrences in origin/main exposureBadges.js), not in a3/alert-surfacing. Exists only in origin/a3/pr48-semantic-fixes for potential re-merge PR. No longer a stacked PR — merged separately but content not delivered to main.
- **PR54 order-safety**: MERGED to main `d5dbd7d` (2026-09-10T01:44:39Z). Idempotency key reuse + paper-order venue-idempotent retries. No agent-4 review gate (Nav/owner merged).
- **PR56 P2 dependency pins**: MERGED to main `d5dbd7d` (2026-09-10T02:15:08Z). FastAPI 0.141.1 + Starlette 1.6.0 + PyMongo 4.6.3 + cryptography 50.0.1 + 4 route-inventory assertion adaptations. Nav/owner merged.
- **PR55 kind-aware badge truth (OPEN)**: E4-55 APPROVED at `7481f72` (60/60 focused green, 5 TDD tests Red→Green, source-verified KIND_TITLES content; full-suite 66/531 green re-confirmed at exact head — see receipt). 5 frontend files. CI: ruff+frontend-build+backend-tests all green at PR head. REST: agent-4 full-suite OK; CI is the merge gate.
- Never re-audit merged heads at unchanged state (PR28-43, PR45-46).
- Three alert pipelines exist (alert_engine, exposure_alerts, flow_alerts)
  with overlapping rule names (`CHARM_PIN` ≠ `CHARM_PINNING`,
  `GAMMA_FLIP` ≠ `GAMMA_FLIP_PROXIMITY`). Any review touching alerts must
  name WHICH pipeline and cite the exact rule const.

## Phase9 honesty disposition (current)

DONE (in main): F1, F3, F4, F7 (F0 wave, PR35); F5, F6, F11, F17, F19 (PR40);
F9a/F9b (PR43, source-verified); F2-label/F13-label (PR43, weights untouched);
F15 (contract note); F16 (verified present, no change).

OPEN: F2-strip + F13 down-weight (need weights/product call),
F8/F10/F12/F14 (need paper-content verification).

All F1–F19 disposition is now recorded; no bulk "honesty fixed" commit
prohibition needed — each ID has its own status.

## Recent Heatseeker/ticker decision boundary

RH-1 questions are SUPERSEDED by the take-over work (PR33 T1-only, PR34 H1,
PR36 H2, PR39 provider stack). The T1 contract is law: one deduped universe
(`tickerUniverse.js`), capped render (RENDER_CAP), filter-before-slice search,
wrap arrows, active-item reveal, full-list reachability. Any unit regressing it
is wrong — revert.

## Proprietary-data program

The GSD discovery map is `PROPRIETARY-DATA-DISCOVERY-MAP.md`. It is not ready for
specification until D-1 through D-6 close. After graduation, expected one-day slices
are: normalized contracts; provider capture; sequencing/gap recovery; raw+normalized
replay; Public shadow comparator; observability/budgets; consumer router; UI provenance;
chaos/performance audit; staged cutover/rollback. These names are planning candidates,
not filed contracts until the discovery process approves them.

## Separate `swarmSPX` program

`/Users/nav/GitHub/swarmSPX` has its own Git history, configuration, tests, provider
