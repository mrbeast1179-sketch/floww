# Recovery queue v2 — current state (main 56cfff2)

`QUEUE.md` retains the full P1–P7, D1–D7, X1–X5, and E1–E5 contracts. This
file tracks current candidate heads and the live backlog. Status is evidence-based
as of 2026-09-08.

## CLOSED as a merge queue

Main is `56cfff2`. Merged, in order: PR28 (D7 parity), PR29 (X1 journal),
PR30 (P1 silent-except gate), PR31 (A3 conviction wiring), PR33 (T1-only),
PR34 (H1 strike-truth fixture), PR35 (F0 wave + clock fix), PR36 (H2-partial),
PR37 (GEX date-string fix), PR38 (dead-code removal + kanban datetime fix),
PR39 (provider cap + deepen + enrich, merged by Nav), PR40 (honesty labels),
PR41 (strike floor), PR42 (T2 full universe + order-key 401 fix), PR43
(honesty citations), PR45 (TOXIC_FLOW alerts), PR46 (GAMMA_FLIP alerts),
PR47 (numba charm vec + liquidity-stress alerts).
One open PR: PR48 (a3/alert-surfacing, head f25de2e31, E4-48b APPROVED — rework
verified 49/49, merge needs CI green + Nav call). Stacked PR49 (head 2f19bb4,
needs rebase onto f25de2e31).
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
    Status: **DONE via PR48** (a3/alert-surfacing, head f25de2e31). E4-48b
    APPROVED (2026-09-09 re-review: all 3 rework defects resolved, 49/49
    green; merge needs CI green + Nav call). Receipt:
    evidence/E4-48b-PR48-rereview.md (live; E4-48 + E4-48-PR48-review.md cover
    the superseded head 4d7172e).

  1b. **Alert-engine mapper (1c)** — `alertEngineBadges.js` (11 catalog types,
    TDD RED-first, 17 tests) + CLUSTER badge in exposureBadges (feed-proven).
    No UI wiring yet (alert_engine serves via /api/alerts/*, design = 1d).
    Status: **DONE via PR49** (a3/alert-engine-badges, head 2f19bb4, stacked
    on PR48 — do NOT merge before #48). 68/68 green. E4-49 verdict: REWORK
    (2 title fixes + wire the mapper or hold for wiring unit) → titles FIXED
    in 2f19bb4 (TDD RED-first, +2 copy-pin tests); wiring HELD for 1d by
    design (/api/alerts/* vs feed merge is new scope). Receipt:
    evidence/E4-49-PR49-review.md.

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
- PR48 alert-surfacing: E4-48b APPROVED at f25de2e31 (rework verified 49/49; merge needs CI green + Nav call).
- PR49 alert-engine-badges: E4-49 APPROVED-conditional at 2f19bb4 BUT stacked on old PR48 head — needs rebase onto f25de2e31, then re-verify. Merge held until then.
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
