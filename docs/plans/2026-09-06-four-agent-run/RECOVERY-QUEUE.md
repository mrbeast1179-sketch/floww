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
One open PR: none (PR44 merged main 56cfff2 2026-09-08T11:48:51Z).
6 superseded branches deleted after patch-id proof (product identical to main;
docs in archive). Every merge verified: green required CI on the merged head +
local reproduction where applicable. Full receipt trail in GSD-PASSES.md
take-over section + lane receipts + evidence/DEEP-SWEEP-2026-09-08.md.

## Remaining (gated — no executable builder work left ungated)

| ID | State | Gate |
|---|---|---|---|
| O-2 reuse-or-remove | QUEUED with spec | Cross-key cache surgery or swing-depth product call — Nav's |
| O-4/O-5 failover order | QUEUED with spec | Provider sandbox + product sign-off — Nav's |
| P2 upgrades | Baseline KNOWN (11 advisories) | pymongo/starlette/nltk bumps need resolver pass — Nav's |
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

### Agent 3 backlog (queued, not admitted)

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

2. **XH-1** — UI quote/side/sweep/block copy preserves unknowns, labels proxies.
3. **X2** — mounted Phase9 consumer + responsive acceptance.
4. **X4** — poll/remount/race/partial-data stability.
5. **RT-1 / RH-2** — only on fresh Agent-1 contracts.

### Agent 4 standing review

- PR44 G3-salvage: prior verdict E4-44 APPROVED-conditional, merge gated on
  the external witness. Standing job: confirm it stays green and
  unmerged until witnessed; re-verify at any new head.
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
policy, paper engine, synthetic backtest concerns, and UI/alert surfaces. It receives a
separate GSD map after its truth audit. No Floww worker deletes Schwab or changes that
repo from a Floww task card. Shared ideas cross repositories only through an explicit
interface/spec, never by copying an entire provider or agent framework.
## Take-over loop 2 — provider directive + sweep (2026-09-08)

Owner directive: Public API (unlimited) is primary; cvserver (20 req/hr) is
scarce failover; small-stock strike coverage must improve with real rows only.

LIVE KYTX DIAGNOSIS (backend on merged main + PR39 code, real keys):
Public 400s KYTX expirations (symbol unsupported — vendor limit, not our bug);
cvserver 429-paused (vendor throttle state; our pause handling correct);
yfinance fallback had all 8 strikes but the display band cut to 3. Vendor HAS
the data — our band was the limiter. VALIDATED FIX live: KYTX now shows all
8 strikes [2.5–20.0] with gex on every row (source cvserver after its 429
cleared; deepen + enrich both fired per logs).

- PR37 MERGED: GEX date-string crash fix (`_parse_expiry`, unskipped linearity
  pin, golden oracle green; silent-except justifications added per P1 gate).
- PR38 MERGED: dead-code removal (Movers.jsx, finnhub_api shim) + kanban
  datetime fix (un-xfailed).
- PR39 MERGED by Nav (`5771dfc`, cap+deepen+enrich). Lesson logged: merged PRs
  don't track later branch pushes and fire no PR CI — verify `headRefOid`
  before assuming a push reached its PR.
- PR40 MERGED (F5/F6/F11/F17/F19 honesty wave; F16 verified present).
- PR41 MERGED (strike floor; KYTX live-validated 8 strikes).
- 61-ref archaeology: 6 superseded branches deleted after patch-id proof;
  G3 + swarm-sizing rescue backlogs specced (evidence/DEEP-SWEEP-2026-09-08.md).
- Baselines @ `56cfff2`: backend 5048, frontend 62/479, ruff clean.

## Take-over loop 3 — honesty + G3 (2026-09-08)

- PR43 MERGED: F9a/F9b source-verified (RFS 2021, Pan-Poteshman "in"), F2/F13 label-only. Weights + paper-content citations untouched.
- PR44 OPEN (`astra/g3-paper-loop`, DO NOT MERGE): G3 product hunks split
  from ledger docs (5 commits squashed, LEDGER dropped); 109 offline green.
  Needs Agent-4 review + external G-WITNESS gate.
- F15 closed via scanLogic JSDoc contract note. F16 verified present.
  Skipped with rationale: F8/F10/F12/F14 (paper-content), F18 (satisfied).
- O-2 CLOSED obsolete-under-directive; O-4 SUPERSEDED by provider directive;
  O-5 SATISFIED (deepen reuses merged path, labels follow winner). Rationale
  in agent-2-backend/receipts/H2.md.

## Take-over loop 4 — prop-desk edges (2026-09-08)

## Take-over loop 5 — second edge: flip proximity (2026-09-08)

## Take-over loop 6 — Agent-2 backlog (2026-09-08)

- PR47 MERGED: numba charm vec (identical totals, 1.7x on 15k chains) +
  LIQUIDITY_STRESS rule (Kyle+Amihud ILLIQUID agreement, registry fed per
  snapshot, read-only snapshots, cold-silent, fail-open). Trade-level
  liquidity_metrics variants deliberately unused (feed mismatch, recorded).
- OFI assessment (receipt): multi_level_ofi, composite_flow_score,
  hmm_regime, chain_replay all TESTED + WIRED — keep, nothing to do.
- Agent-2 backlog now exhausted except gated items (F-weights need A3-SCORE,
  paper items need papers). Builder lane parked clean.

- PR46 MERGED: GAMMA_FLIP rule live on main.

Owner directive: build like a prop desk (VPIN toxicity, higher-order Greeks,
dealer positioning), unlimited data, paper only, everything committed.

- Recon: orderflow (29 analytics incl. VPIN/Kyle/Amihud, Almgren-Chriss, 19
  pattern flags, dark pool), OptionStratLib (full Greeks incl.
  Vanna/Vomma/Veta/Charm/Color, vol surfaces, decimal precision, identity
  tests). Transferable (no Rust rewrite): VPIN alerts, unused numba Greeks,
  Kyle/Amihud regime, gamma-flip approach alerts.
- PR45 MERGED: TOXIC_FLOW rule live on main.
- Hygiene: 8 merged branches verified-in-main and deleted
  (trade-fire, sparse-chain-public/v2, honesty-citations/labels,
  cleanup-dead-code, bugfix-gex-expiry, t1-only). Stale worktrees removed;
  active lanes only remain.

## Honesty backlog (fix-queue F-IDs vs landed work)

DONE (in main): F1, F3, F4, F7 (F0 wave); F5, F6, F11, F17, F19 (PR40);
F9a/F9b (PR43, source-verified); F2-label/F13-label (PR43, weights untouched);
F15 (contract note); F16 (verified present, no change).
OPEN: F2-strip + F13 down-weight (need weights/product call),
F8/F10/F12/F14 (need paper-content verification).

## Stop conditions

- Provider stream returns no bytes or HTTP 429 without a durable boot/checkpoint.
- Branch ancestry or diff includes files outside the task lease.
- A task needs a frozen file without a recorded waiver.
- A data field's semantics, licensing, entitlement, or timestamp are unresolved.
- A worker would hide a failing check, fabricate a live witness, or infer merge/deploy.
- Two builders need the same whole file.
